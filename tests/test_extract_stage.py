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


def test_extract_retries_when_units_key_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({})  # malformed, no units key
    ft.add_chat_json({"units": [{
        "source_id": "s1", "kind": "claim", "statement": "memory is rebuilt",
        "quote": "Memory is reconstructive", "loc": "p.1", "theme_tags": []}]})
    result = extract_stage.run_extract(ch, _client(ft))
    assert result["s1"] == {"kept": 1, "dropped": 0}


def test_extract_records_error_and_continues_past_failing_source(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    import store as _store
    from models import Segment, Source
    s1 = Source(source_id="s1", title="A", type="paper",
                segments=[Segment(loc="p.1", text="Memory is reconstructive, not a recording.")])
    s2 = Source(source_id="s2", title="B", type="paper",
                segments=[Segment(loc="p.1", text="Recall is collective and social.")])
    _store.save_segments(tmp_path, [s1, s2])
    ft = FakeTransport()
    for _ in range(3):  # s1 exhausts generate retries (retries=2 means 3 attempts)
        ft.add_chat_json({})
    ft.add_chat_json({"units": [{
        "source_id": "s2", "kind": "claim", "statement": "recall social",
        "quote": "Recall is collective", "loc": "p.1", "theme_tags": []}]})
    result = extract_stage.run_extract(tmp_path, _client(ft))
    assert "error" in result["s1"]
    assert result["s2"] == {"kept": 1, "dropped": 0}


def test_extract_resume_skips_existing_units(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    store.save_units(ch, "s1", [
        {"source_id": "s1", "kind": "claim", "statement": "x",
         "quote": "Memory is reconstructive", "loc": "p.1", "verified": True}])
    ft = FakeTransport()  # no queued responses, so any model call would blow up
    result = extract_stage.run_extract(ch, _client(ft), resume=True)
    assert result["s1"]["kept"] == 1
    assert result["s1"]["skipped"] is True
