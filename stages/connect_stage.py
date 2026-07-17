from __future__ import annotations

import math
from pathlib import Path


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
