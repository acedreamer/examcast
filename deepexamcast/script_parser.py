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
        # Unicode isalnum() check — never use ASCII-only regex so Devanagari & Malayalam pass cleanly
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
