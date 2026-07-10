import json
from pathlib import Path

import pytest

import ingest


def test_ingest_reads_sources_and_applies_metadata_sidecar(tmp_path: Path):
    chapter = tmp_path / "chapter1"
    sources = chapter / "sources"
    sources.mkdir(parents=True)
    (sources / "book-a.md").write_text("Idea one.\n\nIdea two.\n", encoding="utf-8")
    (sources / "meta.json").write_text(
        json.dumps({"book-a": {"author": "Jane Doe", "year": 2019, "type": "book"}}),
        encoding="utf-8",
    )
    result = ingest.ingest_chapter(chapter)
    assert len(result) == 1
    src = result[0]
    assert src.source_id == "book-a"
    assert src.author == "Jane Doe"
    assert src.year == 2019
    assert src.type == "book"
    assert len(src.segments) == 2
    assert (chapter / "store" / "segments.json").exists()


def test_ingest_skips_unsupported_extension(tmp_path):
    chapter = tmp_path / "chapter1"
    sources = chapter / "sources"
    sources.mkdir(parents=True)
    (sources / "a.md").write_text("One.\n\nTwo.\n", encoding="utf-8")
    (sources / "b.xyz").write_text("junk", encoding="utf-8")
    result = ingest.ingest_chapter(chapter)
    assert [s.source_id for s in result] == ["a"]


def test_ingest_raises_on_missing_sources_dir(tmp_path):
    import pytest
    with pytest.raises(ingest.IngestError):
        ingest.ingest_chapter(tmp_path / "nope")


def test_ingest_raises_on_malformed_meta(tmp_path):
    import pytest
    chapter = tmp_path / "chapter1"
    sources = chapter / "sources"
    sources.mkdir(parents=True)
    (sources / "a.md").write_text("One.\n", encoding="utf-8")
    (sources / "meta.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ingest.IngestError):
        ingest.ingest_chapter(chapter)
