from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path


class OcrUnavailable(Exception):
    pass


def _try_ocrmac(image) -> str | None:
    try:
        from ocrmac import ocrmac
    except Exception:
        return None
    try:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ocr.png"
            image.save(p)
            annotations = ocrmac.OCR(str(p), recognition_level="accurate").recognize()
        return "\n".join(a[0] for a in annotations)
    except Exception as e:
        print(f"warning: apple vision ocr failed ({e.__class__.__name__}: {e}); falling back",
              file=sys.stderr)
        return None


def _try_tesseract(image) -> str | None:
    if shutil.which("tesseract") is None:
        return None
    try:
        import pytesseract
        return pytesseract.image_to_string(image)
    except Exception:
        return None


def available() -> bool:
    try:
        from ocrmac import ocrmac  # noqa: F401
        return True
    except Exception:
        return shutil.which("tesseract") is not None


def image_to_text(image) -> str:
    for backend in (_try_ocrmac, _try_tesseract):
        text = backend(image)
        if text is not None:
            return text.strip()
    raise OcrUnavailable(
        "no OCR backend available; install ocrmac (mac) or tesseract"
    )
