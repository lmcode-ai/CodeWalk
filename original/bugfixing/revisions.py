"""Pinned HuggingFace dataset revisions the released benchmark was built from.

SWE-rebench-v2 is updated over time, so loading `main` can yield different windows and
candidates. Change these only if you want to build from newer data on purpose; the output
will then differ from the release.
"""
REVISIONS = {
    "nebius/SWE-rebench":    "89cdfbab4ab1bd8f5a658bb212d1b63624f4f881",
    "nebius/SWE-rebench-v2": "475dd5e8703bb5fb22dd3c60b5d038b019eba1e0",
}

def revision(name):
    """Pinned revision for a dataset id (case-insensitive), or None for unpinned sources."""
    return {k.lower(): v for k, v in REVISIONS.items()}.get(name.lower())
