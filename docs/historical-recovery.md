# Historical benchmark recovery

The later Verus archive supplied all 400 original reference files. The
[original workflows](original-benchmarks.md) document their provenance and verification.
The reference reconstruction described below predates that archive.

The earlier selected policy was to preserve existing paper results and prioritize recovery of the
actual original questions. Matching row counts does not establish dataset identity.
Newly composed tasks must never inherit historical scores. Do not choose tasks or invent
per-task outcomes to match aggregate success rates. Existing reconstructed exports remain
separate experimental artifacts, and the paper release gate remains closed.

The subsequent decision uses replacement Clone/BigO questions for the new v2 benchmark;
see `evaluating-v2.md`. Historical recovery artifacts remain intact, and existing paper
scores still must not be assigned to new questions.

## Recovered original inputs

- **Repair: 568 definitions**, with original groups, commits, image references, test
  patches and gold patches from HF revision
  `7c46f19a018e0d98d3924cbf0dc195ca581a5bce`. Full historical container admission has
  not been replayed. One native joint-repair smoke check is not a full-bank result.
- **Verus: 400 original task files**, all matching their published SHA-256 hashes at
  HF revision `f0e6ec27f39a688ac130d2e98b386ea82f3098b4`.
  Recovered references follow the original component groups. All 400 reference proofs
  verify; all 400 unchanged unfinished tasks are well formed and fail proof verification.
  Original executable tokens, preconditions, and fixed step/driver blocks are preserved.
  These are recovered references, not a claim to recover the original proof-file bytes.

The Verus check used official release `0.2026.07.18.3a4d30b` and Rust 1.96.0 on Windows.
The paper's Linux platform has not been replayed. The official archive SHA-256 is
`85f52a17fd9ee335ac03e1302d9a4723ec4d40ea486e9b74f268cdc5bf51b1d7`.
Reference restoration reuses token-identical public spec helpers where required;
it does not add axioms or assumptions. Raw verification receipts are preserved.

## Still missing

- The paper's **418 Clone tasks**, including depth 10. HF's legacy 300 tasks are not
  established as the paper held-out bank.
- The paper's **320 BigO tasks** and the full 277-problem original atomic selection.
- Historical per-task model responses, evaluation manifests and result bindings.
- Full historical runtime replay and resolution of the paper/HF repair repository-count
  discrepancy (270 stated versus 280 distinct repositories in published definitions).

The partial recovery contains 968 inputs out of the paper's expected 1,706. This is input
recovery coverage, not evaluation completion or proof that historical scores are reproduced.

## Recovery searches

As checked on 2026-11-06: public HF histories contain no missing Clone held-out bank or
BigO bank. The submission Overleaf history (106 commits) and separate preprint history
(six commits) contain paper sources but no task archives. The connected project tracker
contains aggregate scores only. Scoped Flowmatic project and project-memory searches
found earlier QuixBugs/repair work, not these two missing banks. Two public lmcode-ai
repositories concern earlier projects. Mao timed out both directly and via Flowmatic.
No local AWS/Modal credential configuration was found for archive recovery.

The original OpenReview submission is `https://openreview.net/forum?id=WUUreagouA`.
Access currently requires human verification or login; supplementary materials have not
yet been inspected. No claim is made that they contain the missing banks.

## Local artifacts and repeatable packaging

Run `python scripts/package_historical_partial.py` after the recovery checks have completed.
It validates proof receipts and source/reference hashes before packaging the partial
recovery under `outputs/canonical-originals/`. It also freezes hashes of the local paper
experiment sections without editing them. The archive includes repair gold patches and
Verus references: keep judge files separate from model inputs during evaluation.

The previous 1,706-task count-matched reconstruction is retained for research only.
Neither that reconstruction nor this partial archive is approved as a complete paper
benchmark release. No new model evaluation, training, publication or paper edits are
implied by this recovery step.
