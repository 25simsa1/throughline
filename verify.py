from __future__ import annotations

import json
from pathlib import Path

import store
from models import Source


def normalize_ws(s: str) -> str:
    return " ".join(s.split())


def locate(quote: str, source: Source) -> str | None:
    needle = normalize_ws(quote)
    if not needle:
        return None
    for seg in source.segments:
        if needle in normalize_ws(seg.text):
            return seg.loc
    return None


def _sources_by_id(chapter_dir: Path) -> dict[str, Source]:
    return {s.source_id: s for s in store.load_segments(chapter_dir)}


def verify_units_file(chapter_dir: Path, source_id: str) -> dict:
    sources = _sources_by_id(chapter_dir)
    src = sources.get(source_id)
    units = store.load_units(chapter_dir, source_id)
    verified = 0
    for u in units:
        loc = locate(u.get("quote", ""), src) if src else None
        u["verified"] = loc is not None
        if loc and not u.get("loc"):
            u["loc"] = loc
        verified += 1 if u["verified"] else 0
    store.save_units(chapter_dir, source_id, units)
    return {"verified": verified, "unverified": len(units) - verified}


def verify_report_file(chapter_dir: Path) -> dict:
    sources = _sources_by_id(chapter_dir)
    path = chapter_dir / "report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    unverified = 0
    for conn in report.get("connections", []):
        for ev in conn.get("evidence", []):
            src = sources.get(ev.get("source_id"))
            ok = bool(src) and locate(ev.get("quote", ""), src) is not None
            ev["verified"] = ok
            unverified += 0 if ok else 1
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"unverified_evidence": unverified}
