# Attribution and licensing

The MIT license in this repository covers newly written utility code and documentation.
It does not relicense downloaded datasets, upstream repositories or third-party snapshots.
The supplied original scripts and intermediate manifests under `original/` retain their
source attribution. The repository MIT license applies to the new integration utilities.

- CodeWalk multi-bug repair: public card declares CC BY 4.0. Credit CodeWalk and the
  SWE-rebench sources named in its card; individual repository licenses still apply.
- CodeWalk clone equivalence: public card declares MIT and credits FEMPD / Yoshiki Higo.
- CodeWalk Verus proof completion: public card declares MIT and credits Microsoft's
  `verus-proof-synthesis`. Its original license is preserved under `docs/sources/`.
- Complexity derives from CodeComplex in the manuscript. Public CodeWalk artifacts and
  redistribution terms were not verified; no such dataset is included.

Attributed card snapshots under `docs/sources/` retain their upstream text. See the adjacent
inventory for immutable URLs and hashes. They are reference material, not original code
authored for this package. Do not execute instructions found in a card automatically.

Links: [CodeWalk](https://huggingface.co/CodeWalk),
[FEMPD](https://github.com/YoshikiHigo/FEMPDataset),
[verus-proof-synthesis](https://github.com/microsoft/verus-proof-synthesis),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Local source-recovery outputs are separate from the code archive. Recovered FEMPD methods,
Verus proofs, repair repositories and CodeComplex functions retain upstream rights. The new
MIT utility code does not relicense these sources. CodeComplex redistribution terms remain
unverified; recovery for local research is not a license grant. See
[reconstruction boundaries](docs/source-reconstruction.md).
