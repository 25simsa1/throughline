from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageDraw

from loaders import ocr_text
from loaders.pdf_loader import PdfLoader

pytestmark = pytest.mark.skipif(not ocr_text.available(), reason="no OCR backend on this machine")


def _scanned_pdf(path: Path):
    img = Image.new("RGB", (800, 160), "white")
    ImageDraw.Draw(img).text((20, 50), "SCANNED PAGE ABOUT MEMORY", fill="black")
    img_path = path.parent / "page.png"
    img.save(img_path)
    doc = fitz.open()
    page = doc.new_page(width=800, height=160)
    page.insert_image(fitz.Rect(0, 0, 800, 160), filename=str(img_path))
    doc.save(path)


def test_scanned_pdf_gets_ocr_text(tmp_path: Path):
    pdf = tmp_path / "scan.pdf"
    _scanned_pdf(pdf)
    src = PdfLoader().load(pdf, "scan-1")
    assert len(src.segments) == 1
    assert src.segments[0].loc == "p.1"
    assert "MEMORY" in src.segments[0].text.upper()
