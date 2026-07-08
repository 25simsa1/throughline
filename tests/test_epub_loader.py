from pathlib import Path

from loaders.epub_loader import EpubLoader

FIX = Path(__file__).parent / "fixtures" / "tiny.epub"


def test_epub_loader_extracts_text_with_item_locations():
    src = EpubLoader().load(FIX, "book-y")
    assert len(src.segments) == 1
    assert src.segments[0].loc == "c1.xhtml"
    assert "habit" in src.segments[0].text
