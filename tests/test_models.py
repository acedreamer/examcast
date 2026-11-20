from deepexamcast.models import (
    DEFAULT_VOICE_PAIR_ID,
    PACING_BATCH_LIMITS,
    VOICE_PAIRS,
    BatchRecord,
    Chunk,
    CoverageInfo,
    ReparseRequest,
    SessionData,
    StudyState,
    SuggestedRange,
    compute_audio_hash,
    match_voice_pair_id,
)


def test_voice_pairs_and_matching():
    assert len(VOICE_PAIRS) == 5
    assert VOICE_PAIRS[0].id == DEFAULT_VOICE_PAIR_ID == "us_natural"
    by_id = {vp.id: vp for vp in VOICE_PAIRS}
    assert by_id["us_natural"].language == "en"
    assert by_id["in_english"].language == "en"
    assert by_id["uk_natural"].language == "en"
    assert by_id["hi_in"].language == "hi"
    assert by_id["ml_in"].language == "ml"

    assert match_voice_pair_id("en-IN-PrabhatNeural", "en-IN-NeerjaExpressiveNeural") == "in_english"
    assert match_voice_pair_id("en-GB-RyanNeural", "en-GB-SoniaNeural") == "uk_natural"
    assert match_voice_pair_id("hi-IN-MadhurNeural", "hi-IN-SwaraNeural") == "hi_in"
    assert match_voice_pair_id("ml-IN-MidhunNeural", "ml-IN-SobhanaNeural") == "ml_in"
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


def test_default_study_state_and_v3_schemas():
    state = StudyState()
    assert state.voice_pair_id == "us_natural"
    assert state.host_a_voice == "en-US-AndrewMultilingualNeural"
    assert state.host_b_voice == "en-US-AvaMultilingualNeural"
    assert state.playback_rate == 1.0
    assert state.auto_scroll is True
    assert state.last_line_index == 0
    assert state.pacing == "deep_dive"
    assert state.language == "en"

    assert PACING_BATCH_LIMITS["deep_dive"] == (20, 9000, 4)
    assert PACING_BATCH_LIMITS["revision"] == (32, 13000, 5)

    c_default = Chunk(id="C1", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="Text")
    assert c_default.chunk_type == "text"
    for ctype in ("table", "formula", "figure", "chart"):
        c = Chunk(id="C2", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="Data", chunk_type=ctype)
        assert c.chunk_type == ctype

    req = ReparseRequest()
    assert req.use_vision is True


def test_legacy_session_json_backwards_compatible():
    legacy = {
        "session_id": "legacy-123456",
        "title": "legacy.pdf",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "page_count": 1,
        "pages": [{"page": 1, "width": 600.0, "height": 800.0, "chunk_count": 1}],
        "chunks": [{"id": "C1", "page": 1, "bbox": [0.1, 0.1, 0.9, 0.2], "text": "Legacy chunk"}],
        "script": [],
        "batches": [
            {
                "batch_id": "b_1",
                "timestamp": "2026-01-01T00:00:00Z",
                "mode": "replace",
                "start_index": 0,
                "line_count": 0,
            }
        ],
        "state": {
            "last_line_index": 0,
            "playback_rate": 1.25,
            "voice_pair_id": "us_natural",
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
            "auto_scroll": True,
        },
    }
    session = SessionData.model_validate(legacy)
    assert session.chunks[0].chunk_type == "text"
    assert session.state.pacing == "deep_dive"
    assert session.state.language == "en"
    assert session.batches[0].pacing is None
    assert session.batches[0].language is None

    cov = CoverageInfo(
        total_chunks=1,
        covered_chunk_count=0,
        covered_chunk_ids=[],
        pages_coverage=[],
        fully_covered_pages=[],
        partial_pages=[],
        suggested_next_range=SuggestedRange(start_page=1, end_page=1, chunk_count=1, char_count=12),
        estimated_total_sec=0.0,
    )
    assert cov.is_complete is False
