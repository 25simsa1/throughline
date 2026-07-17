from pathlib import Path

import store
from models import Segment, Source
from stages import extract_stage
from tests.fakes import FakeTransport
import llm


def _chapter(tmp_path: Path) -> Path:
    src = Source(
        source_id="s1", title="T", type="paper",
        segments=[Segment(loc="p.1", text="Memory is reconstructive, not a recording.")],
    )
    store.save_segments(tmp_path, [src])
    return tmp_path


def _client(ft):
    return llm.OllamaClient(host="http://fake", transport=ft)


def test_extract_writes_verified_units(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({"units": [{
        "source_id": "s1", "kind": "claim", "statement": "memory is rebuilt",
        "quote": "Memory is reconstructive", "loc": "p.1", "theme_tags": ["memory"],
    }]})
    result = extract_stage.run_extract(ch, _client(ft))
    assert result["s1"] == {"kept": 1, "dropped": 0}
    units = store.load_units(ch, "s1")
    assert units[0]["verified"] is True


def test_extract_repairs_then_drops_bad_quotes(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({"units": [
        {"source_id": "s1", "kind": "claim", "statement": "real",
         "quote": "Memory is reconstructive", "loc": "p.1", "theme_tags": []},
        {"source_id": "s1", "kind": "claim", "statement": "invented",
         "quote": "a hallucinated span", "loc": "p.1", "theme_tags": []},
    ]})
    ft.add_chat_json({"quote": "still not in the page"})
    result = extract_stage.run_extract(ch, _client(ft))
    assert result["s1"] == {"kept": 1, "dropped": 1}
    units = store.load_units(ch, "s1")
    assert len(units) == 1 and units[0]["statement"] == "real"


def test_extract_repair_can_rescue_a_quote(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({"units": [
        {"source_id": "s1", "kind": "claim", "statement": "rescued",
         "quote": "wrong words here", "loc": "p.1", "theme_tags": []},
    ]})
    ft.add_chat_json({"quote": "not a recording"})
    result = extract_stage.run_extract(ch, _client(ft))
    assert result["s1"] == {"kept": 1, "dropped": 0}
    units = store.load_units(ch, "s1")
    assert units[0]["quote"] == "not a recording"
    assert units[0]["verified"] is True
