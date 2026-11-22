"""Comprehensive test suite for Indic TTS dual-script support, normalization, and validation."""

import asyncio
import json
from pathlib import Path
import unicodedata

from fastapi.testclient import TestClient
import fitz
import pytest

import app as app_module
from deepexamcast.indic_text import (
    MALAYALAM_CHILLU_MAP,
    has_devanagari,
    has_expected_script,
    has_latin,
    has_malayalam,
    normalize_tts_text,
    resolve_spoken_text,
    validate_script_for_voices,
    voice_language_code,
)
from deepexamcast.models import Chunk, ScriptLine, SessionData, compute_audio_hash
from deepexamcast.prompt_builder import build_prompt
from deepexamcast.script_parser import parse_gemini_script
from deepexamcast.tts_engine import spoken_text_for_line, synthesize_lines


def _sample_chunk() -> Chunk:
    return Chunk(id="C1", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="Operating systems fundamentals.")


def _fake_mp3_bytes(size: int = 4800) -> bytes:
    return bytes([0xFF, 0xFB, 0x30, 0x00]) + (b"\x55" * (size - 4))


# ---------------------------------------------------------------------------
# 1. Indic Text Normalization & Script Detection Tests
# ---------------------------------------------------------------------------

def test_normalize_tts_text_all_six_malayalam_chillus():
    """Verify all 6 legacy ZWJ chillu sequences map to atomic Unicode 5.1+ chillus."""
    for legacy_seq, atomic_chillu in MALAYALAM_CHILLU_MAP.items():
        assert len(legacy_seq) == 3
        assert len(atomic_chillu) == 1
        res = normalize_tts_text(f"prefix {legacy_seq} suffix")
        assert res == f"prefix {atomic_chillu} suffix"

    # Test real Malayalam words using legacy ZWJ sequences:
    # അവൻ (avan): അ + വ + ൻ (legacy ന + ് + ZWJ)
    legacy_avan = "\u0D05\u0D35\u0D28\u0D4D\u200D"
    normalized_avan = normalize_tts_text(legacy_avan)
    assert normalized_avan == "അവൻ"
    assert "\u0D7B" in normalized_avan

    # അവൾ (aval): അ + വ + ൾ (legacy ള + ് + ZWJ)
    legacy_aval = "\u0D05\u0D35\u0D33\u0D4D\u200D"
    assert normalize_tts_text(legacy_aval) == "അവൾ"


def test_normalize_tts_text_nfc_zwnj_preservation_and_ascii_identity():
    """Verify NFC composition, ZWNJ preservation, and ASCII byte identity."""
    # ASCII is byte-for-byte identical
    ascii_sample = "Hello World! This is an exam prep podcast 123."
    assert normalize_tts_text(ascii_sample) == ascii_sample

    # Legitimate ZWNJ (\u200C) must NOT be stripped
    zwnj_sample = "പാൽ\u200C"
    norm_zwnj = normalize_tts_text(zwnj_sample)
    assert "\u200C" in norm_zwnj

    # NFC composition of Malayalam split vowel signs (െ + ാ -> ൊ)
    decomposed = "\u0D15\u0D46\u0D3E"
    composed = "\u0D15\u0D4A"
    assert normalize_tts_text(decomposed) == composed


def test_script_detection_helpers():
    """Verify language code extraction and script boolean detection."""
    assert voice_language_code("ml-IN-MidhunNeural") == "ml"
    assert voice_language_code("ml-IN-SobhanaNeural") == "ml"
    assert voice_language_code("hi-IN-MadhurNeural") == "hi"
    assert voice_language_code("hi-IN-SwaraNeural") == "hi"
    assert voice_language_code("en-US-AndrewMultilingualNeural") == "en"
    assert voice_language_code("en-IN-PrabhatNeural") == "en"
    assert voice_language_code("") == ""

    assert has_devanagari("नमस्ते दोस्तो") is True
    assert has_devanagari("Hello world") is False

    assert has_malayalam("നമസ്കാരം സുഹൃത്തുക്കളെ") is True
    assert has_malayalam("Hello world") is False

    assert has_latin("Hello 123") is True
    assert has_latin("12345 !") is False
    assert has_latin("മലയാളം") is False

    assert has_expected_script("नमस्ते", "hi") is True
    assert has_expected_script("Hello", "hi") is False
    assert has_expected_script("നമസ്കാരം", "ml") is True
    assert has_expected_script("Hello", "ml") is False
    assert has_expected_script("Hello", "en") is True
    assert has_expected_script("നമസ്കാരം", "en") is False


# ---------------------------------------------------------------------------
# 2. Spoken Text Resolution Tests
# ---------------------------------------------------------------------------

def test_resolve_spoken_text_dual_script_and_legacy_native():
    """Verify resolve_spoken_text chooses tts_text when native, or text when legacy."""
    ml_voice = "ml-IN-MidhunNeural"
    hi_voice = "hi-IN-MadhurNeural"

    # Dual-script normal case: Manglish display text, native Malayalam tts_text
    spoken, swapped = resolve_spoken_text(
        text="Innu nammal CPU scheduling padikkam.",
        tts_text="ഇന്ന് നമ്മൾ സി പി യു ഷെഡ്യൂളിംഗ് പഠിക്കാം.",
        voice=ml_voice,
    )
    assert spoken == "ഇന്ന് നമ്മൾ സി പി യു ഷെഡ്യൂളിംഗ് പഠിക്കാം."
    assert swapped is False

    # Dual-script normal case: Hinglish display text, native Devanagari tts_text
    spoken_hi, swapped_hi = resolve_spoken_text(
        text="Aaj hum CPU scheduling samjhenge.",
        tts_text="आज हम सी पी यू शेड्यूलिंग समझेंगे।",
        voice=hi_voice,
    )
    assert spoken_hi == "आज हम सी पी यू शेड्यूलिंग समझेंगे।"
    assert swapped_hi is False

    # Legacy native-only script (tts_text is None)
    spoken_leg, swapped_leg = resolve_spoken_text(
        text="നമസ്കാരം, ഇത് പഴയ സ്ക്രിപ്റ്റ് ആണ്.",
        tts_text=None,
        voice=ml_voice,
    )
    assert spoken_leg == "നമസ്കാരം, ഇത് പഴയ സ്ക്രിപ്റ്റ് ആണ്."
    assert swapped_leg is False


def test_resolve_spoken_text_swapped_recovery():
    """Verify safe recovery when Gemini accidentally swaps text and tts_text."""
    ml_voice = "ml-IN-MidhunNeural"

    # Accidental swap: text has Malayalam, tts_text has Romanized Manglish
    spoken, swapped = resolve_spoken_text(
        text="ഇന്ന് നമ്മൾ പഠിക്കാം.",
        tts_text="Innu nammal padikkam.",
        voice=ml_voice,
    )
    assert spoken == "ഇന്ന് നമ്മൾ പഠിക്കാം."
    assert swapped is True


def test_resolve_spoken_text_english_voice_safety():
    """Verify English voice receives Romanized text, never Indic Unicode tts_text."""
    en_voice = "en-US-AndrewMultilingualNeural"

    # Bilingual line passed to English voice -> must pick text (Romanized)
    spoken, swapped = resolve_spoken_text(
        text="Innu nammal CPU scheduling padikkam.",
        tts_text="ഇന്ന് നമ്മൾ സി പി യു ഷെഡ്യൂളിംഗ് പഠിക്കാം.",
        voice=en_voice,
    )
    assert spoken == "Innu nammal CPU scheduling padikkam."
    assert swapped is False

    # English text + English tts_text -> uses tts_text
    spoken_en, swapped_en = resolve_spoken_text(
        text="Display text.",
        tts_text="Spoken text phonetically.",
        voice=en_voice,
    )
    assert spoken_en == "Spoken text phonetically."
    assert swapped_en is False


# ---------------------------------------------------------------------------
# 3. Voice & Script Validation Tests
# ---------------------------------------------------------------------------

def test_validate_script_for_voices_blocking_errors():
    """Verify 100% Romanized on Indic voices or 100% Indic on English voices is blocked."""
    ml_voice = "ml-IN-MidhunNeural"
    hi_voice = "hi-IN-MadhurNeural"
    en_voice = "en-US-AndrewMultilingualNeural"

    # 100% Romanized Manglish on Malayalam voice -> blocked
    err, warns = validate_script_for_voices([(ml_voice, "Innu nammal padikkam.")])
    assert err is not None
    assert "Malayalam" in err
    assert "Edge-TTS" in err
    assert "tts_text" in err

    # 100% Romanized Hinglish on Hindi voice -> blocked
    err_hi, _ = validate_script_for_voices([(hi_voice, "Aaj hum padhenge.")])
    assert err_hi is not None
    assert "Hindi" in err_hi
    assert "Devanagari" in err_hi

    # Pure Indic on English voice -> blocked
    err_en, _ = validate_script_for_voices([(en_voice, "മലയാളം മാത്രം")])
    assert err_en is not None
    assert "English voice" in err_en
    assert "Latin" in err_en


def test_validate_script_for_voices_warnings_and_success():
    """Verify valid scripts pass and partial missing scripts emit non-blocking warnings."""
    ml_voice = "ml-IN-MidhunNeural"

    # 100% valid native script -> passes with 0 warnings
    err, warns = validate_script_for_voices([
        (ml_voice, "ഇന്ന് നമ്മൾ പഠിക്കാം."),
        (ml_voice, "ശരി സാർ, തുടങ്ങാം."),
    ])
    assert err is None
    assert warns == []

    # Partial missing: 1 line native, 1 line purely ASCII/digits -> warning, no block
    err_part, warns_part = validate_script_for_voices([
        (ml_voice, "ഇന്ന് നമ്മൾ പഠിക്കാം."),
        (ml_voice, "123 456"),
    ])
    assert err_part is None
    assert len(warns_part) == 1
    assert "1 of 2 line(s)" in warns_part[0]
    assert "Malayalam" in warns_part[0]


# ---------------------------------------------------------------------------
# 4. Script Parser Dual-Script & Normalization Tests
# ---------------------------------------------------------------------------

def test_script_parser_extracts_tts_text_and_normalizes():
    """Verify parser extracts tts_text, supports aliases, and normalizes chillus."""
    raw = json.dumps([
        {
            "speaker": "HOST_A",
            "text": "**Innu** nammal padikkam.",
            "tts_text": "ഇന്ന് നമ്മൾ \u0D05\u0D35\u0D28\u0D4D\u200D പഠിക്കാം.",  # contains legacy chillu
            "chunk_ids": ["C1"],
            "exam_note": "Core concept",
        },
        {
            "speaker": "HOST_B",
            "text": "Sheri sir.",
            "spoken_text": "ശരി സാർ.",  # alias spoken_text
            "chunk_ids": ["C1"],
        },
    ])
    res = parse_gemini_script(raw, {"C1"})
    assert len(res.items) == 2

    item1 = res.items[0]
    assert item1.text == "Innu nammal padikkam."  # markdown stripped
    assert item1.tts_text == "ഇന്ന് നമ്മൾ അവൻ പഠിക്കാം."  # chillu normalized to \u0D7B
    assert "\u0D7B" in item1.tts_text

    item2 = res.items[1]
    assert item2.text == "Sheri sir."
    assert item2.tts_text == "ശരി സാർ."


def test_script_parser_backward_compatible_without_tts_text():
    """Verify parser handles scripts without tts_text cleanly."""
    raw = json.dumps([
        {"speaker": "HOST_A", "text": "English line.", "chunk_ids": ["C1"]},
    ])
    res = parse_gemini_script(raw, {"C1"})
    assert len(res.items) == 1
    assert res.items[0].text == "English line."
    assert res.items[0].tts_text is None


# ---------------------------------------------------------------------------
# 5. Prompt Builder Dual-Script Guidance Tests
# ---------------------------------------------------------------------------

def test_prompt_builder_en_unchanged_and_indic_dual_script():
    """Verify English prompt schema has 4 fields, and Indic prompts enforce dual-script."""
    chunk = _sample_chunk()

    # English prompt: must have exactly 4-field schema (speaker, text, chunk_ids, exam_note)
    en_pr = build_prompt([chunk], page_count=1, start_page=1, end_page=1, language="en")
    assert '"tts_text"' not in en_pr.prompt
    assert '"speaker": "HOST_A"' in en_pr.prompt
    assert '"text": "Spoken dialogue here..."' in en_pr.prompt

    # Hindi prompt: dual-script profile and schema
    hi_pr = build_prompt([chunk], page_count=1, start_page=1, end_page=1, language="hi")
    assert "Hinglish" in hi_pr.prompt
    assert "Devanagari" in hi_pr.prompt
    assert '"tts_text"' in hi_pr.prompt
    assert "बी एफ एस" in hi_pr.prompt  # phonetic technical term example

    # Malayalam prompt: dual-script profile and schema
    ml_pr = build_prompt([chunk], page_count=1, start_page=1, end_page=1, language="ml")
    assert "Manglish" in ml_pr.prompt
    assert "Malayalam script" in ml_pr.prompt
    assert '"tts_text"' in ml_pr.prompt
    assert "ബി എഫ് എസ്" in ml_pr.prompt  # phonetic technical term example


# ---------------------------------------------------------------------------
# 6. TTS Engine Synthesis with Dual-Script
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tts_engine_synthesizes_tts_text_not_text(tmp_path: Path, monkeypatch):
    """Verify edge_tts.Communicate receives normalized tts_text, not Manglish text."""
    spoken_inputs: list[str] = []

    class MockCommunicate:
        def __init__(self, text: str, voice: str):
            self.text = text
            self.voice = voice
            spoken_inputs.append(text)

        async def save(self, path: str) -> None:
            Path(path).write_bytes(_fake_mp3_bytes(4800))

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", MockCommunicate)

    line = ScriptLine(
        index=0,
        speaker="HOST_A",
        text="Innu nammal padikkam.",
        tts_text="ഇന്ന് നമ്മൾ അവൻ പഠിക്കാം.",
        chunk_ids=["C1"],
        voice="ml-IN-MidhunNeural",
        audio_hash=compute_audio_hash("ml-IN-MidhunNeural", "ഇന്ന് നമ്മൾ അവൻ പഠിക്കാം."),
        audio_file=f"{compute_audio_hash('ml-IN-MidhunNeural', 'ഇന്ന് നമ്മൾ അവൻ പഠിക്കാം.')}.mp3",
    )

    assert spoken_text_for_line(line) == "ഇന്ന് നമ്മൾ അവൻ പഠിക്കാം."

    res = await synthesize_lines(tmp_path, [line])
    assert res.generated_count == 1
    assert len(spoken_inputs) == 1
    assert spoken_inputs[0] == "ഇന്ന് നമ്മൾ അവൻ പഠിക്കാം."
    assert "Innu" not in spoken_inputs[0]


# ---------------------------------------------------------------------------
# 7. End-to-End API Integration Tests (Dual-Script Lifecycle)
# ---------------------------------------------------------------------------

def _build_test_pdf(text: str) -> bytes:
    doc = fitz.open()
    p = doc.new_page(width=600, height=800)
    p.insert_textbox(fitz.Rect(60, 100, 540, 220), text)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    static_dir = tmp_path / "static"
    vendor_dir = static_dir / "vendor"
    vendor_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html>DeepExamCast</html>", encoding="utf-8")
    (vendor_dir / "pdf.min.mjs").write_text("export const ok = true;", encoding="utf-8")

    class FakeCommunicate:
        def __init__(self, text: str, voice: str):
            self.text = text
            self.voice = voice

        async def save(self, path: str) -> None:
            await asyncio.sleep(0.01)
            Path(path).write_bytes(_fake_mp3_bytes(4800))

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", FakeCommunicate)
    application = app_module.create_app(sessions_dir=sessions_dir, static_dir=static_dir)
    return TestClient(application)


def test_api_generate_and_resynthesize_dual_script_lifecycle(api_client):
    """Test full API lifecycle with bilingual Malayalam script, resynthesize to English and back."""
    pdf_bytes = _build_test_pdf("Algorithm analysis and CPU scheduling.")
    up = api_client.post(
        "/api/upload",
        files={"file": ("lecture.pdf", pdf_bytes, "application/pdf")},
    )
    assert up.status_code == 200
    sid = up.json()["session"]["session_id"]

    # 1. Reject 100% Romanized Manglish on Malayalam voice pair
    bad_gen = api_client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([
                {"speaker": "HOST_A", "text": "Innu nammal CPU scheduling padikkam.", "chunk_ids": ["C1"]}
            ]),
            "host_a_voice": "ml-IN-MidhunNeural",
            "host_b_voice": "ml-IN-SobhanaNeural",
            "mode": "replace",
        },
    )
    assert bad_gen.status_code == 400
    assert "Malayalam" in bad_gen.json()["detail"]
    assert "tts_text" in bad_gen.json()["detail"]

    # 2. Succeed with dual-script JSON (Manglish text + Malayalam tts_text)
    good_gen = api_client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([
                {
                    "speaker": "HOST_A",
                    "text": "Innu nammal CPU scheduling padikkam.",
                    "tts_text": "ഇന്ന് നമ്മൾ സി പി യു ഷെഡ്യൂളിംഗ് പഠിക്കാം.",
                    "chunk_ids": ["C1"],
                },
                {
                    "speaker": "HOST_B",
                    "text": "Athe sir, enthaanu scheduling algorithm?",
                    "tts_text": "അതെ സർ, എന്താണ് ഷെഡ്യൂളിംഗ് അൽഗോരിതം?",
                    "chunk_ids": ["C1"],
                },
            ]),
            "host_a_voice": "ml-IN-MidhunNeural",
            "host_b_voice": "ml-IN-SobhanaNeural",
            "mode": "replace",
        },
    )
    assert good_gen.status_code == 200
    g_data = good_gen.json()
    script = g_data["session"]["script"]
    assert len(script) == 2
    # text is Romanized Manglish for UI display
    assert script[0]["text"] == "Innu nammal CPU scheduling padikkam."
    # tts_text is native Malayalam
    assert script[0]["tts_text"] == "ഇന്ന് നമ്മൾ സി പി യു ഷെഡ്യൂളിംഗ് പഠിക്കാം."
    # audio hash matches the Malayalam tts_text
    expected_hash = compute_audio_hash("ml-IN-MidhunNeural", "ഇന്ന് നമ്മൾ സി പി യു ഷെഡ്യൂളിംഗ് പഠിക്കാം.")
    assert script[0]["audio_hash"] == expected_hash

    # 3. Resynthesize to English voice (US Natural)
    # resolve_spoken_text picks Romanized text, avoiding Indic chars on English voices -> succeeds!
    resyn_en = api_client.post(
        f"/api/sessions/{sid}/resynthesize",
        json={
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
        },
    )
    assert resyn_en.status_code == 200
    en_script = resyn_en.json()["session"]["script"]
    assert len(en_script) == 2
    # Preserves both text and tts_text
    assert en_script[0]["text"] == "Innu nammal CPU scheduling padikkam."
    assert en_script[0]["tts_text"] == "ഇന്ന് നമ്മൾ സി പി യു ഷെഡ്യൂളിംഗ് പഠിക്കാം."
    # audio_hash now matches the spoken Romanized text for English voice
    expected_en_hash = compute_audio_hash("en-US-AndrewMultilingualNeural", "Innu nammal CPU scheduling padikkam.")
    assert en_script[0]["audio_hash"] == expected_en_hash

    # 4. Resynthesize back to Malayalam voice -> succeeds and uses preserved tts_text!
    resyn_ml = api_client.post(
        f"/api/sessions/{sid}/resynthesize",
        json={
            "host_a_voice": "ml-IN-MidhunNeural",
            "host_b_voice": "ml-IN-SobhanaNeural",
        },
    )
    assert resyn_ml.status_code == 200
    ml_script = resyn_ml.json()["session"]["script"]
    assert ml_script[0]["audio_hash"] == expected_hash


def test_api_resynthesize_rejects_english_only_script_on_malayalam_voice(api_client):
    """Test that resynthesizing a pure English script into Malayalam voices is rejected with 400."""
    pdf_bytes = _build_test_pdf("Operating system concurrency.")
    up = api_client.post(
        "/api/upload",
        files={"file": ("os.pdf", pdf_bytes, "application/pdf")},
    )
    sid = up.json()["session"]["session_id"]

    # Generate pure English script on US Natural
    gen = api_client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([
                {"speaker": "HOST_A", "text": "Let us discuss semaphores.", "chunk_ids": ["C1"]}
            ]),
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
            "mode": "replace",
        },
    )
    assert gen.status_code == 200

    # Resynthesize to Malayalam voice -> 400 blocking error (no Malayalam characters available)
    resyn_fail = api_client.post(
        f"/api/sessions/{sid}/resynthesize",
        json={
            "host_a_voice": "ml-IN-MidhunNeural",
            "host_b_voice": "ml-IN-SobhanaNeural",
        },
    )
    assert resyn_fail.status_code == 400
    assert "Malayalam" in resyn_fail.json()["detail"]


def test_legacy_session_json_with_tts_text_omitted_deserializes_cleanly():
    """Verify SessionData with legacy ScriptLine (no tts_text field) deserializes with None."""
    legacy_line = {
        "index": 0,
        "speaker": "HOST_A",
        "text": "Legacy line text.",
        "chunk_ids": ["C1"],
        "voice": "en-US-AndrewMultilingualNeural",
        "audio_hash": "a" * 32,
        "audio_file": f"{'a' * 32}.mp3",
    }
    line = ScriptLine.model_validate(legacy_line)
    assert line.text == "Legacy line text."
    assert line.tts_text is None
