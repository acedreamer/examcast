"""Indic script normalization and validation utilities for DeepExamCast."""

from __future__ import annotations

import unicodedata

# Mapping of legacy 3-character Malayalam ZWJ chillu sequences (Consonant + Virama + ZWJ)
# to atomic Unicode 5.1+ chillu characters (\u0D7A–\u0D7F).
MALAYALAM_CHILLU_MAP: dict[str, str] = {
    "\u0D23\u0D4D\u200D": "\u0D7A",  # ൺ (chillu nn)
    "\u0D28\u0D4D\u200D": "\u0D7B",  # ൻ (chillu n)
    "\u0D30\u0D4D\u200D": "\u0D7C",  # ർ (chillu rr)
    "\u0D32\u0D4D\u200D": "\u0D7D",  # ൽ (chillu l)
    "\u0D33\u0D4D\u200D": "\u0D7E",  # ൾ (chillu ll)
    "\u0D15\u0D4D\u200D": "\u0D7F",  # ൿ (chillu k)
}


def normalize_tts_text(text: str) -> str:
    """Normalize text for neural TTS engines.

    1. Applies Unicode NFC normalization.
    2. Maps legacy ZWJ chillu sequences to atomic Unicode 5.1+ chillus.
    3. Preserves legitimate standalone ZWNJ (\u200C) and other ZWJ (\u200D).
    4. Leaves pure ASCII/English text byte-for-byte identical.
    """
    normalized = unicodedata.normalize("NFC", text)
    for seq, chillu in MALAYALAM_CHILLU_MAP.items():
        if seq in normalized:
            normalized = normalized.replace(seq, chillu)
    return normalized


def voice_language_code(voice: str) -> str:
    """Extract lowercased 2-letter language code from voice name (e.g. 'ml-IN-MidhunNeural' -> 'ml')."""
    if not voice:
        return ""
    prefix = voice.split("-")[0].strip().lower()
    return prefix


def has_devanagari(text: str) -> bool:
    """Return True if text contains at least one Devanagari character (\u0900–\u097F)."""
    return any("\u0900" <= ch <= "\u097F" for ch in text)


def has_malayalam(text: str) -> bool:
    """Return True if text contains at least one Malayalam character (\u0D00–\u0D7F)."""
    return any("\u0D00" <= ch <= "\u0D7F" for ch in text)


def has_latin(text: str) -> bool:
    """Return True if text contains at least one Latin character (A-Z, a-z)."""
    return any(("A" <= ch <= "Z") or ("a" <= ch <= "z") for ch in text)


def has_expected_script(text: str, lang: str) -> bool:
    """Return True if text contains the expected script for the language code."""
    if lang == "hi":
        return has_devanagari(text)
    if lang == "ml":
        return has_malayalam(text)
    if lang == "en":
        return has_latin(text)
    return bool(text.strip())


def resolve_spoken_text(text: str, tts_text: str | None, voice: str) -> tuple[str, bool]:
    """Resolve and normalize the actual text to be sent to edge-tts.

    Returns (normalized_spoken_text, swapped_fallback_used).

    Rules:
    - For Hindi/Malayalam voices:
      1. If tts_text contains the expected native script, use tts_text.
      2. If text contains the expected native script (legacy native script OR swapped text/tts_text),
         use text and mark swapped_fallback_used=True if tts_text was provided.
      3. Otherwise fall back to (tts_text or text).
    - For English voices:
      1. If tts_text contains Latin and no Indic script, use tts_text.
      2. Otherwise use text (preventing feeding Indic Unicode tts_text to English voices).
    - For other voices:
      Use (tts_text or text).
    """
    lang = voice_language_code(voice)
    has_tts = bool(tts_text and tts_text.strip())

    if lang in ("hi", "ml"):
        if has_tts and has_expected_script(tts_text, lang):  # type: ignore[arg-type]
            return normalize_tts_text(tts_text), False  # type: ignore[arg-type]
        if has_expected_script(text, lang):
            return normalize_tts_text(text), has_tts
        fallback = tts_text if has_tts else text
        return normalize_tts_text(fallback), False  # type: ignore[arg-type]

    if lang == "en":
        if (
            has_tts
            and has_latin(tts_text)  # type: ignore[arg-type]
            and not (has_devanagari(tts_text) or has_malayalam(tts_text))  # type: ignore[arg-type]
        ):
            return normalize_tts_text(tts_text), False  # type: ignore[arg-type]
        return normalize_tts_text(text), False

    fallback = tts_text if has_tts else text
    return normalize_tts_text(fallback), False  # type: ignore[arg-type]


def validate_script_for_voices(voice_text_pairs: list[tuple[str, str]]) -> tuple[str | None, list[str]]:
    """Validate that spoken text matches voice language requirements.

    Returns (blocking_error_or_None, non_blocking_warnings).
    """
    warnings: list[str] = []

    # Check Hindi and Malayalam
    lang_info = {
        "hi": ("Hindi", "Devanagari", "\\u0900-\\u097F"),
        "ml": ("Malayalam", "Malayalam", "\\u0D00-\\u0D7F"),
    }

    for lang, (lang_name, script_name, unicode_range) in lang_info.items():
        lang_lines = [spoken for voice, spoken in voice_text_pairs if voice_language_code(voice) == lang]
        if lang_lines:
            matched = sum(1 for spoken in lang_lines if has_expected_script(spoken, lang))
            total = len(lang_lines)
            if matched == 0:
                error = (
                    f"Selected {lang_name} voice pair requires native {script_name} Unicode script ({unicode_range}). "
                    f"Edge-TTS {lang_name} neural voices produce broken or garbled speech when fed Romanized {lang_name if lang == 'hi' else 'Manglish'} or Latin characters. "
                    f"To fix this, re-copy the updated {lang_name} prompt so Gemini generates native-script 'tts_text' alongside Romanized 'text', "
                    f"or switch to an English voice pair."
                )
                return error, warnings
            if matched < total:
                unmatched = total - matched
                warnings.append(
                    f"{unmatched} of {total} line(s) for {lang_name} voice lack native {script_name} characters and may sound unnatural."
                )

    # Check English
    en_lines = [spoken for voice, spoken in voice_text_pairs if voice_language_code(voice) == "en"]
    if en_lines:
        matched = sum(1 for spoken in en_lines if has_latin(spoken))
        total = len(en_lines)
        if matched == 0:
            error = (
                "Selected English voice pair requires Latin characters. "
                "Pure Indic native script cannot be synthesized by English neural voices. "
                "To fix this, select a Hindi or Malayalam voice pair or provide English/Romanized text."
            )
            return error, warnings
        if matched < total:
            unmatched = total - matched
            warnings.append(
                f"{unmatched} of {total} line(s) for English voice lack Latin characters and may sound unnatural."
            )

    return None, warnings
