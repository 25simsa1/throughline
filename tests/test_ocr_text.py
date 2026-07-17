import pytest
from PIL import Image, ImageDraw

from loaders import ocr_text

pytestmark = pytest.mark.skipif(not ocr_text.available(), reason="no OCR backend on this machine")


def _text_image(text="MEMORY"):
    img = Image.new("RGB", (400, 80), "white")
    ImageDraw.Draw(img).text((10, 25), text, fill="black")
    return img


def test_image_to_text_reads_rendered_text():
    assert "MEMORY" in ocr_text.image_to_text(_text_image()).upper()
