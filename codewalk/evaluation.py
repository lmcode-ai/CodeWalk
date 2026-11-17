"""Strict label grading and coverage-aware metrics. Not an agent or proof verifier."""
from __future__ import annotations
from collections import Counter
import re

COMPLEXITY_LABELS = {"constant", "logn", "linear", "nlogn", "quadratic", "cubic", "np"}


def parse_label(domain, response):
    if not isinstance(response, str):
        raise ValueError("response must be a string")
    if domain == "codeclone":
        matches = re.findall(r"(?m)^\s*VERDICT:\s*([01])\s*$", response)
        return ({"1": "equivalent", "0": "not_equivalent"}[matches[0]]
                if len(matches) == 1 else None)
    if domain == "bigo":
        label = response.strip()
        return label if label in COMPLEXITY_LABELS else None
    raise ValueError("Executable repair and proof tasks need their domain verifier")


def grade_label(domain, response, target):
    allowed = {"equivalent", "not_equivalent"} if domain == "codeclone" else COMPLEXITY_LABELS
    if target not in allowed:
        raise ValueError("Invalid target label")
    parsed = parse_label(domain, response)
    return {"status": "success" if parsed == target else "failure", "parsed_label": parsed}


def summarize(tasks, attempts, n):
    if type(n) is not int or n < 1:
        raise ValueError("n must be a positive integer")
    if not tasks or any(not isinstance(t.get("task_id"), str) or not t["task_id"] or
                        type(t.get("level")) is not int or t["level"] < 1 for t in tasks):
        raise ValueError("Tasks need unique ids and positive integer levels")
    bank = {t["task_id"]: t for t in tasks}
    if len(bank) != len(tasks):
        raise ValueError("Duplicate task ids")
    seen = {}
    for row in attempts:
        i = row.get("sample_idx")
        if row.get("task_id") not in bank or type(i) is not int or not 0 <= i < n:
            raise ValueError("Unknown task or out-of-range sample index")
        key = row["task_id"], i
        if key in seen:
            raise ValueError("Duplicate attempt identity; resolve retries before scoring")
        if row.get("status") not in {"success", "failure", "infra_error"}:
            raise ValueError("Unrecognized outcome")
        seen[key] = row
    def group(ids):
        rr = [r for (task, _), r in seen.items() if task in ids]
        counts = Counter(r["status"] for r in rr)
        expected = len(ids) * n
        complete = len(rr) == expected and not counts["infra_error"]
        successes = counts["success"]
        solved = len({r["task_id"] for r in rr if r["status"] == "success"})
        return {"tasks": len(ids), "expected_attempts": expected, "recorded_attempts": len(rr),
                "missing_attempts": expected - len(rr), "infra_errors": counts["infra_error"],
                "successes": successes, "solved_tasks_so_far": solved, "complete": complete,
                "pass_at_1": successes / expected if complete else None,
                f"pass_at_{n}_coverage": solved / len(ids) if complete else None}
    return {"overall": group(set(bank)), "by_level": {
        str(level): group({t["task_id"] for t in tasks if t["level"] == level})
        for level in sorted({t["level"] for t in tasks})}}
