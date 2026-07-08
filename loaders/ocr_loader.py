from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image

from models import Segment, Source
from loaders.base import Loader


class OcrLoader(Loader):
    extensions = (".png", ".jpg", ".jpeg", ".tiff")

    def load(self, path: Path, source_id: str) -> Source:
        text = pytesseract.image_to_string(Image.open(path)).strip()
        segments = [Segment(loc="p.1", text=text)] if text else []
        return Source(
            source_id=source_id, title=path.stem, type="book", segments=segments
        )
