# Throughline MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Throughline MVP, a Python harness plus a Claude Code skill that ingests mixed-type sources, extracts traceable material, surfaces candidate cross-source connections for a chapter thesis, and drafts prose for the ones the scholar keeps.

**Architecture:** A deterministic Python harness owns ingestion, the on-disk store, JSON-shape validation, and verbatim-quote verification. A Claude Code skill owns the reasoning stages (extract, connect, draft, critique), reading and writing the same store and gating every quote through the Python verifier. The store on disk is the single source of truth.

**Tech Stack:** Python 3.11+, PyMuPDF (fitz), ebooklib, beautifulsoup4, pytesseract plus Pillow (OCR), pytest. Reasoning runs on Claude via Claude Code (no metered API key).

## Global Constraints

Every task's requirements implicitly include these.

- Python 3.11 or newer. Use only the dependencies named in the Tech Stack.
- Repo lives at `~/throughline`, already git-initialized with local identity Simon Sang / simonlapsang@gmail.com.
- Commits use first-person past tense with a capital I (for example "I added the text loader"), one commit per meaningful unit, and never any Co-Authored-By or AI-attribution trailer.
- In any Markdown or docs authored for the user, avoid em dashes and avoid colons in prose sentences. Code, field labels, and JSON are exempt.
- A quote is trusted only if it appears verbatim (whitespace-normalized) in its source and carries a location. Anything else is marked UNVERIFIED.
- Locations are strings that adapt to source type (`p.42` for a book page, `§3.2` or `abstract` for a paper section, an EPUB item name for EPUB).

---

## File structure

```
~/throughline/
  models.py                 # Segment, Source dataclasses + (de)serialization
  store.py                  # read/write segments.json and <source>.units.json
  schemas.py                # validate_unit, validate_connection
  verify.py                 # whitespace-normalized verbatim quote verification
  ingest.py                 # orchestrates loaders + metadata sidecar merge
  throughline.py            # argparse CLI: new, ingest, verify, status
  loaders/
    __init__.py
    base.py                 # Loader ABC + LoaderError
    registry.py             # choose a loader by file extension
    text_loader.py
    pdf_loader.py
    epub_loader.py
    ocr_loader.py
  templates/
    rubric.md               # starter calibration rubric
    gold-example.md         # worked-example template
  skills/throughline/SKILL.md   # authored in-repo, symlinked into ~/.claude/skills
  install-skill.sh          # symlink the skill into ~/.claude/skills
  chapters/                 # per-chapter data (gitignored store/)
  tests/
    conftest.py
    fixtures/
    test_models.py
    test_text_loader.py
    test_pdf_loader.py
    test_epub_loader.py
    test_ocr_loader.py
    test_store.py
    test_schemas.py
    test_verify.py
    test_ingest.py
    test_e2e.py
  README.md
```

---

## Task 1: Project scaffold and core models

**Files:**
- Create: `models.py`
- Create: `requirements.txt`
- Create: `tests/conftest.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Segment(loc: str, text: str)`; `Source(source_id: str, title: str, author: str, year: int | None, venue: str | None, type: str, segments: list[Segment])`; `Source.to_dict() -> dict`; `Source.from_dict(d: dict) -> Source`.

- [ ] **Step 1: Create the virtual environment and install dependencies**

Run:
```bash
cd ~/throughline
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install pymupdf ebooklib beautifulsoup4 pytesseract Pillow pytest
.venv/bin/pip freeze > requirements.txt
```
Expected: `requirements.txt` written with the pinned versions.

- [ ] **Step 2: Write the failing test**

`tests/test_models.py`:
```python
from models import Segment, Source


def test_source_round_trips_through_dict():
    src = Source(
        source_id="book-a",
        title="A Book",
        author="Jane Doe",
        year=2019,
        venue=None,
        type="book",
        segments=[Segment(loc="p.1", text="Hello world.")],
    )
    restored = Source.from_dict(src.to_dict())
    assert restored == src
    assert restored.segments[0].loc == "p.1"


def test_source_from_dict_defaults_missing_optionals():
    d = {"source_id": "s", "title": "T", "type": "paper", "segments": []}
    src = Source.from_dict(d)
    assert src.author == ""
    assert src.year is None
    assert src.venue is None
    assert src.segments == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models'`.

- [ ] **Step 4: Write the implementation**

`models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Segment:
    loc: str
    text: str

    def to_dict(self) -> dict:
        return {"loc": self.loc, "text": self.text}

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(loc=d["loc"], text=d["text"])


@dataclass
class Source:
    source_id: str
    title: str
    type: str
    segments: list[Segment] = field(default_factory=list)
    author: str = ""
    year: int | None = None
    venue: str | None = None

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "author": self.author,
            "year": self.year,
            "venue": self.venue,
            "type": self.type,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        return cls(
            source_id=d["source_id"],
            title=d["title"],
            type=d["type"],
            author=d.get("author", ""),
            year=d.get("year"),
            venue=d.get("venue"),
            segments=[Segment.from_dict(s) for s in d.get("segments", [])],
        )
```

`tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 6: Commit**

```bash
git add models.py requirements.txt tests/conftest.py tests/test_models.py
git commit -m "I added the Segment and Source models and pinned the project dependencies"
```

---

## Task 2: Loader interface, registry, and text loader

**Files:**
- Create: `loaders/__init__.py` (empty)
- Create: `loaders/base.py`
- Create: `loaders/registry.py`
- Create: `loaders/text_loader.py`
- Test: `tests/test_text_loader.py`

**Interfaces:**
- Consumes: `models.Source`, `models.Segment`.
- Produces: `class Loader` with `extensions: tuple[str, ...]` and `load(self, path: Path, source_id: str) -> Source`; `class LoaderError(Exception)`; `registry.loader_for(path: Path) -> Loader`; `TextLoader`.

- [ ] **Step 1: Write the failing test**

`tests/test_text_loader.py`:
```python
from pathlib import Path

from loaders.registry import loader_for
from loaders.text_loader import TextLoader


def test_text_loader_makes_one_segment_per_paragraph(tmp_path: Path):
    f = tmp_path / "notes.md"
    f.write_text("First para.\n\nSecond para.\n", encoding="utf-8")
    src = TextLoader().load(f, "notes")
    assert src.source_id == "notes"
    assert [s.text for s in src.segments] == ["First para.", "Second para."]
    assert src.segments[0].loc == "para.1"
    assert src.segments[1].loc == "para.2"


def test_registry_selects_text_loader_for_md(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert isinstance(loader_for(f), TextLoader)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_text_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loaders.text_loader'`.

- [ ] **Step 3: Write the implementation**

`loaders/base.py`:
```python
from __future__ import annotations

from pathlib import Path

from models import Source


class LoaderError(Exception):
    pass


class Loader:
    extensions: tuple[str, ...] = ()

    def load(self, path: Path, source_id: str) -> Source:
        raise NotImplementedError
```

`loaders/text_loader.py`:
```python
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
```

`loaders/registry.py`:
```python
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
```

Note. `registry.py` imports the loaders built in Tasks 3, 4, and 5. Create empty placeholder classes now so imports resolve, and flesh them out in their own tasks:

`loaders/pdf_loader.py`, `loaders/epub_loader.py`, `loaders/ocr_loader.py` each start as:
```python
from loaders.base import Loader


class PdfLoader(Loader):  # rename per file: EpubLoader / OcrLoader
    extensions = ()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_text_loader.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 5: Commit**

```bash
git add loaders/ tests/test_text_loader.py
git commit -m "I built the loader interface, the extension registry, and the text loader"
```

---

## Task 3: PDF loader

**Files:**
- Modify: `loaders/pdf_loader.py`
- Create: `tests/fixtures/two-page.pdf` (generated in Step 1)
- Test: `tests/test_pdf_loader.py`

**Interfaces:**
- Produces: `PdfLoader` with `extensions = (".pdf",)` and one `Segment` per page, `loc="p.{n}"` (1-indexed).

- [ ] **Step 1: Create the fixture PDF**

Run:
```bash
.venv/bin/python - <<'PY'
import fitz
doc = fitz.open()
for text in ["Page one about memory.", "Page two about time."]:
    page = doc.new_page()
    page.insert_text((72, 72), text)
doc.save("tests/fixtures/two-page.pdf")
PY
```
Expected: `tests/fixtures/two-page.pdf` created.

- [ ] **Step 2: Write the failing test**

`tests/test_pdf_loader.py`:
```python
from pathlib import Path

from loaders.pdf_loader import PdfLoader

FIX = Path(__file__).parent / "fixtures" / "two-page.pdf"


def test_pdf_loader_one_segment_per_page():
    src = PdfLoader().load(FIX, "paper-x")
    assert len(src.segments) == 2
    assert src.segments[0].loc == "p.1"
    assert "memory" in src.segments[0].text
    assert src.segments[1].loc == "p.2"
    assert "time" in src.segments[1].text
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pdf_loader.py -v`
Expected: FAIL (empty `extensions`, or `AssertionError` on segment count).

- [ ] **Step 4: Write the implementation**

`loaders/pdf_loader.py`:
```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pdf_loader.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add loaders/pdf_loader.py tests/test_pdf_loader.py tests/fixtures/two-page.pdf
git commit -m "I wrote the PDF loader so it emits one located segment per page"
```

---

## Task 4: EPUB loader

**Files:**
- Modify: `loaders/epub_loader.py`
- Create: `tests/fixtures/tiny.epub` (generated in Step 1)
- Test: `tests/test_epub_loader.py`

**Interfaces:**
- Produces: `EpubLoader` with `extensions = (".epub",)`, one `Segment` per document item, `loc` set to the item file name.

- [ ] **Step 1: Create the fixture EPUB**

Run:
```bash
.venv/bin/python - <<'PY'
from ebooklib import epub
book = epub.EpubBook()
book.set_identifier("id1")
book.set_title("Tiny Book")
c1 = epub.EpubHtml(title="C1", file_name="c1.xhtml")
c1.content = "<html><body><p>Chapter one on habit.</p></body></html>"
book.add_item(c1)
book.spine = [c1]
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())
epub.write_epub("tests/fixtures/tiny.epub", book)
PY
```
Expected: `tests/fixtures/tiny.epub` created.

- [ ] **Step 2: Write the failing test**

`tests/test_epub_loader.py`:
```python
from pathlib import Path

from loaders.epub_loader import EpubLoader

FIX = Path(__file__).parent / "fixtures" / "tiny.epub"


def test_epub_loader_extracts_text_with_item_locations():
    src = EpubLoader().load(FIX, "book-y")
    joined = " ".join(s.text for s in src.segments)
    assert "habit" in joined
    assert any(s.loc == "c1.xhtml" for s in src.segments)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_epub_loader.py -v`
Expected: FAIL.

- [ ] **Step 4: Write the implementation**

`loaders/epub_loader.py`:
```python
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
            soup = BeautifulSoup(item.get_content(), "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            if text:
                segments.append(Segment(loc=item.get_name(), text=text))
        title = book.get_metadata("DC", "title")
        title_str = title[0][0] if title else path.stem
        return Source(
            source_id=source_id, title=title_str, type="book", segments=segments
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_epub_loader.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add loaders/epub_loader.py tests/test_epub_loader.py tests/fixtures/tiny.epub
git commit -m "I added the EPUB loader that keeps each document item as a located segment"
```

---

## Task 5: OCR loader

**Files:**
- Modify: `loaders/ocr_loader.py`
- Test: `tests/test_ocr_loader.py`

**Interfaces:**
- Produces: `OcrLoader` with `extensions = (".png", ".jpg", ".jpeg", ".tiff")`, one `Segment` per image, `loc="p.1"` for single images.

Note. The OCR loader handles image files. Scanned image-PDFs are converted to images upstream by the ingest step in Task 6 before reaching this loader. The test guards on the tesseract binary being installed and skips cleanly if it is missing, so the suite stays green on machines without OCR.

- [ ] **Step 1: Write the failing test**

`tests/test_ocr_loader.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ocr_loader.py -v`
Expected: FAIL (empty `extensions`) or SKIP if tesseract is absent. If skipped, install tesseract (`brew install tesseract`) before implementing so you can see it pass.

- [ ] **Step 3: Write the implementation**

`loaders/ocr_loader.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ocr_loader.py -v`
Expected: PASS (or SKIP if tesseract is not installed on this machine).

- [ ] **Step 5: Commit**

```bash
git add loaders/ocr_loader.py tests/test_ocr_loader.py
git commit -m "I added the OCR loader for scanned image sources, guarded on the tesseract binary"
```

---

## Task 6: Store and ingest orchestration

**Files:**
- Create: `store.py`
- Create: `ingest.py`
- Test: `tests/test_store.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `models.Source`, `loaders.registry.loader_for`.
- Produces:
  - `store.save_segments(chapter_dir: Path, sources: list[Source]) -> Path`
  - `store.load_segments(chapter_dir: Path) -> list[Source]`
  - `store.save_units(chapter_dir: Path, source_id: str, units: list[dict]) -> Path`
  - `store.load_units(chapter_dir: Path, source_id: str) -> list[dict]`
  - `store.load_all_units(chapter_dir: Path) -> list[dict]`
  - `ingest.ingest_chapter(chapter_dir: Path) -> list[Source]`

- [ ] **Step 1: Write the failing store test**

`tests/test_store.py`:
```python
from pathlib import Path

import store
from models import Segment, Source


def _src():
    return Source(
        source_id="s1", title="T", type="paper",
        segments=[Segment(loc="p.1", text="hello")],
    )


def test_segments_save_and_load_round_trip(tmp_path: Path):
    store.save_segments(tmp_path, [_src()])
    loaded = store.load_segments(tmp_path)
    assert loaded == [_src()]


def test_units_save_and_load_and_aggregate(tmp_path: Path):
    store.save_units(tmp_path, "s1", [{"source_id": "s1", "kind": "claim"}])
    store.save_units(tmp_path, "s2", [{"source_id": "s2", "kind": "quote"}])
    assert store.load_units(tmp_path, "s1")[0]["kind"] == "claim"
    all_units = store.load_all_units(tmp_path)
    assert {u["source_id"] for u in all_units} == {"s1", "s2"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'store'`.

- [ ] **Step 3: Write the store implementation**

`store.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from models import Source


def _store_dir(chapter_dir: Path) -> Path:
    d = chapter_dir / "store"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_segments(chapter_dir: Path, sources: list[Source]) -> Path:
    path = _store_dir(chapter_dir) / "segments.json"
    payload = {"sources": [s.to_dict() for s in sources]}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_segments(chapter_dir: Path) -> list[Source]:
    path = _store_dir(chapter_dir) / "segments.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Source.from_dict(d) for d in payload["sources"]]


def save_units(chapter_dir: Path, source_id: str, units: list[dict]) -> Path:
    path = _store_dir(chapter_dir) / f"{source_id}.units.json"
    path.write_text(json.dumps(units, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_units(chapter_dir: Path, source_id: str) -> list[dict]:
    path = _store_dir(chapter_dir) / f"{source_id}.units.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_units(chapter_dir: Path) -> list[dict]:
    units: list[dict] = []
    for path in sorted(_store_dir(chapter_dir).glob("*.units.json")):
        units.extend(json.loads(path.read_text(encoding="utf-8")))
    return units
```

- [ ] **Step 4: Run the store test to verify it passes**

Run: `.venv/bin/pytest tests/test_store.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 5: Write the failing ingest test**

`tests/test_ingest.py`:
```python
import json
from pathlib import Path

import ingest


def test_ingest_reads_sources_and_applies_metadata_sidecar(tmp_path: Path):
    chapter = tmp_path / "chapter1"
    sources = chapter / "sources"
    sources.mkdir(parents=True)
    (sources / "book-a.md").write_text("Idea one.\n\nIdea two.\n", encoding="utf-8")
    (sources / "meta.json").write_text(
        json.dumps({"book-a": {"author": "Jane Doe", "year": 2019, "type": "book"}}),
        encoding="utf-8",
    )
    result = ingest.ingest_chapter(chapter)
    assert len(result) == 1
    src = result[0]
    assert src.source_id == "book-a"
    assert src.author == "Jane Doe"
    assert src.year == 2019
    assert src.type == "book"
    assert len(src.segments) == 2
    assert (chapter / "store" / "segments.json").exists()
```

- [ ] **Step 6: Run the ingest test to verify it fails**

Run: `.venv/bin/pytest tests/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ingest'`.

- [ ] **Step 7: Write the ingest implementation**

`ingest.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

import store
from loaders.registry import loader_for

_META = "meta.json"


def _load_meta(sources_dir: Path) -> dict:
    p = sources_dir / _META
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def ingest_chapter(chapter_dir: Path) -> list[store.Source]:
    sources_dir = chapter_dir / "sources"
    meta = _load_meta(sources_dir)
    sources = []
    for path in sorted(sources_dir.iterdir()):
        if path.name == _META or not path.is_file():
            continue
        source_id = path.stem
        loader = loader_for(path)
        src = loader.load(path, source_id)
        overrides = meta.get(source_id, {})
        for key in ("title", "author", "year", "venue", "type"):
            if key in overrides:
                setattr(src, key, overrides[key])
        sources.append(src)
    store.save_segments(chapter_dir, sources)
    return sources
```

Note. `store.Source` is re-exported by importing `Source` at the top of `store.py`; add `from models import Source` there (already present) and it is reachable as `store.Source`.

- [ ] **Step 8: Run the ingest test to verify it passes**

Run: `.venv/bin/pytest tests/test_ingest.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add store.py ingest.py tests/test_store.py tests/test_ingest.py
git commit -m "I wrote the on-disk store and the ingest step that merges a metadata sidecar"
```

---

## Task 7: JSON-shape validation

**Files:**
- Create: `schemas.py`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Produces:
  - `schemas.validate_unit(u: dict) -> list[str]` (empty list means valid)
  - `schemas.validate_connection(c: dict) -> list[str]`
  - `schemas.validate_units(units: list[dict]) -> list[str]`

- [ ] **Step 1: Write the failing test**

`tests/test_schemas.py`:
```python
import schemas


def test_valid_unit_has_no_errors():
    u = {"source_id": "s", "kind": "claim", "statement": "x",
         "quote": "q", "loc": "p.1"}
    assert schemas.validate_unit(u) == []


def test_unit_missing_quote_and_loc_reports_both():
    errs = schemas.validate_unit({"source_id": "s", "kind": "claim", "statement": "x"})
    assert any("quote" in e for e in errs)
    assert any("loc" in e for e in errs)


def test_unit_bad_kind_is_rejected():
    errs = schemas.validate_unit(
        {"source_id": "s", "kind": "opinion", "statement": "x", "quote": "q", "loc": "p.1"}
    )
    assert any("kind" in e for e in errs)


def test_connection_requires_tensions_and_evidence():
    c = {"id": "c1", "move": "m", "sources_involved": ["a"],
         "interpretation": "i", "evidence": [], "advances_thesis": "t"}
    errs = schemas.validate_connection(c)
    assert any("tensions" in e for e in errs)
    assert any("evidence" in e for e in errs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'schemas'`.

- [ ] **Step 3: Write the implementation**

`schemas.py`:
```python
from __future__ import annotations

_UNIT_KINDS = {"claim", "concept", "quote"}
_UNIT_REQUIRED = ("source_id", "kind", "statement", "quote", "loc")
_CONN_REQUIRED = (
    "id", "move", "sources_involved", "interpretation",
    "evidence", "advances_thesis", "tensions",
)


def validate_unit(u: dict) -> list[str]:
    errs = []
    for key in _UNIT_REQUIRED:
        if not u.get(key):
            errs.append(f"unit missing required field {key!r}")
    kind = u.get("kind")
    if kind and kind not in _UNIT_KINDS:
        errs.append(f"unit kind {kind!r} not in {sorted(_UNIT_KINDS)}")
    return errs


def validate_units(units: list[dict]) -> list[str]:
    errs = []
    for i, u in enumerate(units):
        errs.extend(f"[{i}] {e}" for e in validate_unit(u))
    return errs


def validate_connection(c: dict) -> list[str]:
    errs = []
    for key in _CONN_REQUIRED:
        if key not in c or c[key] in (None, "", []):
            errs.append(f"connection missing required field {key!r}")
    for j, ev in enumerate(c.get("evidence", []) or []):
        for key in ("source_id", "quote", "loc"):
            if not ev.get(key):
                errs.append(f"evidence[{j}] missing {key!r}")
    return errs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_schemas.py -v`
Expected: PASS, 4 passed.

- [ ] **Step 5: Commit**

```bash
git add schemas.py tests/test_schemas.py
git commit -m "I added shape validation for units and connections, with tensions required on every connection"
```

---

## Task 8: Verbatim-quote verification

**Files:**
- Create: `verify.py`
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: `models.Source`, `store.load_segments`, `store.load_units`, `store.save_units`.
- Produces:
  - `verify.normalize_ws(s: str) -> str`
  - `verify.locate(quote: str, source: Source) -> str | None`
  - `verify.verify_units_file(chapter_dir: Path, source_id: str) -> dict` returning `{"verified": int, "unverified": int}` and writing the `verified` flag plus a filled `loc` back into the units file.
  - `verify.verify_report_file(chapter_dir: Path) -> dict` returning `{"unverified_evidence": int}` and annotating each evidence item with `verified`.

- [ ] **Step 1: Write the failing test**

`tests/test_verify.py`:
```python
import json
from pathlib import Path

import store
import verify
from models import Segment, Source


def _seed(tmp_path: Path):
    src = Source(
        source_id="s1", title="T", type="paper",
        segments=[Segment(loc="p.3", text="Time   is\n the fire  in which we burn.")],
    )
    store.save_segments(tmp_path, [src])


def test_normalize_collapses_whitespace():
    assert verify.normalize_ws("a   b\n c") == "a b c"


def test_locate_finds_segment_ignoring_whitespace(tmp_path: Path):
    _seed(tmp_path)
    src = store.load_segments(tmp_path)[0]
    assert verify.locate("Time is the fire", src) == "p.3"
    assert verify.locate("a paraphrase not present", src) is None


def test_verify_units_flags_and_fills_loc(tmp_path: Path):
    _seed(tmp_path)
    store.save_units(tmp_path, "s1", [
        {"source_id": "s1", "kind": "quote", "statement": "x",
         "quote": "Time is the fire", "loc": ""},
        {"source_id": "s1", "kind": "quote", "statement": "y",
         "quote": "invented line", "loc": ""},
    ])
    result = verify.verify_units_file(tmp_path, "s1")
    assert result == {"verified": 1, "unverified": 1}
    units = store.load_units(tmp_path, "s1")
    assert units[0]["verified"] is True
    assert units[0]["loc"] == "p.3"
    assert units[1]["verified"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_verify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'verify'`.

- [ ] **Step 3: Write the implementation**

`verify.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

import store
from models import Source


def normalize_ws(s: str) -> str:
    return " ".join(s.split())


def locate(quote: str, source: Source) -> str | None:
    needle = normalize_ws(quote)
    if not needle:
        return None
    for seg in source.segments:
        if needle in normalize_ws(seg.text):
            return seg.loc
    return None


def _sources_by_id(chapter_dir: Path) -> dict[str, Source]:
    return {s.source_id: s for s in store.load_segments(chapter_dir)}


def verify_units_file(chapter_dir: Path, source_id: str) -> dict:
    sources = _sources_by_id(chapter_dir)
    src = sources.get(source_id)
    units = store.load_units(chapter_dir, source_id)
    verified = 0
    for u in units:
        loc = locate(u.get("quote", ""), src) if src else None
        u["verified"] = loc is not None
        if loc and not u.get("loc"):
            u["loc"] = loc
        verified += 1 if u["verified"] else 0
    store.save_units(chapter_dir, source_id, units)
    return {"verified": verified, "unverified": len(units) - verified}


def verify_report_file(chapter_dir: Path) -> dict:
    sources = _sources_by_id(chapter_dir)
    path = chapter_dir / "report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    unverified = 0
    for conn in report.get("connections", []):
        for ev in conn.get("evidence", []):
            src = sources.get(ev.get("source_id"))
            ok = bool(src) and locate(ev.get("quote", ""), src) is not None
            ev["verified"] = ok
            unverified += 0 if ok else 1
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"unverified_evidence": unverified}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_verify.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 5: Commit**

```bash
git add verify.py tests/test_verify.py
git commit -m "I built the verbatim quote verifier that flags unverified quotes and backfills locations"
```

---

## Task 9: Command-line harness

**Files:**
- Create: `throughline.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `ingest.ingest_chapter`, `verify.verify_units_file`, `verify.verify_report_file`, `store`.
- Produces CLI subcommands `new`, `ingest`, `verify`, `status`, all taking a chapter name and resolving it under `chapters/<name>`. `main(argv: list[str]) -> int` is the testable entry point.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from pathlib import Path

import throughline


def test_new_creates_chapter_scaffold(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = throughline.main(["new", "chapter1"])
    assert rc == 0
    assert (tmp_path / "chapters" / "chapter1" / "sources").is_dir()
    assert (tmp_path / "chapters" / "chapter1" / "thesis.md").exists()


def test_ingest_then_status_reports_counts(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    throughline.main(["new", "chapter1"])
    src = tmp_path / "chapters" / "chapter1" / "sources" / "a.md"
    src.write_text("One.\n\nTwo.\n", encoding="utf-8")
    assert throughline.main(["ingest", "chapter1"]) == 0
    assert throughline.main(["status", "chapter1"]) == 0
    out = capsys.readouterr().out
    assert "1 source" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'throughline'`.

- [ ] **Step 3: Write the implementation**

`throughline.py`:
```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import ingest
import store
import verify

_THESIS_STUB = "# Chapter thesis\n\nWrite the chapter thesis and theme note here.\n"


def _chapter_dir(name: str) -> Path:
    return Path("chapters") / name


def cmd_new(args) -> int:
    ch = _chapter_dir(args.chapter)
    (ch / "sources").mkdir(parents=True, exist_ok=True)
    (ch / "drafts").mkdir(parents=True, exist_ok=True)
    thesis = ch / "thesis.md"
    if not thesis.exists():
        thesis.write_text(_THESIS_STUB, encoding="utf-8")
    print(f"created chapter scaffold at {ch}")
    return 0


def cmd_ingest(args) -> int:
    sources = ingest.ingest_chapter(_chapter_dir(args.chapter))
    print(f"ingested {len(sources)} source(s)")
    return 0


def cmd_verify(args) -> int:
    ch = _chapter_dir(args.chapter)
    for src in store.load_segments(ch):
        r = verify.verify_units_file(ch, src.source_id)
        print(f"{src.source_id}: {r['verified']} verified, {r['unverified']} UNVERIFIED")
    if (ch / "report.json").exists():
        r = verify.verify_report_file(ch)
        print(f"report: {r['unverified_evidence']} UNVERIFIED evidence item(s)")
    return 0


def cmd_status(args) -> int:
    ch = _chapter_dir(args.chapter)
    seg = ch / "store" / "segments.json"
    n_sources = len(store.load_segments(ch)) if seg.exists() else 0
    n_units = len(list((ch / "store").glob("*.units.json"))) if seg.exists() else 0
    n_drafts = len(list((ch / "drafts").glob("*.md"))) if (ch / "drafts").exists() else 0
    has_report = (ch / "report.md").exists()
    print(f"{n_sources} source(s) ingested")
    print(f"{n_units} source(s) with extracted units")
    print(f"report present: {has_report}")
    print(f"{n_drafts} draft(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="throughline")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in [("new", cmd_new), ("ingest", cmd_ingest),
                     ("verify", cmd_verify), ("status", cmd_status)]:
        p = sub.add_parser(name)
        p.add_argument("chapter")
        p.set_defaults(func=fn)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 5: Commit**

```bash
git add throughline.py tests/test_cli.py
git commit -m "I wired the CLI with new, ingest, verify, and status subcommands"
```

---

## Task 10: The Throughline skill (reasoning stages)

**Files:**
- Create: `skills/throughline/SKILL.md`
- Create: `install-skill.sh`

**Interfaces:**
- Consumes: the CLI and store from Tasks 6, 8, 9. The skill reads `thesis.md`, `rubric.md`, `gold/`, and `store/*.json`, and writes `store/<source>.units.json`, `report.md`, `report.json`, and `drafts/*.md`.
- Produces: an installed skill invokable as `/throughline <stage> <chapter>`.

This task authors prose and an install script, so it is verified by a documented manual run rather than a unit test.

- [ ] **Step 1: Write the skill document**

`skills/throughline/SKILL.md`:
```markdown
---
name: throughline
description: Reads a chapter's sources and surfaces cross-source connections for a book or paper. Use for the extract, connect, draft, and critique stages of a Throughline chapter.
---

# /throughline

Orchestrates the reasoning stages of Throughline. Deterministic work (ingest, verify, status) is done by `throughline.py`. You do the reasoning here, always guided by `rubric.md` and any files in `gold/`.

## Usage

- `/throughline extract <chapter>` extract units from each ingested source
- `/throughline connect <chapter>` build the connection report
- `/throughline draft <chapter>` draft prose for kept connections
- `/throughline critique <chapter>` fold the scholar's mark-ups into the rubric

Resolve `<chapter>` to `chapters/<chapter>`. Always read `rubric.md` and every file in `gold/` first, and hold them as the standard for this scholar.

## extract

1. Run `python throughline.py ingest <chapter>` if `store/segments.json` is missing.
2. Read `store/segments.json`. For each source, read its segments.
3. For each source, produce a JSON array of units. Each unit is an object with `source_id`, `kind` (one of claim, concept, quote), `statement`, `quote` (verbatim from a segment), `loc` (copy the segment loc), and `theme_tags`.
4. Only use text that appears verbatim in the segments for `quote`. Never paraphrase inside a quote.
5. Write each array to `store/<source_id>.units.json`.
6. Run `python throughline.py verify <chapter>`. If any unit is UNVERIFIED, open the units file, fix or drop the offending quote, and rerun verify until zero are UNVERIFIED.

## connect

1. Read `thesis.md`, `rubric.md`, `gold/`, and every `store/*.units.json`.
2. Propose candidate cross-source connections that serve the thesis. Follow the rubric. Prefer connections that span disciplines and that the units genuinely support.
3. For each connection, produce an object with `id`, `move`, `sources_involved`, `interpretation`, `evidence` (a list of objects with `source_id`, `quote`, `loc`, drawn only from verified units), `advances_thesis`, `tensions` (required, name where the connection strains), `novelty` (0 to 1), `confidence` (0 to 1), `status` set to "candidate", and an empty `scholar_note`.
4. Write all connections to `report.json` under the key `connections`, and render a readable `report.md` from the same data.
5. Run `python throughline.py verify <chapter>`. Fix any UNVERIFIED evidence before finishing.

## draft

1. Read `report.json`. Draft only connections whose `status` is "keep".
2. For each kept connection, write `drafts/<id>.md`, prose in the register the rubric and gold examples set, weaving the verified quotes with citations that match the source metadata.
3. Mark each sentence's basis as evidence or interpretation in a trailing notes block, so the scholar can audit.
4. Do not introduce any quote that is not already verified in `report.json`.

## critique

1. Read the scholar's mark-ups (inline comments in `report.md`, `drafts/*.md`, or a `critique.md`).
2. Summarize the recurring preferences and objections.
3. Append them to `rubric.md` as new principles or anti-patterns, dated. Do not rewrite the scholar's existing rubric text, only add.
```

- [ ] **Step 2: Write the install script**

`install-skill.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
dst="$HOME/.claude/skills/throughline"
mkdir -p "$(dirname "$dst")"
ln -sfn "$(cd "$(dirname "$0")" && pwd)/skills/throughline" "$dst"
echo "linked $dst -> repo skills/throughline"
```

- [ ] **Step 3: Install and verify the skill is registered**

Run:
```bash
chmod +x install-skill.sh
./install-skill.sh
ls -l ~/.claude/skills/throughline/SKILL.md
```
Expected: the symlink resolves to the repo `SKILL.md`.

- [ ] **Step 4: Commit**

```bash
git add skills/throughline/SKILL.md install-skill.sh
git commit -m "I wrote the throughline skill for the extract, connect, draft, and critique stages"
```

---

## Task 11: Templates and README

**Files:**
- Create: `templates/rubric.md`
- Create: `templates/gold-example.md`
- Create: `README.md`
- Modify: `throughline.py` (have `new` copy the rubric template to `rubric.md` if absent, and create an empty `gold/`)
- Test: `tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: `cmd_new` from Task 9.
- Produces: `new` also seeds `rubric.md` (repo-level) and `gold/`.

- [ ] **Step 1: Write the failing test (extend the CLI test)**

Add to `tests/test_cli.py`:
```python
def test_new_seeds_rubric_and_gold(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "rubric.md").write_text("# Rubric\n", encoding="utf-8")
    throughline.main(["new", "chapter1"])
    assert (tmp_path / "rubric.md").exists()
    assert (tmp_path / "gold").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli.py::test_new_seeds_rubric_and_gold -v`
Expected: FAIL (`rubric.md` not created).

- [ ] **Step 3: Extend `cmd_new`**

In `throughline.py`, add to `cmd_new` before the `print`:
```python
    Path("gold").mkdir(exist_ok=True)
    rubric = Path("rubric.md")
    template = Path("templates") / "rubric.md"
    if not rubric.exists() and template.exists():
        rubric.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
```

- [ ] **Step 4: Write the template and README content**

`templates/rubric.md`:
```markdown
# Connection rubric

Principles the scholar holds for a strong cross-source connection. Grown over time by the critique stage.

## What makes a strong connection
- It advances the chapter thesis, not just restates a shared topic.
- It rests on what each source actually argues, quoted and located.
- It names a real mechanism or shared structure, not a surface word match.

## Anti-patterns to avoid
- Superficial similarity (two sources mention the same word).
- Name-dropping without engaging the argument.
- Ignoring the context or scope conditions of a claim.

## Voice and register
- Describe the target register here.

## Handling tensions
- Every connection must state where it strains or where the sources disagree.

## Citation norms
- Books cite by page. Papers cite by section or page. Match the source metadata.
```

`templates/gold-example.md`:
```markdown
# Gold example

A worked connection the scholar authored by hand, used as a demonstration.

## Thesis
Paste the chapter thesis this example served.

## Sources
List the sources and their key claims.

## The connection
Write the connective move and the interpretation, in the scholar's own words.

## The prose
Paste the paragraph the scholar wrote from this connection.
```

`README.md`:
```markdown
# Throughline

Reads mixed-type sources (books, articles, research papers) and surfaces cross-source connections for a chapter thesis, then drafts prose for the connections the scholar keeps. Reasoning runs on Claude via Claude Code. Deterministic work runs in `throughline.py`.

## Setup
```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./install-skill.sh
```

## Workflow
1. `python throughline.py new chapter1`
2. Write the thesis in `chapters/chapter1/thesis.md`, drop sources in `chapters/chapter1/sources/`, add a `sources/meta.json` if you want richer citations.
3. Fill in `rubric.md` and add at least one worked example under `gold/`.
4. `python throughline.py ingest chapter1`
5. `/throughline extract chapter1`
6. `/throughline connect chapter1`, then edit `report.md` to mark connections keep or drop.
7. `/throughline draft chapter1`
8. `/throughline critique chapter1` after you mark up the output.

Every quote is verified verbatim against its source. Anything unverifiable is flagged UNVERIFIED and never trusted.
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS, all CLI tests.

- [ ] **Step 6: Commit**

```bash
git add templates/ README.md throughline.py tests/test_cli.py
git commit -m "I added the rubric and gold templates, the README, and made new seed them"
```

---

## Task 12: End-to-end smoke test

**Files:**
- Create: `tests/fixtures/e2e/sources/source-a.md`
- Create: `tests/fixtures/e2e/sources/source-b.md`
- Test: `tests/test_e2e.py`

**Interfaces:**
- Consumes: `ingest`, `store`, `verify`.
- Produces: a test proving ingest, unit persistence, and verification run together on two sources and correctly separate a verified quote from an invented one.

- [ ] **Step 1: Create the fixture sources**

`tests/fixtures/e2e/sources/source-a.md`:
```
Memory is reconstructive, not a recording.

The past is rebuilt each time it is recalled.
```

`tests/fixtures/e2e/sources/source-b.md`:
```
Attention selects what later becomes memory.

What is unattended rarely leaves a trace.
```

- [ ] **Step 2: Write the end-to-end test**

`tests/test_e2e.py`:
```python
import shutil
from pathlib import Path

import ingest
import store
import verify

FIX = Path(__file__).parent / "fixtures" / "e2e"


def test_pipeline_ingests_stores_and_verifies(tmp_path: Path):
    chapter = tmp_path / "chapter1"
    shutil.copytree(FIX, chapter)

    sources = ingest.ingest_chapter(chapter)
    assert {s.source_id for s in sources} == {"source-a", "source-b"}

    store.save_units(chapter, "source-a", [
        {"source_id": "source-a", "kind": "claim", "statement": "memory is rebuilt",
         "quote": "Memory is reconstructive, not a recording.", "loc": ""},
        {"source_id": "source-a", "kind": "quote", "statement": "hallucinated",
         "quote": "Memory is a perfect video recording.", "loc": ""},
    ])

    result = verify.verify_units_file(chapter, "source-a")
    assert result == {"verified": 1, "unverified": 1}

    units = store.load_units(chapter, "source-a")
    assert units[0]["verified"] is True
    assert units[0]["loc"] == "para.1"
    assert units[1]["verified"] is False
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_e2e.py -v`
Expected: PASS.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/pytest -v`
Expected: all tests pass (the OCR test may SKIP if tesseract is not installed).

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/e2e/ tests/test_e2e.py
git commit -m "I added an end-to-end smoke test that runs ingest, storage, and verification on two sources"
```

---

## Self-review notes

- **Spec coverage.** Ingest with mixed loaders (Tasks 2 to 6), extraction schema (Task 7, plus the skill in Task 10), verbatim-quote verification and mandatory locations (Task 8), connection schema with required tensions (Task 7 and Task 10 connect), two-stage report-then-draft output (Task 10 connect and draft), calibration via rubric and gold with a critique loop (Tasks 10 and 11), file layout and commands (Tasks 9 and 11), testing including the smoke test (Task 12). The two spec open questions (OCR tool choice, starter source types) do not block the build.
- **Deferred by design.** Citation-network analysis and graphify integration are fast-follows, not in these tasks, matching the spec non-goals.
- **Type consistency.** `Source` and `Segment` signatures, store function names, and verify return shapes are used identically across tasks.
