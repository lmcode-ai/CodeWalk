# Verus proof completion

Public data: [CodeWalk/verus-proof-completion](https://huggingface.co/datasets/CodeWalk/verus-proof-completion).
This contains 400 unfinished tasks, source provenance and hashes. It does **not** include
reference proofs, original verified atomic functions, or the composition scripts.

## Construction recipe

1. Extract verified functions with named return values and postconditions from the source pool.
   Retain auxiliary definitions and the upstream license. Source program and function IDs
   identify atoms; helper functions do not increase the composition level.
2. Build directed compatibility edges from output type to a particular downstream input.
   Record conversions explicitly: direct passing, borrowing, or `Vec<T>.as_slice()`.
   Other downstream arguments must satisfy the supported scalar-input rules.
3. Namespace declarations and references with a Rust-aware transformation, not global text
   replacement. Copy each postcondition into a fixed `step_i` predicate, translating views
   consistently. Preserve the semantics of preconditions and supporting definitions.
4. Render a `chain_driver` that uses actual intermediate outputs. Its contract represents
   the conjunction of stage predicates; its proof establishes the predicates on the actual
   intermediates. Upstream contracts must justify downstream input-dependent preconditions.
5. Restore the reference annotations and require Verus to accept the whole program.
6. Strip only editable component postconditions/proof annotations, preserving executable code,
   existing preconditions, fixed predicates and the driver. The unfinished task must remain
   well formed but fail proof verification. A syntax error is not an admission success.

The domain-specific paper check is whole-program verification failure after stripping;
do not claim every component was independently proven unfinished if that was not measured.

## Evaluation

The public archive pins Verus `0.2026.07.18.3a4d30b` and Rust
`1.96.0-x86_64-unknown-linux-gnu`. The paper describes AutoVerus generation/refinement/repair,
10 repair rounds, 16000 tokens per non-repair call, 4096 per repair call and 4800 seconds/task.
The original AutoVerus configuration/commit is not recovered here.

Raw verifier acceptance is insufficient. The trusted grader must restore/check the task's
original fixed predicates and driver, preserve executable behavior/preconditions, and reject
proof-bypass constructs such as `assume`, `admit`, `external_body` and
`exec_allows_no_decreases`. Missing protected blocks are failures. A regex-only keyword check
is not a sound implementation of specification preservation.

## Included implementation and remaining work

Update: `generate verus` now renders structured scalar atoms, stage predicates and an actual
typed driver, invokes Verus on atomic and joint references, and requires verification failure
for the unfinished task. See [contracts](../generation-atom-contracts.md). It shares executable
segments between reference and task rather than rewriting arbitrary Rust source.

The module plans certified typed chains. The downloader verifies task SHA-256 when it fetches
Rust sources, and answer-free export rechecks those hashes. AST extraction, renaming, stripping,
historical reference reconstruction and the model-answer gold-preserving grader are **not implemented**; these require
the missing source artifacts and toolchain validation. Do not label `verus candidate.rs` alone
as the benchmark grader.

## Source recovery update (2026-11-06)

The [source reconstruction report](../source-reconstruction.md) records the newer real-source recovery,
679 admitted tasks and its limitations. Earlier counts and availability statements in this
document describe the initial public release or earlier fixture verification, not this new bank.

## Active paper-sized profile

The [paper-sized reconstruction guide](../paper-sized-reconstruction.md) supersedes the earlier subset as
the active release target. It specifies all 1,706 paper slots, actual clone data-flow chains,
expanded complexity atoms, complete L1 Verus recovery and exact restoration of published
repair definitions. Fresh admission and imported historical definitions remain distinct.
