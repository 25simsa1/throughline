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
4. Write all connections to `report.json` under the key `connections`, and render a readable `report.md` from the same data. Each connection's block in report.md ends with a line `Decision: candidate`. The scholar will edit report.md and change this to `keep` or `drop`. (report.json remains the machine record with evidence.)
5. Run `python throughline.py verify <chapter>`. Fix any UNVERIFIED evidence before finishing.

## select

The scholar edits report.md and changes each connection's Decision line from `candidate` to `keep` or `drop`, optionally adding a short note beneath it. This is a human step. Do not make the decision for them.

## draft

1. Read `report.md`. Collect connections whose Decision line is `keep`. For each, look up its evidence (verbatim quotes and locations) in `report.json` by matching the connection id. Draft only those connections.
2. For each kept connection, write `drafts/<id>.md`, prose in the register the rubric and gold examples set, weaving the verified quotes with citations that match the source metadata.
3. Mark each sentence's basis as evidence or interpretation in a trailing notes block, so the scholar can audit.
4. Do not introduce any quote that is not already verified in `report.json`.

## critique

1. Read the scholar's mark-ups (inline comments in `report.md`, `drafts/*.md`, or a `critique.md`).
2. Summarize the recurring preferences and objections.
3. Append them to `rubric.md` as new principles or anti-patterns, dated. Do not rewrite the scholar's existing rubric text, only add.
