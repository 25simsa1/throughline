from __future__ import annotations

from pathlib import Path

from PIL import Image

from models import Segment, Source
from loaders.base import Loader
from loaders import ocr_text


class OcrLoader(Loader):
    extensions = (".png", ".jpg", ".jpeg", ".tiff")

    def load(self, path: Path, source_id: str) -> Source:
        text = ocr_text.image_to_text(Image.open(path))
        segments = [Segment(loc="p.1", text=text)] if text else []
        return Source(
            source_id=source_id, title=path.stem, type="book", segments=segments
        )
