from __future__ import annotations

import json
from pathlib import Path

from models import Source


def _store_dir(chapter_dir: Path) -> Path:
    d = chapter_dir / "store"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_segments(chapter_dir: Path, sources: list[Source]) -> Path:
    path = _store_dir(chapter_dir) / "segments.json"
    payload = {"sources": [s.to_dict() for s in sources]}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_segments(chapter_dir: Path) -> list[Source]:
    path = _store_dir(chapter_dir) / "segments.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Source.from_dict(d) for d in payload["sources"]]


def save_units(chapter_dir: Path, source_id: str, units: list[dict]) -> Path:
    path = _store_dir(chapter_dir) / f"{source_id}.units.json"
    path.write_text(json.dumps(units, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_units(chapter_dir: Path, source_id: str) -> list[dict]:
    path = _store_dir(chapter_dir) / f"{source_id}.units.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_units(chapter_dir: Path) -> list[dict]:
    units: list[dict] = []
    for path in sorted(_store_dir(chapter_dir).glob("*.units.json")):
        units.extend(json.loads(path.read_text(encoding="utf-8")))
    return units
