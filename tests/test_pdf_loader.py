from pathlib import Path

from loaders.pdf_loader import PdfLoader

FIX = Path(__file__).parent / "fixtures" / "two-page.pdf"


def test_pdf_loader_one_segment_per_page():
    src = PdfLoader().load(FIX, "paper-x")
    assert len(src.segments) == 2
    assert src.segments[0].loc == "p.1"
    assert "memory" in src.segments[0].text
    assert src.segments[1].loc == "p.2"
    assert "time" in src.segments[1].text
