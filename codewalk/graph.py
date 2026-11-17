"""Deterministic candidate sampling. A graph-compatible group is NOT an admitted task."""
from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any

Atom = dict[str, Any]


def sample_groups(
    atoms: Sequence[Atom], compatible: Callable[[Atom, Atom], bool], *,
    level: int, count: int, seed: int, directed: bool,
    max_attempts: int = 10000, max_per_source: int | None = None,
    lookahead: bool = False,
) -> list[list[Atom]]:
    """Follow the tail for chains; use the whole frontier for undirected groups.

    Sampling is reproducible but not uniform over all possible subgraphs.
    Exhausting the budget raises instead of silently returning fewer tasks.
    """
    if level < 1 or count < 1 or max_attempts < 1:
        raise ValueError("level, count and max_attempts must be positive")
    if max_per_source is not None and max_per_source < 1:
        raise ValueError("max_per_source must be positive")
    if any(not isinstance(a.get("id"), str) or not a["id"] for a in atoms):
        raise ValueError("Each atom needs a nonempty string id")
    pool = sorted(atoms, key=lambda a: a["id"])
    if len({a["id"] for a in pool}) != len(pool):
        raise ValueError("Duplicate atom ids")
    if level > len(pool):
        raise ValueError("Insufficient distinct atoms")
    if max_per_source and any(not a.get("source_id") for a in pool):
        raise ValueError("source_id required for source reuse limits")
    edges = {
        a["id"]: {b["id"] for b in pool if a["id"] != b["id"] and compatible(a, b)}
        for a in pool
    }
    if not directed:
        for a in pool:
            for b in edges[a["id"]]:
                if a["id"] not in edges[b]:
                    raise ValueError("Undirected compatibility must be symmetric")
    rng = random.Random(seed)
    reachability={}
    visits=0
    def extends(node,used,remaining):
        nonlocal visits
        if not remaining:return True
        key=(node,frozenset(used),remaining)
        if key in reachability:return reachability[key]
        visits+=1
        if visits>100000:return False
        result=any(extends(other,used|{other},remaining-1) for other in sorted(edges[node]-used))
        reachability[key]=result
        return result
    starts=[a for a in pool if not (lookahead and directed) or extends(a['id'],{a['id']},level-1)]
    if not starts:raise ValueError('No path found within bounded lookahead')
    seen: set[tuple[str, ...]] = set()
    result: list[list[Atom]] = []
    for _ in range(max_attempts):
        group = [rng.choice(starts)]
        while len(group) < level:
            used = {a["id"] for a in group}
            frontier = edges[group[-1]["id"]] if directed else set().union(*(edges[a["id"]] for a in group))
            sources = Counter(a.get("source_id") for a in group)
            choices = [a for a in pool if a["id"] in frontier - used
                       and (max_per_source is None or sources[a["source_id"]] < max_per_source)]
            if lookahead and directed:
                choices=[a for a in choices if extends(a['id'],used|{a['id']},level-len(group)-1)]
            if not choices:
                break
            group.append(rng.choice(choices))
        if len(group) != level:
            continue
        ids = tuple(a["id"] for a in group)
        key = ids if directed else tuple(sorted(ids))
        if key not in seen:
            seen.add(key)
            result.append(group if directed else sorted(group, key=lambda a: a["id"]))
        if len(result) == count:
            return result
    raise ValueError(f"Only found {len(result)}/{count} groups in {max_attempts} attempts; nothing silently dropped")
