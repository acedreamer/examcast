import asyncio
import json
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
import fitz
import pytest

import app as app_module


def _build_test_pdf(pages_texts: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages_texts:
        p = doc.new_page(width=600, height=800)
        p.insert_textbox(fitz.Rect(60, 100, 540, 220), text)
    data = doc.tobytes()
    doc.close()
    return data


def _fake_mp3(size: int = 4800) -> bytes:
    return bytes([0xFF, 0xFB, 0x30, 0x00]) + (b"\x55" * (size - 4))


@pytest.fixture
def client_and_dirs(tmp_path: Path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    static_dir = tmp_path / "static"
    vendor_dir = static_dir / "vendor"
    vendor_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>DeepExamCast</body></html>", encoding="utf-8")
    (vendor_dir / "pdf.min.mjs").write_text("export const ok = true;", encoding="utf-8")

    class FakeCommunicate:
        def __init__(self, text: str, voice: str):
            self.text = text
            self.voice = voice

        async def save(self, path: str) -> None:
            await asyncio.sleep(0.01)
            Path(path).write_bytes(_fake_mp3(4800))

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", FakeCommunicate)
    application = app_module.create_app(sessions_dir=sessions_dir, static_dir=static_dir)
    return TestClient(application), sessions_dir, static_dir


def test_full_study_lifecycle_undo_resynthesize_delete(client_and_dirs):
    client, _sdir, _static = client_and_dirs

    assert client.get("/").status_code == 200
    assert len(client.get("/api/voices").json()["voice_pairs"]) == 3

    # Explicit JS MIME type on /static/vendor/*.mjs
    vendor_resp = client.get("/static/vendor/pdf.min.mjs")
    assert vendor_resp.status_code == 200
    assert "text/javascript" in vendor_resp.headers["content-type"]
    assert client.get("/static/vendor/../../app.py").status_code in (400, 404)

    # Upload PDF with non-ASCII filename -> 'doc-<6hex>' fallback
    pdf_bytes = _build_test_pdf(["Page one deadlock.", "Page two semaphore."])
    up = client.post(
        "/api/upload",
        files={"file": ("अध्याय1.pdf", pdf_bytes, "application/pdf")},
    )
    assert up.status_code == 200
    data = up.json()
    sid = data["session"]["session_id"]
    assert sid.startswith("doc-")
    assert "raw_scripts" not in data["session"]
    assert client.get(f"/api/sessions/{sid}/pdf").headers["content-type"].startswith("application/pdf")

    # Empty script resynthesize -> 400
    empty_resyn = client.post(
        f"/api/sessions/{sid}/resynthesize",
        json={"host_a_voice": "en-IN-PrabhatNeural", "host_b_voice": "en-IN-NeerjaExpressiveNeural"},
    )
    assert empty_resyn.status_code == 400

    # Prompt
    pr = client.get(f"/api/sessions/{sid}/prompt?start_page=1&end_page=2")
    assert pr.status_code == 200
    assert pr.json()["chunk_id_range"] == ["C1", "C2"]

    # Generate replace covering only C1 -> missed C2 warning
    gen1 = client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([{"speaker": "HOST_A", "text": "Deadlock basics.", "chunk_ids": ["C1"]}]),
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
            "mode": "replace",
            "start_page": 1,
            "end_page": 2,
        },
    )
    assert gen1.status_code == 200
    g1 = gen1.json()
    assert g1["missed_chunk_ids"] == ["C2"]
    assert any("C2" in w for w in g1["warnings"])
    audio1 = g1["session"]["script"][0]["audio_file"]
    assert client.get(f"/api/sessions/{sid}/audio/{audio1}").status_code == 200
    assert client.get(f"/api/sessions/{sid}/audio/bad.mp3").status_code == 400

    # Append C2
    gen2 = client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([{"speaker": "HOST_B", "text": "Semaphore basics.", "chunk_ids": ["C2"]}]),
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
            "mode": "append",
            "start_page": 2,
            "end_page": 2,
        },
    )
    assert gen2.status_code == 200
    assert len(gen2.json()["session"]["script"]) == 2
    assert gen2.json()["coverage"]["fully_covered_pages"] == [1, 2]

    # Resynthesize into Indian English
    resyn = client.post(
        f"/api/sessions/{sid}/resynthesize",
        json={"host_a_voice": "en-IN-PrabhatNeural", "host_b_voice": "en-IN-NeerjaExpressiveNeural"},
    )
    assert resyn.status_code == 200
    assert resyn.json()["session"]["state"]["voice_pair_id"] == "in_english"

    # Multi-step undo: undo resynthesize -> undo append -> audio1 still exists!
    u1 = client.post(f"/api/sessions/{sid}/undo")
    assert u1.status_code == 200
    assert len(u1.json()["session"]["script"]) == 2
    assert u1.json()["session"]["script"][0]["audio_file"] == audio1
    assert client.get(f"/api/sessions/{sid}/audio/{audio1}").status_code == 200

    u2 = client.post(f"/api/sessions/{sid}/undo")
    assert u2.status_code == 200
    assert len(u2.json()["session"]["script"]) == 1
    assert client.get(f"/api/sessions/{sid}/audio/{audio1}").status_code == 200

    # Delete session
    assert client.delete(f"/api/sessions/{sid}").status_code == 200
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_upload_validation_and_size_limit(client_and_dirs, monkeypatch):
    client, _sdir, _static = client_and_dirs
    assert client.post("/api/upload", files={"file": ("x.pdf", b"not-a-pdf", "application/pdf")}).status_code == 400

    monkeypatch.setattr(app_module, "MAX_UPLOAD_BYTES", 200)
    big_pdf = b"%PDF-1.4\n" + (b"0" * 300)
    assert client.post("/api/upload", files={"file": ("big.pdf", big_pdf, "application/pdf")}).status_code == 413


def test_concurrent_patch_preserved_and_409_and_status_reset_on_502(client_and_dirs, monkeypatch):
    client, _sdir, _static = client_and_dirs
    up = client.post(
        "/api/upload",
        files={"file": ("race.pdf", _build_test_pdf(["Chunk one."]), "application/pdf")},
    )
    sid = up.json()["session"]["session_id"]

    entered = threading.Event()
    release = threading.Event()

    class SlowCommunicate:
        def __init__(self, text: str, voice: str):
            self.text = text

        async def save(self, path: str) -> None:
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            Path(path).write_bytes(_fake_mp3())

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", SlowCommunicate)

    results: list[int] = []

    def run_generate() -> None:
        resp = client.post(
            f"/api/sessions/{sid}/generate",
            json={
                "raw_json": json.dumps([{"speaker": "HOST_A", "text": "Slow line.", "chunk_ids": ["C1"]}]),
                "host_a_voice": "en-US-AndrewMultilingualNeural",
                "host_b_voice": "en-US-AvaMultilingualNeural",
                "mode": "replace",
            },
        )
        results.append(resp.status_code)

    t = threading.Thread(target=run_generate)
    t.start()
    assert entered.wait(timeout=3.0)

    # While generating: status is running, second generate gets 409, PATCH /state succeeds and persists
    assert client.get(f"/api/sessions/{sid}/generate/status").json()["running"] is True
    conflict = client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([{"speaker": "HOST_A", "text": "Dup.", "chunk_ids": ["C1"]}]),
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
            "mode": "replace",
        },
    )
    assert conflict.status_code == 409

    patch_resp = client.patch(f"/api/sessions/{sid}/state", json={"playback_rate": 1.5, "auto_scroll": False})
    assert patch_resp.status_code == 200

    release.set()
    t.join(timeout=5.0)
    assert results == [200]

    loaded = client.get(f"/api/sessions/{sid}").json()
    assert loaded["session"]["state"]["playback_rate"] == 1.5
    assert loaded["session"]["state"]["auto_scroll"] is False
    assert client.get(f"/api/sessions/{sid}/generate/status").json()["running"] is False

    # 502 error resets /generate/status back to idle
    class FailCommunicate:
        def __init__(self, text: str, voice: str):
            pass

        async def save(self, path: str) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", FailCommunicate)
    real_sleep = asyncio.sleep
    monkeypatch.setattr("deepexamcast.tts_engine.asyncio.sleep", lambda _s: real_sleep(0))
    fail_resp = client.post(
        f"/api/sessions/{sid}/generate",
        json={
            "raw_json": json.dumps([{"speaker": "HOST_A", "text": "Will fail now.", "chunk_ids": ["C1"]}]),
            "host_a_voice": "en-US-AndrewMultilingualNeural",
            "host_b_voice": "en-US-AvaMultilingualNeural",
            "mode": "replace",
        },
    )
    assert fail_resp.status_code == 502
    assert client.get(f"/api/sessions/{sid}/generate/status").json()["running"] is False
    assert client.get(f"/api/sessions/{sid}").json()["session"]["script"][0]["text"] == "Slow line."
