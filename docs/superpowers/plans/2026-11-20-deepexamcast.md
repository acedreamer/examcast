# DeepExamCast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build **DeepExamCast**, a local, zero-API-key, zero-`ffmpeg`, zero-frontend-build-step FastAPI + Material 3 Expressive web app that converts exam PDF chapter notes into synchronized two-host `edge-tts` audio lectures from copy-pasted Gemini Web JSON scripts.

**Architecture:** Thin `app.py` FastAPI router backed by focused modules in `deepexamcast/` (`models.py`, `pdf_parser.py`, `prompt_builder.py`, `script_parser.py`, `tts_engine.py`, `session_store.py`), content-addressed audio storage (`sessions/<session_id>/audio/<sha256[:32]>.mp3`), per-session `asyncio.Lock` concurrency control, and a single-file Material 3 Expressive dark-mode frontend (`static/index.html`) using patched PDF.js `4.10.38` ESM with bounded canvas rendering and a hardened dual-`<audio>` queue.

**Tech Stack:** Python 3.13+, FastAPI (`>=0.115,<1.0`), Uvicorn (`>=0.30,<1.0`), PyMuPDF (`>=1.24,<2.0`), `edge-tts` (`>=7.0.0`), `python-multipart` (`>=0.0.9`), Pytest (`>=8.0`), HTTPX (`>=0.27`), Material 3 Expressive Web CSS (`linear()` springs + inline OKLCH/hex tokens + Tailwind CDN), PDF.js `4.10.38` ESM.

## Global Constraints

- **Zero API keys, zero `ffmpeg`, zero frontend build step.**
- **Pinned dependencies:** `requirements.txt` contains `fastapi>=0.115,<1.0`, `uvicorn[standard]>=0.30,<1.0`, `pymupdf>=1.24,<2.0`, `edge-tts>=7.0.0`, `python-multipart>=0.0.9`. `requirements-dev.txt` contains `pytest>=8.0`, `httpx>=0.27`.
- **Content-addressed audio:** Filenames under `sessions/<session_id>/audio/` are `{audio_hash}.mp3` where `audio_hash = sha256(f"{voice}\0{text}".encode("utf-8")).hexdigest()[:32]`, validated by `^[0-9a-f]{32}\.mp3$`, served with `Cache-Control: public, max-age=31536000, immutable`. No `manifest.json` is used.
- **Session IDs & safety:** Validated against `^[a-z0-9][a-z0-9_-]{1,80}$`, built from ASCII slug `<=70` chars (falling back to `"doc"` if empty) plus `-<6hex>`.
- **Per-session locking & concurrency:** `session_store.py` owns `dict[session_id, asyncio.Lock]`, `active_generations`, and `progress_map`. Concurrent `POST /generate`, `POST /resynthesize`, `POST /undo`, or `DELETE /sessions/{id}` while a generation is active returns `409 Conflict`. Slow TTS I/O runs with the session lock released, then re-acquires the lock, re-reads fresh `session.json`, merges preserving `state`, commits atomically (`tmp` + `os.replace`), and resets `active_generations` + `GenerateProgress` in `finally`.
- **Streaming upload guardrails:** `POST /api/upload` reads in `1 MB` chunks, checks `%PDF-` on chunk 1 (`400` immediately if invalid), rejects uploads exceeding `100 * 1024 * 1024` bytes (`413`), offloads blocking PDF/disk work via `asyncio.to_thread()`, and cleans up partial session directories on failure.
- **Multi-step undo & audio GC:** Retain `.prev.json` snapshots for the last 3 `replace`/`resynthesize` operations; `gc_unreferenced_audio()` keeps all MP3s referenced by `session.script` plus all retained `.prev.json` snapshots, ignoring Windows `PermissionError` as best-effort. `POST /resynthesize` returns `400` if `len(script) == 0`.
- **PDF.js & vendor MIME hardening:** `/static/vendor/{filename}` (`^[a-z0-9._-]+\.(mjs|js|css)$`) forces `text/javascript; charset=utf-8` for `.mjs`/`.js` and `text/css; charset=utf-8` for `.css`. Frontend loads `pdfjs-dist@4.10.38` ESM with `isEvalSupported: false` and a same-origin `Blob` Web Worker shim when falling back to CDN.
- **Material 3 Expressive UI & Security:** Implement every element `E-01`..`E-23` and interaction `I-01`..`I-20` from `docs/superpowers/specs/2026-11-20-deepexamcast-m3-ui-spec.md`; use compiled `linear()` springs (`compile_springs.py --platform web --scheme expressive`); zero `transition: all`, zero `ease-in-out`, zero layout-property transitions (`width`/`height`/`top`/`left`/`margin`/`padding`), zero `border-left`/`border-right` > 1px accent stripes, zero gradient text, zero emojis, zero `innerHTML` with untrusted content; `prefers-reduced-motion` `<=200ms` fade; `48x48dp` touch targets; offline-capable inline CSS layout skeleton.
- **Built-in Voice Pairs:**
  - `us_natural` ("US Natural", default): `en-US-AndrewMultilingualNeural` / `en-US-AvaMultilingualNeural`
  - `in_english` ("Indian English"): `en-IN-PrabhatNeural` / `en-IN-NeerjaExpressiveNeural`
  - `uk_natural` ("UK Natural"): `en-GB-RyanNeural` / `en-GB-SoniaNeural`

---

## File Structure

| File | Responsibility |
| :--- | :--- |
| `requirements.txt` | Pinned runtime Python dependencies |
| `requirements-dev.txt` | Pinned pytest/httpx development dependencies |
| `.impeccable.md` | Project Design Context (audience, brand personality, M3 Expressive principles) |
| `deepexamcast/__init__.py` | Package initialization |
| `deepexamcast/models.py` | Pydantic domain models, `VOICE_PAIRS`, `match_voice_pair_id`, `compute_audio_hash` |
| `deepexamcast/pdf_parser.py` | Band/column-aware PyMuPDF extraction, de-hyphenation, margin boilerplate suppression, micro-chunk merging |
| `deepexamcast/prompt_builder.py` | Page-range filtering, continuity context, zero-skimming Gemini prompt builder |
| `deepexamcast/script_parser.py` | Multi-candidate typo-tolerant JSON extractor, markdown sanitizer, Unicode speakable guard |
| `deepexamcast/tts_engine.py` | Content-addressed concurrent `edge-tts` synthesizer, timeout/jittered retry, pure-Python MP3 duration, orphan GC |
| `deepexamcast/session_store.py` | Disk I/O, per-session locks, 409/progress tracking, multi-step undo snapshots, chunk-level coverage & budgeted batching |
| `app.py` | FastAPI application factory & route handlers (`uvicorn app:app`) |
| `static/index.html` | Single-file M3 Expressive dark-mode UI (PDF.js 4.10.38 ESM, dual-`<audio>` engine, offline CSS layout skeleton) |
| `README.md` | Concise GFM documentation with install/run commands, Gemini workflow, shortcuts, and offline vendoring instructions |
| `tests/test_models.py` | Unit tests for schemas, voice matching, and audio hashing |
| `tests/test_pdf_parser.py` | Unit tests for PyMuPDF extraction, rotation, CropBox, 2-column + mid-page headings, hyphenation, headers, micro-chunks |
| `tests/test_prompt_builder.py` | Unit tests for prompt formatting, rules, continuity snippet, and validation |
| `tests/test_script_parser.py` | Unit tests for multi-candidate extraction, typo reporting, Unicode speakable check, and warnings |
| `tests/test_tts_engine.py` | Unit tests for semaphore bound, cache hits, in-batch dedup progress, timeout, jittered retry, partial recovery, duration, GC |
| `tests/test_session_store.py` | Unit tests for slug fallback, locking, chunk coverage, budgeted ranges, missed chunks, and multi-step undo GC |
| `tests/test_api_integration.py` | End-to-end FastAPI `TestClient` tests across all 15 routes, concurrency, 409/413/400/502, undo, resynthesize, delete |
| `tests/test_frontend_contract.py` | Automated HTML/CSS/JS contract checks + deterministic `audit_m3_spec.py --code` gate |

---

### Task 1: Project Scaffolding, Dependencies, Design Context & Domain Models

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.impeccable.md`
- Create: `deepexamcast/__init__.py`
- Create: `deepexamcast/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: Pydantic v2 (`BaseModel`, `Field`)
- Produces (`deepexamcast/models.py`): `VoicePair`, `VOICE_PAIRS`, `DEFAULT_VOICE_PAIR_ID`, `match_voice_pair_id(host_a_voice: str, host_b_voice: str) -> str`, `compute_audio_hash(voice: str, text: str) -> str`, `PageInfo`, `Chunk`, `ScriptLine`, `BatchRecord`, `StudyState`, `PageCoverage`, `SuggestedRange`, `CoverageInfo`, `SessionData`, `SessionSummary`, `GenerateRequest`, `ResynthesizeRequest`, `StatePatchRequest`, `GenerateProgress`

- [ ] **Step 1: Create `requirements.txt`, `requirements-dev.txt`, `.impeccable.md`, and `deepexamcast/__init__.py`**

Write `requirements.txt`:
```text
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30,<1.0
pymupdf>=1.24,<2.0
edge-tts>=7.0.0
python-multipart>=0.0.9
```

Write `requirements-dev.txt`:
```text
pytest>=8.0
httpx>=0.27
```

Write `.impeccable.md`:
```markdown
## Design Context

### Users
University B.Tech and exam students studying 20–60 page chapter notes late at night on laptops, desktops, and tablets. They need zero-friction audio lectures anchored line-by-line to their exact PDF paragraphs and formulas.

### Brand Personality
Nocturnal, studious, razor-sharp. Calm focus under exam deadlines without visual clutter or neon distractions.

### Aesthetic Direction
Material 3 (Expressive) Nocturnal Dark Theme (`#111318` obsidian surface ladder with study-lamp warm amber `#F5C84C` primary, cool slate-blue `#ADC6FF` for Professor `HOST_A`, and sage-teal `#80D5C8` for Student `HOST_B`). `Sora` display chrome, `Figtree` high-legibility dialogue body (`15px`, `1.65` line height, `65ch` max width), and `JetBrains Mono` `tabular-nums` technical readouts. Crisp inline SVGs only (zero emojis), zero >1px side-stripe card borders, zero gradient text.

### Design Principles
1. **Sync Above Ornament:** Every visual highlight, card state, and progress meter reinforces exact paragraph-to-voice synchronization.
2. **Split-Spring 120fps Motion:** Spatial morphs use compiled Expressive `linear()` springs (`fast-spatial`, `default-spatial`); colors/opacity use critically damped Effects springs (`fast-effects`, `default-effects`); keyboard actions (`Space`, arrows, `R`) respond in 0ms.
3. **Offline & Accessibility Integrity:** Inline M3 tokens + full CSS layout skeleton guarantee clean offline rendering, `48x48dp` touch targets (`40px` pointer-fine), `3px` `:focus-visible` secondary outlines, WCAG AA contrast, and `prefers-reduced-motion` fallbacks.
```

Write `deepexamcast/__init__.py`:
```python
"""DeepExamCast backend package."""
```

- [ ] **Step 2: Install runtime and dev dependencies and verify core imports**

Run:
```powershell
pip install -r requirements.txt -r requirements-dev.txt
python -c "import edge_tts, fitz, fastapi, uvicorn, pytest, httpx; print('ok')"
```
Expected: `ok` with exit code `0`.

- [ ] **Step 3: Write the failing test `tests/test_models.py`**

```python
from deepexamcast.models import (
    DEFAULT_VOICE_PAIR_ID,
    VOICE_PAIRS,
    StudyState,
    compute_audio_hash,
    match_voice_pair_id,
)


def test_voice_pairs_and_matching():
    assert len(VOICE_PAIRS) == 3
    assert VOICE_PAIRS[0].id == DEFAULT_VOICE_PAIR_ID == "us_natural"
    assert match_voice_pair_id("en-IN-PrabhatNeural", "en-IN-NeerjaExpressiveNeural") == "in_english"
    assert match_voice_pair_id("en-GB-RyanNeural", "en-GB-SoniaNeural") == "uk_natural"
    assert match_voice_pair_id("en-US-AndrewMultilingualNeural", "en-IN-NeerjaExpressiveNeural") == "custom"


def test_compute_audio_hash_deterministic_and_sensitive():
    h1 = compute_audio_hash("en-US-AndrewMultilingualNeural", "Hello world")
    h2 = compute_audio_hash("en-US-AndrewMultilingualNeural", "Hello world")
    h3 = compute_audio_hash("en-US-AvaMultilingualNeural", "Hello world")
    h4 = compute_audio_hash("en-US-AndrewMultilingualNeural", "Hello world!")
    assert h1 == h2
    assert len(h1) == 32
    assert all(c in "0123456789abcdef" for c in h1)
    assert h1 != h3
    assert h1 != h4


def test_default_study_state():
    state = StudyState()
    assert state.voice_pair_id == "us_natural"
    assert state.host_a_voice == "en-US-AndrewMultilingualNeural"
    assert state.host_b_voice == "en-US-AvaMultilingualNeural"
    assert state.playback_rate == 1.0
    assert state.auto_scroll is True
    assert state.last_line_index == 0
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deepexamcast.models'`.

- [ ] **Step 5: Implement `deepexamcast/models.py`**

```python
"""Pydantic domain schemas and built-in voice pair registry for DeepExamCast."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field


class VoicePair(BaseModel):
    id: str
    label: str
    host_a_voice: str
    host_b_voice: str


VOICE_PAIRS: list[VoicePair] = [
    VoicePair(
        id="us_natural",
        label="US Natural",
        host_a_voice="en-US-AndrewMultilingualNeural",
        host_b_voice="en-US-AvaMultilingualNeural",
    ),
    VoicePair(
        id="in_english",
        label="Indian English",
        host_a_voice="en-IN-PrabhatNeural",
        host_b_voice="en-IN-NeerjaExpressiveNeural",
    ),
    VoicePair(
        id="uk_natural",
        label="UK Natural",
        host_a_voice="en-GB-RyanNeural",
        host_b_voice="en-GB-SoniaNeural",
    ),
]

DEFAULT_VOICE_PAIR_ID = VOICE_PAIRS[0].id


def match_voice_pair_id(host_a_voice: str, host_b_voice: str) -> str:
    """Return matching built-in voice pair ID, or 'custom' if mixed/custom."""
    for pair in VOICE_PAIRS:
        if pair.host_a_voice == host_a_voice and pair.host_b_voice == host_b_voice:
            return pair.id
    return "custom"


def compute_audio_hash(voice: str, text: str) -> str:
    """Return 32-char lowercase hex SHA-256 content hash for (voice, text)."""
    digest = hashlib.sha256(f"{voice}\0{text}".encode("utf-8")).hexdigest()
    return digest[:32]


class PageInfo(BaseModel):
    page: int
    width: float
    height: float
    chunk_count: int


class Chunk(BaseModel):
    id: str
    page: int
    bbox: list[float]
    text: str


class ScriptLine(BaseModel):
    index: int
    speaker: Literal["HOST_A", "HOST_B"]
    text: str
    chunk_ids: list[str] = Field(default_factory=list)
    exam_note: str | None = None
    voice: str
    audio_hash: str
    audio_file: str
    duration_sec: float = 0.0


class BatchRecord(BaseModel):
    batch_id: str
    timestamp: str
    mode: Literal["replace", "append", "resynthesize"]
    start_index: int
    line_count: int
    page_range: list[int] | None = None
    raw_script_file: str | None = None
    prev_script_file: str | None = None


class StudyState(BaseModel):
    last_line_index: int = 0
    playback_rate: float = 1.0
    voice_pair_id: str = DEFAULT_VOICE_PAIR_ID
    host_a_voice: str = VOICE_PAIRS[0].host_a_voice
    host_b_voice: str = VOICE_PAIRS[0].host_b_voice
    auto_scroll: bool = True


class PageCoverage(BaseModel):
    page: int
    covered_chunks: int
    total_chunks: int
    missed_chunk_ids: list[str] = Field(default_factory=list)
    status: Literal["empty", "uncovered", "partial", "full"]


class SuggestedRange(BaseModel):
    start_page: int
    end_page: int
    chunk_count: int
    char_count: int


class CoverageInfo(BaseModel):
    total_chunks: int
    covered_chunk_count: int
    covered_chunk_ids: list[str]
    pages_coverage: list[PageCoverage]
    fully_covered_pages: list[int]
    partial_pages: list[PageCoverage]
    suggested_next_range: SuggestedRange
    estimated_total_sec: float


class SessionData(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    page_count: int
    pages: list[PageInfo]
    chunks: list[Chunk]
    script: list[ScriptLine] = Field(default_factory=list)
    batches: list[BatchRecord] = Field(default_factory=list)
    state: StudyState = Field(default_factory=StudyState)


class SessionSummary(BaseModel):
    session_id: str
    title: str
    page_count: int
    chunk_count: int
    covered_chunk_count: int
    fully_covered_page_count: int
    line_count: int
    estimated_total_sec: float
    last_line_index: int
    created_at: str
    updated_at: str


class GenerateRequest(BaseModel):
    raw_json: str
    host_a_voice: str
    host_b_voice: str
    mode: Literal["replace", "append"] = "replace"
    start_page: int | None = None
    end_page: int | None = None


class ResynthesizeRequest(BaseModel):
    host_a_voice: str
    host_b_voice: str


class StatePatchRequest(BaseModel):
    last_line_index: int | None = None
    playback_rate: float | None = None
    voice_pair_id: str | None = None
    host_a_voice: str | None = None
    host_b_voice: str | None = None
    auto_scroll: bool | None = None


class GenerateProgress(BaseModel):
    running: bool = False
    phase: Literal["idle", "synthesizing", "committing"] = "idle"
    completed: int = 0
    cached: int = 0
    total: int = 0
    failed: int = 0
```

- [ ] **Step 6: Run test to verify it passes and commit**

Run:
```powershell
pytest tests/test_models.py -v
git add requirements.txt requirements-dev.txt .impeccable.md deepexamcast/__init__.py deepexamcast/models.py tests/test_models.py
git commit -m "feat: add dependencies, design context, and core Pydantic models"
```
Expected: `3 passed` in pytest, clean git commit.

---

### Task 2: Horizontal-Band Column-Aware PDF Parser

**Files:**
- Create: `deepexamcast/pdf_parser.py`
- Test: `tests/test_pdf_parser.py`

**Interfaces:**
- Consumes: `deepexamcast.models.PageInfo`, `deepexamcast.models.Chunk`
- Produces (`deepexamcast/pdf_parser.py`): `PdfParseError(ValueError)`, `parse_pdf_bytes(data: bytes) -> tuple[list[PageInfo], list[Chunk]]`

- [ ] **Step 1: Write failing tests in `tests/test_pdf_parser.py`**

```python
import fitz
import pytest

from deepexamcast.pdf_parser import PdfParseError, parse_pdf_bytes


def _make_pdf_bytes(builder) -> bytes:
    doc = fitz.open()
    builder(doc)
    data = doc.tobytes()
    doc.close()
    return data


def test_parse_single_column_order_hyphenation_and_bboxes():
    def build(doc):
        p1 = doc.new_page(width=600, height=800)
        p1.insert_textbox(fitz.Rect(60, 120, 540, 220), "Dead-\nlock occurs when processes wait forever.")
        p1.insert_textbox(fitz.Rect(60, 260, 540, 340), "Circular wait is the fourth Coffman condition.")
        p2 = doc.new_page(width=600, height=800)
        p2.insert_textbox(fitz.Rect(60, 100, 540, 180), "Banker algorithm checks safe states.")

    data = _make_pdf_bytes(build)
    pages, chunks = parse_pdf_bytes(data)

    assert len(pages) == 2
    assert pages[0].page == 1 and pages[0].width == 600.0 and pages[0].height == 800.0
    assert pages[0].chunk_count == 2
    assert pages[1].chunk_count == 1
    assert [c.id for c in chunks] == ["C1", "C2", "C3"]
    assert chunks[0].page == 1
    assert chunks[2].page == 2
    assert "Deadlock occurs when processes wait forever." in chunks[0].text
    for c in chunks:
        assert len(c.bbox) == 4
        assert 0.0 <= c.bbox[0] <= c.bbox[2] <= 1.0
        assert 0.0 <= c.bbox[1] <= c.bbox[3] <= 1.0


def test_two_column_with_midpage_full_width_heading_order():
    def build(doc):
        page = doc.new_page(width=600, height=800)
        page.insert_textbox(fitz.Rect(50, 40, 550, 80), "1. Chapter Top Overview Across Full Width")
        page.insert_textbox(fitz.Rect(40, 110, 270, 200), "Left upper paragraph one.")
        page.insert_textbox(fitz.Rect(330, 110, 560, 200), "Right upper paragraph two.")
        page.insert_textbox(fitz.Rect(40, 220, 270, 310), "Left upper paragraph three.")
        page.insert_textbox(fitz.Rect(330, 220, 560, 310), "Right upper paragraph four.")
        page.insert_textbox(fitz.Rect(50, 350, 550, 395), "2. Mid-Page Full Width Section Heading")
        page.insert_textbox(fitz.Rect(40, 430, 270, 520), "Left lower paragraph five.")
        page.insert_textbox(fitz.Rect(330, 430, 560, 520), "Right lower paragraph six.")

    pages, chunks = parse_pdf_bytes(_make_pdf_bytes(build))
    assert pages[0].chunk_count == 8
    texts = [c.text for c in chunks]
    assert texts[0].startswith("1. Chapter Top")
    assert texts[1].startswith("Left upper paragraph one")
    assert texts[2].startswith("Left upper paragraph three")
    assert texts[3].startswith("Right upper paragraph two")
    assert texts[4].startswith("Right upper paragraph four")
    assert texts[5].startswith("2. Mid-Page Full Width")
    assert texts[6].startswith("Left lower paragraph five")
    assert texts[7].startswith("Right lower paragraph six")


def test_rotated_and_cropbox_normalization():
    def build(doc):
        p = doc.new_page(width=600, height=800)
        p.set_cropbox(fitz.Rect(50, 50, 550, 750))
        p.insert_textbox(fitz.Rect(100, 120, 450, 200), "Cropped page paragraph text.")
        p.set_rotation(90)

    pages, chunks = parse_pdf_bytes(_make_pdf_bytes(build))
    assert len(pages) == 1
    assert len(chunks) == 1
    x0, y0, x1, y1 = chunks[0].bbox
    assert 0.0 <= x0 < x1 <= 1.0
    assert 0.0 <= y0 < y1 <= 1.0


def test_suppresses_repeating_headers_footers_and_page_numbers():
    def build(doc):
        for idx in range(1, 5):
            p = doc.new_page(width=600, height=800)
            p.insert_textbox(fitz.Rect(60, 15, 540, 38), "CS301 Operating Systems Notes")
            p.insert_textbox(fitz.Rect(60, 140, 540, 220), f"Unique lecture concept on page {idx}.")
            p.insert_textbox(fitz.Rect(250, 765, 350, 790), f"Page {idx} of 4")

    pages, chunks = parse_pdf_bytes(_make_pdf_bytes(build))
    assert len(pages) == 4
    assert len(chunks) == 4
    for idx, chunk in enumerate(chunks, start=1):
        assert chunk.text == f"Unique lecture concept on page {idx}."


def test_micro_chunk_merging_and_image_only_filtering():
    def build(doc):
        p = doc.new_page(width=600, height=800)
        p.insert_textbox(fitz.Rect(60, 120, 82, 145), "•")
        p.insert_textbox(fitz.Rect(88, 120, 520, 165), "Mutex locks prevent simultaneous critical section entry.")
        p.draw_rect(fitz.Rect(100, 300, 400, 450), color=(0, 0, 0))
        doc.new_page(width=600, height=800)  # Blank page with 0 text blocks

    pages, chunks = parse_pdf_bytes(_make_pdf_bytes(build))
    assert len(pages) == 2
    assert pages[0].chunk_count == 1
    assert pages[1].chunk_count == 0
    assert len(chunks) == 1
    assert "Mutex locks prevent" in chunks[0].text
    assert chunks[0].bbox[0] <= 0.12


def test_corrupt_or_empty_pdf_raises():
    with pytest.raises(PdfParseError):
        parse_pdf_bytes(b"not a pdf at all")
    with pytest.raises(PdfParseError):
        parse_pdf_bytes(b"")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pdf_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deepexamcast.pdf_parser'`.

- [ ] **Step 3: Implement `deepexamcast/pdf_parser.py`**

```python
"""Column-aware PyMuPDF text block extraction and bbox normalization."""

from __future__ import annotations

from dataclasses import dataclass
import re

import fitz

from deepexamcast.models import Chunk, PageInfo

_HYPHEN_WRAP_RE = re.compile(r"(\w)-\s*\n\s*(\w)")
_PAGE_NUMBER_RE = re.compile(r"^(?:page\s*)?\d+(?:\s*(?:/|of)\s*\d+)?$", re.IGNORECASE)


class PdfParseError(ValueError):
    """Raised when uploaded bytes cannot be parsed as a valid PDF."""


@dataclass
class _RawBlock:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    band_key: int = 0
    stream_tag: str = "single"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _normalize_text(raw_text: str) -> str:
    dehyphenated = _HYPHEN_WRAP_RE.sub(r"\1\2", raw_text)
    return " ".join(dehyphenated.split())


def _is_full_width(block: _RawBlock) -> bool:
    width = block.x1 - block.x0
    return width > 0.55 or (block.x0 < 0.48 and block.x1 > 0.52)


def _is_left_col(block: _RawBlock) -> bool:
    cx = (block.x0 + block.x1) / 2.0
    return cx < 0.50 and block.x1 <= 0.54


def _is_right_col(block: _RawBlock) -> bool:
    cx = (block.x0 + block.x1) / 2.0
    return cx >= 0.50 and block.x0 >= 0.46


def _order_page_blocks(blocks: list[_RawBlock]) -> list[_RawBlock]:
    if not blocks:
        return []

    full_blocks = sorted(
        (b for b in blocks if _is_full_width(b)),
        key=lambda b: (round(b.y0, 4), round(b.x0, 4)),
    )
    narrow_blocks = [b for b in blocks if not _is_full_width(b)]

    all_left = [b for b in narrow_blocks if _is_left_col(b)]
    all_right = [b for b in narrow_blocks if _is_right_col(b)]
    page_is_two_col = len(all_left) >= 2 and len(all_right) >= 2

    bands: list[list[_RawBlock]] = [[] for _ in range(len(full_blocks) + 1)]
    sep_mids = [(s.y0 + s.y1) / 2.0 for s in full_blocks]

    for block in narrow_blocks:
        mid = (block.y0 + block.y1) / 2.0
        band_idx = 0
        for s_mid in sep_mids:
            if mid >= s_mid:
                band_idx += 1
            else:
                break
        bands[band_idx].append(block)

    ordered: list[_RawBlock] = []
    for idx, band in enumerate(bands):
        if band:
            b_idx = idx * 2
            left = [b for b in band if _is_left_col(b)]
            right = [b for b in band if _is_right_col(b)]
            unclassified = [b for b in band if not _is_left_col(b) and not _is_right_col(b)]

            can_split_columns = (
                page_is_two_col
                and not unclassified
                and left
                and right
                and max(b.x1 for b in left) <= min(b.x0 for b in right)
            )
            if can_split_columns:
                for b in sorted(left, key=lambda item: (round(item.y0, 4), round(item.x0, 4))):
                    b.band_key = b_idx
                    b.stream_tag = "left"
                    ordered.append(b)
                for b in sorted(right, key=lambda item: (round(item.y0, 4), round(item.x0, 4))):
                    b.band_key = b_idx
                    b.stream_tag = "right"
                    ordered.append(b)
            else:
                for b in sorted(band, key=lambda item: (round(item.y0, 3), round(item.x0, 3))):
                    b.band_key = b_idx
                    b.stream_tag = "single"
                    ordered.append(b)

        if idx < len(full_blocks):
            sep = full_blocks[idx]
            sep.band_key = idx * 2 + 1
            sep.stream_tag = "full"
            ordered.append(sep)

    return ordered


def _can_merge_micro(prev: _RawBlock, curr: _RawBlock) -> bool:
    if prev.band_key != curr.band_key or prev.stream_tag != curr.stream_tag:
        return False
    if len(prev.text) >= 40 and len(curr.text) >= 40:
        return False

    prev_h = max(prev.y1 - prev.y0, 1e-5)
    curr_h = max(curr.y1 - curr.y0, 1e-5)
    y_overlap = min(prev.y1, curr.y1) - max(prev.y0, curr.y0)
    overlap_ratio = y_overlap / min(prev_h, curr_h)
    horiz_gap = curr.x0 - prev.x1

    # Same-line prefix (e.g. bullet glyph + paragraph)
    if overlap_ratio > 0.5 and -0.01 <= horiz_gap < 0.04:
        return True

    # Vertically stacked tiny fragment in aligned column
    vert_gap = curr.y0 - prev.y1
    if -0.005 <= vert_gap < 0.015 and abs(prev.x0 - curr.x0) < 0.15:
        return True

    return False


def _merge_micro_chunks(blocks: list[_RawBlock]) -> list[_RawBlock]:
    if not blocks:
        return []
    merged: list[_RawBlock] = [blocks[0]]
    for curr in blocks[1:]:
        prev = merged[-1]
        if _can_merge_micro(prev, curr):
            merged[-1] = _RawBlock(
                page=prev.page,
                x0=min(prev.x0, curr.x0),
                y0=min(prev.y0, curr.y0),
                x1=max(prev.x1, curr.x1),
                y1=max(prev.y1, curr.y1),
                text=f"{prev.text} {curr.text}".strip(),
                band_key=prev.band_key,
                stream_tag=prev.stream_tag,
            )
        else:
            merged.append(curr)
    return merged


def parse_pdf_bytes(data: bytes) -> tuple[list[PageInfo], list[Chunk]]:
    """Extract normalized, reading-ordered text chunks from PDF bytes."""
    if not data or not data.lstrip().startswith(b"%PDF-"):
        raise PdfParseError("Invalid PDF file: missing %PDF- header.")

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfParseError(f"Could not open PDF document: {exc}") from exc

    try:
        if doc.page_count == 0:
            raise PdfParseError("PDF document has zero pages.")

        raw_pages_meta: list[tuple[int, float, float]] = []
        raw_page_blocks: list[list[_RawBlock]] = []

        for page_idx in range(doc.page_count):
            page = doc[page_idx]
            rect = page.rect
            width = float(rect.width) if rect.width > 0 else 1.0
            height = float(rect.height) if rect.height > 0 else 1.0
            raw_pages_meta.append((page_idx + 1, float(rect.width), float(rect.height)))

            blocks_for_page: list[_RawBlock] = []
            for blk in page.get_text("blocks", sort=False):
                bx0, by0, bx1, by1, raw_text, _block_no, block_type = blk[:7]
                if block_type != 0:
                    continue
                cleaned = _normalize_text(str(raw_text))
                if not cleaned:
                    continue

                nx0 = round(_clamp((float(bx0) - float(rect.x0)) / width), 5)
                ny0 = round(_clamp((float(by0) - float(rect.y0)) / height), 5)
                nx1 = round(_clamp((float(bx1) - float(rect.x0)) / width), 5)
                ny1 = round(_clamp((float(by1) - float(rect.y0)) / height), 5)
                if nx1 <= nx0 or ny1 <= ny0:
                    continue

                blocks_for_page.append(
                    _RawBlock(
                        page=page_idx + 1,
                        x0=nx0,
                        y0=ny0,
                        x1=nx1,
                        y1=ny1,
                        text=cleaned,
                    )
                )
            raw_page_blocks.append(blocks_for_page)

        # Suppress repeating top/bottom margin headers, footers, and page numbers on >=3 page docs
        repeating_margin_texts: set[str] = set()
        if doc.page_count >= 3:
            margin_pages: dict[str, set[int]] = {}
            for page_blocks in raw_page_blocks:
                for b in page_blocks:
                    if b.y1 < 0.07 or b.y0 > 0.93:
                        margin_pages.setdefault(b.text.lower(), set()).add(b.page)
            repeating_margin_texts = {
                text for text, seen_pages in margin_pages.items() if len(seen_pages) >= 3
            }

        pages: list[PageInfo] = []
        chunks: list[Chunk] = []
        chunk_counter = 1

        for (page_num, width, height), page_blocks in zip(raw_pages_meta, raw_page_blocks):
            filtered: list[_RawBlock] = []
            for b in page_blocks:
                in_margin = b.y1 < 0.07 or b.y0 > 0.93
                if doc.page_count >= 3 and in_margin:
                    if _PAGE_NUMBER_RE.match(b.text) or b.text.lower() in repeating_margin_texts:
                        continue
                filtered.append(b)

            ordered = _order_page_blocks(filtered)
            merged = _merge_micro_chunks(ordered)

            for b in merged:
                chunks.append(
                    Chunk(
                        id=f"C{chunk_counter}",
                        page=page_num,
                        bbox=[round(b.x0, 5), round(b.y0, 5), round(b.x1, 5), round(b.y1, 5)],
                        text=b.text,
                    )
                )
                chunk_counter += 1

            pages.append(
                PageInfo(
                    page=page_num,
                    width=width,
                    height=height,
                    chunk_count=len(merged),
                )
            )

        return pages, chunks
    finally:
        doc.close()
```

- [ ] **Step 4: Run test to verify it passes and commit**

Run:
```powershell
pytest tests/test_pdf_parser.py -v
git add deepexamcast/pdf_parser.py tests/test_pdf_parser.py
git commit -m "feat: implement band/column-aware PyMuPDF parser with de-hyphenation"
```
Expected: `6 passed`, clean commit.

---

### Task 3: Deep-Dive Prompt Builder

**Files:**
- Create: `deepexamcast/prompt_builder.py`
- Test: `tests/test_prompt_builder.py`

**Interfaces:**
- Consumes: `deepexamcast.models.Chunk`, `deepexamcast.models.ScriptLine`
- Produces (`deepexamcast/prompt_builder.py`): `PromptBuildError(ValueError)`, `PromptResult`, `build_prompt(chunks: list[Chunk], page_count: int, start_page: int, end_page: int, recent_lines: list[ScriptLine] | None = None) -> PromptResult`

- [ ] **Step 1: Write failing tests in `tests/test_prompt_builder.py`**

```python
import pytest

from deepexamcast.models import Chunk, ScriptLine
from deepexamcast.prompt_builder import PromptBuildError, build_prompt


def _sample_chunks() -> list[Chunk]:
    return [
        Chunk(id="C1", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="Page one intro"),
        Chunk(id="C2", page=2, bbox=[0.1, 0.1, 0.9, 0.2], text="Formula: E = m c^2"),
        Chunk(id="C3", page=3, bbox=[0.1, 0.1, 0.9, 0.2], text="Semaphore prevents race conditions."),
        Chunk(id="C4", page=6, bbox=[0.1, 0.1, 0.9, 0.2], text="Page six scheduling"),
    ]


def test_build_prompt_filters_pages_and_formats_chunks():
    result = build_prompt(_sample_chunks(), page_count=6, start_page=2, end_page=3)
    assert result.start_page == 2
    assert result.end_page == 3
    assert result.chunk_count == 2
    assert result.chunk_id_range == ["C2", "C3"]
    assert result.char_count == len("Formula: E = m c^2") + len("Semaphore prevents race conditions.")
    assert "[C2] (Page 2): Formula: E = m c^2" in result.prompt
    assert "[C3] (Page 3): Semaphore prevents race conditions." in result.prompt
    assert "[C1]" not in result.prompt
    assert "[C4]" not in result.prompt
    assert "ZERO SKIMMING" in result.prompt
    assert "HOST_A" in result.prompt
    assert "HOST_B" in result.prompt
    assert "PREVIOUSLY ON THIS LECTURE" not in result.prompt


def test_build_prompt_includes_continuity_context_on_append():
    recent = [
        ScriptLine(
            index=0,
            speaker="HOST_A",
            text="Let us wrap up paging basics.",
            chunk_ids=["C1"],
            voice="v",
            audio_hash="a" * 32,
            audio_file=f"{'a' * 32}.mp3",
        ),
        ScriptLine(
            index=1,
            speaker="HOST_B",
            text="Got it! What happens when processes share memory?",
            chunk_ids=["C1"],
            voice="v",
            audio_hash="b" * 32,
            audio_file=f"{'b' * 32}.mp3",
        ),
    ]
    result = build_prompt(_sample_chunks(), page_count=6, start_page=2, end_page=3, recent_lines=recent)
    assert "PREVIOUSLY ON THIS LECTURE" in result.prompt
    assert "HOST_B: Got it! What happens when processes share memory?" in result.prompt


def test_build_prompt_validation_errors():
    with pytest.raises(PromptBuildError, match="Invalid page range"):
        build_prompt(_sample_chunks(), page_count=6, start_page=4, end_page=2)
    with pytest.raises(PromptBuildError, match="Invalid page range"):
        build_prompt(_sample_chunks(), page_count=6, start_page=1, end_page=9)
    with pytest.raises(PromptBuildError, match="No extractable text chunks"):
        build_prompt(_sample_chunks(), page_count=6, start_page=4, end_page=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_prompt_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deepexamcast.prompt_builder'`.

- [ ] **Step 3: Implement `deepexamcast/prompt_builder.py`**

```python
"""Deep-dive Gemini Web prompt builder for page-range chunk batches."""

from __future__ import annotations

from pydantic import BaseModel

from deepexamcast.models import Chunk, ScriptLine


class PromptBuildError(ValueError):
    """Raised when page range is invalid or contains no extractable text chunks."""


class PromptResult(BaseModel):
    prompt: str
    start_page: int
    end_page: int
    chunk_count: int
    chunk_id_range: list[str]
    char_count: int


def build_prompt(
    chunks: list[Chunk],
    page_count: int,
    start_page: int,
    end_page: int,
    recent_lines: list[ScriptLine] | None = None,
) -> PromptResult:
    """Build a ready-to-paste Gemini prompt covering chunks in [start_page, end_page]."""
    if start_page < 1 or end_page < start_page or end_page > page_count:
        raise PromptBuildError(
            f"Invalid page range {start_page}..{end_page} for document with {page_count} page(s)."
        )

    selected = [c for c in chunks if start_page <= c.page <= end_page]
    if not selected:
        raise PromptBuildError(
            f"No extractable text chunks found on pages {start_page}–{end_page}."
        )

    c_start = selected[0].id
    c_end = selected[-1].id
    char_count = sum(len(c.text) for c in selected)
    chunk_lines = "\n".join(f"[{c.id}] (Page {c.page}): {c.text}" for c in selected)

    continuity_block = ""
    if recent_lines and start_page > 1:
        tail = recent_lines[-2:]
        formatted_tail = "\n".join(f"{line.speaker}: {line.text}" for line in tail)
        continuity_block = (
            "\nPREVIOUSLY ON THIS LECTURE (do not re-introduce the podcast or repeat these lines; "
            "continue smoothly from here into the first new chunk):\n"
            f"{formatted_tail}\n"
        )

    prompt = (
        f"You are scripting an in-depth, exam-prep study podcast between an enthusiastic, crystal-clear "
        f"Professor (HOST_A) and a sharp, curious Exam Student (HOST_B).\n"
        f"Study source covers Pages {start_page}–{end_page} ({len(selected)} chunks: {c_start} through {c_end}).\n\n"
        f"CRITICAL RULES — FOLLOW EVERY SINGLE ONE:\n"
        f"1. ZERO SKIMMING: Cover EVERY single chunk ID in exact sequential order from {c_start} to {c_end} without skipping any ID. "
        f"Explain every definition, mechanism, formula, exception/edge case, and likely exam question thoroughly using intuitive analogies and memory hooks.\n"
        f"2. CONVERSATIONAL AUDIO STYLE: Keep each spoken turn natural and engaging (1–3 sentences per turn). "
        f"Use NO markdown symbols (*, #, _, `) inside spoken \"text\". Spell out all math symbols and notation as natural spoken English "
        f"(e.g., \"x squared\", \"equals\", \"greater than or equal to\", \"O of n log n\").\n"
        f"3. EXACT TRACEABILITY: Every turn must reference the chunk ID(s) it explains in \"chunk_ids\". "
        f"Add an optional concise 1-line formula, distinction, or exam trap in \"exam_note\" when helpful (omit or set null otherwise).\n"
        f"4. STRICTLY VALID JSON ONLY: Output ONLY a raw JSON array (no intro prose, no outro prose) matching this exact schema:\n"
        f"[\n"
        f"  {{\n"
        f'    "speaker": "HOST_A",\n'
        f'    "text": "Spoken dialogue here...",\n'
        f'    "chunk_ids": ["{c_start}"],\n'
        f'    "exam_note": "Optional short 1-line formula or key exam fact"\n'
        f"  }}\n"
        f"]\n"
        f"{continuity_block}\n"
        f"SOURCE CHUNKS ({c_start} to {c_end}):\n"
        f"{chunk_lines}"
    )

    return PromptResult(
        prompt=prompt,
        start_page=start_page,
        end_page=end_page,
        chunk_count=len(selected),
        chunk_id_range=[c_start, c_end],
        char_count=char_count,
    )
```

- [ ] **Step 4: Run test to verify it passes and commit**

Run:
```powershell
pytest tests/test_prompt_builder.py -v
git add deepexamcast/prompt_builder.py tests/test_prompt_builder.py
git commit -m "feat: add deep-dive zero-skimming Gemini prompt builder"
```
Expected: `3 passed`, clean commit.

---

### Task 4: Multi-Candidate Typo-Tolerant Gemini Script Parser

**Files:**
- Create: `deepexamcast/script_parser.py`
- Test: `tests/test_script_parser.py`

**Interfaces:**
- Produces (`deepexamcast/script_parser.py`): `ScriptParseError(ValueError)`, `ParsedDialogueItem`, `ParsedScriptResult`, `parse_gemini_script(raw_json: str, valid_chunk_ids: set[str]) -> ParsedScriptResult`

- [ ] **Step 1: Write failing tests in `tests/test_script_parser.py`**

```python
import json
import pytest

from deepexamcast.script_parser import ScriptParseError, parse_gemini_script


def test_parse_plain_and_fenced_and_prose_arrays():
    raw = (
        "Here is your script for pages [1, 5]:\n"
        "```json\n"
        '[{"speaker": "host_a", "text": "**Bold** x^2 [check]!", "chunk_ids": "c1", "exam_note": "  Key fact  "},\n'
        ' {"speaker": "HOST_B", "text": "Got it, thanks!", "chunk_ids": ["C1", "C99", "C1"]}]\n'
        "```\n"
        "Let me know if you want the next batch!"
    )
    res = parse_gemini_script(raw, {"C1", "C2"})
    assert len(res.items) == 2
    assert res.items[0].speaker == "HOST_A"
    assert res.items[0].text == "Bold x^2 [check]!"
    assert res.items[0].chunk_ids == ["C1"]
    assert res.items[0].exam_note == "Key fact"
    assert res.items[1].speaker == "HOST_B"
    assert res.items[1].chunk_ids == ["C1"]
    assert any("C99" in w for w in res.warnings)


def test_parse_wrapper_object_prefers_longest_dialogue_list():
    raw = json.dumps(
        {
            "covered_chunks": ["C1", "C2"],
            "dialogue": [
                {"speaker": "HOST_A", "text": "First explanation", "chunk_ids": ["C1"]},
                {"speaker": "HOST_B", "text": "Second question", "chunk_ids": ["C2"]},
            ],
        }
    )
    res = parse_gemini_script(raw, {"C1", "C2"})
    assert len(res.items) == 2
    assert res.items[0].text == "First explanation"


def test_single_item_typo_surfaces_exact_item_error():
    items = [
        {"speaker": "HOST_A", "text": f"Line {i}", "chunk_ids": ["C1"]}
        for i in range(1, 6)
    ]
    items[3] = {"speker": "HOST_A", "text": "Line 4", "chunk_ids": ["C1"]}
    with pytest.raises(ScriptParseError, match=r"Item 4.*speaker"):
        parse_gemini_script(json.dumps(items), {"C1"})


def test_unicode_multilingual_speakable_accepted_but_symbols_rejected():
    ok = parse_gemini_script(
        '[{"speaker": "HOST_A", "text": "अध्याय एक में स्वागत है — café résumé!", "chunk_ids": ["C1"]}]',
        {"C1"},
    )
    assert len(ok.items) == 1

    with pytest.raises(ScriptParseError, match="speakable"):
        parse_gemini_script(
            '[{"speaker": "HOST_A", "text": "... — ***", "chunk_ids": ["C1"]}]',
            {"C1"},
        )


def test_invalid_or_empty_json_raises_informative_error():
    with pytest.raises(ScriptParseError):
        parse_gemini_script("   ", {"C1"})
    with pytest.raises(ScriptParseError):
        parse_gemini_script("[]", {"C1"})
    with pytest.raises(ScriptParseError, match="line"):
        parse_gemini_script('[{"speaker": "HOST_A", "text": "unclosed"', {"C1"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_script_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deepexamcast.script_parser'`.

- [ ] **Step 3: Implement `deepexamcast/script_parser.py`**

```python
"""Multi-candidate typo-tolerant parser for Gemini Web JSON scripts."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_HEADING_MD_RE = re.compile(r"(?:^|\s)#+\s*")
_MD_CHARS_RE = re.compile(r"[*`]+")


class ScriptParseError(ValueError):
    """Raised when pasted Gemini output cannot be parsed into valid dialogue lines."""


class ParsedDialogueItem(BaseModel):
    speaker: Literal["HOST_A", "HOST_B"]
    text: str
    chunk_ids: list[str] = Field(default_factory=list)
    exam_note: str | None = None


class ParsedScriptResult(BaseModel):
    items: list[ParsedDialogueItem]
    warnings: list[str] = Field(default_factory=list)


def _strip_markdown(text: str) -> str:
    collapsed = " ".join(text.split())
    no_ticks = _MD_CHARS_RE.sub("", collapsed)
    no_headings = _HEADING_MD_RE.sub(" ", no_ticks)
    return " ".join(no_headings.split())


def _is_dialogue_candidate(obj: Any) -> bool:
    if not isinstance(obj, list) or not obj:
        return False
    if not all(isinstance(item, dict) for item in obj):
        return False
    matching = 0
    for item in obj:
        lower_keys = {str(k).strip().lower() for k in item.keys()}
        if "speaker" in lower_keys or "text" in lower_keys:
            matching += 1
    threshold = max(1, (len(obj) + 1) // 2)
    return matching >= threshold


def _extract_candidates(region: str, out_lists: list[list[dict[str, Any]]], errors: list[json.JSONDecodeError]) -> None:
    decoder = json.JSONDecoder()
    idx = 0
    length = len(region)
    while idx < length:
        ch = region[idx]
        if ch in "[{":
            try:
                decoded, end_idx = decoder.raw_decode(region, idx)
            except json.JSONDecodeError as exc:
                errors.append(exc)
                idx += 1
                continue

            if _is_dialogue_candidate(decoded):
                out_lists.append(decoded)
            elif isinstance(decoded, dict):
                for val in decoded.values():
                    if _is_dialogue_candidate(val):
                        out_lists.append(val)
            idx = max(idx + 1, end_idx)
        else:
            idx += 1


def _format_json_error(raw: str, errors: list[json.JSONDecodeError]) -> str:
    if not errors:
        return "No valid JSON dialogue array found. Ensure Gemini output contains a JSON array of {speaker, text, chunk_ids} objects."
    best = max(errors, key=lambda e: e.pos)
    snippet_start = max(0, best.pos - 30)
    snippet_end = min(len(raw), best.pos + 30)
    snippet = raw[snippet_start:snippet_end].replace("\n", " ")
    return f"Invalid JSON syntax near line {best.lineno}, column {best.colno}: {best.msg} (near: '{snippet}')."


def parse_gemini_script(raw_json: str, valid_chunk_ids: set[str]) -> ParsedScriptResult:
    """Extract, validate, and sanitize a Gemini dialogue script JSON payload."""
    cleaned_raw = raw_json.lstrip("\ufeff").strip()
    if not cleaned_raw:
        raise ScriptParseError("Pasted script is empty. Paste Gemini's JSON response first.")

    regions: list[str] = []
    for match in _FENCE_RE.finditer(cleaned_raw):
        block = match.group(1).strip()
        if block:
            regions.append(block)
    regions.append(cleaned_raw)

    candidate_lists: list[list[dict[str, Any]]] = []
    decode_errors: list[json.JSONDecodeError] = []
    for region in regions:
        _extract_candidates(region, candidate_lists, decode_errors)

    if not candidate_lists:
        raise ScriptParseError(_format_json_error(cleaned_raw, decode_errors))

    chosen = max(candidate_lists, key=len)

    parsed_items: list[ParsedDialogueItem] = []
    unknown_ids: list[str] = []
    unknown_seen: set[str] = set()

    for idx, raw_item in enumerate(chosen, start=1):
        norm_map = {str(k).strip().lower(): v for k, v in raw_item.items()}

        raw_speaker = norm_map.get("speaker")
        if not isinstance(raw_speaker, str) or raw_speaker.strip().upper() not in {"HOST_A", "HOST_B"}:
            raise ScriptParseError(
                f"Item {idx} is missing or has invalid 'speaker' (expected 'HOST_A' or 'HOST_B')."
            )
        speaker: Literal["HOST_A", "HOST_B"] = raw_speaker.strip().upper()  # type: ignore[assignment]

        raw_text = norm_map.get("text")
        if not isinstance(raw_text, str):
            raise ScriptParseError(f"Item {idx} is missing required string field 'text'.")
        spoken_text = _strip_markdown(raw_text)
        if not spoken_text or not any(ch.isalnum() for ch in spoken_text):
            raise ScriptParseError(
                f"Item {idx} has no speakable alphanumeric text after cleanup (got {raw_text!r})."
            )

        raw_chunks = norm_map.get("chunk_ids", [])
        if raw_chunks is None:
            chunk_tokens: list[str] = []
        elif isinstance(raw_chunks, str):
            chunk_tokens = [raw_chunks]
        elif isinstance(raw_chunks, list):
            chunk_tokens = [str(c) for c in raw_chunks if c is not None]
        else:
            raise ScriptParseError(f"Item {idx} field 'chunk_ids' must be a list of chunk IDs.")

        clean_chunks: list[str] = []
        seen_chunks: set[str] = set()
        for tok in chunk_tokens:
            cid = tok.strip().upper()
            if not cid:
                continue
            if cid not in valid_chunk_ids:
                if cid not in unknown_seen:
                    unknown_seen.add(cid)
                    unknown_ids.append(cid)
                continue
            if cid not in seen_chunks:
                seen_chunks.add(cid)
                clean_chunks.append(cid)

        raw_note = norm_map.get("exam_note")
        exam_note: str | None = None
        if isinstance(raw_note, str):
            trimmed_note = " ".join(raw_note.split())
            if trimmed_note:
                exam_note = trimmed_note

        parsed_items.append(
            ParsedDialogueItem(
                speaker=speaker,
                text=spoken_text,
                chunk_ids=clean_chunks,
                exam_note=exam_note,
            )
        )

    warnings: list[str] = []
    if unknown_ids:
        warnings.append(f"Ignored unknown chunk ID(s) not present in this PDF: {', '.join(unknown_ids)}.")

    return ParsedScriptResult(items=parsed_items, warnings=warnings)
```

- [ ] **Step 4: Run test to verify it passes and commit**

Run:
```powershell
pytest tests/test_script_parser.py -v
git add deepexamcast/script_parser.py tests/test_script_parser.py
git commit -m "feat: add typo-tolerant multi-candidate Gemini script parser"
```
Expected: `5 passed`, clean commit.

---

### Task 5: Hardened Content-Addressed `edge-tts` Engine & Pure-Python MP3 Duration

**Files:**
- Create: `deepexamcast/tts_engine.py`
- Test: `tests/test_tts_engine.py`

**Interfaces:**
- Consumes: `deepexamcast.models.ScriptLine`, `edge_tts.Communicate`
- Produces (`deepexamcast/tts_engine.py`): `TtsSynthesisError(RuntimeError)`, `SynthesisResult`, `get_tts_concurrency() -> int`, `estimate_mp3_duration_sec(path: Path) -> float`, `synthesize_lines(audio_dir: Path, lines: list[ScriptLine], concurrency: int | None = None, timeout_sec: float = 30.0, max_attempts: int = 3, progress_cb: Callable[[bool], None] | None = None, base_backoff_sec: float = 1.5) -> SynthesisResult`, `gc_unreferenced_audio(audio_dir: Path, keep_filenames: set[str]) -> int`

- [ ] **Step 1: Write failing tests in `tests/test_tts_engine.py`**

```python
import asyncio
from pathlib import Path
import pytest

from deepexamcast.models import ScriptLine, compute_audio_hash
from deepexamcast.tts_engine import (
    TtsSynthesisError,
    estimate_mp3_duration_sec,
    gc_unreferenced_audio,
    synthesize_lines,
)


def _line(idx: int, text: str, voice: str = "en-US-AndrewMultilingualNeural") -> ScriptLine:
    h = compute_audio_hash(voice, text)
    return ScriptLine(
        index=idx,
        speaker="HOST_A",
        text=text,
        chunk_ids=["C1"],
        voice=voice,
        audio_hash=h,
        audio_file=f"{h}.mp3",
    )


def _fake_mp3_bytes(payload_len: int = 6000) -> bytes:
    # Valid MPEG1 Layer III 48kbps frame header: 0xFF 0xFB 0x30 0x00 (bitrate index 3 => 48 kbps)
    header = bytes([0xFF, 0xFB, 0x30, 0x00])
    return header + (b"\xAA" * (payload_len - len(header)))


@pytest.mark.asyncio
async def test_synthesize_respects_concurrency_and_caches_and_dedups(tmp_path: Path, monkeypatch):
    active = 0
    max_active = 0
    calls: list[str] = []

    class FakeCommunicate:
        def __init__(self, text: str, voice: str):
            self.text = text
            self.voice = voice

        async def save(self, path: str) -> None:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            calls.append(self.text)
            await asyncio.sleep(0.03)
            Path(path).write_bytes(_fake_mp3_bytes(12000))
            active -= 1

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", FakeCommunicate)

    # Line 0 and Line 4 have identical (voice, text) => in-batch deduplication
    lines = [_line(i, f"Sentence {i % 4}") for i in range(6)]
    progress_events: list[bool] = []

    res = await synthesize_lines(
        tmp_path,
        lines,
        concurrency=2,
        progress_cb=lambda cached: progress_events.append(cached),
        base_backoff_sec=0.01,
    )

    assert max_active <= 2
    assert res.total_lines == 6
    assert res.generated_count == 4
    assert res.cached_count == 2
    assert len(progress_events) == 6
    assert all(line.duration_sec > 1.5 for line in res.lines)

    # Second run hits content-addressed cache 100% even with lines reordered
    reordered = [res.lines[2].model_copy(update={"index": 0}), res.lines[0].model_copy(update={"index": 1})]
    calls.clear()
    res2 = await synthesize_lines(tmp_path, reordered, concurrency=2)
    assert calls == []
    assert res2.generated_count == 0
    assert res2.cached_count == 2


@pytest.mark.asyncio
async def test_retry_recovery_and_timeout_and_partial_isolation(tmp_path: Path, monkeypatch):
    attempts: dict[str, int] = {}

    class FlakyCommunicate:
        def __init__(self, text: str, voice: str):
            self.text = text

        async def save(self, path: str) -> None:
            attempts[self.text] = attempts.get(self.text, 0) + 1
            if self.text == "flaky" and attempts[self.text] < 3:
                raise RuntimeError("transient 503")
            if self.text == "hang":
                await asyncio.sleep(0.5)
            Path(path).write_bytes(_fake_mp3_bytes(6000))

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", FlakyCommunicate)

    # Successful recovery on flaky line
    res = await synthesize_lines(
        tmp_path,
        [_line(0, "flaky")],
        max_attempts=3,
        timeout_sec=0.2,
        base_backoff_sec=0.01,
    )
    assert res.generated_count == 1
    assert attempts["flaky"] == 3

    # Timeout failure leaves completed clip cached while raising TtsSynthesisError
    attempts.clear()
    with pytest.raises(TtsSynthesisError) as exc_info:
        await synthesize_lines(
            tmp_path,
            [_line(0, "good"), _line(1, "hang")],
            max_attempts=2,
            timeout_sec=0.05,
            base_backoff_sec=0.01,
        )
    assert exc_info.value.failed_line_index == 1
    good_file = tmp_path / _line(0, "good").audio_file
    assert good_file.exists() and good_file.stat().st_size > 0


def test_estimate_mp3_duration_with_id3_header_and_gc_handles_permission_error(tmp_path: Path, monkeypatch):
    id3_header = b"ID3\x03\x00\x00\x00\x00\x00\x10" + (b"\x00" * 16)
    mp3_path = tmp_path / ("a" * 32 + ".mp3")
    mp3_path.write_bytes(id3_header + _fake_mp3_bytes(12000))
    # 12000 bytes * 8 / 48000 bps = 2.0 sec
    assert estimate_mp3_duration_sec(mp3_path) == 2.0

    keep_file = "a" * 32 + ".mp3"
    locked_file = tmp_path / ("b" * 32 + ".mp3")
    orphan_file = tmp_path / ("c" * 32 + ".mp3")
    locked_file.write_bytes(b"locked")
    orphan_file.write_bytes(b"orphan")

    real_unlink = Path.unlink

    def flaky_unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name == locked_file.name:
            raise PermissionError("simulated Windows lock")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    removed = gc_unreferenced_audio(tmp_path, {keep_file})
    assert removed == 1
    assert mp3_path.exists()
    assert locked_file.exists()
    assert not orphan_file.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tts_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deepexamcast.tts_engine'`.

- [ ] **Step 3: Implement `deepexamcast/tts_engine.py`**

```python
"""Hardened content-addressed edge-tts synthesis, pure-Python MP3 duration, and GC."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import random
from typing import Callable
import uuid

import edge_tts
from pydantic import BaseModel

from deepexamcast.models import ScriptLine

_MPEG1_L3_BITRATES = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_MPEG2_L3_BITRATES = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
_FALLBACK_BITRATE_BPS = 48000


class TtsSynthesisError(RuntimeError):
    """Raised when one or more clips fail synthesis after retries."""

    def __init__(
        self,
        message: str,
        *,
        failed_line_index: int,
        generated_count: int,
        cached_count: int,
    ) -> None:
        super().__init__(message)
        self.failed_line_index = failed_line_index
        self.generated_count = generated_count
        self.cached_count = cached_count


class SynthesisResult(BaseModel):
    lines: list[ScriptLine]
    generated_count: int
    cached_count: int
    total_lines: int


def get_tts_concurrency() -> int:
    """Return configured TTS concurrency clamped to [1, 5]."""
    raw = os.getenv("DEEPEXAMCAST_TTS_CONCURRENCY", "4")
    try:
        val = int(raw)
    except ValueError:
        val = 4
    return max(1, min(5, val))


def estimate_mp3_duration_sec(path: Path) -> float:
    """Estimate MP3 clip duration in seconds using MPEG frame headers (zero ffmpeg)."""
    try:
        file_size = path.stat().st_size
    except OSError:
        return 0.0
    if file_size <= 0:
        return 0.0

    try:
        with path.open("rb") as fh:
            head = fh.read(8192)
    except OSError:
        return 0.0

    audio_offset = 0
    if len(head) >= 10 and head[:3] == b"ID3":
        tag_size = (
            ((head[6] & 0x7F) << 21)
            | ((head[7] & 0x7F) << 14)
            | ((head[8] & 0x7F) << 7)
            | (head[9] & 0x7F)
        )
        audio_offset = 10 + tag_size
        if audio_offset >= len(head):
            try:
                with path.open("rb") as fh:
                    fh.seek(audio_offset)
                    scan_buf = fh.read(8192)
            except OSError:
                scan_buf = b""
        else:
            scan_buf = head[audio_offset:]
    else:
        scan_buf = head

    bitrate_bps = _FALLBACK_BITRATE_BPS
    for i in range(max(0, len(scan_buf) - 3)):
        b0 = scan_buf[i]
        b1 = scan_buf[i + 1]
        b2 = scan_buf[i + 2]
        if b0 == 0xFF and (b1 & 0xE0) == 0xE0:
            version_id = (b1 >> 3) & 0x03
            layer = (b1 >> 1) & 0x03
            bitrate_idx = (b2 >> 4) & 0x0F
            if version_id != 1 and layer == 1 and 0 < bitrate_idx < 15:
                kbps = (
                    _MPEG1_L3_BITRATES[bitrate_idx]
                    if version_id == 3
                    else _MPEG2_L3_BITRATES[bitrate_idx]
                )
                if kbps > 0:
                    bitrate_bps = kbps * 1000
                    break

    payload_bytes = max(1, file_size - audio_offset)
    return round(max(0.1, (payload_bytes * 8.0) / bitrate_bps), 2)


async def _synthesize_single_clip(
    sem: asyncio.Semaphore,
    audio_dir: Path,
    line: ScriptLine,
    timeout_sec: float,
    max_attempts: int,
    base_backoff_sec: float,
) -> Path:
    target_path = audio_dir / line.audio_file
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        tmp_path = audio_dir / f".{line.audio_hash}.{uuid.uuid4().hex}.tmp"
        try:
            async with sem:
                if target_path.exists() and target_path.stat().st_size > 0:
                    return target_path
                comm = edge_tts.Communicate(line.text, line.voice)
                await asyncio.wait_for(comm.save(str(tmp_path)), timeout=timeout_sec)

            if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
                raise RuntimeError("edge-tts produced an empty audio file.")
            os.replace(tmp_path, target_path)
            return target_path
        except Exception as exc:
            last_error = exc
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            if attempt + 1 < max_attempts:
                delay = (base_backoff_sec * (2**attempt)) * (0.7 + 0.6 * random.random())
                await asyncio.sleep(delay)

    raise RuntimeError(
        f"TTS synthesis failed on line {line.index} after {max_attempts} attempt(s): {last_error}"
    ) from last_error


async def synthesize_lines(
    audio_dir: Path,
    lines: list[ScriptLine],
    concurrency: int | None = None,
    timeout_sec: float = 30.0,
    max_attempts: int = 3,
    progress_cb: Callable[[bool], None] | None = None,
    base_backoff_sec: float = 1.5,
) -> SynthesisResult:
    """Synthesize content-addressed .mp3 files concurrently with cache hits & dedup."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    effective_concurrency = max(1, min(5, concurrency)) if concurrency is not None else get_tts_concurrency()
    sem = asyncio.Semaphore(effective_concurrency)

    in_flight: dict[str, asyncio.Task[Path]] = {}
    generated_count = 0
    cached_count = 0
    updated_lines: list[ScriptLine | None] = [None] * len(lines)

    async def process_line(pos: int, line: ScriptLine) -> tuple[int, ScriptLine, bool]:
        nonlocal generated_count, cached_count
        target_path = audio_dir / line.audio_file
        if target_path.exists() and target_path.stat().st_size > 0:
            cached_count += 1
            if progress_cb is not None:
                progress_cb(True)
            dur = estimate_mp3_duration_sec(target_path)
            return pos, line.model_copy(update={"duration_sec": dur}), True

        task = in_flight.get(line.audio_hash)
        is_owner = False
        if task is None:
            is_owner = True
            task = asyncio.create_task(
                _synthesize_single_clip(
                    sem,
                    audio_dir,
                    line,
                    timeout_sec=timeout_sec,
                    max_attempts=max_attempts,
                    base_backoff_sec=base_backoff_sec,
                )
            )
            in_flight[line.audio_hash] = task

        resolved_path = await task
        if is_owner:
            generated_count += 1
            if progress_cb is not None:
                progress_cb(False)
        else:
            cached_count += 1
            if progress_cb is not None:
                progress_cb(True)

        dur = estimate_mp3_duration_sec(resolved_path)
        return pos, line.model_copy(update={"duration_sec": dur}), not is_owner

    outcomes = await asyncio.gather(
        *(process_line(pos, line) for pos, line in enumerate(lines)),
        return_exceptions=True,
    )

    first_error: tuple[int, Exception] | None = None
    for pos, outcome in enumerate(outcomes):
        if isinstance(outcome, Exception):
            if first_error is None:
                first_error = (lines[pos].index, outcome)
        else:
            idx_pos, updated_line, _was_cached = outcome
            updated_lines[idx_pos] = updated_line

    if first_error is not None:
        failed_idx, exc = first_error
        raise TtsSynthesisError(
            str(exc),
            failed_line_index=failed_idx,
            generated_count=generated_count,
            cached_count=cached_count,
        ) from exc

    final_lines = [line for line in updated_lines if line is not None]
    return SynthesisResult(
        lines=final_lines,
        generated_count=generated_count,
        cached_count=cached_count,
        total_lines=len(final_lines),
    )


def gc_unreferenced_audio(audio_dir: Path, keep_filenames: set[str]) -> int:
    """Best-effort cleanup of unreferenced .mp3 files (tolerates Windows PermissionError)."""
    if not audio_dir.exists():
        return 0
    removed = 0
    for entry in audio_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".mp3":
            continue
        if entry.name in keep_filenames:
            continue
        try:
            entry.unlink()
            removed += 1
        except (PermissionError, OSError):
            continue
    return removed
```

- [ ] **Step 4: Run test to verify it passes and commit**

Run:
```powershell
pytest tests/test_tts_engine.py -v
git add deepexamcast/tts_engine.py tests/test_tts_engine.py
git commit -m "feat: add content-addressed edge-tts engine with timeout, jittered retry, and MP3 duration"
```
Expected: `3 passed`, clean commit.

---

### Task 6: Atomic Session Store, Per-Session Locks, Multi-Step Undo & Chunk Coverage

**Files:**
- Create: `deepexamcast/session_store.py`
- Test: `tests/test_session_store.py`

**Interfaces:**
- Consumes: `deepexamcast.models.*`
- Produces (`deepexamcast/session_store.py`): `SESSION_ID_RE`, `AUDIO_FILE_RE`, `SessionNotFoundError(KeyError)`, `InvalidSessionIdError(ValueError)`, `SessionConflictError(RuntimeError)`, `make_session_id(filename: str) -> str`, `compute_coverage(session: SessionData) -> CoverageInfo`, `compute_missed_chunks(session: SessionData, batch_lines: list[ScriptLine], start_page: int | None, end_page: int | None) -> tuple[list[int] | None, list[str]]`, `SessionStore`

- [ ] **Step 1: Write failing tests in `tests/test_session_store.py`**

```python
import asyncio
from pathlib import Path
import pytest

from deepexamcast.models import (
    BatchRecord,
    Chunk,
    PageInfo,
    ScriptLine,
    compute_audio_hash,
)
from deepexamcast.session_store import (
    InvalidSessionIdError,
    SessionStore,
    compute_coverage,
    compute_missed_chunks,
    make_session_id,
)


def test_make_session_id_slugifies_and_falls_back_on_non_ascii():
    sid_en = make_session_id("Ch 04: Deadlocks & Starvation!.pdf")
    assert sid_en.startswith("ch-04-deadlocks-starvation-")
    sid_hi = make_session_id("अध्याय1.pdf")
    assert sid_hi.startswith("doc-")
    sid_dash = make_session_id("---.pdf")
    assert sid_dash.startswith("doc-")
    long_sid = make_session_id(("a" * 120) + ".pdf")
    assert len(long_sid) <= 80


def test_path_traversal_rejected_and_atomic_roundtrip(tmp_path: Path):
    store = SessionStore(tmp_path)
    with pytest.raises(InvalidSessionIdError):
        store.load_session("../etc")
    with pytest.raises(InvalidSessionIdError):
        store.get_audio_path("valid-123456", "../evil.mp3")
    with pytest.raises(InvalidSessionIdError):
        store.get_audio_path("valid-123456", "line_000.mp3")

    pages = [PageInfo(page=1, width=600, height=800, chunk_count=1)]
    chunks = [Chunk(id="C1", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="Intro")]
    session = store.create_session("notes.pdf", b"%PDF-1.4\n%%EOF", pages, chunks)
    loaded = store.load_session(session.session_id)
    assert loaded.title == "notes.pdf"
    assert store.get_pdf_path(session.session_id).read_bytes() == b"%PDF-1.4\n%%EOF"


def test_chunk_level_coverage_budgeted_range_and_missed_chunks(tmp_path: Path):
    store = SessionStore(tmp_path)
    pages = [
        PageInfo(page=1, width=600, height=800, chunk_count=2),
        PageInfo(page=2, width=600, height=800, chunk_count=2),
        PageInfo(page=3, width=600, height=800, chunk_count=30),  # Exceeds 28-chunk budget
    ]
    chunks = [
        Chunk(id="C1", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="A" * 100),
        Chunk(id="C2", page=1, bbox=[0.1, 0.3, 0.9, 0.4], text="B" * 100),
        Chunk(id="C3", page=2, bbox=[0.1, 0.1, 0.9, 0.2], text="C" * 100),
        Chunk(id="C4", page=2, bbox=[0.1, 0.3, 0.9, 0.4], text="D" * 100),
    ] + [
        Chunk(id=f"C{i}", page=3, bbox=[0.1, 0.1, 0.9, 0.2], text="E" * 50)
        for i in range(5, 35)
    ]

    session = store.create_session("chapter.pdf", b"%PDF-1.4", pages, chunks)
    # Initial suggested range stops before page 3 because adding 30 chunks exceeds 28-chunk budget
    cov0 = compute_coverage(session)
    assert cov0.suggested_next_range.start_page == 1
    assert cov0.suggested_next_range.end_page == 2
    assert cov0.suggested_next_range.chunk_count == 4

    # Cover C1 and C3 only -> Page 1 and Page 2 are both partial (NOT full)
    h1 = compute_audio_hash("v", "line1")
    line1 = ScriptLine(
        index=0, speaker="HOST_A", text="line1", chunk_ids=["C1", "C3"],
        voice="v", audio_hash=h1, audio_file=f"{h1}.mp3", duration_sec=2.5,
    )
    session.script = [line1]
    cov1 = compute_coverage(session)
    assert cov1.fully_covered_pages == []
    assert [p.page for p in cov1.partial_pages] == [1, 2]
    assert cov1.pages_coverage[0].missed_chunk_ids == ["C2"]
    assert cov1.suggested_next_range.start_page == 1

    # Explicit and inferred missed chunks
    span_exp, missed_exp = compute_missed_chunks(session, [line1], 1, 2)
    assert span_exp == [1, 2] and missed_exp == ["C2", "C4"]
    span_inf, missed_inf = compute_missed_chunks(session, [line1], None, None)
    assert span_inf == [1, 2] and missed_inf == ["C2", "C4"]


def test_multistep_undo_snapshots_retained_and_pruned_at_3(tmp_path: Path):
    store = SessionStore(tmp_path)
    pages = [PageInfo(page=1, width=600, height=800, chunk_count=1)]
    chunks = [Chunk(id="C1", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="Text")]
    session = store.create_session("undo.pdf", b"%PDF-1.4", pages, chunks)

    for step in range(4):
        bid = f"b_{step}"
        h = compute_audio_hash("v", f"t{step}")
        prev = [ScriptLine(index=0, speaker="HOST_A", text=f"old{step}", chunk_ids=["C1"], voice="v", audio_hash=h, audio_file=f"{h}.mp3")]
        rel = store.save_prev_snapshot(session.session_id, bid, prev)
        session.batches.append(
            BatchRecord(batch_id=bid, timestamp="2026-11-20T00:00:00Z", mode="replace", start_index=0, line_count=1, prev_script_file=rel)
        )

    store.prune_prev_snapshots(session, keep_last=3)
    assert session.batches[0].prev_script_file is None
    assert session.batches[1].prev_script_file is not None
    assert session.batches[2].prev_script_file is not None
    assert session.batches[3].prev_script_file is not None

    retained = store.collect_retained_audio_filenames(session)
    assert len(retained) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deepexamcast.session_store'`.

- [ ] **Step 3: Implement `deepexamcast/session_store.py`**

```python
"""Disk session persistence, per-session asyncio locks, undo snapshots, and chunk coverage."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from deepexamcast.models import (
    BatchRecord,
    Chunk,
    CoverageInfo,
    GenerateProgress,
    PageCoverage,
    PageInfo,
    ScriptLine,
    SessionData,
    SessionSummary,
    StudyState,
    SuggestedRange,
)

SESSION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,80}$")
AUDIO_FILE_RE = re.compile(r"^[0-9a-f]{32}\.mp3$")
_NON_SLUG_RE = re.compile(r"[^a-z0-9_-]+")
_MULTI_DASH_RE = re.compile(r"-{2,}")

MAX_BATCH_CHUNKS = 28
MAX_BATCH_CHARS = 12000
MAX_BATCH_PAGES = 5


class SessionNotFoundError(KeyError):
    """Raised when a requested session directory or session.json does not exist."""


class InvalidSessionIdError(ValueError):
    """Raised when session_id or filename fails strict allowlist validation."""


class SessionConflictError(RuntimeError):
    """Raised when a mutation collides with an in-progress generation on the same session."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_session_id(filename: str) -> str:
    """Generate a path-safe ASCII session ID ending in -<6hex> with 'doc' fallback."""
    stem = Path(filename or "doc").stem.lower()
    slug = _NON_SLUG_RE.sub("-", stem)
    slug = _MULTI_DASH_RE.sub("-", slug).strip("-_")
    if not slug:
        slug = "doc"
    slug = slug[:70].rstrip("-_") or "doc"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def compute_coverage(session: SessionData) -> CoverageInfo:
    """Compute chunk-level coverage and budgeted next-batch range from session.script."""
    valid_ids = {c.id for c in session.chunks}
    covered_set = {
        cid
        for line in session.script
        for cid in line.chunk_ids
        if cid in valid_ids
    }
    covered_chunk_ids = [c.id for c in session.chunks if c.id in covered_set]

    chunks_by_page: dict[int, list[Chunk]] = {p: [] for p in range(1, session.page_count + 1)}
    for chunk in session.chunks:
        chunks_by_page.setdefault(chunk.page, []).append(chunk)

    pages_coverage: list[PageCoverage] = []
    fully_covered_pages: list[int] = []
    partial_pages: list[PageCoverage] = []

    for page_num in range(1, session.page_count + 1):
        p_chunks = chunks_by_page.get(page_num, [])
        total = len(p_chunks)
        missed = [c.id for c in p_chunks if c.id not in covered_set]
        covered = total - len(missed)
        if total == 0:
            status = "empty"
        elif covered == 0:
            status = "uncovered"
        elif covered < total:
            status = "partial"
        else:
            status = "full"

        pc = PageCoverage(
            page=page_num,
            covered_chunks=covered,
            total_chunks=total,
            missed_chunk_ids=missed,
            status=status,
        )
        pages_coverage.append(pc)
        if status == "full":
            fully_covered_pages.append(page_num)
        elif status == "partial":
            partial_pages.append(pc)

    start_page = 1
    for pc in pages_coverage:
        if pc.status in ("uncovered", "partial"):
            start_page = pc.page
            break

    max_page = max(1, session.page_count)
    end_limit = min(start_page + MAX_BATCH_PAGES - 1, max_page)
    first_chunks = chunks_by_page.get(start_page, [])
    cum_chunks = len(first_chunks)
    cum_chars = sum(len(c.text) for c in first_chunks)
    end_page = start_page

    for q in range(start_page + 1, end_limit + 1):
        q_chunks = chunks_by_page.get(q, [])
        q_count = len(q_chunks)
        q_chars = sum(len(c.text) for c in q_chunks)
        if cum_chunks + q_count <= MAX_BATCH_CHUNKS and cum_chars + q_chars <= MAX_BATCH_CHARS:
            end_page = q
            cum_chunks += q_count
            cum_chars += q_chars
        else:
            break

    estimated_total_sec = round(sum(line.duration_sec for line in session.script), 2)

    return CoverageInfo(
        total_chunks=len(session.chunks),
        covered_chunk_count=len(covered_chunk_ids),
        covered_chunk_ids=covered_chunk_ids,
        pages_coverage=pages_coverage,
        fully_covered_pages=fully_covered_pages,
        partial_pages=partial_pages,
        suggested_next_range=SuggestedRange(
            start_page=start_page,
            end_page=end_page,
            chunk_count=cum_chunks,
            char_count=cum_chars,
        ),
        estimated_total_sec=estimated_total_sec,
    )


def compute_missed_chunks(
    session: SessionData,
    batch_lines: list[ScriptLine],
    start_page: int | None,
    end_page: int | None,
) -> tuple[list[int] | None, list[str]]:
    """Return (page_range, missed_chunk_ids) comparing batch lines against page span."""
    chunk_by_id = {c.id: c for c in session.chunks}
    batch_covered = {
        cid
        for line in batch_lines
        for cid in line.chunk_ids
        if cid in chunk_by_id
    }

    if start_page is not None and end_page is not None:
        sp = max(1, start_page)
        ep = min(session.page_count, end_page)
        if sp > ep:
            return None, []
    else:
        ref_pages = [chunk_by_id[cid].page for cid in batch_covered]
        if not ref_pages:
            return None, []
        sp, ep = min(ref_pages), max(ref_pages)

    missed = [
        c.id
        for c in session.chunks
        if sp <= c.page <= ep and c.id not in batch_covered
    ]
    return [sp, ep], missed


class SessionStore:
    """Thread/async-safe manager for ./sessions/<session_id>/ artifacts."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path("sessions")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self.active_generations: set[str] = set()
        self.progress_map: dict[str, GenerateProgress] = {}

    def validate_session_id(self, session_id: str) -> str:
        if not SESSION_ID_RE.match(session_id or ""):
            raise InvalidSessionIdError(f"Invalid session_id: {session_id!r}")
        return session_id

    def get_lock(self, session_id: str) -> asyncio.Lock:
        self.validate_session_id(session_id)
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    def is_generating(self, session_id: str) -> bool:
        return session_id in self.active_generations

    def try_begin_generation(self, session_id: str, total_lines: int) -> None:
        self.validate_session_id(session_id)
        if session_id in self.active_generations:
            raise SessionConflictError("Audio generation is already running for this session.")
        self.active_generations.add(session_id)
        self.progress_map[session_id] = GenerateProgress(
            running=True,
            phase="synthesizing",
            completed=0,
            cached=0,
            total=total_lines,
            failed=0,
        )

    def record_progress(self, session_id: str, *, cached: bool = False) -> None:
        prog = self.progress_map.get(session_id)
        if prog is None:
            return
        prog.completed += 1
        if cached:
            prog.cached += 1

    def set_progress_phase(self, session_id: str, phase: str) -> None:
        prog = self.progress_map.get(session_id)
        if prog is not None:
            prog.phase = phase  # type: ignore[assignment]

    def end_generation(self, session_id: str) -> None:
        self.active_generations.discard(session_id)
        self.progress_map[session_id] = GenerateProgress()

    def get_progress(self, session_id: str) -> GenerateProgress:
        self.validate_session_id(session_id)
        return self.progress_map.get(session_id, GenerateProgress())

    def session_dir(self, session_id: str) -> Path:
        self.validate_session_id(session_id)
        return self.base_dir / session_id

    def audio_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "audio"

    def raw_scripts_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "raw_scripts"

    def get_pdf_path(self, session_id: str) -> Path:
        path = self.session_dir(session_id) / "source.pdf"
        if not path.is_file():
            raise SessionNotFoundError(f"Session PDF not found for {session_id!r}")
        return path

    def get_audio_path(self, session_id: str, filename: str) -> Path:
        self.validate_session_id(session_id)
        if not AUDIO_FILE_RE.match(filename or ""):
            raise InvalidSessionIdError(f"Invalid audio filename: {filename!r}")
        path = self.audio_dir(session_id) / filename
        if not path.is_file():
            raise SessionNotFoundError(f"Audio clip {filename!r} not found.")
        return path

    def new_batch_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"b_{stamp}_{uuid.uuid4().hex[:6]}"

    def create_session(
        self,
        title: str,
        pdf_bytes: bytes,
        pages: list[PageInfo],
        chunks: list[Chunk],
    ) -> SessionData:
        session_id = make_session_id(title)
        sdir = self.session_dir(session_id)
        now = utc_now_iso()
        session = SessionData(
            session_id=session_id,
            title=title or f"{session_id}.pdf",
            created_at=now,
            updated_at=now,
            page_count=len(pages),
            pages=pages,
            chunks=chunks,
            script=[],
            batches=[],
            state=StudyState(),
        )
        try:
            sdir.mkdir(parents=True, exist_ok=True)
            self.audio_dir(session_id).mkdir(parents=True, exist_ok=True)
            self.raw_scripts_dir(session_id).mkdir(parents=True, exist_ok=True)
            (sdir / "source.pdf").write_bytes(pdf_bytes)
            self.save_session(session)
            return session
        except Exception:
            shutil.rmtree(sdir, ignore_errors=True)
            raise

    def save_session(self, session: SessionData) -> None:
        json_path = self.session_dir(session.session_id) / "session.json"
        _atomic_write_text(json_path, session.model_dump_json(indent=2))

    def load_session(self, session_id: str) -> SessionData:
        json_path = self.session_dir(session_id) / "session.json"
        if not json_path.is_file():
            raise SessionNotFoundError(f"Session {session_id!r} not found.")
        return SessionData.model_validate_json(json_path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[SessionSummary]:
        summaries: list[SessionSummary] = []
        if not self.base_dir.exists():
            return summaries
        for entry in self.base_dir.iterdir():
            if not entry.is_dir() or not SESSION_ID_RE.match(entry.name):
                continue
            json_path = entry / "session.json"
            if not json_path.is_file():
                continue
            try:
                session = SessionData.model_validate_json(json_path.read_text(encoding="utf-8"))
                cov = compute_coverage(session)
                summaries.append(
                    SessionSummary(
                        session_id=session.session_id,
                        title=session.title,
                        page_count=session.page_count,
                        chunk_count=len(session.chunks),
                        covered_chunk_count=cov.covered_chunk_count,
                        fully_covered_page_count=len(cov.fully_covered_pages),
                        line_count=len(session.script),
                        estimated_total_sec=cov.estimated_total_sec,
                        last_line_index=session.state.last_line_index,
                        created_at=session.created_at,
                        updated_at=session.updated_at,
                    )
                )
            except Exception:
                continue
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries

    def delete_session(self, session_id: str) -> None:
        sdir = self.session_dir(session_id)
        if not sdir.exists():
            raise SessionNotFoundError(f"Session {session_id!r} not found.")
        shutil.rmtree(sdir)
        self._locks.pop(session_id, None)
        self.progress_map.pop(session_id, None)

    def save_raw_batch(self, session_id: str, batch_id: str, raw_json: str) -> str:
        rel = f"raw_scripts/{batch_id}.json"
        _atomic_write_text(self.session_dir(session_id) / rel, raw_json)
        return rel

    def save_prev_snapshot(self, session_id: str, batch_id: str, script: list[ScriptLine]) -> str:
        rel = f"raw_scripts/{batch_id}.prev.json"
        payload = json.dumps([line.model_dump() for line in script], indent=2)
        _atomic_write_text(self.session_dir(session_id) / rel, payload)
        return rel

    def load_prev_snapshot(self, session_id: str, rel_path: str) -> list[ScriptLine]:
        target = self.session_dir(session_id) / rel_path
        if not target.is_file():
            return []
        data = json.loads(target.read_text(encoding="utf-8"))
        return [ScriptLine.model_validate(item) for item in data]

    def prune_prev_snapshots(self, session: SessionData, keep_last: int = 3) -> None:
        """Retain only the last `keep_last` replace/resynthesize undo snapshots."""
        snapshot_indices = [
            idx for idx, b in enumerate(session.batches) if b.prev_script_file
        ]
        if len(snapshot_indices) <= keep_last:
            return
        stale_indices = snapshot_indices[:-keep_last]
        sdir = self.session_dir(session.session_id)
        for idx in stale_indices:
            rel = session.batches[idx].prev_script_file
            if rel:
                stale_path = sdir / rel
                if stale_path.exists():
                    try:
                        stale_path.unlink()
                    except OSError:
                        pass
                session.batches[idx].prev_script_file = None

    def collect_retained_audio_filenames(self, session: SessionData) -> set[str]:
        """Collect audio filenames referenced by active script and all retained undo snapshots."""
        keep = {line.audio_file for line in session.script}
        for batch in session.batches:
            if batch.prev_script_file:
                for line in self.load_prev_snapshot(session.session_id, batch.prev_script_file):
                    keep.add(line.audio_file)
        return keep
```

- [ ] **Step 4: Run test to verify it passes and commit**

Run:
```powershell
pytest tests/test_session_store.py -v
git add deepexamcast/session_store.py tests/test_session_store.py
git commit -m "feat: add atomic SessionStore with chunk coverage, locking, and multi-step undo"
```
Expected: `4 passed`, clean commit.

---

### Task 7: Thin FastAPI Entrypoint & Full End-to-End Integration Suite

**Files:**
- Create: `app.py`
- Test: `tests/test_api_integration.py`

**Interfaces:**
- Consumes: `deepexamcast.models.*`, `deepexamcast.pdf_parser`, `deepexamcast.prompt_builder`, `deepexamcast.script_parser`, `deepexamcast.tts_engine`, `deepexamcast.session_store`
- Produces (`app.py`): `MAX_UPLOAD_BYTES = 100 * 1024 * 1024`, `VENDOR_FILE_RE`, `create_app(sessions_dir: Path | None = None, static_dir: Path | None = None) -> FastAPI`, `app = create_app()`

- [ ] **Step 1: Write failing integration tests in `tests/test_api_integration.py`**

```python
import asyncio
import json
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
import fitz
import pytest

import app as app_module


def _build_test_pdf(pages_texts: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages_texts:
        p = doc.new_page(width=600, height=800)
        p.insert_textbox(fitz.Rect(60, 100, 540, 220), text)
    data = doc.tobytes()
    doc.close()
    return data


def _fake_mp3(size: int = 4800) -> bytes:
    return bytes([0xFF, 0xFB, 0x30, 0x00]) + (b"\x55" * (size - 4))


@pytest.fixture
def client_and_dirs(tmp_path: Path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    static_dir = tmp_path / "static"
    vendor_dir = static_dir / "vendor"
    vendor_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>DeepExamCast</body></html>", encoding="utf-8")
    (vendor_dir / "pdf.min.mjs").write_text("export const ok = true;", encoding="utf-8")

    class FakeCommunicate:
        def __init__(self, text: str, voice: str):
            self.text = text
            self.voice = voice

        async def save(self, path: str) -> None:
            await asyncio.sleep(0.01)
            Path(path).write_bytes(_fake_mp3(4800))

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", FakeCommunicate)
    application = app_module.create_app(sessions_dir=sessions_dir, static_dir=static_dir)
    return TestClient(application), sessions_dir, static_dir


def test_full_study_lifecycle_undo_resynthesize_delete(client_and_dirs):
    client, _sdir, _static = client_and_dirs

    assert client.get("/").status_code == 200
    assert len(client.get("/api/voices").json()["voice_pairs"]) == 3

    # Explicit JS MIME type on /static/vendor/*.mjs
    vendor_resp = client.get("/static/vendor/pdf.min.mjs")
    assert vendor_resp.status_code == 200
    assert "text/javascript" in vendor_resp.headers["content-type"]
    assert client.get("/static/vendor/../../app.py").status_code in (400, 404)

    # Upload PDF with non-ASCII filename -> 'doc-<6hex>' fallback
    pdf_bytes = _build_test_pdf(["Page one deadlock.", "Page two semaphore."])
    up = client.post(
        "/api/upload",
        files={"file": ("अध्याय1.pdf", pdf_bytes, "application/pdf")},
    )
    assert up.status_code == 200
    data = up.json()
    sid = data["session"]["session_id"]
    assert sid.startswith("doc-")
    assert "raw_scripts" not in data["session"]
    assert client.get(f"/api/sessions/{sid}/pdf").headers["content-type"].startswith("application/pdf")

    # Empty script resynthesize -> 400
    empty_resyn = client.post(
        f"/api/sessions/{sid}/resynthesize",
        json={"host_a_voice": "en-IN-PrabhatNeural", "host_b_voice": "en-IN-NeerjaExpressiveNeural"},
    )
    assert empty_resyn.status_code == 400

    # Prompt
    pr = client.get(f"/api/sessions/{sid}/prompt?start_page=1&end_page=2")
    assert pr.status_code == 200
    assert pr.json()["chunk_id_range"] == ["C1", "C2"]

    # Generate replace covering only C1 -> missed C2 warning
    gen1 = client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([{"speaker": "HOST_A", "text": "Deadlock basics.", "chunk_ids": ["C1"]}]),
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
            "mode": "replace",
            "start_page": 1,
            "end_page": 2,
        },
    )
    assert gen1.status_code == 200
    g1 = gen1.json()
    assert g1["missed_chunk_ids"] == ["C2"]
    assert any("C2" in w for w in g1["warnings"])
    audio1 = g1["session"]["script"][0]["audio_file"]
    assert client.get(f"/api/sessions/{sid}/audio/{audio1}").status_code == 200
    assert client.get(f"/api/sessions/{sid}/audio/bad.mp3").status_code == 400

    # Append C2
    gen2 = client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([{"speaker": "HOST_B", "text": "Semaphore basics.", "chunk_ids": ["C2"]}]),
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
            "mode": "append",
            "start_page": 2,
            "end_page": 2,
        },
    )
    assert gen2.status_code == 200
    assert len(gen2.json()["session"]["script"]) == 2
    assert gen2.json()["coverage"]["fully_covered_pages"] == [1, 2]

    # Resynthesize into Indian English
    resyn = client.post(
        f"/api/sessions/{sid}/resynthesize",
        json={"host_a_voice": "en-IN-PrabhatNeural", "host_b_voice": "en-IN-NeerjaExpressiveNeural"},
    )
    assert resyn.status_code == 200
    assert resyn.json()["session"]["state"]["voice_pair_id"] == "in_english"

    # Multi-step undo: undo resynthesize -> undo append -> audio1 still exists!
    u1 = client.post(f"/api/sessions/{sid}/undo")
    assert u1.status_code == 200
    assert len(u1.json()["session"]["script"]) == 2
    assert u1.json()["session"]["script"][0]["audio_file"] == audio1
    assert client.get(f"/api/sessions/{sid}/audio/{audio1}").status_code == 200

    u2 = client.post(f"/api/sessions/{sid}/undo")
    assert u2.status_code == 200
    assert len(u2.json()["session"]["script"]) == 1
    assert client.get(f"/api/sessions/{sid}/audio/{audio1}").status_code == 200

    # Delete session
    assert client.delete(f"/api/sessions/{sid}").status_code == 200
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_upload_validation_and_size_limit(client_and_dirs, monkeypatch):
    client, _sdir, _static = client_and_dirs
    assert client.post("/api/upload", files={"file": ("x.pdf", b"not-a-pdf", "application/pdf")}).status_code == 400

    monkeypatch.setattr(app_module, "MAX_UPLOAD_BYTES", 200)
    big_pdf = b"%PDF-1.4\n" + (b"0" * 300)
    assert client.post("/api/upload", files={"file": ("big.pdf", big_pdf, "application/pdf")}).status_code == 413


def test_concurrent_patch_preserved_and_409_and_status_reset_on_502(client_and_dirs, monkeypatch):
    client, _sdir, _static = client_and_dirs
    up = client.post(
        "/api/upload",
        files={"file": ("race.pdf", _build_test_pdf(["Chunk one."]), "application/pdf")},
    )
    sid = up.json()["session"]["session_id"]

    entered = threading.Event()
    release = threading.Event()

    class SlowCommunicate:
        def __init__(self, text: str, voice: str):
            self.text = text

        async def save(self, path: str) -> None:
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            Path(path).write_bytes(_fake_mp3())

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", SlowCommunicate)

    results: list[int] = []

    def run_generate() -> None:
        resp = client.post(
            f"/api/sessions/{sid}/generate",
            json={
                "raw_json": json.dumps([{"speaker": "HOST_A", "text": "Slow line.", "chunk_ids": ["C1"]}]),
                "host_a_voice": "en-US-AndrewMultilingualNeural",
                "host_b_voice": "en-US-AvaMultilingualNeural",
                "mode": "replace",
            },
        )
        results.append(resp.status_code)

    t = threading.Thread(target=run_generate)
    t.start()
    assert entered.wait(timeout=3.0)

    # While generating: status is running, second generate gets 409, PATCH /state succeeds and persists
    assert client.get(f"/api/sessions/{sid}/generate/status").json()["running"] is True
    conflict = client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([{"speaker": "HOST_A", "text": "Dup.", "chunk_ids": ["C1"]}]),
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
            "mode": "replace",
        },
    )
    assert conflict.status_code == 409

    patch_resp = client.patch(f"/api/sessions/{sid}/state", json={"playback_rate": 1.5, "auto_scroll": False})
    assert patch_resp.status_code == 200

    release.set()
    t.join(timeout=5.0)
    assert results == [200]

    loaded = client.get(f"/api/sessions/{sid}").json()
    assert loaded["session"]["state"]["playback_rate"] == 1.5
    assert loaded["session"]["state"]["auto_scroll"] is False
    assert client.get(f"/api/sessions/{sid}/generate/status").json()["running"] is False

    # 502 error resets /generate/status back to idle
    class FailCommunicate:
        def __init__(self, text: str, voice: str):
            pass

        async def save(self, path: str) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", FailCommunicate)
    monkeypatch.setattr("deepexamcast.tts_engine.asyncio.sleep", lambda _s: asyncio.sleep(0))
    fail_resp = client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([{"speaker": "HOST_A", "text": "Will fail now.", "chunk_ids": ["C1"]}]),
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
            "mode": "replace",
        },
    )
    assert fail_resp.status_code == 502
    assert client.get(f"/api/sessions/{sid}/generate/status").json()["running"] is False
    assert client.get(f"/api/sessions/{sid}").json()["session"]["script"][0]["text"] == "Slow line."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_integration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 3: Implement `app.py`**

```python
"""FastAPI application entrypoint for DeepExamCast (`uvicorn app:app`)."""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from deepexamcast.models import (
    VOICE_PAIRS,
    BatchRecord,
    GenerateRequest,
    ResynthesizeRequest,
    ScriptLine,
    SessionData,
    StatePatchRequest,
    compute_audio_hash,
    match_voice_pair_id,
)
from deepexamcast.pdf_parser import PdfParseError, parse_pdf_bytes
from deepexamcast.prompt_builder import PromptBuildError, build_prompt
from deepexamcast.script_parser import ScriptParseError, parse_gemini_script
from deepexamcast.session_store import (
    InvalidSessionIdError,
    SessionConflictError,
    SessionNotFoundError,
    SessionStore,
    compute_coverage,
    compute_missed_chunks,
    utc_now_iso,
)
from deepexamcast.tts_engine import TtsSynthesisError, gc_unreferenced_audio, synthesize_lines

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
VENDOR_FILE_RE = re.compile(r"^[a-z0-9._-]+\.(?:mjs|js|css)$", re.IGNORECASE)


def _map_store_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidSessionIdError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, SessionNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SessionConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _session_payload(session: SessionData, warnings: list[str] | None = None) -> dict[str, Any]:
    cov = compute_coverage(session)
    payload: dict[str, Any] = {
        "session": session.model_dump(),
        "coverage": cov.model_dump(),
        "voice_pairs": [vp.model_dump() for vp in VOICE_PAIRS],
    }
    if warnings is not None:
        payload["warnings"] = warnings
    return payload


def create_app(sessions_dir: Path | None = None, static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="DeepExamCast", version="1.0.0")
    store = SessionStore(base_dir=sessions_dir or Path("sessions"))
    resolved_static = static_dir or Path("static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        index_path = resolved_static / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=404, detail="Frontend index.html not found.")
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @app.get("/static/vendor/{filename}")
    async def serve_vendor(filename: str) -> FileResponse:
        if not VENDOR_FILE_RE.match(filename or ""):
            raise HTTPException(status_code=400, detail="Invalid vendor asset filename.")
        target = resolved_static / "vendor" / filename
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Vendor asset not present.")
        ext = target.suffix.lower()
        media_type = "text/css; charset=utf-8" if ext == ".css" else "text/javascript; charset=utf-8"
        return FileResponse(path=target, media_type=media_type)

    @app.get("/api/voices")
    async def get_voices() -> dict[str, Any]:
        return {"voice_pairs": [vp.model_dump() for vp in VOICE_PAIRS]}

    @app.post("/api/upload")
    async def upload_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
        chunks_buf = bytearray()
        total_bytes = 0
        first_chunk = True
        try:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="PDF upload exceeds the 100 MB maximum size.")
                if first_chunk:
                    first_chunk = False
                    if not chunk.lstrip().startswith(b"%PDF-"):
                        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF (%PDF- header missing).")
                chunks_buf.extend(chunk)
        finally:
            await file.close()

        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="Uploaded PDF file is empty.")

        pdf_bytes = bytes(chunks_buf)
        try:
            pages, chunks = await asyncio.to_thread(parse_pdf_bytes, pdf_bytes)
        except PdfParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        title = Path(file.filename or "lecture.pdf").name
        session = await asyncio.to_thread(store.create_session, title, pdf_bytes, pages, chunks)
        warnings: list[str] = []
        if not chunks:
            warnings.append(
                "No selectable text blocks were extracted from this PDF (it may be scanned or image-only)."
            )
        return _session_payload(session, warnings=warnings)

    @app.get("/api/sessions")
    async def list_sessions() -> dict[str, Any]:
        items = await asyncio.to_thread(store.list_sessions)
        return {"sessions": [item.model_dump() for item in items]}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        try:
            session = await asyncio.to_thread(store.load_session, session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc
        return _session_payload(session)

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict[str, str]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            if store.is_generating(session_id):
                raise HTTPException(status_code=409, detail="Cannot delete session while audio generation is running.")
            try:
                await asyncio.to_thread(store.delete_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc
        return {"deleted": session_id}

    @app.get("/api/sessions/{session_id}/pdf")
    async def get_session_pdf(session_id: str) -> FileResponse:
        try:
            pdf_path = await asyncio.to_thread(store.get_pdf_path, session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc
        return FileResponse(path=pdf_path, media_type="application/pdf")

    @app.get("/api/sessions/{session_id}/prompt")
    async def get_prompt(
        session_id: str,
        start_page: int = Query(1, ge=1),
        end_page: int = Query(5, ge=1),
    ) -> dict[str, Any]:
        try:
            session = await asyncio.to_thread(store.load_session, session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        try:
            result = build_prompt(
                session.chunks,
                session.page_count,
                start_page,
                end_page,
                recent_lines=session.script or None,
            )
        except PromptBuildError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.model_dump()

    @app.get("/api/sessions/{session_id}/generate/status")
    async def get_generate_status(session_id: str) -> dict[str, Any]:
        try:
            prog = store.get_progress(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc
        return prog.model_dump()

    @app.post("/api/sessions/{session_id}/generate")
    async def generate_audio(session_id: str, req: GenerateRequest) -> dict[str, Any]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            if store.is_generating(session_id):
                raise HTTPException(status_code=409, detail="Audio generation is already running for this session.")
            try:
                snapshot = await asyncio.to_thread(store.load_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc

            valid_ids = {c.id for c in snapshot.chunks}
            try:
                parsed = parse_gemini_script(req.raw_json, valid_ids)
            except ScriptParseError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            base_index = 0 if req.mode == "replace" else len(snapshot.script)
            target_lines: list[ScriptLine] = []
            for offset, item in enumerate(parsed.items):
                voice = req.host_a_voice if item.speaker == "HOST_A" else req.host_b_voice
                ahash = compute_audio_hash(voice, item.text)
                target_lines.append(
                    ScriptLine(
                        index=base_index + offset,
                        speaker=item.speaker,
                        text=item.text,
                        chunk_ids=item.chunk_ids,
                        exam_note=item.exam_note,
                        voice=voice,
                        audio_hash=ahash,
                        audio_file=f"{ahash}.mp3",
                    )
                )

            try:
                store.try_begin_generation(session_id, len(target_lines))
            except Exception as exc:
                raise _map_store_error(exc) from exc

        try:
            try:
                synth = await synthesize_lines(
                    store.audio_dir(session_id),
                    target_lines,
                    progress_cb=lambda cached: store.record_progress(session_id, cached=cached),
                )
            except TtsSynthesisError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"{exc}. {exc.generated_count} new clip(s) and {exc.cached_count} cached clip(s) "
                        "are saved on disk; retry Generate to resume cleanly."
                    ),
                ) from exc

            store.set_progress_phase(session_id, "committing")
            batch_id = store.new_batch_id()
            raw_rel = await asyncio.to_thread(store.save_raw_batch, session_id, batch_id, req.raw_json)

            async with lock:
                fresh = await asyncio.to_thread(store.load_session, session_id)
                prev_rel: str | None = None
                if req.mode == "replace" and fresh.script:
                    prev_rel = await asyncio.to_thread(store.save_prev_snapshot, session_id, batch_id, fresh.script)

                if req.mode == "replace":
                    fresh.script = synth.lines
                    fresh.state.last_line_index = 0
                    actual_start = 0
                else:
                    actual_start = len(fresh.script)
                    reindexed = [
                        line.model_copy(update={"index": actual_start + idx})
                        for idx, line in enumerate(synth.lines)
                    ]
                    fresh.script = fresh.script + reindexed

                page_range, missed_ids = compute_missed_chunks(fresh, synth.lines, req.start_page, req.end_page)
                fresh.batches.append(
                    BatchRecord(
                        batch_id=batch_id,
                        timestamp=utc_now_iso(),
                        mode=req.mode,
                        start_index=actual_start,
                        line_count=len(synth.lines),
                        page_range=page_range,
                        raw_script_file=raw_rel,
                        prev_script_file=prev_rel,
                    )
                )
                await asyncio.to_thread(store.prune_prev_snapshots, fresh, 3)

                fresh.state.host_a_voice = req.host_a_voice
                fresh.state.host_b_voice = req.host_b_voice
                fresh.state.voice_pair_id = match_voice_pair_id(req.host_a_voice, req.host_b_voice)
                max_idx = max(0, len(fresh.script) - 1)
                fresh.state.last_line_index = max(0, min(fresh.state.last_line_index, max_idx))
                fresh.updated_at = utc_now_iso()

                await asyncio.to_thread(store.save_session, fresh)
                keep_files = await asyncio.to_thread(store.collect_retained_audio_filenames, fresh)
                await asyncio.to_thread(gc_unreferenced_audio, store.audio_dir(session_id), keep_files)

            warnings = list(parsed.warnings)
            if missed_ids and page_range:
                warnings.append(
                    f"Gemini skipped {len(missed_ids)} chunk(s) in Pages {page_range[0]}–{page_range[1]}: {', '.join(missed_ids)}."
                )

            cov = compute_coverage(fresh)
            return {
                "session": fresh.model_dump(),
                "coverage": cov.model_dump(),
                "stats": {
                    "generated_count": synth.generated_count,
                    "cached_count": synth.cached_count,
                    "total_lines": len(fresh.script),
                },
                "missed_chunk_ids": missed_ids,
                "warnings": warnings,
            }
        finally:
            store.end_generation(session_id)

    @app.post("/api/sessions/{session_id}/undo")
    async def undo_last_batch(session_id: str) -> dict[str, Any]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            if store.is_generating(session_id):
                raise HTTPException(status_code=409, detail="Cannot undo while audio generation is running.")
            try:
                session = await asyncio.to_thread(store.load_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc

            if not session.batches:
                raise HTTPException(status_code=400, detail="No script batches available to undo.")

            popped = session.batches.pop()
            if popped.mode == "append":
                session.script = session.script[: popped.start_index]
            else:
                if popped.prev_script_file:
                    session.script = await asyncio.to_thread(
                        store.load_prev_snapshot, session_id, popped.prev_script_file
                    )
                else:
                    session.script = []

            max_idx = max(0, len(session.script) - 1)
            session.state.last_line_index = max(0, min(session.state.last_line_index, max_idx))
            session.updated_at = utc_now_iso()
            await asyncio.to_thread(store.save_session, session)

            keep_files = await asyncio.to_thread(store.collect_retained_audio_filenames, session)
            await asyncio.to_thread(gc_unreferenced_audio, store.audio_dir(session_id), keep_files)

            cov = compute_coverage(session)
            return {
                "session": session.model_dump(),
                "coverage": cov.model_dump(),
                "undone_batch": popped.model_dump(),
            }

    @app.post("/api/sessions/{session_id}/resynthesize")
    async def resynthesize_voices(session_id: str, req: ResynthesizeRequest) -> dict[str, Any]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            if store.is_generating(session_id):
                raise HTTPException(status_code=409, detail="Audio generation is already running for this session.")
            try:
                snapshot = await asyncio.to_thread(store.load_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc

            if not snapshot.script:
                raise HTTPException(status_code=400, detail="Cannot resynthesize voices on an empty script.")

            target_lines: list[ScriptLine] = []
            for idx, line in enumerate(snapshot.script):
                voice = req.host_a_voice if line.speaker == "HOST_A" else req.host_b_voice
                ahash = compute_audio_hash(voice, line.text)
                target_lines.append(
                    line.model_copy(
                        update={
                            "index": idx,
                            "voice": voice,
                            "audio_hash": ahash,
                            "audio_file": f"{ahash}.mp3",
                        }
                    )
                )

            try:
                store.try_begin_generation(session_id, len(target_lines))
            except Exception as exc:
                raise _map_store_error(exc) from exc

        try:
            try:
                synth = await synthesize_lines(
                    store.audio_dir(session_id),
                    target_lines,
                    progress_cb=lambda cached: store.record_progress(session_id, cached=cached),
                )
            except TtsSynthesisError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc}. Completed clips stay cached; retry Re-synthesize to resume.",
                ) from exc

            store.set_progress_phase(session_id, "committing")
            batch_id = store.new_batch_id()

            async with lock:
                fresh = await asyncio.to_thread(store.load_session, session_id)
                prev_rel = await asyncio.to_thread(store.save_prev_snapshot, session_id, batch_id, fresh.script)
                fresh.script = synth.lines
                fresh.batches.append(
                    BatchRecord(
                        batch_id=batch_id,
                        timestamp=utc_now_iso(),
                        mode="resynthesize",
                        start_index=0,
                        line_count=len(synth.lines),
                        page_range=None,
                        raw_script_file=None,
                        prev_script_file=prev_rel,
                    )
                )
                await asyncio.to_thread(store.prune_prev_snapshots, fresh, 3)

                fresh.state.host_a_voice = req.host_a_voice
                fresh.state.host_b_voice = req.host_b_voice
                fresh.state.voice_pair_id = match_voice_pair_id(req.host_a_voice, req.host_b_voice)
                fresh.updated_at = utc_now_iso()

                await asyncio.to_thread(store.save_session, fresh)
                keep_files = await asyncio.to_thread(store.collect_retained_audio_filenames, fresh)
                await asyncio.to_thread(gc_unreferenced_audio, store.audio_dir(session_id), keep_files)

            cov = compute_coverage(fresh)
            return {
                "session": fresh.model_dump(),
                "coverage": cov.model_dump(),
                "stats": {
                    "generated_count": synth.generated_count,
                    "cached_count": synth.cached_count,
                    "total_lines": len(fresh.script),
                },
            }
        finally:
            store.end_generation(session_id)

    @app.get("/api/sessions/{session_id}/audio/{filename}")
    async def get_audio_clip(session_id: str, filename: str) -> FileResponse:
        try:
            audio_path = await asyncio.to_thread(store.get_audio_path, session_id, filename)
        except Exception as exc:
            raise _map_store_error(exc) from exc
        return FileResponse(
            path=audio_path,
            media_type="audio/mpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @app.patch("/api/sessions/{session_id}/state")
    async def patch_state(session_id: str, req: StatePatchRequest) -> dict[str, Any]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            try:
                session = await asyncio.to_thread(store.load_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc

            if req.playback_rate is not None:
                if not (0.5 <= req.playback_rate <= 3.0):
                    raise HTTPException(status_code=400, detail="playback_rate must be between 0.5 and 3.0.")
                session.state.playback_rate = round(float(req.playback_rate), 2)

            if req.last_line_index is not None:
                max_idx = max(0, len(session.script) - 1)
                session.state.last_line_index = max(0, min(req.last_line_index, max_idx))

            if req.host_a_voice is not None:
                session.state.host_a_voice = req.host_a_voice
            if req.host_b_voice is not None:
                session.state.host_b_voice = req.host_b_voice

            if req.voice_pair_id is not None:
                session.state.voice_pair_id = req.voice_pair_id
            elif req.host_a_voice is not None or req.host_b_voice is not None:
                session.state.voice_pair_id = match_voice_pair_id(
                    session.state.host_a_voice, session.state.host_b_voice
                )

            if req.auto_scroll is not None:
                session.state.auto_scroll = req.auto_scroll

            session.updated_at = utc_now_iso()
            await asyncio.to_thread(store.save_session, session)
            return {"state": session.state.model_dump()}

    return app


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass and commit**

Run:
```powershell
pytest tests/test_api_integration.py -v
git add app.py tests/test_api_integration.py
git commit -m "feat: implement FastAPI routes with streaming uploads, concurrency guards, undo, and resynthesize"
```
Expected: `3 passed`, clean commit.

---

### Task 8: Material 3 Expressive Single-File Frontend & Contract Tests

**Files:**
- Create: `tests/test_frontend_contract.py`
- Create: `static/index.html`

**Interfaces:**
- Consumes: All endpoints in `app.py` (`/api/voices`, `/api/upload`, `/api/sessions`, `/api/sessions/{id}`, `/api/sessions/{id}/pdf`, `/api/sessions/{id}/prompt`, `/api/sessions/{id}/generate`, `/api/sessions/{id}/generate/status`, `/api/sessions/{id}/undo`, `/api/sessions/{id}/resynthesize`, `/api/sessions/{id}/audio/{filename}`, `/api/sessions/{id}/state`, `/static/vendor/{filename}`)
- Produces: `static/index.html` implementing `E-01`..`E-23` and `I-01`..`I-20` from `docs/superpowers/specs/2026-11-20-deepexamcast-m3-ui-spec.md`, passing `audit_m3_spec.py --code` with 0 errors and 0 warnings.

- [ ] **Step 1: Write failing contract tests in `tests/test_frontend_contract.py`**

```python
import json
from pathlib import Path
import re
import subprocess
import sys

from fastapi.testclient import TestClient

from app import app

AUDIT_SCRIPT = Path(
    r"C:\Users\Abishek\.gemini\antigravity-cli\skills\m3-expressive-architect\scripts\audit_m3_spec.py"
)
INDEX_PATH = Path("static/index.html")


def test_frontend_file_served_and_security_contracts():
    assert INDEX_PATH.is_file(), "static/index.html must exist"
    html = INDEX_PATH.read_text(encoding="utf-8")

    # FastAPI root serves index.html
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "DeepExamCast" in resp.text

    # Security & PDF.js 4.10.38 hardening
    assert "pdfjs-dist@4.10.38" in html
    assert "isEvalSupported: false" in html
    assert "URL.createObjectURL(blob)" in html
    assert "innerHTML" not in html

    # Compiled M3 Expressive Spring tokens & reduced-motion guard
    assert "--md-sys-motion-spring-fast-spatial:" in html
    assert "--md-sys-motion-spring-default-spatial:" in html
    assert "--md-sys-motion-spring-fast-effects:" in html
    assert "prefers-reduced-motion" in html

    # Key M3 elements E-01..E-23 hooks present
    for elem_id in [
        "sessionSelect",
        "deleteSessionBtn",
        "uploadBtn",
        "drawerToggleBtn",
        "scriptSheet",
        "fromPageInput",
        "toPageInput",
        "copyPromptBtn",
        "jsonInput",
        "voicePairSelect",
        "resynthesizeBtn",
        "appendBtn",
        "replaceBtn",
        "undoBtn",
        "genProgressBox",
        "drawerAlert",
        "prevLineBtn",
        "playPauseBtn",
        "nextLineBtn",
        "repeatLineBtn",
        "speedGroup",
        "lineScrubber",
        "autoScrollBtn",
        "pdfPane",
        "dialoguePane",
        "snackbarStack",
        "mobileTabs",
    ]:
        assert f'id="{elem_id}"' in html, f"Missing element id={elem_id}"

    # Zero side-stripe >1px borders, gradient text, or emojis
    assert not re.search(r"border-(?:left|right)\s*:\s*[2-9]px", html)
    assert "background-clip: text" not in html


def test_frontend_passes_deterministic_m3_code_audit(tmp_path: Path):
    html = INDEX_PATH.read_text(encoding="utf-8")

    token_match = re.search(r"<style[^>]*data-m3-tokens[^>]*>(.*?)</style>", html, re.DOTALL)
    comp_match = re.search(r"<style[^>]*data-m3-components[^>]*>(.*?)</style>", html, re.DOTALL)
    js_match = re.search(r"<script[^>]*data-m3-app[^>]*>(.*?)</script>", html, re.DOTALL)

    assert token_match and comp_match and js_match

    (tmp_path / "m3_tokens.css").write_text(token_match.group(1), encoding="utf-8")
    (tmp_path / "app_styles.css").write_text(comp_match.group(1), encoding="utf-8")
    (tmp_path / "app_script.js").write_text(js_match.group(1), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--code", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"audit_m3_spec.py failed:\n{proc.stdout}\n{proc.stderr}"
    report = json.loads(proc.stdout)
    assert report["passed"] is True
    assert report["errors"] == []
    assert report["warnings"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontend_contract.py -v`
Expected: FAIL with `AssertionError: static/index.html must exist`.

- [ ] **Step 3: Implement complete Material 3 Expressive `static/index.html`**

Write `static/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DeepExamCast — Synced Exam Audio Lecture Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&family=Sora:wght@500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>

  <style data-m3-tokens>
    :root {
      /* Material 3 Expressive — Nocturnal Study-Lamp Dark Theme */
      --md-sys-color-primary: #F5C84C;
      --md-sys-color-on-primary: #3D2E00;
      --md-sys-color-primary-container: #574300;
      --md-sys-color-on-primary-container: #FFE08A;
      --md-sys-color-primary-fixed: #FFE08A;
      --md-sys-color-primary-fixed-dim: #F5C84C;
      --md-sys-color-on-primary-fixed: #241A00;
      --md-sys-color-on-primary-fixed-variant: #574300;

      --md-sys-color-secondary: #ADC6FF;
      --md-sys-color-on-secondary: #102F60;
      --md-sys-color-secondary-container: #2B4678;
      --md-sys-color-on-secondary-container: #D8E2FF;

      --md-sys-color-tertiary: #80D5C8;
      --md-sys-color-on-tertiary: #003731;
      --md-sys-color-tertiary-container: #005048;
      --md-sys-color-on-tertiary-container: #9DF2E4;

      --md-sys-color-surface: #111318;
      --md-sys-color-surface-dim: #0D1015;
      --md-sys-color-surface-bright: #37393E;
      --md-sys-color-surface-container-lowest: #0C0E13;
      --md-sys-color-surface-container-low: #171A20;
      --md-sys-color-surface-container: #1C1F26;
      --md-sys-color-surface-container-high: #262A33;
      --md-sys-color-surface-container-highest: #313540;
      --md-sys-color-on-surface: #E2E2E9;
      --md-sys-color-on-surface-variant: #C4C6D0;
      --md-sys-color-outline: #8E9099;
      --md-sys-color-outline-variant: #44474F;

      --md-sys-color-inverse-surface: #E2E2E9;
      --md-sys-color-on-inverse-surface: #2E3036;
      --md-sys-color-inverse-primary: #745B00;

      --md-sys-color-error: #FFB4AB;
      --md-sys-color-on-error: #690005;
      --md-sys-color-error-container: #93000A;
      --md-sys-color-on-error-container: #FFDAD6;
      --md-sys-color-scrim: rgba(0, 0, 0, 0.56);

      /* PDF Highlight Tokens */
      --md-sys-color-pdf-highlight-fill: rgba(250, 204, 21, 0.35);
      --md-sys-color-pdf-highlight-border: rgba(245, 158, 11, 0.85);
      --md-sys-color-state-hover: rgba(226, 226, 233, 0.08);
      --md-sys-color-state-focus: rgba(226, 226, 233, 0.12);
      --md-sys-color-state-pressed: rgba(226, 226, 233, 0.12);

      /* Typography */
      --md-sys-typescale-display: 'Sora', system-ui, -apple-system, sans-serif;
      --md-sys-typescale-body: 'Figtree', system-ui, -apple-system, sans-serif;
      --md-sys-typescale-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;

      /* Shape Scale */
      --md-sys-shape-extra-small: 4px;
      --md-sys-shape-small: 8px;
      --md-sys-shape-medium: 12px;
      --md-sys-shape-large: 16px;
      --md-sys-shape-large-increased: 20px;
      --md-sys-shape-extra-large: 28px;
      --md-sys-shape-full: 9999px;

      /* Compiled Material 3 (Expressive) GPU-Compositor Springs */
      --md-sys-motion-spring-fast-spatial-duration: 359ms;
      --md-sys-motion-spring-fast-spatial-easing: linear(0, 0.0442, 0.1537, 0.2988, 0.4562, 0.6089, 0.7458, 0.8604, 0.9503, 1.0158, 1.0593, 1.0841, 1.0941, 1.0931, 1.0846, 1.0719, 1.0572, 1.0424, 1.0287, 1.017, 1.0076, 1.0006, 0.9957, 0.9927, 0.9913, 0.991, 0.9916, 0.9927, 0.994, 0.9955, 0.9968, 0.998, 1);
      --md-sys-motion-spring-fast-spatial: 359ms linear(0, 0.0442, 0.1537, 0.2988, 0.4562, 0.6089, 0.7458, 0.8604, 0.9503, 1.0158, 1.0593, 1.0841, 1.0941, 1.0931, 1.0846, 1.0719, 1.0572, 1.0424, 1.0287, 1.017, 1.0076, 1.0006, 0.9957, 0.9927, 0.9913, 0.991, 0.9916, 0.9927, 0.994, 0.9955, 0.9968, 0.998, 1);
      --md-sys-motion-spring-default-spatial-duration: 434ms;
      --md-sys-motion-spring-default-spatial-easing: linear(0, 0.0303, 0.1051, 0.2049, 0.3152, 0.4263, 0.5316, 0.6271, 0.7108, 0.7821, 0.8411, 0.8887, 0.9262, 0.955, 0.9764, 0.9917, 1.0023, 1.009, 1.0129, 1.0148, 1.0151, 1.0145, 1.0133, 1.0117, 1.0101, 1.0084, 1.0068, 1.0054, 1.0042, 1.0031, 1.0023, 1.0016, 1);
      --md-sys-motion-spring-default-spatial: 434ms linear(0, 0.0303, 0.1051, 0.2049, 0.3152, 0.4263, 0.5316, 0.6271, 0.7108, 0.7821, 0.8411, 0.8887, 0.9262, 0.955, 0.9764, 0.9917, 1.0023, 1.009, 1.0129, 1.0148, 1.0151, 1.0145, 1.0133, 1.0117, 1.0101, 1.0084, 1.0068, 1.0054, 1.0042, 1.0031, 1.0023, 1.0016, 1);
      --md-sys-motion-spring-fast-effects-duration: 149ms;
      --md-sys-motion-spring-fast-effects-easing: linear(0, 0.0341, 0.1134, 0.2133, 0.3185, 0.4202, 0.5136, 0.5965, 0.6683, 0.7294, 0.7806, 0.8232, 0.8581, 0.8866, 0.9098, 0.9284, 0.9434, 0.9553, 0.9648, 0.9724, 0.9783, 0.9831, 0.9868, 0.9897, 0.992, 0.9937, 0.9951, 0.9962, 0.9971, 0.9977, 0.9982, 0.9986, 1);
      --md-sys-motion-spring-fast-effects: 149ms linear(0, 0.0341, 0.1134, 0.2133, 0.3185, 0.4202, 0.5136, 0.5965, 0.6683, 0.7294, 0.7806, 0.8232, 0.8581, 0.8866, 0.9098, 0.9284, 0.9434, 0.9553, 0.9648, 0.9724, 0.9783, 0.9831, 0.9868, 0.9897, 0.992, 0.9937, 0.9951, 0.9962, 0.9971, 0.9977, 0.9982, 0.9986, 1);
      --md-sys-motion-spring-default-effects-duration: 230ms;
      --md-sys-motion-spring-default-effects-easing: linear(0, 0.0342, 0.1137, 0.2138, 0.3192, 0.421, 0.5145, 0.5974, 0.6691, 0.7302, 0.7814, 0.8238, 0.8587, 0.8872, 0.9102, 0.9288, 0.9437, 0.9556, 0.9651, 0.9726, 0.9785, 0.9832, 0.9869, 0.9898, 0.992, 0.9938, 0.9952, 0.9963, 0.9971, 0.9978, 0.9983, 0.9987, 1);
      --md-sys-motion-spring-default-effects: 230ms linear(0, 0.0342, 0.1137, 0.2138, 0.3192, 0.421, 0.5145, 0.5974, 0.6691, 0.7302, 0.7814, 0.8238, 0.8587, 0.8872, 0.9102, 0.9288, 0.9437, 0.9556, 0.9651, 0.9726, 0.9785, 0.9832, 0.9869, 0.9898, 0.992, 0.9938, 0.9952, 0.9963, 0.9971, 0.9978, 0.9983, 0.9987, 1);
      --md-sys-motion-spring-slow-effects-duration: 326ms;
      --md-sys-motion-spring-slow-effects-easing: linear(0, 0.0343, 0.1142, 0.2145, 0.3202, 0.4221, 0.5157, 0.5986, 0.6703, 0.7313, 0.7824, 0.8248, 0.8596, 0.8879, 0.9109, 0.9294, 0.9442, 0.956, 0.9654, 0.9729, 0.9788, 0.9834, 0.987, 0.9899, 0.9921, 0.9939, 0.9953, 0.9963, 0.9972, 0.9978, 0.9983, 0.9987, 1);
      --md-sys-motion-spring-slow-effects: 326ms linear(0, 0.0343, 0.1142, 0.2145, 0.3202, 0.4221, 0.5157, 0.5986, 0.6703, 0.7313, 0.7824, 0.8248, 0.8596, 0.8879, 0.9109, 0.9294, 0.9442, 0.956, 0.9654, 0.9729, 0.9788, 0.9834, 0.987, 0.9899, 0.9921, 0.9939, 0.9953, 0.9963, 0.9972, 0.9978, 0.9983, 0.9987, 1);
    }

    @media (prefers-reduced-motion: reduce) {
      :root {
        --md-sys-motion-spring-fast-spatial-duration: 150ms;
        --md-sys-motion-spring-fast-spatial-easing: ease-out;
        --md-sys-motion-spring-fast-spatial: 150ms ease-out;
        --md-sys-motion-spring-default-spatial-duration: 150ms;
        --md-sys-motion-spring-default-spatial-easing: ease-out;
        --md-sys-motion-spring-default-spatial: 150ms ease-out;
        --md-sys-motion-spring-fast-effects-duration: 150ms;
        --md-sys-motion-spring-fast-effects-easing: ease-out;
        --md-sys-motion-spring-fast-effects: 150ms ease-out;
        --md-sys-motion-spring-default-effects-duration: 150ms;
        --md-sys-motion-spring-default-effects-easing: ease-out;
        --md-sys-motion-spring-default-effects: 150ms ease-out;
        --md-sys-motion-spring-slow-effects-duration: 150ms;
        --md-sys-motion-spring-slow-effects-easing: ease-out;
        --md-sys-motion-spring-slow-effects: 150ms ease-out;
      }
    }
  </style>

  <style data-m3-components>
    *, *::before, *::after {
      box-sizing: border-box;
    }

    html, body {
      margin: 0;
      padding: 0;
      height: 100dvh;
      overflow: hidden;
      background-color: var(--md-sys-color-surface);
      color: var(--md-sys-color-on-surface);
      font-family: var(--md-sys-typescale-body);
      -webkit-font-smoothing: antialiased;
    }

    .app-shell {
      display: flex;
      flex-direction: column;
      height: 100dvh;
      width: 100%;
      position: relative;
      background-color: var(--md-sys-color-surface);
    }

    /* Accessible Focus Ring */
    button:focus-visible,
    select:focus-visible,
    input:focus-visible,
    textarea:focus-visible,
    [tabindex]:focus-visible {
      outline: 3px solid var(--md-sys-color-secondary);
      outline-offset: 2px;
    }

    /* E-01 Top App Bar */
    .top-app-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 64px;
      padding: 8px 16px;
      background-color: var(--md-sys-color-surface-container);
      border-bottom: 1px solid var(--md-sys-color-outline-variant);
      flex-shrink: 0;
      z-index: 30;
    }

    .brand-lockup {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-shrink: 0;
    }

    .brand-title {
      font-family: var(--md-sys-typescale-display);
      font-size: 1.05rem;
      font-weight: 600;
      letter-spacing: -0.02em;
      color: var(--md-sys-color-on-surface);
    }

    .top-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
      flex: 1;
      min-width: 0;
    }

    /* M3 Controls & Expressive Morphing */
    .m3-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 40px;
      padding: 0 16px;
      border-radius: var(--md-sys-shape-full);
      border: 1px solid transparent;
      font-family: var(--md-sys-typescale-display);
      font-size: 0.84rem;
      font-weight: 600;
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
      transition:
        transform var(--md-sys-motion-spring-fast-spatial),
        border-radius var(--md-sys-motion-spring-fast-spatial),
        background-color var(--md-sys-motion-spring-fast-effects),
        color var(--md-sys-motion-spring-fast-effects),
        border-color var(--md-sys-motion-spring-fast-effects),
        opacity var(--md-sys-motion-spring-fast-effects);
    }

    .m3-btn:disabled {
      opacity: 0.42;
      cursor: not-allowed;
    }

    .m3-btn:not(:disabled):active {
      transform: scale(0.97);
      border-radius: var(--md-sys-shape-medium);
    }

    .m3-btn-primary {
      background-color: var(--md-sys-color-primary);
      color: var(--md-sys-color-on-primary);
    }

    .m3-btn-tonal {
      background-color: var(--md-sys-color-secondary-container);
      color: var(--md-sys-color-on-secondary-container);
    }

    .m3-btn-amber-tonal {
      background-color: var(--md-sys-color-primary-container);
      color: var(--md-sys-color-on-primary-container);
      border-color: var(--md-sys-color-outline-variant);
    }

    .m3-btn-outlined {
      background-color: transparent;
      color: var(--md-sys-color-on-surface);
      border-color: var(--md-sys-color-outline);
    }

    .m3-icon-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 40px;
      min-height: 40px;
      border-radius: var(--md-sys-shape-full);
      border: 1px solid transparent;
      background-color: transparent;
      color: var(--md-sys-color-on-surface-variant);
      cursor: pointer;
      transition:
        transform var(--md-sys-motion-spring-fast-spatial),
        border-radius var(--md-sys-motion-spring-fast-spatial),
        background-color var(--md-sys-motion-spring-fast-effects),
        color var(--md-sys-motion-spring-fast-effects);
    }

    .m3-icon-btn:not(:disabled):active {
      transform: scale(0.95);
      border-radius: var(--md-sys-shape-small);
    }

    .m3-icon-btn:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    @media (hover: hover) and (pointer: fine) {
      .m3-btn:not(:disabled):hover {
        filter: brightness(1.06);
      }
      .m3-icon-btn:not(:disabled):hover {
        background-color: var(--md-sys-color-state-hover);
        color: var(--md-sys-color-on-surface);
      }
      .m3-icon-btn-danger:not(:disabled):hover {
        color: var(--md-sys-color-error);
      }
    }

    .m3-select, .m3-input, .m3-textarea {
      background-color: var(--md-sys-color-surface-container-high);
      color: var(--md-sys-color-on-surface);
      border: 1px solid var(--md-sys-color-outline-variant);
      border-radius: var(--md-sys-shape-medium);
      padding: 8px 12px;
      font-family: var(--md-sys-typescale-body);
      font-size: 0.875rem;
      transition: border-color var(--md-sys-motion-spring-fast-effects);
    }

    .m3-select {
      min-height: 40px;
      max-width: 280px;
    }

    .m3-input {
      min-height: 40px;
      font-family: var(--md-sys-typescale-mono);
      font-variant-numeric: tabular-nums;
      background-color: var(--md-sys-color-surface-container-highest);
    }

    .m3-textarea {
      width: 100%;
      min-height: 120px;
      resize: vertical;
      background-color: var(--md-sys-color-surface-container-lowest);
      font-family: var(--md-sys-typescale-mono);
      font-size: 0.8rem;
      line-height: 1.5;
    }

    .mono-num {
      font-family: var(--md-sys-typescale-mono);
      font-variant-numeric: tabular-nums;
    }

    /* E-07 Top-Anchored Script Sheet (GPU Compositor Only, Zero Layout Reflow) */
    .sheet-scrim {
      position: fixed;
      inset: 0;
      background-color: var(--md-sys-color-scrim);
      z-index: 35;
      opacity: 0;
      pointer-events: none;
      transition: opacity var(--md-sys-motion-spring-default-effects);
    }

    .sheet-scrim.open {
      opacity: 1;
      pointer-events: auto;
    }

    .script-sheet {
      position: fixed;
      top: 64px;
      left: 50%;
      width: min(960px, calc(100vw - 24px));
      max-height: calc(100dvh - 88px);
      overflow-y: auto;
      background-color: var(--md-sys-color-surface-container-high);
      border: 1px solid var(--md-sys-color-outline-variant);
      border-top: none;
      border-radius: 0 0 var(--md-sys-shape-extra-large) var(--md-sys-shape-extra-large);
      padding: 20px;
      z-index: 40;
      box-shadow: 0 18px 44px rgba(0, 0, 0, 0.48);
      transform: translate3d(-50%, -14px, 0) scale(0.98);
      opacity: 0;
      pointer-events: none;
      transition:
        transform var(--md-sys-motion-spring-default-spatial),
        opacity var(--md-sys-motion-spring-default-effects);
    }

    .script-sheet.open {
      transform: translate3d(-50%, 0, 0) scale(1);
      opacity: 1;
      pointer-events: auto;
    }

    .sheet-grid {
      display: grid;
      gap: 16px;
    }

    .sheet-row {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      gap: 12px;
    }

    .field-group {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .field-label {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--md-sys-color-on-surface-variant);
      letter-spacing: 0.02em;
    }

    .linear-track {
      position: relative;
      height: 8px;
      width: 100%;
      background-color: var(--md-sys-color-surface-container-highest);
      border-radius: var(--md-sys-shape-full);
      overflow: hidden;
    }

    .linear-fill {
      position: absolute;
      inset: 0;
      background-color: var(--md-sys-color-primary);
      border-radius: var(--md-sys-shape-full);
      transform-origin: left center;
      transform: scaleX(0);
      transition: transform var(--md-sys-motion-spring-default-spatial);
    }

    .alert-banner {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-radius: var(--md-sys-shape-large);
      border: 1px solid var(--md-sys-color-outline-variant);
      font-size: 0.85rem;
      line-height: 1.45;
      transition: opacity var(--md-sys-motion-spring-default-effects);
    }

    .alert-error {
      background-color: var(--md-sys-color-error-container);
      color: var(--md-sys-color-on-error-container);
    }

    .alert-warning {
      background-color: var(--md-sys-color-primary-container);
      color: var(--md-sys-color-on-primary-container);
    }

    /* E-16..E-19 Sticky Playback Bar */
    .playback-bar {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      padding: 8px 16px;
      background-color: var(--md-sys-color-surface-container);
      border-bottom: 1px solid var(--md-sys-color-outline-variant);
      flex-shrink: 0;
      z-index: 25;
    }

    .transport-cluster {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .play-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-width: 96px;
      min-height: 40px;
      padding: 0 18px;
      border-radius: var(--md-sys-shape-full);
      border: none;
      background-color: var(--md-sys-color-primary);
      color: var(--md-sys-color-on-primary);
      font-family: var(--md-sys-typescale-display);
      font-size: 0.86rem;
      font-weight: 700;
      cursor: pointer;
      transition:
        transform var(--md-sys-motion-spring-fast-spatial),
        border-radius var(--md-sys-motion-spring-fast-spatial),
        opacity var(--md-sys-motion-spring-fast-effects);
    }

    .play-pill[data-playing="true"] {
      border-radius: var(--md-sys-shape-medium);
    }

    .play-pill:not(:disabled):active {
      transform: scale(0.96);
      border-radius: var(--md-sys-shape-medium);
    }

    .play-pill:disabled {
      opacity: 0.42;
      cursor: not-allowed;
    }

    .speed-group {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 3px;
      background-color: var(--md-sys-color-surface-container-low);
      border-radius: var(--md-sys-shape-full);
      border: 1px solid var(--md-sys-color-outline-variant);
    }

    .speed-pill {
      min-height: 34px;
      padding: 0 10px;
      border: none;
      border-radius: var(--md-sys-shape-full);
      background-color: transparent;
      color: var(--md-sys-color-on-surface-variant);
      font-family: var(--md-sys-typescale-mono);
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      transition:
        transform var(--md-sys-motion-spring-fast-spatial),
        border-radius var(--md-sys-motion-spring-fast-spatial),
        background-color var(--md-sys-motion-spring-fast-effects),
        color var(--md-sys-motion-spring-fast-effects);
    }

    .speed-pill[aria-pressed="true"] {
      background-color: var(--md-sys-color-primary-container);
      color: var(--md-sys-color-on-primary-container);
      border-radius: var(--md-sys-shape-small);
    }

    .speed-pill:active {
      transform: scale(0.95);
    }

    .scrubber-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 1;
      min-width: 200px;
    }

    .m3-slider {
      flex: 1;
      min-width: 110px;
      accent-color: var(--md-sys-color-primary);
      cursor: pointer;
      height: 28px;
    }

    .filter-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 36px;
      padding: 0 14px;
      border-radius: var(--md-sys-shape-small);
      border: 1px solid var(--md-sys-color-outline);
      background-color: transparent;
      color: var(--md-sys-color-on-surface-variant);
      font-family: var(--md-sys-typescale-display);
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      transition:
        transform var(--md-sys-motion-spring-fast-spatial),
        border-radius var(--md-sys-motion-spring-fast-spatial),
        background-color var(--md-sys-motion-spring-fast-effects),
        color var(--md-sys-motion-spring-fast-effects),
        border-color var(--md-sys-motion-spring-fast-effects);
    }

    .filter-chip[aria-pressed="true"] {
      background-color: var(--md-sys-color-secondary-container);
      color: var(--md-sys-color-on-secondary-container);
      border-color: transparent;
      border-radius: var(--md-sys-shape-full);
    }

    .filter-chip:active {
      transform: scale(0.97);
    }

    /* E-23 Mobile Pane Switcher (Hidden >=840px) */
    .mobile-tabs {
      display: none;
      padding: 8px 12px;
      background-color: var(--md-sys-color-surface-container-low);
      border-bottom: 1px solid var(--md-sys-color-outline-variant);
      gap: 8px;
      flex-shrink: 0;
    }

    .mobile-tab-btn {
      flex: 1;
      min-height: 44px;
      border-radius: var(--md-sys-shape-full);
      border: 1px solid var(--md-sys-color-outline-variant);
      background-color: var(--md-sys-color-surface-container-high);
      color: var(--md-sys-color-on-surface-variant);
      font-family: var(--md-sys-typescale-display);
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      transition:
        transform var(--md-sys-motion-spring-fast-spatial),
        background-color var(--md-sys-motion-spring-fast-effects),
        color var(--md-sys-motion-spring-fast-effects);
    }

    .mobile-tab-btn[aria-selected="true"] {
      background-color: var(--md-sys-color-secondary-container);
      color: var(--md-sys-color-on-secondary-container);
      border-color: transparent;
    }

    /* Main Split Supporting-Pane Workspace (68% / 32%) */
    .workspace-grid {
      display: grid;
      grid-template-columns: minmax(0, 68%) minmax(0, 32%);
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }

    .pdf-pane {
      display: flex;
      flex-direction: column;
      min-height: 0;
      background-color: var(--md-sys-color-surface-container-lowest);
      border-right: 1px solid var(--md-sys-color-outline-variant);
    }

    .pdf-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 14px;
      background-color: var(--md-sys-color-surface-container-low);
      border-bottom: 1px solid var(--md-sys-color-outline-variant);
      flex-shrink: 0;
    }

    .pdf-scroll {
      flex: 1;
      overflow: auto;
      padding: 18px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 18px;
    }

    .pdf-page-frame {
      position: relative;
      background-color: var(--md-sys-color-surface-container);
      border-radius: var(--md-sys-shape-small);
      box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
      overflow: hidden;
      flex-shrink: 0;
    }

    .pdf-page-canvas {
      display: block;
      width: 100%;
      height: 100%;
    }

    .chunk-overlay-layer {
      position: absolute;
      inset: 0;
    }

    .chunk-box {
      position: absolute;
      border-radius: var(--md-sys-shape-extra-small);
      border: 1.5px solid transparent;
      background-color: transparent;
      transition:
        background-color var(--md-sys-motion-spring-fast-effects),
        border-color var(--md-sys-motion-spring-fast-effects);
    }

    .chunk-box[data-covered="true"] {
      cursor: pointer;
    }

    @media (hover: hover) and (pointer: fine) {
      .chunk-box[data-covered="true"]:hover {
        background-color: rgba(250, 204, 21, 0.14);
        border-color: rgba(245, 158, 11, 0.45);
      }
      .chunk-box[data-covered="false"]:hover {
        background-color: rgba(226, 226, 233, 0.08);
        border-color: var(--md-sys-color-outline-variant);
      }
    }

    .chunk-box[data-active="true"] {
      background-color: var(--md-sys-color-pdf-highlight-fill);
      border-color: var(--md-sys-color-pdf-highlight-border);
    }

    /* E-21 Supporting Pane (32%) */
    .dialogue-pane {
      display: flex;
      flex-direction: column;
      min-height: 0;
      background-color: var(--md-sys-color-surface-container-low);
    }

    .dialogue-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 16px;
      border-bottom: 1px solid var(--md-sys-color-outline-variant);
      flex-shrink: 0;
    }

    .dialogue-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .dialogue-card {
      width: 100%;
      text-align: left;
      padding: 14px 16px;
      border-radius: var(--md-sys-shape-large-increased);
      border: 1px solid var(--md-sys-color-outline-variant);
      background-color: var(--md-sys-color-surface-container);
      color: var(--md-sys-color-on-surface);
      cursor: pointer;
      transition:
        background-color var(--md-sys-motion-spring-default-effects),
        border-color var(--md-sys-motion-spring-default-effects);
    }

    @media (hover: hover) and (pointer: fine) {
      .dialogue-card:hover {
        background-color: var(--md-sys-color-surface-container-high);
      }
    }

    .dialogue-card[data-active="true"] {
      background-color: var(--md-sys-color-primary-container);
      color: var(--md-sys-color-on-primary-container);
      border-color: var(--md-sys-color-primary);
    }

    .dialogue-card-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 8px;
    }

    .speaker-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 2px 10px;
      border-radius: var(--md-sys-shape-full);
      font-family: var(--md-sys-typescale-display);
      font-size: 0.74rem;
      font-weight: 600;
    }

    .speaker-prof {
      background-color: var(--md-sys-color-secondary-container);
      color: var(--md-sys-color-on-secondary-container);
    }

    .speaker-student {
      background-color: var(--md-sys-color-tertiary-container);
      color: var(--md-sys-color-on-tertiary-container);
    }

    .dialogue-body {
      font-size: 0.9375rem;
      line-height: 1.65;
      max-width: 65ch;
      margin: 0;
    }

    .exam-note-box {
      margin-top: 10px;
      padding: 8px 12px;
      border-radius: var(--md-sys-shape-medium);
      border: 1px solid var(--md-sys-color-outline-variant);
      background-color: var(--md-sys-color-surface-container-high);
      color: var(--md-sys-color-primary-fixed);
      font-size: 0.82rem;
      line-height: 1.5;
    }

    .dialogue-card[data-active="true"] .exam-note-box {
      background-color: var(--md-sys-color-surface-container);
      border-color: var(--md-sys-color-primary);
    }

    .empty-state-card {
      margin: auto;
      max-width: 460px;
      padding: 24px;
      border-radius: var(--md-sys-shape-large-increased);
      border: 1px solid var(--md-sys-color-outline-variant);
      background-color: var(--md-sys-color-surface-container);
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    /* E-22 Snackbar Stack */
    .snackbar-stack {
      position: fixed;
      bottom: 18px;
      right: 18px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      z-index: 50;
      max-width: min(420px, calc(100vw - 32px));
    }

    .snackbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 16px;
      border-radius: var(--md-sys-shape-medium);
      background-color: var(--md-sys-color-inverse-surface);
      color: var(--md-sys-color-on-inverse-surface);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.36);
      font-size: 0.86rem;
      opacity: 0;
      transform: translateY(8px) scale(0.96);
      transition:
        transform var(--md-sys-motion-spring-default-spatial),
        opacity var(--md-sys-motion-spring-fast-effects);
    }

    .snackbar.visible {
      opacity: 1;
      transform: translateY(0) scale(1);
    }

    .snackbar-action {
      border: none;
      background: transparent;
      color: var(--md-sys-color-inverse-primary);
      font-family: var(--md-sys-typescale-display);
      font-weight: 700;
      font-size: 0.82rem;
      cursor: pointer;
      padding: 4px 8px;
      border-radius: var(--md-sys-shape-full);
    }

    /* Responsive Adaptive Window Size Classes */
    @media (max-width: 839px) {
      .mobile-tabs {
        display: flex;
      }
      .workspace-grid {
        grid-template-columns: minmax(0, 1fr);
      }
      .pdf-pane[data-mobile-hidden="true"],
      .dialogue-pane[data-mobile-hidden="true"] {
        display: none;
      }
      .pdf-pane {
        border-right: none;
      }
      .m3-btn, .m3-icon-btn, .play-pill, .filter-chip, .m3-select, .m3-input {
        min-height: 48px;
      }
      .m3-icon-btn {
        min-width: 48px;
      }
      .script-sheet {
        top: 0;
        width: 100vw;
        max-height: 100dvh;
        border-radius: 0 0 var(--md-sys-shape-large) var(--md-sys-shape-large);
      }
    }

    @media (max-height: 479px) {
      .top-app-bar, .playback-bar {
        min-height: 44px;
        padding-top: 4px;
        padding-bottom: 4px;
      }
    }

    /* Instant 0ms Keyboard Action Feedback */
    [data-instant="true"] {
      transition-duration: 0ms !important;
    }

    .hidden-el {
      display: none !important;
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <!-- E-01 Top App Bar -->
    <header class="top-app-bar">
      <div class="brand-lockup">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="2" y="9" width="3" height="6" rx="1.5" fill="var(--md-sys-color-primary)"/>
          <rect x="7" y="5" width="3" height="14" rx="1.5" fill="var(--md-sys-color-primary)"/>
          <rect x="12" y="3" width="3" height="18" rx="1.5" fill="var(--md-sys-color-secondary)"/>
          <rect x="17" y="7" width="3" height="10" rx="1.5" fill="var(--md-sys-color-tertiary)"/>
        </svg>
        <span class="brand-title">DeepExamCast</span>
      </div>

      <div class="top-actions">
        <select id="sessionSelect" class="m3-select" aria-label="Saved study sessions"></select>
        <button id="deleteSessionBtn" class="m3-icon-btn m3-icon-btn-danger" type="button" title="Delete selected session" aria-label="Delete selected session" disabled>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>
          </svg>
        </button>

        <input id="pdfInput" type="file" accept="application/pdf" class="hidden-el">
        <button id="uploadBtn" class="m3-btn m3-btn-tonal" type="button">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <span id="uploadBtnLabel">Upload PDF</span>
        </button>

        <button id="drawerToggleBtn" class="m3-btn m3-btn-amber-tonal" type="button" aria-expanded="false" aria-controls="scriptSheet">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 5v14"/><path d="M5 12h14"/>
          </svg>
          <span>Add / Generate Deep Script</span>
        </button>
      </div>
    </header>

    <!-- E-07 Top-Anchored Script Sheet -->
    <div id="scriptSheetScrim" class="sheet-scrim" aria-hidden="true"></div>
    <section id="scriptSheet" class="script-sheet" aria-label="Add or generate deep script" aria-hidden="true">
      <div class="sheet-grid">
        <div class="sheet-row" style="justify-content: space-between;">
          <div style="display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end;">
            <div class="field-group">
              <label for="fromPageInput" class="field-label">From Page</label>
              <input id="fromPageInput" class="m3-input" type="number" min="1" value="1" style="width:92px;">
            </div>
            <div class="field-group">
              <label for="toPageInput" class="field-label">To Page</label>
              <input id="toPageInput" class="m3-input" type="number" min="1" value="5" style="width:92px;">
            </div>
            <button id="copyPromptBtn" class="m3-btn m3-btn-amber-tonal" type="button">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              <span>Copy Prompt for Gemini Pro</span>
            </button>
          </div>
          <button id="closeSheetBtn" class="m3-icon-btn" type="button" aria-label="Close script drawer">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <!-- E-09 Coverage Meter -->
        <div class="field-group" style="gap:6px;">
          <div style="display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;">
            <span id="coverageSummary" class="field-label mono-num">No PDF loaded</span>
            <span id="partialSummary" class="field-label mono-num"></span>
          </div>
          <div class="linear-track">
            <div id="coverageBarFill" class="linear-fill"></div>
          </div>
        </div>

        <!-- E-11 JSON Paste -->
        <div class="field-group">
          <label for="jsonInput" class="field-label">Paste Gemini JSON Array</label>
          <textarea id="jsonInput" class="m3-textarea" placeholder='[{"speaker":"HOST_A","text":"...","chunk_ids":["C1"],"exam_note":"..."}]'></textarea>
        </div>

        <!-- E-12 & E-13 Voice & Actions -->
        <div class="sheet-row" style="justify-content: space-between;">
          <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end;">
            <div class="field-group">
              <label for="voicePairSelect" class="field-label">Voice Pair</label>
              <select id="voicePairSelect" class="m3-select"></select>
            </div>
            <button id="resynthesizeBtn" class="m3-btn m3-btn-outlined" type="button" disabled>
              Re-synthesize Voice
            </button>
          </div>

          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <button id="undoBtn" class="m3-btn m3-btn-outlined" type="button" disabled>Undo Last Batch</button>
            <button id="appendBtn" class="m3-btn m3-btn-tonal" type="button" disabled>Append to Lecture</button>
            <button id="replaceBtn" class="m3-btn m3-btn-primary" type="button" disabled>Replace &amp; Generate Audio</button>
          </div>
        </div>

        <!-- E-14 Live Synthesis Progress -->
        <div id="genProgressBox" class="field-group hidden-el" aria-live="polite" style="gap:6px;">
          <span id="genProgressText" class="field-label mono-num">Synthesizing 0 / 0 clips...</span>
          <div class="linear-track">
            <div id="genProgressFill" class="linear-fill"></div>
          </div>
        </div>

        <!-- E-15 Inline Alert Banner -->
        <div id="drawerAlert" class="alert-banner alert-error hidden-el" role="alert">
          <span id="drawerAlertText"></span>
          <button id="dismissAlertBtn" class="m3-icon-btn" type="button" aria-label="Dismiss message">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>
    </section>

    <!-- E-16..E-19 Sticky Playback Bar -->
    <nav class="playback-bar" aria-label="Lecture playback controls">
      <div class="transport-cluster">
        <button id="prevLineBtn" class="m3-icon-btn" type="button" title="Previous line (Left Arrow)" aria-label="Previous line" disabled>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/>
          </svg>
        </button>
        <button id="playPauseBtn" class="play-pill" type="button" data-playing="false" disabled>
          <svg id="playIcon" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <polygon points="6 4 20 12 6 20 6 4"/>
          </svg>
          <svg id="pauseIcon" class="hidden-el" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
          </svg>
          <span id="playPauseLabel">Play</span>
        </button>
        <button id="nextLineBtn" class="m3-icon-btn" type="button" title="Next line (Right Arrow)" aria-label="Next line" disabled>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/>
          </svg>
        </button>
        <button id="repeatLineBtn" class="m3-icon-btn" type="button" title="Repeat current line (R)" aria-label="Repeat current line" disabled>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
          </svg>
        </button>
      </div>

      <div id="speedGroup" class="speed-group" role="group" aria-label="Playback speed">
        <button class="speed-pill" type="button" data-rate="1" aria-pressed="true">1x</button>
        <button class="speed-pill" type="button" data-rate="1.25" aria-pressed="false">1.25x</button>
        <button class="speed-pill" type="button" data-rate="1.5" aria-pressed="false">1.5x</button>
        <button class="speed-pill" type="button" data-rate="1.75" aria-pressed="false">1.75x</button>
        <button class="speed-pill" type="button" data-rate="2" aria-pressed="false">2x</button>
      </div>

      <div class="scrubber-wrap">
        <input id="lineScrubber" class="m3-slider" type="range" min="0" max="0" value="0" aria-label="Line progress scrubber" disabled>
        <span id="playbackReadout" class="field-label mono-num" style="white-space:nowrap;">Line 0 / 0 · Page — / —</span>
      </div>

      <button id="autoScrollBtn" class="filter-chip" type="button" aria-pressed="true">
        Auto-Scroll: ON
      </button>
    </nav>

    <!-- E-23 Compact/Medium Mobile Pane Switcher -->
    <div id="mobileTabs" class="mobile-tabs" role="tablist" aria-label="Workspace panes">
      <button id="tabPdfBtn" class="mobile-tab-btn" type="button" role="tab" aria-selected="true">PDF Viewer</button>
      <button id="tabDialogueBtn" class="mobile-tab-btn" type="button" role="tab" aria-selected="false">Dialogue &amp; Notes</button>
    </div>

    <!-- Main Supporting-Pane Split View -->
    <main class="workspace-grid">
      <!-- E-20 Primary Pane (68%) -->
      <section id="pdfPane" class="pdf-pane" aria-label="Synced PDF viewer" data-mobile-hidden="false">
        <div class="pdf-toolbar">
          <div style="display:flex; align-items:center; gap:6px;">
            <button id="zoomOutBtn" class="m3-icon-btn" type="button" title="Zoom out" aria-label="Zoom out">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true">
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>
            <span id="zoomLabel" class="field-label mono-num" style="min-width:48px; text-align:center;">100%</span>
            <button id="zoomInBtn" class="m3-icon-btn" type="button" title="Zoom in" aria-label="Zoom in">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>
            <button id="zoomFitBtn" class="m3-btn m3-btn-outlined" type="button" style="min-height:32px; padding:0 12px; font-size:0.76rem;">Fit Width</button>
          </div>
          <span id="pdfPageReadout" class="field-label mono-num">No document</span>
        </div>

        <div id="pdfScroll" class="pdf-scroll">
          <div id="pdfEmptyState" class="empty-state-card">
            <h2 style="margin:0; font-family:var(--md-sys-typescale-display); font-size:1.15rem;">Upload an Exam Chapter PDF</h2>
            <p style="margin:0; font-size:0.9rem; color:var(--md-sys-color-on-surface-variant); line-height:1.55;">
              DeepExamCast extracts normalized paragraphs, builds zero-skimming Gemini prompts, and syncs neural two-host audio directly to every paragraph.
            </p>
            <div>
              <button id="emptyUploadCta" class="m3-btn m3-btn-primary" type="button">Choose PDF File</button>
            </div>
          </div>
          <div id="pdfPagesContainer" class="hidden-el" style="display:flex; flex-direction:column; align-items:center; gap:18px; width:100%;"></div>
        </div>
      </section>

      <!-- E-21 Supporting Pane (32%) -->
      <aside id="dialoguePane" class="dialogue-pane" aria-label="Live dialogue and exam notes" data-mobile-hidden="true">
        <div class="dialogue-header">
          <span style="font-family:var(--md-sys-typescale-display); font-size:0.9rem; font-weight:600;">Dialogue &amp; Exam Notes</span>
          <span id="dialogueMeta" class="field-label mono-num">0 turns</span>
        </div>
        <div id="dialogueScroll" class="dialogue-scroll">
          <div id="dialogueEmptyState" class="empty-state-card">
            <h3 style="margin:0; font-family:var(--md-sys-typescale-display); font-size:1rem;">3-Step Study Workflow</h3>
            <p style="margin:0; font-size:0.86rem; color:var(--md-sys-color-on-surface-variant); line-height:1.55;">
              1. Upload your chapter PDF.
            </p>
            <p style="margin:0; font-size:0.86rem; color:var(--md-sys-color-on-surface-variant); line-height:1.55;">
              2. Copy the 5-page prompt into Gemini Web.
            </p>
            <p style="margin:0; font-size:0.86rem; color:var(--md-sys-color-on-surface-variant); line-height:1.55;">
              3. Paste Gemini's JSON array and generate cached neural audio.
            </p>
          </div>
          <div id="dialogueList" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>
      </aside>
    </main>

    <!-- E-22 Snackbar Stack -->
    <div id="snackbarStack" class="snackbar-stack" aria-live="polite"></div>
  </div>

  <script type="module" data-m3-app>
    const CDN_PDF_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs";
    const CDN_WORKER_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs";
    const LOCAL_PDF_URL = "/static/vendor/pdf.min.mjs";
    const LOCAL_WORKER_URL = "/static/vendor/pdf.worker.min.mjs";

    const state = {
      sessions: [],
      voicePairs: [],
      currentSession: null,
      coverage: null,
      chunkFirstLine: new Map(),
      currentLineIndex: 0,
      lastKnownPage: null,
      isPlaying: false,
      playbackRate: 1.0,
      autoScroll: true,
      playbackToken: 0,
      decksUnlocked: false,
      drawerOpen: false,
      lastCopiedRange: null,
      zoomScale: 1.0,
      pdfDoc: null,
      pageSlots: [],
      visiblePages: new Set(),
      observer: null,
      generating: false,
      patchTimer: null,
      statusTimer: null,
      activeTab: "pdf",
    };

    const deckA = new Audio();
    const deckB = new Audio();
    deckA.preload = "auto";
    deckB.preload = "auto";
    let activeDeck = deckA;
    let standbyDeck = deckB;
    let breathTimer = null;
    let pdfjsLibPromise = null;

    const el = {
      sessionSelect: document.getElementById("sessionSelect"),
      deleteSessionBtn: document.getElementById("deleteSessionBtn"),
      pdfInput: document.getElementById("pdfInput"),
      uploadBtn: document.getElementById("uploadBtn"),
      uploadBtnLabel: document.getElementById("uploadBtnLabel"),
      emptyUploadCta: document.getElementById("emptyUploadCta"),
      drawerToggleBtn: document.getElementById("drawerToggleBtn"),
      scriptSheetScrim: document.getElementById("scriptSheetScrim"),
      scriptSheet: document.getElementById("scriptSheet"),
      closeSheetBtn: document.getElementById("closeSheetBtn"),
      fromPageInput: document.getElementById("fromPageInput"),
      toPageInput: document.getElementById("toPageInput"),
      copyPromptBtn: document.getElementById("copyPromptBtn"),
      coverageSummary: document.getElementById("coverageSummary"),
      partialSummary: document.getElementById("partialSummary"),
      coverageBarFill: document.getElementById("coverageBarFill"),
      jsonInput: document.getElementById("jsonInput"),
      voicePairSelect: document.getElementById("voicePairSelect"),
      resynthesizeBtn: document.getElementById("resynthesizeBtn"),
      undoBtn: document.getElementById("undoBtn"),
      appendBtn: document.getElementById("appendBtn"),
      replaceBtn: document.getElementById("replaceBtn"),
      genProgressBox: document.getElementById("genProgressBox"),
      genProgressText: document.getElementById("genProgressText"),
      genProgressFill: document.getElementById("genProgressFill"),
      drawerAlert: document.getElementById("drawerAlert"),
      drawerAlertText: document.getElementById("drawerAlertText"),
      dismissAlertBtn: document.getElementById("dismissAlertBtn"),
      prevLineBtn: document.getElementById("prevLineBtn"),
      playPauseBtn: document.getElementById("playPauseBtn"),
      playIcon: document.getElementById("playIcon"),
      pauseIcon: document.getElementById("pauseIcon"),
      playPauseLabel: document.getElementById("playPauseLabel"),
      nextLineBtn: document.getElementById("nextLineBtn"),
      repeatLineBtn: document.getElementById("repeatLineBtn"),
      speedGroup: document.getElementById("speedGroup"),
      lineScrubber: document.getElementById("lineScrubber"),
      playbackReadout: document.getElementById("playbackReadout"),
      autoScrollBtn: document.getElementById("autoScrollBtn"),
      mobileTabs: document.getElementById("mobileTabs"),
      tabPdfBtn: document.getElementById("tabPdfBtn"),
      tabDialogueBtn: document.getElementById("tabDialogueBtn"),
      pdfPane: document.getElementById("pdfPane"),
      dialoguePane: document.getElementById("dialoguePane"),
      zoomOutBtn: document.getElementById("zoomOutBtn"),
      zoomLabel: document.getElementById("zoomLabel"),
      zoomInBtn: document.getElementById("zoomInBtn"),
      zoomFitBtn: document.getElementById("zoomFitBtn"),
      pdfPageReadout: document.getElementById("pdfPageReadout"),
      pdfScroll: document.getElementById("pdfScroll"),
      pdfEmptyState: document.getElementById("pdfEmptyState"),
      pdfPagesContainer: document.getElementById("pdfPagesContainer"),
      dialogueMeta: document.getElementById("dialogueMeta"),
      dialogueScroll: document.getElementById("dialogueScroll"),
      dialogueEmptyState: document.getElementById("dialogueEmptyState"),
      dialogueList: document.getElementById("dialogueList"),
      snackbarStack: document.getElementById("snackbarStack"),
    };

    async function loadPdfJs() {
      if (pdfjsLibPromise) return pdfjsLibPromise;
      pdfjsLibPromise = (async () => {
        try {
          const probe = await fetch(LOCAL_PDF_URL, { method: "HEAD" });
          if (probe.ok) {
            const lib = await import(LOCAL_PDF_URL);
            lib.GlobalWorkerOptions.workerSrc = LOCAL_WORKER_URL;
            return lib;
          }
        } catch (_err) {
          // Local vendor files not present; fall back to CDN
        }
        const lib = await import(CDN_PDF_URL);
        const blob = new Blob([`import "${CDN_WORKER_URL}";`], { type: "text/javascript" });
        lib.GlobalWorkerOptions.workerSrc = URL.createObjectURL(blob);
        return lib;
      })();
      return pdfjsLibPromise;
    }

    function showSnackbar(message, { actions = [], durationMs = 3600 } = {}) {
      const bar = document.createElement("div");
      bar.className = "snackbar";
      const msgSpan = document.createElement("span");
      msgSpan.textContent = message;
      bar.appendChild(msgSpan);

      const actionWrap = document.createElement("div");
      actionWrap.style.display = "flex";
      actionWrap.style.gap = "4px";
      for (const act of actions) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "snackbar-action";
        btn.textContent = act.label;
        btn.addEventListener("click", () => {
          dismiss();
          act.onClick();
        });
        actionWrap.appendChild(btn);
      }
      if (actions.length) {
        bar.appendChild(actionWrap);
      }
      el.snackbarStack.appendChild(bar);
      requestAnimationFrame(() => bar.classList.add("visible"));

      let timerId = null;
      let remaining = durationMs;
      let startedAt = Date.now();

      function dismiss() {
        document.removeEventListener("visibilitychange", onVisibility);
        if (timerId) clearTimeout(timerId);
        bar.classList.remove("visible");
        setTimeout(() => bar.remove(), 180);
      }

      function schedule(ms) {
        if (ms <= 0) return;
        startedAt = Date.now();
        timerId = setTimeout(dismiss, ms);
      }

      function onVisibility() {
        if (durationMs <= 0) return;
        if (document.hidden) {
          remaining = Math.max(0, remaining - (Date.now() - startedAt));
          if (timerId) clearTimeout(timerId);
          timerId = null;
        } else if (remaining > 0) {
          schedule(remaining);
        }
      }

      if (durationMs > 0) {
        document.addEventListener("visibilitychange", onVisibility);
        if (!document.hidden) schedule(remaining);
      }
    }

    function showDrawerAlert(message, kind = "error") {
      el.drawerAlertText.textContent = message;
      el.drawerAlert.className = `alert-banner ${kind === "warning" ? "alert-warning" : "alert-error"}`;
    }

    function hideDrawerAlert() {
      el.drawerAlert.className = "alert-banner alert-error hidden-el";
      el.drawerAlertText.textContent = "";
    }

    function setDrawerOpen(open) {
      state.drawerOpen = open;
      el.drawerToggleBtn.setAttribute("aria-expanded", String(open));
      el.scriptSheet.setAttribute("aria-hidden", String(!open));
      el.scriptSheetScrim.setAttribute("aria-hidden", String(!open));
      el.scriptSheet.classList.toggle("open", open);
      el.scriptSheetScrim.classList.toggle("open", open);
    }

    function formatMinutes(sec) {
      if (!sec || sec <= 0) return "";
      const mins = Math.max(1, Math.round(sec / 60));
      return `~${mins}m`;
    }

    async function apiJson(url, options = {}) {
      const resp = await fetch(url, options);
      let data = null;
      try {
        data = await resp.json();
      } catch (_err) {
        data = null;
      }
      if (!resp.ok) {
        const msg = (data && data.detail) ? data.detail : `Request failed (${resp.status})`;
        const err = new Error(msg);
        err.status = resp.status;
        throw err;
      }
      return data;
    }

    function populateVoicePairs(pairs, selectedId) {
      state.voicePairs = pairs || state.voicePairs;
      el.voicePairSelect.textContent = "";
      for (const vp of state.voicePairs) {
        const opt = document.createElement("option");
        opt.value = vp.id;
        opt.textContent = vp.label;
        el.voicePairSelect.appendChild(opt);
      }
      if (selectedId && state.voicePairs.some((v) => v.id === selectedId)) {
        el.voicePairSelect.value = selectedId;
      }
    }

    function getSelectedVoices() {
      const vp = state.voicePairs.find((p) => p.id === el.voicePairSelect.value) || state.voicePairs[0];
      if (!vp) {
        return {
          host_a_voice: "en-US-AndrewMultilingualNeural",
          host_b_voice: "en-US-AvaMultilingualNeural",
        };
      }
      return { host_a_voice: vp.host_a_voice, host_b_voice: vp.host_b_voice };
    }

    function populateSessionSelect(activeId) {
      el.sessionSelect.textContent = "";
      if (!state.sessions.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "No saved chapters yet";
        el.sessionSelect.appendChild(opt);
        el.deleteSessionBtn.disabled = true;
        return;
      }
      for (const s of state.sessions) {
        const opt = document.createElement("option");
        opt.value = s.session_id;
        const dur = formatMinutes(s.estimated_total_sec);
        const durPart = dur ? ` · ${dur}` : "";
        opt.textContent = `${s.title} — ${s.fully_covered_page_count}/${s.page_count} full pgs${durPart}`;
        el.sessionSelect.appendChild(opt);
      }
      if (activeId) {
        el.sessionSelect.value = activeId;
      }
      el.deleteSessionBtn.disabled = !el.sessionSelect.value;
    }

    function updateCoverageUi() {
      const session = state.currentSession;
      const cov = state.coverage;
      if (!session || !cov) {
        el.coverageSummary.textContent = "No PDF loaded";
        el.partialSummary.textContent = "";
        el.coverageBarFill.style.transform = "scaleX(0)";
        return;
      }
      const ratio = cov.total_chunks > 0 ? cov.covered_chunk_count / cov.total_chunks : 0;
      el.coverageBarFill.style.transform = `scaleX(${Math.max(0, Math.min(1, ratio))})`;
      el.coverageSummary.textContent =
        `Covered: ${cov.covered_chunk_count}/${cov.total_chunks} chunks · ${cov.fully_covered_pages.length}/${session.page_count} full pages`;
      if (cov.partial_pages.length > 0) {
        const preview = cov.partial_pages
          .slice(0, 3)
          .map((p) => `Pg ${p.page} (${p.covered_chunks}/${p.total_chunks})`)
          .join(", ");
        el.partialSummary.textContent = `Partial: ${preview}`;
      } else {
        el.partialSummary.textContent = "";
      }

      el.fromPageInput.max = String(Math.max(1, session.page_count));
      el.toPageInput.max = String(Math.max(1, session.page_count));
      el.fromPageInput.value = String(cov.suggested_next_range.start_page);
      el.toPageInput.value = String(cov.suggested_next_range.end_page);
    }

    function buildChunkMap(session) {
      state.chunkFirstLine.clear();
      if (!session) return;
      for (const line of session.script) {
        for (const cid of line.chunk_ids) {
          if (!state.chunkFirstLine.has(cid)) {
            state.chunkFirstLine.set(cid, line.index);
          }
        }
      }
    }

    function updateActionButtons() {
      const hasSession = Boolean(state.currentSession);
      const scriptLen = hasSession ? state.currentSession.script.length : 0;
      const batchLen = hasSession ? state.currentSession.batches.length : 0;
      const busy = state.generating;

      el.copyPromptBtn.disabled = !hasSession || busy;
      el.appendBtn.disabled = !hasSession || busy;
      el.replaceBtn.disabled = !hasSession || busy;
      el.resynthesizeBtn.disabled = !hasSession || scriptLen === 0 || busy;
      el.undoBtn.disabled = !hasSession || batchLen === 0 || busy;
      el.deleteSessionBtn.disabled = !hasSession || busy;

      const hasAudio = scriptLen > 0;
      el.playPauseBtn.disabled = !hasAudio;
      el.prevLineBtn.disabled = !hasAudio;
      el.nextLineBtn.disabled = !hasAudio;
      el.repeatLineBtn.disabled = !hasAudio;
      el.lineScrubber.disabled = !hasAudio;
      el.lineScrubber.max = String(Math.max(0, scriptLen - 1));
    }

    function renderDialogueList() {
      const session = state.currentSession;
      el.dialogueList.textContent = "";
      if (!session || session.script.length === 0) {
        el.dialogueEmptyState.classList.remove("hidden-el");
        el.dialogueMeta.textContent = "0 turns";
        return;
      }
      el.dialogueEmptyState.classList.add("hidden-el");
      const dur = formatMinutes(state.coverage ? state.coverage.estimated_total_sec : 0);
      el.dialogueMeta.textContent = `${session.script.length} turns${dur ? ` · ${dur}` : ""}`;

      const chunkPageMap = new Map(session.chunks.map((c) => [c.id, c.page]));
      const frag = document.createDocumentFragment();

      for (const line of session.script) {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "dialogue-card";
        card.dataset.lineIndex = String(line.index);
        card.dataset.active = String(line.index === state.currentLineIndex);

        const meta = document.createElement("div");
        meta.className = "dialogue-card-meta";

        const badge = document.createElement("span");
        badge.className = `speaker-pill ${line.speaker === "HOST_A" ? "speaker-prof" : "speaker-student"}`;
        badge.textContent = line.speaker === "HOST_A" ? "Professor" : "Student";
        meta.appendChild(badge);

        const refTag = document.createElement("span");
        refTag.className = "field-label mono-num";
        const firstCid = line.chunk_ids[0];
        const pg = firstCid ? chunkPageMap.get(firstCid) : null;
        if (pg && line.chunk_ids.length) {
          refTag.textContent = `Pg ${pg} · ${line.chunk_ids.join(", ")}`;
        } else {
          refTag.textContent = `Turn ${line.index + 1}`;
        }
        meta.appendChild(refTag);
        card.appendChild(meta);

        const body = document.createElement("p");
        body.className = "dialogue-body";
        body.textContent = line.text;
        card.appendChild(body);

        if (line.exam_note) {
          const note = document.createElement("div");
          note.className = "exam-note-box";
          note.textContent = `Exam Note: ${line.exam_note}`;
          card.appendChild(note);
        }

        card.addEventListener("click", () => {
          jumpToLine(line.index, { autoplay: true, instant: false });
        });
        frag.appendChild(card);
      }

      el.dialogueList.appendChild(frag);
    }

    function applyRateToBoth(rate) {
      state.playbackRate = rate;
      deckA.defaultPlaybackRate = rate;
      deckA.playbackRate = rate;
      deckB.defaultPlaybackRate = rate;
      deckB.playbackRate = rate;
      for (const btn of el.speedGroup.querySelectorAll(".speed-pill")) {
        btn.setAttribute("aria-pressed", String(Number(btn.dataset.rate) === rate));
      }
      updatePlaybackReadout();
    }

    function updateAutoScrollUi() {
      el.autoScrollBtn.setAttribute("aria-pressed", String(state.autoScroll));
      el.autoScrollBtn.textContent = state.autoScroll ? "Auto-Scroll: ON" : "Auto-Scroll: OFF";
    }

    function updatePlayPauseUi() {
      el.playPauseBtn.dataset.playing = String(state.isPlaying);
      el.playIcon.classList.toggle("hidden-el", state.isPlaying);
      el.pauseIcon.classList.toggle("hidden-el", !state.isPlaying);
      el.playPauseLabel.textContent = state.isPlaying ? "Pause" : "Play";
    }

    function updatePlaybackReadout() {
      const session = state.currentSession;
      if (!session || session.script.length === 0) {
        el.playbackReadout.textContent = session
          ? `Line 0 / 0 · Page — / ${session.page_count}`
          : "Line 0 / 0 · Page — / —";
        el.lineScrubber.value = "0";
        return;
      }

      const idx = Math.max(0, Math.min(state.currentLineIndex, session.script.length - 1));
      const line = session.script[idx];
      const chunkMap = new Map(session.chunks.map((c) => [c.id, c.page]));
      for (const cid of line.chunk_ids) {
        const p = chunkMap.get(cid);
        if (p) {
          state.lastKnownPage = p;
          break;
        }
      }

      const pgLabel = state.lastKnownPage ? String(state.lastKnownPage) : "—";
      const remSec = session.script
        .slice(idx)
        .reduce((acc, item) => acc + (item.duration_sec || 0), 0) / state.playbackRate;
      const remPart = remSec > 0 ? ` · ~${Math.max(1, Math.round(remSec / 60))}m left` : "";
      el.playbackReadout.textContent =
        `Line ${idx + 1} / ${session.script.length} · Page ${pgLabel} / ${session.page_count}${remPart}`;
      el.lineScrubber.value = String(idx);
    }

    function syncVisualLine(index, { scroll = true } = {}) {
      const session = state.currentSession;
      if (!session || !session.script.length) return;
      const line = session.script[index];
      const activeSet = new Set(line ? line.chunk_ids : []);

      for (const card of el.dialogueList.querySelectorAll(".dialogue-card")) {
        const isCurrent = Number(card.dataset.lineIndex) === index;
        card.dataset.active = String(isCurrent);
        if (isCurrent && scroll) {
          card.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }

      let firstActiveBox = null;
      for (const box of el.pdfPagesContainer.querySelectorAll(".chunk-box")) {
        const cid = box.dataset.chunkId;
        const isActive = activeSet.has(cid);
        box.dataset.active = String(isActive);
        if (isActive && !firstActiveBox) {
          firstActiveBox = box;
        }
      }

      if (scroll && state.autoScroll && firstActiveBox && activeSet.size > 0) {
        firstActiveBox.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      updatePlaybackReadout();
    }

    function scheduleStatePatch() {
      const session = state.currentSession;
      if (!session) return;
      if (state.patchTimer) clearTimeout(state.patchTimer);
      const sid = session.session_id;
      const payload = {
        last_line_index: state.currentLineIndex,
        playback_rate: state.playbackRate,
        auto_scroll: state.autoScroll,
      };
      state.patchTimer = setTimeout(() => {
        fetch(`/api/sessions/${encodeURIComponent(sid)}/state`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }).catch(() => {});
      }, 450);
    }

    function audioUrlFor(session, line) {
      return `/api/sessions/${encodeURIComponent(session.session_id)}/audio/${encodeURIComponent(line.audio_file)}`;
    }

    function unlockDecksOnGesture() {
      if (state.decksUnlocked) return;
      state.decksUnlocked = true;
      standbyDeck.muted = true;
      const p = standbyDeck.play();
      if (p && typeof p.then === "function") {
        p.then(() => {
          standbyDeck.pause();
          standbyDeck.currentTime = 0;
          standbyDeck.muted = false;
        }).catch(() => {
          standbyDeck.muted = false;
        });
      } else {
        standbyDeck.muted = false;
      }
    }

    function preloadNextLine(index) {
      const session = state.currentSession;
      if (!session || index + 1 >= session.script.length) {
        standbyDeck.removeAttribute("src");
        delete standbyDeck.dataset.preloadedUrl;
        return;
      }
      const nextUrl = audioUrlFor(session, session.script[index + 1]);
      if (standbyDeck.dataset.preloadedUrl !== nextUrl) {
        standbyDeck.src = nextUrl;
        standbyDeck.dataset.preloadedUrl = nextUrl;
        standbyDeck.defaultPlaybackRate = state.playbackRate;
        standbyDeck.playbackRate = state.playbackRate;
        standbyDeck.load();
      }
    }

    function jumpToLine(index, { autoplay = true, instant = false } = {}) {
      const session = state.currentSession;
      if (!session || !session.script.length) return;
      const clamped = Math.max(0, Math.min(index, session.script.length - 1));
      const token = ++state.playbackToken;
      if (breathTimer) {
        clearTimeout(breathTimer);
        breathTimer = null;
      }

      if (instant) {
        el.playPauseBtn.dataset.instant = "true";
        setTimeout(() => delete el.playPauseBtn.dataset.instant, 0);
      }

      state.currentLineIndex = clamped;
      syncVisualLine(clamped, { scroll: true });
      scheduleStatePatch();

      const line = session.script[clamped];
      const url = audioUrlFor(session, line);

      activeDeck.pause();
      standbyDeck.pause();

      if (!autoplay) {
        state.isPlaying = false;
        updatePlayPauseUi();
        if (activeDeck.dataset.loadedUrl !== url) {
          activeDeck.src = url;
          activeDeck.dataset.loadedUrl = url;
          activeDeck.defaultPlaybackRate = state.playbackRate;
          activeDeck.playbackRate = state.playbackRate;
          activeDeck.load();
        } else {
          activeDeck.currentTime = 0;
        }
        preloadNextLine(clamped);
        return;
      }

      unlockDecksOnGesture();
      state.isPlaying = true;
      updatePlayPauseUi();

      if (standbyDeck.dataset.preloadedUrl === url && standbyDeck.readyState >= 2) {
        const oldActive = activeDeck;
        activeDeck = standbyDeck;
        standbyDeck = oldActive;
        activeDeck.dataset.loadedUrl = url;
      } else if (activeDeck.dataset.loadedUrl !== url) {
        activeDeck.src = url;
        activeDeck.dataset.loadedUrl = url;
        activeDeck.defaultPlaybackRate = state.playbackRate;
        activeDeck.playbackRate = state.playbackRate;
        activeDeck.load();
      }

      activeDeck.currentTime = 0;
      activeDeck.defaultPlaybackRate = state.playbackRate;
      activeDeck.playbackRate = state.playbackRate;
      activeDeck.play().catch(() => {
        if (token === state.playbackToken) {
          state.isPlaying = false;
          updatePlayPauseUi();
        }
      });
      preloadNextLine(clamped);
    }

    function togglePlayPause({ instant = false } = {}) {
      const session = state.currentSession;
      if (!session || !session.script.length) return;
      if (instant) {
        el.playPauseBtn.dataset.instant = "true";
        setTimeout(() => delete el.playPauseBtn.dataset.instant, 0);
      }

      if (state.isPlaying) {
        state.playbackToken += 1;
        if (breathTimer) {
          clearTimeout(breathTimer);
          breathTimer = null;
        }
        activeDeck.pause();
        state.isPlaying = false;
        updatePlayPauseUi();
        scheduleStatePatch();
        return;
      }

      unlockDecksOnGesture();
      const line = session.script[state.currentLineIndex];
      const url = audioUrlFor(session, line);
      if (activeDeck.dataset.loadedUrl !== url) {
        jumpToLine(state.currentLineIndex, { autoplay: true, instant });
        return;
      }
      state.isPlaying = true;
      updatePlayPauseUi();
      activeDeck.playbackRate = state.playbackRate;
      activeDeck.play().catch(() => {
        state.isPlaying = false;
        updatePlayPauseUi();
      });
      preloadNextLine(state.currentLineIndex);
    }

    function repeatCurrentLine({ instant = false } = {}) {
      const session = state.currentSession;
      if (!session || !session.script.length) return;
      jumpToLine(state.currentLineIndex, { autoplay: true, instant });
    }

    function bindDeckEvents(deck) {
      deck.addEventListener("loadedmetadata", () => {
        deck.defaultPlaybackRate = state.playbackRate;
        deck.playbackRate = state.playbackRate;
      });
      deck.addEventListener("ended", () => {
        if (deck !== activeDeck || !state.isPlaying) return;
        const session = state.currentSession;
        if (!session) return;
        const token = state.playbackToken;
        if (state.currentLineIndex + 1 < session.script.length) {
          breathTimer = setTimeout(() => {
            if (token === state.playbackToken && state.isPlaying) {
              jumpToLine(state.currentLineIndex + 1, { autoplay: true, instant: false });
            }
          }, 200);
        } else {
          state.isPlaying = false;
          updatePlayPauseUi();
        }
      });
      deck.addEventListener("error", () => {
        if (deck !== activeDeck || !deck.getAttribute("src")) return;
        state.isPlaying = false;
        updatePlayPauseUi();
        const session = state.currentSession;
        const hasNext = session && state.currentLineIndex + 1 < session.script.length;
        const actions = [
          {
            label: "Retry Line",
            onClick: () => jumpToLine(state.currentLineIndex, { autoplay: true }),
          },
        ];
        if (hasNext) {
          actions.push({
            label: "Skip",
            onClick: () => jumpToLine(state.currentLineIndex + 1, { autoplay: true }),
          });
        }
        showSnackbar(`Audio clip failed on line ${state.currentLineIndex + 1}.`, {
          actions,
          durationMs: 0,
        });
      });
    }

    bindDeckEvents(deckA);
    bindDeckEvents(deckB);

    function cancelAndClearPdf() {
      if (state.observer) {
        state.observer.disconnect();
        state.observer = null;
      }
      for (const slot of state.pageSlots) {
        if (slot.renderTask) {
          try {
            slot.renderTask.cancel();
          } catch (_err) {}
          slot.renderTask = null;
        }
      }
      state.pageSlots = [];
      state.visiblePages.clear();
      state.pdfDoc = null;
      el.pdfPagesContainer.textContent = "";
    }

    function sizePageSlot(slot) {
      const w = Math.round(slot.baseWidth * state.zoomScale);
      const h = Math.round(slot.baseHeight * state.zoomScale);
      slot.frameEl.style.width = `${w}px`;
      slot.frameEl.style.height = `${h}px`;
    }

    async function renderPageSlot(slot) {
      if (!state.pdfDoc) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const targetScaleKey = `${state.zoomScale.toFixed(3)}@${dpr}`;
      if (slot.renderedScale === targetScaleKey && slot.canvasEl.width > 0) return;

      if (slot.renderTask) {
        try {
          slot.renderTask.cancel();
        } catch (_err) {}
        slot.renderTask = null;
      }

      const viewport = slot.pageProxy.getViewport({ scale: state.zoomScale * dpr });
      slot.canvasEl.width = Math.max(1, Math.floor(viewport.width));
      slot.canvasEl.height = Math.max(1, Math.floor(viewport.height));
      const ctx = slot.canvasEl.getContext("2d", { alpha: false });
      const task = slot.pageProxy.render({ canvasContext: ctx, viewport });
      slot.renderTask = task;

      try {
        await task.promise;
        if (slot.renderTask === task) {
          slot.renderedScale = targetScaleKey;
          slot.renderTask = null;
        }
      } catch (err) {
        if (err && err.name !== "RenderingCancelledException") {
          slot.renderedScale = null;
        }
      }
    }

    function evictPageSlot(slot) {
      if (slot.renderTask) {
        try {
          slot.renderTask.cancel();
        } catch (_err) {}
        slot.renderTask = null;
      }
      if (slot.canvasEl.width > 0) {
        slot.canvasEl.width = 0;
        slot.canvasEl.height = 0;
      }
      slot.renderedScale = null;
    }

    function refreshPdfRenderWindow() {
      if (!state.pageSlots.length) return;
      const visible = Array.from(state.visiblePages);
      const minVis = visible.length ? Math.min(...visible) : 1;
      const maxVis = visible.length ? Math.max(...visible) : 1;
      el.pdfPageReadout.textContent = `Page ${minVis} / ${state.pageSlots.length}`;

      const renderLo = Math.max(1, minVis - 4);
      const renderHi = Math.min(state.pageSlots.length, maxVis + 4);
      const evictLo = minVis - 8;
      const evictHi = maxVis + 8;

      for (const slot of state.pageSlots) {
        if (slot.pageNum >= renderLo && slot.pageNum <= renderHi) {
          renderPageSlot(slot);
        } else if (slot.pageNum < evictLo || slot.pageNum > evictHi) {
          evictPageSlot(slot);
        }
      }
    }

    function refreshChunkOverlayStates() {
      const session = state.currentSession;
      const activeSet = new Set(
        session && session.script[state.currentLineIndex]
          ? session.script[state.currentLineIndex].chunk_ids
          : []
      );
      for (const box of el.pdfPagesContainer.querySelectorAll(".chunk-box")) {
        const cid = box.dataset.chunkId;
        const firstLine = state.chunkFirstLine.get(cid);
        const covered = firstLine !== undefined;
        box.dataset.covered = String(covered);
        box.dataset.active = String(activeSet.has(cid));
        box.title = covered
          ? `Chunk ${cid} — Click to jump to Turn ${firstLine + 1}`
          : `Chunk ${cid} — Not covered yet`;
      }
    }

    async function renderPdfForSession(session) {
      cancelAndClearPdf();
      if (!session) {
        el.pdfEmptyState.classList.remove("hidden-el");
        el.pdfPagesContainer.classList.add("hidden-el");
        el.pdfPageReadout.textContent = "No document";
        return;
      }

      el.pdfEmptyState.classList.add("hidden-el");
      el.pdfPagesContainer.classList.remove("hidden-el");
      el.pdfPageReadout.textContent = `Loading ${session.page_count} pages...`;

      let pdfjsLib;
      try {
        pdfjsLib = await loadPdfJs();
      } catch (_err) {
        showSnackbar("Could not load PDF.js viewer module.");
        return;
      }

      const task = pdfjsLib.getDocument({
        url: `/api/sessions/${encodeURIComponent(session.session_id)}/pdf`,
        isEvalSupported: false,
      });
      const pdfDoc = await task.promise;
      if (!state.currentSession || state.currentSession.session_id !== session.session_id) {
        return;
      }
      state.pdfDoc = pdfDoc;

      const chunksByPage = new Map();
      for (const ch of session.chunks) {
        if (!chunksByPage.has(ch.page)) chunksByPage.set(ch.page, []);
        chunksByPage.get(ch.page).push(ch);
      }

      const firstPage = await pdfDoc.getPage(1);
      const firstVp = firstPage.getViewport({ scale: 1.0 });
      const availableW = Math.max(320, el.pdfScroll.clientWidth - 48);
      state.zoomScale = Math.max(0.6, Math.min(2.0, Number((availableW / firstVp.width).toFixed(2))));
      el.zoomLabel.textContent = `${Math.round(state.zoomScale * 100)}%`;

      const frag = document.createDocumentFragment();
      for (let p = 1; p <= pdfDoc.numPages; p += 1) {
        const pageProxy = p === 1 ? firstPage : await pdfDoc.getPage(p);
        const vp = pageProxy.getViewport({ scale: 1.0 });

        const frameEl = document.createElement("div");
        frameEl.className = "pdf-page-frame";
        frameEl.dataset.pageNum = String(p);

        const canvasEl = document.createElement("canvas");
        canvasEl.className = "pdf-page-canvas";
        frameEl.appendChild(canvasEl);

        const overlayLayerEl = document.createElement("div");
        overlayLayerEl.className = "chunk-overlay-layer";
        for (const ch of chunksByPage.get(p) || []) {
          const [x0, y0, x1, y1] = ch.bbox;
          const box = document.createElement("div");
          box.className = "chunk-box";
          box.dataset.chunkId = ch.id;
          box.style.left = `${(x0 * 100).toFixed(3)}%`;
          box.style.top = `${(y0 * 100).toFixed(3)}%`;
          box.style.width = `${Math.max(0.5, (x1 - x0) * 100).toFixed(3)}%`;
          box.style.height = `${Math.max(0.5, (y1 - y0) * 100).toFixed(3)}%`;
          box.addEventListener("click", () => {
            const targetIdx = state.chunkFirstLine.get(ch.id);
            if (targetIdx !== undefined) {
              jumpToLine(targetIdx, { autoplay: true });
            } else {
              showSnackbar(`Chunk ${ch.id} is not covered in the current script yet.`);
            }
          });
          overlayLayerEl.appendChild(box);
        }
        frameEl.appendChild(overlayLayerEl);

        const slot = {
          pageNum: p,
          pageProxy,
          baseWidth: vp.width,
          baseHeight: vp.height,
          frameEl,
          canvasEl,
          overlayLayerEl,
          renderTask: null,
          renderedScale: null,
        };
        sizePageSlot(slot);
        state.pageSlots.push(slot);
        frag.appendChild(frameEl);
      }

      el.pdfPagesContainer.appendChild(frag);
      refreshChunkOverlayStates();

      state.observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            const p = Number(entry.target.dataset.pageNum);
            if (entry.isIntersecting) state.visiblePages.add(p);
            else state.visiblePages.delete(p);
          }
          refreshPdfRenderWindow();
        },
        { root: el.pdfScroll, rootMargin: "200px 0px" }
      );
      for (const slot of state.pageSlots) {
        state.observer.observe(slot.frameEl);
      }
      state.visiblePages.add(1);
      refreshPdfRenderWindow();
      syncVisualLine(state.currentLineIndex, { scroll: false });
    }

    function applyZoom(newScale) {
      if (!state.pageSlots.length) return;
      state.zoomScale = Math.max(0.5, Math.min(2.6, Number(newScale.toFixed(2))));
      el.zoomLabel.textContent = `${Math.round(state.zoomScale * 100)}%`;
      for (const slot of state.pageSlots) {
        if (slot.renderTask) {
          try {
            slot.renderTask.cancel();
          } catch (_err) {}
          slot.renderTask = null;
        }
        slot.renderedScale = null;
        sizePageSlot(slot);
      }
      refreshPdfRenderWindow();
    }

    function applySessionData(payload, { reloadPdf = true } = {}) {
      state.playbackToken += 1;
      activeDeck.pause();
      standbyDeck.pause();
      state.isPlaying = false;
      updatePlayPauseUi();

      state.currentSession = payload.session;
      state.coverage = payload.coverage;
      if (payload.voice_pairs) {
        populateVoicePairs(payload.voice_pairs, payload.session.state.voice_pair_id);
      } else {
        populateVoicePairs(state.voicePairs, payload.session.state.voice_pair_id);
      }

      state.currentLineIndex = payload.session.state.last_line_index || 0;
      state.autoScroll = payload.session.state.auto_scroll !== false;
      state.lastKnownPage = null;

      buildChunkMap(state.currentSession);
      applyRateToBoth(payload.session.state.playback_rate || 1.0);
      updateAutoScrollUi();
      updateCoverageUi();
      renderDialogueList();
      updateActionButtons();
      refreshChunkOverlayStates();

      if (state.currentSession.script.length > 0) {
        jumpToLine(state.currentLineIndex, { autoplay: false });
      } else {
        updatePlaybackReadout();
        setDrawerOpen(true);
      }

      if (reloadPdf) {
        renderPdfForSession(state.currentSession);
      }
    }

    async function refreshSessionList(selectedId = null) {
      const data = await apiJson("/api/sessions");
      state.sessions = data.sessions || [];
      populateSessionSelect(selectedId);
    }

    async function selectSession(sessionId) {
      if (!sessionId) {
        state.currentSession = null;
        state.coverage = null;
        cancelAndClearPdf();
        el.pdfEmptyState.classList.remove("hidden-el");
        el.pdfPagesContainer.classList.add("hidden-el");
        renderDialogueList();
        updateCoverageUi();
        updateActionButtons();
        updatePlaybackReadout();
        return;
      }
      const payload = await apiJson(`/api/sessions/${encodeURIComponent(sessionId)}`);
      applySessionData(payload, { reloadPdf: true });
      populateSessionSelect(sessionId);
    }

    async function handleUploadFile(file) {
      if (!file) return;
      hideDrawerAlert();
      el.uploadBtn.disabled = true;
      el.uploadBtnLabel.textContent = "Parsing PDF...";
      const fd = new FormData();
      fd.append("file", file);
      try {
        const payload = await apiJson("/api/upload", { method: "POST", body: fd });
        await refreshSessionList(payload.session.session_id);
        applySessionData(payload, { reloadPdf: true });
        if (payload.warnings && payload.warnings.length) {
          showDrawerAlert(payload.warnings.join(" "), "warning");
        }
        showSnackbar(`Loaded "${payload.session.title}" (${payload.session.page_count} pages).`);
      } catch (err) {
        showSnackbar(err.message);
      } finally {
        el.uploadBtn.disabled = false;
        el.uploadBtnLabel.textContent = "Upload PDF";
        el.pdfInput.value = "";
      }
    }

    async function handleCopyPrompt() {
      const session = state.currentSession;
      if (!session) return;
      hideDrawerAlert();
      const sp = Math.max(1, Number(el.fromPageInput.value || 1));
      const ep = Math.max(sp, Number(el.toPageInput.value || sp));
      try {
        const res = await apiJson(
          `/api/sessions/${encodeURIComponent(session.session_id)}/prompt?start_page=${sp}&end_page=${ep}`
        );
        state.lastCopiedRange = { start_page: res.start_page, end_page: res.end_page };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(res.prompt);
        } else {
          const tmp = document.createElement("textarea");
          tmp.value = res.prompt;
          document.body.appendChild(tmp);
          tmp.select();
          document.execCommand("copy");
          tmp.remove();
        }
        const [cStart, cEnd] = res.chunk_id_range;
        showSnackbar(`Copied! Pages ${res.start_page}–${res.end_page} (${cStart}–${cEnd}).`);
      } catch (err) {
        showDrawerAlert(err.message, "error");
      }
    }

    function startProgressPolling(sessionId, startedMs) {
      el.genProgressBox.classList.remove("hidden-el");
      el.genProgressFill.style.transform = "scaleX(0)";
      el.genProgressText.textContent = "Preparing audio synthesis...";
      state.statusTimer = setInterval(async () => {
        try {
          const prog = await apiJson(`/api/sessions/${encodeURIComponent(sessionId)}/generate/status`);
          const elapsed = Math.floor((Date.now() - startedMs) / 1000);
          const total = Math.max(1, prog.total || 1);
          const ratio = Math.min(1, (prog.completed || 0) / total);
          el.genProgressFill.style.transform = `scaleX(${ratio})`;
          el.genProgressText.textContent =
            `Synthesizing ${prog.completed} / ${prog.total} clips (${prog.cached} cached) · ${elapsed}s`;
        } catch (_err) {}
      }, 900);
    }

    function stopProgressPolling() {
      if (state.statusTimer) {
        clearInterval(state.statusTimer);
        state.statusTimer = null;
      }
      el.genProgressBox.classList.add("hidden-el");
    }

    async function handleGenerate(mode) {
      const session = state.currentSession;
      if (!session) return;
      hideDrawerAlert();

      if (mode === "replace" && session.script.length > 0) {
        const ok = window.confirm(
          "Replace existing lecture lines with this pasted script? (You can undo the last batch afterward.)"
        );
        if (!ok) return;
      }

      const rawJson = el.jsonInput.value.trim();
      if (!rawJson) {
        showDrawerAlert("Paste Gemini's JSON array before generating audio.", "error");
        return;
      }

      const voices = getSelectedVoices();
      const sp = state.lastCopiedRange ? state.lastCopiedRange.start_page : Number(el.fromPageInput.value || 0);
      const ep = state.lastCopiedRange ? state.lastCopiedRange.end_page : Number(el.toPageInput.value || 0);

      state.generating = true;
      updateActionButtons();
      startProgressPolling(session.session_id, Date.now());

      try {
        const payload = await apiJson(`/api/sessions/${encodeURIComponent(session.session_id)}/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            raw_json: rawJson,
            host_a_voice: voices.host_a_voice,
            host_b_voice: voices.host_b_voice,
            mode,
            start_page: sp > 0 ? sp : null,
            end_page: ep >= sp && sp > 0 ? ep : null,
          }),
        });
        el.jsonInput.value = "";
        state.lastCopiedRange = null;
        applySessionData(payload, { reloadPdf: false });
        await refreshSessionList(payload.session.session_id);
        if (payload.warnings && payload.warnings.length) {
          showDrawerAlert(payload.warnings.join(" "), "warning");
        } else {
          setDrawerOpen(false);
        }
        showSnackbar(
          `Ready! ${payload.stats.generated_count} new, ${payload.stats.cached_count} cached (${payload.stats.total_lines} lines).`
        );
      } catch (err) {
        showDrawerAlert(err.message, "error");
      } finally {
        stopProgressPolling();
        state.generating = false;
        updateActionButtons();
      }
    }

    async function handleResynthesize() {
      const session = state.currentSession;
      if (!session || !session.script.length) return;
      hideDrawerAlert();
      const voices = getSelectedVoices();
      state.generating = true;
      updateActionButtons();
      startProgressPolling(session.session_id, Date.now());
      try {
        const payload = await apiJson(`/api/sessions/${encodeURIComponent(session.session_id)}/resynthesize`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(voices),
        });
        applySessionData(payload, { reloadPdf: false });
        await refreshSessionList(payload.session.session_id);
        showSnackbar(`Voices updated (${payload.stats.generated_count} synthesized, ${payload.stats.cached_count} cached).`);
      } catch (err) {
        showDrawerAlert(err.message, "error");
      } finally {
        stopProgressPolling();
        state.generating = false;
        updateActionButtons();
      }
    }

    async function handleUndo() {
      const session = state.currentSession;
      if (!session) return;
      hideDrawerAlert();
      try {
        const payload = await apiJson(`/api/sessions/${encodeURIComponent(session.session_id)}/undo`, {
          method: "POST",
        });
        applySessionData(payload, { reloadPdf: false });
        await refreshSessionList(payload.session.session_id);
        showSnackbar(`Undid last batch (${payload.session.script.length} lines remaining).`);
      } catch (err) {
        showDrawerAlert(err.message, "error");
      }
    }

    async function handleDeleteSession() {
      const session = state.currentSession;
      if (!session) return;
      const ok = window.confirm(`Delete "${session.title}" and all cached audio clips from disk?`);
      if (!ok) return;
      try {
        await apiJson(`/api/sessions/${encodeURIComponent(session.session_id)}`, { method: "DELETE" });
        await refreshSessionList(null);
        const nextId = state.sessions.length ? state.sessions[0].session_id : null;
        await selectSession(nextId);
        showSnackbar("Session deleted.");
      } catch (err) {
        showSnackbar(err.message);
      }
    }

    function setMobileTab(tab) {
      state.activeTab = tab;
      const showPdf = tab === "pdf";
      el.tabPdfBtn.setAttribute("aria-selected", String(showPdf));
      el.tabDialogueBtn.setAttribute("aria-selected", String(!showPdf));
      el.pdfPane.dataset.mobileHidden = String(!showPdf);
      el.dialoguePane.dataset.mobileHidden = String(showPdf);
    }

    // Event Bindings
    el.sessionSelect.addEventListener("change", () => selectSession(el.sessionSelect.value));
    el.deleteSessionBtn.addEventListener("click", handleDeleteSession);
    el.uploadBtn.addEventListener("click", () => el.pdfInput.click());
    el.emptyUploadCta.addEventListener("click", () => el.pdfInput.click());
    el.pdfInput.addEventListener("change", () => handleUploadFile(el.pdfInput.files[0]));

    el.drawerToggleBtn.addEventListener("click", () => setDrawerOpen(!state.drawerOpen));
    el.closeSheetBtn.addEventListener("click", () => setDrawerOpen(false));
    el.scriptSheetScrim.addEventListener("click", () => setDrawerOpen(false));
    el.dismissAlertBtn.addEventListener("click", hideDrawerAlert);

    el.copyPromptBtn.addEventListener("click", handleCopyPrompt);
    el.appendBtn.addEventListener("click", () => handleGenerate("append"));
    el.replaceBtn.addEventListener("click", () => handleGenerate("replace"));
    el.undoBtn.addEventListener("click", handleUndo);
    el.resynthesizeBtn.addEventListener("click", handleResynthesize);

    el.playPauseBtn.addEventListener("click", () => togglePlayPause({ instant: false }));
    el.prevLineBtn.addEventListener("click", () => jumpToLine(state.currentLineIndex - 1, { autoplay: true }));
    el.nextLineBtn.addEventListener("click", () => jumpToLine(state.currentLineIndex + 1, { autoplay: true }));
    el.repeatLineBtn.addEventListener("click", () => repeatCurrentLine({ instant: false }));

    el.speedGroup.addEventListener("click", (evt) => {
      const pill = evt.target.closest(".speed-pill");
      if (!pill) return;
      applyRateToBoth(Number(pill.dataset.rate));
      scheduleStatePatch();
    });

    el.lineScrubber.addEventListener("input", () => {
      jumpToLine(Number(el.lineScrubber.value), { autoplay: state.isPlaying });
    });

    el.autoScrollBtn.addEventListener("click", () => {
      state.autoScroll = !state.autoScroll;
      updateAutoScrollUi();
      scheduleStatePatch();
    });

    el.zoomOutBtn.addEventListener("click", () => applyZoom(state.zoomScale - 0.15));
    el.zoomInBtn.addEventListener("click", () => applyZoom(state.zoomScale + 0.15));
    el.zoomFitBtn.addEventListener("click", () => {
      if (!state.pageSlots.length) return;
      const availableW = Math.max(320, el.pdfScroll.clientWidth - 48);
      applyZoom(availableW / state.pageSlots[0].baseWidth);
    });

    el.tabPdfBtn.addEventListener("click", () => setMobileTab("pdf"));
    el.tabDialogueBtn.addEventListener("click", () => setMobileTab("dialogue"));

    document.addEventListener("keydown", (evt) => {
      if (evt.ctrlKey || evt.altKey || evt.metaKey) return;
      const activeEl = document.activeElement;
      if (
        activeEl &&
        (["INPUT", "TEXTAREA", "SELECT"].includes(activeEl.tagName) || activeEl.isContentEditable)
      ) {
        if (evt.key === "Escape" && state.drawerOpen) setDrawerOpen(false);
        return;
      }
      if (evt.key === "Escape" && state.drawerOpen) {
        setDrawerOpen(false);
        return;
      }
      if (!state.currentSession || !state.currentSession.script.length) return;
      if (evt.code === "Space") {
        evt.preventDefault();
        togglePlayPause({ instant: true });
      } else if (evt.key === "ArrowLeft") {
        evt.preventDefault();
        jumpToLine(state.currentLineIndex - 1, { autoplay: true, instant: true });
      } else if (evt.key === "ArrowRight") {
        evt.preventDefault();
        jumpToLine(state.currentLineIndex + 1, { autoplay: true, instant: true });
      } else if (evt.key === "r" || evt.key === "R") {
        evt.preventDefault();
        repeatCurrentLine({ instant: true });
      }
    });

    async function bootstrap() {
      try {
        const voices = await apiJson("/api/voices");
        populateVoicePairs(voices.voice_pairs || [], "us_natural");
        await refreshSessionList(null);
        if (state.sessions.length) {
          await selectSession(state.sessions[0].session_id);
        } else {
          updateActionButtons();
          updatePlaybackReadout();
        }
      } catch (err) {
        showSnackbar(`Failed to initialize workspace: ${err.message}`);
      }
    }

    bootstrap();
  </script>
</body>
</html>
```

- [ ] **Step 4: Run frontend contract tests & M3 deterministic audit and commit**

Run:
```powershell
pytest tests/test_frontend_contract.py -v
git add static/index.html tests/test_frontend_contract.py
git commit -m "feat: build Material 3 Expressive single-file frontend with PDF.js 4.10.38 ESM"
```
Expected: `2 passed`, `audit_m3_spec.py --code` reports `"passed": true`, `"errors": []`, `"warnings": []`, clean git commit.

---

### Task 9: Documentation (`README.md`) & Final Live Verification Gate

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write concise GFM `README.md` (following `create-readme` skill)**

````markdown
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
````

- [ ] **Step 2: Run full live & deterministic verification gate**

Run:
```powershell
python -m py_compile app.py deepexamcast/*.py
python -c "import edge_tts, fitz, fastapi, uvicorn; print('ok')"
pytest -v
python "C:\Users\Abishek\.gemini\antigravity-cli\skills\m3-expressive-architect\scripts\audit_m3_spec.py" --spec docs/superpowers/specs/2026-11-20-deepexamcast-m3-ui-spec.md
```
Expected: All compile cleanly, imports print `ok`, 100% of pytest tests pass, M3 spec audit exits `0`.

- [ ] **Step 3: Live Uvicorn boot & HTTP 200 smoke test**

Run:
```powershell
python -c "import subprocess, time, urllib.request, sys; p = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', '8019']); time.sleep(2.5); r1 = urllib.request.urlopen('http://127.0.0.1:8019/').status; r2 = urllib.request.urlopen('http://127.0.0.1:8019/api/voices').status; p.terminate(); p.wait(timeout=5); print('HTTP:', r1, r2); assert r1 == 200 and r2 == 200"
```
Expected: `HTTP: 200 200` and clean process termination with exit code `0`.

- [ ] **Step 4: Commit `README.md` and verify clean git status**

Run:
```powershell
git add README.md
git commit -m "docs: add concise README with setup, workflow, shortcuts, and offline setup"
git status
git log --oneline
```
Expected: Clean working tree with all 9 task commits on `main`.
