"""Complexity chain recipe; type compatibility alone cannot determine its cost."""
from .common import candidate, chain_types

DIRECTED = True
compatible = chain_types


def plan(atoms):
    if any(not a.get("size_transfer") for a in atoms):
        raise ValueError("An explicit size-transfer derivation is required for every atom")
    return candidate("bigo", atoms,
        composition="namespace modules; chain typed calls; expose other arguments; preserve side effects",
        atomic_costs=[a["cost"] for a in atoms],
        size_transfers=[a["size_transfer"] for a in atoms],
        admission_required=["references and source annotations trace to the upstream atoms",
                            "a checked end-to-end derivation is representable in the target label vocabulary"],
        warning="Do not take max(atomic labels) or multiply labels without propagating intermediate sizes.")
