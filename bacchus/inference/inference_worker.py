"""
Inference worker for running LLM generation in background thread.

Uses OpenVINO GenAI LLMPipeline for text generation on NPU.
"""

import logging
from typing import Any, Optional

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class InferenceWorker(QThread):
    """
    Background thread for LLM inference.

    Emits tokens as they are generated (streaming).
    """

    token_generated = pyqtSignal(str)  # Emits each token
    generation_completed = pyqtSignal(str)  # Emits full response
    generation_failed = pyqtSignal(str)  # Emits error message

    def __init__(
        self,
        llm_pipeline: Any,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        generation_config: Optional[Any] = None,
        parent=None
    ):
        """
        Initialize inference worker.

        Args:
            llm_pipeline: OpenVINO GenAI LLMPipeline
            prompt: Full prompt to send to model
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            generation_config: Optional pre-configured GenerationConfig (for structured output)
            parent: Parent QObject
        """
        super().__init__(parent)
        self.llm_pipeline = llm_pipeline
        self.prompt = prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.generation_config = generation_config  # Pre-configured for structured output
        self._cancelled = False

    def run(self):
        """Run inference in background thread."""
        if self.llm_pipeline is None:
            self.generation_failed.emit("No model loaded")
            return

        logger.info(f"Starting inference (max_tokens={self.max_tokens}, temp={self.temperature})")
        logger.debug(f"Prompt length: {len(self.prompt)} chars")

        try:
            import openvino_genai as ov_genai

            # Use pre-configured config if provided (for structured output)
            # Otherwise create standard config
            if self.generation_config is not None:
                config = self.generation_config
                logger.info("Using pre-configured GenerationConfig (structured output)")
            else:
                # Create standard generation config
                config = ov_genai.GenerationConfig()
                config.max_new_tokens = self.max_tokens

                # Set temperature (if supported)
                if self.temperature > 0:
                    config.do_sample = True
                    config.temperature = self.temperature
                else:
                    config.do_sample = False

            logger.info("Starting generation on NPU...")

            def _streamer(token: str) -> bool:
                if self._cancelled:
                    return True
                self.token_generated.emit(token)
                return False

            try:
                # Stream tokens when not using structured output (response phase)
                streamer = _streamer if self.generation_config is None else None
                result = self.llm_pipeline.generate(self.prompt, config, streamer=streamer)
            except Exception as gen_error:
                # If structured generation fails, try without it
                if self.generation_config is not None:
                    logger.warning(f"Structured generation failed: {gen_error}")
                    logger.warning("Falling back to standard generation without schema constraints")

                    # Recreate config without structured output
                    fallback_config = ov_genai.GenerationConfig()
                    fallback_config.max_new_tokens = self.max_tokens
                    if self.temperature > 0:
                        fallback_config.do_sample = True
                        fallback_config.temperature = self.temperature
                    else:
                        fallback_config.do_sample = False

                    result = self.llm_pipeline.generate(self.prompt, fallback_config)
                else:
                    raise

            if not self._cancelled:
                # Result is the generated text
                response = str(result)
                self.generation_completed.emit(response)
                logger.info(f"Inference completed, response length: {len(response)} chars")
            else:
                logger.info("Inference was cancelled")

        except Exception as e:
            logger.error(f"Inference failed: {e}", exc_info=True)
            self.generation_failed.emit(str(e))

    def cancel(self):
        """Cancel inference."""
        self._cancelled = True
        logger.info("Inference cancellation requested")
