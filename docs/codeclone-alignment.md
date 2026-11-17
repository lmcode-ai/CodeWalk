# Aligning CodeClone with the paper

Status: optional alignment analysis, deferred. The current release retains the public legacy
dataset; its differences from the paper are accepted and do not by themselves block use.

Scope: CodeClone only. No changes to Bugfixing data, evaluation settings, or manuscript.
Checked on 2026-11-06 against the local manuscript snapshot and the current public HF revision.

## What can be aligned now

The current HF main revision is still `a24a0d0819bfacc28e36594abfb1acb3176638ba`.
It contains only the legacy L1/L2/L3 files, not a newer paper split or L10 bank.
The registry and downloader already pin this revision. Field names, label vocabulary,
answer-free input projection, and the documented single-call evaluation budgets can be
shared across versions. Sharing a protocol does not establish dataset identity.

The version manifest is [codeclone-versions.json](../configs/codeclone-versions.json).
It explicitly names the public legacy artifact and the unavailable paper target. Null
fields are missing evidence, not defaults that can be filled with arbitrary new samples.

## Structural incompatibility

Legacy L2/L3 wrappers call each component independently using separate external arguments,
then return an array of component results or exception tags. The paper describes actual
output-to-input chains. These constructions have different program behavior and difficulty.

For example, the first public L2 task combines `intervalEquals(byte[], int, byte[])`,
returning `boolean`, and `isAlphaNumeric(char)`, returning `boolean`. Its independent calls
are valid as an aggregation. The first return cannot directly supply the second function's
`char` parameter. A direct rewiring would not satisfy the paper's exact-type relation.
Choosing another order or adding arbitrary adapters does not recover its historical task.

All 100 L2 and 100 L3 records have aggregation markers on both sides. This marker check
does not prove every wrapper's semantics; the inspected example establishes why merely
changing a wrapper or description is insufficient.

## Split and provenance incompatibility

The legacy bank has 100/100/100 tasks. The paper target has 86/82/84/166 at N=1/2/3/10.
Selecting the first 86/82/84 legacy records would reproduce counts, not task identities or
program contents. The missing L10 bank cannot be recovered by duplicating shorter tasks.

The legacy levels contain 100, 188, and 262 distinct atomic pair IDs respectively, with
461 distinct IDs overall. Atomic ID overlap is 17 between L1/L2, 32 between L1/L3, and 46
between L2/L3. These overlaps are not themselves proof of invalid evaluation: levels may
reuse atoms by design. They do mean that level membership cannot be treated as evidence
of source-disjoint training/evaluation splits. Historical split manifests are required.

## Preferred path: recover the evaluated paper artifacts

1. Obtain the actual 86/82/84/166 task files and exact task-ID manifests used for evaluation.
2. Retain original source bytes, ordered component IDs, type bindings, labels and source
   provenance. Publish immutable hashes rather than relying on filenames or task counts.
3. Recover atomic type-driven and cross-substitution test evidence, compilation setup,
   composite test inputs and negative distinguishing witnesses. Passing a finite suite
   supports the benchmark's test-based EQ criterion; it is not universal equivalence proof.
4. Match recorded evaluation attempts to exact task IDs and input hashes, then recompute
   tables using the historical parsing, budget and retained-denominator policies.
5. Publish this bank as a separately named HF configuration or version. Retain the old
   aggregation sample with an accurate description; do not overwrite its identity silently.

Exact historical bytes plus matching run records may permit rescoring without new inference.
Matching counts or component IDs alone is insufficient to reuse published results.

## Fallback: independently rebuild a data-flow benchmark

If historical artifacts cannot be recovered, build a new, explicitly versioned dataset:

1. Recover the upstream atomic methods and test suites, establish source families and splits,
   and independently re-verify atomic labels with both declared test-generation methods.
2. Extract signatures and build a directed compatibility graph. Record the downstream input
   position, all additional external inputs, namespaces and any allowed adapters explicitly.
3. Render paired chains with a Java-aware transformer. Define observable behavior, including
   exceptions, arrays, mutation and shared-input aliasing. Use equivalent fresh inputs on
   each side; independent argument slots must not be silently changed into shared references.
4. Compile and execute each atomic pair and complete chain. Require positive agreement on
   admitted tests and an end-to-end witness for each negative task. A negative atom may be
   masked downstream, so discard chains without a real composite witness.
5. Save successful admission evidence, rejection reasons, source/test/toolchain revisions,
   sampler seed, final split IDs, input hashes and balanced per-level counts. Do not describe
   newly obtained yields as the historical paper's admission yields.
6. Run models again on the new programs using the declared evaluation profile. Existing
   accuracy numbers and RFT results do not transfer to changed programs or splits. Update
   the manuscript only from the newly validated results and their actual denominators.

The legacy snippets may help identify upstream atoms, but they do not include the full
historical verified pool, witnesses or transformation machinery. Re-extraction from wrappers
alone is not a validated substitute for those artifacts.

## Recommended release decision

For the current preparation release, retain the legacy sample under its explicit variant
name and mark the paper data-flow target unavailable. Prioritize recovering the evaluated
task bank before writing a replacement generator: it is the shortest route to aligning
public data with existing paper numbers. If recovery fails, a fresh data-flow release and
new evaluation are required. Changing the paper to describe aggregation would instead
require evidence that those exact aggregation tasks produced the reported results; none
is currently available.
