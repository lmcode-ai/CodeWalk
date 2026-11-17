# Source and version audit

Audit date: 2026-11-05. This repository follows the public **CodeWalk** name.
The available local manuscript uses **CoDepth: Model-Free Generation of Coding Benchmarks**
at commit `350e07b0c961ba584502d9cd9acddfacbc0483bc`. Source files consulted:
`sections/problem.tex`, `sections/appendix.tex` and domain experiment sections.
The manuscript is not redistributed here. Evaluation settings are transcribed into configs.

## Public artifacts verified

- [Multi-bug repair](https://huggingface.co/datasets/CodeWalk/multi-bug-repair/tree/7c46f19a018e0d98d3924cbf0dc195ca581a5bce):
  568 unique tasks, L1/L2/L3 = 200/200/168, 1104 bug occurrences, **280** distinct repositories.
  The card matches the data; the manuscript's 270-repository count needs reconciliation.
  Test unions and bug counts are structurally consistent; tests were not executed.
- [Verus](https://huggingface.co/datasets/CodeWalk/verus-proof-completion/tree/f0e6ec27f39a688ac130d2e98b386ea82f3098b4):
  manifest lists 400 tasks, 100 each at N=1/2/3/10. Published tasks are unfinished inputs,
  not reference proofs. Manifest inspection alone is not semantic proof re-verification.
  All 400 source files in the available local numbered ZIP match the pinned HF manifest
  byte-for-byte; see `sources/verus-archive-audit.json`.
- [Clone equivalence](https://huggingface.co/datasets/CodeWalk/clone-equivalence/tree/a24a0d0819bfacc28e36594abfb1acb3176638ba):
  300 unique tasks, 100 each at N=1/2/3, balanced 50 EQ and 50 NEQ per level.
  All 100 L2 and all 100 L3 records have `Object[] results` and `return results;` markers
  on both sides. Inspected wrappers invoke components independently. The paper's typed
  data-flow chain method and 86/82/84/166 held-out sets are not these public artifacts.
- Complexity/Big-O: not listed by the CodeWalk public dataset API. This does not establish
  that no private dataset exists; its link, bytes and license remain unavailable.

Machine-readable checks are in [sources](sources/). Cards are preserved with attribution
and download SHA-256 receipts. Data files themselves remain in the ignored local `data/` folder.

## Reconstruction boundary

The unavailable server was the only supplied location of the original generation scripts.
The public cards and existing local files do not contain their full implementations.
The local `rft_levels` utilities concern a different RFT workflow, not those generators.
The public `lmcode-ai/lmcode` repository is an older evaluation application, not a verified
backup of this composition pipeline. No source code was invented and presented as recovered.

The generic manuscript frontier sampler does not itself guarantee a directed chain.
Our new sampler follows the tail for directed domains and the union frontier for undirected
repair. Complexity size propagation and clone whole-chain label checking are explicit
correctness obligations, not claims that the unavailable historical scripts implemented them.

Release decisions still needed: intended public clone version, missing complexity data,
original or independently validated generators/verifiers, and reconciliation of manuscript
counts. These do not prevent publishing clearly labeled preparation tooling.

## Source recovery update (2026-11-06)

The [source reconstruction report](source-reconstruction.md) records the newer real-source recovery,
679 admitted tasks and its limitations. Earlier counts and availability statements in this
document describe the initial public release or earlier fixture verification, not this new bank.
