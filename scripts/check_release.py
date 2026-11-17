"""Check first-party document links, JSON/Python syntax and tracked packaging boundaries."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "data", "outputs", "private", "__pycache__", "build", "dist", ".venv", ".pytest_cache"}


def main():
    failures = []
    checked = 0
    def release_files():
        for directory, children, files in os.walk(ROOT):
            children[:] = [name for name in children if name not in SKIP and not name.endswith('.egg-info')]
            for name in files:
                yield Path(directory) / name

    for path in release_files():
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(x in SKIP or x.endswith(".egg-info") for x in relative.parts):
            continue
        checked += 1
        if path.stat().st_size > 1024*1024:
            failures.append(f"Oversized release file: {relative}")
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        # Upstream snapshots contain links relative to their own repositories.
        if path.suffix == ".md" and not {"sources", "original"}.intersection(relative.parts):
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" in link or link.startswith("#"):
                    continue
                if not (path.parent / link.split("#")[0]).exists():
                    failures.append(f"Broken link in {relative}: {link}")
    if (ROOT / ".git").is_dir():
        tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
        for name in tracked:
            parts = Path(name).parts
            if any(p in SKIP or p.startswith(".env") or p.endswith(".egg-info") for p in parts):
                failures.append(f"Excluded file tracked: {name}")
    inventory = json.loads((ROOT / "docs/sources/inventory.json").read_text(encoding="utf-8"))
    for item in inventory["artifacts"]:
        content = (ROOT / "docs/sources" / item["file"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            failures.append(f"Source snapshot hash mismatch: {item['file']}")
    original = ROOT / 'original'
    originals = json.loads((original / 'snapshot-sha256.json').read_text(encoding='utf-8'))
    for relative, expected in originals.items():
        path = original / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append(f'Original source checksum mismatch: {relative}')
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Release structure checks passed ({checked} files); not a semantic reproduction or credential audit.")


if __name__ == "__main__":
    main()
