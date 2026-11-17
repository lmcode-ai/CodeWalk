# Release overview

This repository documents composition methods, evaluation settings, and extension interfaces
for four coding domains. Dataset contents remain on Hugging Face; the code pins immutable
revisions and provides download and inspection commands.

## Included components

- Construction methods, atom definitions, interaction relations, references, and admission
  requirements for multi-bug repair, Verus, complexity analysis, and clone equivalence.
- Reproducible connected-group and directed-chain sampling with candidate composition plans.
- Pinned downloads, structural checks, and answer-free exports for three public datasets.
- Classification response parsing and coverage-aware overall and per-level pass metrics.
- Paper-derived evaluation profiles and an executable example for adding a new domain.
- Offline tests, source attribution, integrity records, and release packaging tools.

## Reproduction status

The original composition scripts are unavailable. The implementations here are new.
`generate` renders executable tasks and runs admission under four explicit atomic contracts.
The older `plan` command produces candidate recipes only. Arbitrary historical Java/Rust
extraction and exact reference/test recovery remain outside the new generator's scope.

The verified public releases cover repair, Verus, and clone equivalence. A public complexity
dataset has not been identified. The public clone release contains legacy L1–L3 samples
with 100 tasks per level. Its higher-level wrappers aggregate independent component outputs
in an `Object[]`; they differ from the data-flow chains described in the manuscript.

See [implementation status](implementation-status.md) for missing backends and
[source audit](source-audit.md) for version differences. The repository is prepared as
release tooling with executable normalized-atom composition; exact historical regeneration
still requires the unavailable source pools and extraction/admission artifacts.
