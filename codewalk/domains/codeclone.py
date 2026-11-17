"""Paper's data-flow chain recipe, NOT the public legacy Object[] aggregation."""
from .common import candidate

DIRECTED = True


def compatible(a, b):
    return bool(a.get("output_type")) and a["output_type"] == b.get("input_type")


def plan(atoms):
    labels = [a["label"] for a in atoms]
    if any(x not in {"equivalent", "not_equivalent"} for x in labels):
        raise ValueError("Unknown atomic label")
    if labels.count("not_equivalent") > 1:
        raise ValueError("This protocol allows at most one negative atom per chain")
    return candidate("codeclone", atoms,
        proposed_label="not_equivalent" if "not_equivalent" in labels else "equivalent",
        composition="namespace each component; render two real data-flow chains; construct valid end-to-end tests",
        admission_required=["both atomic re-verification methods confirm every pair",
                            "both composed programs compile",
                            "end-to-end executions confirm the proposed label"],
        warning="A negative atom can be masked downstream. Never admit NEQ solely from its atomic label.")
