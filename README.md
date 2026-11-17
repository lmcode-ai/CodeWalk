# CodeWalk: composition and evaluation release preparation

The supplied original Bugfixing, CodeClone, Verus and BigO sources are integrated under `original/`.
The [original workflows](docs/original-benchmarks.md) describe how to rebuild the exact
published repair release, render original Clone compositions and import all 400 original
Verus tasks with their archived reference proofs, and import archived BigO chains
for the common evaluator.

**Active benchmark: version 2 with replacement questions.** Newly composed Clone (418)
and BigO (320) tasks replace the missing historical banks. Repair retains 568 published
definitions; Verus uses 400 byte-identical original inputs with recovered references.
The unified `evaluate` command supports all four domains. See the
[evaluation guide](docs/evaluating-v2.md) for runtime requirements and current validation
limits. Full Repair runtime replay remains incomplete; no all-1,706 runtime claim is made.
Existing paper scores remain historical and cannot be assigned to v2.
See [historical recovery](docs/historical-recovery.md). HF identities, historical paper
results and full composition-method compliance are not yet aligned. See the
[three-way audit](docs/three-way-alignment.md). Run `python scripts/check_paper_alignment.py`
before presenting any export as the paper benchmark; this gate currently fails.


CodeWalk creates coding tasks by composing existing atomic problems. This repository
organizes **multi-bug repair, Verus proof completion, complexity analysis, and clone
equivalence** around a shared extraction → interaction graph → composition → admission
→ evaluation interface. Original public datasets are on [Hugging Face](https://huggingface.co/CodeWalk).
The replacement v2 benchmark is currently local and has not been uploaded there.

**Separate experimental reconstruction: not the historical benchmark.** The
[paper profile](docs/paper-sized-reconstruction.md) now contains 1,706 tasks: 568 repair,
400 proof, 320 complexity and 418 clone tasks, with the exact paper depth counts.
Fresh generation and restoration of original published definitions have distinct validation
status: 1,138 tasks were freshly admitted, and 568 original repair definitions were restored.
The earlier [679-task subset](docs/source-reconstruction.md) remains archived.
Data stays local and separate from the code release.

The `generate` command renders source/repositories and performs actual admission. Supported
backends include pytest repair, Java aggregation and multi-argument data-flow chains,
annotated Python cost chains and recovered Verus source modules. The imported historical
scripts have their own dependencies and runtime; see
[implementation status](docs/implementation-status.md) for the remaining differences.

The older `plan` command remains candidate-only and never admits a task. Use `generate`
for executable composition. Both share graph sampling, but have different atomic-input schemas.

The following version differences are documented and retained for the current release scope:

- The public repair release contains 568 tasks; the separate 268-task RFT campaign is not this benchmark.
- The public Verus release has 400 task inputs, **without reference proofs or the generator**.
- The public clone release contains legacy balanced 100-task sets at L1–L3, not the paper's
  86/82/84/166 evaluation sets. Released higher-level programs contain independent
  `Object[]` aggregation wrappers. They must not be described as recovered data-flow chains.
- No public complexity dataset was listed under CodeWalk when checked on 2026-11-05.

## Quick start

Python 3.11+; the core and offline tests use only the standard library.

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -s tests -v

# Immutable dataset revisions are in codewalk/datasets.json.
python -m codewalk download codeclone
python -m codewalk inspect codeclone --root data/codeclone
python -m codewalk download bugfixing
python -m codewalk inspect bugfixing --root data/bugfixing
python -m codewalk download verus --include-verus-sources
python -m codewalk inspect verus --root data/verus

# Synthetic example: candidate group only, not an admitted repair task.
python -m codewalk plan bugfixing --atoms examples/repair_atoms.jsonl \
  --level 2 --count 1 --seed 42 --output outputs/repair-plans.json

# Complete, small extension example with executable admission checks.
python -m examples.affine_domain
```

For actual generation, prepare atomic JSONL following the
[domain contracts](docs/generation-atom-contracts.md), then run:

```bash
python -m codewalk generate codeclone --atoms clone-atoms.jsonl --level 3 --count 20 \
  --config configs/generation.native.json --output outputs/clone-generated

# Trusted synthetic fixtures exercising real compilation/execution:
python -m pip install -e '.[repair]'
python -m examples.generation_demo bigo --output outputs/demo-bigo
python -m examples.generation_demo bugfixing --output outputs/demo-repair
python -m examples.generation_demo codeclone --output outputs/demo-clone
python -m examples.generation_demo verus --output outputs/demo-verus
python -m examples.affine_backend --output outputs/demo-new-domain
```

Java requires a JDK; Verus requires its matching Rust toolchain. Configure executable paths
when they are not on PATH. Native mode executes trusted atoms on the host; use a pinned
Docker image for external source code. Only admitted tasks enter a complete export.
See [generator verification](docs/generator-verification.md) and the
[detailed extension guide](docs/adding-a-dataset.md).

`data/` and `outputs/` are excluded from Git. Downloading is opt-in; none of the commands
launches a model, rents a GPU, or starts a remote campaign.

## Composition methods

- [Shared design and graph semantics](docs/composition.md)
- [Multi-bug repair](docs/domains/bugfixing.md): connected shared-file groups at a common live snapshot.
- [Verus](docs/domains/verus.md): typed function chains with fixed predicates and driver.
- [Complexity](docs/domains/bigo.md): typed chains plus explicit intermediate-size derivation.
- [Clone equivalence](docs/domains/codeclone.md): distinguish legacy aggregation from proposed/paper data-flow chains.
- [CodeClone alignment plan](docs/codeclone-alignment.md): recover matching paper artifacts or rebuild and re-evaluate a separately versioned bank.
- [Add a new dataset/domain](docs/adding-a-dataset.md): interface, working example, admission and split checks.

## Evaluation

[Evaluation settings](docs/evaluation.md) and machine-readable
[profiles](configs/evaluation.json) transcribe the **local paper snapshot**. Unspecified
parameters remain `null`; these are not recovered API launch configurations. They separate
the main benchmark from unrelated RFT settings. There is no bundled AutoVerus or repair agent
runner, and no claim that an arbitrary compiler pass is a gold-correct proof.

```bash
python -m codewalk grade-labels codeclone --tasks examples/classification_tasks.jsonl \
  --responses examples/classification_responses.jsonl --output outputs/attempts.jsonl
python -m codewalk score --tasks examples/classification_tasks.jsonl \
  --attempts outputs/attempts.jsonl --n 2 --output outputs/scores.json
```

The scorer requires exact task/sample identities. Missing results and infrastructure errors
prevent a complete score. Invalid model answers are failures. `pass_at_1` is mean success
over all `n` attempts; `pass_at_n_coverage` means at least one success among those `n`.
Do not mix models, protocols, revisions, or splits in one attempt file.

## Repository layout

```text
codewalk/               downloader, candidate planner, classification grading and metrics
codewalk/composition/   unified executable generator and four real admission backends
codewalk/domains/       four explicitly candidate-only domain planning implementations
configs/               evaluation profiles from the paper
docs/domains/          construction method and exact missing backends for each domain
docs/sources/          attributed dataset-card snapshots and source inventory
examples/              synthetic fixtures and a complete new-domain example
tests/                 offline correctness and failure-mode tests
scripts/               release checks and local artifact integrity tools
```

## Sources and publishing

The local manuscript is titled *CoDepth: Model-Free Generation of Coding Benchmarks*;
the public dataset cards use *CodeWalk: Generating Coding Benchmarks by Walking a Problem Graph*.
This package follows the public **CodeWalk** name and records both sources rather than assuming
the snapshots are identical. See [source/version audit](docs/source-audit.md).

New utility code is MIT-licensed. Dataset licenses and upstream code licenses remain separate;
see [NOTICE](NOTICE.md). Do not copy private run logs, model weights, credentials, or benchmark
answers into this repository. [Publishing steps](docs/publishing.md) describe preparing an
independent repository under `lmcode-ai`; no GitHub push is performed by this package.
See [local validation](docs/validation.md) for completed checks and their limits.
The earlier [workflow verification](docs/workflow-verification.md) records artifact/CLI checks;
the current [generator verification](docs/generator-verification.md) covers executable composition.

See the [release overview](docs/overview.md) for included components and reproduction status.
