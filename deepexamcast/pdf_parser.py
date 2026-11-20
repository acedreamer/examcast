"""Column-aware PyMuPDF text, table, and figure extraction with watermark filtering."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

import fitz

from deepexamcast.models import Chunk, ChunkType, PageInfo

_HYPHEN_WRAP_RE = re.compile(r"(\w)-\s*\n\s*(\w)")
_PAGE_NUMBER_RE = re.compile(r"^(?:page\s*)?\d+(?:\s*(?:/|of)\s*\d+)?$", re.IGNORECASE)
_DOMAIN_RE = re.compile(
    r"(?:https?://|www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|in|org|net|edu|io|co|info|xyz)\b",
    re.IGNORECASE,
)

_DIR_TILT_MAX = 0.15
_SPARSE_AREA_MIN = 0.15
_SPARSE_TEXT_MAX = 40
_FIG_MIN_W = 0.15
_FIG_MIN_H = 0.10
_BACKGROUND_MIN = 0.90
_SCANNED_ALNUM_MAX = 30
_COLUMN_GAP_RATIO = 0.06


class PdfParseError(ValueError):
    """Raised when uploaded bytes cannot be parsed as a valid PDF."""


@dataclass
class VisualRegion:
    page: int
    bbox: list[float]
    kind: Literal["figure", "table"]
    has_overlapping_text: bool = False


@dataclass
class PdfParseDetails:
    pages: list[PageInfo]
    chunks: list[Chunk]
    visual_regions: list[VisualRegion]
    scanned_pages: list[int]


@dataclass
class _RawBlock:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    chunk_type: ChunkType = "text"
    band_key: int = 0
    stream_tag: str = "single"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _normalize_text(raw_text: str) -> str:
    dehyphenated = _HYPHEN_WRAP_RE.sub(r"\1\2", raw_text)
    return " ".join(dehyphenated.split())


def _norm_rect(
    r: tuple[float, float, float, float] | list[float] | fitz.Rect,
    rect: fitz.Rect,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    return (
        round(_clamp((float(r[0]) - float(rect.x0)) / width), 5),
        round(_clamp((float(r[1]) - float(rect.y0)) / height), 5),
        round(_clamp((float(r[2]) - float(rect.x0)) / width), 5),
        round(_clamp((float(r[3]) - float(rect.y0)) / height), 5),
    )


def _rect_intersection_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _rect_area(r: tuple[float, float, float, float]) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _table_markdown(rows: list[list]) -> str | None:
    cleaned = [
        [" ".join(str(cell or "").split()).replace("|", "\\|") for cell in row]
        for row in rows
    ]
    cleaned = [row for row in cleaned if any(cell for cell in row)]
    if len(cleaned) < 2:
        return None
    ncols = max(len(r) for r in cleaned)
    if ncols < 2 or sum(1 for r in cleaned for c in r if c) < 2:
        return None
    padded = [r + [""] * (ncols - len(r)) for r in cleaned]
    lines = [
        "| " + " | ".join(padded[0]) + " |",
        "| " + " | ".join(["---"] * ncols) + " |",
    ]
    lines.extend("| " + " | ".join(r) + " |" for r in padded[1:])
    return "\n".join(lines)


def _split_line_groups(lines: list[dict], page_width: float) -> list[list[dict]]:
    """Split lines of a PyMuPDF dict block into horizontal sub-groups using union-find."""
    if len(lines) <= 1:
        return [lines] if lines else []

    gap_limit = _COLUMN_GAP_RATIO * page_width
    n = len(lines)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        ax0, _ay0, ax1, _ay1 = lines[i]["bbox"]
        for j in range(i + 1, n):
            bx0, _by0, bx1, _by1 = lines[j]["bbox"]
            horiz_gap = max(bx0 - ax1, ax0 - bx1)
            if horiz_gap <= gap_limit:
                union(i, j)

    groups: dict[int, list[dict]] = {}
    for idx, line in enumerate(lines):
        root = find(idx)
        groups.setdefault(root, []).append(line)

    result = list(groups.values())
    result.sort(key=lambda grp: (min(l["bbox"][1] for l in grp), min(l["bbox"][0] for l in grp)))
    return result


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

    if not page_is_two_col:
        ordered_single = sorted(
            blocks,
            key=lambda item: (round(item.y0, 3), round(item.x0, 3)),
        )
        for b in ordered_single:
            b.band_key = 0
            b.stream_tag = "single"
        return ordered_single

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
    if prev.chunk_type != "text" or curr.chunk_type != "text":
        return False
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
                chunk_type="text",
                band_key=prev.band_key,
                stream_tag=prev.stream_tag,
            )
        else:
            merged.append(curr)
    return merged


def _dedupe_figure_rects(
    candidates: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    unique: list[tuple[float, float, float, float]] = []
    for cand in sorted(candidates, key=_rect_area, reverse=True):
        c_area = _rect_area(cand)
        if c_area <= 0:
            continue
        merged_away = False
        for existing in unique:
            inter = _rect_intersection_area(cand, existing)
            if inter <= 0:
                continue
            e_area = _rect_area(existing)
            union = c_area + e_area - inter
            if (union > 0 and inter / union > 0.6) or (inter / c_area > 0.85):
                merged_away = True
                break
        if not merged_away:
            unique.append(cand)
    return unique


def parse_pdf_detailed(
    data: bytes,
    *,
    include_figure_placeholders: bool = True,
) -> PdfParseDetails:
    """Extract normalized text, tables, figures, and scanned-page diagnostics from PDF bytes."""
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
        visual_regions: list[VisualRegion] = []
        scanned_pages: list[int] = []

        for page_idx in range(doc.page_count):
            page = doc[page_idx]
            page_num = page_idx + 1
            rect = page.rect
            width = float(rect.width) if rect.width > 0 else 1.0
            height = float(rect.height) if rect.height > 0 else 1.0
            raw_pages_meta.append((page_num, float(rect.width), float(rect.height)))

            blocks_for_page: list[_RawBlock] = []
            extracted_table_rects: list[fitz.Rect] = []
            extracted_table_norm_rects: list[tuple[float, float, float, float]] = []

            # 1. Native Table Extraction
            try:
                tabs = page.find_tables()
                found_tables = list(tabs.tables) if tabs else []
            except Exception:
                found_tables = []

            for tbl in found_tables:
                try:
                    rows = tbl.extract()
                except Exception:
                    rows = []
                md = _table_markdown(rows)
                tx0, ty0, tx1, ty1 = _norm_rect(tbl.bbox, rect, width, height)
                if tx1 <= tx0 or ty1 <= ty0:
                    continue
                if md:
                    blocks_for_page.append(
                        _RawBlock(
                            page=page_num,
                            x0=tx0,
                            y0=ty0,
                            x1=tx1,
                            y1=ty1,
                            text=md,
                            chunk_type="table",
                        )
                    )
                    pad_rect = fitz.Rect(tbl.bbox) + (-2.0, -2.0, 2.0, 2.0)
                    extracted_table_rects.append(pad_rect)
                    extracted_table_norm_rects.append((tx0, ty0, tx1, ty1))
                else:
                    tw, th = tx1 - tx0, ty1 - ty0
                    if tw >= _FIG_MIN_W and th >= _FIG_MIN_H and not (tw > _BACKGROUND_MIN and th > _BACKGROUND_MIN):
                        visual_regions.append(
                            VisualRegion(
                                page=page_num,
                                bbox=[tx0, ty0, tx1, ty1],
                                kind="table",
                                has_overlapping_text=False,
                            )
                        )

            # 2. Dict-based Text Extraction (filtering diagonal watermarks & table cells)
            text_dict = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT)
            for blk in text_dict.get("blocks", []):
                if blk.get("type") != 0:
                    continue

                surviving_lines: list[dict] = []
                for line in blk.get("lines", []):
                    line_dir = line.get("dir", (1.0, 0.0))
                    if abs(float(line_dir[1])) > _DIR_TILT_MAX:
                        continue

                    lbbox = line.get("bbox")
                    if not lbbox:
                        continue
                    lcx = (float(lbbox[0]) + float(lbbox[2])) / 2.0
                    lcy = (float(lbbox[1]) + float(lbbox[3])) / 2.0
                    if any(tr.contains(fitz.Point(lcx, lcy)) for tr in extracted_table_rects):
                        continue

                    line_txt = "".join(str(span.get("text", "")) for span in line.get("spans", []))
                    if not line_txt.strip():
                        continue
                    surviving_lines.append({"bbox": lbbox, "text": line_txt})

                if not surviving_lines:
                    continue

                for group in _split_line_groups(surviving_lines, width):
                    group.sort(key=lambda l: (round(float(l["bbox"][1]), 2), round(float(l["bbox"][0]), 2)))
                    joined_raw = "\n".join(l["text"] for l in group)
                    cleaned = _normalize_text(joined_raw)
                    if not cleaned:
                        continue

                    ux0 = min(float(l["bbox"][0]) for l in group)
                    uy0 = min(float(l["bbox"][1]) for l in group)
                    ux1 = max(float(l["bbox"][2]) for l in group)
                    uy1 = max(float(l["bbox"][3]) for l in group)
                    nx0, ny0, nx1, ny1 = _norm_rect((ux0, uy0, ux1, uy1), rect, width, height)
                    if nx1 <= nx0 or ny1 <= ny0:
                        continue

                    norm_area = (nx1 - nx0) * (ny1 - ny0)
                    if norm_area > _SPARSE_AREA_MIN and len(cleaned) < _SPARSE_TEXT_MAX:
                        continue

                    blocks_for_page.append(
                        _RawBlock(
                            page=page_num,
                            x0=nx0,
                            y0=ny0,
                            x1=nx1,
                            y1=ny1,
                            text=cleaned,
                            chunk_type="text",
                        )
                    )

            # 3. Scanned Page Detection (before adding figure placeholders)
            alnum_count = sum(1 for b in blocks_for_page for ch in b.text if ch.isalnum())
            try:
                page_images = page.get_image_info(xrefs=True)
            except Exception:
                page_images = []
            try:
                page_drawings = page.get_drawings()
            except Exception:
                page_drawings = []

            if alnum_count < _SCANNED_ALNUM_MAX and (len(page_images) > 0 or len(page_drawings) > 0):
                scanned_pages.append(page_num)

            # 4. Figure / Chart / Diagram Detection
            fig_candidates: list[tuple[float, float, float, float]] = []
            for img in page_images:
                ib = img.get("bbox")
                if not ib:
                    continue
                fx0, fy0, fx1, fy1 = _norm_rect(ib, rect, width, height)
                fw, fh = fx1 - fx0, fy1 - fy0
                if fw >= _FIG_MIN_W and fh >= _FIG_MIN_H and not (fw > _BACKGROUND_MIN and fh > _BACKGROUND_MIN):
                    fig_candidates.append((fx0, fy0, fx1, fy1))

            try:
                clusters = page.cluster_drawings()
            except Exception:
                clusters = []
            drawing_rects = [fitz.Rect(d["rect"]) for d in page_drawings if d.get("rect")]
            for cl in clusters:
                cl_rect = fitz.Rect(cl)
                intersecting = sum(1 for dr in drawing_rects if cl_rect.intersects(dr))
                if intersecting < 3:
                    continue
                fx0, fy0, fx1, fy1 = _norm_rect(cl_rect, rect, width, height)
                fw, fh = fx1 - fx0, fy1 - fy0
                if fw >= _FIG_MIN_W and fh >= _FIG_MIN_H and not (fw > _BACKGROUND_MIN and fh > _BACKGROUND_MIN):
                    fig_candidates.append((fx0, fy0, fx1, fy1))

            unique_figs = _dedupe_figure_rects(fig_candidates)
            text_blocks_only = [b for b in blocks_for_page if b.chunk_type == "text"]

            for fig_rect in unique_figs:
                f_area = _rect_area(fig_rect)
                if f_area <= 0:
                    continue
                if any(_rect_intersection_area(fig_rect, tr) / f_area > 0.5 for tr in extracted_table_norm_rects):
                    continue

                has_overlap = False
                for tb in text_blocks_only:
                    tb_rect = (tb.x0, tb.y0, tb.x1, tb.y1)
                    tcx, tcy = (tb.x0 + tb.x1) / 2.0, (tb.y0 + tb.y1) / 2.0
                    if fig_rect[0] <= tcx <= fig_rect[2] and fig_rect[1] <= tcy <= fig_rect[3]:
                        has_overlap = True
                        break
                    min_area = min(f_area, _rect_area(tb_rect))
                    if min_area > 0 and _rect_intersection_area(fig_rect, tb_rect) / min_area > 0.2:
                        has_overlap = True
                        break

                visual_regions.append(
                    VisualRegion(
                        page=page_num,
                        bbox=list(fig_rect),
                        kind="figure",
                        has_overlapping_text=has_overlap,
                    )
                )
                if include_figure_placeholders and not has_overlap:
                    blocks_for_page.append(
                        _RawBlock(
                            page=page_num,
                            x0=fig_rect[0],
                            y0=fig_rect[1],
                            x1=fig_rect[2],
                            y1=fig_rect[3],
                            text=f"[FIGURE/CHART on Page {page_num}]",
                            chunk_type="figure",
                        )
                    )

            raw_page_blocks.append(blocks_for_page)

        # Suppress repeating top/bottom margin headers, footers, page numbers, and repeating domains on >=3 page docs
        repeating_margin_texts: set[str] = set()
        repeating_domain_texts: set[str] = set()
        if doc.page_count >= 3:
            margin_pages: dict[str, set[int]] = {}
            domain_pages: dict[str, set[int]] = {}
            for page_blocks in raw_page_blocks:
                for b in page_blocks:
                    if b.chunk_type != "text":
                        continue
                    low = b.text.lower()
                    if b.y1 < 0.07 or b.y0 > 0.93:
                        margin_pages.setdefault(low, set()).add(b.page)
                    if len(b.text) < 120 and _DOMAIN_RE.search(b.text):
                        domain_pages.setdefault(low, set()).add(b.page)
            repeating_margin_texts = {
                text for text, seen_pages in margin_pages.items() if len(seen_pages) >= 3
            }
            repeating_domain_texts = {
                text for text, seen_pages in domain_pages.items() if len(seen_pages) >= 3
            }

        pages: list[PageInfo] = []
        chunks: list[Chunk] = []
        chunk_counter = 1

        for (page_num, width, height), page_blocks in zip(raw_pages_meta, raw_page_blocks):
            filtered: list[_RawBlock] = []
            for b in page_blocks:
                if b.chunk_type == "text" and doc.page_count >= 3:
                    low = b.text.lower()
                    in_margin = b.y1 < 0.07 or b.y0 > 0.93
                    if in_margin and (_PAGE_NUMBER_RE.match(b.text) or low in repeating_margin_texts):
                        continue
                    if low in repeating_domain_texts:
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
                        chunk_type=b.chunk_type,
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

        return PdfParseDetails(
            pages=pages,
            chunks=chunks,
            visual_regions=visual_regions,
            scanned_pages=scanned_pages,
        )
    finally:
        doc.close()


def parse_pdf_bytes(data: bytes) -> tuple[list[PageInfo], list[Chunk]]:
    """Extract normalized, reading-ordered text, table, and figure chunks from PDF bytes."""
    details = parse_pdf_detailed(data)
    return details.pages, details.chunks
