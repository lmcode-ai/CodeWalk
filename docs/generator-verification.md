# Executable generator verification

This report covers composition v1, implemented after the earlier candidate-only workflow
audit. The public HF dataset versions are unchanged. All code and release documentation
are English-only.

## What is now executable

The four backends use one normalized atom envelope and the same pipeline:

1. Validate atomic records and provenance.
2. Sample compatible connected groups or directed chains.
3. Render real task/reference files.
4. Execute atomic and joint admission through the domain tools.
5. Reject invalid groups or stop on infrastructure failure.
6. Atomically publish admitted tasks, private evidence and reproducibility metadata.

`generate` implements this lifecycle; the old `plan` CLI still produces candidate recipes.
No model calls are required for generation/admission.

## Actual tool checks

The native integration environment used Python 3.12.14, pytest 9.2.0, Temurin JDK 21.0.13+9,
Verus 0.2026.11.02.8bf68ee and its Rust 1.99.1 Windows MSVC toolchain. Tools were installed
under ignored local output directories, not vendored into the release. The historical HF
Verus package pins a different toolchain; this test does not claim compatibility with every
historical program or an identical generator version.

- Complexity: executed emitted Python modules/drivers, checked atomic expected outputs,
  intermediate-size annotations on fixtures and derived end-to-end cost labels.
- Repair: archived a real local Git repository; applied test patches; observed each bug's
  requested pytest test fail; applied joint gold patches; observed every target test pass.
- Clone: compiled generated Java packages/wrappers and executed both atomic suites plus
  complete aggregation tasks. A typed chain masking a genuine negative atom was rejected.
- Verus: verified atomic and joint reference programs; required verification errors on the
  generated unfinished task. A trivial predicate producing an already-verified task was rejected.

The four-domain N=1/2/3/10 matrix has 16 real generation/admission cases; see
[machine-readable results](sources/generator-verification.json).

All 27 local unit/integration tests passed without skips. The suite also covers wrong reference outputs, incorrect joint
repairs, unsupported cost growth, missing compilers, label quotas, partial counts, special
patch files, public/private separation, atomic publication failures, and a complete new
affine-domain extension. Integration tests for Java/Verus skip when those tools/configs are
absent; the local verified run supplied both configs and did not skip those tests.

## Important boundaries

These are trusted synthetic source atoms designed to exercise real tools, not mock verifier
results and not historical benchmark regeneration. Actual upstream extraction, normalization
and complete atomic evidence remain dataset-specific. Passing these fixtures does not prove
all published labels or the ability to normalize arbitrary source programs.

The implemented v1 contracts are pytest repair, normalized Java member-source aggregation
and unary chains, annotated Python unary cost chains, and structured scalar Verus atoms.
Unsupported syntax/types/size growth are rejected explicitly. Cost annotations remain trusted
source evidence; finite tests do not prove arbitrary asymptotic complexity. Java EQ is relative
to the supplied suites. Docker command construction is implemented, but no Docker daemon was
available for a local image/isolation integration test. Native mode is for trusted inputs.

No model inference/agent evaluation was launched. A full evaluation campaign still requires
its runner, prompt, provider settings and domain candidate grader.

The CI workflow now includes JDK/pytest setup and a separate pinned Linux Verus job.
It has not run on GitHub because this repository has not been pushed.

## Rerun

From a source checkout, with the corresponding tools installed:

```bash
python -m pip install -e '.[repair]'
python -m unittest discover -s tests -v
python scripts/verify_generators.py --output outputs/generator-matrix
```

For tools outside PATH, pass `--java-config` and `--verus-config` to the matrix script.
Set `CODEWALK_JAVA_CONFIG` and `CODEWALK_VERUS_CONFIG` to those JSON paths to enable the
same tools in unit/integration tests. Config formats are in the
[extension guide](adding-a-dataset.md). Always choose a new output directory.

## Source recovery update (2026-11-06)

The [source reconstruction report](source-reconstruction.md) records the newer real-source recovery,
679 admitted tasks and its limitations. Earlier counts and availability statements in this
document describe the initial public release or earlier fixture verification, not this new bank.
