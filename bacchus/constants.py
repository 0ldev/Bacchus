"""
Application-wide constants for Bacchus.

Contains model information, paths, and other configuration constants.
"""

from pathlib import Path
from bacchus.config import get_app_data_dir

# Application metadata
APP_NAME = "Bacchus"
APP_VERSION = "0.1.0"

# Directory paths
APP_DATA_DIR = get_app_data_dir()
MODELS_DIR = APP_DATA_DIR / "models"
CONVERSATIONS_DIR = APP_DATA_DIR / "conversations"
LOGS_DIR = APP_DATA_DIR / "logs"
SCRIPTS_DIR = APP_DATA_DIR / "scripts"
SANDBOX_DIR = APP_DATA_DIR / "sandbox"
IMAGES_DIR = APP_DATA_DIR / "images"
DOCUMENTS_DIR = APP_DATA_DIR / "documents"
EMBEDDINGS_DIR = APP_DATA_DIR / "embeddings"
PROJECTS_DIR = APP_DATA_DIR / "projects"

# Model information — OpenVINO NF4 models from 0ldev, optimised for Intel NPU
CHAT_MODELS = {
    "qwen3-vl-2b-nf4-npu": {
        "display_name": "Qwen3 VL 2B Instruct (NF4)",
        "huggingface_repo": "0ldev/Qwen3-VL-2B-Instruct-ov-nf4-npu",
        "quantization": "NF4",
        "approx_size_gb": 1.5,
        "context_window": 32768,
    },
    "gemma-3-4b-nf4-npu": {
        "display_name": "Gemma 3 4B Instruct (NF4)",
        "huggingface_repo": "0ldev/gemma-3-4b-it-ov-nf4-npu",
        "quantization": "NF4",
        "approx_size_gb": 2.5,
        "context_window": 32768,
    },
    "qwen2.5-vl-3b-nf4-npu": {
        "display_name": "Qwen2.5 VL 3B Instruct (NF4)",
        "huggingface_repo": "0ldev/Qwen2.5-VL-3B-Instruct-ov-nf4-npu",
        "quantization": "NF4",
        "approx_size_gb": 2.0,
        "context_window": 32768,
    },
}

# User-selectable context window sizes (tokens) shown in the model settings UI.
# The actual value used is saved per-model in settings.yaml under model_context_sizes.
CONTEXT_SIZE_OPTIONS = [1024, 2048, 4096, 8192, 16384, 32768, 65536]
DEFAULT_CONTEXT_SIZE = 16384

# Generation parameter defaults
DEFAULT_TEMPERATURE = 0.7    # Sampling temperature (0.0 = greedy, higher = more creative)
DEFAULT_MIN_NEW_TOKENS = 0   # Minimum tokens before EOS is allowed (0 = no minimum)

EMBEDDING_MODEL = {
    "folder_name": "all-minilm-l6-v2",
    "display_name": "all-MiniLM-L6-v2",
    "huggingface_repo": "sentence-transformers/all-MiniLM-L6-v2",
    "approx_size_mb": 90,
    "embedding_dim": 384,
}

# RAG parameters (from spec Section 7.1)
RAG_CHUNK_SIZE = 512
RAG_OVERLAP = 64
RAG_TOP_K = 3
RAG_MIN_SIMILARITY = 0.3

# Context management (from spec Section 9.2)
RESPONSE_BUFFER_TOKENS = 512
SYSTEM_MESSAGE_TOKENS_ESTIMATE = 100

# Supported document types (MVP)
SUPPORTED_DOCUMENT_EXTENSIONS = {'.txt', '.md'}

# MCP configuration
MCP_TOOL_TIMEOUT_SECONDS = 30
MCP_SERVER_STARTUP_TIMEOUT_SECONDS = 10

# Device monitor update intervals (ms)
DEVICE_MONITOR_IDLE_INTERVAL_MS = 2000
DEVICE_MONITOR_ACTIVE_INTERVAL_MS = 500

# UI constants
SIDEBAR_WIDTH = 250
MIN_WINDOW_WIDTH = 1024
MIN_WINDOW_HEIGHT = 768
TITLE_MAX_LENGTH = 100
CONVERSATION_LIST_TITLE_LENGTH = 30

# Tool result widget: max characters shown in the scrollable content area.
# This is a UI-only limit — the full result is always sent to the LLM.
# Increase this if you want to inspect longer outputs in the chat UI.
TOOL_RESULT_DISPLAY_CHARS = 50_000

# Log rotation
LOG_RETENTION_DAYS = 7
