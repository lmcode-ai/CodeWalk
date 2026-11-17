# Evaluating the replacement benchmark

The active policy uses newly composed Clone (418) and BigO (320) tasks in place of
missing historical banks, alongside published Repair (568) and Verus (400) inputs.
All task IDs are versioned. This is a new benchmark, not the historical paper dataset.
Existing paper scores remain historical; fresh model evaluation is required for v2.
The three-way historical alignment gate is intentionally not bypassed.

## Common workflow

The local package has `model_inputs/`, private `judge/`, and `preparation/` directories.
Only model inputs and prepared repair source belong in the model workspace. Never expose
gold patches, labels or reference proofs to a model. Judge references are provided for
validation controls, not inference. Treat model submissions as untrusted; use isolated
containers with pinned image digests for source execution. Native mode is for trusted
local controls only. This package supplies grading, not a hosted inference service.

Write submissions as JSONL with `task_id`, zero-based `sample_idx`, and a domain field:

- Clone: `response` containing exactly one `VERDICT: 0` or `VERDICT: 1` line.
- BigO: `response` containing one exact class: `constant`, `logn`, `linear`, `nlogn`,
  `quadratic`, `cubic`, or `np`.
- Verus: `source` containing a complete flat `task.rs`. Keep original executable code,
  signatures and preconditions. Add proof/spec helpers as needed. Original fixed spec
  functions, step predicates and driver are restored before verification. Additional
  macros, attributes, external functions and proof bypasses are rejected.
- Repair: `patch` containing a textual Git unified diff, or an empty string for an
  unchanged baseline. The conservative grader accepts edits only to original gold-source
  paths; test/configuration edits are forbidden. This narrower edit policy differs from
  an unrestricted repair agent and must be reported with results.

Run from the code repository, replacing paths with your local files:

```bash
python -m codewalk evaluate codeclone --root outputs/codewalk-benchmark-v2 --submissions responses.jsonl --output attempts.jsonl
python -m codewalk score --tasks outputs/codewalk-benchmark-v2/judge/codeclone.jsonl --attempts attempts.jsonl --n 8 --output score.json
```

Use `bigo`, `verus`, or `bugfixing` for the other domains. Executable domains also take
`--config runtime.json`. A missing runtime, setup error, skipped test or collection failure
produces `infra_error`, not an incorrect model answer. Missing/error attempts prevent a
complete aggregate score. Duplicate and unknown attempt identities are rejected.

## Verus runtime

Provide `verus` (executable path), `timeout_seconds`, and optional `tool_env` with toolchain
home paths. The recovered original bank was checked with Verus
`0.2026.07.18.3a4d30b`, Rust 1.96.0, on Windows. Linux replay remains separate work.
The package's 400 references have verified; this does not imply a model has solved them.

## Repair runtime

Prepare each task with `scripts/prepare_published_repair.py` using the separate recipe.
The preparation step fetches/checks out the original base and applies test patches only.
It does not install the original dependencies. Provision and record each task's required
environment before scoring. Provide a runtime mapping like:

```json
{
  "execution": "docker",
  "image": "your-prepared-runtime@sha256:<64 hexadecimal characters>",
  "timeout_seconds": 1500,
  "prepared_repositories": {"<versioned-task-id>": "/absolute/prepared/source"},
  "task_overrides": {}
}
```

Per-task `task_overrides` may select different pinned images or Python interpreters.
Do not use the example image literally. Source must be a fresh history-free prepared
tree, without gold patches. Grading copies it before applying the model patch and runs
the union of target pytest node IDs. All targets must run and pass; no regression-test
coverage is claimed. All 568 historical runtime environments have not yet been replayed.

## Validation limits

Local controls on 2026-11-06 passed: all 418 Clone and 320 BigO tasks were graded with
correct, incorrect and malformed responses; all 400 recovered Verus reference proofs
passed this evaluator, while unchanged tasks sampled at all four levels failed as
expected. One real two-bug repair task failed all 10 targets before repair and passed
all 10 with its complete gold repair. The actual CLI was also exercised for all four
domains. Missing repair environments were correctly recorded as infrastructure errors.
These checks are grader controls, not model evaluation results.

Correct/incorrect classification responses are synthetic grader controls, not model
results. Real proof and repair reference checks validate executable graders. A small repair
smoke test cannot establish readiness for all 568 repositories/tasks. New Clone/BigO
composition differs from the paper as documented in the historical three-way audit;
do not claim exact paper-method reproduction or assign old scores to these new questions.
