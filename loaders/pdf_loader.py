from __future__ import annotations

from pathlib import Path

import fitz

from models import Segment, Source
from loaders.base import Loader


class PdfLoader(Loader):
    extensions = (".pdf",)

    def load(self, path: Path, source_id: str) -> Source:
        doc = fitz.open(path)
        segments = []
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                segments.append(Segment(loc=f"p.{i + 1}", text=text))
        return Source(
            source_id=source_id, title=path.stem, type="paper", segments=segments
        )
