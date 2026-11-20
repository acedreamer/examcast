import asyncio
from pathlib import Path
import pytest

from deepexamcast.models import (
    BatchRecord,
    Chunk,
    PageInfo,
    ScriptLine,
    compute_audio_hash,
)
from deepexamcast.session_store import (
    InvalidSessionIdError,
    SessionStore,
    compute_coverage,
    compute_missed_chunks,
    make_session_id,
)


def test_make_session_id_slugifies_and_falls_back_on_non_ascii():
    sid_en = make_session_id("Ch 04: Deadlocks & Starvation!.pdf")
    assert sid_en.startswith("ch-04-deadlocks-starvation-")
    sid_hi = make_session_id("अध्याय1.pdf")
    assert sid_hi.startswith("doc-")
    sid_dash = make_session_id("---.pdf")
    assert sid_dash.startswith("doc-")
    long_sid = make_session_id(("a" * 120) + ".pdf")
    assert len(long_sid) <= 80


def test_path_traversal_rejected_and_atomic_roundtrip(tmp_path: Path):
    store = SessionStore(tmp_path)
    with pytest.raises(InvalidSessionIdError):
        store.load_session("../etc")
    with pytest.raises(InvalidSessionIdError):
        store.get_audio_path("valid-123456", "../evil.mp3")
    with pytest.raises(InvalidSessionIdError):
        store.get_audio_path("valid-123456", "line_000.mp3")

    pages = [PageInfo(page=1, width=600, height=800, chunk_count=1)]
    chunks = [Chunk(id="C1", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="Intro")]
    session = store.create_session("notes.pdf", b"%PDF-1.4\n%%EOF", pages, chunks)
    loaded = store.load_session(session.session_id)
    assert loaded.title == "notes.pdf"
    assert store.get_pdf_path(session.session_id).read_bytes() == b"%PDF-1.4\n%%EOF"


def test_chunk_level_coverage_budgeted_range_and_missed_chunks(tmp_path: Path):
    store = SessionStore(tmp_path)
    pages = [
        PageInfo(page=1, width=600, height=800, chunk_count=2),
        PageInfo(page=2, width=600, height=800, chunk_count=2),
        PageInfo(page=3, width=600, height=800, chunk_count=30),  # Exceeds 28-chunk budget
    ]
    chunks = [
        Chunk(id="C1", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="A" * 100),
        Chunk(id="C2", page=1, bbox=[0.1, 0.3, 0.9, 0.4], text="B" * 100),
        Chunk(id="C3", page=2, bbox=[0.1, 0.1, 0.9, 0.2], text="C" * 100),
        Chunk(id="C4", page=2, bbox=[0.1, 0.3, 0.9, 0.4], text="D" * 100),
    ] + [
        Chunk(id=f"C{i}", page=3, bbox=[0.1, 0.1, 0.9, 0.2], text="E" * 50)
        for i in range(5, 35)
    ]

    session = store.create_session("chapter.pdf", b"%PDF-1.4", pages, chunks)
    # Initial suggested range stops before page 3 because adding 30 chunks exceeds 28-chunk budget
    cov0 = compute_coverage(session)
    assert cov0.suggested_next_range.start_page == 1
    assert cov0.suggested_next_range.end_page == 2
    assert cov0.suggested_next_range.chunk_count == 4

    # Cover C1 and C3 only -> Page 1 and Page 2 are both partial (NOT full)
    h1 = compute_audio_hash("v", "line1")
    line1 = ScriptLine(
        index=0, speaker="HOST_A", text="line1", chunk_ids=["C1", "C3"],
        voice="v", audio_hash=h1, audio_file=f"{h1}.mp3", duration_sec=2.5,
    )
    session.script = [line1]
    cov1 = compute_coverage(session)
    assert cov1.fully_covered_pages == []
    assert [p.page for p in cov1.partial_pages] == [1, 2]
    assert cov1.pages_coverage[0].missed_chunk_ids == ["C2"]
    assert cov1.suggested_next_range.start_page == 1

    # Explicit and inferred missed chunks
    span_exp, missed_exp = compute_missed_chunks(session, [line1], 1, 2)
    assert span_exp == [1, 2] and missed_exp == ["C2", "C4"]
    span_inf, missed_inf = compute_missed_chunks(session, [line1], None, None)
    assert span_inf == [1, 2] and missed_inf == ["C2", "C4"]


def test_multistep_undo_snapshots_retained_and_pruned_at_3(tmp_path: Path):
    store = SessionStore(tmp_path)
    pages = [PageInfo(page=1, width=600, height=800, chunk_count=1)]
    chunks = [Chunk(id="C1", page=1, bbox=[0.1, 0.1, 0.9, 0.2], text="Text")]
    session = store.create_session("undo.pdf", b"%PDF-1.4", pages, chunks)

    for step in range(4):
        bid = f"b_{step}"
        h = compute_audio_hash("v", f"t{step}")
        prev = [ScriptLine(index=0, speaker="HOST_A", text=f"old{step}", chunk_ids=["C1"], voice="v", audio_hash=h, audio_file=f"{h}.mp3")]
        rel = store.save_prev_snapshot(session.session_id, bid, prev)
        session.batches.append(
            BatchRecord(batch_id=bid, timestamp="2026-11-20T00:00:00Z", mode="replace", start_index=0, line_count=1, prev_script_file=rel)
        )

    store.prune_prev_snapshots(session, keep_last=3)
    assert session.batches[0].prev_script_file is None
    assert session.batches[1].prev_script_file is not None
    assert session.batches[2].prev_script_file is not None
    assert session.batches[3].prev_script_file is not None

    retained = store.collect_retained_audio_filenames(session)
    assert len(retained) == 3


def test_pacing_budgets_and_is_complete(tmp_path: Path):
    store = SessionStore(tmp_path)
    pages = [PageInfo(page=p, width=600, height=800, chunk_count=7) for p in range(1, 9)]
    chunks = [
        Chunk(id=f"C{i}", page=1 + (i - 1) // 7, bbox=[0.1, 0.1, 0.9, 0.2], text="X" * 300)
        for i in range(1, 57)
    ]
    s = store.create_session("budget.pdf", b"%PDF-1.4", pages, chunks)
    dd = compute_coverage(s).suggested_next_range
    assert dd.chunk_count <= 20 and dd.char_count <= 9000 and dd.end_page - dd.start_page + 1 <= 4
    rv = compute_coverage(s, pacing="revision").suggested_next_range
    assert rv.chunk_count <= 32 and rv.end_page - rv.start_page + 1 <= 5
    assert rv.end_page > dd.end_page
    assert compute_coverage(s).is_complete is False

    # Mark all chunks covered -> is_complete True
    h = compute_audio_hash("v", "all")
    s.script = [
        ScriptLine(
            index=0,
            speaker="HOST_A",
            text="all",
            chunk_ids=[c.id for c in chunks],
            voice="v",
            audio_hash=h,
            audio_file=f"{h}.mp3",
        )
    ]
    assert compute_coverage(s).is_complete is True
