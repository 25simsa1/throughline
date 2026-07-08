from pathlib import Path

import store
from models import Segment, Source


def _src():
    return Source(
        source_id="s1", title="T", type="paper",
        segments=[Segment(loc="p.1", text="hello")],
    )


def test_segments_save_and_load_round_trip(tmp_path: Path):
    store.save_segments(tmp_path, [_src()])
    loaded = store.load_segments(tmp_path)
    assert loaded == [_src()]


def test_units_save_and_load_and_aggregate(tmp_path: Path):
    store.save_units(tmp_path, "s1", [{"source_id": "s1", "kind": "claim"}])
    store.save_units(tmp_path, "s2", [{"source_id": "s2", "kind": "quote"}])
    assert store.load_units(tmp_path, "s1")[0]["kind"] == "claim"
    all_units = store.load_all_units(tmp_path)
    assert {u["source_id"] for u in all_units} == {"s1", "s2"}
