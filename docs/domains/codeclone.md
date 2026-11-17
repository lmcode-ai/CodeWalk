# Clone equivalence: distinguish two versions

Public data: [CodeWalk/clone-equivalence](https://huggingface.co/datasets/CodeWalk/clone-equivalence).
Its own card identifies the 100-per-level L1–L3 files as a legacy balanced sample and excludes
the paper's held-out 86/82/84/166 task sets and N=10 tasks.

## Public legacy artifact

L1 contains pairs of Java method snippets. In inspected L2/L3 sources, components are placed
in separate `Comp_i` classes; `Outer.outer` invokes them independently, stores outputs or
exception tags in an `Object[]`, and returns that array. This is aggregation of component
outputs. It does not pass an upstream return value into a downstream component.

`codewalk inspect codeclone` counts these text markers across the downloaded files. This is
an artifact audit, not proof of every Java behavior or a reconstruction of the missing generator.
The dataset card's general chain wording must not override the actual source bytes.

## Paper's data-flow construction recipe

1. Extract Java method pairs with shared signatures and source IDs from FEMPD. Re-verify
   each atomic label using the original two independent test-generation methods. Recover
   their seeds/suites before claiming to reproduce this admission step.
2. Build a directed graph where an output type can feed the next designated input. Record
   exact signatures and additional driver inputs, not just a display name for the method.
3. Sample an all-positive chain or a chain with exactly one negative atom. Construct the
   corresponding chain independently on each side, with proper namespace/reference updates.
4. Compile both sides and execute valid end-to-end tests. Confirm EQ through all admitted
   tests and NEQ through a real distinguishing witness. A downstream constant function can
   mask an earlier difference, so an injected NEQ label alone is not sufficient.
5. Balance accepted positive/negative tasks at the chosen level and record rejected groups,
   source/component split identities, witnesses, compiler version and test-generation seeds.

The new `codeclone.plan` implements only graph/label proposals and lists the remaining gates.
It does not silently turn the legacy aggregation files into a different benchmark.

## Evaluation

The local paper describes one call, no tools, an **8096-token** budget, and at most eight
request retries for transient errors. The model must emit `VERDICT: 1` or `VERDICT: 0`.
The new parser accepts one such complete line and rejects ambiguous/conflicting multiple
verdicts. Budget exhaustion without a parseable verdict or an invalid model answer counts as failure; unresolved API
errors remain separate and prevent a complete-score claim.

Pass@1 is the primary classification metric. Pass@8 is near saturation for binary labels
and should not be interpreted as the same difficulty measure as repair/proof task coverage.

## Version scope and missing functionality

Update: `generate codeclone` now renders and compiles Java aggregation tasks by default,
with optional unary data-flow chains, and executes atomic plus whole-composite label checks.
See [generator contracts](../generation-atom-contracts.md). This is a new implementation
consuming normalized methods and supplied suites; it does not recover historical tests.

See the [alignment plan](../codeclone-alignment.md) and
[version manifest](../../configs/codeclone-versions.json) for the exact target, current
evidence, and recovery versus rebuild paths.

The public legacy sample is retained and its differences from the paper are accepted.
The old `plan` command remains a chain recipe, while `generate` has a separately configured
aggregation renderer. Reconstructing identical public tasks still requires their original
atomic normalization and admission suites, not just the new generator.

## Source recovery update (2026-11-06)

The [source reconstruction report](../source-reconstruction.md) records the newer real-source recovery,
679 admitted tasks and its limitations. Earlier counts and availability statements in this
document describe the initial public release or earlier fixture verification, not this new bank.

## Active paper-sized profile

The [paper-sized reconstruction guide](../paper-sized-reconstruction.md) supersedes the earlier subset as
the active release target. It specifies all 1,706 paper slots, actual clone data-flow chains,
expanded complexity atoms, complete L1 Verus recovery and exact restoration of published
repair definitions. Fresh admission and imported historical definitions remain distinct.
