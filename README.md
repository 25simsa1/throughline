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

## Known limitations

The quote verifier matches within a single segment (a page or section). A quote that spans two segments, for example across a page break, will be flagged unverified. Trim such a quote to a single page or section to verify it.
