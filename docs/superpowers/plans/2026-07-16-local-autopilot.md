# Throughline Local Autopilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `python throughline.py extract|connect|draft <chapter>` run the full reasoning pipeline on local Ollama models with no Claude session, plus swap OCR to Apple Vision with a scanned-PDF fallback.

**Architecture:** A stdlib-only Ollama client (`llm.py`, injectable transport) feeds three stage modules under `stages/`. Extract batches pages into unit-extraction prompts and repairs or drops unverified quotes. Connect embeds units, shortlists cross-source pairs by cosine similarity, then prompts once per pair with thesis, rubric, and gold, enforcing that evidence quotes are copied from supplied units. Draft renders kept connections into prose with a deterministic quoted-span check. `render.py` renders and parses report.md so CLI and skill share one format.

**Tech Stack:** Python 3.11+, stdlib urllib/json for HTTP, Ollama structured outputs (JSON schema as `format`), `granite-embedding:30m` for embeddings, `qwen3:14b` with `granite3.3:8b` fallback for reasoning, `ocrmac` (Apple Vision) with pytesseract fallback, PyMuPDF rasterization for scanned PDFs, pytest.

## Global Constraints

Every task's requirements implicitly include these.

- Python 3.11+. New third-party dependency allowed: `ocrmac` only. No numpy, no requests, no ollama pip package. HTTP via stdlib urllib.
- Repo at `~/throughline`, branch `feat/local-autopilot`, venv at `.venv` (run tests with `.venv/bin/pytest`).
- Commits are casual, lowercase-leaning, first-person student voice (match `git log` in this repo, e.g. "wrote the pdf loader so each page becomes one located chunk"). NEVER any Co-Authored-By or AI-attribution trailer.
- All stage tests must run green with no Ollama server, using the injectable transport. The existing 39-test suite stays green.
- A quote is trusted only if verbatim (whitespace-normalized) in its source; anything else is repaired once then dropped or flagged, never silently kept.
- Env vars honored. `OLLAMA_HOST` (default `http://localhost:11434`), `THROUGHLINE_MODEL` (overrides model choice). Embeddings always `granite-embedding:30m`.
- In authored Markdown prose (README, SKILL), avoid em dashes and avoid colons in sentences. Code and structural labels exempt.

---

## File structure

```
~/throughline/
  llm.py                    # OllamaClient: pick_model, generate(schema+validate+retry), embed
  render.py                 # render_report_md + parse_decisions (shared CLI/skill format)
  stages/
    __init__.py
    extract_stage.py        # run_extract + repair loop
    connect_stage.py        # cosine, shortlist_pairs, run_connect
    draft_stage.py          # run_draft + quoted-span check
  loaders/
    ocr_text.py             # image_to_text via ocrmac -> pytesseract fallback
    ocr_loader.py           # modified to use ocr_text
    pdf_loader.py           # modified: rasterize+OCR pages with empty text layer
  throughline.py            # modified: extract/connect/draft subcommands
  tests/
    test_llm.py
    test_render.py
    test_ocr_text.py
    test_pdf_scanned.py
    test_extract_stage.py
    test_connect_stage.py
    test_draft_stage.py
    test_autopilot_e2e.py
    test_live_ollama.py     # live smoke, skips when server/model absent
    fakes.py                # FakeTransport shared by stage tests
```

---

## Task 1: Ollama client (`llm.py`)

**Files:**
- Create: `llm.py`
- Create: `tests/fakes.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces: `LlmError(Exception)`; `OllamaClient(host=None, transport=None)` with `.list_models() -> list[str]`, `.pick_model() -> str`, `.generate(prompt, *, system="", schema=None, validate=None, model=None, retries=2) -> dict`, `.embed(texts: list[str]) -> list[list[float]]`. `transport(url: str, payload: dict | None) -> dict` (None payload means GET). Module constants `PREFERRED_MODELS = ("qwen3:14b", "granite3.3:8b")`, `EMBED_MODEL = "granite-embedding:30m"`.

- [ ] **Step 1: Write the shared fake transport**

`tests/fakes.py`:
```python
from __future__ import annotations

import json


class FakeTransport:
    """Queue-based fake for llm transport. Register responses per url suffix."""

    def __init__(self):
        self.queues: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, dict | None]] = []

    def add(self, suffix: str, response: dict):
        self.queues.setdefault(suffix, []).append(response)

    def add_chat_json(self, obj):
        self.add("/api/chat", {"message": {"content": json.dumps(obj)}})

    def __call__(self, url: str, payload: dict | None) -> dict:
        self.calls.append((url, payload))
        for suffix, queue in self.queues.items():
            if url.endswith(suffix):
                if not queue:
                    raise AssertionError(f"no queued response left for {suffix}")
                return queue.pop(0)
        raise AssertionError(f"unexpected url {url}")
```

- [ ] **Step 2: Write the failing tests**

`tests/test_llm.py`:
```python
import pytest

import llm
from tests.fakes import FakeTransport


def _client(ft):
    return llm.OllamaClient(host="http://fake:11434", transport=ft)


def test_pick_model_prefers_qwen_then_granite(monkeypatch):
    monkeypatch.delenv("THROUGHLINE_MODEL", raising=False)
    ft = FakeTransport()
    ft.add("/api/tags", {"models": [{"name": "granite3.3:8b"}, {"name": "qwen3:14b"}]})
    assert _client(ft).pick_model() == "qwen3:14b"
    ft2 = FakeTransport()
    ft2.add("/api/tags", {"models": [{"name": "granite3.3:8b"}]})
    assert _client(ft2).pick_model() == "granite3.3:8b"


def test_pick_model_env_override(monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "mistral:7b")
    assert _client(FakeTransport()).pick_model() == "mistral:7b"


def test_pick_model_errors_when_nothing_usable(monkeypatch):
    monkeypatch.delenv("THROUGHLINE_MODEL", raising=False)
    ft = FakeTransport()
    ft.add("/api/tags", {"models": [{"name": "granite-embedding:30m"}]})
    with pytest.raises(llm.LlmError):
        _client(ft).pick_model()


def test_generate_parses_json_and_strips_think(monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ft = FakeTransport()
    ft.add("/api/chat", {"message": {"content": "<think>hmm</think>{\"a\": 1}"}})
    out = _client(ft).generate("p", schema={"type": "object"})
    assert out == {"a": 1}
    url, payload = ft.calls[-1]
    assert payload["format"] == {"type": "object"}
    assert payload["stream"] is False


def test_generate_retries_on_validation_errors(monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ft = FakeTransport()
    ft.add_chat_json({"n": 1})
    ft.add_chat_json({"n": 2})
    calls = []

    def validate(obj):
        calls.append(obj)
        return [] if obj["n"] == 2 else ["n must be 2"]

    out = _client(ft).generate("p", validate=validate, retries=2)
    assert out == {"n": 2}
    assert "n must be 2" in ft.calls[-1][1]["messages"][-1]["content"]


def test_generate_raises_after_retries_exhausted(monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ft = FakeTransport()
    ft.add_chat_json({"n": 1})
    ft.add_chat_json({"n": 1})
    with pytest.raises(llm.LlmError):
        _client(ft).generate("p", validate=lambda o: ["bad"], retries=1)


def test_embed_returns_vectors(monkeypatch):
    ft = FakeTransport()
    ft.add("/api/embed", {"embeddings": [[0.1, 0.2], [0.3, 0.4]]})
    vecs = _client(ft).embed(["a", "b"])
    assert vecs == [[0.1, 0.2], [0.3, 0.4]]
    assert ft.calls[-1][1]["model"] == llm.EMBED_MODEL
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm'`.

- [ ] **Step 4: Write the implementation**

`llm.py`:
```python
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_HOST = "http://localhost:11434"
PREFERRED_MODELS = ("qwen3:14b", "granite3.3:8b")
EMBED_MODEL = "granite-embedding:30m"
_THINK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)


class LlmError(Exception):
    pass


def _default_transport(url: str, payload: dict | None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise LlmError(f"cannot reach ollama at {url}; is `ollama serve` running? ({e})")


class OllamaClient:
    def __init__(self, host: str | None = None, transport=None):
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self.transport = transport or _default_transport

    def list_models(self) -> list[str]:
        r = self.transport(f"{self.host}/api/tags", None)
        return [m["name"] for m in r.get("models", [])]

    def pick_model(self) -> str:
        env = os.environ.get("THROUGHLINE_MODEL")
        if env:
            return env
        names = self.list_models()
        for want in PREFERRED_MODELS:
            if any(n == want or n.startswith(want) for n in names):
                return want
        raise LlmError(
            f"no reasoning model found; run `ollama pull {PREFERRED_MODELS[0]}` "
            f"or set THROUGHLINE_MODEL (installed: {names})"
        )

    def generate(self, prompt: str, *, system: str = "", schema: dict | None = None,
                 validate=None, model: str | None = None, retries: int = 2) -> dict:
        model = model or self.pick_model()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        last_errors: list[str] = []
        for _ in range(retries + 1):
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.2},
            }
            if schema is not None:
                payload["format"] = schema
            r = self.transport(f"{self.host}/api/chat", payload)
            content = _THINK_RE.sub("", r["message"]["content"]).strip()
            try:
                obj = json.loads(content)
            except json.JSONDecodeError as e:
                last_errors = [f"reply was not valid JSON: {e}"]
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": self._retry_prompt(last_errors)})
                continue
            errors = validate(obj) if validate else []
            if not errors:
                return obj
            last_errors = errors
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": self._retry_prompt(errors)})
        raise LlmError(f"model output failed validation after retries: {last_errors}")

    @staticmethod
    def _retry_prompt(errors: list[str]) -> str:
        listed = "; ".join(errors)
        return (
            f"Your previous reply had these problems: {listed}. "
            "Reply again with corrected JSON only, no commentary."
        )

    def embed(self, texts: list[str], model: str = EMBED_MODEL) -> list[list[float]]:
        r = self.transport(f"{self.host}/api/embed", {"model": model, "input": texts})
        return r["embeddings"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_llm.py -v`
Expected: PASS, 7 passed.

- [ ] **Step 6: Commit**

```bash
git add llm.py tests/fakes.py tests/test_llm.py
git commit -m "built the ollama client, schema-constrained generate with a validation retry loop plus embeddings"
```

---

## Task 2: Report rendering and decision parsing (`render.py`)

**Files:**
- Create: `render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: nothing new (pure functions over dicts/strings).
- Produces: `render.render_report_md(report: dict, chapter: str) -> str`; `render.parse_decisions(md_text: str) -> dict[str, dict]` mapping connection id to `{"decision": "keep"|"drop"|"candidate", "note": str}` (decision lowercased).

- [ ] **Step 1: Write the failing tests**

`tests/test_render.py`:
```python
import render

REPORT = {
    "provenance": "generated by tests",
    "connections": [
        {
            "id": "C1",
            "move": "Title one. The rest of the move sentence.",
            "sources_involved": ["a", "b"],
            "interpretation": "Interp text.",
            "evidence": [
                {"source_id": "a", "quote": "line one\nline two", "loc": "p.2"},
            ],
            "advances_thesis": "Advances.",
            "tensions": "Strains here.",
            "novelty": 0.5,
            "confidence": 0.6,
            "status": "candidate",
            "scholar_note": "",
        }
    ],
}


def test_render_report_md_shape():
    md = render.render_report_md(REPORT, "demo")
    assert "# Connection report, chapter demo" in md
    assert "## C1. Title one" in md
    assert "**Interpretation.** Interp text." in md
    assert '- a, p.2. "line one line two"' in md
    assert "**Tensions.** Strains here." in md
    assert "Decision: candidate" in md


def test_parse_decisions_round_trip():
    md = render.render_report_md(REPORT, "demo")
    d = render.parse_decisions(md)
    assert d == {"C1": {"decision": "candidate", "note": ""}}


def test_parse_decisions_reads_edits_and_notes():
    md = render.render_report_md(REPORT, "demo").replace(
        "Decision: candidate", "Decision: KEEP\nNote: love this one"
    )
    d = render.parse_decisions(md)
    assert d["C1"]["decision"] == "keep"
    assert d["C1"]["note"] == "love this one"


def test_parse_decisions_handles_scholar_style_report():
    md = (
        "# Connection report, chapter x\n\n"
        "## C2. Ontology is the shared fault line\n\n"
        "stuff\n\nDecision: keep\n\n---\n\n"
        "## C4. The method risks the imposition it studies\n\n"
        "Decision: drop\nNote: This is not a strong connection.\n"
    )
    d = render.parse_decisions(md)
    assert d["C2"]["decision"] == "keep"
    assert d["C4"] == {"decision": "drop", "note": "This is not a strong connection."}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'render'`.

- [ ] **Step 3: Write the implementation**

`render.py`:
```python
from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^##\s+(\S+)\.\s")
_DECISION_RE = re.compile(r"^Decision:\s*(\w+)", re.IGNORECASE)
_NOTE_RE = re.compile(r"^Note:\s*(.*)")


def _one_line(s: str) -> str:
    return " ".join(str(s).split())


def _split_move(move: str) -> tuple[str, str]:
    parts = move.split(". ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return move.rstrip("."), ""


def render_report_md(report: dict, chapter: str) -> str:
    lines = [f"# Connection report, chapter {chapter}", ""]
    if report.get("provenance"):
        lines += [_one_line(report["provenance"]), ""]
    for conn in report.get("connections", []):
        title, rest = _split_move(conn.get("move", conn["id"]))
        lines += ["---", "", f"## {conn['id']}. {title}", ""]
        lines += [f"**Sources.** {', '.join(conn.get('sources_involved', []))}", ""]
        if rest:
            lines += [f"**The move.** {_one_line(rest)}", ""]
        lines += [f"**Interpretation.** {_one_line(conn.get('interpretation', ''))}", ""]
        lines += ["**Evidence.**"]
        for ev in conn.get("evidence", []):
            lines += [f'- {ev.get("source_id")}, {ev.get("loc")}. "{_one_line(ev.get("quote", ""))}"']
        lines += ["", f"**Advances the thesis.** {_one_line(conn.get('advances_thesis', ''))}", ""]
        lines += [f"**Tensions.** {_one_line(conn.get('tensions', ''))}", ""]
        lines += [f"Novelty {conn.get('novelty', 0)}. Confidence {conn.get('confidence', 0)}.", ""]
        status = conn.get("status") or "candidate"
        lines += [f"Decision: {status}", ""]
        if conn.get("scholar_note"):
            lines += [f"Note: {conn['scholar_note']}", ""]
    lines += ["---", "", "To change a decision, edit its Decision line and rerun the draft stage.", ""]
    return "\n".join(lines)


def parse_decisions(md_text: str) -> dict[str, dict]:
    decisions: dict[str, dict] = {}
    current: str | None = None
    for line in md_text.splitlines():
        h = _HEADING_RE.match(line.strip())
        if h:
            current = h.group(1)
            decisions[current] = {"decision": "candidate", "note": ""}
            continue
        if current is None:
            continue
        d = _DECISION_RE.match(line.strip())
        if d:
            decisions[current]["decision"] = d.group(1).lower()
            continue
        n = _NOTE_RE.match(line.strip())
        if n:
            decisions[current]["note"] = n.group(1).strip()
    return decisions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: PASS, 4 passed.

- [ ] **Step 5: Commit**

```bash
git add render.py tests/test_render.py
git commit -m "added a shared report renderer and a decision-line parser so the cli and skill speak one format"
```

---

## Task 3: Apple Vision OCR helper and scanned-PDF fallback

**Files:**
- Create: `loaders/ocr_text.py`
- Modify: `loaders/ocr_loader.py`
- Modify: `loaders/pdf_loader.py`
- Test: `tests/test_ocr_text.py`
- Test: `tests/test_pdf_scanned.py`

**Interfaces:**
- Produces: `ocr_text.image_to_text(image) -> str` accepting a PIL Image, trying ocrmac (Apple Vision) then pytesseract, raising `OcrUnavailable(Exception)` when neither backend works. `ocr_text.available() -> bool`.
- `PdfLoader` behavior change: a page with an empty text layer is rasterized at 200 dpi and OCRed; if OCR is unavailable the old behavior (skip page) remains, with a stderr warning.

- [ ] **Step 1: Install the new dependency**

Run:
```bash
.venv/bin/pip install ocrmac
.venv/bin/pip freeze > requirements.txt
```
Expected: ocrmac plus pyobjc packages appear in requirements.txt.

- [ ] **Step 2: Write the failing tests**

`tests/test_ocr_text.py`:
```python
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
```

`tests/test_pdf_scanned.py`:
```python
from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageDraw

from loaders import ocr_text
from loaders.pdf_loader import PdfLoader

pytestmark = pytest.mark.skipif(not ocr_text.available(), reason="no OCR backend on this machine")


def _scanned_pdf(path: Path):
    img = Image.new("RGB", (800, 160), "white")
    ImageDraw.Draw(img).text((20, 50), "SCANNED PAGE ABOUT MEMORY", fill="black")
    img_path = path.parent / "page.png"
    img.save(img_path)
    doc = fitz.open()
    page = doc.new_page(width=800, height=160)
    page.insert_image(fitz.Rect(0, 0, 800, 160), filename=str(img_path))
    doc.save(path)


def test_scanned_pdf_gets_ocr_text(tmp_path: Path):
    pdf = tmp_path / "scan.pdf"
    _scanned_pdf(pdf)
    src = PdfLoader().load(pdf, "scan-1")
    assert len(src.segments) == 1
    assert src.segments[0].loc == "p.1"
    assert "MEMORY" in src.segments[0].text.upper()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ocr_text.py tests/test_pdf_scanned.py -v`
Expected: FAIL with `ImportError` (ocr_text does not exist).

- [ ] **Step 4: Write the implementation**

`loaders/ocr_text.py`:
```python
from __future__ import annotations

import shutil
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
    except Exception:
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
```

`loaders/ocr_loader.py` (replace whole file):
```python
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
```

`loaders/pdf_loader.py` (replace whole file):
```python
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
```

- [ ] **Step 5: Run the new tests and the full suite**

Run: `.venv/bin/pytest tests/test_ocr_text.py tests/test_pdf_scanned.py tests/test_ocr_loader.py tests/test_pdf_loader.py -v` then `.venv/bin/pytest -q`
Expected: new tests PASS (tesseract and ocrmac both installed on this machine), old loader tests still PASS, full suite green.

- [ ] **Step 6: Commit**

```bash
git add loaders/ requirements.txt tests/test_ocr_text.py tests/test_pdf_scanned.py
git commit -m "switched ocr to apple vision with tesseract fallback and made scanned pdfs rasterize+ocr instead of ingesting empty"
```

---

## Task 4: Extract stage

**Files:**
- Create: `stages/__init__.py` (empty)
- Create: `stages/extract_stage.py`
- Modify: `throughline.py` (add `extract` subcommand)
- Test: `tests/test_extract_stage.py`

**Interfaces:**
- Consumes: `llm.OllamaClient`, `store`, `schemas.validate_unit`, `verify.verify_units_file`, `verify.normalize_ws`, `models.Source`.
- Produces: `extract_stage.run_extract(chapter_dir: Path, client, *, model: str | None = None, max_units_per_source: int = 20) -> dict` returning `{source_id: {"kept": int, "dropped": int}}`. CLI `throughline.py extract <chapter> [--model M]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_extract_stage.py`:
```python
from pathlib import Path

import store
from models import Segment, Source
from stages import extract_stage
from tests.fakes import FakeTransport
import llm


def _chapter(tmp_path: Path) -> Path:
    src = Source(
        source_id="s1", title="T", type="paper",
        segments=[Segment(loc="p.1", text="Memory is reconstructive, not a recording.")],
    )
    store.save_segments(tmp_path, [src])
    return tmp_path


def _client(ft):
    return llm.OllamaClient(host="http://fake", transport=ft)


def test_extract_writes_verified_units(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({"units": [{
        "source_id": "s1", "kind": "claim", "statement": "memory is rebuilt",
        "quote": "Memory is reconstructive", "loc": "p.1", "theme_tags": ["memory"],
    }]})
    result = extract_stage.run_extract(ch, _client(ft))
    assert result["s1"] == {"kept": 1, "dropped": 0}
    units = store.load_units(ch, "s1")
    assert units[0]["verified"] is True


def test_extract_repairs_then_drops_bad_quotes(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({"units": [
        {"source_id": "s1", "kind": "claim", "statement": "real",
         "quote": "Memory is reconstructive", "loc": "p.1", "theme_tags": []},
        {"source_id": "s1", "kind": "claim", "statement": "invented",
         "quote": "a hallucinated span", "loc": "p.1", "theme_tags": []},
    ]})
    ft.add_chat_json({"quote": "still not in the page"})
    result = extract_stage.run_extract(ch, _client(ft))
    assert result["s1"] == {"kept": 1, "dropped": 1}
    units = store.load_units(ch, "s1")
    assert len(units) == 1 and units[0]["statement"] == "real"


def test_extract_repair_can_rescue_a_quote(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({"units": [
        {"source_id": "s1", "kind": "claim", "statement": "rescued",
         "quote": "wrong words here", "loc": "p.1", "theme_tags": []},
    ]})
    ft.add_chat_json({"quote": "not a recording"})
    result = extract_stage.run_extract(ch, _client(ft))
    assert result["s1"] == {"kept": 1, "dropped": 0}
    units = store.load_units(ch, "s1")
    assert units[0]["quote"] == "not a recording"
    assert units[0]["verified"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_extract_stage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stages'`.

- [ ] **Step 3: Write the implementation**

`stages/extract_stage.py`:
```python
from __future__ import annotations

from pathlib import Path

import schemas
import store
import verify

BATCH_CHARS = 6000

UNIT_SCHEMA = {
    "type": "object",
    "properties": {
        "units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["claim", "concept", "quote"]},
                    "statement": {"type": "string"},
                    "quote": {"type": "string"},
                    "loc": {"type": "string"},
                    "theme_tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["source_id", "kind", "statement", "quote", "loc"],
            },
        }
    },
    "required": ["units"],
}

REPAIR_SCHEMA = {
    "type": "object",
    "properties": {"quote": {"type": "string"}},
    "required": ["quote"],
}

EXTRACT_PROMPT = """You are extracting research units from one scholarly source.

Source id: {source_id}
Pages below are labeled [p.N]. Extract up to {n} units from THESE pages only.

A unit is one of
- claim, the source argues something
- concept, the source defines or names something
- quote, a striking passage worth citing as-is

Hard rules
- "quote" must be an exact contiguous span copied character for character from ONE page below, 5 to 35 words. Never paraphrase inside "quote".
- "loc" must be the page label the quote came from, one of {locs}.
- "statement" is your plain-words summary.
- "source_id" is always "{source_id}".

Pages
{pages}
"""

REPAIR_PROMPT = """The quote below was supposed to be an exact span from the page text but it is not found there.

Statement it should support: {statement}
Page [{loc}] text:
{page}

Reply with an exact contiguous span (5 to 35 words) copied character for character from the page text above that best supports the statement.
"""


def _batches(segments, limit=BATCH_CHARS):
    batch, size = [], 0
    for seg in segments:
        if batch and size + len(seg.text) > limit:
            yield batch
            batch, size = [], 0
        batch.append(seg)
        size += len(seg.text)
    if batch:
        yield batch


def _validate_units(obj, source_id, allowed_locs):
    errors = []
    for i, u in enumerate(obj.get("units", [])):
        if isinstance(u, dict):
            u["source_id"] = source_id
            u.setdefault("theme_tags", [])
        errors += [f"[{i}] {e}" for e in schemas.validate_unit(u)] if isinstance(u, dict) else [f"[{i}] not an object"]
        if isinstance(u, dict) and u.get("loc") and u["loc"] not in allowed_locs:
            errors.append(f"[{i}] loc {u['loc']!r} is not one of the page labels given")
    return errors


def run_extract(chapter_dir: Path, client, *, model: str | None = None,
                max_units_per_source: int = 20) -> dict:
    model = model or client.pick_model()
    summary = {}
    for src in store.load_segments(chapter_dir):
        units = []
        for batch in _batches(src.segments):
            locs = [s.loc for s in batch]
            pages = "\n\n".join(f"[{s.loc}]\n{s.text}" for s in batch)
            per_batch = max(4, max_units_per_source // max(1, len(src.segments) // max(1, len(batch))))
            obj = client.generate(
                EXTRACT_PROMPT.format(source_id=src.source_id, n=per_batch,
                                      locs=", ".join(locs), pages=pages),
                schema=UNIT_SCHEMA,
                validate=lambda o, sid=src.source_id, al=set(locs): _validate_units(o, sid, al),
                model=model,
            )
            units.extend(obj["units"])
        units = units[:max_units_per_source]
        store.save_units(chapter_dir, src.source_id, units)
        verify.verify_units_file(chapter_dir, src.source_id)
        kept, dropped = _repair_or_drop(chapter_dir, src, client, model)
        summary[src.source_id] = {"kept": kept, "dropped": dropped}
    return summary


def _repair_or_drop(chapter_dir: Path, src, client, model) -> tuple[int, int]:
    units = store.load_units(chapter_dir, src.source_id)
    pages = {s.loc: s.text for s in src.segments}
    for u in units:
        if u.get("verified"):
            continue
        page = pages.get(u.get("loc"), "")
        if page:
            try:
                fix = client.generate(
                    REPAIR_PROMPT.format(statement=u.get("statement", ""),
                                         loc=u.get("loc"), page=page),
                    schema=REPAIR_SCHEMA, model=model, retries=0,
                )
                u["quote"] = fix.get("quote", u["quote"])
            except Exception:
                pass
    store.save_units(chapter_dir, src.source_id, units)
    verify.verify_units_file(chapter_dir, src.source_id)
    units = store.load_units(chapter_dir, src.source_id)
    kept = [u for u in units if u.get("verified")]
    dropped = len(units) - len(kept)
    store.save_units(chapter_dir, src.source_id, kept)
    return len(kept), dropped
```

- [ ] **Step 4: Wire the CLI**

In `throughline.py` add imports `import llm` and `from stages import extract_stage`, then:
```python
def cmd_extract(args) -> int:
    ch = _chapter_dir(args.chapter)
    if not (ch / "store" / "segments.json").exists():
        print(f"error: chapter '{args.chapter}' not ingested yet; run 'ingest' first", file=sys.stderr)
        return 1
    try:
        client = llm.OllamaClient()
        summary = extract_stage.run_extract(ch, client, model=args.model)
    except llm.LlmError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for sid, r in summary.items():
        print(f"{sid}: {r['kept']} unit(s) kept, {r['dropped']} dropped")
    return 0
```
Register in `main` alongside the other subcommands, with `--model` (default None). Use a loop-safe pattern, subcommands that take `--model` get it added after `set_defaults`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_extract_stage.py -v` then `.venv/bin/pytest -q`
Expected: PASS, full suite green.

- [ ] **Step 6: Commit**

```bash
git add stages/ throughline.py tests/test_extract_stage.py
git commit -m "wired the local extract stage, batches pages into the model and repairs or drops anything the verifier rejects"
```

---

## Task 5: Connect stage, shortlist math

**Files:**
- Create: `stages/connect_stage.py` (math half)
- Test: `tests/test_connect_stage.py` (math tests)

**Interfaces:**
- Produces: `connect_stage.cosine(a: list[float], b: list[float]) -> float`; `connect_stage.shortlist_pairs(units: list[dict], vectors: list[list[float]], k: int = 12, max_per_unit: int = 2) -> list[tuple[int, int]]` returning index pairs, cross-source only, sorted by similarity descending, no unit appearing in more than `max_per_unit` pairs.

- [ ] **Step 1: Write the failing tests**

`tests/test_connect_stage.py` (first half):
```python
from stages import connect_stage


def test_cosine_basics():
    assert connect_stage.cosine([1, 0], [1, 0]) == 1.0
    assert connect_stage.cosine([1, 0], [0, 1]) == 0.0
    assert connect_stage.cosine([0, 0], [1, 0]) == 0.0


def test_shortlist_pairs_cross_source_only_and_capped():
    units = [
        {"source_id": "a"}, {"source_id": "a"},
        {"source_id": "b"}, {"source_id": "c"},
    ]
    vectors = [
        [1.0, 0.0], [0.9, 0.1],
        [0.95, 0.05], [0.0, 1.0],
    ]
    pairs = connect_stage.shortlist_pairs(units, vectors, k=2)
    assert (0, 2) in pairs
    assert all(units[i]["source_id"] != units[j]["source_id"] for i, j in pairs)
    assert len(pairs) == 2


def test_shortlist_respects_max_per_unit():
    units = [{"source_id": "a"}, {"source_id": "b"}, {"source_id": "c"}, {"source_id": "d"}]
    vectors = [[1, 0], [0.99, 0.01], [0.98, 0.02], [0.97, 0.03]]
    pairs = connect_stage.shortlist_pairs(units, vectors, k=10, max_per_unit=1)
    flat = [i for p in pairs for i in p]
    assert len(flat) == len(set(flat))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_connect_stage.py -v`
Expected: FAIL with `ModuleNotFoundError` or `AttributeError`.

- [ ] **Step 3: Write the math half of the implementation**

`stages/connect_stage.py` (start of file; the LLM half arrives in Task 6):
```python
from __future__ import annotations

import math
from pathlib import Path


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def shortlist_pairs(units: list[dict], vectors: list[list[float]],
                    k: int = 12, max_per_unit: int = 2) -> list[tuple[int, int]]:
    scored = []
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            if units[i]["source_id"] == units[j]["source_id"]:
                continue
            scored.append((cosine(vectors[i], vectors[j]), i, j))
    scored.sort(reverse=True)
    used: dict[int, int] = {}
    pairs = []
    for _, i, j in scored:
        if used.get(i, 0) >= max_per_unit or used.get(j, 0) >= max_per_unit:
            continue
        pairs.append((i, j))
        used[i] = used.get(i, 0) + 1
        used[j] = used.get(j, 0) + 1
        if len(pairs) >= k:
            break
    return pairs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_connect_stage.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 5: Commit**

```bash
git add stages/connect_stage.py tests/test_connect_stage.py
git commit -m "added the embedding shortlist math, cross-source cosine pairs with a per-unit cap"
```

---

## Task 6: Connect stage, LLM half

**Files:**
- Modify: `stages/connect_stage.py`
- Modify: `throughline.py` (add `connect` subcommand)
- Test: `tests/test_connect_stage.py` (extend)

**Interfaces:**
- Consumes: Task 5's functions, `llm.OllamaClient`, `store.load_all_units`, `schemas.validate_connection`, `verify.normalize_ws`, `verify.verify_report_file`, `render.render_report_md`.
- Produces: `connect_stage.run_connect(chapter_dir: Path, client, *, model=None, top_k=12, max_connections=6) -> int` (number of connections written). Writes `report.json` and `report.md`. Evidence loc/source_id are rewritten deterministically from the matched unit. CLI `connect <chapter> [--model M] [--top-k N] [--max-connections N]`.

- [ ] **Step 1: Write the failing tests (append to `tests/test_connect_stage.py`)**

```python
import json

import store
from models import Segment, Source
from tests.fakes import FakeTransport
import llm


def _chapter(tmp_path):
    a = Source(source_id="a", title="A", type="paper",
               segments=[Segment(loc="p.1", text="Alpha claims memory is social.")])
    b = Source(source_id="b", title="B", type="paper",
               segments=[Segment(loc="p.2", text="Beta claims recall is collective.")])
    store.save_segments(tmp_path, [a, b])
    store.save_units(tmp_path, "a", [{
        "source_id": "a", "kind": "claim", "statement": "memory social",
        "quote": "memory is social", "loc": "p.1", "verified": True}])
    store.save_units(tmp_path, "b", [{
        "source_id": "b", "kind": "claim", "statement": "recall collective",
        "quote": "recall is collective", "loc": "p.2", "verified": True}])
    (tmp_path / "thesis.md").write_text("# Thesis\nMemory is collective.", encoding="utf-8")
    return tmp_path


def _conn_obj(quote_a="memory is social", quote_b="recall is collective"):
    return {
        "id": "X", "move": "Title. Move text.",
        "sources_involved": ["a", "b"],
        "interpretation": "Together they say more.",
        "evidence": [
            {"source_id": "a", "quote": quote_a, "loc": "p.9"},
            {"source_id": "b", "quote": quote_b, "loc": "p.9"},
        ],
        "advances_thesis": "Directly.",
        "tensions": "Different senses of collective.",
        "novelty": 0.5, "confidence": 0.8,
        "status": "candidate", "scholar_note": "",
    }


def test_run_connect_writes_verified_report(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add("/api/embed", {"embeddings": [[1.0, 0.0], [0.9, 0.1]]})
    ft.add_chat_json(_conn_obj())
    client = llm.OllamaClient(host="http://fake", transport=ft)
    n = connect_stage.run_connect(ch, client, top_k=1, max_connections=3)
    assert n == 1
    report = json.loads((ch / "report.json").read_text(encoding="utf-8"))
    conn = report["connections"][0]
    assert conn["id"] == "C1"
    assert conn["evidence"][0]["loc"] == "p.1"  # loc rewritten from the matched unit
    assert all(ev["verified"] for ev in conn["evidence"])
    md = (ch / "report.md").read_text(encoding="utf-8")
    assert "Decision: candidate" in md


def test_run_connect_rejects_fabricated_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add("/api/embed", {"embeddings": [[1.0, 0.0], [0.9, 0.1]]})
    ft.add_chat_json(_conn_obj(quote_a="a quote that exists nowhere"))
    ft.add_chat_json(_conn_obj(quote_a="a quote that exists nowhere"))
    ft.add_chat_json(_conn_obj(quote_a="a quote that exists nowhere"))
    client = llm.OllamaClient(host="http://fake", transport=ft)
    n = connect_stage.run_connect(ch, client, top_k=1, max_connections=3)
    assert n == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_connect_stage.py -v`
Expected: the two new tests FAIL with `AttributeError: run_connect`.

- [ ] **Step 3: Append the LLM half to `stages/connect_stage.py`**

```python
import json

import render
import schemas
import store
import verify

CONN_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "move": {"type": "string"},
        "sources_involved": {"type": "array", "items": {"type": "string"}},
        "interpretation": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "quote": {"type": "string"},
                    "loc": {"type": "string"},
                },
                "required": ["source_id", "quote", "loc"],
            },
        },
        "advances_thesis": {"type": "string"},
        "tensions": {"type": "string"},
        "novelty": {"type": "number"},
        "confidence": {"type": "number"},
    },
    "required": ["move", "sources_involved", "interpretation", "evidence",
                 "advances_thesis", "tensions", "novelty", "confidence"],
}

CONNECT_PROMPT = """You are proposing ONE scholarly connection between two sources for a book chapter.

Chapter thesis
{thesis}

The author's rubric for a strong connection
{rubric}

A gold example of the standard (the author's own connective move)
{gold}

Allowed units. Your evidence quotes MUST be copied character for character from the "quote" fields below (a shorter contiguous sub-span is fine). Do not invent or paraphrase quotes.
{units}

Focus units. Build the connection primarily between unit {i} and unit {j}.

Produce one connection object.
- "move" is a short title, then a period, then a one-sentence statement of the connective idea.
- "interpretation" argues the connection in 120 to 250 words and must go beyond summarizing either source, proposing a claim neither makes alone.
- "tensions" must honestly name where the connection strains.
- "sources_involved" lists the source_ids you actually drew on.
- "novelty" and "confidence" are 0 to 1.
"""


def _load_context(chapter_dir: Path) -> tuple[str, str, str]:
    thesis = (chapter_dir / "thesis.md").read_text(encoding="utf-8") if (chapter_dir / "thesis.md").exists() else ""
    root = chapter_dir.parent.parent
    rubric_p = root / "rubric.md"
    rubric = rubric_p.read_text(encoding="utf-8")[:2500] if rubric_p.exists() else ""
    gold = ""
    gold_dir = root / "gold"
    if gold_dir.is_dir():
        for p in sorted(gold_dir.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            marker = "## The connection"
            if marker in text:
                gold = text.split(marker, 1)[1][:2500]
                break
    return thesis[:2000], rubric, gold


def _units_block(units: list[dict], idxs: list[int]) -> str:
    lines = []
    for n in idxs:
        u = units[n]
        lines.append(
            f'unit {n}: source_id={u["source_id"]} loc={u["loc"]} kind={u["kind"]}\n'
            f'  statement: {u["statement"]}\n  quote: {u["quote"]}'
        )
    return "\n".join(lines)


def _match_evidence(conn: dict, allowed: list[dict]) -> list[str]:
    errors = []
    for m, ev in enumerate(conn.get("evidence", []) or []):
        if not isinstance(ev, dict):
            errors.append(f"evidence[{m}] is not an object")
            continue
        needle = verify.normalize_ws(ev.get("quote", ""))
        hit = next((u for u in allowed if needle and needle in verify.normalize_ws(u["quote"])), None)
        if hit is None:
            errors.append(f"evidence[{m}] quote is not copied from the allowed units")
        else:
            ev["source_id"] = hit["source_id"]
            ev["loc"] = hit["loc"]
    return errors


def run_connect(chapter_dir: Path, client, *, model: str | None = None,
                top_k: int = 12, max_connections: int = 6) -> int:
    model = model or client.pick_model()
    units = [u for u in store.load_all_units(chapter_dir) if u.get("verified")]
    if len(units) < 2:
        raise ValueError("need at least two verified units across sources; run extract first")
    vectors = client.embed([f'{u["statement"]} {u["quote"]}' for u in units])
    pairs = shortlist_pairs(units, vectors, k=top_k)
    thesis, rubric, gold = _load_context(chapter_dir)
    conns = []
    for i, j in pairs:
        siblings_i = [n for n, u in enumerate(units) if u["source_id"] == units[i]["source_id"] and n != i][:2]
        siblings_j = [n for n, u in enumerate(units) if u["source_id"] == units[j]["source_id"] and n != j][:2]
        idxs = [i, j] + siblings_i + siblings_j
        allowed = [units[n] for n in idxs]

        def validate(obj, allowed=allowed):
            errs = [e for e in schemas.validate_connection({**obj, "id": "tmp"}) if "'id'" not in e]
            errs += _match_evidence(obj, allowed)
            return errs

        try:
            obj = client.generate(
                CONNECT_PROMPT.format(thesis=thesis, rubric=rubric, gold=gold,
                                      units=_units_block(units, idxs), i=i, j=j),
                schema=CONN_SCHEMA, validate=validate, model=model, retries=2,
            )
        except Exception:
            continue
        obj["status"] = "candidate"
        obj["scholar_note"] = ""
        conns.append(obj)
    conns.sort(key=lambda c: c.get("confidence", 0), reverse=True)
    conns = conns[:max_connections]
    for n, c in enumerate(conns, 1):
        c["id"] = f"C{n}"
    report = {
        "provenance": f"generated by the local autopilot (model {model})",
        "connections": conns,
    }
    (chapter_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (chapter_dir / "report.md").write_text(
        render.render_report_md(report, chapter_dir.name), encoding="utf-8")
    verify.verify_report_file(chapter_dir)
    return len(conns)
```

- [ ] **Step 4: Wire the CLI**

In `throughline.py` add `from stages import connect_stage` and:
```python
def cmd_connect(args) -> int:
    ch = _chapter_dir(args.chapter)
    try:
        client = llm.OllamaClient()
        n = connect_stage.run_connect(ch, client, model=args.model,
                                      top_k=args.top_k, max_connections=args.max_connections)
    except (llm.LlmError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"wrote {n} connection(s) to report.md; mark Decision lines keep or drop, then run draft")
    return 0
```
Register with `--model`, `--top-k` (int, default 12), `--max-connections` (int, default 6).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_connect_stage.py -v` then `.venv/bin/pytest -q`
Expected: PASS, full suite green.

- [ ] **Step 6: Commit**

```bash
git add stages/connect_stage.py throughline.py tests/test_connect_stage.py
git commit -m "finished the connect stage, per-pair prompts with rubric and gold, evidence must be copied from real units or its rejected"
```

---

## Task 7: Draft stage

**Files:**
- Create: `stages/draft_stage.py`
- Modify: `throughline.py` (add `draft` subcommand)
- Test: `tests/test_draft_stage.py`

**Interfaces:**
- Consumes: `render.parse_decisions`, `verify.normalize_ws`, `llm.OllamaClient`.
- Produces: `draft_stage.quoted_spans(text: str) -> list[str]`; `draft_stage.check_quotes(text: str, evidence_quotes: list[str]) -> list[str]` (returns offending spans); `draft_stage.run_draft(chapter_dir: Path, client, *, model=None) -> list[str]` (ids drafted). CLI `draft <chapter> [--model M]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_draft_stage.py`:
```python
import json
from pathlib import Path

from stages import draft_stage
from tests.fakes import FakeTransport
import llm


def test_quoted_spans_and_check():
    text = 'He says "memory is social" and also “recall is collective” and "made up".'
    spans = draft_stage.quoted_spans(text)
    assert "memory is social" in spans and "recall is collective" in spans
    bad = draft_stage.check_quotes(text, ["Alpha memory is social beta", "recall is collective"])
    assert bad == ["made up"]


def _chapter(tmp_path: Path):
    report = {"connections": [{
        "id": "C1", "move": "T. M.", "sources_involved": ["a"],
        "interpretation": "x", "evidence": [
            {"source_id": "a", "quote": "memory is social", "loc": "p.1", "verified": True}],
        "advances_thesis": "x", "tensions": "x", "novelty": 0.5, "confidence": 0.5,
        "status": "candidate", "scholar_note": ""}]}
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "report.md").write_text(
        "## C1. T\n\nDecision: keep\n", encoding="utf-8")
    (tmp_path / "drafts").mkdir(exist_ok=True)
    return tmp_path


def test_run_draft_writes_kept_only(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({"draft_markdown": 'Prose quoting "memory is social" faithfully.'})
    client = llm.OllamaClient(host="http://fake", transport=ft)
    drafted = draft_stage.run_draft(ch, client)
    assert drafted == ["C1"]
    text = (ch / "drafts" / "C1.md").read_text(encoding="utf-8")
    assert "memory is social" in text
    assert "UNVERIFIED" not in text


def test_run_draft_flags_unverified_spans(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ch = _chapter(tmp_path)
    ft = FakeTransport()
    ft.add_chat_json({"draft_markdown": 'Prose quoting "an invented line" boldly.'})
    ft.add_chat_json({"draft_markdown": 'Prose quoting "an invented line" boldly.'})
    client = llm.OllamaClient(host="http://fake", transport=ft)
    drafted = draft_stage.run_draft(ch, client)
    assert drafted == ["C1"]
    text = (ch / "drafts" / "C1.md").read_text(encoding="utf-8")
    assert "UNVERIFIED" in text and "an invented line" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_draft_stage.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

`stages/draft_stage.py`:
```python
from __future__ import annotations

import json
import re
from pathlib import Path

import render
import verify

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {"draft_markdown": {"type": "string"}},
    "required": ["draft_markdown"],
}

_QUOTE_RE = re.compile(r'[“"]([^”"]{4,300})[”"]')

DRAFT_PROMPT = """You are drafting one paragraph of scholarly prose for a book chapter, realizing the connection below.

The author's rubric (voice, tensions, citation norms)
{rubric}

The author's own prose, as the register to match
{gold}

The connection to draft
{connection}

Rules
- 150 to 300 words of publishable prose, no headings, no bullet lists.
- Any text you place inside double quotes MUST be copied character for character from the connection's evidence quotes (shorter contiguous sub-spans are fine). Never invent a quotation.
- Cite as the rubric directs (author-date in running prose).
- Let the connection's tensions show, do not sand them off.
"""


def quoted_spans(text: str) -> list[str]:
    return [m.group(1) for m in _QUOTE_RE.finditer(text)]


def check_quotes(text: str, evidence_quotes: list[str]) -> list[str]:
    normalized = [verify.normalize_ws(q) for q in evidence_quotes]
    bad = []
    for span in quoted_spans(text):
        ns = verify.normalize_ws(span)
        if not any(ns in q for q in normalized):
            bad.append(span)
    return bad


def _load_voice(chapter_dir: Path) -> tuple[str, str]:
    root = chapter_dir.parent.parent
    rubric_p = root / "rubric.md"
    rubric = rubric_p.read_text(encoding="utf-8")[:2500] if rubric_p.exists() else ""
    gold = ""
    gold_dir = root / "gold"
    if gold_dir.is_dir():
        for p in sorted(gold_dir.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            marker = "## The prose"
            if marker in text:
                gold = text.split(marker, 1)[1][:3000]
                break
    return rubric, gold


def run_draft(chapter_dir: Path, client, *, model: str | None = None) -> list[str]:
    model = model or client.pick_model()
    report = json.loads((chapter_dir / "report.json").read_text(encoding="utf-8"))
    decisions = render.parse_decisions(
        (chapter_dir / "report.md").read_text(encoding="utf-8"))
    rubric, gold = _load_voice(chapter_dir)
    (chapter_dir / "drafts").mkdir(exist_ok=True)
    drafted = []
    for conn in report.get("connections", []):
        if decisions.get(conn["id"], {}).get("decision") != "keep":
            continue
        ev_quotes = [e.get("quote", "") for e in conn.get("evidence", [])]
        prompt = DRAFT_PROMPT.format(
            rubric=rubric, gold=gold,
            connection=json.dumps(conn, ensure_ascii=False, indent=2))
        obj = client.generate(prompt, schema=DRAFT_SCHEMA, model=model)
        bad = check_quotes(obj["draft_markdown"], ev_quotes)
        if bad:
            retry_prompt = prompt + (
                "\nYour previous draft quoted spans that are not in the evidence: "
                + "; ".join(bad) + ". Redraft using only evidence quotes inside quotation marks."
            )
            obj = client.generate(retry_prompt, schema=DRAFT_SCHEMA, model=model)
            bad = check_quotes(obj["draft_markdown"], ev_quotes)
        title = conn.get("move", conn["id"]).split(". ", 1)[0]
        out = [f"# Draft {conn['id']}. {title}", "", obj["draft_markdown"].strip(), ""]
        if bad:
            out += ["## WARNING, UNVERIFIED quoted spans", ""]
            out += [f"- \"{s}\"" for s in bad]
            out += ["", "These spans are not in the verified evidence. Check before use.", ""]
        out += ["---", "",
                "Drafted by the local autopilot. Quotes inside double quotation marks "
                "were checked against the connection's verified evidence"
                + (" and all passed." if not bad else ", failures listed above."), ""]
        path = chapter_dir / "drafts" / f"{conn['id']}.md"
        path.write_text("\n".join(out), encoding="utf-8")
        drafted.append(conn["id"])
    return drafted
```

- [ ] **Step 4: Wire the CLI**

In `throughline.py` add `from stages import draft_stage` and:
```python
def cmd_draft(args) -> int:
    ch = _chapter_dir(args.chapter)
    if not (ch / "report.json").exists() or not (ch / "report.md").exists():
        print("error: no report found; run connect first", file=sys.stderr)
        return 1
    try:
        client = llm.OllamaClient()
        drafted = draft_stage.run_draft(ch, client, model=args.model)
    except llm.LlmError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not drafted:
        print("no connections are marked keep in report.md")
    for cid in drafted:
        print(f"drafted {cid} -> drafts/{cid}.md")
    return 0
```
Register with `--model`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_draft_stage.py -v` then `.venv/bin/pytest -q`
Expected: PASS, full suite green.

- [ ] **Step 6: Commit**

```bash
git add stages/draft_stage.py throughline.py tests/test_draft_stage.py
git commit -m "added the draft stage with a hard check that every quoted span comes from verified evidence"
```

---

## Task 8: End-to-end fake pipeline test, live smoke, docs

**Files:**
- Create: `tests/test_autopilot_e2e.py`
- Create: `tests/test_live_ollama.py`
- Modify: `README.md`
- Modify: `skills/throughline/SKILL.md`

**Interfaces:**
- Consumes: everything above.
- Produces: proof the three stages compose through the CLI with a fake model, a live smoke that skips cleanly, and docs.

- [ ] **Step 1: Write the e2e test**

`tests/test_autopilot_e2e.py`:
```python
import json
from pathlib import Path

import throughline
import llm
from stages import extract_stage, connect_stage, draft_stage
from tests.fakes import FakeTransport


def test_full_autopilot_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    monkeypatch.chdir(tmp_path)
    throughline.main(["new", "chapter1"])
    ch = tmp_path / "chapters" / "chapter1"
    (ch / "sources" / "a.md").write_text("Alpha says memory is social.", encoding="utf-8")
    (ch / "sources" / "b.md").write_text("Beta says recall is collective.", encoding="utf-8")
    (ch / "thesis.md").write_text("Memory is collective.", encoding="utf-8")
    assert throughline.main(["ingest", "chapter1"]) == 0

    ft = FakeTransport()
    ft.add_chat_json({"units": [{"source_id": "a", "kind": "claim", "statement": "s",
                                 "quote": "memory is social", "loc": "para.1", "theme_tags": []}]})
    ft.add_chat_json({"units": [{"source_id": "b", "kind": "claim", "statement": "s",
                                 "quote": "recall is collective", "loc": "para.1", "theme_tags": []}]})
    ft.add("/api/embed", {"embeddings": [[1.0, 0.0], [0.9, 0.1]]})
    ft.add_chat_json({
        "id": "X", "move": "T. M.", "sources_involved": ["a", "b"],
        "interpretation": "i", "evidence": [
            {"source_id": "a", "quote": "memory is social", "loc": "x"},
            {"source_id": "b", "quote": "recall is collective", "loc": "x"}],
        "advances_thesis": "t", "tensions": "strain", "novelty": 0.5, "confidence": 0.9})
    ft.add_chat_json({"draft_markdown": 'Both agree that "memory is social".'})
    client = llm.OllamaClient(host="http://fake", transport=ft)

    extract_stage.run_extract(ch, client)
    n = connect_stage.run_connect(ch, client, top_k=1)
    assert n == 1
    md = (ch / "report.md").read_text(encoding="utf-8")
    (ch / "report.md").write_text(md.replace("Decision: candidate", "Decision: keep"), encoding="utf-8")
    drafted = draft_stage.run_draft(ch, client)
    assert drafted == ["C1"]
    assert (ch / "drafts" / "C1.md").exists()
    report = json.loads((ch / "report.json").read_text(encoding="utf-8"))
    assert all(ev["verified"] for ev in report["connections"][0]["evidence"])
```

- [ ] **Step 2: Write the live smoke test**

`tests/test_live_ollama.py`:
```python
import urllib.request

import pytest

import llm


def _server_up() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _server_up(), reason="ollama server not running")


def test_live_pick_model_and_tiny_generate():
    client = llm.OllamaClient()
    try:
        model = client.pick_model()
    except llm.LlmError:
        pytest.skip("no preferred reasoning model installed")
    out = client.generate(
        'Reply with JSON {"ok": true}',
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        model=model, retries=1,
    )
    assert out["ok"] is True


def test_live_embeddings():
    client = llm.OllamaClient()
    if llm.EMBED_MODEL.split(":")[0] not in " ".join(client.list_models()):
        pytest.skip("embedding model not installed")
    vecs = client.embed(["hello", "world"])
    assert len(vecs) == 2 and len(vecs[0]) > 10
```

- [ ] **Step 3: Update README.md**

Append this section before "Known limitations" (adjust wording to fit, keep the no em dash, no prose colon rule):
```markdown
## Local autopilot

The reasoning stages can run fully locally on Ollama, no Claude session needed.

Setup, one time. Install Ollama, then
```
ollama pull qwen3:14b
ollama pull granite-embedding:30m
```
If qwen3:14b is missing the tool falls back to granite3.3:8b. Set THROUGHLINE_MODEL to force a model.

Run
```
python throughline.py extract chapter1
python throughline.py connect chapter1
# edit report.md, mark each Decision line keep or drop
python throughline.py draft chapter1
```
Every quote is still machine-verified against the sources. Connections from a local model are serviceable but shallower than the Claude skill's; use the skill for the connections that must impress.
```

- [ ] **Step 4: Update SKILL.md**

Add one short paragraph under the usage section noting that `extract`, `connect`, and `draft` also exist as fully local CLI commands running on Ollama, that both paths share the same files and verifier, and that the skill remains the higher-quality path for connect and draft.

- [ ] **Step 5: Run everything**

Run: `.venv/bin/pytest -q`
Expected: all tests pass; `test_live_ollama.py` runs (server is up on this machine) or skips; zero warnings.

- [ ] **Step 6: Commit**

```bash
git add tests/test_autopilot_e2e.py tests/test_live_ollama.py README.md skills/throughline/SKILL.md
git commit -m "e2e test for the local pipeline, a live ollama smoke that skips politely, and docs for the autopilot"
```

---

## Self-review notes

- **Spec coverage.** Ollama client with injectable transport (T1), shared report format (T2), Vision OCR plus scanned-PDF fix (T3), extract with repair-or-drop (T4), two-stage connect with copied-evidence enforcement (T5, T6), draft with quoted-span check (T7), e2e plus live smoke plus docs (T8). Model management (pick_model, env overrides, fail-fast message) in T1. CLI flags per spec in T4/T6/T7.
- **Type consistency.** `client.generate` signature, `FakeTransport.add_chat_json`, unit and connection schemas, and `normalize_ws` usage are identical across tasks.
- **Known accepted risks.** `run_connect` overwrites report.json/report.md (documented in spec). The extract per-batch unit budget is a heuristic. The draft retry appends to the prompt rather than using chat history, acceptable for one retry.
