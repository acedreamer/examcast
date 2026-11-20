"""Optional local GPU Vision OCR integration (OpenAI-compatible llama-server / LightOnOCR-3)."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

import fitz
from pydantic import BaseModel, Field

from deepexamcast.models import Chunk, ChunkType, PageInfo
from deepexamcast.pdf_parser import parse_pdf_detailed

_GROUND_MD_RE = re.compile(
    r"!\[([A-Za-z_ -]+)\]\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)"
)
_REF_DET_RE = re.compile(
    r"<\|ref\|>(.*?)<\|/ref\|>\s*<\|det\|>\s*\[\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]\]\s*<\|/det\|>"
)
_PIPE_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")

_SKIP_LABELS = {
    "header",
    "footer",
    "page_header",
    "page_footer",
    "watermark",
    "page_number",
}

_LABEL_MAP: dict[str, ChunkType] = {
    "table": "table",
    "formula": "formula",
    "equation": "formula",
    "math": "formula",
    "chart": "chart",
    "plot": "chart",
    "graph": "chart",
    "figure": "figure",
    "image": "figure",
    "diagram": "figure",
    "picture": "figure",
}

TABLE_PROMPT = "Extract this table as a clean GitHub Markdown table. Output only the table."
FIGURE_PROMPT = (
    "Describe this figure for an exam student in 2-4 sentences. If it is a chart, output its "
    "data as a Markdown table; if it is a formula, output LaTeX. No preamble."
)


class VisionOcrError(RuntimeError):
    """Raised when an OpenAI-compatible Vision OCR call fails or times out."""


class VisionStatus(BaseModel):
    available: bool
    url: str
    model: str


class HybridParseResult(BaseModel):
    pages: list[PageInfo]
    chunks: list[Chunk]
    warnings: list[str] = Field(default_factory=list)
    vision_used: bool = False
    vision_pages_processed: int = 0
    vision_crops_processed: int = 0


def get_vision_url() -> str:
    return os.getenv("DEEPEXAMCAST_VISION_URL", "http://127.0.0.1:8081/v1").strip().rstrip("/")


def get_vision_model() -> str:
    return os.getenv("DEEPEXAMCAST_VISION_MODEL", "lightonocr-3").strip() or "lightonocr-3"


def get_vision_timeout() -> float:
    raw = os.getenv("DEEPEXAMCAST_VISION_TIMEOUT", "45.0")
    try:
        val = float(raw)
    except ValueError:
        val = 45.0
    return max(1.0, val)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _map_label_to_type(label: str, default_type: ChunkType = "text") -> ChunkType:
    norm = label.strip().lower().replace("-", "_")
    return _LABEL_MAP.get(norm, default_type)


def _scale_box_0_1000(
    coords: tuple[float, float, float, float],
    crop_bbox: list[float] | None = None,
) -> list[float] | None:
    nx0 = _clamp01(coords[0] / 1000.0)
    ny0 = _clamp01(coords[1] / 1000.0)
    nx1 = _clamp01(coords[2] / 1000.0)
    ny1 = _clamp01(coords[3] / 1000.0)
    if nx1 <= nx0 or ny1 <= ny0:
        return None
    if crop_bbox is not None and len(crop_bbox) == 4:
        cx0, cy0, cx1, cy1 = crop_bbox
        cw = max(0.0, cx1 - cx0)
        ch = max(0.0, cy1 - cy0)
        return [
            round(_clamp01(cx0 + nx0 * cw), 5),
            round(_clamp01(cy0 + ny0 * ch), 5),
            round(_clamp01(cx0 + nx1 * cw), 5),
            round(_clamp01(cy0 + ny1 * ch), 5),
        ]
    return [round(nx0, 5), round(ny0, 5), round(nx1, 5), round(ny1, 5)]


def check_vision_status(timeout: float = 1.5) -> VisionStatus:
    """Ping `{VISION_URL}/models` to detect whether local Vision OCR is online."""
    url = get_vision_url()
    model = get_vision_model()
    req = urllib.request.Request(f"{url}/models", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return VisionStatus(available=False, url=url, model=model)
            body = resp.read().decode("utf-8", errors="replace")
            json.loads(body)
            return VisionStatus(available=True, url=url, model=model)
    except Exception:
        return VisionStatus(available=False, url=url, model=model)


def call_vision_ocr(
    image_png_bytes: bytes,
    prompt: str,
    *,
    timeout: float | None = None,
) -> str:
    """Send a PNG image to an OpenAI-compatible Vision endpoint and return text."""
    url = get_vision_url()
    model = get_vision_model()
    eff_timeout = timeout if timeout is not None else get_vision_timeout()
    b64 = base64.b64encode(image_png_bytes).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=eff_timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
        content = parsed["choices"][0]["message"]["content"]
        if isinstance(content, list):
            parts = [str(p.get("text", "")) for p in content if isinstance(p, dict)]
            return "\n".join(parts).strip()
        return str(content).strip()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise VisionOcrError(f"Vision OCR request failed: {exc}") from exc


def parse_vision_grounding(
    raw_text: str,
    page_num: int,
    *,
    crop_bbox: list[float] | None = None,
    default_type: ChunkType = "text",
) -> list[Chunk]:
    """Parse LightOnOCR-3 grounding output (or JSON / ref-det / plain text) into Chunks."""
    text = (raw_text or "").strip()
    if not text:
        return []

    chunks: list[Chunk] = []

    # 1. LightOnOCR-3 Markdown grounding tags: ![label](x1,y1,x2,y2) content
    md_matches = list(_GROUND_MD_RE.finditer(text))
    if md_matches:
        for idx, match in enumerate(md_matches):
            label = match.group(1).strip().lower().replace("-", "_")
            end_pos = md_matches[idx + 1].start() if idx + 1 < len(md_matches) else len(text)
            body = text[match.end() : end_pos].strip()
            if not body or label in _SKIP_LABELS:
                continue
            coords = (
                float(match.group(2)),
                float(match.group(3)),
                float(match.group(4)),
                float(match.group(5)),
            )
            bbox = _scale_box_0_1000(coords, crop_bbox=crop_bbox)
            if bbox is None:
                continue
            chunks.append(
                Chunk(
                    id=f"V{len(chunks) + 1}",
                    page=page_num,
                    bbox=bbox,
                    text=body,
                    chunk_type=_map_label_to_type(label, default_type="text"),
                )
            )
        return chunks

    # 2. <|ref|>label<|/ref|><|det|>[[x1,y1,x2,y2]]<|/det|> fallback
    ref_matches = list(_REF_DET_RE.finditer(text))
    if ref_matches:
        for idx, match in enumerate(ref_matches):
            label = match.group(1).strip().lower().replace("-", "_")
            end_pos = ref_matches[idx + 1].start() if idx + 1 < len(ref_matches) else len(text)
            body = text[match.end() : end_pos].strip()
            if not body or label in _SKIP_LABELS:
                continue
            coords = (
                float(match.group(2)),
                float(match.group(3)),
                float(match.group(4)),
                float(match.group(5)),
            )
            bbox = _scale_box_0_1000(coords, crop_bbox=crop_bbox)
            if bbox is None:
                continue
            chunks.append(
                Chunk(
                    id=f"V{len(chunks) + 1}",
                    page=page_num,
                    bbox=bbox,
                    text=body,
                    chunk_type=_map_label_to_type(label, default_type="text"),
                )
            )
        return chunks

    # 3. JSON array fallback
    if text.startswith("[") or text.startswith("{"):
        try:
            loaded: Any = json.loads(text)
            if isinstance(loaded, dict):
                for val in loaded.values():
                    if isinstance(val, list):
                        loaded = val
                        break
            if isinstance(loaded, list):
                for item in loaded:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get("type") or item.get("label") or "text").strip().lower()
                    if label in _SKIP_LABELS:
                        continue
                    body = str(item.get("text") or item.get("content") or "").strip()
                    raw_box = item.get("bbox")
                    if not body or not isinstance(raw_box, list) or len(raw_box) != 4:
                        continue
                    coords = (float(raw_box[0]), float(raw_box[1]), float(raw_box[2]), float(raw_box[3]))
                    if max(coords) <= 1.0:
                        coords = tuple(c * 1000.0 for c in coords)  # type: ignore[assignment]
                    bbox = _scale_box_0_1000(coords, crop_bbox=crop_bbox)
                    if bbox is None:
                        continue
                    chunks.append(
                        Chunk(
                            id=f"V{len(chunks) + 1}",
                            page=page_num,
                            bbox=bbox,
                            text=body,
                            chunk_type=_map_label_to_type(label, default_type="text"),
                        )
                    )
                if chunks:
                    return chunks
        except (ValueError, TypeError):
            pass

    # 4. Plain text / Markdown response
    inferred_type: ChunkType = default_type
    if any(_PIPE_TABLE_LINE_RE.match(line) for line in text.splitlines()):
        inferred_type = "table"

    final_bbox = (
        [round(_clamp01(v), 5) for v in crop_bbox]
        if crop_bbox is not None and len(crop_bbox) == 4
        else [0.0, 0.0, 1.0, 1.0]
    )
    return [
        Chunk(
            id="V1",
            page=page_num,
            bbox=final_bbox,
            text=text,
            chunk_type=inferred_type,
        )
    ]


def _bbox_iou(a: list[float], b: list[float]) -> float:
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def extract_pdf_hybrid(pdf_bytes: bytes, *, use_vision: bool = True) -> HybridParseResult:
    """Parse PDF with PyMuPDF first and selectively enrich scanned/visual regions via Vision OCR."""
    details = parse_pdf_detailed(pdf_bytes, include_figure_placeholders=True)
    if not use_vision or (not details.scanned_pages and not details.visual_regions):
        return HybridParseResult(
            pages=details.pages,
            chunks=details.chunks,
            warnings=[],
            vision_used=False,
        )

    status = check_vision_status()
    if not status.available:
        warnings: list[str] = []
        if details.scanned_pages:
            warnings.append(
                f"Detected {len(details.scanned_pages)} scanned/image-only page(s) and Vision OCR server "
                f"({status.url}) is offline; using PyMuPDF fallback."
            )
        return HybridParseResult(
            pages=details.pages,
            chunks=details.chunks,
            warnings=warnings,
            vision_used=False,
        )

    chunks_by_page: dict[int, list[Chunk]] = {p.page: [] for p in details.pages}
    for ch in details.chunks:
        chunks_by_page.setdefault(ch.page, []).append(ch)

    regions_by_page: dict[int, list] = {}
    for reg in details.visual_regions:
        regions_by_page.setdefault(reg.page, []).append(reg)

    warnings = []
    pages_processed = 0
    crops_processed = 0
    vision_aborted = False

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        # 1. Scanned / image-only pages
        for page_num in details.scanned_pages:
            if vision_aborted:
                break
            page = doc[page_num - 1]
            pix = page.get_pixmap(dpi=150)
            png_bytes = pix.tobytes("png")
            try:
                raw_out = call_vision_ocr(png_bytes, "grounding")
                parsed = parse_vision_grounding(raw_out, page_num)
                if parsed:
                    chunks_by_page[page_num] = parsed
                    pages_processed += 1
            except VisionOcrError as exc:
                warnings.append(f"Vision OCR failed on scanned Page {page_num}; using PyMuPDF fallback ({exc}).")
                vision_aborted = True

        # 2. Digital pages with detected tables/figures needing enrichment
        scanned_set = set(details.scanned_pages)
        for page_num, regions in regions_by_page.items():
            if vision_aborted:
                break
            if page_num in scanned_set:
                continue
            page = doc[page_num - 1]
            rect = page.rect
            pw = float(rect.width) if rect.width > 0 else 1.0
            ph = float(rect.height) if rect.height > 0 else 1.0

            for reg in regions:
                if vision_aborted:
                    break
                rx0 = _clamp01(reg.bbox[0] - 0.015)
                ry0 = _clamp01(reg.bbox[1] - 0.015)
                rx1 = _clamp01(reg.bbox[2] + 0.015)
                ry1 = _clamp01(reg.bbox[3] + 0.015)
                clip = fitz.Rect(
                    rect.x0 + rx0 * pw,
                    rect.y0 + ry0 * ph,
                    rect.x0 + rx1 * pw,
                    rect.y0 + ry1 * ph,
                )
                if clip.width <= 1 or clip.height <= 1:
                    continue
                pix = page.get_pixmap(dpi=150, clip=clip)
                png_bytes = pix.tobytes("png")
                prompt = TABLE_PROMPT if reg.kind == "table" else FIGURE_PROMPT
                default_ctype: ChunkType = "table" if reg.kind == "table" else "figure"
                try:
                    raw_out = call_vision_ocr(png_bytes, prompt)
                    enriched = parse_vision_grounding(
                        raw_out,
                        page_num,
                        crop_bbox=reg.bbox,
                        default_type=default_ctype,
                    )
                    if enriched:
                        existing = chunks_by_page.get(page_num, [])
                        kept = [
                            c
                            for c in existing
                            if not (
                                c.chunk_type == "figure"
                                and c.text.startswith("[FIGURE/CHART")
                                and _bbox_iou(c.bbox, reg.bbox) > 0.5
                            )
                        ]
                        kept.extend(enriched)
                        chunks_by_page[page_num] = kept
                        crops_processed += 1
                except VisionOcrError as exc:
                    warnings.append(f"Vision OCR crop fallback on Page {page_num}: {exc}")
                    vision_aborted = True
    finally:
        doc.close()

    # Re-sort per page and renumber C1..CN
    final_chunks: list[Chunk] = []
    final_pages: list[PageInfo] = []
    counter = 1
    for pinfo in details.pages:
        p_chunks = chunks_by_page.get(pinfo.page, [])
        p_chunks.sort(key=lambda c: (round(c.bbox[1], 3), round(c.bbox[0], 3)))
        renumbered: list[Chunk] = []
        for ch in p_chunks:
            renumbered.append(ch.model_copy(update={"id": f"C{counter}"}))
            counter += 1
        final_chunks.extend(renumbered)
        final_pages.append(pinfo.model_copy(update={"chunk_count": len(renumbered)}))

    return HybridParseResult(
        pages=final_pages,
        chunks=final_chunks,
        warnings=warnings,
        vision_used=(pages_processed + crops_processed) > 0,
        vision_pages_processed=pages_processed,
        vision_crops_processed=crops_processed,
    )
