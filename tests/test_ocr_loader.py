import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from loaders.ocr_loader import OcrLoader

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not installed"
)


def test_ocr_loader_reads_text_from_image(tmp_path: Path):
    img = Image.new("RGB", (400, 80), "white")
    ImageDraw.Draw(img).text((10, 25), "MEMORY", fill="black")
    p = tmp_path / "scan.png"
    img.save(p)
    src = OcrLoader().load(p, "scan-1")
    assert "MEMORY" in src.segments[0].text.upper()
    assert src.segments[0].loc == "p.1"
