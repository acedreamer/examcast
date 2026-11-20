import json
import urllib.error

import fitz
import pytest

from deepexamcast import vision_ocr
from deepexamcast.vision_ocr import (
    VisionOcrError,
    VisionStatus,
    check_vision_status,
    extract_pdf_hybrid,
    parse_vision_grounding,
)

GROUNDED = (
    "![title](80,70,920,140) # Uninformed Search\n"
    "![text](80,175,920,225) BFS expands the shallowest node first.\n"
    "![table](80,240,920,400) | Algo | Time |\n| --- | --- |\n| BFS | O(b^d) |\n"
    "![chart](100,420,600,600) Nodes expanded vs depth.\n"
    "![image](100,620,500,800) Search tree diagram.\n"
    "![formula](100,820,600,860) f(n) = g(n) + h(n)\n"
    "![footer](0,960,1000,1000) www.keralanotes.com\n"
)


def _make_hybrid_test_pdf() -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 220, 160), False)
    pix.clear_with(210)
    png_bytes = pix.tobytes("png")

    doc = fitz.open()
    # Page 1: scanned / image-only page (no selectable text)
    p1 = doc.new_page(width=600, height=800)
    p1.insert_image(fitz.Rect(20, 20, 580, 780), stream=png_bytes)

    # Page 2: digital text + raster diagram image
    p2 = doc.new_page(width=600, height=800)
    p2.insert_textbox(fitz.Rect(60, 80, 540, 140), "Heuristic search uses evaluation functions.")
    p2.insert_image(fitz.Rect(120, 240, 480, 460), stream=png_bytes)

    data = doc.tobytes()
    doc.close()
    return data


def test_parse_lightonocr3_grounding_markdown_and_json():
    chunks = parse_vision_grounding(GROUNDED, page_num=3)
    assert [c.chunk_type for c in chunks] == ["text", "text", "table", "chart", "figure", "formula"]
    assert chunks[1].bbox == [0.08, 0.175, 0.92, 0.225]
    assert all(0.0 <= v <= 1.0 for c in chunks for v in c.bbox)
    assert "| BFS | O(b^d) |" in chunks[2].text
    assert not any("keralanotes" in c.text for c in chunks)

    js = json.dumps([{"type": "table", "bbox": [0, 0, 500, 500], "text": "| a | b |"}])
    jchunks = parse_vision_grounding(js, page_num=1)
    assert jchunks[0].chunk_type == "table"
    assert jchunks[0].bbox == [0.0, 0.0, 0.5, 0.5]

    crop = parse_vision_grounding(
        "A flowchart of agent percepts.",
        2,
        crop_bbox=[0.2, 0.3, 0.8, 0.6],
        default_type="figure",
    )
    assert crop[0].bbox == [0.2, 0.3, 0.8, 0.6]
    assert crop[0].chunk_type == "figure"


def test_hybrid_ocr_enriches_scanned_page_and_figure_crop(monkeypatch):
    pdf_bytes = _make_hybrid_test_pdf()

    monkeypatch.setattr(
        vision_ocr,
        "check_vision_status",
        lambda timeout=1.5: VisionStatus(available=True, url="http://127.0.0.1:8081/v1", model="lightonocr-3"),
    )

    def fake_call(image_png_bytes: bytes, prompt: str, *, timeout: float | None = None) -> str:
        assert len(image_png_bytes) > 0
        if prompt.strip().lower() == "grounding":
            return GROUNDED
        return "Diagram showing A* search expanding lowest f(n) node first."

    monkeypatch.setattr(vision_ocr, "call_vision_ocr", fake_call)

    res = extract_pdf_hybrid(pdf_bytes, use_vision=True)
    assert res.vision_used is True
    assert res.vision_pages_processed == 1
    assert res.vision_crops_processed == 1
    assert [c.id for c in res.chunks] == [f"C{i}" for i in range(1, len(res.chunks) + 1)]
    assert sum(p.chunk_count for p in res.pages) == len(res.chunks)

    p1_chunks = [c for c in res.chunks if c.page == 1]
    p2_chunks = [c for c in res.chunks if c.page == 2]
    assert len(p1_chunks) == 6
    assert any("Heuristic search uses evaluation functions." in c.text for c in p2_chunks)
    assert any("Diagram showing A* search" in c.text and c.chunk_type == "figure" for c in p2_chunks)
    assert not any("[FIGURE/CHART on Page 2]" in c.text for c in p2_chunks)


def test_hybrid_ocr_graceful_fallback_when_offline_or_timeout(monkeypatch):
    pdf_bytes = _make_hybrid_test_pdf()

    # Case 1: Server offline
    monkeypatch.setattr(
        vision_ocr,
        "check_vision_status",
        lambda timeout=1.5: VisionStatus(available=False, url="http://127.0.0.1:8081/v1", model="lightonocr-3"),
    )
    res_off = extract_pdf_hybrid(pdf_bytes, use_vision=True)
    assert res_off.vision_used is False
    assert any("scanned" in w.lower() or "vision" in w.lower() for w in res_off.warnings)
    assert any("Heuristic search uses evaluation functions." in c.text for c in res_off.chunks)

    # Case 2: Server online, but call times out
    monkeypatch.setattr(
        vision_ocr,
        "check_vision_status",
        lambda timeout=1.5: VisionStatus(available=True, url="http://127.0.0.1:8081/v1", model="lightonocr-3"),
    )

    def raise_timeout(*_args, **_kwargs):
        raise VisionOcrError("Vision server timed out")

    monkeypatch.setattr(vision_ocr, "call_vision_ocr", raise_timeout)
    res_to = extract_pdf_hybrid(pdf_bytes, use_vision=True)
    assert res_to.vision_used is False
    assert len(res_to.warnings) >= 1
    assert any("Heuristic search uses evaluation functions." in c.text for c in res_to.chunks)


def test_check_vision_status_handles_online_and_offline(monkeypatch):
    class FakeResp:
        def __init__(self, body: bytes):
            self.status = 200
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(vision_ocr.urllib.request, "urlopen", lambda req, timeout=1.5: FakeResp(b'{"data":[]}'))
    st_ok = check_vision_status()
    assert st_ok.available is True
    assert st_ok.url == "http://127.0.0.1:8081/v1"
    assert st_ok.model == "lightonocr-3"

    def raise_url_err(*_args, **_kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(vision_ocr.urllib.request, "urlopen", raise_url_err)
    st_off = check_vision_status()
    assert st_off.available is False
