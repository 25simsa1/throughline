import json

import pytest
import store
import verify
from models import Segment, Source
from stages import connect_stage
from tests.fakes import FakeTransport
import llm


def test_cosine_basics():
    assert connect_stage.cosine([1, 0], [1, 0]) == 1.0
    assert connect_stage.cosine([1, 0], [0, 1]) == 0.0
    assert connect_stage.cosine([0, 0], [1, 0]) == 0.0


def test_shortlist_pairs_cross_source_only_and_capped():
    units = [
        {"source_id": "a"}, {"source_id": "a"},
        {"source_id": "b"}, {"source_id": "c"},
    ]
    vectors = [
        [1.0, 0.0], [0.9, 0.1],
        [0.95, 0.05], [0.0, 1.0],
    ]
    pairs = connect_stage.shortlist_pairs(units, vectors, k=2)
    assert (0, 2) in pairs
    assert all(units[i]["source_id"] != units[j]["source_id"] for i, j in pairs)
    assert len(pairs) == 2


def test_shortlist_respects_max_per_unit():
    units = [{"source_id": "a"}, {"source_id": "b"}, {"source_id": "c"}, {"source_id": "d"}]
    vectors = [[1, 0], [0.99, 0.01], [0.98, 0.02], [0.97, 0.03]]
    pairs = connect_stage.shortlist_pairs(units, vectors, k=10, max_per_unit=1)
    flat = [i for p in pairs for i in p]
    assert len(flat) == len(set(flat))


def test_shortlist_pairs_orders_by_similarity_desc():
    units = [{"source_id": "a"}, {"source_id": "b"}, {"source_id": "c"}]
    vectors = [[1.0, 0.0], [0.6, 0.8], [0.98, 0.02]]
    pairs = connect_stage.shortlist_pairs(units, vectors, k=3)
    scores = [connect_stage.cosine(vectors[i], vectors[j]) for i, j in pairs]
    assert scores == sorted(scores, reverse=True)


def _chapter(tmp_path):
    a = Source(source_id="a", title="A", type="paper",
               segments=[Segment(loc="p.1", text="Alpha claims memory is social.")])
    b = Source(source_id="b", title="B", type="paper",
               segments=[Segment(loc="p.2", text="Beta claims recall is collective.")])
    store.save_segments(tmp_path, [a, b])
    store.save_units(tmp_path, "a", [{
        "source_id": "a", "kind": "claim", "statement": "memory social",
        "quote": "memory is social", "loc": "p.1", "verified": True}])
    store.save_units(tmp_path, "b", [{
        "source_id": "b", "kind": "claim", "statement": "recall collective",
        "quote": "recall is collective", "loc": "p.2", "verified": True}])
    (tmp_path / "thesis.md").write_text("# Thesis\nMemory is collective.", encoding="utf-8")
    return tmp_path


def _conn_obj(quote_a="memory is social", quote_b="recall is collective"):
    return {
        "id": "X", "move": "Title. Move text.",
        "sources_involved": ["a", "b"],
        "interpretation": "Together they say more.",
        "evidence": [
            {"source_id": "a", "quote": quote_a, "loc": "p.9"},
            {"source_id": "b", "quote": quote_b, "loc": "p.9"},
        ],
        "advances_thesis": "Directly.",
        "tensions": "Different senses of collective.",
        "novelty": 0.5, "confidence": 0.8,
        "status": "candidate", "scholar_note": "",
    }


def test_run_connect_writes_verified_report(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add("/api/embed", {"embeddings": [[1.0, 0.0], [0.9, 0.1]]})
    ft.add_chat_json(_conn_obj())
    client = llm.OllamaClient(host="http://fake", transport=ft)
    n = connect_stage.run_connect(ch, client, top_k=1, max_connections=3)
    assert n == 1
    report = json.loads((ch / "report.json").read_text(encoding="utf-8"))
    conn = report["connections"][0]
    assert conn["id"] == "C1"
    assert conn["evidence"][0]["loc"] == "p.1"  # loc rewritten from the matched unit
    assert all(ev["verified"] for ev in conn["evidence"])
    md = (ch / "report.md").read_text(encoding="utf-8")
    assert "Decision: candidate" in md


def test_run_connect_rejects_fabricated_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add("/api/embed", {"embeddings": [[1.0, 0.0], [0.9, 0.1]]})
    ft.add_chat_json(_conn_obj(quote_a="a quote that exists nowhere"))
    ft.add_chat_json(_conn_obj(quote_a="a quote that exists nowhere"))
    ft.add_chat_json(_conn_obj(quote_a="a quote that exists nowhere"))
    client = llm.OllamaClient(host="http://fake", transport=ft)
    n = connect_stage.run_connect(ch, client, top_k=1, max_connections=3)
    assert n == 0


def test_run_connect_logs_skipped_pair(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add("/api/embed", {"embeddings": [[1.0, 0.0], [0.9, 0.1]]})
    for _ in range(3):
        ft.add_chat_json(_conn_obj(quote_a="a quote that exists nowhere"))
    client = llm.OllamaClient(host="http://fake", transport=ft)
    n = connect_stage.run_connect(ch, client, top_k=1, max_connections=3)
    assert n == 0
    assert "skipped pair" in capsys.readouterr().err


def test_run_connect_raises_on_embedding_count_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add("/api/embed", {"embeddings": [[1.0, 0.0]]})  # one vector for two units
    client = llm.OllamaClient(host="http://fake", transport=ft)
    with pytest.raises(llm.LlmError):
        connect_stage.run_connect(ch, client, top_k=1)


def test_run_connect_surfaces_unverified_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add("/api/embed", {"embeddings": [[1.0, 0.0], [0.9, 0.1]]})
    ft.add_chat_json(_conn_obj())
    client = llm.OllamaClient(host="http://fake", transport=ft)
    monkeypatch.setattr(connect_stage.verify, "verify_report_file",
                        lambda c: {"unverified_evidence": 2})
    with pytest.raises(llm.LlmError):
        connect_stage.run_connect(ch, client, top_k=1)
