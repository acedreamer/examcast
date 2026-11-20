# DeepExamCast

Turn exam chapter PDFs into in-depth, two-host conversational audio lectures synchronized paragraph-by-paragraph with an interactive PDF viewer—using **zero API keys**, **zero `ffmpeg`**, and **zero frontend build tools**.

> [!NOTE]
> DeepExamCast pairs your existing Gemini Web subscription (copy-paste JSON workflow) with free local `edge-tts` neural voices (`English`, `Hindi`, and `Malayalam`) and a Material 3 Expressive dark-mode viewer. All PDFs, dialogue scripts, and content-addressed `.mp3` clips stay cached locally inside `./sessions/<session_id>/`.

## Quick Start

### 1. Install Dependencies

```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the Server

```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Study Workflow

1. **Upload a chapter PDF:** Click **Upload PDF**. DeepExamCast strips diagonal/repeating watermarks, extracts native Markdown tables and reading-ordered text blocks (`C1..CN`), detects figures, and pre-fills the next uncovered page batch.
2. **Configure & Copy Prompt in Script Studio:** Open **Script Studio**, choose your **Study Pacing** (`Deep Dive`, `Revision`, `Viva Q&A`, or `ELI5`) and **Language** (`English`, `Hindi (Hinglish)`, or `Malayalam (Manglish)`), adjust the page range if needed, and click **Copy Prompt for Gemini Pro**. Paste into Gemini Web.
3. **Paste JSON & Generate Audio:** Paste Gemini's JSON response back, pick a voice pair, and click **Generate Audio** (or use the split menu to **Replace Entire Lecture** / **Re-synthesize Existing Audio**). Use **Re-parse PDF** in the Script Studio header anytime to re-extract chunks without re-uploading.

> [!TIP]
> **Keyboard Shortcuts & Reader Modes:** `Space` Play/Pause · `←` / `→` Previous/Next Line · `R` Repeat Current Line · `Esc` Close Script Studio / Menus. Switch between **Light**, **Sepia**, and **Dark** paper modes from the floating PDF toolbar while keeping amber chunk highlights crisp. Click any highlighted paragraph on the PDF to jump audio straight to that explanation.

## Optional GPU Vision OCR (`LightOnOCR-3-0.8B` via `llama-server` Vulkan)

Works on AMD (e.g. RX 5500M 4 GB VRAM), NVIDIA, and Intel GPUs. Download a Vulkan build of `llama.cpp`, then run:

```powershell
# Windows 11 (PowerShell)
huggingface-cli download mradermacher/LightOnOCR-3-0.8B-GGUF --include "*Q8_0.gguf" "mmproj*.gguf" --local-dir models
.\llama-server.exe -m models\LightOnOCR-3-0.8B-Q8_0.gguf --mmproj models\mmproj-LightOnOCR-3-0.8B-F16.gguf -ngl 99 --port 8081
```

```bash
# Linux (bash)
huggingface-cli download mradermacher/LightOnOCR-3-0.8B-GGUF --include "*Q8_0.gguf" "mmproj*.gguf" --local-dir models
./llama-server -m models/LightOnOCR-3-0.8B-Q8_0.gguf --mmproj models/mmproj-LightOnOCR-3-0.8B-F16.gguf -ngl 99 --port 8081
```

DeepExamCast checks `GET /api/vision/status` automatically and falls back seamlessly to PyMuPDF whenever `llama-server` is offline.

## Optional Offline PDF.js Setup

Saved lectures load cached audio and CSS completely offline. To also view PDFs with zero internet access, download PDF.js `4.10.38` into `static/vendor/`:

```powershell
New-Item -ItemType Directory -Force static\vendor | Out-Null
Invoke-WebRequest "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs" -OutFile "static\vendor\pdf.min.mjs"
Invoke-WebRequest "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs" -OutFile "static\vendor\pdf.worker.min.mjs"
```

## Configuration & Testing

- `DEEPEXAMCAST_TTS_CONCURRENCY`: Optional integer `1`–`5` (default `4`) controlling concurrent `edge-tts` synthesis tasks.
- `DEEPEXAMCAST_VISION_URL`: OpenAI-compatible Vision server URL (default `http://127.0.0.1:8081/v1`).
- `DEEPEXAMCAST_VISION_MODEL`: Vision model name (default `lightonocr-3`).
- `DEEPEXAMCAST_VISION_TIMEOUT`: Per-page/crop timeout in seconds (default `45.0`).
- Run the full automated test suite:

```bash
pip install -r requirements-dev.txt
pytest -v
```
