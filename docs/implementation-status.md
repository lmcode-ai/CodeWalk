# Implementation status

## Executable composition v1

`generate` now implements the full normalized-atom lifecycle: validation, graph sampling,
source rendering, atomic/joint admission, rejection/resampling, private evidence and public
export. All four backends have passed actual tool-based synthetic integration tests.

- Repair: local Git archive, isolated patch context, shared test snapshot, per-atom pytest
  failures and joint-gold test success. Supports pytest repositories with prepared dependencies.
- Clone: isolated Java packages, aggregation by default, optional unary chains, javac/java
  execution, two supplied atomic suites and whole-composite distinguishing checks.
- Complexity: Python module chains, actual test execution, annotated size propagation and
  polynomial/log cost derivation. It does not prove source annotations or infer arbitrary costs.
- Verus: structured unary scalar atoms, shared executable segments, fixed stage predicates,
  driver, atomic/reference verification and unfinished-task verification failure.

See [contracts](generation-atom-contracts.md), [extension guide](adding-a-dataset.md), and
[generator verification](generator-verification.md). The older `plan` interface remains
candidate-only. Its input schema is not the executable generator's atomic schema.

## Source recovery update

The [source reconstruction report](source-reconstruction.md) records 679 admitted tasks:
all 461 referenced FEMPD pairs and their EvoSuite source were recovered, 87 upstream
Verus references verified, and real repair and CodeComplex atoms extracted. Source-mode
Verus supports the recovered vector, borrowing and helper patterns with checked executable
projections and fixed wrappers. Historical internal extraction and runtime choices remain
unavailable. The limitations below refer to complete historical reproduction.

## Historical scope still not supplied

- Complete historical samplers and atomic pools. The supplied Bugfixing and CodeClone
  source-mining and generation scripts are now included in the
  [original workflows](original-benchmarks.md).
- Arbitrary Rust AST, borrow and vector transformations. The supplied Verus archive
  now provides all 400 original references and the original composition generator.
- Historical CodeWalk clone admission suites and exact reproduction of the released bank;
  original EvoSuite source was recovered, but its full historical runner was not replayed.
- Public complexity artifacts and universal verification of complexity/size annotations.
- Every upstream repair image/test-runner integration or repository dependency installer.
- Model/provider clients, repair-agent/AutoVerus integration and a protected-spec model-answer grader.

The source adapter must provide real normalized atoms, licenses, tests, references and evidence.
The framework cannot reconstruct missing historical data from composite records alone.
The new supported generators work; a byte-for-byte reproduction of historical benchmarks
and a full model evaluation campaign remain different tasks.

Native execution is tested on fixtures and the admitted real-source bank. Docker mode requires a prepared pinned image
and was not locally exercised because a Docker daemon is unavailable. Do not claim tested
isolation/deployment for an arbitrary environment based on the native fixture tests.

## Active paper-sized profile

The [paper-sized reconstruction guide](paper-sized-reconstruction.md) supersedes the earlier subset as
the active release target. It specifies all 1,706 paper slots, actual clone data-flow chains,
expanded complexity atoms, complete L1 Verus recovery and exact restoration of published
repair definitions. Fresh admission and imported historical definitions remain distinct.
