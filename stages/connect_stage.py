from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import render
import schemas
import store
import verify
from llm import LlmError


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
- In "interpretation" and "tensions", never refer to units by number. Name the sources and quote or paraphrase the text itself.
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
    if len(vectors) != len(units):
        raise LlmError(
            f"embedding backend returned {len(vectors)} vector(s) for {len(units)} unit(s)"
        )
    pairs = shortlist_pairs(units, vectors, k=top_k)
    thesis, rubric, gold = _load_context(chapter_dir)
    conns = []
    for i, j in pairs:
        siblings_i = [n for n, u in enumerate(units) if u["source_id"] == units[i]["source_id"] and n != i][:2]
        siblings_j = [n for n, u in enumerate(units) if u["source_id"] == units[j]["source_id"] and n != j][:2]
        idxs = [i, j] + siblings_i + siblings_j
        allowed = [units[n] for n in idxs]

        def validate(obj, allowed=allowed):
            # temp id satisfies the id-required check; real ids are assigned after ranking
            errs = schemas.validate_connection({**obj, "id": "tmp"})
            errs += _match_evidence(obj, allowed)
            return errs

        try:
            obj = client.generate(
                CONNECT_PROMPT.format(thesis=thesis, rubric=rubric, gold=gold,
                                      units=_units_block(units, idxs), i=i, j=j),
                schema=CONN_SCHEMA, validate=validate, model=model, retries=2,
            )
        except LlmError as e:
            print(f"note: skipped pair ({units[i]['source_id']} x {units[j]['source_id']}): {e}",
                  file=sys.stderr)
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
    r = verify.verify_report_file(chapter_dir)
    if r["unverified_evidence"]:
        raise LlmError(
            f"{r['unverified_evidence']} evidence item(s) failed verbatim verification "
            "after write; report.json/report.md left on disk for inspection but must not be trusted"
        )
    return len(conns)
