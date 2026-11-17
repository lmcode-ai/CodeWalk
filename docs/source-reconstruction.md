# Archived source reconstruction subset

The active export now contains all 1,706 paper slots; see the
[paper-sized reconstruction](paper-sized-reconstruction.md). The 679-task bank below is retained as history.

The `source-reconstructed-2026-11-06` bank contains **679 tasks** admitted by actual
compilers, tests or Verus. It is a new source-derived benchmark, not an exact historical
reproduction. The initial Hugging Face releases remain unchanged. No model inference was run;
previous benchmark scores cannot be assigned to this bank.

## What was recovered

- **CodeClone: 300 tasks**, 100 each at L1, L2 and L3, with 50 EQ and 50 NEQ at each level.
  All 461 component pair IDs referenced by the initial release were recovered from the
  [FEMPD database](https://github.com/YoshikiHigo/FEMPDataset), including actual Java methods
  and original EvoSuite test source. Of these, 412 passed the supported deterministic atom
  checks; 391 appear in the final bank. **238 tasks retain the original component group and
  order**. The remaining 62 slots use new groups from that same original component pool.
  The legacy independent `Object[]` aggregation design is retained. Unseeded random pair
  13254 is excluded; its three affected slots were replaced and fully re-admitted.
- **Bugfixing: 37 tasks**, L1/L2/L3 = 12/15/10. Original repository commits, patches and
  test patches are used for python-fastjsonschema, python-markdownify and packaging. Every
  target test fails normally before the gold fixes and passes after their joint application.
  Native Windows dependencies differ from the original benchmark containers. Other repositories
  were not admitted merely to reach the old 568-task count.
- **Verus: 147 tasks**, L1/L2/L3/L10 = 87/25/25/10. Actual algorithms and reference proofs
  were recovered from [verus-proof-synthesis](https://github.com/microsoft/verus-proof-synthesis).
  Executable projections and fixed wrappers are checked against their source. References verify;
  unfinished tasks fail proof verification. All 147 public tasks also pass an additional
  type check with proof verification disabled. The L10 bank uses a conservative compatible
  vector subset. New wrappers and a different toolchain prevent byte-for-byte equivalence.
- **BigO: 195 tasks**, L1/L2/L3/L10 = 25/80/80/10. A restricted extractor obtained 25 supported
  atoms from 4,900 actual [CodeComplex](https://github.com/sybaik1/CodeComplex) programs.
  Accepted function costs agree with the original program labels and restricted AST analysis;
  supplied execution cases check size transfer. This does not prove arbitrary Python costs.
  There are no cubic or NP atoms. The historical CodeWalk BigO pool remains unavailable.

Clone equivalence is relative to recovered/regenerated tests, not a mathematical equivalence
proof. Extracted regression inputs and generated boundary inputs share witnesses; they must
not be described as independent historical suites or a full replay of the original EvoSuite
runner. Surviving source is preferable to invented algorithms, but it cannot recover missing
historical selection decisions, environments or all admission tests.

## Local outputs and evidence

Generated data stays outside Git under `outputs/reconstructed-benchmark-final/`, with the
archive at `outputs/source-reconstructed-benchmark-final.zip`.

- `model_inputs/`: public task rows and source/repository files only.
- `judge/`: labels, reference proofs, gold patches, provenance and admission evidence.
- `judge/verus-additional-typechecks.json`: separate public-task well-formedness checks.
- `manifest.json`, `reconstruction-report.json` and `SHA256SUMS`: counts and integrity records.
- `LICENSES/`: recovered upstream notices; individual repositories retain their own notices.

Never expose the judge directory to a model. Use `codewalk materialize` to create an agent
workspace from a public row. Source overlap with the initial bank is intentional; this is
not an unseen-source test split. The [machine-readable report](sources/source-reconstruction.json)
records exact counts and limitations. Thirty-eight local tests pass, including actual tool
integration; reference-label controls are plumbing checks, not model evaluation scores.

## Rebuilding and extending

Install the optional recovery dependencies with `pip install -e '.[repair,recovery]'`.
Pinned upstream revisions are in `codewalk/recovery/upstreams.json`. Recovery scripts use
`outputs/source-recovery/` for cached sources and normalized atomic JSONL. Start with
`scripts/recover_upstream.py` and `scripts/recover_fempd.py`, then the domain-specific
`scripts/rebuild_*_atoms.py` adapters. Recovery uses the pinned public downloads in `data/`;
download those first with the README commands. Scripts without an argument parser use
the documented workspace paths directly; inspect these paths before executing them.
Recovery may require network access and configured Java, Python dependencies and matching
Verus/Rust toolchains. Native execution runs upstream code locally.

The generation scripts consume these real atoms through the same validation, compatibility,
rendering and admission interface as other datasets. `generate_clone_original_first.py`
prioritizes original groups; `replace_stochastic_clone.py` replaces unsupported random
components. `recompose_repair.py`, `generate_recovered_verus.py` and
`generate_recovered_bigo.py` create the other banks. The bounded conservative Verus chain
mode avoids known incompatible downstream preconditions without weakening their contracts.
Explicit candidate groups passed through `generate --groups` still undergo full admission.

`configs/source-reconstruction.json` selects the admitted runs and exact quotas;
`scripts/package_reconstructed_data.py` checks public-file hashes, admission gates,
duplicate component groups and expected counts before export. Keep generated evidence and
source caches as separate backups. The detailed [new dataset guide](adding-a-dataset.md)
and [atom contracts](generation-atom-contracts.md) describe the common design.

Source recovery is not a redistribution license. CodeComplex redistribution terms have not
been verified; the local data archive has not been published. Preserve all upstream notices
and resolve source-specific terms before public data redistribution.

## Full-size targets confirmed against the paper

The [target profile](../configs/reconstruction-targets.json) records paper counts, not
completed generation: repair 200/200/168 (568), Verus 100/100/100/100 (400), BigO
80/80/80/80 (320), and clone 86/82/84/166 (418). The four depths are 1, 2, 3 and 10
except repair, which ends at 3. Clone retained denominators 161--166 at depth 10 are
model-specific evaluation exclusions, not different generation quotas.

All paper banks sum to 1,706 tasks. Retaining the previously accepted legacy 300-task
clone version gives 1,588 tasks. The admitted recovered bank above remains 679 tasks.
Published repair and Verus records in `data/` retain their full original counts; local
native re-admission subsets are smaller. Targets cannot be satisfied by duplicating
questions, changing depth labels, or counting unadmitted candidates as successful generation.

## Active paper-sized profile

The [paper-sized reconstruction guide](paper-sized-reconstruction.md) supersedes the earlier subset as
the active release target. It specifies all 1,706 paper slots, actual clone data-flow chains,
expanded complexity atoms, complete L1 Verus recovery and exact restoration of published
repair definitions. Fresh admission and imported historical definitions remain distinct.
