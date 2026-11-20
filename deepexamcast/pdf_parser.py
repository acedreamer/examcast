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
            block_flags = fitz.TEXTFLAGS_BLOCKS | fitz.TEXT_SEGMENT
            for blk in page.get_text("blocks", sort=False, flags=block_flags):
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
