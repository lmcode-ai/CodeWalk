# Original benchmark workflows

The supplied sources are integrated under [Bugfixing](../original/bugfixing),
[CodeClone](../original/codeclone), [Verus](../original/verus), and [BigO](../original/bigo). The
[checksum manifest](../original/snapshot-sha256.json) records the imported files.
Use a working copy of each directory for the original
scripts that generate files beside their inputs.

## Bugfixing

The original implementation includes SWE-rebench mining, candidate selection, pinned
source revisions, Modal G1/G2 gates, assembly, agent evaluation and regression regrading.
The archive contains 570 validated groups before capping. The original assembler exports
568 tasks, with 200 at L1, 200 at L2 and 168 at L3.

Rebuild from the pinned release already downloaded in the CodeWalk workspace:

```bash
python scripts/use_original_benchmarks.py rebuild-repair \
  --published data/bugfixing/data/test.jsonl \
  --output outputs/original-repair-rebuilt
```

The bridge extracts a cache from the pinned dataset and runs the original `assemble.py`
with the supplied `all_valid.jsonl`. It verifies the assembled release SHA-256 and writes
the task index and instance cache alongside the dataset. This path checks original
assembly using already published patch data. The upstream-data workflow starts at
`build_cache.py` and is documented in the [original README](../original/bugfixing/README.md).

For the original evaluator, copy `benchmark_all.json` and `instances_cache.json` into
your Bugfixing working copy. Install its `requirements.txt` and configure Modal and the
chosen model provider. From that directory run `python run_bench.py benchmark_all.json
validate validation.jsonl` for the gates, or `python run_bench.py benchmark_all.json eval
results.jsonl openrouter/<model>` for agent evaluation. The original runtime uses the
benchmark images and the union of `FAIL_TO_PASS` tests. Local integration checked assembly
and release identity. Modal gates and model calls require their configured runtimes.

## CodeClone

The original implementation includes FEMPD positive/negative selection, execution and
EvoSuite verification, Java composition and model evaluation. Its composition concatenates
component arguments and aggregates their results into `Object[]`. Use the original
generation directory when evaluating that design. The CodeWalk v2 bank uses data-flow
chains with a separate task identity.

The original builders expect a local FEMPD database at `fempd/ijadataset.db` and `java`
and `javac` on `PATH`. From the `composition` directory, `python build_l1.py` renders
atomic pairs. `python build_l2.py` and `python build_l3.py` generate accepted groups, and
`python build_ln.py 10 <target-per-class>` generates depth-10 groups. The no-overlap
builder expects `negative_atom_buckets_nooverlap.json`. Select a supplied bucket version
explicitly before using that variant, since the archive includes numbered alternatives.

Render accepted group files and export them to the common evaluator in one command:

```bash
python scripts/use_original_benchmarks.py render-clone \
  --database /path/to/ijadataset.db \
  --positive /path/to/l10_accepted_positive.json \
  --negative /path/to/l10_accepted_negative.json \
  --level 10 --output outputs/original-clone-l10
```

Use `import-clone --input <file> [<file> ...] --output <new-directory>` in the same script
for already rendered JSON or JSONL tasks such as `l1_full.json`. Both commands write
answer-free inputs and a separate judge file. The exported `original-codeclone:` IDs
are used in submission files for `python -m codewalk evaluate codeclone`.

The supplied archive omits the full FEMPD database and the final paper evaluation task
list. Local integration used recovered FEMPD methods to compile and run one equivalent
and one divergent L2 composition through the original verifier, then rendered and graded
both with the common evaluator. This checks the integration. It does not establish the
identity of the paper's 418 questions.

## Verus

The four supplied archive parts reconstruct a 115,357,554-byte Zstandard tar archive.
The verified SHA-256 is
`20fe2a203bb9186c7f06246b394dcc605faf2ed4cd29eab17f97a61c5d9cbd56`.
The integrated source includes `compose.py`, `taskify.py`, the bank builders, original
atomic pools, batch evaluation drivers and the archived AutoVerus implementation with
its prompts and examples. Comments and status messages were translated into English
in nine files. Their original hashes are recorded in the
[archive receipt](../original/verus-archive-receipt.json).

The archive's `tasks/` and `tasks_s10/` directories contain the 400 published inputs,
with 100 at each of L1, L2, L3 and L10. The pinned manifest maps every input to its
original reference. All 400 inputs match their published SHA-256 values, and the
original `taskify.py` reproduced every input exactly from its archived reference.
All 400 original references passed the unified evaluator using Verus
`0.2026.07.18.3a4d30b` and Rust 1.96.0 on Windows. The original composer also passed
reference and unfinished-proof controls at each of the four levels.

Extract the verified archive into a working directory, then import the original bank:

```bash
python scripts/use_original_benchmarks.py import-verus \
  --source /path/to/verus_composition --output outputs/verus-original-bank
python -m codewalk evaluate verus --root outputs/verus-original-bank \
  --submissions responses.jsonl --config verus-runtime.json --output attempts.jsonl
```

The import verifies task and reference hashes and reruns the original taskifier.
Use the `original-verus:` task IDs in submissions. The generated `judge/` directory
contains the original reference proofs and stays separate from model inputs. See the
[evaluation guide](evaluating-v2.md) for submission and runtime formats.

For original bank generation and model evaluation, use the complete extracted archive
on Linux. The batch drivers expect the archived directory layout, a compatible Python
environment, Verus, and AutoVerus utilities including Lynette. Provide your own model
configuration for `run_full_batch_v3.py`. The code package includes source files while
the complete archive retains the runtime dependencies and historical run artifacts.
Linux model runs and binding historical scores to individual archived tasks remain
unverified.

## BigO

The supplied archive contains six original Python scripts and 733 generated chains.
The chain counts are 325 at L2, 296 at L3, and 112 at L10. The archive includes
growth measurements and a generation report. The L1 bank, underlying `python_data.jsonl`,
and final paper evaluation task list are absent. The
[archive receipt](../original/bigo-archive-receipt.json) records the hashes.

The original generator converts single-integer stdin/stdout solutions to callable
stages, checks agreement among sibling solutions, searches for compatible chains
and compares composed outputs with stage-by-stage execution. It estimates each
intermediate output's growth and propagates it through the stage cost labels.
Run it with an input JSONL containing `problem`, `src` and `complexity`:

```bash
python original/bigo/generate.py --data /path/to/python_data.jsonl \
  --levels 2 3 10 --out outputs/bigo-generated --cache outputs/bigo-runs.sqlite
```

The generator executes input programs. Use a trusted input corpus or an isolated
runtime. To evaluate the archived chains, import their generated files:

```bash
python scripts/use_original_benchmarks.py import-bigo \
  --input /path/to/chains/output/chains_L2.jsonl \
          /path/to/chains/output/chains_L3.jsonl \
          /path/to/chains/output/chains_L10.jsonl \
  --output outputs/bigo-original-bank
python -m codewalk evaluate bigo --root outputs/bigo-original-bank \
  --submissions responses.jsonl --output attempts.jsonl
```

Use the `original-bigo:` task IDs and a standalone complexity label in each
submission. The importer keeps original labels and records source hashes in the
judge file. Local checks replayed the recorded input/output example and recomputed
the archived label with the original cost formula for all 733 chains. The label
checks reuse the archived atomic labels and measured growth classes. The paper rule
requiring a different complexity class from the strongest atomic stage holds for
34 L2, 81 L3, and 80 L10 chains. The archived export therefore documents the
supplied generation run and does not establish the paper's 320-task selection.
