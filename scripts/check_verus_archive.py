"""Compare an existing task ZIP against the pinned public manifest; never execute code."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    parser.add_argument("--manifest", default="data/verus/manifest.json")
    parser.add_argument("--output", default="outputs/verus-archive-audit.json")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    checked = 0
    with zipfile.ZipFile(args.archive) as archive:
        manifests = [x for x in archive.namelist() if x.endswith("/manifest.json") or x == "manifest.json"]
        if len(manifests) != 1:
            raise ValueError("Expected exactly one manifest")
        prefix = manifests[0][:-len("manifest.json")]
        for row in manifest["tasks"]:
            source = archive.read(prefix + row["file"])
            if hashlib.sha256(source).hexdigest() != row["sha256"]:
                raise ValueError(f"Content mismatch: {row['file']}")
            checked += 1
    result = {"archive_filename": Path(args.archive).name, "matched_tasks": checked,
              "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
              "scope": "byte integrity only; no proof verification"}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
