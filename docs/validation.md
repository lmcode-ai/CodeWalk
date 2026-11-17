# Local validation

The executable generator was subsequently added and validated with real domain tools.
See [generator verification](generator-verification.md) for the current composition checks.
The original artifact/utility validation below is retained as a historical record.

Validated on 2026-11-05 with Python 3.12.14 on Windows:

- 16 offline tests passed: graph direction/connectivity, reproducibility, deduplication,
  source reuse, repair candidate planning, exact attempt identities, missing/error coverage,
  label parsing, model-payload exclusion, path/hash integrity, and extension admission.
- `pip install --no-deps -e .` succeeded with isolated build dependencies; installed
  `codewalk --help` worked. Runtime tools use the standard library.
- README repair planning, synthetic extension, classification grading and scoring ran.
  The synthetic example has pass@1=0.5 and pass@2 coverage=1.0; these are not benchmark scores.
- Pinned HF metadata/data downloads and schema inspections passed for all three public datasets.
- All 400 Rust inputs in the existing numbered ZIP match the public manifest hashes.
- First-party Markdown links and Python/JSON syntax passed release checks.

The included CI matrix targets Python 3.11–3.13 on Linux but has not run remotely.
No Java/Verus compilation, repair containers, inference calls, training or semantic
re-verification of benchmark labels/proofs was performed. Source inspections and hashing
do not establish end-to-end reproducibility. See [implementation status](implementation-status.md).

Rerun `python -m unittest discover -s tests -v` and `python scripts/check_release.py` from
the repository root to verify the portable offline portion.

## Source recovery update (2026-11-06)

The [source reconstruction report](source-reconstruction.md) records the newer real-source recovery,
679 admitted tasks and its limitations. Earlier counts and availability statements in this
document describe the initial public release or earlier fixture verification, not this new bank.
