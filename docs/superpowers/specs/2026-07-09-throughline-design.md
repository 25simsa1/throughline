# Throughline Design

- **Date.** 2026-07-09
- **Status.** Approved design, pre-implementation
- **Working name.** Throughline (rename freely)

## Problem

A scholar is writing a book whose early chapters draw on many sources (books, journal articles, research papers) across different disciplines. They have not read most of the sources in full, but they hold a general sense of how the sources might connect. They want a tool that reads the sources for them and helps make the nuanced, cross-disciplinary connections they would make themselves if they had read everything. Generic chat summarization does not satisfy them, because it stays shallow and does not match the standard of an expert reader.

The scholar is a demanding reader and wants to remain the author of the argument. The tool augments their judgment. It does not replace it.

## Goals

- Ingest sources of mixed type (text passages, digital PDF or EPUB, scanned or photographed pages) into one normalized store.
- Extract structured, traceable material from each source so the scholar does not have to read them in full.
- Surface candidate cross-source connections tied to a chapter thesis, each grounded in verbatim evidence.
- Let the scholar pick the promising connections, then draft prose for those, in their register.
- Learn the scholar's standard through a rubric plus worked examples, refined by a critique loop.
- Never present unverifiable or fabricated evidence.

## Non-goals (for the MVP)

- No fine-tuning of any model.
- No citation or reference-network analysis yet (fast-follow for papers).
- No graphify integration yet (back-pocket upgrade for the 20-source scale-up).
- No standalone runnable program yet (skill-driven, operator-run for now).
- No polished GUI. The scholar interacts by editing Markdown files while Simon operates the tool.

## Locked decisions

1. **Reasoning engine.** Claude via Claude Code, skill-driven, using existing Claude Code access. No metered API key. Python does the deterministic work.
2. **Input.** Pluggable loaders for text, digital PDF or EPUB, and scanned or OCR sources, all normalizing into one store.
3. **Output.** Two stages. First a connection report of candidates, then drafted prose for the connections the scholar keeps.
4. **Calibration.** A written rubric plus gold worked examples, refined by a critique loop.

## Architecture overview

Two layers of responsibility.

- **Python harness (`throughline.py` plus `loaders/`).** Deterministic work. Ingest, normalize, chunk, store, verify verbatim quotes, report status, and gather the right context for each reasoning step. Fully testable.
- **Claude skill (`~/.claude/skills/throughline/SKILL.md`).** The reasoning work. Extract units, build the connection report, draft prose, and fold critiques into the rubric. Prompted every time with the rubric and the relevant gold example.

The store on disk is the single source of truth. Every stage reads from it and writes back to it, so any stage can rerun without redoing earlier work.

## Pipeline

| Stage | Owner | Input | Output |
|---|---|---|---|
| Ingest | Python | raw files in `sources/` | `store/segments.json` (normalized text with locations) |
| Extract | Claude | segments for one source | `store/<source>.units.json` (claims, concepts, quotes) |
| Verify | Python | units plus segments | units annotated verified or UNVERIFIED |
| Connect | Claude | all units plus thesis plus rubric plus gold | `report.md` and `report.json` |
| Select | Scholar | `report.md` | keep or drop marks plus steering notes |
| Draft | Claude | kept connections plus rubric plus gold | `drafts/<connection>.md` |
| Critique | Claude | scholar mark-ups | appended principles in `rubric.md` |

## Data schemas

Locations adapt to source type. A book uses page or chapter. A paper uses a section path such as `§3.2`, `abstract`, or a page. Every unit and every quote must carry a location, or it is rejected.

### Segment (from ingestion)

```json
{
  "source_id": "book-a",
  "title": "…",
  "author": "…",
  "year": 2019,
  "venue": "…",
  "type": "book | article | paper",
  "segments": [
    { "loc": "p.42", "text": "…" }
  ]
}
```

### Unit (from extraction)

```json
{
  "source_id": "book-a",
  "kind": "claim | concept | quote",
  "statement": "the book's claim, or concept definition, in plain words",
  "quote": "verbatim text from the source",
  "loc": "p.42",
  "theme_tags": ["memory", "time"],
  "verified": true
}
```

### Connection (from connect)

```json
{
  "id": "connection-3",
  "move": "one-line statement of the connective idea",
  "sources_involved": ["book-a", "paper-c"],
  "interpretation": "the nuanced argument linking the sources",
  "evidence": [
    { "source_id": "book-a", "quote": "…", "loc": "p.42" },
    { "source_id": "paper-c", "quote": "…", "loc": "§4.1" }
  ],
  "advances_thesis": "how it serves the chapter argument",
  "tensions": "counterpoints, disanalogies, where the connection strains",
  "novelty": 0.0,
  "confidence": 0.0,
  "status": "candidate | keep | drop",
  "scholar_note": ""
}
```

The `tensions` field is required, not optional. A connection presented with no friction reads as superficial to an expert reader, so the connect stage must always surface where the link is weak or contestable.

## Calibration mechanics

- **`rubric.md`.** The scholar's principles, authored by them and grown over time. Sections cover what makes a strong connection, anti-patterns to avoid (superficial similarity, name-dropping, ignoring context), voice and register, how to treat tensions, and citation norms for books versus papers. Every reasoning stage receives the current rubric.
- **`gold/`.** Worked examples the scholar authored by hand. Each holds a thesis, its sources, the connection they drew, and the prose they wrote. Used as few-shot demonstrations in the connect and draft stages. The MVP starts with one example, the scholar's own manual connection for the first two sources.
- **Critique loop.** The scholar marks up any report or draft. The critique stage reads the mark-ups, proposes new principles or anti-patterns, and appends them to `rubric.md`. Strong scholar edits can later become additional gold examples.

## Trust guardrails

These are non-negotiable, because fabricated evidence would immediately lose a demanding scholar's trust.

- **Verbatim-quote verification.** After extraction and after connect and draft, the Python harness checks that every quoted string actually appears in the source segments, normalized for whitespace. A quote not found is flagged UNVERIFIED and never silently trusted.
- **Locations are mandatory.** Every claim and quote carries a location. Unlocatable units are rejected at verification.
- **Evidence versus interpretation.** The connect and draft stages must label a statement as evidence (backed by a quote in the store) or as interpretation (the scholar's or the model's reasoning). The model cannot present an unsupported assertion as fact.
- **Idempotent stages.** Rerunning a stage regenerates its outputs from the store. The store is authoritative.

## File layout

```
~/throughline/
  chapters/
    chapter1/
      thesis.md            # the scholar's chapter thesis and theme note
      sources/             # scholar drops in pdf, epub, txt, or image files
      store/               # generated: segments.json, <source>.units.json
      report.md            # connection candidates, human readable
      report.json          # machine-readable sidecar of the same
      drafts/              # prose per kept connection
  rubric.md                # global calibration principles
  gold/                    # worked examples
  throughline.py           # CLI harness
  loaders/                 # text, pdf, epub, ocr adapters
  tests/                   # pytest suite plus fixtures
  docs/superpowers/specs/  # this spec and future ones
~/.claude/skills/throughline/SKILL.md   # orchestration
```

## Commands

Reasoning commands run through the skill. Deterministic commands run through the harness directly.

- `/throughline ingest chapter1` runs the loaders and builds the store.
- `/throughline extract chapter1` extracts units per source, then the harness verifies quotes.
- `/throughline connect chapter1` builds the connection report.
- `/throughline draft chapter1` drafts prose for kept connections.
- `/throughline critique chapter1` folds the scholar's critiques into the rubric.
- `python throughline.py status chapter1` shows where the chapter stands.

## Ingestion loaders

Each loader takes a raw file and returns the normalized segment structure above. They share one interface so new source types plug in without touching the rest of the pipeline.

- **text.** Reads `.txt` and `.md`. Locations are line or paragraph ranges. Trivial.
- **pdf.** PyMuPDF (fitz) extracts text with page numbers. For papers it keeps section headings where detectable.
- **epub.** ebooklib plus BeautifulSoup extract text with chapter and section anchors.
- **ocr.** For scanned or image PDFs. The MVP wires a working-but-basic adapter (ocrmypdf or pytesseract behind the tesseract binary). The interface is clean enough that DeepSeek-OCR or Claude vision can swap in later for higher accuracy.

The loader also attempts to capture academic metadata (title, authors, year, venue) so the draft stage can cite papers correctly.

## Error handling

- Loaders report unparseable files rather than failing the whole run. OCR surfaces low-confidence pages.
- Extraction output is validated against the unit JSON shape before it is stored. Malformed output triggers a retry of that source only.
- The quote verifier is a hard gate. Nothing marked UNVERIFIED flows into a draft without the scholar seeing the flag.

## Testing

- Unit tests for each loader, using tiny fixture files, asserting correct text and locations.
- Unit tests for the quote verifier, including a case that catches a paraphrase presented as a quote.
- A store round-trip test.
- Reasoning stages are gated by JSON-shape validation plus the automated quote verifier rather than by asserting on content.
- One small end-to-end smoke test on two short public-domain sources, confirming the whole pipeline runs.

## Dependencies

- Python 3.11 or newer.
- PyMuPDF, ebooklib, beautifulsoup4 for parsing.
- ocrmypdf or pytesseract plus a tesseract install for the OCR adapter.
- pytest for tests.

## MVP scope

One chapter, two sources, the full extract, connect, draft, critique loop, a rubric, and one gold example. OCR is basic. Content-based connections only.

## Fast-follows and future work

- **Citation and reference network.** For papers, parse reference lists and surface shared-citation and direct-citation links as an extra connection source.
- **graphify integration.** At the 20-source scale, use graphify's community detection as an additional connection source feeding the connect stage. Its value grows with corpus size.
- **Standalone program.** Move to the Claude Agent SDK on the Claude Code login if the scholar wants to run the tool without an interactive Claude Code session.
- **Friendlier selection.** Replace Markdown-editing selection with a lighter interface once the workflow is proven.

## Open questions

- Exact OCR tool choice for the MVP adapter (ocrmypdf versus pytesseract) pending a quick accuracy check on a real scanned page.
- Whether the two starter sources will be papers, books, or one of each, which affects which loader gets exercised first.
