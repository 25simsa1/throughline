import json
from pathlib import Path

import throughline
import llm
from stages import extract_stage, connect_stage, draft_stage
from tests.fakes import FakeTransport


def test_full_autopilot_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    monkeypatch.chdir(tmp_path)
    throughline.main(["new", "chapter1"])
    ch = tmp_path / "chapters" / "chapter1"
    (ch / "sources" / "a.md").write_text("Alpha says memory is social.", encoding="utf-8")
    (ch / "sources" / "b.md").write_text("Beta says recall is collective.", encoding="utf-8")
    (ch / "thesis.md").write_text("Memory is collective.", encoding="utf-8")
    assert throughline.main(["ingest", "chapter1"]) == 0

    ft = FakeTransport()
    ft.add_chat_json({"units": [{"source_id": "a", "kind": "claim", "statement": "s",
                                 "quote": "memory is social", "loc": "para.1", "theme_tags": []}]})
    ft.add_chat_json({"units": [{"source_id": "b", "kind": "claim", "statement": "s",
                                 "quote": "recall is collective", "loc": "para.1", "theme_tags": []}]})
    ft.add("/api/embed", {"embeddings": [[1.0, 0.0], [0.9, 0.1]]})
    ft.add_chat_json({
        "id": "X", "move": "T. M.", "sources_involved": ["a", "b"],
        "interpretation": "i", "evidence": [
            {"source_id": "a", "quote": "memory is social", "loc": "x"},
            {"source_id": "b", "quote": "recall is collective", "loc": "x"}],
        "advances_thesis": "t", "tensions": "strain", "novelty": 0.5, "confidence": 0.9})
    ft.add_chat_json({"draft_markdown": 'Both agree that "memory is social".'})
    client = llm.OllamaClient(host="http://fake", transport=ft)

    extract_stage.run_extract(ch, client)
    n = connect_stage.run_connect(ch, client, top_k=1)
    assert n == 1
    md = (ch / "report.md").read_text(encoding="utf-8")
    (ch / "report.md").write_text(md.replace("Decision: candidate", "Decision: keep"), encoding="utf-8")
    drafted = draft_stage.run_draft(ch, client)
    assert drafted == ["C1"]
    assert (ch / "drafts" / "C1.md").exists()
    report = json.loads((ch / "report.json").read_text(encoding="utf-8"))
    assert all(ev["verified"] for ev in report["connections"][0]["evidence"])
