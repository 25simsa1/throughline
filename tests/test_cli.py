from pathlib import Path

import throughline


def test_new_creates_chapter_scaffold(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = throughline.main(["new", "chapter1"])
    assert rc == 0
    assert (tmp_path / "chapters" / "chapter1" / "sources").is_dir()
    assert (tmp_path / "chapters" / "chapter1" / "thesis.md").exists()


def test_ingest_then_status_reports_counts(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    throughline.main(["new", "chapter1"])
    src = tmp_path / "chapters" / "chapter1" / "sources" / "a.md"
    src.write_text("One.\n\nTwo.\n", encoding="utf-8")
    assert throughline.main(["ingest", "chapter1"]) == 0
    assert throughline.main(["status", "chapter1"]) == 0
    out = capsys.readouterr().out
    assert "1 source" in out
