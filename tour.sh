#!/usr/bin/env bash
# guided code tour, run from the repo root:  ./tour.sh
# narrates the design stop by stop and shows the real code as it goes.
# set TOUR_AUTO=1 to run without pauses (useful for a quick skim).
set -u
cd "$(dirname "$0")"

BOLD=$(tput bold 2>/dev/null || true)
DIM=$(tput dim 2>/dev/null || true)
CYAN=$(tput setaf 6 2>/dev/null || true)
YELLOW=$(tput setaf 3 2>/dev/null || true)
RESET=$(tput sgr0 2>/dev/null || true)

banner() {
  echo
  echo "${BOLD}${CYAN}============================================================${RESET}"
  echo "${BOLD}${CYAN}  $1${RESET}"
  echo "${BOLD}${CYAN}============================================================${RESET}"
}

say() { echo "${YELLOW}$1${RESET}"; }

pause() {
  if [ "${TOUR_AUTO:-0}" = "1" ]; then return; fi
  echo
  read -r -p "${DIM}[enter] for the next stop...${RESET}" _
}

# print a top-level def/class block from a python file, by name
show_def() {
  local file=$1 name=$2
  echo "${DIM}--- $file :: $name ---${RESET}"
  awk -v pat="$name" '
    $0 ~ "^(def|class) " pat { printing=1 }
    printing && NR>1 && /^(def|class) / && $0 !~ "^(def|class) " pat { exit }
    printing { print }
  ' "$file" | head -40
}

show_head() {
  local file=$1 n=${2:-25}
  echo "${DIM}--- $file (first $n lines) ---${RESET}"
  head -n "$n" "$file"
}

banner "THROUGHLINE CODE TOUR"
say "Eleven stops, maybe 20 minutes. The long-form version of this tour"
say "lives in docs/code-tour.md if you want prose instead of a terminal."
echo
say "The 30-second map:"
cat <<'MAP'

  sources/ (pdf, epub, txt, images)
     -> loaders/                 everything becomes located text
     -> store/segments.json      one segment per page, each with a loc
     -> extract                  a model pulls claims/concepts/quotes
     -> verify                   every quote checked verbatim vs the source
     -> store/<src>.units.json   only verified units survive
     -> connect                  embeddings shortlist, model argues pairs
     -> report.md / report.json  human surface / machine record
     -> (you mark Decision: keep or drop in report.md)
     -> draft                    prose per keep, quotes machine-checked
     -> drafts/<id>.md

  Rule 1: Python does everything deterministic, models only reason.
  Rule 2: fail closed. Unverifiable quotes never survive as trusted.
MAP
pause

banner "STOP 1  models.py, the atoms"
say "Two dataclasses everything else is built from. A Segment is text plus"
say "a loc string like p.4 or para.2. A Source is metadata plus segments."
show_head models.py 30
pause

banner "STOP 2  loaders/, everything becomes located text"
say "base.py is the whole contract. A loader has extensions and load()."
show_head loaders/base.py 17
echo
say "registry.py picks a loader by extension. Adding a format = one file."
show_def loaders/registry.py loader_for
echo
say "pdf_loader is the interesting one, a page with no text layer gets"
say "rasterized and OCRed (Apple Vision first, tesseract fallback)."
show_def loaders/pdf_loader.py "PdfLoader"
pause

banner "STOP 3  store.py + ingest.py, the disk is the truth"
say "After ingest, no stage ever reopens a PDF. Everything reads and"
say "writes JSON under chapters/<name>/store/, so every stage can rerun."
show_def ingest.py ingest_chapter
pause

banner "STOP 4  schemas.py, shape law"
say "Validators return a list of error strings, empty means valid. Note"
say "that tensions is REQUIRED on every connection, a connection that"
say "names no weakness is not accepted. Content rule enforced as shape."
show_head schemas.py 12
pause

banner "STOP 5  verify.py, the trust guardrail"
say "The most important 70 lines in the repo. locate() finds a quote's"
say "real page or returns None. A real quote with a wrong page gets its"
say "loc corrected and flagged loc_corrected, a permanent audit trail."
show_def verify.py locate
echo
show_def verify.py verify_units_file
pause

banner "STOP 6  llm.py, talking to the local model"
say "Stdlib-only Ollama client. generate() constrains output with a JSON"
say "schema, validates the reply, and retries with the errors appended."
say "The think=false line matters, thinking models burned 10+ minutes"
say "before constrained output started. One line, timeout to 7 seconds."
show_def llm.py "OllamaClient" | head -12
grep -n "think" llm.py | head -4
pause

banner "STOP 7  stages/extract_stage.py, reading so you do not have to"
say "Batches pages, prompts for units, verifies. Unverifiable quotes get"
say "ONE repair round then are dropped. The final save writes kept units"
say "only, there is no path where an unverified unit reaches disk."
show_def stages/extract_stage.py _repair_or_drop
pause

banner "STOP 8  stages/connect_stage.py, the two-stage trick"
say "Small models cannot hold 20 sources in their head, so stage one is"
say "arithmetic (embed units, cosine-shortlist cross-source pairs) and"
say "stage two prompts once per pair with the rubric and gold example."
show_def stages/connect_stage.py shortlist_pairs
echo
say "The trust move, evidence must be COPIED from the supplied units,"
say "and the matched unit overwrites whatever loc the model claimed."
show_def stages/connect_stage.py _match_evidence
pause

banner "STOP 9  stages/draft_stage.py, prose with a leash"
say "Drafts keeps only. Every span in double quotes or curly single"
say "quotes must be a substring of that connection's evidence, or the"
say "draft ships with a loud warning block naming the invented spans."
show_def stages/draft_stage.py check_quotes
pause

banner "STOP 10  render.py + throughline.py, the seams"
say "render.py makes report.md and parses your Decision edits back out,"
say "one module so the CLI and the Claude skill speak the same format."
say "throughline.py is the argparse CLI, clear errors instead of"
say "tracebacks for every state a user actually hits."
show_def render.py parse_decisions
pause

banner "STOP 11  tests/, what green proves"
say "FakeTransport queues canned model replies, so 78 of 80 tests prove"
say "plumbing, retries, and guardrails with no model running at all."
say "Read these as documentation:"
say "  test_verify.py         a paraphrase is caught, wrong page corrected"
say "  test_connect_stage.py  fabricated evidence yields zero connections"
say "  test_draft_stage.py    invented quoted spans get flagged"
say "  test_autopilot_e2e.py  the whole pipeline composes through files"
pause

banner "HANDS-ON  watch the guardrail catch a lie"
if [ "${TOUR_AUTO:-0}" = "1" ]; then
  demo=n
else
  read -r -p "Run the live demo? Creates a throwaway chapters/tour-demo, needs no model. [y/N] " demo
fi
if [ "${demo:-n}" = "y" ] || [ "${demo:-n}" = "Y" ]; then
  PY=.venv/bin/python
  [ -x "$PY" ] || PY=python3
  $PY throughline.py new tour-demo
  printf 'Memory is reconstructive, not a recording.\n' > chapters/tour-demo/sources/a.md
  $PY throughline.py ingest tour-demo
  say "Now we hand-write two units, one honest, one FABRICATED..."
  $PY - <<'PYEOF'
import store
from pathlib import Path
ch = Path("chapters/tour-demo")
store.save_units(ch, "a", [
    {"source_id": "a", "kind": "claim", "statement": "memory is rebuilt",
     "quote": "Memory is reconstructive", "loc": "para.1"},
    {"source_id": "a", "kind": "quote", "statement": "invented",
     "quote": "Memory is a perfect recording device", "loc": "para.1"},
])
print("wrote 2 units, one of them a lie")
PYEOF
  say "...and run verify:"
  echo
  $PY throughline.py verify tour-demo
  echo
  say "1 verified, 1 UNVERIFIED. That flag is the whole philosophy in one line."
  if [ "${TOUR_AUTO:-0}" != "1" ]; then
    read -r -p "Delete the throwaway chapter? [Y/n] " del
    if [ "${del:-y}" != "n" ] && [ "${del:-y}" != "N" ]; then
      rm -rf chapters/tour-demo && say "cleaned up."
    fi
  fi
else
  say "Skipped. The commands live at the end of docs/code-tour.md whenever"
  say "you want them, including breaking a quote on purpose to see the flag."
fi

banner "END OF TOUR"
say "Deeper prose version: docs/code-tour.md"
say "Design history: docs/superpowers/specs/ and docs/superpowers/plans/"
