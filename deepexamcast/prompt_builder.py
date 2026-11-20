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
