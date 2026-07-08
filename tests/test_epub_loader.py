from pathlib import Path

from loaders.epub_loader import EpubLoader

FIX = Path(__file__).parent / "fixtures" / "tiny.epub"


def test_epub_loader_extracts_text_with_item_locations():
    src = EpubLoader().load(FIX, "book-y")
    joined = " ".join(s.text for s in src.segments)
    assert "habit" in joined
    assert any(s.loc == "c1.xhtml" for s in src.segments)
