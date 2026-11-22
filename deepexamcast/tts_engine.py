"""Hardened content-addressed edge-tts synthesis, pure-Python MP3 duration, and GC."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import random
from typing import Callable
import uuid

import edge_tts
from pydantic import BaseModel

from deepexamcast.indic_text import resolve_spoken_text
from deepexamcast.models import ScriptLine

_MPEG1_L3_BITRATES = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_MPEG2_L3_BITRATES = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
_FALLBACK_BITRATE_BPS = 48000


class TtsSynthesisError(RuntimeError):
    """Raised when one or more clips fail synthesis after retries."""

    def __init__(
        self,
        message: str,
        *,
        failed_line_index: int,
        generated_count: int,
        cached_count: int,
    ) -> None:
        super().__init__(message)
        self.failed_line_index = failed_line_index
        self.generated_count = generated_count
        self.cached_count = cached_count


class SynthesisResult(BaseModel):
    lines: list[ScriptLine]
    generated_count: int
    cached_count: int
    total_lines: int


def spoken_text_for_line(line: ScriptLine) -> str:
    """Return the normalized text to be spoken by edge-tts for this line."""
    return resolve_spoken_text(line.text, line.tts_text, line.voice)[0]


def get_tts_concurrency() -> int:
    """Return configured TTS concurrency clamped to [1, 5]."""
    raw = os.getenv("DEEPEXAMCAST_TTS_CONCURRENCY", "4")
    try:
        val = int(raw)
    except ValueError:
        val = 4
    return max(1, min(5, val))


def estimate_mp3_duration_sec(path: Path) -> float:
    """Estimate MP3 clip duration in seconds using MPEG frame headers (zero ffmpeg)."""
    try:
        file_size = path.stat().st_size
    except OSError:
        return 0.0
    if file_size <= 0:
        return 0.0

    try:
        with path.open("rb") as fh:
            head = fh.read(8192)
    except OSError:
        return 0.0

    audio_offset = 0
    if len(head) >= 10 and head[:3] == b"ID3":
        tag_size = (
            ((head[6] & 0x7F) << 21)
            | ((head[7] & 0x7F) << 14)
            | ((head[8] & 0x7F) << 7)
            | (head[9] & 0x7F)
        )
        audio_offset = 10 + tag_size
        if audio_offset >= len(head):
            try:
                with path.open("rb") as fh:
                    fh.seek(audio_offset)
                    scan_buf = fh.read(8192)
            except OSError:
                scan_buf = b""
        else:
            scan_buf = head[audio_offset:]
    else:
        scan_buf = head

    bitrate_bps = _FALLBACK_BITRATE_BPS
    for i in range(max(0, len(scan_buf) - 3)):
        b0 = scan_buf[i]
        b1 = scan_buf[i + 1]
        b2 = scan_buf[i + 2]
        if b0 == 0xFF and (b1 & 0xE0) == 0xE0:
            version_id = (b1 >> 3) & 0x03
            layer = (b1 >> 1) & 0x03
            bitrate_idx = (b2 >> 4) & 0x0F
            if version_id != 1 and layer == 1 and 0 < bitrate_idx < 15:
                kbps = (
                    _MPEG1_L3_BITRATES[bitrate_idx]
                    if version_id == 3
                    else _MPEG2_L3_BITRATES[bitrate_idx]
                )
                if kbps > 0:
                    bitrate_bps = kbps * 1000
                    break

    payload_bytes = max(1, file_size - audio_offset)
    return round(max(0.1, (payload_bytes * 8.0) / bitrate_bps), 2)


async def _synthesize_single_clip(
    sem: asyncio.Semaphore,
    audio_dir: Path,
    line: ScriptLine,
    timeout_sec: float,
    max_attempts: int,
    base_backoff_sec: float,
) -> Path:
    target_path = audio_dir / line.audio_file
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        tmp_path = audio_dir / f".{line.audio_hash}.{uuid.uuid4().hex}.tmp"
        try:
            async with sem:
                if target_path.exists() and target_path.stat().st_size > 0:
                    return target_path
                spoken_text = spoken_text_for_line(line)
                comm = edge_tts.Communicate(spoken_text, line.voice)
                await asyncio.wait_for(comm.save(str(tmp_path)), timeout=timeout_sec)

            if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
                raise RuntimeError("edge-tts produced an empty audio file.")
            os.replace(tmp_path, target_path)
            return target_path
        except Exception as exc:
            last_error = exc
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            if attempt + 1 < max_attempts:
                delay = (base_backoff_sec * (2**attempt)) * (0.7 + 0.6 * random.random())
                await asyncio.sleep(delay)

    raise RuntimeError(
        f"TTS synthesis failed on line {line.index} after {max_attempts} attempt(s): {last_error}"
    ) from last_error


async def synthesize_lines(
    audio_dir: Path,
    lines: list[ScriptLine],
    concurrency: int | None = None,
    timeout_sec: float = 30.0,
    max_attempts: int = 3,
    progress_cb: Callable[[bool], None] | None = None,
    base_backoff_sec: float = 1.5,
) -> SynthesisResult:
    """Synthesize content-addressed .mp3 files concurrently with cache hits & dedup."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    effective_concurrency = max(1, min(5, concurrency)) if concurrency is not None else get_tts_concurrency()
    sem = asyncio.Semaphore(effective_concurrency)

    in_flight: dict[str, asyncio.Task[Path]] = {}
    generated_count = 0
    cached_count = 0
    updated_lines: list[ScriptLine | None] = [None] * len(lines)

    async def process_line(pos: int, line: ScriptLine) -> tuple[int, ScriptLine, bool]:
        nonlocal generated_count, cached_count
        target_path = audio_dir / line.audio_file
        if target_path.exists() and target_path.stat().st_size > 0:
            cached_count += 1
            if progress_cb is not None:
                progress_cb(True)
            dur = estimate_mp3_duration_sec(target_path)
            return pos, line.model_copy(update={"duration_sec": dur}), True

        task = in_flight.get(line.audio_hash)
        is_owner = False
        if task is None:
            is_owner = True
            task = asyncio.create_task(
                _synthesize_single_clip(
                    sem,
                    audio_dir,
                    line,
                    timeout_sec=timeout_sec,
                    max_attempts=max_attempts,
                    base_backoff_sec=base_backoff_sec,
                )
            )
            in_flight[line.audio_hash] = task

        resolved_path = await task
        if is_owner:
            generated_count += 1
            if progress_cb is not None:
                progress_cb(False)
        else:
            cached_count += 1
            if progress_cb is not None:
                progress_cb(True)

        dur = estimate_mp3_duration_sec(resolved_path)
        return pos, line.model_copy(update={"duration_sec": dur}), not is_owner

    outcomes = await asyncio.gather(
        *(process_line(pos, line) for pos, line in enumerate(lines)),
        return_exceptions=True,
    )

    first_error: tuple[int, Exception] | None = None
    for pos, outcome in enumerate(outcomes):
        if isinstance(outcome, Exception):
            if first_error is None:
                first_error = (lines[pos].index, outcome)
        else:
            idx_pos, updated_line, _was_cached = outcome
            updated_lines[idx_pos] = updated_line

    if first_error is not None:
        failed_idx, exc = first_error
        raise TtsSynthesisError(
            str(exc),
            failed_line_index=failed_idx,
            generated_count=generated_count,
            cached_count=cached_count,
        ) from exc

    final_lines = [line for line in updated_lines if line is not None]
    return SynthesisResult(
        lines=final_lines,
        generated_count=generated_count,
        cached_count=cached_count,
        total_lines=len(final_lines),
    )


def gc_unreferenced_audio(audio_dir: Path, keep_filenames: set[str]) -> int:
    """Best-effort cleanup of unreferenced .mp3 files (tolerates Windows PermissionError)."""
    if not audio_dir.exists():
        return 0
    removed = 0
    for entry in audio_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".mp3":
            continue
        if entry.name in keep_filenames:
            continue
        try:
            entry.unlink()
            removed += 1
        except (PermissionError, OSError):
            continue
    return removed
