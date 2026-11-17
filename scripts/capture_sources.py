"""Copy attributed cards/receipts (not task data) into the release source inventory."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from codewalk.data import registry


def main():
    output = ROOT / "docs/sources"
    output.mkdir(parents=True, exist_ok=True)
    inventory = {"audit_date": "2026-11-05", "artifacts": []}
    for domain, spec in registry().items():
        if not spec.get("repo_id"):
            continue
        source = ROOT / "data" / domain
        receipt = json.loads((source / "download_receipt.json").read_text(encoding="utf-8"))
        if (receipt["repo_id"], receipt["revision"]) != (spec["repo_id"], spec["revision"]):
            raise ValueError("Receipt does not match pinned source")
        for relative in spec["files"]:
            if not (relative.endswith(".md") or relative.startswith("licenses/")):
                continue
            content = (source / relative).read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != receipt["files"][relative]["sha256"]:
                raise ValueError("Downloaded source has changed")
            filename = domain + "-" + Path(relative).name
            (output / filename).write_bytes(content)
            inventory["artifacts"].append({"file": filename, "sha256": digest,
                "upstream_url": f"https://huggingface.co/datasets/{spec['repo_id']}/blob/{spec['revision']}/{relative}",
                "declared_license": spec["license"]})
        (output / f"{domain}-download-receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    (output / "inventory.json").write_text(json.dumps(inventory, indent=2)+"\n", encoding="utf-8")
    print(f"Captured {len(inventory['artifacts'])} attributed source documents")


if __name__ == "__main__":
    main()
