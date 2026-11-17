# CodeWalk — Multi-Bug Repair generator

Code that builds the **co-located multi-bug repair** benchmark from
*CodeWalk: Generating Coding Benchmarks by Walking a Problem Graph*.

A level-*N* task presents *N* coupled bugs that are all live at one repository commit.
The agent must fix the source so that the union of the bugs' `FAIL_TO_PASS` tests
passes. Every task passes two gold-verification gates, so a joint solution is known to
exist.

The released dataset (568 tasks, L1–L3) is on HuggingFace:
[`CodeWalk/multi-bug-repair`](https://huggingface.co/datasets/CodeWalk/multi-bug-repair).
This directory holds the code that produced it, plus the two intermediate files you need
to rebuild it exactly.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
modal token new                    # gates and evaluation run in Modal x86 sandboxes
export TOGETHER_API_KEY=...        # only for evaluation, models named together_ai/...
export OPENROUTER_API_KEY=...      # only for evaluation, models named openrouter/...
```

Run every script from this directory. Drivers start sub-steps with the current
interpreter; set `MODAL_PY=/path/to/python` to use a different one.

**Pinned data.** Every script loads SWE-rebench at the revision the release was built
from (`revisions.py`). SWE-rebench-v2 is still being updated, and its `main` has moved
past our revision, so loading `main` would give different candidates. Change
`revisions.py` only if you want to build from newer data on purpose.

## Rebuild the released dataset (no Modal needed)

`all_valid.jsonl` stores the gold-verified groups behind the release. With it, two
commands rebuild `benchmark_dataset.jsonl` byte-for-byte:

```bash
python build_cache.py    # streams SWE-rebench v1/v2 from HF -> instances_cache.json
python assemble.py       # -> benchmark_all.json, benchmark_dataset.jsonl
```

## Full pipeline from scratch

| Step | Command | Output |
|------|---------|--------|
| 0a | `python mine_chains.py --sources swerebench --min-window 2 --max-window 5 --out candidates_swerebench_w2.jsonl`<br>`python mine_chains.py --sources swerebenchv2 --min-window 2 --max-window 4 --out candidates_v2.jsonl` | mined windows |
| 0b | `python build_candidates.py` | `all_candidates.json` |
| 1 | `python build_cache.py` | `instances_cache.json` |
| 2–3 | `python validate_all.py [TARGET=100] [MAXJOBS=8] [TIMEOUT=420]` | `all_valid.jsonl` (v1 L1–L3, v2 L2–L3) |
| 3b | `python build_v2l1_candidates.py`<br>`python run_bench.py v2_l1_candidates.json validate v2l1_valid.jsonl` | v2 L1 candidates, then the validated ones |
| 3c | `python merge_v2l1.py` | appends v2 L1 rows to `all_valid.jsonl` |
| 4 | `python assemble.py` | `benchmark_all.json`, `benchmark_dataset.jsonl` |

What each step does:

- **0a `mine_chains.py`** pools SWE-rebench instances, groups them by repo, sorts by
  commit date, and slides windows over consecutive fixes. It keeps a window only if its
  gold patches form a connected overlap graph over shared files and functions.
- **0b `build_candidates.py`** turns windows into per-level candidates. A level-*N*
  candidate is the first *N* bugs of a mined window. For v1, every bug must also have a
  prebuilt image. v1 L1 is 250 image-having singles, at most 6 per repo. Because a
  candidate is a prefix, it need not be overlap-connected on its own.
- **1 `build_cache.py`** stores base commit, patch, test patch, F2P and image for every
  referenced instance, so later steps never reload the full datasets. It is resumable.
- **2–3 `validate_all.py`** runs a gate script on each candidate, `gate_v1.py` for
  SWE-rebench and `gate_v2.py` for SWE-rebench-v2. It stops each (source, level) at
  `TARGET` valid tasks. In each sandbox, the gate checks out the earliest bug's base
  commit, applies every test patch, then checks:
  - **G1:** every bug's tests fail at the base.
  - **G2:** after applying every gold patch, all those tests pass.

  A group is valid only if both gates hold.
- **3b–3c:** v2 L1 tasks are the single bugs inside the validated v2 L2/L3 chains. Steps
  3b–3c gate the first 160, then append the first 100 that pass.
- **4 `assemble.py`** keeps at most 100 tasks per (source, level) and writes a
  self-contained task per line: image, base commit, and per-bug gold patch, test patch
  and F2P.

**Determinism.** Steps 0a, 0b, 1, 3b and 4 are deterministic. Steps 2–3 run real test
suites concurrently and stop early per (source, level), so a fresh run gives a valid
set that can differ from ours. Jobs still running when a level reaches `TARGET` can
also push it past `TARGET`; step 4 trims the extra. v1 L3 ends at 68 tasks because its
candidates ran out. To get the exact release, use the shipped `all_valid.jsonl`.

## Evaluate a model

```bash
python run_bench.py benchmark_all.json eval results.jsonl openrouter/<model> [MAXJOBS=6]
```

Each task runs in a sandbox with no network access. The `.git` directory is
re-initialized to one sealed commit, so the upstream fix cannot be recovered from
history. The agent gets a single bash tool, one command per turn, with a budget of 100
turns, $1.50 and 1500 s. A task counts as solved when every test in `all_FAIL_TO_PASS`
passes. Trajectories are saved as `colocated_<task>.traj.json` (v1) or
`v2_<task>.traj.json` (v2).

**Complete pass (optional).** This also requires the instances' `PASS_TO_PASS` tests to
stay green:

```bash
python p2p_cache_fill.py                     # -> p2p_cache.json
python regrade_p2p.py results.jsonl          # replays each solved trajectory via modal_regrade_p2p.py
```

The regrade replays the agent's commands, restores the test files to block tampering,
and runs F2P and P2P.

## Files

| File | Role |
|------|------|
| `mine_chains.py` | 0a: mine overlap-connected windows |
| `build_candidates.py` | 0b: windows → per-level candidate pool |
| `build_cache.py` | 1: per-instance cache |
| `gate_v1.py`, `gate_v2.py` | G1/G2 gates for one group (`--run-agent` also runs a model) |
| `validate_all.py` | 2–3: gate every candidate concurrently |
| `build_v2l1_candidates.py`, `merge_v2l1.py` | 3b–3c: v2 L1 tasks |
| `assemble.py` | 4: cap and package the dataset |
| `run_bench.py` | validate or evaluate a task list |
| `p2p_cache_fill.py`, `regrade_p2p.py`, `modal_regrade_p2p.py` | optional complete-pass regrade |
| `revisions.py` | pinned SWE-rebench dataset revisions |
| `all_candidates.json` | shipped candidate pool (5,443 groups) |
| `all_valid.jsonl` | shipped gold-verified groups: 570 rows; v2 L2 and v2 L3 have 101 each, so step 4 keeps 568 |

## Reproducibility check

We re-ran the pipeline with this code in online mode, after SWE-rebench-v2's `main` had
moved past the pinned revision, and compared against the original artifacts:

| Step | Result |
|------|--------|
| 0a mining (v1, v2) | identical windows (19,533 and 5,149) |
| 0b candidate pool | identical `all_candidates.json` |
| 3b v2 L1 candidates | identical |
| 3c merge | identical `all_valid.jsonl` |
| 4 assemble | identical `benchmark_dataset.jsonl`, same file as the HF release |
| 2 gates on 5 groups (v1/v2 × L2/L3, plus one rejected pair) | same verdicts, and identical per-bug pass/fail/error counts before and after gold |

## Sources and license

Tasks are built from [`nebius/SWE-rebench`](https://huggingface.co/datasets/nebius/SWE-rebench)
and [`nebius/SWE-rebench-V2`](https://huggingface.co/datasets/nebius/SWE-rebench-V2),
both CC BY 4.0. Each task also carries code from an upstream GitHub repository, whose
own license applies.

- **SWE-rebench (v1):** image `swerebench/sweb.eval.x86_64.<id>`, repo at `/testbed`,
  conda env `testbed`.
- **SWE-rebench-v2:** image `docker.io/swerebenchv2/<repo>:<tag>`, repo at
  `/<reponame>`, system python.

## Citation

```bibtex
@misc{codewalk2026,
  title        = {CodeWalk: Generating Coding Benchmarks by Walking a Problem Graph},
  author       = {Jiaxin Fang and Runyuan He and Arnav Gupta and Sahil Kumawat and Huanzhi Mao and Alvin Cheung},
  year         = {2026},
  howpublished = {arXiv preprint (forthcoming)}
}
```
