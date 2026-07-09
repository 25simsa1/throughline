from __future__ import annotations

_UNIT_KINDS = {"claim", "concept", "quote"}
_UNIT_REQUIRED = ("source_id", "kind", "statement", "quote", "loc")
_CONN_REQUIRED = (
    "id", "move", "sources_involved", "interpretation",
    "evidence", "advances_thesis", "tensions",
)


def validate_unit(u: dict) -> list[str]:
    errs = []
    for key in _UNIT_REQUIRED:
        if not u.get(key):
            errs.append(f"unit missing required field {key!r}")
    kind = u.get("kind")
    if kind and kind not in _UNIT_KINDS:
        errs.append(f"unit kind {kind!r} not in {sorted(_UNIT_KINDS)}")
    return errs


def validate_units(units: list[dict]) -> list[str]:
    errs = []
    for i, u in enumerate(units):
        errs.extend(f"[{i}] {e}" for e in validate_unit(u))
    return errs


def validate_connection(c: dict) -> list[str]:
    errs = []
    for key in _CONN_REQUIRED:
        if key not in c or c[key] in (None, "", []):
            errs.append(f"connection missing required field {key!r}")
    for j, ev in enumerate(c.get("evidence", []) or []):
        if not isinstance(ev, dict):
            errs.append(f"evidence[{j}] is not an object")
            continue
        for key in ("source_id", "quote", "loc"):
            if not ev.get(key):
                errs.append(f"evidence[{j}] missing {key!r}")
    return errs
