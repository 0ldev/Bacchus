"""
Model manager for Bacchus.

Handles loading, unloading, and switching between OpenVINO models.
Uses OpenVINO GenAI for LLM inference on NPU.
"""

import logging
from pathlib import Path
from typing import Optional, Any

import openvino as ov

from bacchus import constants
from bacchus.config import get_cache_dir, load_settings

logger = logging.getLogger(__name__)


class ModelManager:
    """
    Manages OpenVINO model loading and inference.

    Uses OpenVINO GenAI LLMPipeline for chat models on NPU.
    """

    def __init__(self):
        """Initialize model manager."""
        self.core = ov.Core()

        # Current loaded models
        self._current_chat_model: Optional[str] = None
        self._current_embedding_model: Optional[str] = None

        # LLM Pipeline (from openvino_genai)
        self._llm_pipeline: Optional[Any] = None

        # VLM Pipeline (for vision-language models)
        self._vlm_pipeline: Optional[Any] = None

        # Compiled models (for embeddings)
        self._embedding_compiled_model: Optional[ov.CompiledModel] = None

        # Device to use (NPU required)
        self._device = self._detect_device()
        self._active_device: str = self._device

        logger.info(f"Model manager initialized, using device: {self._device}")

    def _detect_device(self) -> str:
        """
        Detect available device for inference.

        Returns:
            Device name: "NPU" if available, else "CPU"
        """
        available_devices = self.core.available_devices
        logger.info(f"Available OpenVINO devices: {available_devices}")

        if "NPU" in available_devices:
            logger.info("NPU detected and will be used for inference")
            return "NPU"
        else:
            logger.warning("NPU not detected, falling back to CPU")
            return "CPU"

    def has_npu(self) -> bool:
        """Check if NPU is available."""
        return self._device == "NPU"

    def get_active_device(self) -> str:
        """Get the device currently used for the loaded model."""
        return self._active_device

    def get_available_chat_models(self) -> list[str]:
        """
        Get list of downloaded chat models.

        Returns:
            List of model folder names
        """
        if not constants.MODELS_DIR.exists():
            return []

        chat_models = []

        # Check all models defined in CHAT_MODELS constant
        for folder_name in constants.CHAT_MODELS.keys():
            model_path = constants.MODELS_DIR / folder_name
            if self._verify_model(model_path):
                chat_models.append(folder_name)

        return sorted(chat_models)

    def _verify_model(self, model_path: Path) -> bool:
        """
        Verify that model files exist.

        Supports two layouts:
        - Standard text models:  openvino_model.xml / .bin at root
        - VL / multimodal models: openvino_language_model.xml / .bin at root

        Args:
            model_path: Path to model directory

        Returns:
            True if model files are present
        """
        if not model_path.exists():
            return False

        # Standard text model
        if (model_path / "openvino_model.xml").exists():
            return (model_path / "openvino_model.bin").exists()

        # VL / multimodal model
        if (model_path / "openvino_language_model.xml").exists():
            return (model_path / "openvino_language_model.bin").exists()

        return False

    def _is_vl_model_path(self, model_path: Path) -> bool:
        """
        Detect whether a model directory is a vision-language model.

        VLM exports use openvino_language_model.xml at the root instead of
        the standard openvino_model.xml used by text-only LLMs.

        Args:
            model_path: Path to model directory

        Returns:
            True if VLM layout is detected
        """
        return (model_path / "openvino_language_model.xml").exists()

    def load_chat_model(self, model_folder_name: str) -> bool:
        """
        Load a chat model for inference using OpenVINO GenAI.

        Args:
            model_folder_name: Name of model folder (e.g., "phi-3.5-mini")

        Returns:
            True if load succeeded, False otherwise
        """
        model_path = constants.MODELS_DIR / model_folder_name

        if not self._verify_model(model_path):
            logger.error(f"Model not found or incomplete: {model_path}")
            return False

        logger.info(f"Loading chat model: {model_folder_name}")

        try:
            # Import openvino_genai
            import openvino_genai as ov_genai
            import sys

            # Unload current model if any
            if self._llm_pipeline is not None or self._vlm_pipeline is not None:
                logger.info(f"Unloading previous model: {self._current_chat_model}")
                self._llm_pipeline = None
                self._vlm_pipeline = None

            # Get device (NPU for optimal performance)
            device = self._device

            # Detect VLM model by file layout
            is_vl = self._is_vl_model_path(model_path)

            # Create LLMPipeline - this handles all the complexity
            if is_vl:
                logger.info(f"Detected VLM model layout for {model_folder_name}")
            else:
                logger.info(f"Creating LLMPipeline for {device}...")

            # Context size: read from per-model user setting, defaulting to 16K
            from bacchus.constants import DEFAULT_CONTEXT_SIZE
            settings = load_settings()
            desired_context = (
                settings.get("model_context_sizes", {})
                .get(model_folder_name, DEFAULT_CONTEXT_SIZE)
            )
            logger.info(f"Using context size {desired_context} for {model_folder_name}")

            # Each (model, context_size) pair gets its own cache subdirectory.
            # NPU compiles a separate binary per MAX_PROMPT_LEN — using the same
            # cache dir for different context sizes would serve the wrong binary.
            cache_dir = get_cache_dir() / f"{model_folder_name}_{desired_context}"
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Check if a compiled binary for this exact (model, context) already exists
            model_cache_exists = any(cache_dir.iterdir())

            # Print user-friendly message
            print(f"\n  Loading {model_folder_name} on {device}...")
            if model_cache_exists:
                print(f"  (Using cached compiled model — {desired_context} token context)\n")
            else:
                print(f"  (First load — compiling for {desired_context} token context, "
                      f"may take 1-2 minutes)\n")
            sys.stdout.flush()
            sys.stderr.flush()

            # Force log flush
            for handler in logging.getLogger().handlers:
                handler.flush()

            if is_vl:
                # VLMPipeline for vision-language models.
                #
                # MAX_PROMPT_LEN is passed as a flat kwarg — this works because
                # the patched openvino-genai (commit 3366e1b, issue #3366) correctly
                # routes it only to the NPU LM subgraph and not to the CPU vision encoder.
                if device == "NPU":
                    vl_config = {
                        "CACHE_DIR": str(cache_dir),
                        "MAX_PROMPT_LEN": desired_context,
                    }
                    logger.info(
                        f"Creating VLMPipeline on NPU with MAX_PROMPT_LEN={desired_context}..."
                    )
                else:
                    # CPU/GPU: dynamic shapes, no context limit needed
                    vl_config = {"CACHE_DIR": str(cache_dir)}
                    logger.info(f"Creating VLMPipeline on {device}...")

                pipeline = ov_genai.VLMPipeline(str(model_path), device, **vl_config)
                print(f"  VLM model loaded successfully on {device}!\n")
                logger.info("VLMPipeline created successfully")
                self._vlm_pipeline = pipeline
                self._llm_pipeline = None
                self._active_device = device
            else:
                config = {
                    "CACHE_DIR": str(cache_dir),
                }

                # NPU-specific configuration: MAX_PROMPT_LEN is a compile-time parameter
                if device == "NPU":
                    config["MAX_PROMPT_LEN"] = desired_context
                    logger.info(f"Loading {model_folder_name} with {desired_context} token context window...")
                else:
                    logger.info(f"Loading {model_folder_name} on {device} (CPU fallback)...")

                # Create pipeline with specified device
                pipeline = ov_genai.LLMPipeline(
                    str(model_path),
                    device,
                    **config
                )

                print(f"  Model loaded successfully on {device}!\n")
                logger.info("LLMPipeline created successfully")
                self._llm_pipeline = pipeline
                self._vlm_pipeline = None
            self._current_chat_model = model_folder_name
            self._active_device = device

            logger.info(f"Successfully loaded chat model: {model_folder_name} on {device}")

            return True

        except ImportError as e:
            logger.error(f"OpenVINO GenAI not installed: {e}")
            logger.error("Please install with: pip install openvino-genai")
            return False
        except Exception as e:
            logger.error(f"Failed to load chat model {model_folder_name}: {e}", exc_info=True)
            self._llm_pipeline = None
            self._current_chat_model = None
            return False

    def load_embedding_model(self) -> bool:
        """
        Load the embedding model for RAG.

        Returns:
            True if load succeeded, False otherwise
        """
        model_folder_name = "all-minilm-l6-v2"
        model_path = constants.MODELS_DIR / model_folder_name

        if not self._verify_model(model_path):
            logger.warning(f"Embedding model not found: {model_path}")
            return False

        logger.info(f"Loading embedding model: {model_folder_name}")

        try:
            # Read model
            xml_file = model_path / "openvino_model.xml"
            model = self.core.read_model(str(xml_file))

            # Compile model (embeddings use CPU)
            logger.info(f"Compiling embedding model for CPU...")
            compiled_model = self.core.compile_model(model, "CPU")

            # Store compiled model
            self._embedding_compiled_model = compiled_model
            self._current_embedding_model = model_folder_name

            logger.info(f"Successfully loaded embedding model: {model_folder_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}", exc_info=True)
            self._embedding_compiled_model = None
            self._current_embedding_model = None
            return False

    def unload_chat_model(self):
        """Unload the current chat model."""
        if self._llm_pipeline is not None or self._vlm_pipeline is not None:
            logger.info(f"Unloading chat model: {self._current_chat_model}")
            self._llm_pipeline = None
            self._vlm_pipeline = None
            self._current_chat_model = None

    def get_current_chat_model(self) -> Optional[str]:
        """Get the currently loaded chat model name."""
        return self._current_chat_model

    def get_current_embedding_model(self) -> Optional[str]:
        """Get the currently loaded embedding model name."""
        return self._current_embedding_model

    def is_chat_model_loaded(self) -> bool:
        """Check if a chat model is loaded."""
        return self._llm_pipeline is not None or self._vlm_pipeline is not None

    def is_vl_pipeline_loaded(self) -> bool:
        """Check if a VLM pipeline (vision-language model) is currently loaded."""
        return self._vlm_pipeline is not None

    def get_vlm_pipeline(self) -> Optional[Any]:
        """Get the VLM pipeline for vision-language inference."""
        return self._vlm_pipeline

    def is_embedding_model_loaded(self) -> bool:
        """Check if embedding model is loaded."""
        return self._embedding_compiled_model is not None

    def get_llm_pipeline(self) -> Optional[Any]:
        """Get the LLM pipeline for inference."""
        return self._llm_pipeline

    def get_chat_compiled_model(self) -> Optional[ov.CompiledModel]:
        """Get the compiled chat model for inference (deprecated, use get_llm_pipeline)."""
        # For backwards compatibility - return None as we use LLMPipeline now
        return None

    def get_embedding_compiled_model(self) -> Optional[ov.CompiledModel]:
        """Get the compiled embedding model for inference."""
        return self._embedding_compiled_model

    def load_default_model(self) -> Optional[str]:
        """
        Load default model based on settings and availability.

        Returns:
            Name of loaded model, or None if no models available
        """
        settings = load_settings()
        last_model = settings.get("last_model")

        # Try to load last used model
        if last_model:
            model_path = constants.MODELS_DIR / last_model
            if self._verify_model(model_path):
                logger.info(f"Loading last used model: {last_model}")
                if self.load_chat_model(last_model):
                    return last_model

        # Try to load any available model
        available_models = self.get_available_chat_models()
        if available_models:
            first_model = available_models[0]
            logger.info(f"Loading first available model: {first_model}")
            if self.load_chat_model(first_model):
                return first_model

        logger.warning("No chat models available to load")
        return None

    def get_context_window(self) -> int:
        """
        Get the configured context window size for the currently loaded model.

        Returns the user-configured size from settings (saved at load time), falling
        back to the model's native max if not configured, then 8192 as a safe default.
        """
        model = self._current_chat_model
        if model:
            from bacchus.constants import DEFAULT_CONTEXT_SIZE
            configured = load_settings().get("model_context_sizes", {}).get(model)
            if configured:
                return configured
            if model in constants.CHAT_MODELS:
                return constants.CHAT_MODELS[model]["context_window"]
        return 8192  # Safe fallback

    def get_model_display_name(self, folder_name: str) -> str:
        """
        Get display name for a model folder name.

        Args:
            folder_name: Model folder name (e.g., "phi-3.5-mini")

        Returns:
            Human-readable display name
        """
        # Check chat models
        if folder_name in constants.CHAT_MODELS:
            return constants.CHAT_MODELS[folder_name]["display_name"]

        # Check embedding model
        if folder_name == constants.EMBEDDING_MODEL["folder_name"]:
            return constants.EMBEDDING_MODEL["display_name"]

        # Fallback to folder name
        return folder_name

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        """
        Generate text using the loaded LLM.

        Args:
            prompt: Input prompt text
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Generated text
        """
        if self._llm_pipeline is None:
            raise RuntimeError("No chat model loaded")

        import openvino_genai as ov_genai

        # Create generation config
        config = ov_genai.GenerationConfig()
        config.max_new_tokens = max_tokens
        config.temperature = temperature

        # Generate
        result = self._llm_pipeline.generate(prompt, config)

        return result
