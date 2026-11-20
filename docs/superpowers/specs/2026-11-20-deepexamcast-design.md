# DeepExamCast — Design Specification

**Date:** 2026-11-20  
**Project:** DeepExamCast (`F:\projects\examcast`)  
**Status:** Draft for Spec Review

---

## 1. Overview & Goals

**DeepExamCast** is a local, zero-API-key web application that turns exam PDF chapter notes (typically ~30 pages, up to 50–60 pages) into an in-depth, two-host conversational audio lecture synchronized accurately with an interactive PDF viewer.

Users generate scripts using their existing Gemini Web subscription via a fast copy-paste JSON workflow in 5-page batches, while the backend synthesizes high-quality neural audio locally via free `edge-tts` voices and caches every asset on disk so chapters can be closed and reopened instantly without regenerating audio.

### Core Constraints
- **Zero API keys** (no Gemini API SDK, no paid TTS services).
- **Zero `ffmpeg`** (per-line `.mp3` files played seamlessly by a dual-`<audio>` queue in the browser).
- **Zero frontend build step** (single `static/index.html` served directly by FastAPI, loading PDF.js and Tailwind CSS via CDN).
- **Local-first persistence** in `./sessions/<session_id>/` including PDFs, extracted chunks, dialogue scripts, cached `.mp3` clips, and study resume state.

---

## 2. Tech Stack & Repository Layout

### Runtime & Test Dependencies
- `requirements.txt` (runtime only):
  - `fastapi`
  - `uvicorn[standard]`
  - `pymupdf` (`fitz`)
  - `edge-tts`
  - `python-multipart`
- `requirements-dev.txt` (test dependencies):
  - `pytest`
  - `httpx`

### Directory Structure
```text
examcast/
├── app.py                     # Thin FastAPI entrypoint (`uvicorn app:app`)
├── deepexamcast/
│   ├── __init__.py
│   ├── models.py              # Pydantic schemas + built-in VOICE_PAIRS registry
│   ├── pdf_parser.py          # PyMuPDF text block extraction & bbox normalization
│   ├── prompt_builder.py      # Page-range chunk filtering + zero-skimming Gemini prompt
│   ├── script_parser.py       # Fence stripping, balanced JSON extraction, validation
│   ├── tts_engine.py          # Concurrent edge-tts (Semaphore(5)), hash cache, retries
│   └── session_store.py       # Atomic session.json I/O, path guards, coverage & batching
├── static/
│   └── index.html             # Single-file dark-mode UI (PDF.js 3.11.174 + Tailwind CDN)
├── tests/
│   ├── test_pdf_parser.py
│   ├── test_prompt_builder.py
│   ├── test_script_parser.py
│   ├── test_tts_engine.py
│   └── test_api_integration.py
├── sessions/                  # Gitignored runtime storage: ./sessions/<session_id>/
├── docs/superpowers/specs/    # Design specifications
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
└── README.md
```

### Module Boundaries
- **`deepexamcast/models.py`**: Pure data contracts (`PageInfo`, `Chunk`, `ScriptLine`, `RawScriptRecord`, `StudyState`, `CoverageInfo`, `SessionData`, `SessionSummary`, `GenerateRequest`, `StatePatchRequest`, `VoicePair`) and the canonical `VOICE_PAIRS` list.
- **`deepexamcast/pdf_parser.py`**: Pure PDF ingestion (`parse_pdf_bytes(data: bytes) -> tuple[list[PageInfo], list[Chunk]]`). No filesystem session coupling.
- **`deepexamcast/prompt_builder.py`**: Pure prompt assembly (`build_prompt(chunks, start_page, end_page, has_existing_script) -> PromptResult`).
- **`deepexamcast/script_parser.py`**: Pure LLM output parser (`parse_gemini_script(raw_json, valid_chunk_ids) -> ParsedScriptResult`).
- **`deepexamcast/tts_engine.py`**: Async audio synthesizer (`synthesize_lines(audio_dir, lines, mode, concurrency=5) -> SynthesisResult`). Owns `edge-tts` calls, retry backoff, SHA-256 manifest verification, and orphan file cleanup.
- **`deepexamcast/session_store.py`**: Sole owner of `./sessions/<session_id>/` disk I/O, session ID sanitization, atomic JSON writes (`tmp` + `os.replace`), session listing, and derived page-coverage computation.
- **`app.py`**: Wires FastAPI routes, maps domain exceptions to clean HTTP `400`/`404`/`502` responses, and serves `static/index.html`.

---

## 3. On-Disk Storage & Data Model

Each uploaded PDF creates `./sessions/<session_id>/` where `session_id` is a readable, path-safe identifier matching `^[a-z0-9][a-z0-9_-]{1,80}$` (format: `<slug>-<6-hex-chars>`, e.g., `ch04-deadlocks-7f3a9c`).

```text
sessions/<session_id>/
├── source.pdf          # Original uploaded PDF bytes
├── session.json        # Authoritative session state & metadata (atomically written)
└── audio/
    ├── manifest.json   # Maps filename -> 16-char SHA-256 content hash of generated MP3
    ├── line_000.mp3
    ├── line_001.mp3
    └── ...
```

### `session.json` Schema
```json
{
  "session_id": "ch04-deadlocks-7f3a9c",
  "title": "ch04_deadlocks.pdf",
  "created_at": "2026-11-20T08:00:00Z",
  "updated_at": "2026-11-20T08:15:00Z",
  "page_count": 32,
  "pages": [
    { "page": 1, "width": 595.0, "height": 842.0, "chunk_count": 9 }
  ],
  "chunks": [
    {
      "id": "C1",
      "page": 1,
      "bbox": [0.102, 0.085, 0.891, 0.142],
      "text": "A deadlock occurs when a set of processes are blocked..."
    }
  ],
  "script": [
    {
      "index": 0,
      "speaker": "HOST_A",
      "text": "Let us dive straight into deadlocks.",
      "chunk_ids": ["C1"],
      "exam_note": "Deadlock = circular wait for resources held by other blocked processes",
      "voice": "en-US-AndrewMultilingualNeural",
      "audio_file": "line_000.mp3",
      "audio_hash": "9f86d081884c7d65"
    }
  ],
  "raw_scripts": [
    {
      "timestamp": "2026-11-20T08:15:00Z",
      "mode": "replace",
      "line_count": 42,
      "raw_json": "[...]"
    }
  ],
  "state": {
    "last_line_index": 0,
    "playback_rate": 1.0,
    "voice_pair_id": "us_natural",
    "host_a_voice": "en-US-AndrewMultilingualNeural",
    "host_b_voice": "en-US-AvaMultilingualNeural",
    "auto_scroll": true
  }
}
```

### Derived Coverage & Smart Next-Batch Calculation
Computed dynamically on session read (never out of sync with `script`):
- `covered_chunk_ids`: sorted unique valid chunk IDs referenced by any line in `script`.
- `covered_pages`: sorted unique 1-indexed page numbers containing at least one covered chunk.
- `covered_page_count`: `len(covered_pages)`.
- `suggested_next_range`: finds the smallest 1-indexed page `p` in `1..page_count` that has `chunk_count > 0` and is not in `covered_pages`. Returns `{ "start_page": p, "end_page": min(p + 4, page_count) }`. If every text-bearing page is already covered (or the PDF has 0 text chunks), returns `{ "start_page": 1, "end_page": min(5, max(1, page_count)) }`.

---

## 4. Built-in Voice Pairs

Defined once in `deepexamcast/models.py` and exposed via `GET /api/voices` (and included in session responses):

| `id` | Label | `host_a_voice` (Professor) | `host_b_voice` (Student) |
| :--- | :--- | :--- | :--- |
| `us_natural` | US Natural | `en-US-AndrewMultilingualNeural` | `en-US-AvaMultilingualNeural` |
| `in_english` | Indian English | `en-IN-PrabhatNeural` | `en-IN-NeerjaExpressiveNeural` |
| `uk_natural` | UK Natural | `en-GB-RyanNeural` | `en-GB-SoniaNeural` |

Default for new sessions: `us_natural`.

---

## 5. Backend API Specification

### `GET /`
Serves `static/index.html` with `text/html`.

### `GET /api/voices`
Returns `{ "voice_pairs": [...] }`.

### `POST /api/upload`
- **Input:** `multipart/form-data` with field `file` (`.pdf`).
- **Validation:** Reject empty upload or non-PDF bytes (`%PDF-` header check + PyMuPDF open validation) with HTTP `400` and descriptive `detail`.
- **Behavior:**
  1. Parse PDF with `pdf_parser.parse_pdf_bytes`.
  2. Persist `source.pdf` and initial `session.json` under `./sessions/<session_id>/`.
  3. If `len(chunks) == 0`, still create the session and include a `warnings` message noting that no selectable text blocks were extracted (e.g., scanned/image-only PDF).
- **Response (`200`):** Full session response (`session`, `coverage`, `voice_pairs`, `warnings`).

### `GET /api/sessions`
- Lists all valid sessions under `./sessions/` sorted by `updated_at` descending.
- **Response (`200`):** `{ "sessions": [{ "session_id", "title", "page_count", "chunk_count", "line_count", "covered_page_count", "last_line_index", "created_at", "updated_at" }] }`.

### `GET /api/sessions/{session_id}`
- Validates `session_id` format and existence (`404` if missing).
- **Response (`200`):** `{ "session": ..., "coverage": ..., "voice_pairs": ... }`.

### `GET /api/sessions/{session_id}/pdf`
- Streams `source.pdf` (`application/pdf`) for PDF.js. Returns `404` if missing.

### `GET /api/sessions/{session_id}/prompt?start_page=1&end_page=5`
- **Validation:**
  - `1 <= start_page <= end_page <= page_count` (else HTTP `400`).
  - Selected page range must contain at least 1 chunk (else HTTP `400` stating pages contain no extractable text).
- **Response (`200`):**
  ```json
  {
    "prompt": "...",
    "start_page": 1,
    "end_page": 5,
    "chunk_count": 28,
    "chunk_id_range": ["C1", "C28"]
  }
  ```

### `POST /api/sessions/{session_id}/generate`
- **Request Body:**
  ```json
  {
    "raw_json": "...",
    "host_a_voice": "en-US-AndrewMultilingualNeural",
    "host_b_voice": "en-US-AvaMultilingualNeural",
    "mode": "replace"
  }
  ```
  (`mode` is `"replace"` or `"append"`.)
- **Behavior:**
  1. Parse and validate `raw_json` via `script_parser.parse_gemini_script` before mutating audio or `session.json`. On invalid JSON/schema, return HTTP `400` with exact error message (including line/column snippet on JSON syntax failure).
  2. Assign target indices:
     - `replace`: indices `0 .. M-1`.
     - `append`: preserve existing `0 .. N-1`; new lines get indices `N .. N+M-1`.
  3. Compute `voice` (`host_a_voice` for `HOST_A`, `host_b_voice` for `HOST_B`) and `audio_hash = sha256(f"{voice}\0{text}".encode("utf-8")).hexdigest()[:16]` for each target line.
  4. Synthesize missing/changed clips via `tts_engine.synthesize_lines` (`asyncio.Semaphore(5)`).
     - On `append`, only lines `N .. N+M-1` are synthesized (existing `0 .. N-1` stay untouched).
     - On `replace`, every line `0 .. M-1` is checked against `audio/manifest.json` + file existence (`size > 0`); matching lines are skipped. After synthesis succeeds, orphan files `line_XXX.mp3` with index `>= M` are removed and pruned from `audio/manifest.json`.
  5. Update `session.json` atomically: save `script`, append to `raw_scripts`, update `state.host_a_voice`, `state.host_b_voice`, matched `state.voice_pair_id` (or `"custom"`), and reset `state.last_line_index = 0` only when `mode == "replace"` (keep existing position on `append`).
- **Response (`200`):**
  ```json
  {
    "session": { ... },
    "coverage": { ... },
    "stats": {
      "generated_count": 38,
      "cached_count": 4,
      "total_lines": 42
    },
    "warnings": []
  }
  ```
- **Partial TTS Failure (`502`):** If any clip still fails after 3 retry attempts, `audio/manifest.json` still records all clips that succeeded during the batch, `session.json` is not corrupted, and the response returns HTTP `502` with exact line index, error summary, and count of already-cached clips so clicking Generate again resumes without redoing completed clips.

### `GET /api/sessions/{session_id}/audio/{filename}`
- Strict validation: `filename` must match `^line_\d{3,}\.mp3$` (returns `400` otherwise, preventing any path traversal).
- Returns `FileResponse` with `media_type="audio/mpeg"` and header `Cache-Control: no-cache` (`404` if missing).

### `PATCH /api/sessions/{session_id}/state`
- **Request Body:** Partial JSON containing any subset of `last_line_index`, `playback_rate`, `voice_pair_id`, `host_a_voice`, `host_b_voice`, `auto_scroll`.
- **Validation:** `playback_rate` clamped/validated in `[0.5, 3.0]`; `last_line_index` clamped to `[0, max(0, len(script) - 1)]`.
- **Response (`200`):** `{ "state": { ... } }`.

---

## 6. Core Processing Algorithms

### 6.1 PDF Parsing (`pdf_parser.py`)
1. Open PDF bytes via `fitz.open(stream=data, filetype="pdf")`.
2. Iterate 1-indexed pages `1 .. len(doc)`:
   - Record `width = float(page.rect.width)`, `height = float(page.rect.height)`.
   - Extract blocks via `page.get_text("blocks", sort=True)`.
   - Keep only text blocks (`block_type == 0`).
   - Normalize whitespace inside each block (`" ".join(raw_text.split())`); skip if empty.
   - Normalize bounding box against `page.rect`:
     - `x0 = clamp((bx0 - rect.x0) / rect.width, 0.0, 1.0)`
     - `y0 = clamp((by0 - rect.y0) / rect.height, 0.0, 1.0)`
     - `x1 = clamp((bx1 - rect.x0) / rect.width, 0.0, 1.0)`
     - `y1 = clamp((by1 - rect.y0) / rect.height, 0.0, 1.0)`
     - Round to 5 decimal places.
   - Assign sequential chunk IDs `C1`, `C2`, ..., `CN`.

### 6.2 Deep-Dive Prompt Template (`prompt_builder.py`)
- Filters `chunks` to `start_page <= c.page <= end_page`.
- Formats chunk payload lines strictly as:
  `[C12] (Page 3): <text>`
- Prompt instructions enforce:
  - Roles: enthusiastic Professor (`HOST_A`) and sharp Exam Student (`HOST_B`) recording a deep-dive study podcast.
  - **ZERO SKIMMING:** Cover every single chunk ID in exact sequential order from `C_start` to `C_end`. Explain every definition, mechanism, formula, exception/edge case, and likely exam question clearly using intuitive analogies and memory hooks.
  - Conversational spoken audio style: 1–3 natural sentences per turn; zero markdown symbols (`*`, `#`, `_`, `` ` ``) in `text`; spell out all math and symbols as natural spoken English (e.g., "x squared", "equals", "greater than or equal to", "O of n log n").
  - If `has_existing_script` is true and `start_page > 1`, include a 1-line continuity note instructing the hosts to pick up seamlessly without re-introducing the podcast.
  - Strict JSON-only output format:
    ```json
    [
      {
        "speaker": "HOST_A",
        "text": "Spoken dialogue here...",
        "chunk_ids": ["C12"],
        "exam_note": "Optional short 1-line formula or key exam fact"
      }
    ]
    ```

### 6.3 Robust Gemini JSON Extraction (`script_parser.py`)
1. Strip UTF-8 BOM and outer whitespace.
2. If markdown code fences (```` ```json ... ``` ```` or ```` ``` ... ``` ````) are present, extract fenced block candidates first, while still keeping the full raw string as fallback.
3. Scan for `[` characters and attempt `json.JSONDecoder().raw_decode(text, idx)`. Because `raw_decode` parses valid JSON grammar natively, intro/outro prose before or after the array—and literal `]` characters inside spoken strings—never break extraction. Accept the first decoded `list` (preferring non-empty list of dicts).
4. Validate each element `i`:
   - Must be a JSON object (`dict`).
   - `speaker`: case-insensitive match to `"HOST_A"` or `"HOST_B"`; normalize to uppercase. Invalid value raises `ScriptParseError` citing item index `i`.
   - `text`: must be a string with non-empty content after collapsing newlines and trimming whitespace.
   - `chunk_ids`: accept list of strings (or coerce a single string into a 1-element list), uppercase and deduplicate preserving order. Any chunk ID not present in `valid_chunk_ids` is dropped from the line's `chunk_ids` and recorded in `warnings` (non-fatal so one Gemini typo never blocks a 50-line batch).
   - `exam_note`: optional string; trim whitespace and store `None` if absent or blank.
5. Reject empty dialogue arrays (`[]`) with a clear `ScriptParseError`.

### 6.4 Concurrent `edge-tts` Engine (`tts_engine.py`)
- Loads existing `audio/manifest.json` (`dict[filename, hash]`, defaulting to `{}` if absent/corrupt).
- Runs tasks under `asyncio.Semaphore(5)`.
- Per line:
  - Target filename: `f"line_{line.index:03d}.mp3"`.
  - Cache hit check: if `manifest.get(filename) == line.audio_hash` AND `(audio_dir / filename).exists()` AND file size `> 0`, skip synthesis (`cached_count += 1`).
  - Otherwise synthesize to `audio_dir / f".{filename}.{uuid4().hex}.tmp"` via `await edge_tts.Communicate(line.text, line.voice).save(str(tmp_path))`, verify `size > 0`, atomically `os.replace(tmp_path, target_path)`, update in-memory manifest, increment `generated_count`.
  - Retry up to 3 attempts on failure with exponential backoff (`1s`, `2s`, `4s`), cleaning up any partial `.tmp` file on each failed attempt.
- Always flush updated `audio/manifest.json` atomically even if one or more lines fail after retries, so completed clips stay cached for immediate retry.
- On `mode == "replace"` success, delete any existing `line_*.mp3` files whose numeric index `>= total_lines` and remove them from `audio/manifest.json`.

---

## 7. Frontend Architecture (`static/index.html`)

Single HTML file served at `/`, loading:
- Tailwind CSS via CDN (`https://cdn.tailwindcss.com`) with dark slate/obsidian palette (`#0B0F17` canvas, `#111827`/`#161E2E` surfaces, `#1F2937` hairlines, `#FACC15`/`#F59E0B` amber accents for highlights and exam notes).
- PDF.js `3.11.174` via CDN (`pdf.min.js` + `pdf.worker.min.js` from matching CDN URL).

### 7.1 Layout & Components
1. **Top Control Bar (compact, fixed height):**
   - App title (**DeepExamCast**).
   - **Session Selector `<select>`** listing saved PDFs (`title — X/Y pgs`) + **Upload New PDF** button triggering hidden `<input type="file" accept="application/pdf">` with upload indicator.
   - Collapsible toggle button: **"Add / Generate Deep Script"** (automatically expanded when a session has 0 lines; collapses cleanly once audio is ready).
2. **Collapsible "Add / Generate Deep Script" Drawer:**
   - **Page Range Row:** `From Page` / `To Page` number inputs pre-filled from `coverage.suggested_next_range` (5-page batches), page-coverage indicator (`Covered: X / Y pages` + slim progress bar), and 1-click **"Copy Prompt for Gemini Pro"** button with `"Copied!"` toast showing chunk range (`C1–C28`).
   - **JSON Paste & Voice Row:** Multi-line `<textarea>` for Gemini's JSON response; **Voice Pair `<select>`** (US Natural, Indian English, UK Natural); **"Append to Lecture"** and **"Replace & Generate Audio"** buttons (with confirmation dialog when replacing an existing non-empty script).
   - Live loading spinner showing elapsed seconds (`Generating audio… 12s`) while `POST /generate` runs, plus dismissible error/warning banners.
3. **Sticky Playback Bar:**
   - Transport controls: **Prev Line**, **Play / Pause**, **Next Line**, **Repeat Current Line (`R`)**.
   - **Playback Speed** pill buttons: `1x`, `1.25x`, `1.5x`, `1.75x`, `2x`.
   - Scrubbable/clickable progress bar + readout: `Line X / Y` and `Page P / N`.
   - Toggle button: **`Auto-Scroll: ON`** / **`Auto-Scroll: OFF`**.
4. **Main Split View (remaining viewport height, independent pane scrolling):**
   - **Left Pane (68% width) — Synced PDF Viewer (PDF.js):**
     - Compact zoom bar (`-`, `100%`, `+`, `Fit Width`) + page indicator.
     - Pre-creates stacked page containers for all pages using exact viewport aspect ratios so scroll positions and chunk overlays are immediately accurate across 30–60 pages.
     - Lazily renders HiDPI (`window.devicePixelRatio`) `<canvas>` elements near the viewport via `IntersectionObserver` (`rootMargin: '800px 0px'`). Re-renders cleanly on zoom changes without losing active highlights.
     - **Normalized Chunk Overlay Layer:** Each chunk renders as an absolutely positioned div (`left: x0*100%`, `top: y0*100%`, `width: (x1-x0)*100%`, `height: (y1-y0)*100%`):
       - **Active chunks** (in current line's `chunk_ids`): translucent yellow box (`rgba(250, 204, 21, 0.35)`) + soft amber border (`1.5px solid rgba(245, 158, 11, 0.85)`).
       - **Covered chunks** (mapped to at least one dialogue line): subtle hover highlight + pointer cursor; clicking jumps audio & sidebar directly to the first dialogue line referencing that chunk (**Reverse Sync**).
       - **Uncovered chunks**: faint neutral hover outline with tooltip indicating page batch is not yet generated.
     - **Forward Sync:** Whenever active `chunk_ids` change and `Auto-Scroll` is ON, smoothly scrolls the first active highlight into the vertical center of the PDF pane.
   - **Right Pane (32% width) — Live Dialogue & Exam Notes Panel:**
     - Scrollable list of dialogue cards showing speaker badge (`Professor` in indigo/sky for `HOST_A`, `Student` in emerald/teal for `HOST_B`), page + chunk ID tag (e.g., `Pg 3 · C12`), spoken dialogue text, and an amber-highlighted **`exam_note`** callout box whenever present.
     - Active card gets an amber left accent border and elevated dark surface, and smoothly scrolls into view in the sidebar.
     - Clicking any dialogue card jumps playback and PDF highlight immediately to that line.

### 7.2 Dual-`<audio>` Gapless-Feel Queue Engine
- Uses two `HTMLAudioElement` instances (`deckA`, `deckB`), an `activeDeck` reference, a `breathTimer` handle, and a monotonic `playbackToken` counter to eliminate race conditions on rapid jumps/pauses.
- Audio URLs use cache-busting query strings: `/api/sessions/{sessionId}/audio/{audio_file}?h={audio_hash}`.
- Playing line `i`:
  1. Increment `playbackToken`, cancel any pending `breathTimer`, pause `standbyDeck`.
  2. Load line `i` into `activeDeck` (reusing it immediately if `standbyDeck` already preloaded line `i`), apply `playbackRate`, call `.play()`.
  3. Preload line `i + 1` onto `standbyDeck` (`preload = "auto"`, `playbackRate = currentRate`, `.load()`).
  4. Sync active highlights, active sidebar card, playback bar readout, and debounced `PATCH /api/sessions/{id}/state`.
- On `activeDeck` `ended` event (matching current `playbackToken`):
  - If `i + 1 < script.length`: wait `200ms` natural conversational breath (`breathTimer`), swap `activeDeck` ↔ `standbyDeck`, and play line `i + 1`.
  - If at final line: transition cleanly to paused state at the last line.
- **Repeat (`R`):** cancels `breathTimer`, resets `activeDeck.currentTime = 0`, plays line `i` immediately.
- **Keyboard Shortcuts:**
  - `Space`: Play / Pause (calls `preventDefault()` so page does not jump).
  - `ArrowLeft`: Previous line.
  - `ArrowRight`: Next line.
  - `R` / `r`: Replay current line.
  - Ignored when `document.activeElement` is `<input>`, `<textarea>`, `<select>`, or `contentEditable`, or when Ctrl/Alt/Meta modifiers are active.

---

## 8. Error Handling & Edge Cases

- **Corrupt or non-PDF upload:** Clear HTTP `400` surfaced in UI toast/banner; no partial session directory left on disk.
- **Image-only / scanned pages:** Upload succeeds with warning banner; prompt endpoint rejects page ranges with 0 extractable chunks with a clear message.
- **Messy or truncated Gemini JSON:** Automatic fence stripping + balanced `raw_decode` handles prose wrappers; broken/truncated JSON returns HTTP `400` with exact line/column and context snippet shown inline in the drawer.
- **Unknown chunk IDs from Gemini:** Non-fatal warning listing skipped chunk IDs so the user still gets synced audio for all valid chunks.
- **Transient `edge-tts` errors / rate limits:** Automatic 3-attempt exponential backoff per line + partial manifest preservation so retrying never regenerates completed clips.
- **Path traversal attempts:** Strict allowlist regex on both `session_id` (`^[a-z0-9][a-z0-9_-]{1,80}$`) and audio `filename` (`^line_\d{3,}\.mp3$`).
- **Browser autoplay restrictions:** Restoring a saved session sets `last_line_index` visually (highlighting the PDF chunk and active sidebar card) without auto-playing until the user clicks Play or presses `Space`.

---

## 9. Testing & Verification Strategy

### Automated Test Suite (`pytest`)
1. **`tests/test_pdf_parser.py`**: Generates synthetic multi-page PDFs with PyMuPDF; verifies sequential `C1..CN` IDs, 1-indexed pages, normalized `[0.0, 1.0]` bboxes, top-to-bottom order, blank/non-text filtering, and invalid PDF error handling.
2. **`tests/test_prompt_builder.py`**: Verifies exact `[C12] (Page 3): <text>` formatting, strict `start_page..end_page` filtering, zero-skimming and JSON rules, empty-range errors, and append continuity hint.
3. **`tests/test_script_parser.py`**: Verifies plain JSON, fenced ```` ```json ```` blocks, Gemini intro/outro prose, literal `]` inside dialogue strings, single-string `chunk_ids` normalization, unknown chunk ID warnings, and descriptive syntax/schema errors.
4. **`tests/test_tts_engine.py`**: Uses mocked `edge_tts.Communicate` to verify `Semaphore(5)` concurrency bound, SHA-256 cache hits vs regeneration on text/voice change, retry-with-backoff recovery, partial-failure manifest persistence, and `replace`-mode orphan `.mp3` deletion.
5. **`tests/test_api_integration.py`**: End-to-end FastAPI `TestClient` flow: upload PDF → list/reload sessions → stream PDF → generate prompt → generate audio (`replace` and `append`) → stream audio + reject path traversal → `PATCH /state` persistence → verify `coverage` and `suggested_next_range`.

### Live Verification Gate (Deliverable Checks)
1. `python -m py_compile app.py deepexamcast/*.py` passes with zero errors.
2. `python -c "import edge_tts, fitz, fastapi, uvicorn; print('ok')"` passes cleanly.
3. `pytest -v` passes 100%.
4. Boot `uvicorn app:app --host 127.0.0.1 --port 8000` and verify HTTP `200` on `GET /` and `GET /api/voices`.
