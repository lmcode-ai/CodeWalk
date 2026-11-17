# Preparing a GitHub release

Scientific release status: the current reconstruction is count-matched only. Run
`python scripts/check_paper_alignment.py` before presenting any dataset as the paper
benchmark. This gate currently fails; see [three-way alignment](three-way-alignment.md).
Passing code tests does not establish task identity or historical-result reproducibility.

The code release repository is [lmcode-ai/CodeWalk](https://github.com/lmcode-ai/CodeWalk).

Run from its root:

```bash
python -m unittest discover -s tests -v
python scripts/check_release.py
git diff --cached --check
git status --short
```

Review README limitations, source audit, licenses, and the staged file list. Do not stage
`data/`, `outputs/`, private paper sources, credentials, checkpoints or historical logs.
The package can be shared as **release-preparation tooling**; do not advertise full benchmark
regeneration while the implementation-status gaps remain.

Use your GitHub commit identity and submit later updates from a topic branch.
Dataset releases remain on Hugging Face at pinned revisions.

For offline review, `python scripts/package_release.py` packages the
staged files into `outputs/codewalk-release-preparation.zip` with a SHA-256 sidecar. It uses
the index, so stage your final changes first. It excludes the downloaded datasets and Git
history and does not create a commit or publish anything.
