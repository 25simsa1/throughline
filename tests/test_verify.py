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
