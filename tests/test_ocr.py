"""OCR ingest tests (Workstream 2 — scanned/image PDFs).

These run WITHOUT the tesseract binary by mocking the OCR call, so they verify the
routing/fallback logic (the part that breaks silently) rather than tesseract itself.
"""
import pathlib

from study_planner.ingest import ocr
from study_planner.tools import pdf_tools

_SAMPLE = pathlib.Path(__file__).parent.parent / "sample_data"


def test_content_chars_strips_page_markers():
    assert ocr._content_chars("--- page 1 ---\n   ") == 0
    assert ocr._content_chars("--- page 1 ---\nHello") == 5


def test_extract_text_uses_embedded_layer_for_text_pdf():
    # The sample handbook has a real text layer -> no OCR needed.
    text, used_ocr = ocr.extract_text(_SAMPLE / "module_handbook.pdf")
    assert used_ocr is False
    assert "Module" in text or len(text) > 200


def test_extract_text_falls_back_to_ocr_when_scanned(monkeypatch):
    # Simulate a scanned PDF: no embedded text, OCR recovers content.
    monkeypatch.setattr(pdf_tools, "_extract_pdf_text", lambda p: "--- page 1 ---\n")
    monkeypatch.setattr(ocr, "ocr_pdf",
                        lambda p, **k: "--- page 1 ---\nRecovered by OCR")
    text, used_ocr = ocr.extract_text(_SAMPLE / "module_handbook.pdf")
    assert used_ocr is True
    assert "Recovered by OCR" in text


def test_extract_text_degrades_gracefully_when_ocr_unavailable(monkeypatch):
    # Scanned PDF + OCR unavailable -> returns the (empty) text, never raises.
    monkeypatch.setattr(pdf_tools, "_extract_pdf_text", lambda p: "--- page 1 ---\n")
    monkeypatch.setattr(ocr, "ocr_pdf", lambda p, **k: "")  # unavailable -> ""
    text, used_ocr = ocr.extract_text(_SAMPLE / "module_handbook.pdf")
    assert used_ocr is False
    assert ocr._content_chars(text) == 0


def test_ocr_pdf_returns_empty_when_unavailable(monkeypatch):
    monkeypatch.setattr(ocr, "ocr_available", lambda: False)
    assert ocr.ocr_pdf(_SAMPLE / "module_handbook.pdf") == ""
