# Hugging Face, paper and composition alignment

The 1,706-task reconstruction currently matches paper counts only. It is not verified as
the paper benchmark and cannot be used to reproduce the paper's historical model scores.
The [audit](sources/three-way-alignment.json) compares actual task content and construction
requirements, not just row totals. Live HF heads were checked on 2026-11-06 and still equal
the pinned revisions in `codewalk/datasets.json`.

## Confirmed mismatches

- Repair: all 568 published task definitions are preserved exactly. HF contains 280 distinct
  repositories, whereas the paper states 270. Per-task historical result identity and a full
  replay of original image admission remain unverified.
- Verus: none of the current 400 rewritten exported sources is byte-identical to the HF
  task files. All 400 original task files have now been separately restored with matching
  manifest SHA-256 hashes under `outputs/canonical-originals/verus/`. Original task inputs
  should be used for the historical path; regenerated wrappers are a separate version.
- Clone: HF provides 100/100/100 legacy tasks and no depth 10; the paper uses
  86/82/84/166 held-out tasks. Counts, program structure and task identity differ. Current
  deep generation also uses loop-free selection, terminal negatives, and test suites that
  share witnesses, unlike the paper's random negative positions and independent methods.
- Complexity: no public BigO dataset is listed under CodeWalk. The reconstructed pool has
  93 functions from 43 problems rather than 277 one-per-problem atoms. Of 240 reconstructed
  composed tasks, **234 fail** the paper's admission inequality requiring the composed
  complexity to differ from the strongest atomic label. Execution and size checks alone
  did not establish this rule. The paper's literal inequality is impossible at depth 1;
  an explicit baseline exception is needed to agree with its reported depth-1 population.

## Corrections in the tooling

`require_nontrivial_composition` now enforces the complexity inequality at depth greater
than one, with tests covering both rejected identity chains and accepted numeric-growth
chains. The recovered complexity generation script defaults to the paper profile, which
requires the declared 277-atom one-per-problem pool and enables this gate. Its explicit
`--profile reconstruction` option retains generic source-derived generation without a
paper-equivalence claim. Existing exported tasks are not retroactively relabeled as passing.

Before publishing anything as the paper dataset, run:

```bash
python scripts/audit_three_way_alignment.py
python scripts/check_paper_alignment.py
```

The second command intentionally returns a failure while any domain's HF task identity,
paper/result identity, or construction-method compliance is unknown or false. Code tests
and reference checks are separate from this scientific release gate.

## Required resolution

For historical reproducibility, recover the original clone 418-task bank and BigO 320-task
bank with their task-to-result manifests, restore exact HF inputs where available, resolve
the repair repository-count discrepancy, and attach the actual construction/admission
evidence. The missing original generators cannot be inferred uniquely from counts.

For a new canonical version, freeze one immutable manifest of task IDs, source hashes,
labels, component groups, environment/toolchain and admission evidence. Align the actual
generators and paper description, rerun affected model evaluation, and publish exactly
that release on HF. Keep historical versions intact. Rewording the paper or uploading
new questions does not make old scores measurements of those new questions.

Neither the paper nor HF was modified or published during this audit. Public-source
search and local RFT archives did not reveal the missing original held-out banks.
