"""
VLM inference worker for Bacchus.

Handles image+text inference using OpenVINO GenAI VLMPipeline on a background thread.
Supports multi-turn context replay for tool-call iterations.
"""

import logging
from typing import Any, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class VLMInferenceWorker(QThread):
    """
    Background thread for VLM (vision-language model) inference.

    Uses VLMPipeline.start_chat / generate / finish_chat.

    For multi-turn tool call iterations, prior conversation turns are replayed
    via generate() calls (outputs discarded) to rebuild the KV-cache context before
    the final generate() call that produces the actual response.
    """

    generation_completed = pyqtSignal(str)   # Emits full response text
    generation_failed = pyqtSignal(str)       # Emits error message
    image_described = pyqtSignal(int, str)    # Emits (message_id, description) after auto-describe
    token_generated = pyqtSignal(str)         # Emits each token (streaming response phase only)

    def __init__(
        self,
        vlm_pipeline: Any,
        system_message: str,
        messages: List[Any],
        max_tokens: int = 512,
        temperature: float = 0.7,
        generation_config: Optional[Any] = None,
        streaming: bool = False,
        parent=None,
    ):
        """
        Initialize VLM inference worker.

        Args:
            vlm_pipeline: Loaded VLMPipeline instance.
            system_message: Full system prompt injected via start_chat.
            messages: List of Message dataclass objects (role, content, image_path).
                      Must have at least one element.
            max_tokens: Maximum tokens to generate for the final turn.
            temperature: Sampling temperature for unstructured generation.
            generation_config: Optional pre-configured GenerationConfig (e.g. decision
                               schema for structured tool-call decisions).  When provided,
                               it is used for the final generate() call only.
            streaming: If True, emit token_generated for each decoded token (plain gen only).
            parent: Parent QObject.
        """
        super().__init__(parent)
        self.vlm_pipeline = vlm_pipeline
        self.system_message = system_message
        self.messages = messages
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.generation_config = generation_config
        self.streaming = streaming

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_image_tensor(path: str) -> Any:
        """Load an image file and return a 4D ov.Tensor (1, H, W, 3) uint8.

        Resizes to at most 448x448 (preserving aspect ratio) as required by
        the NPU VLMPipeline vision encoder.
        """
        import numpy as np
        import openvino as ov
        from PIL import Image as PILImage

        img = PILImage.open(path).convert("RGB")
        img.thumbnail((448, 448), PILImage.LANCZOS)
        arr = np.array(img, dtype=np.uint8)
        arr = arr.reshape(1, arr.shape[0], arr.shape[1], 3)  # (1, H, W, 3)
        return ov.Tensor(arr)

    # ------------------------------------------------------------------
    # QThread.run
    # ------------------------------------------------------------------

    def run(self):
        """Run VLM inference, replaying history then generating the final turn."""
        try:
            import openvino_genai as ov_genai

            logger.debug(f"VLM system message length: {len(self.system_message)} chars")

            # -- Auto-describe image if not yet described ----------------
            current = self.messages[-1]
            if current.image_path and not current.image_description:
                self._auto_describe(ov_genai, current)

            self.vlm_pipeline.start_chat(self.system_message)
            try:
                response_text = self._generate_with_history(ov_genai)
            finally:
                self.vlm_pipeline.finish_chat()

            logger.info(f"VLM generation completed, {len(response_text)} chars")
            self.generation_completed.emit(response_text)

        except Exception as e:
            logger.error(f"VLM inference failed: {e}", exc_info=True)
            self.generation_failed.emit(str(e))

    # ------------------------------------------------------------------
    # image auto-description
    # ------------------------------------------------------------------

    def _auto_describe(self, ov_genai, message) -> None:
        """Generate a text description of the image attached to *message* and emit image_described.

        Uses a short isolated start_chat/finish_chat session so it does not pollute the
        main conversation KV-cache.
        """
        import os
        if not os.path.isfile(message.image_path):
            logger.warning(f"Auto-describe: image file not found: {message.image_path}")
            return
        try:
            tensor = self._load_image_tensor(message.image_path)
            describe_prompt = (
                "Describe this image in detail. "
                "Preserve all visible text, numbers, labels, data, and key visual elements exactly. "
                "If this is a document or screenshot, transcribe all readable text."
            )
            cfg = ov_genai.GenerationConfig()
            cfg.max_new_tokens = 256
            cfg.do_sample = False

            self.vlm_pipeline.start_chat("")
            try:
                result = self.vlm_pipeline.generate(describe_prompt, image=tensor, generation_config=cfg)
                description = result.texts[0].strip()
            finally:
                self.vlm_pipeline.finish_chat()

            logger.info(f"Auto-described image for message {message.id}: {len(description)} chars")
            self.image_described.emit(message.id, description)
            # Patch in-memory so the same worker instance sees the description during replay
            message.image_description = description
        except Exception as e:
            logger.warning(f"Auto-describe failed for {message.image_path}: {e}")

    def _generate_with_history(self, ov_genai) -> str:
        """
        Replay prior conversation turns then generate a response for the last turn.

        VLMPipeline manages its own chat template and KV-cache via alternating
        start_chat / generate / generate / … / finish_chat calls.  Each generate()
        adds one user→assistant exchange to the cache.

        Strategy
        --------
        - All messages except the last are "prior turns" replayed to rebuild context.
          For user/system messages we call generate() with a small max_new_tokens
          budget and discard the output — we only need the KV-cache state.
          Assistant messages are skipped because the KV-cache already holds them as
          the output of the preceding generate() call.
        - The final message is generated with the real generation config / token budget.
        - Images are attached to every user message that carries a valid image_path on disk.
        """
        import os
        prior = self.messages[:-1]
        current = self.messages[-1]

        # ---- replay prior turns ----------------------------------------
        for msg in prior:
            if msg.role == "assistant":
                # Already in KV cache as output of the preceding generate() call.
                continue
            if msg.role not in ("user", "system"):
                continue

            imgs = []
            if msg.role == "user" and msg.image_path and os.path.isfile(msg.image_path):
                try:
                    imgs = [self._load_image_tensor(msg.image_path)]
                    logger.debug(f"Replay: loaded image {msg.image_path}")
                except Exception as e:
                    logger.warning(f"Replay: failed to load image {msg.image_path}: {e}")

            # Small budget — we only need the KV-cache side-effect.
            replay_config = ov_genai.GenerationConfig()
            replay_config.max_new_tokens = 128
            replay_kwargs: dict = {"generation_config": replay_config}
            if imgs:
                replay_kwargs["image"] = imgs[0]
            self.vlm_pipeline.generate(msg.content or "", **replay_kwargs)
            logger.debug(f"Replayed prior {msg.role} turn for KV cache")

        # ---- final turn ------------------------------------------------
        imgs = []
        if current.role == "user" and current.image_path and os.path.isfile(current.image_path):
            try:
                imgs = [self._load_image_tensor(current.image_path)]
                logger.info(f"Loaded image for final turn: {current.image_path}")
            except Exception as e:
                logger.warning(f"Failed to load image {current.image_path}: {e}")

        if self.generation_config is not None:
            final_config = self.generation_config
        else:
            final_config = ov_genai.GenerationConfig()
            final_config.max_new_tokens = self.max_tokens
            if self.temperature > 0:
                final_config.do_sample = True
                final_config.temperature = self.temperature
            else:
                final_config.do_sample = False

        generate_kwargs: dict = {"generation_config": final_config}
        if imgs:
            generate_kwargs["image"] = imgs[0]
        if self.streaming:
            def _streamer(token: str) -> bool:
                self.token_generated.emit(token)
                return False
            generate_kwargs["streamer"] = _streamer
        result = self.vlm_pipeline.generate(current.content or "", **generate_kwargs)
        return result.texts[0]
