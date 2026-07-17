# Code tour

A guided walk through the codebase, in the order that makes the design make sense. Each stop says what to open, what to look for, and why it exists. Following along takes about 45 minutes with the files open.

## The 30-second map

Everything is a pipeline over plain files on disk.

```
sources/ (pdf, epub, txt, images)
   -> loaders/            everything becomes located text
   -> store/segments.json the raw material, one segment per page with a loc
   -> extract             a model pulls claims/concepts/quotes as "units"
   -> verify              every quote checked verbatim against the source
   -> store/<src>.units.json   only verified units survive
   -> connect             embeddings shortlist pairs, a model argues connections
   -> report.md / report.json  human surface / machine record
   -> (a human marks Decision: keep or drop)
   -> draft               prose per kept connection, quotes machine-checked
   -> drafts/<id>.md
```

Two principles explain almost every line. First, deterministic Python does everything that can be deterministic (parsing, storage, verification, rendering), and a model does only the reasoning. Second, the system fails closed. A quote that cannot be verified verbatim against the source never survives as trusted, no matter which model produced it.

## Stop 1. `models.py`, the atoms

Two dataclasses. `Segment` is a chunk of source text plus a `loc` string ("p.4" for a PDF page, "para.2" for a text file). `Source` is a document's metadata plus its segments. Everything else in the system is built from these. Notice there is no cleverness here, just `to_dict`/`from_dict` so they round-trip through JSON.

## Stop 2. `loaders/`, everything becomes located text

Open `base.py` first, it is the whole contract, a `Loader` has `extensions` and a `load(path, source_id) -> Source`. Then `registry.py`, which picks a loader by file extension. Then skim one concrete loader, `pdf_loader.py` is the most interesting, one segment per page, and if a page has no text layer it rasterizes the page and OCRs it (that is the scanned-book path). `ocr_text.py` is the OCR backend chooser, Apple Vision first, tesseract as fallback.

The point of the design, adding a new input format touches exactly one new file plus one registry line.

## Stop 3. `store.py` and `ingest.py`, the disk is the truth

`store.py` reads and writes the JSON files under `chapters/<name>/store/`. `ingest.py` walks `sources/`, dispatches to loaders, merges an optional `meta.json` sidecar (authors, years), skips files it cannot parse with a warning instead of dying, and saves `segments.json`. After this point no stage ever goes back to the PDFs, the store is the single source of truth, which is what makes every stage rerunnable.

## Stop 4. `schemas.py`, shape law

Pure functions that check dicts and return a list of error strings, empty means valid. A unit needs `source_id`, `kind` (claim, concept, or quote), `statement`, `quote`, `loc`. A connection needs, among other things, non-empty `tensions`, that is a content rule enforced as a shape rule, a connection that names no weakness is not accepted. These validators run both in tests and live inside the model retry loop.

## Stop 5. `verify.py`, the trust guardrail

The most important 70 lines in the repo. `normalize_ws` collapses whitespace. `locate(quote, source)` returns the loc of the first segment whose normalized text contains the normalized quote, or None. `verify_units_file` stamps every unit `verified` true or false, and if a quote is real but its claimed page is wrong it corrects the loc and stamps `loc_corrected` as a permanent audit flag. `verify_report_file` does the same for the evidence in a report.

Read the docstring on `locate`, it documents the one known limit, matching is per segment, so a quote spanning a page break flags as unverified by design.

## Stop 6. `llm.py`, talking to the local model

A stdlib-only HTTP client for Ollama. Three things to notice. `pick_model` honors `THROUGHLINE_MODEL`, then walks a preference list and returns the actually-installed tag. `generate` sends a JSON schema as Ollama's `format` so the model is constrained to valid shapes, runs a caller-supplied `validate` function on the reply, and on errors appends them to the conversation and retries, exhaustion raises `LlmError`. And the `think` flag, thinking models like qwen3 burn minutes of reasoning budget before schema-constrained output starts, so thinking is disabled for them, this single line was the difference between ten-minute timeouts and seven-second calls.

The `transport` argument is injectable, which is how the whole test suite runs with no model at all (see stop 11).

## Stop 7. `stages/extract_stage.py`, reading so you do not have to

Batches a source's pages (about 3000 chars per batch), prompts for units in the schema, validates shape, then hands everything to the verifier. Units with unverifiable quotes get exactly one repair round (re-prompt with the page text, asking for an exact span) and are then dropped. The final save writes only verified units, there is no code path where an unverified unit reaches disk. A source that fails entirely is recorded in the summary and the run continues to the next source. The `--resume` flag skips sources that already have a units file, which is what makes overnight runs restartable.

## Stop 8. `stages/connect_stage.py`, the two-stage trick

Small local models cannot hold twenty sources in their head, so connect is split. Stage one is arithmetic, embed every unit with a tiny embedding model, compute cosine similarity for every cross-source pair, shortlist the top K. Stage two prompts the reasoning model once per shortlisted pair, with the thesis, the author's rubric, and the gold example in every prompt.

The trust move here is `_match_evidence`, every evidence quote the model returns must be a substring of one of the unit quotes it was given, and the matched unit's source and loc overwrite whatever the model claimed. A connection whose evidence cannot be matched is rejected after retries, never kept. After writing the report, the verifier runs again as an independent second gate and a nonzero unverified count raises.

## Stop 9. `stages/draft_stage.py`, prose with a leash

Reads the Decision lines out of `report.md` (humans edit that file, nothing else), drafts prose for keeps only, then runs a deterministic check, every span inside double quotes or curly single quotes in the draft must be a substring of that connection's evidence. Violations get one redraft, then the draft is written with a loud warning block naming the unverified spans. The draft is never silently trusted and never silently blocked, the human sees exactly what failed.

## Stop 10. `render.py` and `throughline.py`, the seams

`render.py` renders `report.json` into the `report.md` format and parses Decision lines back out, one module so the CLI and the Claude skill speak the same format. `throughline.py` is the argparse CLI, `new`, `ingest`, `verify`, `status` are pure Python, `extract`, `connect`, `draft` drive the model stages. Every command fails with a clear message and exit code 1 rather than a traceback for the states a user will actually hit.

`skills/throughline/SKILL.md` is the other front end, the same stages run by a stronger model in a Claude Code session, reading and writing the same files, gated by the same verifier.

## Stop 11. `tests/`, what green actually proves

`tests/fakes.py` holds `FakeTransport`, a queue of canned model replies keyed by URL suffix. Every stage test injects it, so the suite proves the plumbing, validation, retry, repair, and guardrails without any model running. The tests worth reading as documentation, `test_verify.py` (a paraphrase is caught, a wrong page is corrected and flagged), `test_connect_stage.py` (fabricated evidence yields zero connections), `test_draft_stage.py` (an invented quoted span is flagged, curly quotes included), and `test_autopilot_e2e.py` (the three stages compose through real files). `test_live_ollama.py` is the one test that touches the real server and it skips politely when there is none.

## Try it with your own hands

Trace one unit end to end on the demo chapter.

```
python throughline.py new tour-demo
echo "Memory is reconstructive, not a recording." > chapters/tour-demo/sources/a.md
echo "Recall is a collective act performed by groups." > chapters/tour-demo/sources/b.md
python throughline.py ingest tour-demo
python throughline.py extract tour-demo
python -m json.tool chapters/tour-demo/store/a.units.json
python throughline.py connect tour-demo --top-k 2 --max-connections 1
cat chapters/tour-demo/report.md
```

Then break it on purpose, open `a.units.json`, change a quote to something not in the source, run `python throughline.py verify tour-demo`, and watch it get flagged. That flag is the whole philosophy in one line of output.
