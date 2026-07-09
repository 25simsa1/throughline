import json
from pathlib import Path

import store
import verify
from models import Segment, Source


def _seed(tmp_path: Path):
    src = Source(
        source_id="s1", title="T", type="paper",
        segments=[Segment(loc="p.3", text="Time   is\n the fire  in which we burn.")],
    )
    store.save_segments(tmp_path, [src])


def test_normalize_collapses_whitespace():
    assert verify.normalize_ws("a   b\n c") == "a b c"


def test_locate_finds_segment_ignoring_whitespace(tmp_path: Path):
    _seed(tmp_path)
    src = store.load_segments(tmp_path)[0]
    assert verify.locate("Time is the fire", src) == "p.3"
    assert verify.locate("a paraphrase not present", src) is None


def test_verify_units_flags_and_fills_loc(tmp_path: Path):
    _seed(tmp_path)
    store.save_units(tmp_path, "s1", [
        {"source_id": "s1", "kind": "quote", "statement": "x",
         "quote": "Time is the fire", "loc": ""},
        {"source_id": "s1", "kind": "quote", "statement": "y",
         "quote": "invented line", "loc": ""},
    ])
    result = verify.verify_units_file(tmp_path, "s1")
    assert result == {"verified": 1, "unverified": 1}
    units = store.load_units(tmp_path, "s1")
    assert units[0]["verified"] is True
    assert units[0]["loc"] == "p.3"
    assert units[1]["verified"] is False


def test_verify_units_corrects_and_flags_wrong_loc(tmp_path):
    src = Source(source_id="s1", title="T", type="paper",
        segments=[Segment(loc="p.1", text="irrelevant filler."),
                  Segment(loc="p.99", text="Time is the fire in which we burn.")])
    store.save_segments(tmp_path, [src])
    store.save_units(tmp_path, "s1", [
        {"source_id": "s1", "kind": "quote", "statement": "x",
         "quote": "Time is the fire", "loc": "p.1"}])  # wrong: real match is p.99
    result = verify.verify_units_file(tmp_path, "s1")
    units = store.load_units(tmp_path, "s1")
    assert result == {"verified": 1, "unverified": 0}
    assert units[0]["verified"] is True
    assert units[0]["loc"] == "p.99"
    assert units[0]["loc_corrected"] is True


def test_verify_units_does_not_flag_correct_loc(tmp_path):
    src = Source(source_id="s1", title="T", type="paper",
        segments=[Segment(loc="p.3", text="Time is the fire in which we burn.")])
    store.save_segments(tmp_path, [src])
    store.save_units(tmp_path, "s1", [
        {"source_id": "s1", "kind": "quote", "statement": "x",
         "quote": "Time is the fire", "loc": "p.3"}])
    verify.verify_units_file(tmp_path, "s1")
    units = store.load_units(tmp_path, "s1")
    assert units[0]["verified"] is True
    assert units[0].get("loc_corrected", False) is False


def test_verify_report_flags_unverified_evidence(tmp_path):
    src = Source(source_id="s1", title="T", type="paper",
        segments=[Segment(loc="p.3", text="Time is the fire in which we burn.")])
    store.save_segments(tmp_path, [src])
    report = {"connections": [{"id": "c1", "evidence": [
        {"source_id": "s1", "quote": "Time is the fire", "loc": "p.3"},
        {"source_id": "s1", "quote": "invented line", "loc": "p.3"}]}]}
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    result = verify.verify_report_file(tmp_path)
    assert result == {"unverified_evidence": 1}
    written = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    ev = written["connections"][0]["evidence"]
    assert ev[0]["verified"] is True
    assert ev[1]["verified"] is False
