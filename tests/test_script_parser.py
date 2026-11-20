import json
import pytest

from deepexamcast.script_parser import ScriptParseError, parse_gemini_script


def test_parse_plain_and_fenced_and_prose_arrays():
    raw = (
        "Here is your script for pages [1, 5]:\n"
        "```json\n"
        '[{"speaker": "host_a", "text": "**Bold** x^2 [check]!", "chunk_ids": "c1", "exam_note": "  Key fact  "},\n'
        ' {"speaker": "HOST_B", "text": "Got it, thanks!", "chunk_ids": ["C1", "C99", "C1"]}]\n'
        "```\n"
        "Let me know if you want the next batch!"
    )
    res = parse_gemini_script(raw, {"C1", "C2"})
    assert len(res.items) == 2
    assert res.items[0].speaker == "HOST_A"
    assert res.items[0].text == "Bold x^2 [check]!"
    assert res.items[0].chunk_ids == ["C1"]
    assert res.items[0].exam_note == "Key fact"
    assert res.items[1].speaker == "HOST_B"
    assert res.items[1].chunk_ids == ["C1"]
    assert any("C99" in w for w in res.warnings)


def test_parse_wrapper_object_prefers_longest_dialogue_list():
    raw = json.dumps(
        {
            "covered_chunks": ["C1", "C2"],
            "dialogue": [
                {"speaker": "HOST_A", "text": "First explanation", "chunk_ids": ["C1"]},
                {"speaker": "HOST_B", "text": "Second question", "chunk_ids": ["C2"]},
            ],
        }
    )
    res = parse_gemini_script(raw, {"C1", "C2"})
    assert len(res.items) == 2
    assert res.items[0].text == "First explanation"


def test_single_item_typo_surfaces_exact_item_error():
    items = [
        {"speaker": "HOST_A", "text": f"Line {i}", "chunk_ids": ["C1"]}
        for i in range(1, 6)
    ]
    items[3] = {"speker": "HOST_A", "text": "Line 4", "chunk_ids": ["C1"]}
    with pytest.raises(ScriptParseError, match=r"Item 4.*speaker"):
        parse_gemini_script(json.dumps(items), {"C1"})


def test_unicode_multilingual_speakable_accepted_but_symbols_rejected():
    ok = parse_gemini_script(
        '[{"speaker": "HOST_A", "text": "अध्याय एक में स्वागत है — café résumé!", "chunk_ids": ["C1"]}]',
        {"C1"},
    )
    assert len(ok.items) == 1

    with pytest.raises(ScriptParseError, match="speakable"):
        parse_gemini_script(
            '[{"speaker": "HOST_A", "text": "... — ***", "chunk_ids": ["C1"]}]',
            {"C1"},
        )


def test_invalid_or_empty_json_raises_informative_error():
    with pytest.raises(ScriptParseError):
        parse_gemini_script("   ", {"C1"})
    with pytest.raises(ScriptParseError):
        parse_gemini_script("[]", {"C1"})
    with pytest.raises(ScriptParseError, match="line"):
        parse_gemini_script('[{"speaker": "HOST_A", "text": "unclosed"', {"C1"})


def test_pure_devanagari_and_malayalam_lines_are_speakable():
    res = parse_gemini_script(
        json.dumps(
            [
                {"speaker": "HOST_A", "text": "नमस्ते दोस्तों, आज हम खोज एल्गोरिदम समझेंगे।", "chunk_ids": ["C1"]},
                {"speaker": "HOST_B", "text": "നമസ്കാരം, ഇന്ന് നമ്മൾ സെർച്ച് അൽഗോരിതം പഠിക്കാം. അവൻ, അൾ", "chunk_ids": ["C1"]},
            ],
            ensure_ascii=False,
        ),
        {"C1"},
    )
    assert len(res.items) == 2
    with pytest.raises(ScriptParseError, match="speakable"):
        parse_gemini_script('[{"speaker": "HOST_A", "text": "। ॥ — …", "chunk_ids": ["C1"]}]', {"C1"})
