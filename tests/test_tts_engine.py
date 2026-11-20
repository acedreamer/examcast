import asyncio
from pathlib import Path
import pytest

from deepexamcast.models import ScriptLine, compute_audio_hash
from deepexamcast.tts_engine import (
    TtsSynthesisError,
    estimate_mp3_duration_sec,
    gc_unreferenced_audio,
    synthesize_lines,
)


def _line(idx: int, text: str, voice: str = "en-US-AndrewMultilingualNeural") -> ScriptLine:
    h = compute_audio_hash(voice, text)
    return ScriptLine(
        index=idx,
        speaker="HOST_A",
        text=text,
        chunk_ids=["C1"],
        voice=voice,
        audio_hash=h,
        audio_file=f"{h}.mp3",
    )


def _fake_mp3_bytes(payload_len: int = 6000) -> bytes:
    # Valid MPEG1 Layer III 48kbps frame header: 0xFF 0xFB 0x30 0x00 (bitrate index 3 => 48 kbps)
    header = bytes([0xFF, 0xFB, 0x30, 0x00])
    return header + (b"\xAA" * (payload_len - len(header)))


@pytest.mark.asyncio
async def test_synthesize_respects_concurrency_and_caches_and_dedups(tmp_path: Path, monkeypatch):
    active = 0
    max_active = 0
    calls: list[str] = []

    class FakeCommunicate:
        def __init__(self, text: str, voice: str):
            self.text = text
            self.voice = voice

        async def save(self, path: str) -> None:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            calls.append(self.text)
            await asyncio.sleep(0.03)
            Path(path).write_bytes(_fake_mp3_bytes(12000))
            active -= 1

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", FakeCommunicate)

    # Line 0 and Line 4 have identical (voice, text) => in-batch deduplication
    lines = [_line(i, f"Sentence {i % 4}") for i in range(6)]
    progress_events: list[bool] = []

    res = await synthesize_lines(
        tmp_path,
        lines,
        concurrency=2,
        progress_cb=lambda cached: progress_events.append(cached),
        base_backoff_sec=0.01,
    )

    assert max_active <= 2
    assert res.total_lines == 6
    assert res.generated_count == 4
    assert res.cached_count == 2
    assert len(progress_events) == 6
    assert all(line.duration_sec > 1.5 for line in res.lines)

    # Second run hits content-addressed cache 100% even with lines reordered
    reordered = [res.lines[2].model_copy(update={"index": 0}), res.lines[0].model_copy(update={"index": 1})]
    calls.clear()
    res2 = await synthesize_lines(tmp_path, reordered, concurrency=2)
    assert calls == []
    assert res2.generated_count == 0
    assert res2.cached_count == 2


@pytest.mark.asyncio
async def test_retry_recovery_and_timeout_and_partial_isolation(tmp_path: Path, monkeypatch):
    attempts: dict[str, int] = {}

    class FlakyCommunicate:
        def __init__(self, text: str, voice: str):
            self.text = text

        async def save(self, path: str) -> None:
            attempts[self.text] = attempts.get(self.text, 0) + 1
            if self.text == "flaky" and attempts[self.text] < 3:
                raise RuntimeError("transient 503")
            if self.text == "hang":
                await asyncio.sleep(0.5)
            Path(path).write_bytes(_fake_mp3_bytes(6000))

    monkeypatch.setattr("deepexamcast.tts_engine.edge_tts.Communicate", FlakyCommunicate)

    # Successful recovery on flaky line
    res = await synthesize_lines(
        tmp_path,
        [_line(0, "flaky")],
        max_attempts=3,
        timeout_sec=0.2,
        base_backoff_sec=0.01,
    )
    assert res.generated_count == 1
    assert attempts["flaky"] == 3

    # Timeout failure leaves completed clip cached while raising TtsSynthesisError
    attempts.clear()
    with pytest.raises(TtsSynthesisError) as exc_info:
        await synthesize_lines(
            tmp_path,
            [_line(0, "good"), _line(1, "hang")],
            max_attempts=2,
            timeout_sec=0.05,
            base_backoff_sec=0.01,
        )
    assert exc_info.value.failed_line_index == 1
    good_file = tmp_path / _line(0, "good").audio_file
    assert good_file.exists() and good_file.stat().st_size > 0


def test_estimate_mp3_duration_with_id3_header_and_gc_handles_permission_error(tmp_path: Path, monkeypatch):
    id3_header = b"ID3\x03\x00\x00\x00\x00\x00\x10" + (b"\x00" * 16)
    mp3_path = tmp_path / ("a" * 32 + ".mp3")
    mp3_path.write_bytes(id3_header + _fake_mp3_bytes(12000))
    # 12000 bytes * 8 / 48000 bps = 2.0 sec
    assert estimate_mp3_duration_sec(mp3_path) == 2.0

    keep_file = "a" * 32 + ".mp3"
    locked_file = tmp_path / ("b" * 32 + ".mp3")
    orphan_file = tmp_path / ("c" * 32 + ".mp3")
    locked_file.write_bytes(b"locked")
    orphan_file.write_bytes(b"orphan")

    real_unlink = Path.unlink

    def flaky_unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name == locked_file.name:
            raise PermissionError("simulated Windows lock")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    removed = gc_unreferenced_audio(tmp_path, {keep_file})
    assert removed == 1
    assert mp3_path.exists()
    assert locked_file.exists()
    assert not orphan_file.exists()
