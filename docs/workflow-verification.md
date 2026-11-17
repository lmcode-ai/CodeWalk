# Workflow verification

Historical snapshot: this report predates executable composition v1. The newer
[generator verification](generator-verification.md) supersedes its statements about
missing composition renderers/admission. Its data loading and classification checks remain valid.

Verified on 2026-11-06. Existing dataset versions are retained; matching the paper's
CodeClone split and data-flow construction is not required for the current scope.

## Conclusion

The current repository does **not** provide end-to-end evaluation or full composition
for all four domains. It provides working data/CLI utilities, classification grading,
metrics and candidate planning. Missing implementations, not paper-version differences,
prevent declaring the complete pipelines operational.

## Checks executed

- All pinned download receipts were checked against the current downloaded file bytes.
- Repair: 568 records inspected and 568 answer-free inputs exported.
- Clone: 300 records inspected and 300 answer-free inputs exported. The grading and scoring
  CLI processed all 300 tasks under three controls: reference-label echoes passed, opposite
  labels failed, and malformed responses failed. These controls do not measure a model.
- Verus: all 400 task files from the existing local ZIP matched the pinned public manifest.
  All 400 inputs were exported through the CLI with source hash checks.
- Complexity: all seven label controls graded correctly. No real dataset was available.
- All four domain planning CLIs ran at N=1/2/3/10 on synthetic normalized atoms: 16 planning
  cases. Every result remained `candidate_only` and `admitted: false`, as required.
- Nine failure controls passed: cross-repository repair groups, incompatible typed chains,
  missing size-transfer metadata, multiple negative clone atoms, unavailable complexity
  downloads, duplicate attempts, unknown task IDs, missing attempts and infrastructure errors.
- The 16 existing offline unit tests passed.

The full machine-readable result is [workflow-verification.json](sources/workflow-verification.json).
No model inference was performed. Fixture response controls and synthetic plans are not
benchmark results, generated benchmark programs, or admission evidence.

## Evaluation readiness

- **Clone:** loading, model-input projection, response grading and metrics are verified.
  A model inference runner, canonical prompt/run manifest and request-limit handling are
  still needed for a complete evaluation campaign. Label matching does not require Java
  execution, but re-validating the released labels does require the missing execution tests.
- **Repair:** record loading and projection are verified. The package lacks the environment
  preparation, isolated agent execution, candidate-patch replay and target-test grader.
- **Verus:** source loading, integrity and projection are verified. The package lacks the
  specification-preserving candidate grader and AutoVerus integration. Reference proofs are
  needed for generation/admission validation; grading supplied answers also requires the
  protected-specification checks and a working Verus toolchain.
- **Complexity:** the label grader is verified only against synthetic controls. There is no
  real task bank, loader or inference runner for this domain in the current package.

The executables `java`, `javac`, `verus` and `docker` were not found on the local PATH.
Installing them alone would not supply the missing runners or graders. Other local RFT
utilities are not integrated into this package and have not been substituted for these
benchmark-specific backends.

## Composition readiness

Candidate sampling and recipe construction work. None of the four domain modules emits
an executable composed task or runs domain admission. Published composed records are not
normalized atomic inputs, so downloading a dataset does not make `plan` an end-to-end
generator. All domains still need extraction, rendering and actual admission backends.
In particular, the current clone planner describes typed chains, while the retained public
dataset uses aggregation; the original aggregation generator has not been recovered.

## Reproduction commands

From the repository root, after downloading the three public metadata/data packages:

```bash
python -m unittest discover -s tests -v
python scripts/verify_workflows.py
```

To also verify/export every Verus source from an existing numbered ZIP:

```bash
python scripts/verify_workflows.py --verus-archive /path/to/numbered-verus-tasks.zip
```

Reports, synthetic fixture controls and projected model inputs are written under ignored
`outputs/workflow-verification/`. The script launches no model, container or paid service.
