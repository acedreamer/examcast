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


def test_deep_dive_injects_budgets_anti_bundling_and_five_beats():
    chunks = [
        Chunk(id=f"C{i}", page=1 + (i - 1) // 3, bbox=[0.1, 0.1, 0.9, 0.2], text=f"Concept {i}")
        for i in range(1, 13)
    ]
    chunks[4] = chunks[4].model_copy(update={"chunk_type": "table", "text": "| a | b |"})
    r = build_prompt(chunks, page_count=4, start_page=1, end_page=4)
    assert r.pacing == "deep_dive"
    assert "24–32 dialogue turns" in r.prompt          # 6*4 – 8*4
    assert "760–920 spoken words" in r.prompt          # 190*4 – 230*4
    assert "NEVER bundle more than 2–3" in r.prompt
    for beat in ("Intuition", "Formal Definition", "Analogy", "Confusion Check", "Exam Takeaway"):
        assert beat in r.prompt
    assert "[C5] (Page 2) [TABLE]: | a | b |" in r.prompt
    assert "[C1] (Page 1): Concept 1" in r.prompt


def test_pacing_profiles_render_distinct_instructions():
    prompts = {
        p: build_prompt(_sample_chunks(), 6, 2, 3, pacing=p).prompt
        for p in ("deep_dive", "revision", "exam_drill", "eli5")
    }
    assert "EXAM NIGHT SPRINT" in prompts["revision"] and "6–8 dialogue turns" in prompts["revision"]
    assert "VIVA" in prompts["exam_drill"] and "7-mark" in prompts["exam_drill"]
    assert "INTUITION FIRST" in prompts["eli5"]
    assert len(set(prompts.values())) == 4
    for p in prompts.values():
        assert "ZERO SKIMMING" in p
    with pytest.raises(PromptBuildError):
        build_prompt(_sample_chunks(), 6, 2, 3, pacing="speedrun")


def test_hindi_and_malayalam_language_rules():
    hi = build_prompt(_sample_chunks(), 6, 2, 3, language="hi").prompt
    ml = build_prompt(_sample_chunks(), 6, 2, 3, language="ml").prompt
    assert "Devanagari" in hi and "exam_note" in hi and "English" in hi
    assert "Malayalam script" in ml and "exam_note" in ml and "English" in ml
