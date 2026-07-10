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


def test_verify_before_extract_reports_not_extracted(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    throughline.main(["new", "chapter1"])
    (tmp_path / "chapters" / "chapter1" / "sources" / "a.md").write_text(
        "One.\n\nTwo.\n", encoding="utf-8")
    throughline.main(["ingest", "chapter1"])
    rc = throughline.main(["verify", "chapter1"])
    assert rc == 0
    assert "not extracted yet" in capsys.readouterr().out


def test_verify_missing_chapter_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = throughline.main(["verify", "ghost"])
    assert rc == 1
    assert "not ingested" in capsys.readouterr().err


def test_ingest_missing_sources_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = throughline.main(["ingest", "ghost"])
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_ingest_skips_unsupported_file_via_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    throughline.main(["new", "chapter1"])
    src = tmp_path / "chapters" / "chapter1" / "sources"
    (src / "a.md").write_text("One.\n\nTwo.\n", encoding="utf-8")
    (src / "b.xyz").write_text("junk", encoding="utf-8")
    rc = throughline.main(["ingest", "chapter1"])
    assert rc == 0
    assert "ingested 1 source" in capsys.readouterr().out
