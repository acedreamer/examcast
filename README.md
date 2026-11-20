# DeepExamCast

Turn exam chapter PDFs into in-depth, two-host conversational audio lectures synchronized paragraph-by-paragraph with an interactive PDF viewer—using **zero API keys**, **zero `ffmpeg`**, and **zero frontend build tools**.

> [!NOTE]
> DeepExamCast pairs your existing Gemini Web subscription (copy-paste JSON workflow) with free local `edge-tts` neural voices and a Material 3 Expressive dark-mode viewer. All PDFs, dialogue scripts, and content-addressed `.mp3` clips stay cached locally inside `./sessions/<session_id>/`.

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

1. **Upload a chapter PDF:** Click **Upload PDF**. DeepExamCast extracts reading-ordered text blocks (`C1..CN`) and pre-fills the next uncovered page batch.
2. **Copy Prompt for Gemini Pro:** Open **Add / Generate Deep Script**, adjust the page range if needed, and click **Copy Prompt for Gemini Pro**. Paste into Gemini Web.
3. **Paste JSON & Generate Audio:** Paste Gemini's JSON response back, choose a voice pair (`US Natural`, `Indian English`, or `UK Natural`), and click **Replace & Generate Audio** (or **Append to Lecture** for subsequent batches).

> [!TIP]
> **Keyboard Shortcuts:** `Space` Play/Pause · `←` / `→` Previous/Next Line · `R` Repeat Current Line · `Esc` Close Script Drawer. Click any highlighted paragraph on the PDF to jump audio straight to that explanation.

## Optional Offline PDF.js Setup

Saved lectures load cached audio and CSS completely offline. To also view PDFs with zero internet access, download PDF.js `4.10.38` into `static/vendor/`:

```powershell
New-Item -ItemType Directory -Force static\vendor | Out-Null
Invoke-WebRequest "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs" -OutFile "static\vendor\pdf.min.mjs"
Invoke-WebRequest "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs" -OutFile "static\vendor\pdf.worker.min.mjs"
```

## Configuration & Testing

- `DEEPEXAMCAST_TTS_CONCURRENCY`: Optional integer `1`–`5` (default `4`) controlling concurrent `edge-tts` synthesis tasks.
- Run the full automated test suite:

```bash
pip install -r requirements-dev.txt
pytest -v
```
