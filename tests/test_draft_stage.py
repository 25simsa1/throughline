import json
from pathlib import Path

from stages import draft_stage
from tests.fakes import FakeTransport
import llm


def test_quoted_spans_and_check():
    text = 'He says "memory is social" and also “recall is collective” and "made up".'
    spans = draft_stage.quoted_spans(text)
    assert "memory is social" in spans and "recall is collective" in spans
    bad = draft_stage.check_quotes(text, ["Alpha memory is social beta", "recall is collective"])
    assert bad == ["made up"]


def test_curly_quoted_invented_span_is_caught():
    text = 'Prose quoting “an invented curly line” confidently.'
    assert draft_stage.quoted_spans(text) == ["an invented curly line"]
    assert draft_stage.check_quotes(text, ["memory is social"]) == ["an invented curly line"]


def _chapter(tmp_path: Path):
    report = {"connections": [{
        "id": "C1", "move": "T. M.", "sources_involved": ["a"],
        "interpretation": "x", "evidence": [
            {"source_id": "a", "quote": "memory is social", "loc": "p.1", "verified": True}],
        "advances_thesis": "x", "tensions": "x", "novelty": 0.5, "confidence": 0.5,
        "status": "candidate", "scholar_note": ""}]}
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "report.md").write_text(
        "## C1. T\n\nDecision: keep\n", encoding="utf-8")
    (tmp_path / "drafts").mkdir(exist_ok=True)
    return tmp_path


def test_run_draft_writes_kept_only(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({"draft_markdown": 'Prose quoting "memory is social" faithfully.'})
    client = llm.OllamaClient(host="http://fake", transport=ft)
    drafted = draft_stage.run_draft(ch, client)
    assert drafted == ["C1"]
    text = (ch / "drafts" / "C1.md").read_text(encoding="utf-8")
    assert "memory is social" in text
    assert "UNVERIFIED" not in text


def test_run_draft_flags_unverified_spans(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({"draft_markdown": 'Prose quoting "an invented line" boldly.'})
    ft.add_chat_json({"draft_markdown": 'Prose quoting "an invented line" boldly.'})
    client = llm.OllamaClient(host="http://fake", transport=ft)
    drafted = draft_stage.run_draft(ch, client)
    assert drafted == ["C1"]
    text = (ch / "drafts" / "C1.md").read_text(encoding="utf-8")
    assert "UNVERIFIED" in text and "an invented line" in text


def test_run_draft_warns_on_keep_without_connection(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    md = (ch / "report.md").read_text(encoding="utf-8")
    (ch / "report.md").write_text(md + "\n## C9. Ghost\n\nDecision: keep\n", encoding="utf-8")
    ft = FakeTransport()
    ft.add_chat_json({"draft_markdown": 'Prose quoting "memory is social" faithfully.'})
    client = llm.OllamaClient(host="http://fake", transport=ft)
    drafted = draft_stage.run_draft(ch, client)
    assert drafted == ["C1"]
    assert "C9" in capsys.readouterr().err
