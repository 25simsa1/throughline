from __future__ import annotations

from pathlib import Path

import schemas
import store
import verify
from llm import LlmError

BATCH_CHARS = 6000

UNIT_SCHEMA = {
    "type": "object",
    "properties": {
        "units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["claim", "concept", "quote"]},
                    "statement": {"type": "string"},
                    "quote": {"type": "string"},
                    "loc": {"type": "string"},
                    "theme_tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["source_id", "kind", "statement", "quote", "loc"],
            },
        }
    },
    "required": ["units"],
}

REPAIR_SCHEMA = {
    "type": "object",
    "properties": {"quote": {"type": "string"}},
    "required": ["quote"],
}

EXTRACT_PROMPT = """You are extracting research units from one scholarly source.

Source id: {source_id}
Pages below are labeled [p.N]. Extract up to {n} units from THESE pages only.

A unit is one of
- claim, the source argues something
- concept, the source defines or names something
- quote, a striking passage worth citing as-is

Hard rules
- "quote" must be an exact contiguous span copied character for character from ONE page below, 5 to 35 words. Never paraphrase inside "quote".
- "loc" must be the page label the quote came from, one of {locs}.
- "statement" is your plain-words summary.
- "source_id" is always "{source_id}".

Pages
{pages}
"""

REPAIR_PROMPT = """The quote below was supposed to be an exact span from the page text but it is not found there.

Statement it should support: {statement}
Page [{loc}] text:
{page}

Reply with an exact contiguous span (5 to 35 words) copied character for character from the page text above that best supports the statement.
"""


def _batches(segments, limit=BATCH_CHARS):
    batch, size = [], 0
    for seg in segments:
        if batch and size + len(seg.text) > limit:
            yield batch
            batch, size = [], 0
        batch.append(seg)
        size += len(seg.text)
    if batch:
        yield batch


def _validate_units(obj, source_id, allowed_locs):
    if not isinstance(obj.get("units"), list):
        return ["reply must be an object with a top-level 'units' array"]
    errors = []
    for i, u in enumerate(obj.get("units", [])):
        if isinstance(u, dict):
            u["source_id"] = source_id
            u.setdefault("theme_tags", [])
        errors += [f"[{i}] {e}" for e in schemas.validate_unit(u)] if isinstance(u, dict) else [f"[{i}] not an object"]
        if isinstance(u, dict) and u.get("loc") and u["loc"] not in allowed_locs:
            errors.append(f"[{i}] loc {u['loc']!r} is not one of the page labels given")
    return errors


def run_extract(chapter_dir: Path, client, *, model: str | None = None,
                max_units_per_source: int = 20) -> dict:
    model = model or client.pick_model()
    summary = {}
    for src in store.load_segments(chapter_dir):
        try:
            units = []
            for batch in _batches(src.segments):
                locs = [s.loc for s in batch]
                pages = "\n\n".join(f"[{s.loc}]\n{s.text}" for s in batch)
                per_batch = max(4, max_units_per_source // max(1, len(src.segments) // max(1, len(batch))))
                obj = client.generate(
                    EXTRACT_PROMPT.format(source_id=src.source_id, n=per_batch,
                                          locs=", ".join(locs), pages=pages),
                    schema=UNIT_SCHEMA,
                    validate=lambda o, sid=src.source_id, al=set(locs): _validate_units(o, sid, al),
                    model=model,
                )
                units.extend(obj["units"])
            units = units[:max_units_per_source]
            store.save_units(chapter_dir, src.source_id, units)
            verify.verify_units_file(chapter_dir, src.source_id)
            kept, dropped = _repair_or_drop(chapter_dir, src, client, model)
            summary[src.source_id] = {"kept": kept, "dropped": dropped}
        except LlmError as e:
            summary[src.source_id] = {"kept": 0, "dropped": 0, "error": str(e)}
    return summary


def _repair_or_drop(chapter_dir: Path, src, client, model) -> tuple[int, int]:
    units = store.load_units(chapter_dir, src.source_id)
    pages = {s.loc: s.text for s in src.segments}
    for u in units:
        if u.get("verified"):
            continue
        page = pages.get(u.get("loc"), "")
        if page:
            try:
                fix = client.generate(
                    REPAIR_PROMPT.format(statement=u.get("statement", ""),
                                         loc=u.get("loc"), page=page),
                    schema=REPAIR_SCHEMA, model=model, retries=0,
                )
                u["quote"] = fix.get("quote", u["quote"])
            except LlmError:
                pass
    store.save_units(chapter_dir, src.source_id, units)
    verify.verify_units_file(chapter_dir, src.source_id)
    units = store.load_units(chapter_dir, src.source_id)
    kept = [u for u in units if u.get("verified")]
    dropped = len(units) - len(kept)
    store.save_units(chapter_dir, src.source_id, kept)
    return len(kept), dropped
