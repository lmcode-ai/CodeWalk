# Multi-bug repair

Public data: [CodeWalk/multi-bug-repair](https://huggingface.co/datasets/CodeWalk/multi-bug-repair).
The fixed revision is in `codewalk/datasets.json`. It combines SWE-rebench v1 and V2;
the 268-task v1-only RFT campaign is a different population.

## Construction recipe

An atom contains repository, buggy base commit, fixing date, gold source patch, test patch,
and nonempty FAIL_TO_PASS test IDs. Extract changed source-file paths from diff headers
using a real patch parser; do not use substring overlap between repository names.

1. Group atoms by repository and create an undirected edge when gold patches share a file.
2. Sample a connected N-atom group. Connectivity does not require one file shared by all N bugs.
3. Propose the base commit of the earliest-fixed atom. Resolve/record its container image
   and repository working directory. Do not assume every V2 image uses `/testbed`.
4. In a clean, isolated environment, check out that base and apply **all test patches**.
5. G1: run each atom's target tests in this shared state. Every atom must still have its
   required failing-test behavior. Patch conflicts, collection errors and missing dependencies
   are construction/environment failures, not evidence of a live bug.
6. In a separate clean copy, apply all gold source patches. G2: every test in the union must pass.
7. Publish the common snapshot, test context and provenance; keep gold information out of
   the model workspace. Seal repository history and disable network in evaluation containers.

Rejected groups are recorded with reasons and resampled. The gold patches must apply and
pass together; a proposed base cannot be accepted solely because its date precedes all fixes.

## Evaluation

The trusted harness prepares the task. The agent sees the repository and target tests,
not `bugs[].gold_patch`, the fixing history or hidden reference files. Reject modifications
to tests and grading configuration. Replay the candidate patch into a fresh grader workspace
and require every target test to pass, with valid test collection and a successful test run.

The main paper profile is 100 turns, $1.50 and 1500 seconds, with one bash tool and fresh
shells. This is distinct from the 60-step/1800-second RFT protocol. Its reported objective is
FAIL_TO_PASS-only targeted repair, not the stricter upstream resolved metric that also checks
PASS_TO_PASS regressions. Do not silently switch between these metrics.

## Included implementation and remaining work

Update: `generate bugfixing` now archives a local Git base, applies test patches, runs real
pytest FAIL_TO_PASS checks, applies joint gold patches and requires all target tests to pass.
See [normalized contracts](../generation-atom-contracts.md). The implementation is for pytest
repositories with supplied dependencies; arbitrary historical image/test-runner adapters
and the evaluation agent are not provided.

`codewalk/domains/bugfixing.py` implements shared-file compatibility, candidate snapshot
selection and test-union planning for explicitly normalized atoms. The published composed
records do not supply every original mining/fixing-date artifact, so they are not a complete
atom-extraction source. The [supplied original workflow](../original-benchmarks.md) now
includes patch mining, image routing and the original agent harness. The native pytest
backend also executes G1/G2 for supported atoms.
Existing local RFT utilities were not copied in
as if they were the paper's generator.
