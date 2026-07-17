# Throughline Local Autopilot Design

- **Date.** 2026-07-16
- **Status.** Approved design, pre-implementation
- **Builds on.** 2026-07-09-throughline-design.md (the MVP spec). Everything there still holds; this spec adds an automated path.

## Problem

Today the reasoning stages (extract, connect, draft) run through a Claude Code chat session, so every run needs Simon at the keyboard. The goal is a fully automated pipeline, one terminal command per stage, no chat session, running entirely on local models so it is free, private, and runnable by anyone with a Mac (eventually the scholar). Simon chose local-only over headless Claude, accepting a quality tradeoff on the interpretive steps in exchange for independence.

## Goals

- `python throughline.py extract|connect|draft <chapter>` run end to end with no Claude anywhere.
- Reasoning on a local Ollama model, embeddings on the already-installed `granite-embedding:30m`.
- The trust guardrails carry the quality burden. Schema validation with retries on every model output, verbatim-quote verification on every quote, deterministic post-checks on drafts. A weak model may write a shallow connection but can never fabricate evidence that survives.
- Swap the OCR adapter to Apple Vision (better than tesseract on real scans), keep tesseract as fallback, and close the known scanned-PDF gap by rasterizing and OCRing pages with no text layer.
- The Claude Code skill remains as the premium path. Both paths read and write the same store files, in the same formats, gated by the same verifier.

## Non-goals

- No critique-stage automation (folding scholar feedback into the rubric stays a judgment task for the skill).
- No fine-tuning, no API keys, no cloud calls.
- No packaging/installer for the scholar's machine yet. This spec makes the tool runnable without Claude Code; distribution is a follow-up.
- No numpy or other heavy math deps. Cosine similarity over a few hundred small vectors is fine in pure Python.

## Architecture

One new client module plus three stage modules, wired into the existing CLI.

- **`llm.py`** owns all Ollama traffic. Plain stdlib HTTP (urllib) against `http://localhost:11434` (env `OLLAMA_HOST` overrides). Capabilities. `list_models()`; `pick_model()` resolving env `THROUGHLINE_MODEL`, else the first present from a preference list (`qwen3:14b`, then `granite3.3:8b`); `generate(prompt, system, schema, validate, retries)` using Ollama structured outputs (the JSON schema passed as `format`), parsing the reply and re-prompting with the validation errors appended up to N retries; `embed(texts)` via `/api/embed` with `granite-embedding:30m`. The HTTP transport is injectable so tests run against a fake with canned replies, no server needed.
- **`stages/extract_stage.py`** batches each source's pages (about 6,000 chars per batch, whole pages), prompts for units in the exact unit schema, validates shape per unit, writes `store/<source>.units.json`, then runs the existing verifier. Units whose quotes fail verification get one repair round (re-prompt with the page text, asking for an exact span), then are dropped. Nothing unverified is ever kept.
- **`stages/connect_stage.py`** is two-stage, which is what makes a small model viable. Stage one embeds every unit (statement plus quote) and shortlists the top-K cross-source pairs by cosine similarity (pure function, unit-testable). Stage two prompts the reasoning model once per shortlisted pair with the thesis, the rubric, the gold example's connection section, and the two units plus a little same-source context, asking for one connection object in the schema. Evidence quotes must be copied verbatim from the supplied units, enforced deterministically (each evidence quote must be a whitespace-normalized substring of a supplied unit quote) with one retry, then rejection. Survivors are ranked by confidence, capped, assigned ids C1..Cn, written to `report.json`, rendered to `report.md` with `Decision: candidate` lines, and verified.
- **`stages/draft_stage.py`** parses the Decision lines from `report.md`, and for each keep prompts with the rubric's voice and tensions sections, the gold prose, and the connection object, producing `drafts/<id>.md` with the audit-notes block. Deterministic post-check. Every double-quoted span in the draft must be a whitespace-normalized substring of that connection's evidence quotes; violations get one retry, then the draft is written with a prominent warning block listing the unverified spans.
- **`render.py`** renders `report.md` from a report dict and parses Decision lines back out, shared so the CLI and the skill produce and consume the same format.

## OCR swap

- New helper `loaders/ocr_text.py` exposing `image_to_text(image) -> str`. Tries Apple Vision via the `ocrmac` package first, falls back to pytesseract, raises a clear error when neither is available.
- `loaders/ocr_loader.py` uses the helper (behavior otherwise unchanged).
- `loaders/pdf_loader.py` rasterizes any page whose text layer is empty (PyMuPDF pixmap at 200 dpi) and OCRs it through the same helper, so a scanned PDF ingests with real text and correct page locs instead of silently ingesting empty. This closes the gap flagged in the MVP's final review.
- New dependency `ocrmac` (brings pyobjc Vision bindings). Mac-only by nature; the fallback keeps other platforms working.

## Model management

Default reasoning model `qwen3:14b` (about 9 GB, comfortable on a 24 GB M4). If absent, fall back to `granite3.3:8b` which is already installed, so the pipeline runs with zero downloads. `THROUGHLINE_MODEL` overrides everything. Embeddings always `granite-embedding:30m` (62 MB, installed). If the Ollama server is unreachable, stages fail fast with a clear message naming the fix (`ollama serve`).

## CLI

`extract`, `connect`, `draft` join the existing subcommands, each taking the chapter name plus `--model` (override), and connect also takes `--top-k` (shortlist size, default 12) and `--max-connections` (default 6). Connect overwrites `report.json`/`report.md` for the chapter; that is documented, and the scholar-facing workflow is unchanged (edit Decision lines, then draft).

## Quality expectations, stated honestly

Extraction and evidence grounding are well within an 8B to 14B model's ability, and the verifier catches what is not. The interpretive quality of connections and drafts will be below what the Claude skill produced for the genai-linguistics chapter. The rubric and gold example in every prompt narrow the gap. The intended division of labor is autopilot for bulk and scale, skill for the connections that must impress.

## Testing

- All stage tests run against a fake transport with canned JSON replies, fast and green with no Ollama running.
- The shortlist math, Decision-line parsing, evidence substring checks, and draft quote checks are pure functions with direct tests.
- Repair and rejection paths are tested (a bad quote gets repaired or dropped, never kept).
- One live smoke test runs a tiny extract against the real server and skips cleanly when Ollama is down or no model is present, same pattern as the tesseract skip.
- Existing suite (39 tests) must stay green throughout.

## Risks

- `qwen3:14b` at 24 GB RAM alongside other work may be slow or memory-tight; the granite fallback and `--model` flag are the pressure valves.
- Local models sometimes emit near-miss quotes (curly versus straight quotes, dropped diacritics). The whitespace-normalized verifier treats those as unverified, which is the safe direction; the repair round exists precisely for this.
- `ocrmac` adds pyobjc; if its install fails on some future machine the tesseract fallback keeps OCR working.
