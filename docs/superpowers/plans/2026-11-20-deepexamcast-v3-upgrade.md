# DeepExamCast v3 Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. UI work (Task 6) additionally REQUIRES the `m3-expressive-architect` skill (Stage 1 → 2 → 3 with deterministic audits).

**Goal:** Upgrade DeepExamCast with watermark/table/figure-aware PDF parsing, optional local GPU Vision OCR, a structurally deeper prompt engine with pacing modes, Hindi/Malayalam voices, and a Material 3 Expressive dark UI rebuild, all without regressing any existing hardened behavior.

**Architecture:** Backend stays FastAPI + PyMuPDF + edge-tts. `pdf_parser.py` gains a `parse_pdf_detailed()` core that returns chunks plus visual-region / scanned-page metadata; a new stdlib-only `vision_ocr.py` optionally enriches those regions through any OpenAI-compatible vision server (default `llama-server` + `LightOnOCR-3-0.8B`). `prompt_builder.py` becomes profile-driven (`PACING_PROFILES` × `LANGUAGE_PROFILES`), and `session_store.compute_coverage()` uses per-pacing batch budgets from a single table in `models.py`. The frontend remains a single zero-build `static/index.html`.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, PyMuPDF 1.27/1.28, edge-tts 7.x, PDF.js 4.10.38 (ESM CDN + optional `static/vendor`), pytest + pytest-asyncio + httpx (TestClient).

## Global Constraints

- Zero new runtime dependencies in `requirements.txt`; `vision_ocr.py` uses only `urllib.request` / `base64` / `json` + PyMuPDF.
- Every new Pydantic field has a default — existing `sessions/*/session.json` must load with zero migration.
- Vision env vars: `DEEPEXAMCAST_VISION_URL` (default `http://127.0.0.1:8081/v1`), `DEEPEXAMCAST_VISION_MODEL` (default `lightonocr-3`), `DEEPEXAMCAST_VISION_TIMEOUT` (default `45.0`); health-check timeout `1.5s`; render DPI `150`.
- Voice pairs (exact): `us_natural`, `in_english`, `uk_natural` (`en`), `hi_in` (`hi-IN-MadhurNeural`/`hi-IN-SwaraNeural`), `ml_in` (`ml-IN-MidhunNeural`/`ml-IN-SobhanaNeural`).
- Preserve: content-addressed `audio/{hash}.mp3`, per-session `asyncio.Lock` + `409` + re-read-before-merge, PDF.js `4.10.38` with `isEvalSupported: false`, `±4` render / `±8` evict window, `RenderTask.cancel()`, dual-`<audio>` decks (`defaultPlaybackRate`, standby unlock, Retry/Skip snackbar), `textContent`-only DOM (zero `innerHTML`), shortcuts `Space` / `←` / `→` / `R` / `Esc`.
- UI must keep: Delete Session, Re-synthesize Voice, live synthesis progress, dismissible banners, real `<input type="number">` page fields, 4-button transport `|<` `▶/⏸` `>|` `↺`.
- `index.html` must pass `audit_m3_spec.py --code` with **0 errors and 0 warnings** → all `#RRGGBB` hex values live only inside `<style data-m3-tokens>`; no `transition: all`, no `ease-in-out`, no transitions on layout props.
- Test runner: system `python -m pytest` (the `.venv` lacks pytest/httpx). `py_compile` must pass in both interpreters.

## Pre-Flight Findings (verified empirically — do not re-litigate)

| Finding | Consequence |
| --- | --- |
| Real KTU PDF (`sessions/ktu-s7-mod-1-…/source.pdf`, 26 pp): diagonal `keralanotes.com` has `dir = (0.707, -0.707)`, bbox ≈ `[0.24,0.30,0.76,0.70]`; current parser emits it as 27 chunks (area 0.20–0.34). | `abs(dir[1]) > 0.15` filter fixes it; must compute bbox from **surviving lines**, not `block["bbox"]`. |
| Footer `For More Study Materials : www.keralanotes.com` is horizontal, `y0 > 0.93`, on every page. | Already caught by margin-repeat filter; domain filter is a second net. |
| `get_text("dict", flags=TEXTFLAGS_DICT \| TEXT_SEGMENT)` returns ~0 blocks. | Use `flags=fitz.TEXTFLAGS_DICT` **only**. |
| Without `TEXT_SEGMENT`, `dict` merges side-by-side column lines into one block (e.g. "Left upper…" + "Right upper…"). | Split each block's lines into horizontal sub-groups (gap > 6% page width) before ordering, or `test_two_column_with_midpage_full_width_heading_order` breaks. |
| `line["dir"]` stays `(1.0, 0.0)` on `set_rotation(90)` pages. | Rotation test remains safe. |
| KTU PDF: 0 `find_tables()` hits, 19 raster images ≥ 0.15×0.10, plus a small logo `[0.73,0.01,0.96,0.05]` (filtered by size). | Figure detection matters more than tables for real notes. |
| `cluster_drawings()` returns a single rect for a lone `draw_rect`. | Require ≥ 3 intersecting drawing primitives for vector-figure candidates (keeps existing `test_micro_chunk_merging…` green). |
| LightOnOCR-3 grounding output: `![label](x1,y1,x2,y2) content` on a 0–1000 grid, prompt text `"grounding"`, needs `--mmproj`. | Parser targets this format first, plus JSON / `<|ref|><|det|>` fallbacks. |

## Current Progress

- [x] Task 1 implemented and green (`tests/test_models.py`: 4 passed).
- [x] Task 2 Step 1 (failing tests written in `tests/test_pdf_parser.py`; collection fails on missing `parse_pdf_detailed` as expected).

## File Map

| File | Action | Responsibility |
| --- | --- | --- |
| `deepexamcast/models.py` | Modify | Type aliases, `PACING_BATCH_LIMITS`, 5 voice pairs, new defaulted fields, `ReparseRequest` |
| `deepexamcast/pdf_parser.py` | Modify | `parse_pdf_detailed()` (dict extraction, dir filter, tables, figures, scanned pages); `parse_pdf_bytes()` wrapper |
| `deepexamcast/vision_ocr.py` | Create | Env config, health check, OpenAI-compatible call, grounding parser, `extract_pdf_hybrid()` |
| `deepexamcast/prompt_builder.py` | Modify | Profile-driven prompt with computed budgets + language rules |
| `deepexamcast/session_store.py` | Modify | Pacing-aware `compute_coverage()` + `is_complete` |
| `deepexamcast/script_parser.py` | Verify only | Already uses `any(ch.isalnum() ...)`; add tests |
| `app.py` | Modify | `/api/vision/status`, `use_vision` upload form field, `/reparse`, pacing/language on prompt/generate/state |
| `static/index.html` | Rewrite | M3 Expressive dark UI |
| `docs/superpowers/specs/2026-11-20-deepexamcast-m3-ui-spec.md` | Rewrite | v3 Stage 1 + Stage 2 spec (audited) |
| `tests/test_*.py` | Modify / Create | Coverage per task |
| `README.md` | Modify | v3 workflow + GPU Vision OCR section |

---

### Task 1: Domain Models, Chunk Types & Hindi/Malayalam Voice Pairs ✅ DONE

**Files:** Modify `deepexamcast/models.py`, `tests/test_models.py`

**Interfaces — Produces:**
- `LanguageCode = Literal["en","hi","ml"]`, `PacingMode = Literal["deep_dive","revision","exam_drill","eli5"]`, `ChunkType = Literal["text","table","formula","figure","chart"]`
- `PACING_BATCH_LIMITS: dict[str, tuple[int,int,int]]` → `(max_chunks, max_chars, max_pages)`: `deep_dive (20, 9000, 4)`, `revision (32, 13000, 5)`, `exam_drill (24, 10000, 4)`, `eli5 (20, 9000, 4)`
- `VoicePair.language`; `Chunk.chunk_type = "text"`; `BatchRecord.pacing/language = None`; `StudyState.pacing = "deep_dive"`, `.language = "en"`; `CoverageInfo.is_complete = False`; `GenerateRequest.pacing/language = None`; `StatePatchRequest.pacing/language = None`; `ReparseRequest(use_vision: bool = True)`

- [x] Step 1: Write failing tests (5 voice pairs, language matching, chunk_type defaults, legacy JSON loads)
- [x] Step 2: Run → ImportError on `PACING_BATCH_LIMITS`
- [x] Step 3: Implement
- [x] Step 4: `python -m pytest tests/test_models.py -v` → 4 passed
- [ ] Step 5: Commit

```bash
git add deepexamcast/models.py tests/test_models.py
git commit -m "feat(models): add chunk types, pacing/language state, Hindi & Malayalam voice pairs"
```

---

### Task 2: PDF Parser — Diagonal Watermarks, Native Tables, Figure Detection

**Files:** Modify `deepexamcast/pdf_parser.py`, `tests/test_pdf_parser.py`

**Interfaces:**
- Consumes: `Chunk`, `PageInfo`, `ChunkType` (Task 1)
- Produces:
  ```python
  @dataclass
  class VisualRegion:
      page: int
      bbox: list[float]                 # normalized [x0, y0, x1, y1]
      kind: Literal["figure", "table"]
      has_overlapping_text: bool = False

  @dataclass
  class PdfParseDetails:
      pages: list[PageInfo]
      chunks: list[Chunk]
      visual_regions: list[VisualRegion]
      scanned_pages: list[int]

  def parse_pdf_detailed(data: bytes, *, include_figure_placeholders: bool = True) -> PdfParseDetails
  def parse_pdf_bytes(data: bytes) -> tuple[list[PageInfo], list[Chunk]]   # unchanged signature
  ```

- [x] **Step 1: Failing tests already written** — `test_diagonal_watermark_dropped_and_horizontal_text_preserved`, `test_repeating_watermark_url_suppressed_across_pages`, `test_native_table_extracted_as_single_markdown_chunk`, `test_figure_raster_and_vector_diagram_detected` (all 6 legacy tests untouched).

- [ ] **Step 2: Confirm failure**

  Run: `python -m pytest tests/test_pdf_parser.py -v` → Expected: collection `ImportError: cannot import name 'parse_pdf_detailed'`.

- [ ] **Step 3: Implement helpers and per-page pipeline**

  Add to `_RawBlock`: `chunk_type: str = "text"`. In `_can_merge_micro`, first line: `if prev.chunk_type != "text" or curr.chunk_type != "text": return False`.

  New constants / helpers:
  ```python
  _DIR_TILT_MAX = 0.15
  _SPARSE_AREA_MIN = 0.15
  _SPARSE_TEXT_MAX = 40
  _FIG_MIN_W, _FIG_MIN_H = 0.15, 0.10
  _BACKGROUND_MIN = 0.90
  _SCANNED_ALNUM_MAX = 30
  _COLUMN_GAP_RATIO = 0.06
  _DOMAIN_RE = re.compile(
      r"(?:https?://|www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|in|org|net|edu|io|co|info|xyz)\b",
      re.IGNORECASE,
  )

  def _norm_rect(r, rect, width, height) -> tuple[float, float, float, float]:
      return (
          round(_clamp((float(r[0]) - rect.x0) / width), 5),
          round(_clamp((float(r[1]) - rect.y0) / height), 5),
          round(_clamp((float(r[2]) - rect.x0) / width), 5),
          round(_clamp((float(r[3]) - rect.y0) / height), 5),
      )

  def _table_markdown(rows: list[list]) -> str | None:
      cleaned = [[" ".join(str(c or "").split()).replace("|", "\\|") for c in row] for row in rows]
      cleaned = [row for row in cleaned if any(cell for cell in row)]
      if len(cleaned) < 2:
          return None
      ncols = max(len(r) for r in cleaned)
      if ncols < 2 or sum(1 for r in cleaned for c in r if c) < 2:
          return None
      padded = [r + [""] * (ncols - len(r)) for r in cleaned]
      lines = ["| " + " | ".join(padded[0]) + " |", "| " + " | ".join(["---"] * ncols) + " |"]
      lines += ["| " + " | ".join(r) + " |" for r in padded[1:]]
      return "\n".join(lines)

  def _split_line_groups(lines: list[dict], page_width: float) -> list[list[dict]]:
      """Union-find: lines join a group when x-intervals overlap or gap <= 6% page width."""
  ```

  Per-page order of operations inside `parse_pdf_detailed`:
  1. **Tables:** `try: tabs = page.find_tables()` / `except Exception: tabs = None`. For each table: `md = _table_markdown(t.extract())`. If `md` → `_RawBlock(chunk_type="table", text=md, bbox=norm(t.bbox))` and append `fitz.Rect(t.bbox) + (-2, -2, 2, 2)` to `table_rects`. Else, if normalized size ≥ 0.15×0.10 and not ≥ 0.90×0.90 → `VisualRegion(kind="table")`.
  2. **Text:** `page.get_text("dict", flags=fitz.TEXTFLAGS_DICT)` (**never** OR `TEXT_SEGMENT`). For each `type == 0` block, keep lines where `abs(line["dir"][1]) <= 0.15`, line center not inside any `table_rects`, and span text non-blank. Split survivors with `_split_line_groups`; per group sort by `(round(y0,2), round(x0,2))`, join with `"\n"`, `_normalize_text`, bbox = union of **line** bboxes. Drop if normalized area `> 0.15` and `len(text) < 40`.
  3. **Figures:** candidates from `page.get_image_info(xrefs=True)` and from `page.cluster_drawings()` (latter only if ≥ 3 rects from `page.get_drawings()` intersect the cluster). Keep normalized `w >= 0.15 and h >= 0.10` and not `(w > 0.90 and h > 0.90)`. Dedupe (containment or IoU > 0.6); drop if > 50% covered by an extracted table. `has_overlapping_text` = any text block center inside the figure, or overlap / min(area) > 0.2. Record `VisualRegion(kind="figure")`; if `include_figure_placeholders and not has_overlapping_text` → `_RawBlock(text=f"[FIGURE/CHART on Page {p}]", chunk_type="figure")`.
  4. **Scanned detection:** alnum count over the page's text + table blocks `< 30` **and** (`page.get_images()` or `page.get_drawings()`) → append to `scanned_pages`.

  Cross-page filtering (after collecting all pages; keep existing margin logic intact):
  - Existing `>= 3`-page margin repeat + `_PAGE_NUMBER_RE` suppression unchanged.
  - New: for text blocks with `len < 120` and `_DOMAIN_RE.search(text)`, track `text.lower()` → set of pages; suppress any seen on `>= 3` pages, anywhere on the page.
  - Then `_order_page_blocks` → `_merge_micro_chunks` → assign `C1..CN` with `chunk_type` passed into `Chunk`.

  `parse_pdf_bytes(data)` becomes `d = parse_pdf_detailed(data); return d.pages, d.chunks`.

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_pdf_parser.py -v` → 10 passed. If the two-column order test fails after sub-group splitting, **stop and re-plan** (see bottom).

- [ ] **Step 5: Real-document regression check (read-only)**

  ```powershell
  @'
  import json
  from deepexamcast.pdf_parser import parse_pdf_detailed
  from deepexamcast.models import SessionData
  base = r"sessions\ktu-s7-mod-1-artificial-intelligence-pdf-notes-b12f5c"
  SessionData.model_validate_json(open(base + r"\session.json", encoding="utf-8").read())
  d = parse_pdf_detailed(open(base + r"\source.pdf", "rb").read())
  wm = [c.id for c in d.chunks if "keralanotes" in c.text.lower()]
  big = [c.id for c in d.chunks if (c.bbox[2]-c.bbox[0])*(c.bbox[3]-c.bbox[1]) > 0.25 and c.chunk_type == "text"]
  print("chunks", len(d.chunks), "watermarks", wm, "bloated", big, "figures", len(d.visual_regions), "scanned", d.scanned_pages)
  '@ | python -
  ```
  Expected: `watermarks []`, `bloated []`, `figures` ≈ 19, `scanned []`.

- [ ] **Step 6: Commit**
  ```bash
  git add deepexamcast/pdf_parser.py tests/test_pdf_parser.py
  git commit -m "fix(pdf): drop diagonal/repeating watermarks, extract native tables, detect figures"
  ```

---

### Task 3: Optional Hybrid GPU Vision OCR

**Files:** Create `deepexamcast/vision_ocr.py`, `tests/test_vision_ocr.py`

**Interfaces:**
- Consumes: `parse_pdf_detailed`, `PdfParseDetails`, `VisualRegion` (Task 2); `Chunk`, `PageInfo`, `ChunkType` (Task 1)
- Produces:
  ```python
  def get_vision_url() -> str            # env, rstrip("/")
  def get_vision_model() -> str
  def get_vision_timeout() -> float      # safe parse, >= 1.0
  class VisionOcrError(RuntimeError): ...
  class VisionStatus(BaseModel): available: bool; url: str; model: str
  class HybridParseResult(BaseModel):
      pages: list[PageInfo]; chunks: list[Chunk]
      warnings: list[str] = []; vision_used: bool = False
      vision_pages_processed: int = 0; vision_crops_processed: int = 0
  def check_vision_status(timeout: float = 1.5) -> VisionStatus
  def call_vision_ocr(image_png_bytes: bytes, prompt: str, *, timeout: float | None = None) -> str
  def parse_vision_grounding(raw_text: str, page_num: int, *, crop_bbox: list[float] | None = None,
                             default_type: ChunkType = "text") -> list[Chunk]
  def extract_pdf_hybrid(pdf_bytes: bytes, *, use_vision: bool = True) -> HybridParseResult
  ```

- [ ] **Step 1: Write failing tests** in `tests/test_vision_ocr.py`:
  ```python
  import json, urllib.error
  import fitz, pytest
  from deepexamcast import vision_ocr
  from deepexamcast.vision_ocr import (VisionOcrError, VisionStatus, check_vision_status,
                                       extract_pdf_hybrid, parse_vision_grounding)

  GROUNDED = (
      "![title](80,70,920,140) # Uninformed Search\n"
      "![text](80,175,920,225) BFS expands the shallowest node first.\n"
      "![table](80,240,920,400) | Algo | Time |\n| --- | --- |\n| BFS | O(b^d) |\n"
      "![chart](100,420,600,600) Nodes expanded vs depth.\n"
      "![image](100,620,500,800) Search tree diagram.\n"
      "![formula](100,820,600,860) f(n) = g(n) + h(n)\n"
      "![footer](0,960,1000,1000) www.keralanotes.com\n"
  )

  def test_parse_lightonocr3_grounding_markdown_and_json():
      chunks = parse_vision_grounding(GROUNDED, page_num=3)
      assert [c.chunk_type for c in chunks] == ["text", "text", "table", "chart", "figure", "formula"]
      assert chunks[1].bbox == [0.08, 0.175, 0.92, 0.225]
      assert all(0.0 <= v <= 1.0 for c in chunks for v in c.bbox)
      assert "| BFS | O(b^d) |" in chunks[2].text
      assert not any("keralanotes" in c.text for c in chunks)
      js = json.dumps([{"type": "table", "bbox": [0, 0, 500, 500], "text": "| a | b |"}])
      jchunks = parse_vision_grounding(js, page_num=1)
      assert jchunks[0].chunk_type == "table" and jchunks[0].bbox == [0.0, 0.0, 0.5, 0.5]
      crop = parse_vision_grounding("A flowchart of agent percepts.", 2,
                                    crop_bbox=[0.2, 0.3, 0.8, 0.6], default_type="figure")
      assert crop[0].bbox == [0.2, 0.3, 0.8, 0.6] and crop[0].chunk_type == "figure"
  ```
  plus `test_hybrid_ocr_enriches_scanned_page_and_figure_crop` (2-page PDF: page 1 image-only via `insert_image` of a Pixmap PNG; page 2 text + raster figure; monkeypatch `vision_ocr.check_vision_status` → available and `vision_ocr.call_vision_ocr` → `GROUNDED` for the full page / a plain sentence for crops; assert `vision_used`, `vision_pages_processed == 1`, `vision_crops_processed == 1`, page-2 text preserved, IDs sequential `C1..CN`, `PageInfo.chunk_count` consistent), `test_hybrid_ocr_graceful_fallback_when_offline_or_timeout` (status unavailable → PyMuPDF chunks + 1 warning mentioning scanned pages; status available but `call_vision_ocr` raises `VisionOcrError("timed out")` → no exception, warning present), and `test_check_vision_status_handles_online_and_offline` (monkeypatch `urllib.request.urlopen` with a fake context manager returning `b'{"data":[]}'` → `available True`; raising `urllib.error.URLError` → `available False`; `url`/`model` echo env defaults).

- [ ] **Step 2: Run** `python -m pytest tests/test_vision_ocr.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement** key pieces:
  ```python
  _GROUND_MD_RE = re.compile(r"!\[([A-Za-z_ -]+)\]\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
  _REF_DET_RE = re.compile(r"<\|ref\|>(.*?)<\|/ref\|>\s*<\|det\|>\s*\[\[\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\]\]\s*<\|/det\|>")
  _SKIP_LABELS = {"header", "footer", "page_header", "page_footer", "watermark", "page_number"}
  _LABEL_MAP = {"table": "table", "formula": "formula", "equation": "formula", "math": "formula",
                "chart": "chart", "plot": "chart", "graph": "chart",
                "figure": "figure", "image": "figure", "diagram": "figure", "picture": "figure"}
  TABLE_PROMPT = "Extract this table as a clean GitHub Markdown table. Output only the table."
  FIGURE_PROMPT = ("Describe this figure for an exam student in 2-4 sentences. If it is a chart, output its "
                   "data as a Markdown table; if it is a formula, output LaTeX. No preamble.")
  ```
  - Grounding parser: split text at each tag match; content = text up to next tag, stripped; drop empty / skip-labels; coords `/1000` clamped, `x0<x1`, `y0<y1`; with `crop_bbox` map `x = cx0 + nx*(cx1-cx0)` (same for y); emit `Chunk(id="V{n}", page=page_num, ...)` (temporary IDs, renumbered later). JSON path: `json.loads` list of dicts with `bbox` + `text|content` + `type|label`. No tags + `crop_bbox` → single chunk (type `"table"` if a line matches `^\s*\|.*\|\s*$`, else `default_type`). No tags and no crop → single text chunk spanning `[0,0,1,1]` if non-empty.
  - `call_vision_ocr`: POST `{"model", "messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,…"}},{"type":"text","text":prompt}]}], "temperature":0.1, "max_tokens":2048}`; wrap every `URLError`/`TimeoutError`/`OSError`/`ValueError`/`KeyError` into `VisionOcrError`.
  - `extract_pdf_hybrid`: as specified (short-circuit with zero network when `not use_vision` or nothing to enrich; offline → warn only if `scanned_pages`; scanned pages → `page.get_pixmap(dpi=150)` + `"grounding"`; regions → `clip=` padded by `0.015` normalized; replace overlapping placeholder (IoU > 0.5) else append; on `VisionOcrError` warn once and stop further crops). Finally sort per page by `(round(y0,3), round(x0,3))`, renumber `C1..CN` across the doc, rebuild `PageInfo.chunk_count`.

- [ ] **Step 4: Run** → 4 passed. Also re-run `tests/test_pdf_parser.py`.

- [ ] **Step 5: Commit** `feat(ocr): optional hybrid LightOnOCR-3 vision enrichment with graceful fallback`

---

### Task 4: Prompt Engine, Pacing Profiles, Languages, Pacing-Aware Coverage

**Files:** Modify `deepexamcast/prompt_builder.py`, `deepexamcast/session_store.py`, `tests/test_prompt_builder.py`, `tests/test_session_store.py`, `tests/test_script_parser.py`

**Interfaces:**
- Produces:
  ```python
  PACING_PROFILES: dict[str, dict]     # keys: deep_dive, revision, exam_drill, eli5
  LANGUAGE_PROFILES: dict[str, str]    # keys: en, hi, ml
  class PromptResult(BaseModel): ... + pacing: PacingMode = "deep_dive"; language: LanguageCode = "en"
  def build_prompt(chunks, page_count, start_page, end_page, recent_lines=None,
                   pacing: str = "deep_dive", language: str = "en") -> PromptResult
  def compute_coverage(session: SessionData, pacing: PacingMode | None = None) -> CoverageInfo
  ```

- [ ] **Step 1: Write failing tests**
  ```python
  # tests/test_prompt_builder.py (append)
  def test_deep_dive_injects_budgets_anti_bundling_and_five_beats():
      chunks = [Chunk(id=f"C{i}", page=1 + (i - 1) // 3, bbox=[0.1, 0.1, 0.9, 0.2], text=f"Concept {i}")
                for i in range(1, 13)]
      chunks[4] = chunks[4].model_copy(update={"chunk_type": "table", "text": "| a | b |"})
      r = build_prompt(chunks, page_count=4, start_page=1, end_page=4)
      assert r.pacing == "deep_dive"
      assert "24–32 dialogue turns" in r.prompt          # 6*4 – 8*4
      assert "760–920 spoken words" in r.prompt          # 190*4 – 230*4
      assert "NEVER bundle more than 2–3" in r.prompt
      for beat in ("Intuition", "Formal Definition", "Analogy", "Confusion Check", "Exam Takeaway"):
          assert beat in r.prompt
      assert "[C5] (Page 2) [TABLE]: | a | b |" in r.prompt
      assert "[C1] (Page 1): Concept 1" in r.prompt

  def test_pacing_profiles_render_distinct_instructions():
      prompts = {p: build_prompt(_sample_chunks(), 6, 2, 3, pacing=p).prompt
                 for p in ("deep_dive", "revision", "exam_drill", "eli5")}
      assert "EXAM NIGHT SPRINT" in prompts["revision"] and "6–8 dialogue turns" in prompts["revision"]
      assert "VIVA" in prompts["exam_drill"] and "7-mark" in prompts["exam_drill"]
      assert "INTUITION FIRST" in prompts["eli5"]
      assert len(set(prompts.values())) == 4
      for p in prompts.values():
          assert "ZERO SKIMMING" in p
      with pytest.raises(PromptBuildError):
          build_prompt(_sample_chunks(), 6, 2, 3, pacing="speedrun")

  def test_hindi_and_malayalam_language_rules():
      hi = build_prompt(_sample_chunks(), 6, 2, 3, language="hi").prompt
      ml = build_prompt(_sample_chunks(), 6, 2, 3, language="ml").prompt
      assert "Devanagari" in hi and "exam_note" in hi and "English" in hi
      assert "Malayalam script" in ml and "exam_note" in ml and "English" in ml
  ```
  ```python
  # tests/test_session_store.py (append)
  def test_pacing_budgets_and_is_complete(tmp_path):
      store = SessionStore(tmp_path)
      pages = [PageInfo(page=p, width=600, height=800, chunk_count=7) for p in range(1, 9)]
      chunks = [Chunk(id=f"C{i}", page=1 + (i - 1) // 7, bbox=[0.1, 0.1, 0.9, 0.2], text="X" * 300)
                for i in range(1, 57)]
      s = store.create_session("budget.pdf", b"%PDF-1.4", pages, chunks)
      dd = compute_coverage(s).suggested_next_range                      # default deep_dive
      assert dd.chunk_count <= 20 and dd.char_count <= 9000 and dd.end_page - dd.start_page + 1 <= 4
      rv = compute_coverage(s, pacing="revision").suggested_next_range
      assert rv.chunk_count <= 32 and rv.end_page - rv.start_page + 1 <= 5
      assert rv.end_page > dd.end_page
      assert compute_coverage(s).is_complete is False
  ```
  Update existing `test_chunk_level_coverage_budgeted_range_and_missed_chunks` comment only (4 chunks still fit; page 3's 30 chunks exceed 20 → `end_page == 2` unchanged).
  ```python
  # tests/test_script_parser.py (append)
  def test_pure_devanagari_and_malayalam_lines_are_speakable():
      res = parse_gemini_script(json.dumps([
          {"speaker": "HOST_A", "text": "नमस्ते दोस्तों, आज हम खोज एल्गोरिदम समझेंगे।", "chunk_ids": ["C1"]},
          {"speaker": "HOST_B", "text": "നമസ്കാരം, ഇന്ന് നമ്മൾ സെർച്ച് അൽഗോരിതം പഠിക്കാം. അവൻ, അൾ", "chunk_ids": ["C1"]},
      ], ensure_ascii=False), {"C1"})
      assert len(res.items) == 2
      with pytest.raises(ScriptParseError, match="speakable"):
          parse_gemini_script('[{"speaker": "HOST_A", "text": "। ॥ — …", "chunk_ids": ["C1"]}]', {"C1"})
  ```

- [ ] **Step 2: Run** the three files → new tests fail (unexpected kwargs / missing strings).

- [ ] **Step 3: Implement**
  - `PACING_PROFILES[p]` holds `label`, `turns_per_page (lo, hi)`, `words_per_page (lo, hi) | None`, and an instruction block. Budgets are rendered as `f"{n*lo}–{n*hi} dialogue turns"` and `f"{n*wlo}–{n*whi} spoken words"` with `n = end_page - start_page + 1`:
    - `deep_dive`: turns (6, 8), words (190, 230); block contains the anti-mega-bundling sentence verbatim, the turn-cadence sentence (HOST_A 3–5 sentences / 50–85 words; HOST_B 1–3 sentences / 20–40 words), and the numbered 5-beat list (**Intuition / Why It Exists**, **Deconstructed Formal Definition & Mechanism**, **Concrete Real-World Analogy or Walkthrough** incl. `[TABLE]/[CHART]/[FIGURE]` narration, **Student Confusion Check & Edge Cases**, **Exam Takeaway Anchor**).
    - `revision`: header `EXAM NIGHT SPRINT`, turns (3, 4), words (90, 120); definitions, keywords, comparisons, mnemonics, `exam_note` on nearly every turn.
    - `exam_drill`: header `VIVA / Q&A GRILL`, turns (4, 6), words `None`; pose likely 3-mark and 7-mark questions per topic, rhetorical beat, point-by-point marking-scheme answer.
    - `eli5`: header `INTUITION FIRST`, turns (5, 7), words (150, 190); everyday analogy first, then map back to formal syllabus terms.
  - `LANGUAGE_PROFILES`: `en` (natural spoken English, spell out math), `hi` (conversational classroom Hindi in **Devanagari** script, not Sanskritized news register, natural English technical terms, `exam_note` in crisp English keywords/formulas), `ml` (warm conversational classroom Malayalam in **Malayalam script**, not newsreader register, English technical terms woven in, `exam_note` in crisp English keywords/formulas).
  - Chunk line format: unchanged for `text`; `f"[{c.id}] (Page {c.page}) [{c.chunk_type.upper()}]: {c.text}"` otherwise.
  - Keep `ZERO SKIMMING`, traceability rule, no-markdown spoken text, JSON-only schema, continuity block.
  - `compute_coverage`: resolve `effective = pacing or session.state.pacing or "deep_dive"`, read `PACING_BATCH_LIMITS`, replace the module constants in the loop, set `is_complete = bool(session.chunks) and len(covered_chunk_ids) >= len(session.chunks)`. Keep `MAX_BATCH_*` names as aliases of the deep_dive values for import compatibility.
  - `script_parser.py`: no change (already Unicode `isalnum`); add a one-line comment stating why ASCII regex must never be used.

- [ ] **Step 4: Run** `python -m pytest tests/test_prompt_builder.py tests/test_session_store.py tests/test_script_parser.py -v` → all pass.

- [ ] **Step 5: Commit** `feat(prompt): pacing profiles, computed deep-dive budgets, Hindi/Malayalam rules, pacing-aware batches`

---

### Task 5: FastAPI Routes

**Files:** Modify `app.py`, `tests/test_api_integration.py`

**Interfaces — Consumes:** `extract_pdf_hybrid`, `check_vision_status` (Task 3); `build_prompt(..., pacing, language)`, `compute_coverage(session, pacing)` (Task 4); `ReparseRequest`, `PacingMode`, `LanguageCode` (Task 1).

**Produces (HTTP):**
| Route | Change |
| --- | --- |
| `GET /api/vision/status` | New → `{available, url, model}` via `asyncio.to_thread(check_vision_status)` |
| `POST /api/upload` | `use_vision: bool = Form(True)`; parse via `extract_pdf_hybrid`; response adds `vision_used` |
| `POST /api/sessions/{id}/reparse` | New; body `ReparseRequest` (optional); lock → 409 if generating → read PDF → parse **outside** lock → re-lock → 409 re-check → re-read session → replace `pages/chunks/page_count` → save; warning if script exists |
| `GET /api/sessions/{id}/prompt` | Query `pacing`, `language` (optional, default to `session.state`) |
| `POST /api/sessions/{id}/generate` | Store `pacing/language` on `BatchRecord`; update `state` when provided |
| `PATCH /api/sessions/{id}/state` | Accept `pacing/language`; response adds `coverage` |

- [ ] **Step 1: Write failing tests**
  - Update lifecycle test: `voice_pairs` length `5`, ids include `hi_in`, `ml_in`, `languages == {"en","hi","ml"}`.
  - `test_vision_status_and_reparse_and_pacing_language(client_and_dirs, monkeypatch)`: monkeypatch `app_module.check_vision_status` / `deepexamcast.vision_ocr.check_vision_status` to return `VisionStatus(available=False, url="http://127.0.0.1:8081/v1", model="lightonocr-3")`; `GET /api/vision/status` → 200 with those keys; upload 2-page PDF with `data={"use_vision": "false"}` → `vision_used is False`; `POST /reparse` `{"use_vision": false}` → 200, same chunk IDs; `GET /prompt?start_page=1&end_page=2&pacing=revision&language=ml` → prompt contains `EXAM NIGHT SPRINT` and `Malayalam script`, response `pacing == "revision"`; `PATCH /state {"pacing":"revision","language":"ml"}` → `state.pacing == "revision"` and `"coverage"` in body.
  - Extend the slow-generate concurrency test: while generation is blocked, `POST /reparse` → `409`.

- [ ] **Step 2: Run** → failures (404 routes, 3 vs 5 voices).

- [ ] **Step 3: Implement** per table; keep all existing guards, error mapping, and `finally: store.end_generation`.

- [ ] **Step 4: Run** `python -m pytest tests/test_api_integration.py -v` then full `python -m pytest -v` (frontend contract tests still green on the old HTML).

- [ ] **Step 5: Commit** `feat(api): vision status, reparse endpoint, pacing/language-aware prompt and state`

---

### Task 6: M3 Expressive Dark UI — Spec, Then `static/index.html`

**Files:** Rewrite `docs/superpowers/specs/2026-11-20-deepexamcast-m3-ui-spec.md`, rewrite `static/index.html`, modify `tests/test_frontend_contract.py`

**Interfaces — Consumes (HTTP):** all Task 5 routes plus existing ones. **Produces (DOM contract IDs):** every legacy ID (`sessionSelect, deleteSessionBtn, uploadBtn, drawerToggleBtn, scriptSheet, fromPageInput, toPageInput, copyPromptBtn, jsonInput, voicePairSelect, resynthesizeBtn, appendBtn, replaceBtn, undoBtn, genProgressBox, drawerAlert, prevLineBtn, playPauseBtn, nextLineBtn, repeatLineBtn, speedGroup, lineScrubber, autoScrollBtn, pdfPane, dialoguePane, snackbarStack, mobileTabs`) **plus** `modeStatusBadge, pacingGroup, languageGroup, paperModeGroup, visionStatusPill, reparseBtn, wavyScrubberSvg, coverageWavySvg, chapterCompleteBadge, generateMainBtn, splitMenuToggleBtn, splitActionMenu, splitResynthesizeBtn, pdfPageReadout, zoomLabel`.

- [ ] **Step 1 (M3 Stage 1+2): Rewrite the spec** — Element inventory `E-01..E-30`, interaction table `I-01..I-28` (each I-ID referenced again in the motion table), adaptive matrix with Compact / Medium / Expanded / Large / Extra-large / Compact-Height rows (breakpoint for split = 900px), token JSON (values below), component→Tier mapping (sheet = Tier 1; buttons/chips/switch/speed/pacing = Tier 2; transcript cards, chunk boxes = Tier 3), motion spec pairing `*-spatial` with `*-effects` and a reduced-motion column, a11y (48px touch / 40px pointer-fine, `3px :focus-visible`). Then:
  ```bash
  python "C:\Users\Abishek\.gemini\antigravity-cli\skills\m3-expressive-architect\scripts\audit_m3_spec.py" --spec docs/superpowers/specs/2026-11-20-deepexamcast-m3-ui-spec.md
  ```
  Expected exit `0`, `errors: []`, `warnings: []`.

- [ ] **Step 2: Extend frontend contract test (failing)** — keep every existing assertion; add the new IDs loop, `assert "function formatChunkIds" in html`, `assert ".paper-dark .pdf-page-canvas" in html and ".paper-dark .chunk" not in html`, `assert "/api/vision/status" in html and "/reparse" in html`, `assert "Plus Jakarta Sans" in html and "cdn.tailwindcss.com" not in html`, and a new test running `audit_m3_spec.py --spec` on the spec file. Run → fails on missing IDs.

- [ ] **Step 3: Tokens block** (`<style data-m3-tokens>` — the only place hex is allowed): `--md-canvas #131316`, `--md-surface-low #1B1B1F`, `--md-surface #212126`, `--md-surface-high #2B2B31`, `--md-surface-highest #383842`, `--md-sheet #24242A`, `--md-well #151519`, `--md-dock #25252B`, `--md-outline-subtle rgba(255,255,255,.08)`, `--md-primary #F3C669`, `--md-on-primary #1D1500`, `--md-primary-border-active rgba(243,198,105,.55)`, `--md-active-tint rgba(243,198,105,.06)`, `--md-on-surface #F4F4F8`, `--md-on-surface-variant #B9B9C6`, `--md-professor-bg #39384D` / `-fg #DDD9F6`, `--md-student-bg #253D32` / `-fg #B7E4CE`, `--md-exam-note-bg #3F310E` / `-fg #FFE09B`, `--md-mint #B7E4CE`, error roles, PDF highlight `rgba(243,198,105,.32)` + border, fonts, shape scale (`12/16/20/24/28/9999`), and the compiled spring block from `compile_springs.py --platform web --scheme expressive` (all six tokens + reduced-motion overrides).

- [ ] **Step 4: Layout & components** (`<style data-m3-components>` uses only `var(--…)`):
  - Shell: CSS grid rows `56px | 1fr | auto` on `--md-canvas`. Thin scrollbars (`scrollbar-width: thin`, `::-webkit-scrollbar { width: 6px }`, translucent thumb).
  - Top bar: amber 34px rounded-12 waveform icon + `DeepExamCast`; center tonal pill = `sessionSelect` (`max-width:340px; text-overflow:ellipsis`) + `modeStatusBadge` + `deleteSessionBtn`; right = tonal `uploadBtn` + amber `drawerToggleBtn` (sparkle SVG, label `Script Studio`).
  - Workspace: `grid-template-columns: minmax(0,64fr) minmax(0,36fr); gap:12px; padding:0 12px`; panes `--md-surface-low`, radius 24px. `< 900px` → single column + `mobileTabs`.
  - PDF pane: `position:relative`; `#pdfScroll` with `padding-bottom:88px`; floating toolbar (`position:absolute; bottom:18px; left:50%; transform:translateX(-50%)`, `--md-surface-high` pill): `zoomOutBtn`, `zoomLabel`, `zoomInBtn`, divider, `zoomFitBtn` (`Fit`), divider, `pdfPageReadout`, divider, `paperModeGroup` (light/sepia/dark SVG buttons, `aria-pressed`). Paper CSS **only on canvas**: `.paper-sepia .pdf-page-canvas{filter:sepia(.28) brightness(.94)}`, `.paper-dark .pdf-page-canvas{filter:invert(.88) hue-rotate(180deg) contrast(.95)}`; mode persisted in `localStorage("dec.paperMode")`.
  - Page readout: `IntersectionObserver` with `threshold:[0,.25,.5,.75,1]` storing `ratioByPage`; `state.readoutSource = "playback" | "browse"`. Playback jumps set `"playback"` and show the active line's page; a user `wheel`/`pointerdown`/`keydown` scroll on `#pdfScroll` sets `"browse"` and shows the max-ratio page. Render window still derives from visible set (`±4` render / `±8` evict).
  - Transcript: header `Lecture Transcript` + `dialogueMeta` pill. `formatChunkIds(ids)` groups numeric runs → `C127–C133`, joins non-contiguous with `, `, truncates after 3 groups with `+N`. Ref tag `Pg 7 · C127–C133`, `white-space:nowrap`. Active card: `--md-surface-high` + `1px solid var(--md-primary-border-active)` + `box-shadow: inset 0 0 0 999px var(--md-active-tint)`; pulsing 3-bar SVG (CSS `transform: scaleY` keyframes, disabled under reduced motion) shown only on active card; exam note chip radius 14px in exam-note roles.
  - Player dock: `margin:10px 12px 12px; border-radius:9999px; background:var(--md-dock)`. Left: 48px amber circular `playPauseBtn` (play/pause SVGs) + circular tonal `prevLineBtn` (`|<`), `nextLineBtn` (`>|`), `repeatLineBtn` (`↺`). Connected `speedGroup` (5 pills, active amber). Scrubber: wrapper `position:relative` containing `<svg id="wavyScrubberSvg">` (played sine `<path>` amplitude 3px / wavelength 18px, remaining flat `<line>` `--md-surface-highest`, `<circle>` thumb) under a transparent full-size `<input id="lineScrubber" type="range">` (keeps keyboard + pointer drag + a11y). Redraw on index change and `ResizeObserver`; under `matchMedia('(prefers-reduced-motion: reduce)')` draw flat line. `playbackReadout` mono `Line 34 / 104 · ~19m left`. Right: `autoScrollBtn` switch (`aria-pressed`, thumb `transform: translateX`).
  - Script Studio sheet: `position:fixed; top:0; right:0; bottom:0; width:clamp(400px,40vw,520px); border-radius:28px 0 0 28px; background:var(--md-sheet)`; hidden via `transform:translateX(104%)` (Tier 1, `default-spatial` + `default-effects` opacity). Scrim covers **only** `left: calc(64% + 6px)` → right edge at ≥ 900px (PDF stays visible & scrollable); full-screen scrim below 900px. Body scrolls; footer sticky.
    1. Header: `Script Studio`, `visionStatusPill` (`Vision OCR: Ready` / `Text Mode`), `reparseBtn` (icon, title `Re-parse PDF`), `closeSheetBtn`.
    2. `pacingGroup` connected buttons: `deep_dive` "Deep Dive", `revision` "Revision", `exam_drill` "Viva Q&A", `eli5` "ELI5".
    3. `languageGroup` chips `en` English / `hi` Hindi (Hinglish) / `ml` Malayalam (Manglish) with mint check SVG when `aria-pressed="true"`; `voicePairSelect` filtered to `vp.language === state.language` (auto-select first match if current pair mismatches); `resynthesizeBtn`.
    4. Coverage card: `chapterCompleteBadge` (`Chapter Complete — Pick pages to regenerate`, shown when `coverage.is_complete`; inputs then default to `1..min(4,page_count)` instead of `1..1`), `fromPageInput`/`toPageInput` (`type="number"`), `coverageWavySvg`, `coverageSummary` (`Covered: X / Y pages · A / B chunks`), `partialSummary`, wide `copyPromptBtn` → `/prompt?start_page&end_page&pacing&language`.
    5. `jsonInput` textarea in `--md-well`, radius 20px, mono.
    6. `genProgressBox` (unchanged polling text `Synthesizing N / T clips (C cached) · Ss`) + `drawerAlert` banner (error/warning, dismiss button).
    7. Footer: `undoBtn`, `appendBtn`, split button `generateMainBtn` (`Generate Audio`: append when script exists, else replace) + `splitMenuToggleBtn` (`aria-expanded`, chevron) → `splitActionMenu` (`role="menu"`) with `replaceBtn` (`Replace Entire Lecture`, `confirm()` guard) and `splitResynthesizeBtn` (`Re-synthesize Existing Audio`). Menu closes on outside click / `Esc`.
  - Pacing/language changes: update badge (`Deep Dive · EN`), debounce `PATCH /state {pacing, language}`, apply returned `coverage` to page inputs (unless the user edited them since last suggestion), include both in `generate` body.
  - Upload sends `use_vision=true`; after upload/reparse show `warnings` in `drawerAlert` (warning style). `reparseBtn` → `POST /reparse {use_vision: visionAvailable}` → `applySessionData(payload, {reloadPdf: true})`.
  - Port **verbatim** (adjusting only element refs): `loadPdfJs`, `showSnackbar`, `apiJson`, `jumpToLine`, `togglePlayPause`, `unlockDecksOnGesture`, `preloadNextLine`, `bindDeckEvents`, `renderPageSlot`, `evictPageSlot`, `refreshPdfRenderWindow`, `cancelAndClearPdf`, `applyZoom`, `scheduleStatePatch`, keyboard handler, progress polling.

- [ ] **Step 5: Code audit + tests**
  ```bash
  python -m pytest tests/test_frontend_contract.py -v
  ```
  (the test extracts the three tagged blocks and runs `audit_m3_spec.py --code`; must report 0 errors, 0 warnings). Then a manual browser pass: upload, copy prompt, paste JSON, generate, play/next/repeat/keys, paper modes keep amber highlights, sheet leaves PDF scrollable, mobile < 900px.

- [ ] **Step 6: Commit** `feat(ui): Material 3 Expressive dark rebuild with Script Studio side sheet, wavy scrubber, paper modes`

---

### Task 7: README & Verification Gate

**Files:** Modify `README.md`

- [ ] **Step 1: README** — refresh workflow (Script Studio, pacing modes, Hindi/Malayalam voices, paper modes, Re-parse PDF), shortcuts, and add:

  ````markdown
  ## Optional GPU Vision OCR (`LightOnOCR-3-0.8B` via `llama-server` Vulkan)

  Works on AMD (e.g. RX 5500M 4 GB), NVIDIA, and Intel GPUs. Grab a Vulkan build of llama.cpp, then:

  ```powershell
  # Windows 11
  huggingface-cli download <repo>/LightOnOCR-3-0.8B-GGUF --include "*Q8_0.gguf" "mmproj*.gguf" --local-dir models
  .\llama-server.exe -m models\LightOnOCR-3-0.8B-Q8_0.gguf --mmproj models\mmproj-LightOnOCR-3-0.8B-F16.gguf -ngl 99 --port 8081
  ```
  ```bash
  # Linux
  huggingface-cli download <repo>/LightOnOCR-3-0.8B-GGUF --include "*Q8_0.gguf" "mmproj*.gguf" --local-dir models
  ./llama-server -m models/LightOnOCR-3-0.8B-Q8_0.gguf --mmproj models/mmproj-LightOnOCR-3-0.8B-F16.gguf -ngl 99 --port 8081
  ```
  ````
  plus the three env vars and a note that the app silently falls back to PyMuPDF when the server is off. (Executor: confirm the exact HF repo id before writing; leave `<repo>` only if none can be verified, and say so.)

- [ ] **Step 2: Gate**
  ```powershell
  python -m py_compile app.py (Get-ChildItem deepexamcast\*.py).FullName
  .venv\Scripts\python.exe -m py_compile app.py (Get-ChildItem deepexamcast\*.py).FullName
  python -m pytest -v
  ```
  Expected: compile silent; all tests pass (≈ 29 legacy + ≈ 20 new).
- [ ] **Step 3:** Re-run the Task 2 Step 5 real-PDF regression script.
- [ ] **Step 4: Live smoke** — start `uvicorn app:app --host 127.0.0.1 --port 8000` as a background task, then `Invoke-WebRequest` `/`, `/api/voices` (5 pairs incl. `hi_in`, `ml_in`), `/api/vision/status` (keys `available,url,model`) → all `200`; kill the task.
- [ ] **Step 5: Commit** `docs: v3 workflow and optional GPU Vision OCR setup`

---

## Re-plan Triggers

- `get_text("dict", flags=TEXTFLAGS_DICT)` + line sub-grouping cannot keep `test_two_column_with_midpage_full_width_heading_order` green.
- `audit_m3_spec.py --code` reports an error/warning that cannot be fixed inside the token/component blocks.
- Any existing `sessions/*/session.json` fails `SessionData.model_validate_json`.
- Any legacy test fails for a reason other than the intentional voice-pair count change (3 → 5).

## Self-Review

- **Spec coverage:** §1A → Task 2; §1B → Tasks 3 + 5; §2A/2B → Task 4 (+ prompt/state routes in Task 5); §3 → Tasks 1, 4; §4A/4B → Task 6; §5.1–5.4 → tests in Tasks 2–6; §5.5 → Task 7 Step 1; §5.6 → Task 7 Steps 2–4. Grounding rules (kept controls, 4-button transport, hardened mechanics) → Global Constraints + Task 6 Step 4 port list.
- **Type consistency:** `parse_pdf_detailed` / `PdfParseDetails` / `VisualRegion` (Task 2) used unchanged by Task 3; `extract_pdf_hybrid` / `check_vision_status` / `HybridParseResult.vision_used` used by Task 5; `compute_coverage(session, pacing=None)` and `build_prompt(..., pacing, language)` used by Task 5; DOM IDs in Task 6 match the contract test list.
