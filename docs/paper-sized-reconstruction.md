# Count-matched reconstruction archive

**Alignment audit correction:** this bank matches counts, not all paper methods or HF
identities. See the [three-way alignment audit](three-way-alignment.md). In particular,
234/240 higher-level complexity tasks fail the paper nontriviality rule. The commands
below document the earlier reconstruction and do not reproduce the historical experiment.
Complexity reproduction requires explicit `--profile reconstruction`; paper-mode generation
now requires the original 277-atom one-per-problem pool and enforces the nontriviality gate.
Exporting this archive requires `--allow-count-matched-reconstruction`.


This is the completed local paper-sized export. The earlier 679-task recovered subset and the legacy
300-task clone bank remain separate historical artifacts.

The exact paper quotas are:

- Repair: 200, 200 and 168 tasks at depths 1, 2 and 3; total 568.
- Proof completion: 100 tasks at each of depths 1, 2, 3 and 10; total 400.
- Complexity: 80 tasks at each of depths 1, 2, 3 and 10; total 320.
- Clone equivalence: 86, 82, 84 and 166 tasks at depths 1, 2, 3 and 10; total 418.

All four domains total **1,706** tasks. Clone levels are individually balanced EQ/NEQ.
The paper's model-specific retained clone denominator of 161--166 at depth 10 reflects
evaluation exclusions, not different bank sizes. The authoritative curation profile is
[`configs/paper-reconstruction.json`](../configs/paper-reconstruction.json).

## What matching the paper means here

The output matches the paper's task counts and depth distribution. Clone now uses actual
exact-type data-flow chains, including multi-argument methods: one downstream parameter
receives the preceding return, while the other parameters remain explicit public inputs.
Fresh atomic and whole-chain checks reject masked negatives and chains with no normal
paired execution. Only one negative component is allowed per chain.

Missing historical artifacts still prevent an exact replication of the paper's experiments.
The following differences remain explicit in the machine-readable manifest:

- Repair restores all 568 original published definitions, preserving original component
  groups, common commits, image names, test patches and gold patches. This is more faithful
  than replacing them with new small-repository combinations. The full original image
  environments have not all been replayed locally. These rows have status
  `published_original_not_locally_readmitted`; they are not assigned new passing G1/G2 flags.
- Verus recovers all 100 original L1 executable/specification definitions, with systematic
  identifier normalization and actual upstream proofs. Two references restate an existing
  immutable input bound as a loop invariant for the current verifier. Higher levels are
  newly checked compatible-vector chains and differ from the original chain selection.
  Preconditions, executable tokens and protected drivers remain intact.
- Complexity uses 93 distinct real functions across 43 source problems. Unary and fixed
  multi-argument adapters expose an explicit size measure. Multiple functions from one
  problem may enter the pool; each composite uses at most one atom per source problem.
  This differs from the paper's 277-atom one-per-problem pool. Restricted AST analysis,
  original program-label agreement and finite size checks are not universal cost proofs.
  The recovered supported pool does not contain cubic or NP atoms.
- Clone admission uses recovered regression and regenerated boundary inputs with shared
  witnesses, not the two independent historical CodeWalk suites. Depth-10 generation
  restricts candidates to real methods without explicit loops to control execution time.
  Negative depth-10 candidates place their single negative component last, then still
  require an actual whole-chain witness. This changes source selection and difficulty.

New benchmark scores are required. Neither matching counts nor passing reference checks
licenses reusing the paper's historical model scores. No model inference is part of this
reconstruction. Source overlap is intentional; the bank is not an unseen-source test split.

## Rebuild the source pools

Use Python 3.11+ and install `pip install -e '.[repair,recovery]'`. Download the pinned
public datasets using the README commands. Verus recovery can read the public source
tree produced by `codewalk download verus --include-verus-sources`, so the original
internal source repository or a local ZIP is not required. A matching numbered public
ZIP can alternatively be supplied with `--archive`.

Run `recover_upstream.py`, `recover_fempd.py` and `rebuild_clone_atoms.py` as described
in the [source recovery notes](source-reconstruction.md). Configure a real JDK and the
matching Verus/Rust toolchain; local configurations and source caches stay outside Git.

```bash
python scripts/rebuild_complexity_atoms.py --selection function \
  --output outputs/source-recovery/bigo-unary
python scripts/rebuild_multiargument_complexity_atoms.py \
  --output outputs/source-recovery/bigo-multi
python scripts/assemble_complexity_pool.py \
  --unary outputs/source-recovery/bigo-unary/validated-candidates.jsonl \
  --multi outputs/source-recovery/bigo-multi/validated-candidates.jsonl \
  --output outputs/source-recovery/bigo-paper

python scripts/rebuild_verus_atoms.py --config outputs/verus-config.json \
  --standalone --output outputs/source-recovery/verus-paper-l1
python scripts/restore_published_repair.py --output outputs/paper-original-repair
```

Standalone Verus atoms support original non-chainable types without weakening validation.
Their raw executable helpers, spec helpers and fixed drivers must still match references;
they are restricted to depth 1. Higher-level source atoms use the typed chain contract.

## Generate and curate

```bash
python scripts/generate_recovered_bigo.py \
  --atoms outputs/source-recovery/bigo-paper/atoms.jsonl \
  --counts 1:80,2:80,3:80,10:80 --max-per-source 1 \
  --output outputs/source-derived-datasets/paper-bigo

# Run each depth separately with its corresponding output directory.
python scripts/generate_recovered_clone.py --config outputs/java-config.json \
  --mode chain --counts 1:86 --output outputs/source-derived-datasets/paper-clone-1
# Repeat for 2:82 and 3:84 with paper-clone-2 and paper-clone-3.

# Class-specific deep-chain shards: 83 EQ and 83 NEQ.
python scripts/generate_recovered_clone.py --config outputs/java-config.json \
  --mode chain --loop-free --label equivalent --counts 10:83 \
  --output outputs/source-derived-datasets/paper-clone-positive
python scripts/generate_recovered_clone.py --config outputs/java-config.json \
  --mode chain --loop-free --label not_equivalent --counts 10:83 \
  --output outputs/source-derived-datasets/paper-clone-negative

python scripts/generate_recovered_verus.py --config outputs/verus-config.json \
  --atoms outputs/source-recovery/verus-paper-l1/atoms.jsonl --counts 1:100 \
  --output outputs/source-derived-datasets/paper-verus-1
# For each of 2, 3 and 10, use the chainable recovered pool with --conservative,
# --counts DEPTH:100 and --output outputs/source-derived-datasets/paper-verus-DEPTH.

python scripts/package_reconstructed_data.py --profile configs/paper-reconstruction.json \
  --output outputs/paper-sized-benchmark --archive outputs/paper-sized-benchmark.zip
```

The curation step checks exact quotas, unique ordered chain identities, public-input hashes
and both admission gates for freshly generated tasks. It restores published repair tasks
through a separate explicit path. It never marks their imported historical definitions as
newly admitted. Extra admitted clone candidates are downsampled to the exact balanced quota.
Rejected, timed-out, duplicate or excess candidates do not fill the final counts.

An optional `atomic_reference_cache` in a Verus configuration saves repeated atomic proofs.
Keys include exact source, execution configuration and available Verus executable/standard
library fingerprints. Every composite reference and unfinished public task is still checked
individually. Cache receipts preserve the original successful atomic verification execution.

## Repair preparation and evaluation boundary

`model_inputs/` contains public questions. `preparation/bugfixing.jsonl` contains original
environment recipes for the trusted harness. `judge/` contains all answers, reference proofs,
gold patches, source lineage and validation status. Do not mount judge data into an agent
workspace or serialize preparation metadata into the prompt.

Prepare a repair task lazily from its exact common base and original test patches:

```bash
python scripts/prepare_published_repair.py \
  --recipes outputs/paper-sized-benchmark/preparation/bugfixing.jsonl \
  --task-id ORIGINAL_TASK_ID --output outputs/agent-workspace
# Optional: --repository /path/to/local/git/object/store avoids a source download.
```

The preparer uses a Git archive or the original GitHub commit archive, applies test patches
in an isolated Git context, and excludes history and gold patches from the workspace.
Special-file/symlink repositories require their original container preparation. It does not
install dependencies, recreate every historical image or run G1/G2. Use the original image
recipe for actual benchmark execution, resolve and record its immutable digest, and locate
its real repository path; do not assume every image uses `/testbed`.

For proof and clone tasks, `codewalk materialize` writes only public files. Classification
uses `grade-labels` and `score`; actual repair agents and protected-spec proof grading remain
separate from these label utilities. Follow the existing [evaluation settings](evaluation.md).

Data and source backups remain local. Preserve upstream notices. CodeComplex redistribution
terms remain unverified, so local reconstruction is not permission to publish that source.

## Verification of the completed export

The export audit confirms 1,706 unique task identities, zero duplicate semantic groups,
exact level quotas and balanced clone labels. Fresh admission covers 1,138 new clone,
complexity and proof tasks. All 320 complexity tasks were additionally re-admitted with
shared-argument bounds enabled. Forty-two local tests pass. A restored original repair
L2 task was prepared and replayed natively: all 10 targets fail before the fixes and all
10 pass after the joint gold patches. This smoke test is not a replay of all 568 original
image environments. All 738 classification tasks pass reference/incorrect/malformed
control checks (1.0/0.0/0.0), which are pipeline controls, not model scores.

See the [machine-readable verification report](sources/paper-sized-reconstruction.json).
