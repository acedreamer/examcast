import fitz
import pytest

from deepexamcast.pdf_parser import PdfParseError, parse_pdf_bytes


def _make_pdf_bytes(builder) -> bytes:
    doc = fitz.open()
    builder(doc)
    data = doc.tobytes()
    doc.close()
    return data


def test_parse_single_column_order_hyphenation_and_bboxes():
    def build(doc):
        p1 = doc.new_page(width=600, height=800)
        p1.insert_textbox(fitz.Rect(60, 120, 540, 220), "Dead-\nlock occurs when processes wait forever.")
        p1.insert_textbox(fitz.Rect(60, 260, 540, 340), "Circular wait is the fourth Coffman condition.")
        p2 = doc.new_page(width=600, height=800)
        p2.insert_textbox(fitz.Rect(60, 100, 540, 180), "Banker algorithm checks safe states.")

    data = _make_pdf_bytes(build)
    pages, chunks = parse_pdf_bytes(data)

    assert len(pages) == 2
    assert pages[0].page == 1 and pages[0].width == 600.0 and pages[0].height == 800.0
    assert pages[0].chunk_count == 2
    assert pages[1].chunk_count == 1
    assert [c.id for c in chunks] == ["C1", "C2", "C3"]
    assert chunks[0].page == 1
    assert chunks[2].page == 2
    assert "Deadlock occurs when processes wait forever." in chunks[0].text
    for c in chunks:
        assert len(c.bbox) == 4
        assert 0.0 <= c.bbox[0] <= c.bbox[2] <= 1.0
        assert 0.0 <= c.bbox[1] <= c.bbox[3] <= 1.0


def test_two_column_with_midpage_full_width_heading_order():
    def build(doc):
        page = doc.new_page(width=600, height=800)
        page.insert_textbox(fitz.Rect(50, 40, 550, 80), "1. Chapter Top Overview Across Full Width", fontsize=18)
        page.insert_textbox(fitz.Rect(40, 110, 270, 200), "Left upper paragraph one.")
        page.insert_textbox(fitz.Rect(330, 110, 560, 200), "Right upper paragraph two.")
        page.insert_textbox(fitz.Rect(40, 220, 270, 310), "Left upper paragraph three.")
        page.insert_textbox(fitz.Rect(330, 220, 560, 310), "Right upper paragraph four.")
        page.insert_textbox(fitz.Rect(50, 350, 550, 395), "2. Mid-Page Full Width Section Heading", fontsize=18)
        page.insert_textbox(fitz.Rect(40, 430, 270, 520), "Left lower paragraph five.")
        page.insert_textbox(fitz.Rect(330, 430, 560, 520), "Right lower paragraph six.")

    pages, chunks = parse_pdf_bytes(_make_pdf_bytes(build))
    assert pages[0].chunk_count == 8
    texts = [c.text for c in chunks]
    assert texts[0].startswith("1. Chapter Top")
    assert texts[1].startswith("Left upper paragraph one")
    assert texts[2].startswith("Left upper paragraph three")
    assert texts[3].startswith("Right upper paragraph two")
    assert texts[4].startswith("Right upper paragraph four")
    assert texts[5].startswith("2. Mid-Page Full Width")
    assert texts[6].startswith("Left lower paragraph five")
    assert texts[7].startswith("Right lower paragraph six")


def test_rotated_and_cropbox_normalization():
    def build(doc):
        p = doc.new_page(width=600, height=800)
        p.set_cropbox(fitz.Rect(50, 50, 550, 750))
        p.insert_textbox(fitz.Rect(100, 120, 450, 200), "Cropped page paragraph text.")
        p.set_rotation(90)

    pages, chunks = parse_pdf_bytes(_make_pdf_bytes(build))
    assert len(pages) == 1
    assert len(chunks) == 1
    x0, y0, x1, y1 = chunks[0].bbox
    assert 0.0 <= x0 < x1 <= 1.0
    assert 0.0 <= y0 < y1 <= 1.0


def test_suppresses_repeating_headers_footers_and_page_numbers():
    def build(doc):
        for idx in range(1, 5):
            p = doc.new_page(width=600, height=800)
            p.insert_textbox(fitz.Rect(60, 15, 540, 38), "CS301 Operating Systems Notes")
            p.insert_textbox(fitz.Rect(60, 140, 540, 220), f"Unique lecture concept on page {idx}.")
            p.insert_textbox(fitz.Rect(250, 765, 350, 790), f"Page {idx} of 4")

    pages, chunks = parse_pdf_bytes(_make_pdf_bytes(build))
    assert len(pages) == 4
    assert len(chunks) == 4
    for idx, chunk in enumerate(chunks, start=1):
        assert chunk.text == f"Unique lecture concept on page {idx}."


def test_micro_chunk_merging_and_image_only_filtering():
    def build(doc):
        p = doc.new_page(width=600, height=800)
        p.insert_textbox(fitz.Rect(60, 118, 180, 138), "Note:")
        p.insert_textbox(fitz.Rect(60, 142, 520, 175), "Mutex locks prevent simultaneous critical section entry.")
        p.draw_rect(fitz.Rect(100, 300, 400, 450), color=(0, 0, 0))
        doc.new_page(width=600, height=800)  # Blank page with 0 text blocks

    pages, chunks = parse_pdf_bytes(_make_pdf_bytes(build))
    assert len(pages) == 2
    assert pages[0].chunk_count == 1
    assert pages[1].chunk_count == 0
    assert len(chunks) == 1
    assert "Note:" in chunks[0].text and "Mutex locks prevent" in chunks[0].text
    assert chunks[0].bbox[0] <= 0.12


def test_corrupt_or_empty_pdf_raises():
    with pytest.raises(PdfParseError):
        parse_pdf_bytes(b"not a pdf at all")
    with pytest.raises(PdfParseError):
        parse_pdf_bytes(b"")
