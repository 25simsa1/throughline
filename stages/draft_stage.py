from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import render
import verify

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {"draft_markdown": {"type": "string"}},
    "required": ["draft_markdown"],
}

# matches spans in straight (U+0022) or curly (U+201C/U+201D) double quotes,
# and curly single-quote pairs (U+2018...U+2019, distinct from apostrophes);
# written with escapes on purpose, do not "simplify" to literal quote characters
_QUOTE_RE = re.compile(
    '[“"]([^”"]{4,300})[”"]'
    '|‘([^’]{4,300})’'
)

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
- Always use double quotation marks for quoted material, never single quotation marks, so the machine check can verify every quote.
"""


def quoted_spans(text: str) -> list[str]:
    return [m.group(1) or m.group(2) for m in _QUOTE_RE.finditer(text)]


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
    known = {c["id"] for c in report.get("connections", [])}
    for cid, d in decisions.items():
        if d.get("decision") == "keep" and cid not in known:
            print(f"warning: {cid} is marked keep in report.md but has no entry in report.json",
                  file=sys.stderr)
    return drafted
