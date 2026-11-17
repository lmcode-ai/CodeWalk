from __future__ import annotations
import hashlib
import json


def candidate(domain, atoms, **details):
    identity = {"domain": domain, "atom_ids": [a["id"] for a in atoms], "details": details}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    return {
        "candidate_id": f"{domain}-L{len(atoms)}-{digest}",
        "domain": domain, "level": len(atoms), "atom_ids": identity["atom_ids"],
        "source_ids": [a.get("source_id") for a in atoms],
        "status": "candidate_only", "admitted": False,
        "implementation": "release-reimplementation-v1", **details,
    }


def chain_types(a, b):
    """Explicit, extractor-certified compatibility; no inferred language coercions."""
    return bool(a.get("output_type")) and a["output_type"] in b.get("accepted_input_types", [])
