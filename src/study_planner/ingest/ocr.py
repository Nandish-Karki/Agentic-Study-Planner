"""OCR fallback for scanned / image-only PDFs.

Real module handbooks are sometimes scanned images: pypdf extracts ~0 characters
and every downstream agent then hallucinates. This renders each page to an image
and OCRs it.

All heavy imports (pytesseract, pdf2image) and the tesseract binary are LAZY: the
module imports fine and the app runs even when they're absent — OCR simply reports
"unavailable" and the caller falls back to a friendly "couldn't read this scan"
message. The binaries ship in the Docker image (tesseract-ocr + poppler-utils);
local dev without them still runs (text PDFs work; scanned ones report unavailable).
"""
from __future__ import annotations

import pathlib
import re

# Below this many real chars/page, the embedded text layer is unusable -> try OCR.
OCR_TRIGGER_CHARS_PER_PAGE = 100


def _content_chars(text: str) -> int:
    """Char count with the synthetic '--- page N ---' markers stripped."""
    return len(re.sub(r"--- page \d+ ---", "", text or "").strip())


def ocr_available() -> bool:
    """True only if both the Python libs AND the tesseract binary are present."""
    try:
        import pytesseract  # noqa: F401
        import pdf2image  # noqa: F401
    except Exception:
        return False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_pdf(path: str | pathlib.Path, dpi: int = 200, max_pages: int = 300) -> str:
    """OCR every page of a PDF into text with page markers. '' if OCR unavailable.

    Bounded by max_pages so a pathological upload can't run forever."""
    if not ocr_available():
        return ""
    import pdf2image
    import pytesseract
    try:
        images = pdf2image.convert_from_path(str(path), dpi=dpi)
    except Exception:
        return ""
    parts: list[str] = []
    for i, img in enumerate(images[:max_pages], 1):
        try:
            parts.append(f"--- page {i} ---\n{pytesseract.image_to_string(img)}")
        except Exception:
            parts.append(f"--- page {i} ---\n")
    return "\n".join(parts)


def extract_text(path: str | pathlib.Path) -> tuple[str, bool]:
    """Best-effort text for a PDF as (text, used_ocr).

    Prefers the embedded text layer; when that's empty/too sparse (scanned), tries
    OCR and uses it only if it recovered more text. Never raises on a bad file."""
    from study_planner.tools.pdf_tools import _extract_pdf_text
    p = pathlib.Path(path)
    try:
        text = _extract_pdf_text(p)
    except Exception:
        text = ""
    chars = _content_chars(text)

    try:
        from pypdf import PdfReader
        pages = max(1, len(PdfReader(str(p)).pages))
    except Exception:
        pages = 1

    if chars / pages < OCR_TRIGGER_CHARS_PER_PAGE:
        ocr_text = ocr_pdf(p)
        if _content_chars(ocr_text) > chars:
            return ocr_text, True
    return text, False
