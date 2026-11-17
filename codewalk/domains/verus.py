"""Typed proof-completion chain recipe, requiring a real Rust/Verus renderer."""
from .common import candidate, chain_types

DIRECTED = True
compatible = chain_types


def plan(atoms):
    return candidate("verus", atoms,
        composition="namespace functions; chain calls with certified adapters; lift postconditions to fixed step predicates; synthesize driver; strip only editable proof annotations",
        admission_required=["joint reference verifies with the pinned Verus toolchain",
                            "unfinished whole program parses but fails proof verification"],
        protected=["executable code", "existing preconditions", "step predicates", "chain_driver"],
        unsupported_without_backend=["Rust AST rewriting", "specification restoration", "proof-bypass detection", "Verus execution"])
