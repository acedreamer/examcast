# DeepExamCast — Design Specification

**Date:** 2026-11-20  
**Revision:** v2 (Critic-Hardened + Repository Skills Integrated)  
**Project:** DeepExamCast (`F:\projects\examcast`)  
**Status:** Ready for Final Spec Review

---

## 1. Overview & Goals

**DeepExamCast** is a local, zero-API-key web application that turns exam PDF chapter notes (typically ~30 pages, up to 50–60 pages) into an in-depth, two-host conversational audio lecture synchronized accurately with an interactive PDF viewer.

Users generate scripts with their existing Gemini Web subscription via a fast copy-paste JSON workflow in smart page batches, while the backend synthesizes high-quality neural audio locally via free `edge-tts` voices and caches every asset on disk so chapters can be closed and reopened instantly without regenerating audio.

### Core Constraints
- **Zero API keys** (no Gemini API SDK, no paid TTS services).
- **Zero `ffmpeg`** (per-line `.mp3` clips played seamlessly by a dual-`<audio>` queue; durations estimated via pure-Python MPEG frame inspection).
- **Zero frontend build step** (single `static/index.html` served directly by FastAPI, with patched PDF.js 4.x ESM + Tailwind CSS + inline CSS token fallback for zero FOUC and offline resilience).
- **Local-first persistence** in `./sessions/<session_id>/` including PDFs, extracted chunks, dialogue scripts, content-addressed `.mp3` clips, raw batch history, and study resume state.

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
│   ├── pdf_parser.py          # Column-aware PyMuPDF extraction, de-hyphenation, header filtering
│   ├── prompt_builder.py      # Page-range filtering, continuity context, zero-skimming prompt
│   ├── script_parser.py       # Multi-candidate JSON extraction, speakable guard, validation
│   ├── tts_engine.py          # Content-addressed edge-tts, timeout/jitter retries, MP3 duration
│   └── session_store.py       # Per-session asyncio.Lock, 409 guard, atomic I/O, chunk coverage
├── static/
│   ├── index.html             # Single-file dark-mode UI (patched PDF.js 4.10.38 ESM + Tailwind)
│   └── vendor/                # Optional local pdf.min.mjs + pdf.worker.min.mjs for 100% offline use
├── tests/
│   ├── test_pdf_parser.py
│   ├── test_prompt_builder.py
│   ├── test_script_parser.py
│   ├── test_tts_engine.py
│   └── test_api_integration.py
├── sessions/                  # Gitignored runtime storage: ./sessions/<session_id>/
├── docs/superpowers/specs/    # Design specifications
├── .impeccable.md             # Project Design Context (audience, tone, aesthetic principles)
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
└── README.md
```

### Module Boundaries
- **`deepexamcast/models.py`**: Pure Pydantic data contracts (`PageInfo`, `Chunk`, `ScriptLine`, `BatchRecord`, `StudyState`, `PageCoverage`, `SuggestedRange`, `CoverageInfo`, `SessionData`, `SessionSummary`, `GenerateRequest`, `ResynthesizeRequest`, `StatePatchRequest`, `GenerateProgress`, `VoicePair`) and canonical `VOICE_PAIRS`.
- **`deepexamcast/pdf_parser.py`**: Pure PDF ingestion (`parse_pdf_bytes(data: bytes) -> tuple[list[PageInfo], list[Chunk]]`). Handles column-aware ordering, de-hyphenation, repeating header/footer suppression, micro-chunk merging, and normalized bbox extraction.
- **`deepexamcast/prompt_builder.py`**: Pure prompt assembly (`build_prompt(chunks, start_page, end_page, recent_lines) -> PromptResult`). Injects the last 2 existing lines as continuity context on append batches.
- **`deepexamcast/script_parser.py`**: Pure LLM output parser (`parse_gemini_script(raw_json, valid_chunk_ids) -> ParsedScriptResult`). Extracts candidate dialogue arrays from fenced blocks, prose, or wrapper objects; strips stray markdown; enforces speakable alphanumeric text.
- **`deepexamcast/tts_engine.py`**: Async content-addressed synthesizer (`synthesize_lines(audio_dir, lines, concurrency, progress_cb) -> SynthesisResult`) + pure-Python `estimate_mp3_duration_sec(path)` + best-effort orphan GC (`gc_unreferenced_audio(audio_dir, keep_filenames)`).
- **`deepexamcast/session_store.py`**: Sole owner of `./sessions/<session_id>/` disk I/O, per-session `asyncio.Lock` registry, `active_generations` 409 guard, live `GenerateProgress` tracker, atomic JSON writes (`tmp` + `os.replace`), raw batch/undo snapshot storage, and chunk-level coverage calculation.
- **`app.py`**: Wires FastAPI routes (offloading blocking PDF/disk work via `asyncio.to_thread` so the Uvicorn event loop never blocks audio streaming), maps domain errors to clean `400`/`404`/`409`/`413`/`502` responses, and serves `static/index.html` and optional `static/vendor/*`.

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
├── source.pdf                      # Original uploaded PDF bytes
├── session.json                    # Authoritative lightweight state & script (atomically written)
├── raw_scripts/
│   ├── b_20261120_081500_a1b2.json # Pasted Gemini JSON archive (never returned in GET /session)
│   └── b_20261120_081500_a1b2.prev.json # Displaced script snapshot on `replace` (enables Undo)
└── audio/
    ├── 9f86d081884c7d659a2feaa0c55ad015.mp3  # Content-addressed: sha256(voice + "\0" + text)[:32]
    └── ...
```

### Why Content-Addressed Audio (`audio/{audio_hash}.mp3`)
1. **Zero Windows file-lock crashes:** New clips never overwrite a currently streaming `.mp3` handle (`WinError 5`/`WinError 32` eliminated).
2. **True atomic failure safety:** If generation fails midway on clip 20 of 50 during `replace` mode, the existing `session.json` and every old `<hash>.mp3` it references remain 100% untouched, while the 20 newly finished clips stay cached on disk for instant retry.
3. **100% cache reuse across edits/reorders/undo:** Inserting, deleting, or reordering lines never invalidates unchanged clips.
4. **No `manifest.json` needed:** File existence + `st_size > 0` at `audio/{audio_hash}.mp3` IS the verified cache.
5. **Immutable HTTP caching:** `GET /audio/{filename}` serves with `Cache-Control: public, max-age=31536000, immutable` (no `?h=` query-string cache-busting hacks).
6. **Best-effort GC after commit:** Only after `session.json` is atomically committed does `gc_unreferenced_audio()` unlink `.mp3` files not referenced by `session.script` or the most recent undo snapshot—silently ignoring `PermissionError` on Windows if a browser tab still holds a handle.

### Per-Session Concurrency & Lock Discipline
- `session_store.py` maintains an in-process `dict[session_id, asyncio.Lock]` and `active_generations: set[session_id]`.
- **Single-writer generation guard:** `POST /generate` and `POST /resynthesize` check/add `session_id` in `active_generations` under the session lock; if already running, immediately return **HTTP `409 Conflict`**.
- **Non-blocking synthesis + re-read-before-merge:** Once validated and registered in `active_generations`, the session lock is **released** during slow `edge-tts` network I/O so `PATCH /state` (speed changes, scrolling, auto-scroll toggles) works freely while generating. When synthesis finishes, the handler re-acquires the session lock, **re-reads fresh `session.json`**, merges the new `script` + `batches` while **preserving the latest `state`**, writes atomically, and releases `active_generations` in a `finally` block.
- `PATCH /state`, `POST /undo`, and `DELETE /sessions/{id}` acquire the per-session lock (and `undo`/`DELETE` return `409` if `session_id in active_generations`).

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
  1. Find the smallest 1-indexed page `p` with `status in ("uncovered", "partial")`. (If all text-bearing pages are `"full"` or PDF has 0 text chunks, default to `start_page = 1`, expanding by the same budget rule.)
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
| `GET /` | Serves `static/index.html` (`text/html`). |
| `GET /static/vendor/{filename}` | Serves optional vendored PDF.js files (`pdf.min.mjs`, `pdf.worker.min.mjs`) if present; `404` otherwise (allowlist `^[a-z0-9._-]+\.(mjs|js|css)$`). |
| `GET /api/voices` | Returns `{ "voice_pairs": [...] }`. |
| `POST /api/upload` | Multipart `file` upload. Cap at **100 MB** (`413` if exceeded). Validates `%PDF-` magic header + PyMuPDF open (`400` on invalid/corrupt PDF; cleans up partial dir on any exception). Returns `{ "session", "coverage", "voice_pairs", "warnings" }` (warns if 0 selectable text chunks extracted). |
| `GET /api/sessions` | Lists saved sessions sorted by `updated_at` desc (`session_id`, `title`, `page_count`, `chunk_count`, `covered_chunk_count`, `fully_covered_page_count`, `line_count`, `estimated_total_sec`, `last_line_index`, `created_at`, `updated_at`). |
| `GET /api/sessions/{session_id}` | Returns `{ "session", "coverage", "voice_pairs" }` (`404` if missing). Raw JSON archives stay on disk and are excluded from payload. |
| `DELETE /api/sessions/{session_id}` | Acquires session lock (`409` if generation running, `404` if missing), removes `./sessions/<session_id>/`, returns `{ "deleted": session_id }`. |
| `GET /api/sessions/{session_id}/pdf` | Streams `source.pdf` (`application/pdf`). |
| `GET /api/sessions/{session_id}/prompt?start_page=1&end_page=5` | Validates `1 <= start_page <= end_page <= page_count` and >= 1 chunk in range (`400` otherwise). Returns `{ "prompt", "start_page", "end_page", "chunk_count", "chunk_id_range", "char_count" }`. |
| `GET /api/sessions/{session_id}/generate/status` | Non-blocking read of in-memory synthesis progress: `{ "running": bool, "phase": "idle" \| "synthesizing" \| "committing", "completed": int, "cached": int, "total": int, "failed": int }`. |
| `POST /api/sessions/{session_id}/generate` | Body: `{ "raw_json", "host_a_voice", "host_b_voice", "mode": "replace" \| "append", "start_page"?: int, "end_page"?: int }`. Rejects concurrent call with `409`; invalid JSON/schema with `400`; TTS failure with `502` (preserving old `session.json` and keeping completed `<hash>.mp3` clips cached). Computes `missed_chunk_ids` within the batch page range and includes explicit zero-skimming warnings. Archives raw JSON to `raw_scripts/<batch_id>.json` (and prior script to `<batch_id>.prev.json` on `replace`). Returns `{ "session", "coverage", "stats": { "generated_count", "cached_count", "total_lines" }, "missed_chunk_ids", "warnings" }`. |
| `POST /api/sessions/{session_id}/undo` | Pops the latest entry from `batches` (`400` if empty, `409` if generating): on `append` truncates `script` to `batch.start_index`; on `replace` restores `prev_script_file` (or `[]`). Clamps `last_line_index`, commits atomically, runs best-effort audio GC, returns `{ "session", "coverage", "undone_batch" }`. |
| `POST /api/sessions/{session_id}/resynthesize` | Body: `{ "host_a_voice", "host_b_voice" }`. Re-hashes and synthesizes all existing script lines with the new voices (409 guard, live progress status, content-addressed cache hits, preserves latest `state` via re-read-before-merge, best-effort GC after commit). Returns `{ "session", "coverage", "stats" }`. |
| `GET /api/sessions/{session_id}/audio/{filename}` | Strict regex `^[0-9a-f]{32}\.mp3$` (`400` otherwise). Serves `audio/{filename}` with `media_type="audio/mpeg"` and `Cache-Control: public, max-age=31536000, immutable` (`404` if missing). |
| `PATCH /api/sessions/{session_id}/state` | Acquires per-session lock; partial update of `last_line_index` (clamped `[0, max(0, len(script)-1)]`), `playback_rate` (validated `[0.5, 3.0]`), `voice_pair_id`, `host_a_voice`, `host_b_voice`, `auto_scroll`. Returns `{ "state": ... }`. |

---

## 6. Core Processing Algorithms

### 6.1 Column-Aware PDF Parsing (`pdf_parser.py`)
1. Open PDF bytes via `fitz.open(stream=data, filetype="pdf")`.
2. Pass 1 — Extract raw text blocks across all pages `1..N`:
   - Read `rect = page.rect` (`width = float(rect.width)`, `height = float(rect.height)`). Note: PyMuPDF's `page.rect` already accounts for `/Rotate` (90°/180°/270°) and `/CropBox` shift; normalize each block against `(rect.x0, rect.y0, rect.width, rect.height)` clamped to `[0.0, 1.0]`.
   - Call `page.get_text("blocks", sort=False)` and keep only text blocks (`block_type == 0`).
   - **De-hyphenate line wraps:** Apply `re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", raw_text)` before collapsing whitespace via `" ".join(text.split())`; discard empty blocks.
3. Pass 2 — Suppress repeating boilerplate headers/footers (when `page_count >= 3`):
   - Inspect blocks in top margin (`y1 < 0.07`) or bottom margin (`y0 > 0.93`).
   - Drop pure page-number blocks matching `^(?:page\s*)?\d+(?:\s*(?:/|of)\s*\d+)?$` (case-insensitive) in top/bottom margins, plus any identical normalized margin string repeated on `>= 3` pages.
4. Pass 3 — Column-aware reading order per page:
   - Partition remaining blocks into full-width (`(x1 - x0) > 0.55` or straddling center `0.42..0.58`), left-column (`x1 <= 0.54`), and right-column (`x0 >= 0.46`).
   - If `len(left) >= 2` and `len(right) >= 2` with no overlap between `max(b.x1 for b in left)` and `min(b.x0 for b in right)` (clear vertical gutter): emit full-width blocks above the columns sorted by `y0`, then left column sorted by `(y0, x0)`, then right column sorted by `(y0, x0)`, then full-width blocks below sorted by `y0`.
   - Otherwise (single-column layout): sort by `(round(y0, 3), round(x0, 3))`.
5. Pass 4 — Micro-chunk merging:
   - Merge tiny adjacent fragments in the same column when either block is `< 40` chars (e.g., standalone bullet markers `"•"` / `"-"` or split caption lines) and vertical gap `< 0.015` (or same-line bullet prefix where vertical overlap > 50% and horizontal gap `< 0.04`), computing the union normalized bbox `[min(x0), min(y0), max(x1), max(y1)]` rounded to 5 decimals.
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
4. Score/filter candidate lists: keep only non-empty lists where every item is a `dict` containing both `"speaker"` and `"text"` keys (case-insensitive). Select the **longest** matching dialogue list (so prose like `"pages [1, 5]"` or `{"covered_chunks": ["C1", "C2"]}` is never mistaken for the script!).
   - If no valid candidate exists, surface the most informative JSON syntax error (line, column, and snippet) or schema reason as `ScriptParseError` (HTTP `400`).
5. Validate & sanitize each item `i`:
   - `speaker`: case-insensitive `"HOST_A"` or `"HOST_B"` → normalize to uppercase.
   - `text`: collapse newlines/whitespace, strip stray markdown tokens (`**`, `*`, `` ` ``, leading `#` headings) defensively, and verify **speakable content** (`re.search(r"[A-Za-z0-9]", text)` must match; lines containing only `"..."` or symbols raise `ScriptParseError` citing item `i` so `edge-tts` never fails with `NoAudioReceived`).
   - `chunk_ids`: accept list of strings (or coerce a single string into a 1-element list); uppercase and deduplicate preserving order. Unknown chunk IDs not in `valid_chunk_ids` are dropped and added to `warnings`.
   - `exam_note`: optional string; trim and store `None` if absent/blank.

### 6.4 Hardened Concurrent `edge-tts` Engine (`tts_engine.py`)
- **Configurable concurrency:** Default `int(os.getenv("DEEPEXAMCAST_TTS_CONCURRENCY", "4"))` clamped to `[1, 5]`, enforced via `asyncio.Semaphore(concurrency)`.
- **Content hash:** `sha256(f"{voice}\0{text}".encode("utf-8")).hexdigest()[:32]`; target file `audio/{audio_hash}.mp3`.
- **Cache check:** If target file exists and `st_size > 0`, skip synthesis immediately (`cached_count += 1`) and call `progress_cb(cached=True)`.
- **Deduplication within batch:** If two lines share identical `(voice, text)`, synthesize that hash only once via an in-batch `dict[audio_hash, asyncio.Task]` dedup map so concurrent tasks never collide on the same target filename.
- **Timeout + Jittered Retry:** Wrap every attempt in `asyncio.wait_for(edge_tts.Communicate(text, voice).save(str(tmp_path)), timeout=30.0)`. Retry up to 3 attempts with jittered exponential backoff: `(1.5 * (2 ** attempt)) * (0.7 + 0.6 * random.random())`. Verify `tmp_path.stat().st_size > 0` before atomic `os.replace(tmp_path, target_path)`, cleaning up `.tmp` on any error.
- **Pure-Python MP3 duration estimation (zero `ffmpeg`):** After synthesis (or cache hit), read the first valid MPEG frame header (sync bits `0xFFE`, MPEG version + Layer III bitrate table) to compute exact `duration_sec = round((file_size_bytes - id3_tag_size) * 8 / bitrate_bps, 2)`, falling back cleanly to `48000` bps (`edge-tts` standard 24kHz 48kbps CBR).

---

## 7. Frontend Architecture (`static/index.html`)

### 7.1 Loading Strategy, Security & Zero-FOUC Resilience
- **Patched PDF.js 4.x ESM (CVE-2024-4367 mitigated):** Load `pdfjs-dist@4.10.38` via `<script type="module">`, attempting local `/static/vendor/pdf.min.mjs` first and falling back seamlessly to `https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs` (matching worker URL). Always call `pdfjsLib.getDocument({ url, isEvalSupported: false })`.
- **Tailwind CSS + Inline Token Baseline:** Load Tailwind CSS via CDN alongside an inline `<style>` block declaring full OKLCH design tokens, typography, layout grid, and button/card classes so initial paint has **zero FOUC** and saved chapters stay usable even if the CDN is unreachable.
- **Strict XSS Prevention:** Every untrusted string (`title`, `text`, `exam_note`, `chunk_ids`, warnings, errors) MUST be inserted exclusively via `textContent` / `document.createElement`. Zero `innerHTML` with user, PDF, or LLM content.

### 7.2 Visual Design System & Motion Engineering (Grounded in Repository Skills)
- **Aesthetic Direction (`impeccable` + `design-taste-frontend`):** *Nocturnal, studious, razor-sharp.* Deep warm-tinted obsidian dark surfaces in OKLCH (no pure `#000000` or `#FFFFFF`, no AI purple/neon glows, no gradient text, **no `border-left`/`border-right` > 1px accent stripes** on cards/callouts).
  - Surfaces: canvas `oklch(0.145 0.010 255)`, panel `oklch(0.185 0.012 255)`, elevated active surface `oklch(0.225 0.016 255)`, hairline borders `oklch(0.29 0.014 255)`.
  - Single warm study-lamp amber accent (`oklch(0.84 0.165 86)` / `#FACC15`) for active PDF highlight (`rgba(250, 204, 21, 0.35)` + `1.5px solid rgba(245, 158, 11, 0.85)`), active dialogue card border/tint, and `exam_note` callout.
  - Restrained speaker pills: `Professor` (cool slate-sky tint) and `Student` (muted sage-teal tint).
  - **Anti-Emoji Policy:** Zero emojis anywhere in UI chrome; crisp inline SVG icons (`stroke-width="1.75"`, consistent 16px/18px sizing).
- **Typography (`impeccable` + `typeset`):**
  - Display / Chrome: `Sora` (with clean sans fallback).
  - Dialogue Body: `Figtree` at `0.9375rem` (15px) with `line-height: 1.65` (+0.08 extra leading for light-on-dark reading comfort) and `max-width: 65ch`.
  - Technical Readouts (`Line X / Y`, `Page P / N`, `C12`, `1.25x`, `~14m left`): `JetBrains Mono` with `font-variant-numeric: tabular-nums`.
- **Motion Discipline (`emil-design-eng` + `animate`):**
  - Custom curves: `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)` (buttons/toasts), `--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)` (drawer). Zero `ease-in`, zero `transition: all`, zero bounce/elastic easing.
  - **Keyboard-initiated actions (`Space`, `ArrowLeft`, `ArrowRight`, `R`): 0ms instant response (never animated).**
  - Tactile buttons: `transition: transform 160ms var(--ease-out)` with `:active { transform: scale(0.97); }`.
  - Collapsible drawer: smooth `grid-template-rows: 0fr -> 1fr` transition (`240ms var(--ease-drawer)`), GPU-friendly, no `height` layout animation.
  - Toasts: enter from `opacity: 0; transform: translateY(6px) scale(0.96)` using interruptible CSS transitions (exit 25% faster than enter), pausing auto-dismiss timers while `document.hidden` is true.
  - Hover micro-states gated behind `@media (hover: hover) and (pointer: fine)`; `@media (prefers-reduced-motion: reduce)` removes transform motion while preserving color/opacity clarity.

### 7.3 Layout & Components
- **Root Viewport:** `h-[100dvh] flex flex-col overflow-hidden` (never `h-screen`).
- **Top Control Bar:** Brand mark (**DeepExamCast**), **Session Selector `<select>`** (`title — X/Y full pgs · ~18m`), **Delete Session** icon button (with confirmation), **Upload New PDF** button, and **"Add / Generate Deep Script"** drawer toggle (`aria-expanded`).
- **Collapsible "Add / Generate Deep Script" Drawer:**
  - **Batch Row:** `From Page` / `To Page` inputs pre-filled from budgeted `suggested_next_range` + live chunk/page coverage readout (showing full vs partial pages and skipped chunk badges if any) + 1-click **"Copy Prompt for Gemini Pro"** button (`"Copied!"` toast with chunk range `C1–C24`).
  - **Paste & Voice Row:** JSON `<textarea>`, **Voice Pair `<select>`** (US Natural / Indian English / UK Natural) + **"Re-synthesize Voice"** button (for existing scripts when switching voices without re-pasting JSON), **"Append to Lecture"**, **"Replace & Generate Audio"** (with confirm guard if overwriting), and **"Undo Last Batch"** button (enabled when `batches.length > 0`).
  - **Live Progress Bar:** While `POST /generate` or `/resynthesize` is running, polls `GET /generate/status` every `1000ms` to display `"Synthesizing 14 / 48 clips (3 cached) · 11s"` with a smooth progress bar, plus inline dismissible error/warning banners (including Gemini-skipped chunk IDs).
- **Sticky Playback Bar:**
  - Real `<button>` transport controls: Previous, Play/Pause, Next, Repeat (`R`), Speed pills (`1x`, `1.25x`, `1.5x`, `1.75x`, `2x` with `aria-pressed`).
  - **Line-index scrub bar** (explicitly labeled by line index) + tabular readout: `Line X / Y`, `Page P / N` (shows last known page or `Page — / N` on empty `chunk_ids` lines), and `~14m remaining` (sum of `duration_sec` from current line onward divided by `playbackRate`).
  - Toggle button: **`Auto-Scroll: ON`** / **`Auto-Scroll: OFF`** (`aria-pressed`).
- **Main Split View (`grid-template-columns: minmax(0, 68%) minmax(0, 32%)`, stacking cleanly below `900px`):**
  - **Left Pane (68%) — Synced PDF Viewer (PDF.js):**
    - Zoom bar (`-`, `100%`, `+`, `Fit Width`) + current page indicator.
    - Pre-sized page containers for all 30–60 pages + always-mounted normalized `%` chunk overlays.
    - **Bounded Canvas Render Window + Cancellation:** Renders HiDPI (`devicePixelRatio`, capped at `2`) canvases for pages within `±4` of visible pages via `IntersectionObserver`; evicts backing bitmaps (`canvas.width = 0; canvas.height = 0;`) for pages outside `±8` so 60-page PDFs stay under ~250 MB RAM instead of 1.1 GB. Tracks per-page `RenderTask` handles and calls `task.cancel()` cleanly on zoom changes/eviction.
    - **Forward Sync:** Active chunks glow in translucent yellow (`rgba(250, 204, 21, 0.35)` + `1.5px solid rgba(245, 158, 11, 0.85)`) and smooth-scroll into center view when `Auto-Scroll` is ON (skipped cleanly if active line has `chunk_ids: []`).
    - **Reverse Sync:** Hovering covered chunks shows pointer cursor & tooltip; clicking jumps audio & sidebar immediately to the first explaining line. Uncovered chunks show subtle neutral hover tooltip.
  - **Right Pane (32%) — Live Dialogue & Exam Notes Panel:**
    - Composed empty states when no PDF is uploaded or no script has been generated yet (guiding the 3-step copy-paste workflow).
    - Scrollable dialogue cards: `Professor` / `Student` pill, `Pg X · C12` mono tag, spoken dialogue text (`Figtree`, `65ch`), and amber-tinted full-border `exam_note` callout (no left-stripe border).
    - Active card styled with 1px amber border + elevated warm-tinted surface + live indicator dot, auto-scrolling smoothly into view. Clicking any card jumps playback & PDF immediately.

### 7.4 Hardened Dual-`<audio>` Gapless-Feel Queue Engine
- Two `HTMLAudioElement` instances (`deckA`, `deckB`), `activeDeck`, `standbyDeck`, `breathTimer`, monotonic `playbackToken`.
- **Speed preservation:** Whenever speed changes (or on restore), update BOTH `defaultPlaybackRate = rate` AND `playbackRate = rate` on both decks, and re-apply `playbackRate` on `loadedmetadata` and immediately prior to `.play()` (prevents browser `.load()` reset to `1.0`).
- **Autoplay gesture unlock:** Inside the user's first Play click/`Space` handler, unlock the idle `standbyDeck` silently (`muted = true`, `play()` → immediate `pause()`, `muted = false`) so the `200ms` `breathTimer` handoff never trips Safari/strict Chromium autoplay blocks.
- **Gapless-feel preloading:** While line `i` plays from `/api/sessions/{id}/audio/{audio_file}`, preload line `i + 1` on `standbyDeck` (`preload = "auto"`). On `ended` (matching `playbackToken`), wait `200ms` (`breathTimer`), swap decks, play line `i + 1`, sync UI, and persist `last_line_index` (debounced 800ms).
- **Playback error / stalled recovery:** Attach `error` listener to both decks; on failure, transition cleanly to paused state and surface an inline toast with **"Retry Line"** and **"Skip to Next"** buttons so playback never silently hangs.
- **Keyboard Shortcuts:** `Space` (Play/Pause), `ArrowLeft` (Prev), `ArrowRight` (Next), `R`/`r` (Replay current line) — instant 0ms response, ignored inside `<input>`, `<textarea>`, `<select>`, `contentEditable`, or when Ctrl/Alt/Meta modifiers are held.

---

## 8. Error Handling & Edge Cases

- **Oversized (>100 MB) or corrupt/non-PDF upload:** HTTP `413`/`400` with clear message; no partial directory left under `./sessions/`.
- **Image-only / scanned PDF:** Upload succeeds with warning banner; prompt endpoint rejects ranges with 0 extractable chunks (`400`).
- **Concurrent generation / double-click:** HTTP `409 Conflict` with friendly message; concurrent `PATCH /state` safely preserved via lock + re-read-before-merge.
- **Messy, wrapper-object, or truncated Gemini JSON:** Multi-candidate extraction handles prose arrays & wrapper objects; broken/non-speakable input returns HTTP `400` with line/column snippet.
- **Gemini skimming / unknown chunk IDs:** Missed chunks within the batch's page range and unknown IDs are surfaced explicitly in `warnings` and per-page `"partial"` coverage.
- **Transient `edge-tts` timeouts / throttling:** 30s per-clip timeout, jittered 3-attempt backoff, content-addressed cache preserves all finished clips without touching old `session.json`.
- **Accidental bad paste or voice change:** Instant recovery via `POST /undo`, `POST /resynthesize`, and `DELETE /api/sessions/{id}`.
- **Security hardening:** Patched PDF.js 4.10.38 with `isEvalSupported: false`, zero `innerHTML` XSS exposure, strict regex allowlists on `session_id`, `audio/{filename}`, and `static/vendor/{filename}`.

---

## 9. Testing & Verification Strategy

### Automated Test Suite (`pytest`)
1. **`tests/test_pdf_parser.py`**: Synthetic PyMuPDF fixtures testing sequential `C1..CN` IDs, normalized `[0.0, 1.0]` bboxes, **rotated pages (90°/270°)**, **non-zero `/CropBox` origins**, **two-column reading order**, **hyphenated line wraps (`dead-\nlock`)**, **repeating header/footer & page-number suppression**, **micro-chunk merging**, blank/image block filtering, and corrupt PDF rejection.
2. **`tests/test_prompt_builder.py`**: Exact `[C12] (Page 3): <text>` formatting, page-range filtering, zero-skimming & JSON schema instructions, **continuity snippet injection from last 2 lines**, and empty-range rejection.
3. **`tests/test_script_parser.py`**: Plain JSON, fenced blocks, Gemini prose containing `[1, 5]`, wrapper objects `{"covered_chunks": [...], "script": [...]}`, literal `]` inside strings, markdown stripping, **non-speakable `"..."` rejection**, single-string `chunk_ids` normalization, unknown chunk ID warnings, and syntax error reporting.
4. **`tests/test_tts_engine.py`**: Mocked `edge_tts.Communicate` verifying `Semaphore(concurrency)` bound, content-addressed `<hash>.mp3` cache hits across reorders/inserts, in-batch duplicate dedup, **30s timeout handling**, **jittered retry recovery**, **partial-failure isolation** (completed clips kept, existing files untouched), **pure-Python MP3 duration estimation**, and best-effort orphan GC (including simulated Windows `PermissionError`).
5. **`tests/test_api_integration.py`**: End-to-end FastAPI `TestClient` tests covering upload (including **non-ASCII filename slug fallback** and **>100 MB rejection**), list/reload, PDF streaming, prompt, generate (`replace` & `append` with **missed-chunk warnings** & **chunk-level partial/full coverage** & **budgeted `suggested_next_range`**), **concurrent `PATCH /state` preservation during generation**, **`409 Conflict` double-generate rejection**, live `/generate/status`, `POST /undo` (both append & replace), `POST /resynthesize`, `DELETE /sessions/{id}`, and audio path-traversal rejection.

### Live Verification Gate (Deliverable Checks)
1. `python -m py_compile app.py deepexamcast/*.py` passes with zero errors.
2. `python -c "import edge_tts, fitz, fastapi, uvicorn; print('ok')"` passes cleanly.
3. `pytest -v` passes 100%.
4. Boot `uvicorn app:app --host 127.0.0.1 --port 8000` and verify HTTP `200` on `GET /` and `GET /api/voices`.

---

## 10. Repository Skills Playbook (Execution & Quality Integration)

Every phase of building DeepExamCast binds explicitly to our installed skills so engineering quality, visual craft, motion polish, and documentation stay disciplined end-to-end:

| Phase / Area | Skill(s) Applied | Concrete Enforcement |
| :--- | :--- | :--- |
| **Spec & Planning** | `brainstorming` → `writing-plans` | Approved v2 spec committed first; next step generates a bite-sized, zero-placeholder TDD plan in `docs/superpowers/plans/`. |
| **Backend & Testing** | `subagent-driven-development`, `systematic-debugging`, `full-output-enforcement` | Task-by-task TDD implementation with fresh review gates, root-cause debugging on any failure, and complete unabridged code. |
| **UI Design System** | `impeccable`, `design-taste-frontend`, `typeset` | `.impeccable.md` Design Context; OKLCH warm-tinted dark surfaces; `Sora` + `Figtree` + `JetBrains Mono` (`tabular-nums`); SVG-only zero-emoji chrome; zero left-stripe borders or gradient text; `100dvh` CSS Grid layout; complete empty/loading/error states. |
| **UI Motion & Feel** | `emil-design-eng`, `animate` | 0ms instant keyboard navigation; `scale(0.97)` tactile press with custom `--ease-out`; `grid-template-rows` drawer transition; interruptible toast transitions pausing on hidden tab; GPU-only `transform`/`opacity`; `@media (hover: hover)` and `prefers-reduced-motion`. |
| **Pre-Ship Audit & Polish** | `audit`, `polish` | Verify WCAG AA contrast (`>= 4.5:1`), ARIA roles/labels/`aria-live`, `:focus-visible`, zero `innerHTML` XSS, responsive collapse `< 900px`, and zero console errors/layout shift. |
| **Documentation** | `create-readme` | Concise GFM `README.md` with GitHub admonitions (`[!NOTE]`/`[!TIP]`), exact Windows/Linux install & run commands, Gemini workflow, keyboard shortcuts, and optional 2-line offline PDF.js vendoring command. |
