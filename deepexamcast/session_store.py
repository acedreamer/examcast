"""Disk session persistence, per-session asyncio locks, undo snapshots, and chunk coverage."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from deepexamcast.models import (
    PACING_BATCH_LIMITS,
    BatchRecord,
    Chunk,
    CoverageInfo,
    GenerateProgress,
    PacingMode,
    PageCoverage,
    PageInfo,
    ScriptLine,
    SessionData,
    SessionSummary,
    StudyState,
    SuggestedRange,
)

SESSION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,80}$")
AUDIO_FILE_RE = re.compile(r"^[0-9a-f]{32}\.mp3$")
_NON_SLUG_RE = re.compile(r"[^a-z0-9_-]+")
_MULTI_DASH_RE = re.compile(r"-{2,}")

MAX_BATCH_CHUNKS, MAX_BATCH_CHARS, MAX_BATCH_PAGES = PACING_BATCH_LIMITS["deep_dive"]


class SessionNotFoundError(KeyError):
    """Raised when a requested session directory or session.json does not exist."""


class InvalidSessionIdError(ValueError):
    """Raised when session_id or filename fails strict allowlist validation."""


class SessionConflictError(RuntimeError):
    """Raised when a mutation collides with an in-progress generation on the same session."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_session_id(filename: str) -> str:
    """Generate a path-safe ASCII session ID ending in -<6hex> with 'doc' fallback."""
    stem = Path(filename or "doc").stem.lower()
    slug = _NON_SLUG_RE.sub("-", stem)
    slug = _MULTI_DASH_RE.sub("-", slug).strip("-_")
    if not slug or not any("a" <= ch <= "z" for ch in slug):
        slug = "doc"
    slug = slug[:70].rstrip("-_") or "doc"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def compute_coverage(session: SessionData, pacing: PacingMode | None = None) -> CoverageInfo:
    """Compute chunk-level coverage and pacing-budgeted next-batch range from session.script."""
    effective_pacing = pacing or session.state.pacing or "deep_dive"
    max_chunks, max_chars, max_pages = PACING_BATCH_LIMITS.get(
        effective_pacing, PACING_BATCH_LIMITS["deep_dive"]
    )
    valid_ids = {c.id for c in session.chunks}
    covered_set = {
        cid
        for line in session.script
        for cid in line.chunk_ids
        if cid in valid_ids
    }
    covered_chunk_ids = [c.id for c in session.chunks if c.id in covered_set]

    chunks_by_page: dict[int, list[Chunk]] = {p: [] for p in range(1, session.page_count + 1)}
    for chunk in session.chunks:
        chunks_by_page.setdefault(chunk.page, []).append(chunk)

    pages_coverage: list[PageCoverage] = []
    fully_covered_pages: list[int] = []
    partial_pages: list[PageCoverage] = []

    for page_num in range(1, session.page_count + 1):
        p_chunks = chunks_by_page.get(page_num, [])
        total = len(p_chunks)
        missed = [c.id for c in p_chunks if c.id not in covered_set]
        covered = total - len(missed)
        if total == 0:
            status = "empty"
        elif covered == 0:
            status = "uncovered"
        elif covered < total:
            status = "partial"
        else:
            status = "full"

        pc = PageCoverage(
            page=page_num,
            covered_chunks=covered,
            total_chunks=total,
            missed_chunk_ids=missed,
            status=status,
        )
        pages_coverage.append(pc)
        if status == "full":
            fully_covered_pages.append(page_num)
        elif status == "partial":
            partial_pages.append(pc)

    start_page = 1
    for pc in pages_coverage:
        if pc.status in ("uncovered", "partial"):
            start_page = pc.page
            break

    max_page = max(1, session.page_count)
    end_limit = min(start_page + max_pages - 1, max_page)
    first_chunks = chunks_by_page.get(start_page, [])
    cum_chunks = len(first_chunks)
    cum_chars = sum(len(c.text) for c in first_chunks)
    end_page = start_page

    for q in range(start_page + 1, end_limit + 1):
        q_chunks = chunks_by_page.get(q, [])
        q_count = len(q_chunks)
        q_chars = sum(len(c.text) for c in q_chunks)
        if cum_chunks + q_count <= max_chunks and cum_chars + q_chars <= max_chars:
            end_page = q
            cum_chunks += q_count
            cum_chars += q_chars
        else:
            break

    estimated_total_sec = round(sum(line.duration_sec for line in session.script), 2)
    is_complete = bool(session.chunks) and len(covered_chunk_ids) >= len(session.chunks)

    return CoverageInfo(
        total_chunks=len(session.chunks),
        covered_chunk_count=len(covered_chunk_ids),
        covered_chunk_ids=covered_chunk_ids,
        pages_coverage=pages_coverage,
        fully_covered_pages=fully_covered_pages,
        partial_pages=partial_pages,
        suggested_next_range=SuggestedRange(
            start_page=start_page,
            end_page=end_page,
            chunk_count=cum_chunks,
            char_count=cum_chars,
        ),
        estimated_total_sec=estimated_total_sec,
        is_complete=is_complete,
    )


def compute_missed_chunks(
    session: SessionData,
    batch_lines: list[ScriptLine],
    start_page: int | None,
    end_page: int | None,
) -> tuple[list[int] | None, list[str]]:
    """Return (page_range, missed_chunk_ids) comparing batch lines against page span."""
    chunk_by_id = {c.id: c for c in session.chunks}
    batch_covered = {
        cid
        for line in batch_lines
        for cid in line.chunk_ids
        if cid in chunk_by_id
    }

    if start_page is not None and end_page is not None:
        sp = max(1, start_page)
        ep = min(session.page_count, end_page)
        if sp > ep:
            return None, []
    else:
        ref_pages = [chunk_by_id[cid].page for cid in batch_covered]
        if not ref_pages:
            return None, []
        sp, ep = min(ref_pages), max(ref_pages)

    missed = [
        c.id
        for c in session.chunks
        if sp <= c.page <= ep and c.id not in batch_covered
    ]
    return [sp, ep], missed


class SessionStore:
    """Thread/async-safe manager for ./sessions/<session_id>/ artifacts."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path("sessions")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self.active_generations: set[str] = set()
        self.progress_map: dict[str, GenerateProgress] = {}

    def validate_session_id(self, session_id: str) -> str:
        if not SESSION_ID_RE.match(session_id or ""):
            raise InvalidSessionIdError(f"Invalid session_id: {session_id!r}")
        return session_id

    def get_lock(self, session_id: str) -> asyncio.Lock:
        self.validate_session_id(session_id)
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    def is_generating(self, session_id: str) -> bool:
        return session_id in self.active_generations

    def try_begin_generation(self, session_id: str, total_lines: int) -> None:
        self.validate_session_id(session_id)
        if session_id in self.active_generations:
            raise SessionConflictError("Audio generation is already running for this session.")
        self.active_generations.add(session_id)
        self.progress_map[session_id] = GenerateProgress(
            running=True,
            phase="synthesizing",
            completed=0,
            cached=0,
            total=total_lines,
            failed=0,
        )

    def record_progress(self, session_id: str, *, cached: bool = False) -> None:
        prog = self.progress_map.get(session_id)
        if prog is None:
            return
        prog.completed += 1
        if cached:
            prog.cached += 1

    def set_progress_phase(self, session_id: str, phase: str) -> None:
        prog = self.progress_map.get(session_id)
        if prog is not None:
            prog.phase = phase  # type: ignore[assignment]

    def end_generation(self, session_id: str) -> None:
        self.active_generations.discard(session_id)
        self.progress_map[session_id] = GenerateProgress()

    def get_progress(self, session_id: str) -> GenerateProgress:
        self.validate_session_id(session_id)
        return self.progress_map.get(session_id, GenerateProgress())

    def session_dir(self, session_id: str) -> Path:
        self.validate_session_id(session_id)
        return self.base_dir / session_id

    def audio_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "audio"

    def raw_scripts_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "raw_scripts"

    def get_pdf_path(self, session_id: str) -> Path:
        path = self.session_dir(session_id) / "source.pdf"
        if not path.is_file():
            raise SessionNotFoundError(f"Session PDF not found for {session_id!r}")
        return path

    def get_audio_path(self, session_id: str, filename: str) -> Path:
        self.validate_session_id(session_id)
        if not AUDIO_FILE_RE.match(filename or ""):
            raise InvalidSessionIdError(f"Invalid audio filename: {filename!r}")
        path = self.audio_dir(session_id) / filename
        if not path.is_file():
            raise SessionNotFoundError(f"Audio clip {filename!r} not found.")
        return path

    def new_batch_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"b_{stamp}_{uuid.uuid4().hex[:6]}"

    def create_session(
        self,
        title: str,
        pdf_bytes: bytes,
        pages: list[PageInfo],
        chunks: list[Chunk],
    ) -> SessionData:
        session_id = make_session_id(title)
        sdir = self.session_dir(session_id)
        now = utc_now_iso()
        session = SessionData(
            session_id=session_id,
            title=title or f"{session_id}.pdf",
            created_at=now,
            updated_at=now,
            page_count=len(pages),
            pages=pages,
            chunks=chunks,
            script=[],
            batches=[],
            state=StudyState(),
        )
        try:
            sdir.mkdir(parents=True, exist_ok=True)
            self.audio_dir(session_id).mkdir(parents=True, exist_ok=True)
            self.raw_scripts_dir(session_id).mkdir(parents=True, exist_ok=True)
            (sdir / "source.pdf").write_bytes(pdf_bytes)
            self.save_session(session)
            return session
        except Exception:
            shutil.rmtree(sdir, ignore_errors=True)
            raise

    def save_session(self, session: SessionData) -> None:
        json_path = self.session_dir(session.session_id) / "session.json"
        _atomic_write_text(json_path, session.model_dump_json(indent=2))

    def load_session(self, session_id: str) -> SessionData:
        json_path = self.session_dir(session_id) / "session.json"
        if not json_path.is_file():
            raise SessionNotFoundError(f"Session {session_id!r} not found.")
        return SessionData.model_validate_json(json_path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[SessionSummary]:
        summaries: list[SessionSummary] = []
        if not self.base_dir.exists():
            return summaries
        for entry in self.base_dir.iterdir():
            if not entry.is_dir() or not SESSION_ID_RE.match(entry.name):
                continue
            json_path = entry / "session.json"
            if not json_path.is_file():
                continue
            try:
                session = SessionData.model_validate_json(json_path.read_text(encoding="utf-8"))
                cov = compute_coverage(session)
                summaries.append(
                    SessionSummary(
                        session_id=session.session_id,
                        title=session.title,
                        page_count=session.page_count,
                        chunk_count=len(session.chunks),
                        covered_chunk_count=cov.covered_chunk_count,
                        fully_covered_page_count=len(cov.fully_covered_pages),
                        line_count=len(session.script),
                        estimated_total_sec=cov.estimated_total_sec,
                        last_line_index=session.state.last_line_index,
                        created_at=session.created_at,
                        updated_at=session.updated_at,
                    )
                )
            except Exception:
                continue
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries

    def delete_session(self, session_id: str) -> None:
        sdir = self.session_dir(session_id)
        if not sdir.exists():
            raise SessionNotFoundError(f"Session {session_id!r} not found.")
        shutil.rmtree(sdir)
        self._locks.pop(session_id, None)
        self.progress_map.pop(session_id, None)

    def save_raw_batch(self, session_id: str, batch_id: str, raw_json: str) -> str:
        rel = f"raw_scripts/{batch_id}.json"
        _atomic_write_text(self.session_dir(session_id) / rel, raw_json)
        return rel

    def save_prev_snapshot(self, session_id: str, batch_id: str, script: list[ScriptLine]) -> str:
        rel = f"raw_scripts/{batch_id}.prev.json"
        payload = json.dumps([line.model_dump() for line in script], indent=2)
        _atomic_write_text(self.session_dir(session_id) / rel, payload)
        return rel

    def load_prev_snapshot(self, session_id: str, rel_path: str) -> list[ScriptLine]:
        target = self.session_dir(session_id) / rel_path
        if not target.is_file():
            return []
        data = json.loads(target.read_text(encoding="utf-8"))
        return [ScriptLine.model_validate(item) for item in data]

    def prune_prev_snapshots(self, session: SessionData, keep_last: int = 3) -> None:
        """Retain only the last `keep_last` replace/resynthesize undo snapshots."""
        snapshot_indices = [
            idx for idx, b in enumerate(session.batches) if b.prev_script_file
        ]
        if len(snapshot_indices) <= keep_last:
            return
        stale_indices = snapshot_indices[:-keep_last]
        sdir = self.session_dir(session.session_id)
        for idx in stale_indices:
            rel = session.batches[idx].prev_script_file
            if rel:
                stale_path = sdir / rel
                if stale_path.exists():
                    try:
                        stale_path.unlink()
                    except OSError:
                        pass
                session.batches[idx].prev_script_file = None

    def collect_retained_audio_filenames(self, session: SessionData) -> set[str]:
        """Collect audio filenames referenced by active script and all retained undo snapshots."""
        keep = {line.audio_file for line in session.script}
        for batch in session.batches:
            if batch.prev_script_file:
                for line in self.load_prev_snapshot(session.session_id, batch.prev_script_file):
                    keep.add(line.audio_file)
        return keep
