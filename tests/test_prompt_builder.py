import pytest

from deepexamcast.models import Chunk, ScriptLine
from deepexamcast.prompt_builder import PromptBuildError, build_prompt


def _sample_chunks() -> list[Chunk]:
    return [
        Chunk(id="C1", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="Page one intro"),
        Chunk(id="C2", page=2, bbox=[0.1, 0.1, 0.9, 0.2], text="Formula: E = m c^2"),
        Chunk(id="C3", page=3, bbox=[0.1, 0.1, 0.9, 0.2], text="Semaphore prevents race conditions."),
        Chunk(id="C4", page=6, bbox=[0.1, 0.1, 0.9, 0.2], text="Page six scheduling"),
    ]


def test_build_prompt_filters_pages_and_formats_chunks():
    result = build_prompt(_sample_chunks(), page_count=6, start_page=2, end_page=3)
    assert result.start_page == 2
    assert result.end_page == 3
    assert result.chunk_count == 2
    assert result.chunk_id_range == ["C2", "C3"]
    assert result.char_count == len("Formula: E = m c^2") + len("Semaphore prevents race conditions.")
    assert "[C2] (Page 2): Formula: E = m c^2" in result.prompt
    assert "[C3] (Page 3): Semaphore prevents race conditions." in result.prompt
    assert "[C1]" not in result.prompt
    assert "[C4]" not in result.prompt
    assert "ZERO SKIMMING" in result.prompt
    assert "HOST_A" in result.prompt
    assert "HOST_B" in result.prompt
    assert "PREVIOUSLY ON THIS LECTURE" not in result.prompt


def test_build_prompt_includes_continuity_context_on_append():
    recent = [
        ScriptLine(
            index=0,
            speaker="HOST_A",
            text="Let us wrap up paging basics.",
            chunk_ids=["C1"],
            voice="v",
            audio_hash="a" * 32,
            audio_file=f"{'a' * 32}.mp3",
        ),
        ScriptLine(
            index=1,
            speaker="HOST_B",
            text="Got it! What happens when processes share memory?",
            chunk_ids=["C1"],
            voice="v",
            audio_hash="b" * 32,
            audio_file=f"{'b' * 32}.mp3",
        ),
    ]
    result = build_prompt(_sample_chunks(), page_count=6, start_page=2, end_page=3, recent_lines=recent)
    assert "PREVIOUSLY ON THIS LECTURE" in result.prompt
    assert "HOST_B: Got it! What happens when processes share memory?" in result.prompt


def test_build_prompt_validation_errors():
    with pytest.raises(PromptBuildError, match="Invalid page range"):
        build_prompt(_sample_chunks(), page_count=6, start_page=4, end_page=2)
    with pytest.raises(PromptBuildError, match="Invalid page range"):
        build_prompt(_sample_chunks(), page_count=6, start_page=1, end_page=9)
    with pytest.raises(PromptBuildError, match="No extractable text chunks"):
        build_prompt(_sample_chunks(), page_count=6, start_page=4, end_page=5)
