"""Pydantic domain schemas and built-in voice pair registry for DeepExamCast."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field


LanguageCode = Literal["en", "hi", "ml"]
PacingMode = Literal["deep_dive", "revision", "exam_drill", "eli5"]
ChunkType = Literal["text", "table", "formula", "figure", "chart"]

PACING_BATCH_LIMITS: dict[str, tuple[int, int, int]] = {
    # pacing: (max_chunks, max_chars, max_pages)
    "deep_dive": (20, 9000, 4),
    "revision": (32, 13000, 5),
    "exam_drill": (24, 10000, 4),
    "eli5": (20, 9000, 4),
}


class VoicePair(BaseModel):
    id: str
    label: str
    language: LanguageCode = "en"
    host_a_voice: str
    host_b_voice: str


VOICE_PAIRS: list[VoicePair] = [
    VoicePair(
        id="us_natural",
        label="US Natural",
        language="en",
        host_a_voice="en-US-AndrewMultilingualNeural",
        host_b_voice="en-US-AvaMultilingualNeural",
    ),
    VoicePair(
        id="in_english",
        label="Indian English",
        language="en",
        host_a_voice="en-IN-PrabhatNeural",
        host_b_voice="en-IN-NeerjaExpressiveNeural",
    ),
    VoicePair(
        id="uk_natural",
        label="UK Natural",
        language="en",
        host_a_voice="en-GB-RyanNeural",
        host_b_voice="en-GB-SoniaNeural",
    ),
    VoicePair(
        id="hi_in",
        label="Hindi · Madhur & Swara",
        language="hi",
        host_a_voice="hi-IN-MadhurNeural",
        host_b_voice="hi-IN-SwaraNeural",
    ),
    VoicePair(
        id="ml_in",
        label="Malayalam · Midhun & Sobhana",
        language="ml",
        host_a_voice="ml-IN-MidhunNeural",
        host_b_voice="ml-IN-SobhanaNeural",
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
    chunk_type: ChunkType = "text"


class ScriptLine(BaseModel):
    index: int
    speaker: Literal["HOST_A", "HOST_B"]
    text: str
    tts_text: str | None = None
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
    pacing: PacingMode | None = None
    language: LanguageCode | None = None


class StudyState(BaseModel):
    last_line_index: int = 0
    playback_rate: float = 1.0
    voice_pair_id: str = DEFAULT_VOICE_PAIR_ID
    host_a_voice: str = VOICE_PAIRS[0].host_a_voice
    host_b_voice: str = VOICE_PAIRS[0].host_b_voice
    auto_scroll: bool = True
    pacing: PacingMode = "deep_dive"
    language: LanguageCode = "en"


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
    is_complete: bool = False


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
    pacing: PacingMode | None = None
    language: LanguageCode | None = None


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
    pacing: PacingMode | None = None
    language: LanguageCode | None = None


class ReparseRequest(BaseModel):
    use_vision: bool = True


class GenerateProgress(BaseModel):
    running: bool = False
    phase: Literal["idle", "synthesizing", "committing"] = "idle"
    completed: int = 0
    cached: int = 0
    total: int = 0
    failed: int = 0
