from __future__ import annotations

from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

from models import Segment, Source
from loaders.base import Loader


class EpubLoader(Loader):
    extensions = (".epub",)

    def load(self, path: Path, source_id: str) -> Source:
        book = epub.read_epub(str(path))
        segments = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            if isinstance(item, epub.EpubNav):
                continue
            soup = BeautifulSoup(item.get_content(), "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            if text:
                segments.append(Segment(loc=item.get_name(), text=text))
        title = book.get_metadata("DC", "title")
        title_str = title[0][0] if title else path.stem
        return Source(
            source_id=source_id, title=title_str, type="book", segments=segments
        )
