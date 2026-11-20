from deepexamcast.models import (
    DEFAULT_VOICE_PAIR_ID,
    VOICE_PAIRS,
    StudyState,
    compute_audio_hash,
    match_voice_pair_id,
)


def test_voice_pairs_and_matching():
    assert len(VOICE_PAIRS) == 3
    assert VOICE_PAIRS[0].id == DEFAULT_VOICE_PAIR_ID == "us_natural"
    assert match_voice_pair_id("en-IN-PrabhatNeural", "en-IN-NeerjaExpressiveNeural") == "in_english"
    assert match_voice_pair_id("en-GB-RyanNeural", "en-GB-SoniaNeural") == "uk_natural"
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


def test_default_study_state():
    state = StudyState()
    assert state.voice_pair_id == "us_natural"
    assert state.host_a_voice == "en-US-AndrewMultilingualNeural"
    assert state.host_b_voice == "en-US-AvaMultilingualNeural"
    assert state.playback_rate == 1.0
    assert state.auto_scroll is True
    assert state.last_line_index == 0
