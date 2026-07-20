import json
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
        {"id": "C2", "move": "A weak one & bad.", "sources_involved": ["curry-2025"],
         "interpretation": "z", "evidence": [{"source_id": "curry-2025", "quote": "q", "loc": "p.1"}],
         "tensions": "t", "status": "candidate"},
    ]}
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "report.md").write_text(
        "## C1. Homogeneity by design\n\nDecision: keep\n\n---\n\n"
        "## C2. A weak one\n\nDecision: drop\nNote: too thin\n", encoding="utf-8")
    return tmp_path


def test_build_map_writes_self_contained_html(tmp_path):
    ch = _chapter(tmp_path)
    out = graph.build_map(ch)
    assert out == ch / "map.html"
    text = out.read_text(encoding="utf-8")
    # self-contained, no external resource fetches
    assert "http://" not in text and "https://" not in text
    assert text.startswith("<!doctype html>")


def test_map_shows_sources_connections_and_decisions(tmp_path):
    ch = _chapter(tmp_path)
    text = graph.build_map(ch).read_text(encoding="utf-8")
    # source nodes with friendly labels
    assert "Curry et al. 2025" in text
    assert "O&#x27;Regan &amp; Ferri 2025" in text  # apostrophe + ampersand escaped
    # connection titles from the move's first sentence
    assert "Homogeneity by design" in text
    # decisions from report.md drive the status, not report.json's "candidate"
    assert "C1 &middot; KEPT" in text
    assert "C2 &middot; DROPPED" in text
    # the drop note surfaces, and its card is dashed
    assert "too thin" in text
    assert 'class="conn dropped"' in text
    # verified-quote count shown for the kept one
    assert "2 verified quotations" in text


def test_map_escapes_untrusted_text(tmp_path):
    ch = _chapter(tmp_path)
    text = graph.build_map(ch).read_text(encoding="utf-8")
    # the "& bad" in C2's move must be escaped, never raw
    assert "A weak one &amp; bad" in text or "A weak one" in text
    assert "& bad." not in text.replace("&amp;", "AMP")
