import json
import re
from pathlib import Path

import graph
import store
from models import Segment, Source


def _chapter(tmp_path: Path) -> Path:
    a = Source(source_id="curry-2025", title="A question of alignment",
               type="paper", author="Curry et al.", year=2025,
               segments=[Segment(loc="p.1", text="x")])
    b = Source(source_id="oregan-2025", title="Depth ontology",
               type="paper", author="O'Regan & Ferri", year=2025,
               segments=[Segment(loc="p.1", text="y")])
    store.save_segments(tmp_path, [a, b])
    report = {"connections": [
        {"id": "C1", "move": "Homogeneity by design. The rest of the move.",
         "sources_involved": ["curry-2025", "oregan-2025"],
         "interpretation": "Long interpretation text.",
         "evidence": [{"source_id": "curry-2025", "quote": "q", "loc": "p.1"},
                      {"source_id": "oregan-2025", "quote": "r", "loc": "p.1"}],
         "tensions": "t", "status": "candidate"},
        {"id": "C2", "move": "A weak <x> one & bad.", "sources_involved": ["curry-2025"],
         "interpretation": "z", "evidence": [{"source_id": "curry-2025", "quote": "q", "loc": "p.1"}],
         "tensions": "t", "status": "candidate"},
    ]}
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "report.md").write_text(
        "## C1. Homogeneity by design\n\nDecision: keep\n\n---\n\n"
        "## C2. A weak one\n\nDecision: drop\nNote: too thin\n", encoding="utf-8")
    return tmp_path


def _embedded(text: str) -> dict:
    m = re.search(r'id="gdata">(.*?)</script>', text, re.DOTALL)
    assert m, "no embedded graph data found"
    return json.loads(m.group(1))


def test_build_map_writes_self_contained_html(tmp_path):
    ch = _chapter(tmp_path)
    out = graph.build_map(ch)
    assert out == ch / "map.html"
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "http://" not in text and "https://" not in text
    assert "<canvas" in text  # it is the force-graph canvas, not cards


def test_graph_data_has_hub_papers_and_connections(tmp_path):
    ch = _chapter(tmp_path)
    d = _embedded(graph.build_map(ch).read_text(encoding="utf-8"))
    types = {}
    for n in d["nodes"]:
        types.setdefault(n["type"], []).append(n)
    assert len(types["hub"]) == 1
    labels = {n["label"] for n in types["paper"]}
    assert "Curry et al. 2025" in labels
    assert "O'Regan & Ferri 2025" in labels
    conn = {n["id"]: n for n in types["conn"]}
    # decisions from report.md drive status, overriding report.json's "candidate"
    assert conn["C1"]["status"] == "keep"
    assert conn["C2"]["status"] == "drop"
    assert conn["C1"]["ev"] == 2
    assert d["counts"] == {"sources": 2, "connections": 2, "kept": 1}


def test_edges_wire_hub_to_connections_to_sources(tmp_path):
    ch = _chapter(tmp_path)
    d = _embedded(graph.build_map(ch).read_text(encoding="utf-8"))
    pairs = {(e["s"], e["t"]) for e in d["edges"]}
    assert ("__hub__", "C1") in pairs
    assert ("C1", "curry-2025") in pairs
    assert ("C1", "oregan-2025") in pairs
    assert ("C2", "curry-2025") in pairs


def test_untrusted_markup_cannot_escape_the_script_tag(tmp_path):
    ch = _chapter(tmp_path)
    text = graph.build_map(ch).read_text(encoding="utf-8")
    # the raw "<x>" from C2's move must not appear unescaped in the page
    assert "<x>" not in text
    assert "\\u003cx>" in text
    # but it round-trips back to the real string inside the parsed data
    d = _embedded(text)
    c2 = next(n for n in d["nodes"] if n.get("id") == "C2")
    assert c2["label"] == "A weak <x> one & bad"
