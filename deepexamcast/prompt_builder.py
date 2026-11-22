"""Profile-driven Gemini Web prompt builder for page-range chunk batches."""

from __future__ import annotations

from pydantic import BaseModel

from deepexamcast.models import Chunk, LanguageCode, PacingMode, ScriptLine


class PromptBuildError(ValueError):
    """Raised when page range, pacing, or language is invalid or no chunks exist."""


class PromptResult(BaseModel):
    prompt: str
    start_page: int
    end_page: int
    chunk_count: int
    chunk_id_range: list[str]
    char_count: int
    pacing: PacingMode = "deep_dive"
    language: LanguageCode = "en"


PACING_PROFILES: dict[str, dict] = {
    "deep_dive": {
        "label": "Deep Dive (Scratch to Finish)",
        "turns_per_page": (6, 8),
        "words_per_page": (190, 230),
        "instructions": (
            "PACING PROFILE — DEEP DIVE (THEORY MASTERY):\n"
            "- Quantitative Target for this batch: {turn_lo}–{turn_hi} dialogue turns and {word_lo}–{word_hi} spoken words (~75–90 seconds/page at 150 wpm).\n"
            "- STRICT ANTI-MEGA-BUNDLING RULE: NEVER bundle more than 2–3 closely related chunks into a single turn. "
            "Every distinct concept, heading, definition, mechanism, formula, table, or diagram MUST receive its own 2–4 turn teaching exchange.\n"
            "- TURN CADENCE: HOST_A (Professor) teaching turns MUST be rich, unhurried 3–5 natural spoken sentences (50–85 words); "
            "HOST_B (Student) turns MUST be sharp 1–3 sentences (20–40 words) asking genuine conceptual/exam questions rather than empty agreements.\n"
            "- MANDATORY 5-BEAT THEORY MASTERY STRUCTURE (for every core topic):\n"
            "  1. Intuition / Why It Exists (build the mental model before jargon).\n"
            "  2. Deconstructed Formal Definition & Mechanism (exact syllabus keywords explained clearly).\n"
            "  3. Concrete Real-World Analogy or Walkthrough (for [TABLE], [CHART], or [FIGURE] chunks, explicitly narrate what the comparisons, axes, or diagram flow show).\n"
            "  4. Student Confusion Check & Edge Cases (HOST_B asks about common exam traps, distinctions, or limitations).\n"
            "  5. Exam Takeaway Anchor (crisp memory hook + structured exam_note with exact university exam keywords/formulas)."
        ),
    },
    "revision": {
        "label": "Revision (Exam Night Sprint)",
        "turns_per_page": (3, 4),
        "words_per_page": (90, 120),
        "instructions": (
            "PACING PROFILE — EXAM NIGHT SPRINT (HIGH-YIELD REVISION):\n"
            "- Quantitative Target for this batch: {turn_lo}–{turn_hi} dialogue turns and {word_lo}–{word_hi} spoken words (~35–45 seconds/page).\n"
            "- Cover every single chunk ID rapidly with zero skimming. Punch straight to exact definitions, syllabus keywords, side-by-side comparisons, and mnemonics.\n"
            "- Include a crisp, high-yield exam_note on nearly every turn for rapid last-minute scanning."
        ),
    },
    "exam_drill": {
        "label": "Viva Q&A (Exam Drill)",
        "turns_per_page": (4, 6),
        "words_per_page": None,
        "instructions": (
            "PACING PROFILE — VIVA / Q&A GRILL:\n"
            "- Quantitative Target for this batch: {turn_lo}–{turn_hi} dialogue turns.\n"
            "- For every topic/chunk group, HOST_B or HOST_A poses a likely 3-mark or 7-mark university exam / viva question, "
            "gives a brief rhetorical beat, and lays out the exact point-by-point marking-scheme answer to score full marks."
        ),
    },
    "eli5": {
        "label": "ELI5 (Intuition First)",
        "turns_per_page": (5, 7),
        "words_per_page": (150, 190),
        "instructions": (
            "PACING PROFILE — INTUITION FIRST (ELI5):\n"
            "- Quantitative Target for this batch: {turn_lo}–{turn_hi} dialogue turns and {word_lo}–{word_hi} spoken words.\n"
            "- Strip jargon first using vivid everyday analogies and concrete mental pictures before linking each idea back to formal exam terminology."
        ),
    },
}

LANGUAGE_PROFILES: dict[str, str] = {
    "en": (
        "LANGUAGE & AUDIO STYLE (ENGLISH): Natural spoken English. Keep zero markdown symbols (*, #, _, `) inside spoken \"text\". "
        "Spell out all math symbols and notation as natural spoken English (e.g., \"x squared\", \"equals\", \"greater than or equal to\", \"O of n log n\")."
    ),
    "hi": (
        "LANGUAGE & DUAL-SCRIPT STYLE (HINDI / HINGLISH):\n"
        "- \"text\" (Display script shown to user): Write conversational Romanized Hinglish in easy-to-read Latin letters with standard English CS/engineering technical terms.\n"
        "- \"tts_text\" (REQUIRED spoken script for neural TTS): Write the exact same dialogue line in pure native Devanagari script with warm, natural classroom phrasing (not stiff Sanskritized newsreader register).\n"
        "  Transliterate all English technical terms, acronyms, and math symbols phonetically into Devanagari inside \"tts_text\" (e.g., BFS -> बी एफ एस, CPU -> सी पी यू, algorithm -> एल्गोरिदम, A* -> ए स्टार). Keep zero markdown symbols (*, #, _, `) and zero raw ASCII math symbols.\n"
        "- \"exam_note\": Keep in crisp English keywords/formulas for written university exam recall."
    ),
    "ml": (
        "LANGUAGE & DUAL-SCRIPT STYLE (MALAYALAM / MANGLISH):\n"
        "- \"text\" (Display script shown to user): Write conversational Romanized Manglish in easy-to-read Latin letters with standard English CS/engineering technical terms.\n"
        "- \"tts_text\" (REQUIRED spoken script for neural TTS): Write the exact same dialogue line in pure native Malayalam script with warm, natural classroom phrasing (warm professor-student tone, NOT stiff formal newsreader Malayalam).\n"
        "  Transliterate all English technical terms, acronyms, and math symbols phonetically into Malayalam script inside \"tts_text\" (e.g., BFS -> ബി എഫ് എസ്, CPU -> സി പി യു, algorithm -> അൽഗോരിതം, A* -> എ സ്റ്റാർ). Keep zero markdown symbols (*, #, _, `) and zero raw ASCII math symbols.\n"
        "- \"exam_note\": Keep in crisp English keywords/formulas for written university exam recall."
    ),
}


def _format_chunk_line(c: Chunk) -> str:
    if c.chunk_type == "text":
        return f"[{c.id}] (Page {c.page}): {c.text}"
    return f"[{c.id}] (Page {c.page}) [{c.chunk_type.upper()}]: {c.text}"


def build_prompt(
    chunks: list[Chunk],
    page_count: int,
    start_page: int,
    end_page: int,
    recent_lines: list[ScriptLine] | None = None,
    pacing: PacingMode = "deep_dive",
    language: LanguageCode = "en",
) -> PromptResult:
    """Build a ready-to-paste Gemini prompt covering chunks in [start_page, end_page]."""
    if pacing not in PACING_PROFILES:
        raise PromptBuildError(f"Unsupported pacing profile: {pacing!r}.")
    if language not in LANGUAGE_PROFILES:
        raise PromptBuildError(f"Unsupported language code: {language!r}.")

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
    chunk_lines = "\n".join(_format_chunk_line(c) for c in selected)

    num_pages = end_page - start_page + 1
    profile = PACING_PROFILES[pacing]
    t_lo, t_hi = profile["turns_per_page"]
    w_range = profile["words_per_page"]
    w_lo, w_hi = w_range if w_range is not None else (0, 0)
    pacing_block = profile["instructions"].format(
        turn_lo=num_pages * t_lo,
        turn_hi=num_pages * t_hi,
        word_lo=num_pages * w_lo,
        word_hi=num_pages * w_hi,
    )
    language_block = LANGUAGE_PROFILES[language]

    continuity_block = ""
    if recent_lines and start_page > 1:
        tail = recent_lines[-2:]
        formatted_tail = "\n".join(f"{line.speaker}: {line.text}" for line in tail)
        continuity_block = (
            "\nPREVIOUSLY ON THIS LECTURE (do not re-introduce the podcast or repeat these lines; "
            "continue smoothly from here into the first new chunk):\n"
            f"{formatted_tail}\n"
        )

    if language == "hi":
        schema_block = (
            "[\n"
            "  {\n"
            '    "speaker": "HOST_A",\n'
            '    "text": "Romanized Hinglish dialogue for display (e.g., Aaj hum BFS algorithm samjhenge)...",\n'
            '    "tts_text": "Exact same line in pure Devanagari script with phonetic terms (e.g., आज हम बी एफ एस एल्गोरिदम समझेंगे)...",\n'
            f'    "chunk_ids": ["{c_start}"],\n'
            '    "exam_note": "Optional short 1-line formula or key exam fact in English"\n'
            "  }\n"
            "]"
        )
    elif language == "ml":
        schema_block = (
            "[\n"
            "  {\n"
            '    "speaker": "HOST_A",\n'
            '    "text": "Romanized Manglish dialogue for display (e.g., Innu nammal BFS algorithm padikkam)...",\n'
            '    "tts_text": "Exact same line in pure Malayalam script with phonetic terms (e.g., ഇന്ന് നമ്മൾ ബി എഫ് എസ് അൽഗോരിതം പഠിക്കാം)...",\n'
            f'    "chunk_ids": ["{c_start}"],\n'
            '    "exam_note": "Optional short 1-line formula or key exam fact in English"\n'
            "  }\n"
            "]"
        )
    else:
        schema_block = (
            "[\n"
            "  {\n"
            '    "speaker": "HOST_A",\n'
            '    "text": "Spoken dialogue here...",\n'
            f'    "chunk_ids": ["{c_start}"],\n'
            '    "exam_note": "Optional short 1-line formula or key exam fact"\n'
            "  }\n"
            "]"
        )

    prompt = (
        f"You are scripting an in-depth, exam-prep study podcast between an enthusiastic, crystal-clear "
        f"Professor (HOST_A) and a sharp, curious Exam Student (HOST_B).\n"
        f"Study source covers Pages {start_page}–{end_page} ({num_pages} page(s), {len(selected)} chunks: {c_start} through {c_end}).\n\n"
        f"CRITICAL RULES — FOLLOW EVERY SINGLE ONE:\n"
        f"1. ZERO SKIMMING: Cover EVERY single chunk ID in exact sequential order from {c_start} to {c_end} without skipping any ID.\n"
        f"2. {language_block}\n"
        f"3. {pacing_block}\n"
        f"4. EXACT TRACEABILITY: Every turn must reference the chunk ID(s) it explains in \"chunk_ids\". "
        f"Add a concise 1-line formula, distinction, or exam trap in \"exam_note\" when helpful (omit or set null otherwise).\n"
        f"5. STRICTLY VALID JSON ONLY: Output ONLY a raw JSON array (no intro prose, no outro prose) matching this exact schema:\n"
        f"{schema_block}\n"
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
        pacing=pacing,
        language=language,
    )
