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
Every quote is still machine-verified against the sources. Connections from a local model are serviceable but shallower than the Claude skill's, so use the skill for the connections that must impress.

## Known limitations

The quote verifier matches within a single segment (a page or section). A quote that spans two segments, for example across a page break, will be flagged unverified. Trim such a quote to a single page or section to verify it.

The draft quote check only machine-verifies double-quoted spans of 4 or more characters, so single-quoted or very short spans are not checked and still need a human eye.
