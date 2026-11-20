"""FastAPI application entrypoint for DeepExamCast (`uvicorn app:app`)."""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from deepexamcast.models import (
    VOICE_PAIRS,
    BatchRecord,
    GenerateRequest,
    LanguageCode,
    PacingMode,
    ReparseRequest,
    ResynthesizeRequest,
    ScriptLine,
    SessionData,
    StatePatchRequest,
    compute_audio_hash,
    match_voice_pair_id,
)
from deepexamcast.pdf_parser import PdfParseError
from deepexamcast.prompt_builder import PromptBuildError, build_prompt
from deepexamcast.script_parser import ScriptParseError, parse_gemini_script
from deepexamcast.session_store import (
    InvalidSessionIdError,
    SessionConflictError,
    SessionNotFoundError,
    SessionStore,
    compute_coverage,
    compute_missed_chunks,
    utc_now_iso,
)
from deepexamcast.tts_engine import TtsSynthesisError, gc_unreferenced_audio, synthesize_lines
from deepexamcast.vision_ocr import check_vision_status, extract_pdf_hybrid

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
VENDOR_FILE_RE = re.compile(r"^[a-z0-9._-]+\.(?:mjs|js|css)$", re.IGNORECASE)


def _map_store_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidSessionIdError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, SessionNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SessionConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _session_payload(session: SessionData, warnings: list[str] | None = None) -> dict[str, Any]:
    cov = compute_coverage(session)
    payload: dict[str, Any] = {
        "session": session.model_dump(),
        "coverage": cov.model_dump(),
        "voice_pairs": [vp.model_dump() for vp in VOICE_PAIRS],
    }
    if warnings is not None:
        payload["warnings"] = warnings
    return payload


def create_app(sessions_dir: Path | None = None, static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="DeepExamCast", version="1.0.0")
    store = SessionStore(base_dir=sessions_dir or Path("sessions"))
    resolved_static = static_dir or Path("static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        index_path = resolved_static / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=404, detail="Frontend index.html not found.")
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @app.get("/static/vendor/{filename}")
    async def serve_vendor(filename: str) -> FileResponse:
        if not VENDOR_FILE_RE.match(filename or ""):
            raise HTTPException(status_code=400, detail="Invalid vendor asset filename.")
        target = resolved_static / "vendor" / filename
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Vendor asset not present.")
        ext = target.suffix.lower()
        media_type = "text/css; charset=utf-8" if ext == ".css" else "text/javascript; charset=utf-8"
        return FileResponse(path=target, media_type=media_type)

    @app.get("/api/voices")
    async def get_voices() -> dict[str, Any]:
        return {"voice_pairs": [vp.model_dump() for vp in VOICE_PAIRS]}

    @app.get("/api/vision/status")
    async def get_vision_status() -> dict[str, Any]:
        status = await asyncio.to_thread(check_vision_status)
        return status.model_dump()

    @app.post("/api/upload")
    async def upload_pdf(
        file: UploadFile = File(...),
        use_vision: bool = Form(True),
    ) -> dict[str, Any]:
        chunks_buf = bytearray()
        total_bytes = 0
        first_chunk = True
        try:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="PDF upload exceeds the 100 MB maximum size.")
                if first_chunk:
                    first_chunk = False
                    if not chunk.lstrip().startswith(b"%PDF-"):
                        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF (%PDF- header missing).")
                chunks_buf.extend(chunk)
        finally:
            await file.close()

        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="Uploaded PDF file is empty.")

        pdf_bytes = bytes(chunks_buf)
        try:
            parsed_pdf = await asyncio.to_thread(extract_pdf_hybrid, pdf_bytes, use_vision=use_vision)
        except PdfParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        title = Path(file.filename or "lecture.pdf").name
        session = await asyncio.to_thread(
            store.create_session, title, pdf_bytes, parsed_pdf.pages, parsed_pdf.chunks
        )
        warnings = list(parsed_pdf.warnings)
        if not parsed_pdf.chunks:
            warnings.append(
                "No selectable text blocks were extracted from this PDF (it may be scanned or image-only)."
            )
        payload = _session_payload(session, warnings=warnings)
        payload["vision_used"] = parsed_pdf.vision_used
        return payload

    @app.get("/api/sessions")
    async def list_sessions() -> dict[str, Any]:
        items = await asyncio.to_thread(store.list_sessions)
        return {"sessions": [item.model_dump() for item in items]}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        try:
            session = await asyncio.to_thread(store.load_session, session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc
        return _session_payload(session)

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict[str, str]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            if store.is_generating(session_id):
                raise HTTPException(status_code=409, detail="Cannot delete session while audio generation is running.")
            try:
                await asyncio.to_thread(store.delete_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc
        return {"deleted": session_id}

    @app.get("/api/sessions/{session_id}/pdf")
    async def get_session_pdf(session_id: str) -> FileResponse:
        try:
            pdf_path = await asyncio.to_thread(store.get_pdf_path, session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc
        return FileResponse(path=pdf_path, media_type="application/pdf")

    @app.post("/api/sessions/{session_id}/reparse")
    async def reparse_session_pdf(
        session_id: str,
        req: ReparseRequest = ReparseRequest(),
    ) -> dict[str, Any]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            if store.is_generating(session_id):
                raise HTTPException(status_code=409, detail="Cannot re-parse PDF while audio generation is running.")
            try:
                pdf_path = await asyncio.to_thread(store.get_pdf_path, session_id)
                pdf_bytes = await asyncio.to_thread(pdf_path.read_bytes)
            except Exception as exc:
                raise _map_store_error(exc) from exc

        try:
            parsed_pdf = await asyncio.to_thread(extract_pdf_hybrid, pdf_bytes, use_vision=req.use_vision)
        except PdfParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        async with lock:
            if store.is_generating(session_id):
                raise HTTPException(status_code=409, detail="Cannot re-parse PDF while audio generation is running.")
            try:
                fresh = await asyncio.to_thread(store.load_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc

            fresh.pages = parsed_pdf.pages
            fresh.chunks = parsed_pdf.chunks
            fresh.page_count = len(parsed_pdf.pages)
            fresh.updated_at = utc_now_iso()
            await asyncio.to_thread(store.save_session, fresh)

        warnings = list(parsed_pdf.warnings)
        if fresh.script:
            warnings.append(
                "PDF chunks were re-extracted; existing script chunk highlights may need regeneration if page structure changed."
            )
        payload = _session_payload(fresh, warnings=warnings)
        payload["vision_used"] = parsed_pdf.vision_used
        return payload

    @app.get("/api/sessions/{session_id}/prompt")
    async def get_prompt(
        session_id: str,
        start_page: int = Query(1, ge=1),
        end_page: int = Query(5, ge=1),
        pacing: PacingMode | None = Query(None),
        language: LanguageCode | None = Query(None),
    ) -> dict[str, Any]:
        try:
            session = await asyncio.to_thread(store.load_session, session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        try:
            result = build_prompt(
                session.chunks,
                session.page_count,
                start_page,
                end_page,
                recent_lines=session.script or None,
                pacing=pacing or session.state.pacing,
                language=language or session.state.language,
            )
        except PromptBuildError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.model_dump()

    @app.get("/api/sessions/{session_id}/generate/status")
    async def get_generate_status(session_id: str) -> dict[str, Any]:
        try:
            prog = store.get_progress(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc
        return prog.model_dump()

    @app.post("/api/sessions/{session_id}/generate")
    async def generate_audio(session_id: str, req: GenerateRequest) -> dict[str, Any]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            if store.is_generating(session_id):
                raise HTTPException(status_code=409, detail="Audio generation is already running for this session.")
            try:
                snapshot = await asyncio.to_thread(store.load_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc

            valid_ids = {c.id for c in snapshot.chunks}
            try:
                parsed = parse_gemini_script(req.raw_json, valid_ids)
            except ScriptParseError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            base_index = 0 if req.mode == "replace" else len(snapshot.script)
            target_lines: list[ScriptLine] = []
            for offset, item in enumerate(parsed.items):
                voice = req.host_a_voice if item.speaker == "HOST_A" else req.host_b_voice
                ahash = compute_audio_hash(voice, item.text)
                target_lines.append(
                    ScriptLine(
                        index=base_index + offset,
                        speaker=item.speaker,
                        text=item.text,
                        chunk_ids=item.chunk_ids,
                        exam_note=item.exam_note,
                        voice=voice,
                        audio_hash=ahash,
                        audio_file=f"{ahash}.mp3",
                    )
                )

            try:
                store.try_begin_generation(session_id, len(target_lines))
            except Exception as exc:
                raise _map_store_error(exc) from exc

        try:
            try:
                synth = await synthesize_lines(
                    store.audio_dir(session_id),
                    target_lines,
                    progress_cb=lambda cached: store.record_progress(session_id, cached=cached),
                )
            except TtsSynthesisError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"{exc}. {exc.generated_count} new clip(s) and {exc.cached_count} cached clip(s) "
                        "are saved on disk; retry Generate to resume cleanly."
                    ),
                ) from exc

            store.set_progress_phase(session_id, "committing")
            batch_id = store.new_batch_id()
            raw_rel = await asyncio.to_thread(store.save_raw_batch, session_id, batch_id, req.raw_json)

            async with lock:
                fresh = await asyncio.to_thread(store.load_session, session_id)
                prev_rel: str | None = None
                if req.mode == "replace" and fresh.script:
                    prev_rel = await asyncio.to_thread(store.save_prev_snapshot, session_id, batch_id, fresh.script)

                if req.mode == "replace":
                    fresh.script = synth.lines
                    fresh.state.last_line_index = 0
                    actual_start = 0
                else:
                    actual_start = len(fresh.script)
                    reindexed = [
                        line.model_copy(update={"index": actual_start + idx})
                        for idx, line in enumerate(synth.lines)
                    ]
                    fresh.script = fresh.script + reindexed

                eff_pacing = req.pacing or fresh.state.pacing
                eff_language = req.language or fresh.state.language
                page_range, missed_ids = compute_missed_chunks(fresh, synth.lines, req.start_page, req.end_page)
                fresh.batches.append(
                    BatchRecord(
                        batch_id=batch_id,
                        timestamp=utc_now_iso(),
                        mode=req.mode,
                        start_index=actual_start,
                        line_count=len(synth.lines),
                        page_range=page_range,
                        raw_script_file=raw_rel,
                        prev_script_file=prev_rel,
                        pacing=eff_pacing,
                        language=eff_language,
                    )
                )
                await asyncio.to_thread(store.prune_prev_snapshots, fresh, 3)

                fresh.state.host_a_voice = req.host_a_voice
                fresh.state.host_b_voice = req.host_b_voice
                fresh.state.voice_pair_id = match_voice_pair_id(req.host_a_voice, req.host_b_voice)
                if req.pacing is not None:
                    fresh.state.pacing = req.pacing
                if req.language is not None:
                    fresh.state.language = req.language
                max_idx = max(0, len(fresh.script) - 1)
                fresh.state.last_line_index = max(0, min(fresh.state.last_line_index, max_idx))
                fresh.updated_at = utc_now_iso()

                await asyncio.to_thread(store.save_session, fresh)
                keep_files = await asyncio.to_thread(store.collect_retained_audio_filenames, fresh)
                await asyncio.to_thread(gc_unreferenced_audio, store.audio_dir(session_id), keep_files)

            warnings = list(parsed.warnings)
            if missed_ids and page_range:
                warnings.append(
                    f"Gemini skipped {len(missed_ids)} chunk(s) in Pages {page_range[0]}–{page_range[1]}: {', '.join(missed_ids)}."
                )

            cov = compute_coverage(fresh)
            return {
                "session": fresh.model_dump(),
                "coverage": cov.model_dump(),
                "stats": {
                    "generated_count": synth.generated_count,
                    "cached_count": synth.cached_count,
                    "total_lines": len(fresh.script),
                },
                "missed_chunk_ids": missed_ids,
                "warnings": warnings,
            }
        finally:
            store.end_generation(session_id)

    @app.post("/api/sessions/{session_id}/undo")
    async def undo_last_batch(session_id: str) -> dict[str, Any]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            if store.is_generating(session_id):
                raise HTTPException(status_code=409, detail="Cannot undo while audio generation is running.")
            try:
                session = await asyncio.to_thread(store.load_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc

            if not session.batches:
                raise HTTPException(status_code=400, detail="No script batches available to undo.")

            popped = session.batches.pop()
            if popped.mode == "append":
                session.script = session.script[: popped.start_index]
            else:
                if popped.prev_script_file:
                    session.script = await asyncio.to_thread(
                        store.load_prev_snapshot, session_id, popped.prev_script_file
                    )
                else:
                    session.script = []

            max_idx = max(0, len(session.script) - 1)
            session.state.last_line_index = max(0, min(session.state.last_line_index, max_idx))
            session.updated_at = utc_now_iso()
            await asyncio.to_thread(store.save_session, session)

            keep_files = await asyncio.to_thread(store.collect_retained_audio_filenames, session)
            await asyncio.to_thread(gc_unreferenced_audio, store.audio_dir(session_id), keep_files)

            cov = compute_coverage(session)
            return {
                "session": session.model_dump(),
                "coverage": cov.model_dump(),
                "undone_batch": popped.model_dump(),
            }

    @app.post("/api/sessions/{session_id}/resynthesize")
    async def resynthesize_voices(session_id: str, req: ResynthesizeRequest) -> dict[str, Any]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            if store.is_generating(session_id):
                raise HTTPException(status_code=409, detail="Audio generation is already running for this session.")
            try:
                snapshot = await asyncio.to_thread(store.load_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc

            if not snapshot.script:
                raise HTTPException(status_code=400, detail="Cannot resynthesize voices on an empty script.")

            target_lines: list[ScriptLine] = []
            for idx, line in enumerate(snapshot.script):
                voice = req.host_a_voice if line.speaker == "HOST_A" else req.host_b_voice
                ahash = compute_audio_hash(voice, line.text)
                target_lines.append(
                    line.model_copy(
                        update={
                            "index": idx,
                            "voice": voice,
                            "audio_hash": ahash,
                            "audio_file": f"{ahash}.mp3",
                        }
                    )
                )

            try:
                store.try_begin_generation(session_id, len(target_lines))
            except Exception as exc:
                raise _map_store_error(exc) from exc

        try:
            try:
                synth = await synthesize_lines(
                    store.audio_dir(session_id),
                    target_lines,
                    progress_cb=lambda cached: store.record_progress(session_id, cached=cached),
                )
            except TtsSynthesisError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc}. Completed clips stay cached; retry Re-synthesize to resume.",
                ) from exc

            store.set_progress_phase(session_id, "committing")
            batch_id = store.new_batch_id()

            async with lock:
                fresh = await asyncio.to_thread(store.load_session, session_id)
                prev_rel = await asyncio.to_thread(store.save_prev_snapshot, session_id, batch_id, fresh.script)
                fresh.script = synth.lines
                fresh.batches.append(
                    BatchRecord(
                        batch_id=batch_id,
                        timestamp=utc_now_iso(),
                        mode="resynthesize",
                        start_index=0,
                        line_count=len(synth.lines),
                        page_range=None,
                        raw_script_file=None,
                        prev_script_file=prev_rel,
                    )
                )
                await asyncio.to_thread(store.prune_prev_snapshots, fresh, 3)

                fresh.state.host_a_voice = req.host_a_voice
                fresh.state.host_b_voice = req.host_b_voice
                fresh.state.voice_pair_id = match_voice_pair_id(req.host_a_voice, req.host_b_voice)
                fresh.updated_at = utc_now_iso()

                await asyncio.to_thread(store.save_session, fresh)
                keep_files = await asyncio.to_thread(store.collect_retained_audio_filenames, fresh)
                await asyncio.to_thread(gc_unreferenced_audio, store.audio_dir(session_id), keep_files)

            cov = compute_coverage(fresh)
            return {
                "session": fresh.model_dump(),
                "coverage": cov.model_dump(),
                "stats": {
                    "generated_count": synth.generated_count,
                    "cached_count": synth.cached_count,
                    "total_lines": len(fresh.script),
                },
            }
        finally:
            store.end_generation(session_id)

    @app.get("/api/sessions/{session_id}/audio/{filename}")
    async def get_audio_clip(session_id: str, filename: str) -> FileResponse:
        try:
            audio_path = await asyncio.to_thread(store.get_audio_path, session_id, filename)
        except Exception as exc:
            raise _map_store_error(exc) from exc
        return FileResponse(
            path=audio_path,
            media_type="audio/mpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @app.patch("/api/sessions/{session_id}/state")
    async def patch_state(session_id: str, req: StatePatchRequest) -> dict[str, Any]:
        try:
            lock = store.get_lock(session_id)
        except Exception as exc:
            raise _map_store_error(exc) from exc

        async with lock:
            try:
                session = await asyncio.to_thread(store.load_session, session_id)
            except Exception as exc:
                raise _map_store_error(exc) from exc

            if req.playback_rate is not None:
                if not (0.5 <= req.playback_rate <= 3.0):
                    raise HTTPException(status_code=400, detail="playback_rate must be between 0.5 and 3.0.")
                session.state.playback_rate = round(float(req.playback_rate), 2)

            if req.last_line_index is not None:
                max_idx = max(0, len(session.script) - 1)
                session.state.last_line_index = max(0, min(req.last_line_index, max_idx))

            if req.host_a_voice is not None:
                session.state.host_a_voice = req.host_a_voice
            if req.host_b_voice is not None:
                session.state.host_b_voice = req.host_b_voice

            if req.voice_pair_id is not None:
                session.state.voice_pair_id = req.voice_pair_id
            elif req.host_a_voice is not None or req.host_b_voice is not None:
                session.state.voice_pair_id = match_voice_pair_id(
                    session.state.host_a_voice, session.state.host_b_voice
                )

            if req.auto_scroll is not None:
                session.state.auto_scroll = req.auto_scroll
            if req.pacing is not None:
                session.state.pacing = req.pacing
            if req.language is not None:
                session.state.language = req.language

            session.updated_at = utc_now_iso()
            await asyncio.to_thread(store.save_session, session)
            cov = compute_coverage(session)
            return {"state": session.state.model_dump(), "coverage": cov.model_dump()}

    return app


app = create_app()
