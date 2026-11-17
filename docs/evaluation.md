# Evaluation protocol and result format

The machine-readable source is [evaluation.json](../configs/evaluation.json). It transcribes
the local paper appendix, not the later RFT campaign. Unknown settings are `null`; fill them
in and save the completed run manifest before evaluating. In particular, do not infer n=8,
temperature, prompts or model names from old chat history. A shared setting means equal
budgets and prompts across models **within a domain**; repair and proof scaffolds inherently differ.

## Domain protocols

- Repair: one bash tool, fresh shell per command, 100 turns, $1.50, 1500 seconds.
  The model receives repository context and the failing-test union, with N hidden.
  Evaluate in a clean grader environment; all targeted tests must pass. PASS_TO_PASS
  regression testing is a separately named, stricter metric, not the reported target metric.
- Verus: AutoVerus default phases, at most 10 repair rounds, 16000 tokens per ordinary call,
  4096 for repair, 4800 seconds. Restore original predicates and driver and reject proof
  bypasses; preserve executable code/preconditions. See the [domain guide](domains/verus.md).
- Complexity: a single call without tools, 4096 tokens, 300 seconds; match the reference class.
- Clone: a single call without tools, **8096** tokens (literal manuscript value), at most eight
  transient request retries, one `VERDICT: 0`/`VERDICT: 1` line. The published legacy sample
  and the paper's evaluation split are distinct datasets.

The strict parsers supplied here are new implementations. They are not claimed to reproduce
the missing historical parser's treatment of every output. Record their package revision.

## Inputs and isolation

Use `export-inputs` to create an allowlisted payload. `task_id` is an external routing key:
never copy it or level/provenance metadata into the model prompt. For repair, build the
container using trusted metadata separately. Published gold patches must be excluded from
the agent filesystem, environment and repository history. For clone, labels stay judge-side.
Verus exports require downloaded source files and validate their manifest hashes.

This package has no remote inference client. A real runner must keep a manifest with dataset
revision, split and task IDs, model/provider, prompt hash, all generation limits, retry policy,
environment image digests, verifier versions and code revision. Score one manifest at a time.

## Attempts and metrics

Task JSONL rows contain `task_id` and integer `level`; classification judge files also have
`label`. Attempt rows contain `task_id`, zero-based `sample_idx`, and `status`:
`success`, `failure`, or `infra_error`. Use exactly n unique attempts per task. Resolve
transport retries into one attempt, retaining retry logs separately; retries are not samples.

A completed but malformed model response or task-timeout is a failure. For clone, the
manuscript specifically counts budget exhaustion **without a parseable verdict** as failure;
do not invent a rule for other finish reasons without recording it in the run manifest.
An unavailable image, test collection crash or unresolved API outage is an
infrastructure error. `grade-labels` accepts completed response strings only: a runner must
record budget/time-limit outcomes under its declared policy and infrastructure errors itself.
Never omit those rows to increase reported scores. Historical paper tables sometimes exclude
unresolved infrastructure failures (for example 161/166 retained clone tasks for Kimi at N=10).
This new scorer deliberately requires full coverage for a complete score; a reproduction of
those historical retained-set tables must declare that filtered denominator separately.

For T tasks and n attempts each, `pass_at_1 = successes/(T*n)` estimates average single-sample
success; `pass_at_n_coverage = solved_tasks/T` measures at least one success in those n attempts.
This does not extrapolate pass@k from a larger pool. Missing attempts or infrastructure errors
make affected aggregate scores `null`. Level aggregates may be complete while the overall run
is incomplete. Overall scores weight tasks equally; do not average unequal-sized level rates.

For binary classification, pass@8 can be high even for weak random predictions. Prefer pass@1
for model comparison and report n, task counts and the exact version alongside any pass@8.
