# Bacchus

A local LLM chat application for Intel NPU, powered by OpenVINO.

The name is a pun: **Bacchus** is the Roman god of wine, and **OpenVINO** translates to "open wine" in Italian.

---

## What it does

Bacchus runs AI models entirely on your local machine using the dedicated Neural Processing Unit (NPU) built into modern Intel processors. No cloud, no API keys, no data leaving your machine.

- **Chat** with vision-language models that can read images you attach
- **Web search and browsing** via built-in MCP tools
- **RAG** — attach a `.txt` or `.md` document to a conversation for grounded answers
- **Bilingual UI** — Portuguese (BR) and English
- **Conversation history** persisted locally in SQLite

---

## Hardware requirements

| Requirement | Details |
|---|---|
| CPU | Intel Core Ultra (Lunar Lake / Arrow Lake / Meteor Lake with NPU4) |
| NPU Driver | Intel AI Boost ≥ 32.0.100.4512 |
| RAM | 16 GB recommended |
| Storage | ~3 GB per model |
| OS | Windows 10 / 11 |

> **Note:** Models run on the NPU only. CPU/GPU inference is not currently supported.

---

## Available models

| Model | Type | Size |
|---|---|---|
| `0ldev/Qwen3-VL-2B-Instruct-ov-nf4-npu` | Vision + Text | ~1.5 GB |
| `0ldev/Qwen2.5-VL-3B-Instruct-ov-nf4-npu` | Vision + Text | ~2.0 GB |
| `0ldev/gemma-3-4b-it-ov-nf4-npu` | Text only | ~2.5 GB |

All models are downloaded automatically from Hugging Face on first use via the built-in download manager.

---

## Installation

### Prerequisites

- Python 3.11 or 3.12
- [Intel NPU driver](https://www.intel.com/content/www/us/en/download/794734/) ≥ 32.0.100.4512
- Visual Studio 2019 or later (for the patched `openvino-genai` build — see below)
- CMake ≥ 3.23

### 1. Clone and set up the environment

```powershell
git clone https://github.com/0ldev/Bacchus.git
cd Bacchus
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Install the patched openvino-genai

The official `openvino-genai 2025.4.1` on PyPI has a bug where `VLMPipeline` on NPU silently ignores the `MAX_PROMPT_LEN` property, capping all prompts at 1024 tokens regardless of model context size. This is tracked as [openvinotoolkit/openvino.genai#3366](https://github.com/openvinotoolkit/openvino.genai/issues/3366).

Until the fix ships in an official release, you must build from the patched fork:

```powershell
# 1. Import MSVC into the current PowerShell session
cmd /c "`"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat`" && set" | ForEach-Object {
    if ($_ -match "^([^=]+)=(.*)$") { [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process") }
}

# 2. Point CMake to the pip-installed OpenVINO headers
$env:OpenVINO_DIR = ".\venv\Lib\site-packages\openvino\cmake"

# 3. Clone the fork (one directory above the project is fine)
cd ..
git clone --recursive https://github.com/0ldev/openvino.genai.git openvino_genai_fork
cd openvino_genai_fork

# 4. Checkout the 2025.4.1 release tag and apply the fix
git remote add upstream https://github.com/openvinotoolkit/openvino.genai.git
git fetch upstream tag 2025.4.1.0 --no-tags
git checkout -b fix-2025.4.1 2025.4.1.0
git cherry-pick 6decf4c4
git submodule update --init --recursive

# 5. Build and install (~15-30 min)
pip install py-build-cmake
..\Bacchus\venv\Scripts\pip.exe install . --no-build-isolation

# 6. Verify
..\Bacchus\venv\Scripts\python.exe -c "import openvino_genai; print(openvino_genai.__version__)"
# Should print: 2025.4.1.0-...-fix-2025.4.1
```

> Once Intel ships the fix in an official release, step 2 will no longer be necessary and `pip install -r requirements.txt` will be sufficient.

### 3. Run

```powershell
cd Bacchus
python main.py
```

---

## Usage

1. **Download a model** — open Settings → Models, pick a model, click Download
2. **Select the model** — click it in the model list to load it onto the NPU (first load compiles for your chosen context size, takes ~1–2 minutes)
3. **Chat** — type a message and press Enter or click Send
4. **Attach an image** — click the paperclip icon (vision models only)
5. **Attach a document** — drag a `.txt` or `.md` file into the chat for RAG-assisted answers
6. **Web tools** — the model can search the web and fetch pages autonomously when MCP servers are enabled (Settings → MCP)

---

## Architecture

```
bacchus/
├── app.py              # QApplication entry point, main window bootstrap
├── config.py           # YAML settings (loaded from %APPDATA%/Bacchus/config.yaml)
├── constants.py        # Model registry, paths, UI constants
├── database.py         # SQLite CRUD (conversations, messages)
├── model_manager.py    # Model loading, VLMPipeline / LLMPipeline lifecycle
├── inference/
│   ├── chat.py         # Token estimation, context trimming, prompt construction
│   ├── inference_worker.py   # Background QThread for LLM generation
│   ├── vlm_worker.py         # Background QThread for VLM generation
│   ├── decision_schema.py    # Structured JSON schema for tool-call decisions
│   └── autonomous_tools.py   # Tool execution, result formatting
├── rag/
│   ├── document.py     # Text chunking with line tracking
│   └── retrieval.py    # Cosine similarity retrieval
├── mcp/
│   ├── client.py       # MCP protocol client
│   ├── web_search.py   # DuckDuckGo search tool
│   ├── web_request.py  # URL fetch + html2text tool
│   └── filesystem.py   # Read/list file tools
├── prompts/            # Dynamic system prompts (en / pt-BR yaml templates)
├── ui/
│   ├── main_window.py  # Main window, inference orchestration
│   ├── chat_widget.py  # Message display
│   ├── sidebar.py      # Conversation list
│   ├── settings_dialog.py
│   └── ...
└── locales/            # UI strings (en.yaml, pt-BR.yaml)
```

**Data location:** `%APPDATA%\Bacchus\`

**Threading model:** All UI on the main thread. Inference, downloads, and document processing run on background `QThread`s and communicate back via Qt signals.

---

## Development

```powershell
pip install -r requirements-dev.txt

# Run all tests
pytest

# Unit tests only (no hardware required)
pytest tests/unit/

# Integration tests
pytest tests/integration/

# With coverage
pytest --cov=bacchus --cov-report=html
```

Tests that require OpenVINO inference or network access are excluded from CI by convention — see `CLAUDE.md` for the full testing strategy.

---

## Known limitations

- **Context window cap:** NPU compiles a static KV-cache at load time. The default is 16384 tokens; changing it requires reloading the model (re-compilation).
- **Single document per conversation:** RAG supports one `.txt` / `.md` file per conversation.
- **No streaming:** Responses appear only after full generation completes.
- **Windows only:** The NPU plugin for OpenVINO is currently Windows-only.

---

## License

MIT
