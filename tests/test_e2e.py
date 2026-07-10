import shutil
from pathlib import Path

import ingest
import store
import verify

FIX = Path(__file__).parent / "fixtures" / "e2e"


def test_pipeline_ingests_stores_and_verifies(tmp_path: Path):
    chapter = tmp_path / "chapter1"
    shutil.copytree(FIX, chapter)

    sources = ingest.ingest_chapter(chapter)
    assert {s.source_id for s in sources} == {"source-a", "source-b"}

    store.save_units(chapter, "source-a", [
        {"source_id": "source-a", "kind": "claim", "statement": "memory is rebuilt",
         "quote": "Memory is reconstructive, not a recording.", "loc": ""},
        {"source_id": "source-a", "kind": "quote", "statement": "hallucinated",
         "quote": "Memory is a perfect video recording.", "loc": ""},
    ])

    result = verify.verify_units_file(chapter, "source-a")
    assert result == {"verified": 1, "unverified": 1}

    units = store.load_units(chapter, "source-a")
    assert units[0]["verified"] is True
    assert units[0]["loc"] == "para.1"
    assert units[1]["verified"] is False
