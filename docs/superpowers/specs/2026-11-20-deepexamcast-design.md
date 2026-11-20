# DeepExamCast — Design Specification

**Date:** 2026-11-20  
**Revision:** v3 (Second-Pass Hardened + Material 3 Expressive UI & Skills Integrated)  
**Project:** DeepExamCast (`F:\projects\examcast`)  
**Companion UI Spec:** [2026-11-20-deepexamcast-m3-ui-spec.md](2026-11-20-deepexamcast-m3-ui-spec.md)  
**Status:** Finalized for Implementation Planning (`writing-plans`)

---

## 1. Overview & Goals

**DeepExamCast** is a local, zero-API-key web application that turns exam PDF chapter notes (typically ~30 pages, up to 50–60 pages) into an in-depth, two-host conversational audio lecture synchronized accurately with an interactive PDF viewer.

Users generate scripts with their existing Gemini Web subscription via a fast copy-paste JSON workflow in budgeted page batches, while the backend synthesizes high-quality neural audio locally via free `edge-tts` voices and caches every asset on disk so chapters can be closed and reopened instantly without regenerating audio.

### Core Constraints
- **Zero API keys** (no Gemini API SDK, no paid TTS services).
- **Zero `ffmpeg`** (per-line `.mp3` clips played seamlessly by a dual-`<audio>` queue; durations estimated via pure-Python MPEG frame inspection).
- **Zero frontend build step** (single `static/index.html` served directly by FastAPI, styled in **Material 3 Expressive Dark Theme** with compiled GPU-compositor `linear()` springs, complete offline CSS layout skeleton, Tailwind CSS utility layer, and patched PDF.js 4.10.38 ESM).
- **Local-first persistence** in `./sessions/<session_id>/` including PDFs, extracted chunks, dialogue scripts, content-addressed `.mp3` clips, raw batch history, undo snapshots, and study resume state.

---

## 2. Tech Stack & Repository Layout

### Runtime & Test Dependencies (Pinned Floors)
- `requirements.txt` (runtime only):
  - `fastapi>=0.115,<1.0`
  - `uvicorn[standard]>=0.30,<1.0`
  - `pymupdf>=1.24,<2.0`
  - `edge-tts>=7.0.0`
  - `python-multipart>=0.0.9`
- `requirements-dev.txt` (test dependencies):
  - `pytest>=8.0`
  - `httpx>=0.27`

### Directory Structure
```text
examcast/
├── app.py                     # Thin FastAPI entrypoint (`uvicorn app:app`)
├── deepexamcast/
│   ├── __init__.py
│   ├── models.py              # Pydantic schemas + built-in VOICE_PAIRS registry
│   ├── pdf_parser.py          # Band/column-aware PyMuPDF extraction, de-hyphenation, header filtering
│   ├── prompt_builder.py      # Page-range filtering, continuity context, zero-skimming prompt
│   ├── script_parser.py       # Multi-candidate JSON extraction, Unicode speakable guard, validation
│   ├── tts_engine.py          # Content-addressed edge-tts, timeout/jitter retries, MP3 duration
│   └── session_store.py       # Per-session asyncio.Lock, 409 guard, atomic I/O, chunk coverage
├── static/
│   ├── index.html             # Single-file M3 Expressive dark-mode UI (PDF.js 4.10.38 ESM + Tailwind)
│   └── vendor/                # Optional local pdf.min.mjs + pdf.worker.min.mjs for 100% offline use
├── tests/
│   ├── test_pdf_parser.py
│   ├── test_prompt_builder.py
│   ├── test_script_parser.py
│   ├── test_tts_engine.py
│   └── test_api_integration.py
├── sessions/                  # Gitignored runtime storage: ./sessions/<session_id>/
├── docs/superpowers/specs/    # Core architecture spec + M3 Expressive UI spec
├── .impeccable.md             # Project Design Context (audience, tone, aesthetic principles)
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
└── README.md
```

### Module Boundaries
- **`deepexamcast/models.py`**: Pure Pydantic data contracts (`PageInfo`, `Chunk`, `ScriptLine`, `BatchRecord`, `StudyState`, `PageCoverage`, `SuggestedRange`, `CoverageInfo`, `SessionData`, `SessionSummary`, `GenerateRequest`, `ResynthesizeRequest`, `StatePatchRequest`, `GenerateProgress`, `VoicePair`) and canonical `VOICE_PAIRS`.
- **`deepexamcast/pdf_parser.py`**: Pure PDF ingestion (`parse_pdf_bytes(data: bytes) -> tuple[list[PageInfo], list[Chunk]]`). Handles horizontal-band column-aware ordering, de-hyphenation, repeating header/footer suppression, micro-chunk merging, and normalized bbox extraction.
- **`deepexamcast/prompt_builder.py`**: Pure prompt assembly (`build_prompt(chunks, start_page, end_page, recent_lines) -> PromptResult`). Injects the last 2 existing lines as continuity context on append batches.
- **`deepexamcast/script_parser.py`**: Pure LLM output parser (`parse_gemini_script(raw_json, valid_chunk_ids) -> ParsedScriptResult`). Extracts candidate dialogue arrays from fenced blocks, prose, or wrapper objects; strips stray markdown; enforces Unicode speakable text (`any(ch.isalnum() for ch in text)`).
- **`deepexamcast/tts_engine.py`**: Async content-addressed synthesizer (`synthesize_lines(audio_dir, lines, concurrency, progress_cb) -> SynthesisResult`) + pure-Python `estimate_mp3_duration_sec(path)` + best-effort orphan GC (`gc_unreferenced_audio(audio_dir, keep_filenames)`).
- **`deepexamcast/session_store.py`**: Sole owner of `./sessions/<session_id>/` disk I/O, per-session `asyncio.Lock` registry, `active_generations` 409 guard, live `GenerateProgress` tracker, atomic JSON writes (`tmp` + `os.replace`), raw batch/undo snapshot storage (capped to last 3 replace/resynthesize snapshots), and chunk-level coverage calculation.
- **`app.py`**: Wires FastAPI routes (offloading blocking PDF/disk work via `asyncio.to_thread` so the Uvicorn event loop never blocks audio streaming), streams uploads in 1 MB chunks, sets explicit JS/CSS MIME types on `/static/vendor/*`, maps domain errors to clean `400`/`404`/`409`/`413`/`502` responses, and serves `static/index.html`.

---

## 3. On-Disk Storage, Concurrency & Data Model

### Session ID Generation & Path Safety
- Uploaded PDF filenames are ASCII-slugified to `[a-z0-9_-]`, stripped of leading/trailing hyphens/underscores, and truncated to `<= 70` chars.
- **Empty-slug fallback:** If the sanitized slug is empty (e.g., non-ASCII `अध्याय1.pdf` or `---.pdf`), fall back to `"doc"`.
- Append `-<6-hex-chars>` (e.g., `ch04-deadlocks-7f3a9c` or `doc-7f3a9c`).
- All routes validate `session_id` against `^[a-z0-9][a-z0-9_-]{1,80}$`.

### Directory Layout (`./sessions/<session_id>/`)
```text
sessions/<session_id>/
├── source.pdf                            # Original uploaded PDF bytes
├── session.json                          # Authoritative lightweight state & script (atomically written)
├── raw_scripts/
│   ├── b_20261120_081500_a1b2.json       # Pasted Gemini JSON archive (excluded from GET /session)
│   └── b_20261120_081500_a1b2.prev.json  # Displaced script snapshot on replace/resynthesize (last 3 kept)
└── audio/
    ├── 9f86d081884c7d659a2feaa0c55ad015.mp3  # Content-addressed: sha256(voice + "\0" + text)[:32]
    └── ...
```

### Content-Addressed Audio (`audio/{audio_hash}.mp3`) & Multi-Step Undo GC
1. **Zero Windows file-lock crashes:** New clips never overwrite a currently streaming `.mp3` handle (`WinError 5`/`WinError 32` eliminated).
2. **True atomic failure safety:** If generation fails midway on clip 20 of 50 during `replace` mode, the existing `session.json` and every old `<hash>.mp3` it references remain 100% untouched, while the 20 newly finished clips stay cached on disk for instant retry.
3. **100% cache reuse across edits/reorders/undo:** Inserting, deleting, or reordering lines never invalidates unchanged clips.
4. **No `manifest.json` needed:** File existence + `st_size > 0` at `audio/{audio_hash}.mp3` IS the verified cache.
5. **Immutable HTTP caching:** `GET /audio/{filename}` serves with `Cache-Control: public, max-age=31536000, immutable`.
6. **Multi-step undo safe GC:** Retain `.prev.json` snapshots for the **last 3** `replace`/`resynthesize` operations in `session.batches` (unlinking older `.prev.json` files and setting their `prev_script_file = null` before GC). After `session.json` commits atomically, `gc_unreferenced_audio()` builds `keep_filenames` from `session.script` **plus every retained `prev_script_file` snapshot** in `session.batches`, then unlinks unreferenced `.mp3` files on a best-effort basis (ignoring `PermissionError` on Windows).

### Per-Session Concurrency & Lock Discipline
- `session_store.py` maintains an in-process `dict[session_id, asyncio.Lock]`, `active_generations: set[session_id]`, and `progress_map: dict[session_id, GenerateProgress]`.
- **Single-writer generation guard:** `POST /generate` and `POST /resynthesize` check/add `session_id` in `active_generations` under the session lock; if already running, immediately return **HTTP `409 Conflict`**.
- **Non-blocking synthesis + re-read-before-merge:** Once validated and registered in `active_generations`, the session lock is **released** during slow `edge-tts` network I/O so `PATCH /state` works freely while generating. When synthesis finishes, the handler re-acquires the session lock, **re-reads fresh `session.json`**, merges the new `script` + `batches` while **preserving the latest `state`**, writes atomically, and in a **`finally` block** always removes `session_id` from `active_generations` AND resets `GenerateProgress` (`running = False, phase = "idle"`) so a `502` or error never leaves `/generate/status` stuck reporting `"running": true`.
- `PATCH /state`, `POST /undo`, and `DELETE /sessions/{id}` acquire the per-session lock (`undo` and `DELETE` return `409` if `session_id in active_generations`).

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
      "audio_hash": "9f86d081884c7d659a2feaa0c55ad015",
      "audio_file": "9f86d081884c7d659a2feaa0c55ad015.mp3",
      "duration_sec": 3.4
    }
  ],
  "batches": [
    {
      "batch_id": "b_20261120_081500_a1b2",
      "timestamp": "2026-11-20T08:15:00Z",
      "mode": "replace",
      "start_index": 0,
      "line_count": 42,
      "page_range": [1, 4],
      "raw_script_file": "raw_scripts/b_20261120_081500_a1b2.json",
      "prev_script_file": null
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

### Chunk-Level Coverage & Budgeted Next-Batch Calculation
Computed dynamically on session read (never stale):
- `covered_chunk_ids`: sorted unique valid chunk IDs referenced by any line in `script`.
- `pages_coverage`: per page `1..page_count`:
  - `{ "page", "covered_chunks", "total_chunks", "missed_chunk_ids", "status" }`
  - `status`: `"empty"` (`total_chunks == 0`), `"uncovered"` (`covered_chunks == 0`), `"partial"` (`0 < covered_chunks < total_chunks`), or `"full"` (`covered_chunks == total_chunks`).
- `fully_covered_pages`: pages with `status == "full"`.
- `partial_pages`: list of page summaries where `status == "partial"`, including `missed_chunk_ids`.
- `suggested_next_range`:
  1. Find the smallest 1-indexed page `p` with `status in ("uncovered", "partial")`. (If all text-bearing pages are `"full"` or PDF has 0 text chunks, default to `start_page = 1`.)
  2. Expand `end_page` from `p` up to `min(p + 4, page_count)` while keeping cumulative `chunk_count <= 28` and cumulative `char_count <= 12000` (always including at least page `p` itself).
  3. Returns `{ "start_page", "end_page", "chunk_count", "char_count" }`.

---

## 4. Built-in Voice Pairs

Defined once in `deepexamcast/models.py` and exposed via `GET /api/voices` (and session responses):

| `id` | Label | `host_a_voice` (Professor) | `host_b_voice` (Student) |
| :--- | :--- | :--- | :--- |
| `us_natural` | US Natural | `en-US-AndrewMultilingualNeural` | `en-US-AvaMultilingualNeural` |
| `in_english` | Indian English | `en-IN-PrabhatNeural` | `en-IN-NeerjaExpressiveNeural` |
| `uk_natural` | UK Natural | `en-GB-RyanNeural` | `en-GB-SoniaNeural` |

Default for new sessions: `us_natural`.

---

## 5. Backend API Specification

All blocking PyMuPDF/disk calls execute via `asyncio.to_thread()` so Uvicorn's event loop stays responsive for audio streaming and progress polling.

| Endpoint | Behavior & Status Codes |
| :--- | :--- |
| `GET /` | Serves `static/index.html` (`text/html; charset=utf-8`). |
| `GET /static/vendor/{filename}` | Serves optional vendored PDF.js files if present (`404` otherwise, allowlist `^[a-z0-9._-]+\.(mjs\|js\|css)$`). **Explicit MIME types** (Windows-safe): `text/javascript; charset=utf-8` for `.mjs`/`.js`, `text/css; charset=utf-8` for `.css`. |
| `GET /api/voices` | Returns `{ "voice_pairs": [...] }`. |
| `POST /api/upload` | Streams multipart `file` in **1 MB chunks**: verifies non-empty + `%PDF-` magic header on chunk 1 (`400` immediately if invalid) and aborts immediately with **`413`** if cumulative bytes exceed **100 MB**. Parses via `asyncio.to_thread(parse_pdf_bytes, ...)`; cleans up partial dir on any error. Returns `{ "session", "coverage", "voice_pairs", "warnings" }` (warns if 0 selectable text chunks extracted). |
| `GET /api/sessions` | Lists saved sessions sorted by `updated_at` desc (`session_id`, `title`, `page_count`, `chunk_count`, `covered_chunk_count`, `fully_covered_page_count`, `line_count`, `estimated_total_sec`, `last_line_index`, `created_at`, `updated_at`). |
| `GET /api/sessions/{session_id}` | Returns `{ "session", "coverage", "voice_pairs" }` (`404` if missing). Raw JSON archives stay on disk and are excluded from payload. |
| `DELETE /api/sessions/{session_id}` | Acquires session lock (`409` if generation running, `404` if missing), removes `./sessions/<session_id>/`, returns `{ "deleted": session_id }`. |
| `GET /api/sessions/{session_id}/pdf` | Streams `source.pdf` (`application/pdf`). |
| `GET /api/sessions/{session_id}/prompt?start_page=1&end_page=5` | Validates `1 <= start_page <= end_page <= page_count` and `>= 1` chunk in range (`400` otherwise). Returns `{ "prompt", "start_page", "end_page", "chunk_count", "chunk_id_range", "char_count" }`. |
| `GET /api/sessions/{session_id}/generate/status` | Non-blocking read of in-memory synthesis progress: `{ "running": bool, "phase": "idle" \| "synthesizing" \| "committing", "completed": int, "cached": int, "total": int, "failed": int }`. Always resets to idle in `finally`. |
| `POST /api/sessions/{session_id}/generate` | Body: `{ "raw_json", "host_a_voice", "host_b_voice", "mode": "replace" \| "append", "start_page"?: int, "end_page"?: int }`. Rejects concurrent call with `409`; invalid JSON/schema with `400`; TTS failure with `502` (preserving old `session.json` and keeping completed `<hash>.mp3` clips cached). Computes `missed_chunk_ids` against `[start_page, end_page]` (or inferred `[min_page, max_page]` of valid referenced chunks in the batch if omitted) and surfaces explicit zero-skimming warnings. Archives raw JSON to `raw_scripts/<batch_id>.json` (and prior script to `<batch_id>.prev.json` on `replace`, capping retained snapshots to last 3). Returns `{ "session", "coverage", "stats": { "generated_count", "cached_count", "total_lines" }, "missed_chunk_ids", "warnings" }`. |
| `POST /api/sessions/{session_id}/undo` | Pops the latest entry from `batches` (`400` if empty, `409` if generating): on `append` truncates `script` to `batch.start_index`; on `replace` or `resynthesize` restores `prev_script_file` (or `[]`). Clamps `last_line_index`, commits atomically, runs multi-step-safe audio GC, returns `{ "session", "coverage", "undone_batch" }`. |
| `POST /api/sessions/{session_id}/resynthesize` | Body: `{ "host_a_voice", "host_b_voice" }`. Returns **`400`** if `len(script) == 0`; **`409`** if already generating. Re-hashes and synthesizes all existing script lines with the new voices (live progress status, content-addressed cache hits, preserves latest `state` via re-read-before-merge, saves `prev_script_file` undo snapshot, best-effort GC after commit). Returns `{ "session", "coverage", "stats" }`. |
| `GET /api/sessions/{session_id}/audio/{filename}` | Strict regex `^[0-9a-f]{32}\.mp3$` (`400` otherwise). Serves `audio/{filename}` with `media_type="audio/mpeg"` and `Cache-Control: public, max-age=31536000, immutable` (`404` if missing). |
| `PATCH /api/sessions/{session_id}/state` | Acquires per-session lock; partial update of `last_line_index` (clamped `[0, max(0, len(script)-1)]`), `playback_rate` (validated `[0.5, 3.0]`), `voice_pair_id`, `host_a_voice`, `host_b_voice`, `auto_scroll`. Returns `{ "state": ... }`. |

---

## 6. Core Processing Algorithms

### 6.1 Horizontal-Band Column-Aware PDF Parsing (`pdf_parser.py`)
1. Open PDF bytes via `fitz.open(stream=data, filetype="pdf")`.
2. Pass 1 — Extract raw text blocks across all pages `1..N`:
   - Read `rect = page.rect` (`width = float(rect.width)`, `height = float(rect.height)`). Normalize each block against `(rect.x0, rect.y0, rect.width, rect.height)` clamped to `[0.0, 1.0]` (handles `/Rotate` 90°/180°/270° and non-zero `/CropBox` origins).
   - Call `page.get_text("blocks", sort=False)` and keep only text blocks (`block_type == 0`).
   - **De-hyphenate line wraps:** Apply `re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", raw_text)` before collapsing whitespace via `" ".join(text.split())`; discard empty blocks.
3. Pass 2 — Suppress repeating boilerplate headers/footers (when `page_count >= 3`):
   - Inspect blocks in top margin (`y1 < 0.07`) or bottom margin (`y0 > 0.93`).
   - Drop pure page-number blocks matching `^(?:page\s*)?\d+(?:\s*(?:/|of)\s*\d+)?$` (case-insensitive) in top/bottom margins, plus any identical normalized margin string repeated on `>= 3` pages.
4. Pass 3 — Horizontal-band column-aware reading order per page (zero dropped mid-page blocks):
   - Classify each block as **full-width** when `(x1 - x0) > 0.55 or (x0 < 0.48 and x1 > 0.52)`; all other blocks are **narrow**.
   - Sort full-width blocks by `(y0, x0)`. They partition the vertical Y-axis into ordered **horizontal bands** (before first separator, between consecutive separators, and after last separator) based on each narrow block's vertical midpoint `(y0 + y1) / 2`.
   - Within each horizontal band: split narrow blocks into `left` (`(x0 + x1) / 2 < 0.50` and `x1 <= 0.52`) and `right` (`(x0 + x1) / 2 >= 0.50` and `x0 >= 0.48`). If `len(left) >= 1 and len(right) >= 1` and `max(b.x1 for b in left) <= min(b.x0 for b in right)` (and the page has at least 2 left and 2 right column blocks overall), emit `left` sorted by `(y0, x0)` then `right` sorted by `(y0, x0)`; otherwise emit all blocks in the band sorted by `(round(y0, 3), round(x0, 3))`.
   - Emit bands and full-width separators in strict vertical order, preserving 100% of blocks including mid-page full-width section headings and figure captions.
5. Pass 4 — Micro-chunk merging:
   - Merge tiny adjacent fragments within the same band/column when either block is `< 40` chars (e.g., standalone bullet markers `"•"` / `"-"` or split caption lines) and vertical gap `< 0.015` (or same-line bullet prefix where vertical overlap > 50% and horizontal gap `< 0.04`), computing the union normalized bbox `[min(x0), min(y0), max(x1), max(y1)]` rounded to 5 decimals.
6. Assign sequential chunk IDs `C1`, `C2`, ..., `CN` across the whole PDF.

### 6.2 Deep-Dive Prompt Template (`prompt_builder.py`)
- Filters chunks to `start_page <= c.page <= end_page`, formatting each chunk strictly as:
  `[C12] (Page 3): <text>`
- Prompt instructions enforce:
  - Personas: enthusiastic Professor (`HOST_A`) and sharp Exam Student (`HOST_B`) recording a deep-dive study podcast.
  - **ZERO SKIMMING:** Cover every single chunk ID in exact sequential order from `C_start` to `C_end`. Explain every definition, mechanism, formula, edge case/exception, and likely exam question clearly using intuitive analogies and memory hooks.
  - Spoken audio discipline: 1–3 natural conversational sentences per turn; zero markdown symbols (`*`, `#`, `_`, `` ` ``) in `text`; spell out all math and symbols as natural spoken English ("x squared", "equals", "greater than or equal to", "O of n log n").
  - **Append continuity context:** When `recent_lines` (last 2 dialogue lines of existing script) are provided and `start_page > 1`, inject a brief `"PREVIOUSLY ON THIS LECTURE (do not repeat—transition smoothly into the first new chunk):"` section quoting those last 2 lines.
  - Strict JSON-only output schema:
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

### 6.3 Multi-Candidate Gemini JSON Extraction (`script_parser.py`)
1. Strip UTF-8 BOM and outer whitespace.
2. Collect candidate text regions: all markdown fenced blocks (```` ```json ... ``` ```` and ```` ``` ... ``` ````) plus the full raw string.
3. For each region, scan every `[` and `{` index with `json.JSONDecoder().raw_decode(region, idx)`:
   - If decoded value is a `list`, add as candidate list.
   - If decoded value is a `dict` (wrapper objects like `{"dialogue": [...]}` or `{"covered_chunks": [...], "script": [...]}`), inspect every `list` value inside it as a candidate list.
4. **Typo-tolerant candidate selection:** Keep non-empty lists of `dict` objects where **at least 50% of items (or `>= 1` item)** contain a `"speaker"` or `"text"` key (case-insensitive). Pick the **longest** matching list so a single typo like `"speker"` on line 27 of a 45-line paste still selects the array and surfaces `"Item 27 is missing required key 'speaker'"` in Step 5 instead of a generic failure.
   - If no valid candidate exists, surface the most informative JSON syntax error (line, column, snippet) or schema reason as `ScriptParseError` (HTTP `400`).
5. Validate & sanitize each item `i` (0-indexed; human-readable 1-based line number in error messages):
   - `speaker`: required string matching `"HOST_A"` or `"HOST_B"` (case-insensitive) → normalize to uppercase.
   - `text`: required string; collapse newlines/whitespace, strip stray markdown tokens (`**`, `*`, `` ` ``, leading `#` headings) defensively, and enforce **Unicode speakable text** via `any(ch.isalnum() for ch in text)` (supports multilingual/accented/Hinglish text while rejecting `"..."` or pure punctuation before `edge-tts` fails with `NoAudioReceived`).
   - `chunk_ids`: accept list of strings (or coerce a single string into a 1-element list); uppercase and deduplicate preserving order. Unknown chunk IDs not in `valid_chunk_ids` are dropped and added to `warnings`.
   - `exam_note`: optional string; trim and store `None` if absent/blank.

### 6.4 Hardened Concurrent `edge-tts` Engine (`tts_engine.py`)
- **Configurable concurrency:** Default `int(os.getenv("DEEPEXAMCAST_TTS_CONCURRENCY", "4"))` clamped to `[1, 5]`, enforced via `asyncio.Semaphore(concurrency)`.
- **Content hash:** `sha256(f"{voice}\0{text}".encode("utf-8")).hexdigest()[:32]`; target file `audio/{audio_hash}.mp3`.
- **Cache check:** If target file exists and `st_size > 0`, skip synthesis immediately (`cached_count += 1`) and invoke `progress_cb(cached=True)`.
- **Deduplication within batch + accurate progress accounting:** If two lines share identical `(voice, text)`, synthesize that hash only once via an in-batch `dict[audio_hash, asyncio.Task]` dedup map so concurrent tasks never collide on disk. When a duplicate line awaits the shared task, it **still invokes `progress_cb(cached=True)`** once the task completes so `completed` always reaches `total` (e.g., `50 / 50`).
- **Timeout + Jittered Retry:** Wrap every attempt in `asyncio.wait_for(edge_tts.Communicate(text, voice).save(str(tmp_path)), timeout=30.0)`. Retry up to 3 attempts with jittered exponential backoff: `(1.5 * (2 ** attempt)) * (0.7 + 0.6 * random.random())`. Verify `tmp_path.stat().st_size > 0` before atomic `os.replace(tmp_path, target_path)`, cleaning up `.tmp` on any error.
- **Pure-Python MP3 duration estimation (zero `ffmpeg`):** Read the first valid MPEG frame header (skipping any ID3v2 header, parsing MPEG version + Layer III bitrate table) to compute `duration_sec = round((file_size_bytes - audio_offset) * 8 / bitrate_bps, 2)`, falling back cleanly to `48000` bps (`edge-tts` standard 24kHz 48kbps CBR).

---

## 7. Frontend Architecture (`static/index.html`) — Material 3 Expressive

Full Element Inventory (`E-01`–`E-23`), Interaction Table (`I-01`–`I-20`), 6-class Adaptive Matrix, complete Light/Dark M3 Design Token JSON, compiled GPU-compositor CSS `linear()` springs, Physics Tier mapping (`Tier 1`/`Tier 2`/`Tier 3`), Motion Specification, and A11y states are formally defined and verified in **[2026-11-20-deepexamcast-m3-ui-spec.md](2026-11-20-deepexamcast-m3-ui-spec.md)**.

### Key Engineering Requirements Summarized
1. **Patched PDF.js 4.10.38 ESM + Cross-Origin Worker Blob Shim:**
   - Try `/static/vendor/pdf.min.mjs` first (served with explicit `text/javascript; charset=utf-8` + same-origin `/static/vendor/pdf.worker.min.mjs`).
   - On CDN fallback (`https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs`), bootstrap the worker via a same-origin Blob shim so `new Worker(...)` never triggers cross-origin main-thread fallback:
     ```js
     const blob = new Blob([`import "${CDN_WORKER_URL}";`], { type: "text/javascript" });
     pdfjsLib.GlobalWorkerOptions.workerSrc = URL.createObjectURL(blob);
     ```
   - Always pass `isEvalSupported: false` to `pdfjsLib.getDocument({ url, isEvalSupported: false })`.
2. **Offline-Safe CSS Layout Skeleton + M3 Expressive Dark Tokens:**
   - Inline `<style>` defines complete M3 Dark color roles (`surface`, `surfaceContainerLowest..Highest`, warm study-lamp amber `primary*`, cool slate-blue `secondary*` for Professor, sage-teal `tertiary*` for Student), compiled `linear()` Spatial & Effects spring variables, AND full core layout classes (top bar, top-anchored sheet, sticky playback bar, 68%/32% Supporting Pane grid, scrollable panes, buttons, chips, dialogue cards) so offline sessions render cleanly even without Tailwind Play CDN.
3. **Strict XSS Prevention:** Exclusively `textContent` / `document.createElement` for all untrusted strings (`title`, `text`, `exam_note`, `chunk_ids`, warnings, errors). Zero `innerHTML` for user/PDF/LLM data.
4. **Prompt Batch Memory:** Remember `lastCopiedRange = { start_page, end_page }` on **"Copy Prompt for Gemini Pro"** (falling back to current `From Page`/`To Page` inputs) and pass it to `POST /generate` so zero-skimming `missed_chunk_ids` warnings match the intended batch.
5. **Bounded PDF.js Canvas Window & Cancellation:** Render HiDPI canvases (`devicePixelRatio <= 2`) within `±4` of visible pages via `IntersectionObserver`; evict bitmaps (`canvas.width = 0; canvas.height = 0`) outside `±8`; cancel in-flight `RenderTask` handles cleanly on zoom/eviction.
6. **Hardened Dual-`<audio>` Queue Engine:** Two decks (`deckA`/`deckB`), `defaultPlaybackRate` + `playbackRate` synced across `.load()` and `loadedmetadata`, silent muted unlock of `standbyDeck` inside first user Play gesture, `200ms` cancellable conversational breath, `error` handler with Retry/Skip snackbar, instant 0ms keyboard shortcuts (`Space`, `ArrowLeft`, `ArrowRight`, `R`, `Esc`).

---

## 8. Error Handling & Edge Cases

- **Oversized (>100 MB) or corrupt/non-PDF upload:** Streamed 1 MB chunk check aborts immediately with HTTP `413`/`400`; no partial directory left under `./sessions/`.
- **Image-only / scanned PDF:** Upload succeeds with warning banner; prompt endpoint rejects ranges with 0 extractable chunks (`400`).
- **Concurrent generation / double-click:** HTTP `409 Conflict`; concurrent `PATCH /state` safely preserved via lock + re-read-before-merge; `GenerateProgress` always resets to idle in `finally`.
- **Messy, wrapper-object, single-typo, or truncated Gemini JSON:** Typo-tolerant multi-candidate extraction surfaces exact line/field errors (`400`); Unicode speakable check accepts multilingual text while rejecting `"..."`.
- **Gemini skimming / unknown chunk IDs:** Missed chunks within `[start_page, end_page]` (or inferred page span) and unknown IDs are surfaced explicitly in `warnings` and per-page `"partial"` coverage.
- **Transient `edge-tts` timeouts / throttling:** 30s per-clip timeout, jittered 3-attempt backoff, content-addressed cache preserves all finished clips without touching old `session.json`.
- **Accidental bad paste or voice change:** Instant recovery via `POST /undo` (multi-step safe with last-3 `.prev.json` retention), `POST /resynthesize` (`400` if empty script), and `DELETE /api/sessions/{id}`.
- **Security hardening:** Patched PDF.js 4.10.38 with `isEvalSupported: false` + Blob worker shim, explicit `.mjs` MIME types, zero `innerHTML` XSS exposure, strict regex allowlists on `session_id`, `audio/{filename}`, and `static/vendor/{filename}`.

---

## 9. Testing & Verification Strategy

### Automated Test Suite (`pytest`)
1. **`tests/test_pdf_parser.py`**: Synthetic PyMuPDF fixtures testing sequential `C1..CN` IDs, normalized `[0.0, 1.0]` bboxes, rotated pages (`90°`/`270°`), non-zero `/CropBox` origins, two-column reading order **with mid-page full-width section headings**, hyphenated line wraps (`dead-\nlock`), repeating header/footer & page-number suppression, micro-chunk merging, blank/image block filtering, and corrupt PDF rejection.
2. **`tests/test_prompt_builder.py`**: Exact `[C12] (Page 3): <text>` formatting, page-range filtering, zero-skimming & JSON schema instructions, continuity snippet injection from last 2 lines, and empty-range rejection.
3. **`tests/test_script_parser.py`**: Plain JSON, fenced blocks, Gemini prose containing `[1, 5]`, wrapper objects `{"covered_chunks": [...], "script": [...]}`, literal `]` inside strings, **single-item typo (`"speker"`) reporting exact item error**, markdown stripping, **Unicode multilingual/Hinglish speakable acceptance** + non-speakable `"..."` rejection, single-string `chunk_ids` normalization, unknown chunk ID warnings, and syntax error reporting.
4. **`tests/test_tts_engine.py`**: Mocked `edge_tts.Communicate` verifying `Semaphore(concurrency)` bound, content-addressed `<hash>.mp3` cache hits across reorders/inserts, **in-batch duplicate dedup with complete `N/N` progress accounting**, 30s timeout handling, jittered retry recovery, partial-failure isolation, pure-Python MP3 duration estimation, and multi-snapshot-safe orphan GC (including simulated Windows `PermissionError`).
5. **`tests/test_api_integration.py`**: End-to-end FastAPI `TestClient` tests covering streamed upload (non-ASCII filename slug fallback, bad magic bytes, >100 MB `413` rejection), explicit `.mjs` MIME type on `/static/vendor/`, list/reload, PDF streaming, prompt, generate (`replace` & `append` with missed-chunk warnings for both explicit and inferred page ranges, partial/full coverage, budgeted `suggested_next_range`), concurrent `PATCH /state` preservation during generation, `409 Conflict` double-generate rejection, `/generate/status` reset after `502`, **multi-step `POST /undo` across `replace -> append -> replace` and `resynthesize`**, `POST /resynthesize` (`400` on empty script + success), `DELETE /sessions/{id}`, and audio path-traversal rejection.

### Live & Deterministic Verification Gates
1. `python -m py_compile app.py deepexamcast/*.py` passes with zero errors.
2. `python -c "import edge_tts, fitz, fastapi, uvicorn; print('ok')"` passes cleanly.
3. `pytest -v` passes 100%.
4. `python ".../m3-expressive-architect/scripts/audit_m3_spec.py" --spec docs/superpowers/specs/2026-11-20-deepexamcast-m3-ui-spec.md` exits `0`.
5. `python ".../m3-expressive-architect/scripts/audit_m3_spec.py" --code static/index.html` (and extracted style/script verification) exits `0`.
6. Boot `uvicorn app:app --host 127.0.0.1 --port 8000` and verify HTTP `200` on `GET /` and `GET /api/voices`.

---

## 10. Repository Skills Playbook (Execution & Quality Integration)

| Phase / Area | Skill(s) Applied | Concrete Enforcement |
| :--- | :--- | :--- |
| **Spec & Planning** | `brainstorming` → `writing-plans` | Approved v3 spec + verified M3 UI spec committed first; next step generates a bite-sized, zero-placeholder TDD plan in `docs/superpowers/plans/`. |
| **Material 3 Expressive UI** | `m3-expressive-architect` | Complete Stage 1–3 pipeline: `E-01..E-23` inventory, `I-01..I-20` motion table, 6 window size classes, Light/Dark M3 tokens with `surfaceContainer*` & `*Fixed*`, Expressive shape morphing (`full` ↔ `medium`/`small`), compiled `linear()` Spatial/Effects springs (`compile_springs.py`), and deterministic verification via `audit_m3_spec.py`. |
| **Visual Craft & Typography** | `impeccable`, `design-taste-frontend`, `typeset` | `.impeccable.md` Design Context; `Sora` + `Figtree` (`line-height: 1.65`, `65ch`) + `JetBrains Mono` (`tabular-nums`); SVG-only zero-emoji chrome; zero side-stripe borders or gradient text; `100dvh` layout; complete empty/loading/error/offline states. |
| **Tactile Motion Discipline** | `emil-design-eng`, `animate` | 0ms instant keyboard shortcuts (`Space`, `←`, `→`, `R`); interruptible transitions; pause snackbar timers on `document.hidden`; `@media (hover: hover)` hover gating; `prefers-reduced-motion` `<=200ms` cross-fade. |
| **Backend & TDD Execution** | `subagent-driven-development`, `systematic-debugging`, `full-output-enforcement` | Task-by-task TDD implementation with fresh review gates, root-cause debugging on any failure, and complete unabridged code. |
| **Pre-Ship Audit & Polish** | `audit`, `polish` | WCAG AA contrast (`>= 4.5:1`), `48x48dp` touch targets, ARIA roles/labels/`aria-live`, `3px` `:focus-visible` focus rings (`secondary` role), zero `innerHTML` XSS, responsive checks across all M3 window size classes. |
| **Documentation** | `create-readme` | Concise GFM `README.md` with GitHub admonitions (`[!NOTE]`/`[!TIP]`), exact Windows/Linux install & run commands, Gemini copy-paste workflow, keyboard shortcuts, and optional 2-line offline PDF.js vendoring command. |
