from __future__ import annotations

from pathlib import Path

from models import Segment, Source
from loaders.base import Loader


class TextLoader(Loader):
    extensions = (".txt", ".md")

    def load(self, path: Path, source_id: str) -> Source:
        raw = path.read_text(encoding="utf-8")
        paras = [p.strip() for p in raw.split("\n\n") if p.strip()]
        segments = [
            Segment(loc=f"para.{i + 1}", text=p) for i, p in enumerate(paras)
        ]
        return Source(
            source_id=source_id, title=path.stem, type="article", segments=segments
        )
