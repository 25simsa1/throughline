from __future__ import annotations

import io
import sys
from pathlib import Path

import fitz
from PIL import Image

from models import Segment, Source
from loaders.base import Loader
from loaders import ocr_text


class PdfLoader(Loader):
    extensions = (".pdf",)

    def load(self, path: Path, source_id: str) -> Source:
        doc = fitz.open(path)
        segments = []
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if not text:
                text = self._ocr_page(page, path.name, i + 1)
            if text:
                segments.append(Segment(loc=f"p.{i + 1}", text=text))
        doc.close()
        return Source(
            source_id=source_id, title=path.stem, type="paper", segments=segments
        )

    @staticmethod
    def _ocr_page(page, filename: str, pageno: int) -> str:
        try:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            return ocr_text.image_to_text(img).strip()
        except ocr_text.OcrUnavailable:
            print(
                f"warning: {filename} p.{pageno} has no text layer and no OCR backend is available",
                file=sys.stderr,
            )
            return ""
