from __future__ import annotations

import json
import sys
from pathlib import Path

import store
from loaders.base import LoaderError
from loaders.registry import loader_for

_META = "meta.json"


class IngestError(Exception):
    pass


def _load_meta(sources_dir: Path) -> dict:
    p = sources_dir / _META
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise IngestError(f"{_META} is not valid JSON: {e}")


def ingest_chapter(chapter_dir: Path) -> list[store.Source]:
    sources_dir = chapter_dir / "sources"
    if not sources_dir.is_dir():
        raise IngestError(
            f"no sources directory at {sources_dir}; run 'new' first and add sources"
        )
    meta = _load_meta(sources_dir)
    sources = []
    skipped = []
    for path in sorted(sources_dir.iterdir()):
        if path.name == _META or not path.is_file():
            continue
        source_id = path.stem
        try:
            loader = loader_for(path)
        except LoaderError:
            skipped.append(path.name)
            continue
        src = loader.load(path, source_id)
        overrides = meta.get(source_id, {})
        for key in ("title", "author", "year", "venue", "type"):
            if key in overrides:
                setattr(src, key, overrides[key])
        sources.append(src)
    if skipped:
        print(
            f"skipped {len(skipped)} unsupported file(s): {', '.join(skipped)}",
            file=sys.stderr,
        )
    store.save_segments(chapter_dir, sources)
    return sources
