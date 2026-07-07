from __future__ import annotations

from pathlib import Path

from loaders.base import Loader, LoaderError
from loaders.text_loader import TextLoader
from loaders.pdf_loader import PdfLoader
from loaders.epub_loader import EpubLoader
from loaders.ocr_loader import OcrLoader

_LOADERS: list[Loader] = [TextLoader(), EpubLoader(), PdfLoader(), OcrLoader()]


def loader_for(path: Path) -> Loader:
    ext = path.suffix.lower()
    for loader in _LOADERS:
        if ext in loader.extensions:
            return loader
    raise LoaderError(f"no loader for extension {ext!r}")
