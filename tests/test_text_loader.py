from pathlib import Path

from loaders.registry import loader_for
from loaders.text_loader import TextLoader


def test_text_loader_makes_one_segment_per_paragraph(tmp_path: Path):
    f = tmp_path / "notes.md"
    f.write_text("First para.\n\nSecond para.\n", encoding="utf-8")
    src = TextLoader().load(f, "notes")
    assert src.source_id == "notes"
    assert [s.text for s in src.segments] == ["First para.", "Second para."]
    assert src.segments[0].loc == "para.1"
    assert src.segments[1].loc == "para.2"


def test_registry_selects_text_loader_for_md(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert isinstance(loader_for(f), TextLoader)
