from __future__ import annotations

import json
from pathlib import Path

import store
from loaders.registry import loader_for

_META = "meta.json"


def _load_meta(sources_dir: Path) -> dict:
    p = sources_dir / _META
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def ingest_chapter(chapter_dir: Path) -> list[store.Source]:
    sources_dir = chapter_dir / "sources"
    meta = _load_meta(sources_dir)
    sources = []
    for path in sorted(sources_dir.iterdir()):
        if path.name == _META or not path.is_file():
            continue
        source_id = path.stem
        loader = loader_for(path)
        src = loader.load(path, source_id)
        overrides = meta.get(source_id, {})
        for key in ("title", "author", "year", "venue", "type"):
            if key in overrides:
                setattr(src, key, overrides[key])
        sources.append(src)
    store.save_segments(chapter_dir, sources)
    return sources
