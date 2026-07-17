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
