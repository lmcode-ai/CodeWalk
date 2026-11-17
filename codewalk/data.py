"""Download pinned public artifacts, inspect schema, and export answer-free inputs."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.request


def registry():
    return json.loads(Path(__file__).with_name("datasets.json").read_text(encoding="utf-8"))


def safe_path(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
        raise ValueError("Unsafe artifact path")
    resolved_root = Path(root).resolve()
    target = (resolved_root / relative).resolve()
    if not target.is_relative_to(resolved_root):
        raise ValueError("Artifact escapes destination")
    return target


def download(domain, destination, *, include_verus_sources=False):
    spec = registry()[domain]
    if not spec.get("repo_id"):
        raise ValueError("No verified public repository for this domain; supply the real source first")
    root = Path(destination) / domain
    files = list(spec["files"])
    receipt = {"repo_id": spec["repo_id"], "revision": spec["revision"], "files": {}}
    def fetch(relative):
        target = safe_path(root, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/datasets/{spec['repo_id']}/resolve/{spec['revision']}/{relative}"
        request = urllib.request.Request(url, headers={"User-Agent": "CodeWalk-release/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
        temp = target.with_name(target.name + ".part")
        temp.write_bytes(content)
        temp.replace(target)
        receipt["files"][relative] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
    for relative in files:
        fetch(relative)
    if domain == "verus" and include_verus_sources:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        for task in manifest["tasks"]:
            fetch(task["file"])
            if receipt["files"][task["file"]]["sha256"] != task["sha256"]:
                raise ValueError(f"Manifest checksum mismatch: {task['file']}")
    (root / "download_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def read_jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def records(domain, root):
    root = Path(root)
    if domain == "bugfixing":
        return read_jsonl(root / "data/test.jsonl")
    if domain == "codeclone":
        return [r for level in (1, 2, 3) for r in json.loads((root / f"data/level_{level}.json").read_text(encoding="utf-8"))]
    if domain == "verus":
        return json.loads((root / "manifest.json").read_text(encoding="utf-8"))["tasks"]
    raise ValueError("No public complexity source is configured")


def inspect(domain, root):
    rr = records(domain, root)
    id_key = "task_id" if domain == "bugfixing" else "id"
    if len({r[id_key] for r in rr}) != len(rr):
        raise ValueError("Duplicate task ids")
    counts = dict(sorted(Counter(str(r["level"]) for r in rr).items()))
    expected = registry()[domain]["expected_levels"]
    if counts != expected:
        raise ValueError(f"Coverage differs from pinned registry: {counts} != {expected}")
    result = {"domain": domain, "tasks": len(rr), "levels": counts, "scope": "schema/integrity only, not semantic re-verification"}
    if domain == "bugfixing":
        for r in rr:
            union = {t for b in r["bugs"] for t in b["FAIL_TO_PASS"]}
            if len(r["bugs"]) != r["level"] or r["num_bugs"] != r["level"] or not union or union != set(r["all_FAIL_TO_PASS"]):
                raise ValueError(f"Invalid bug/test union: {r['task_id']}")
        result.update(repositories=len({r["repo"] for r in rr}), bugs=sum(len(r["bugs"]) for r in rr))
    if domain == "codeclone":
        result["labels_by_level"] = {str(l): dict(Counter(r["label"] for r in rr if r["level"] == l)) for l in (1, 2, 3)}
        result["legacy_aggregation_markers_by_level"] = {str(l): sum(
            r["level"] == l and all("Object[] results" in r[s] and "return results;" in r[s]
                                    for s in ("side_a_code", "side_b_code")) for r in rr) for l in (1, 2, 3)}
        result["marker_note"] = "Text markers identify legacy aggregation wrappers; this is not a Java semantic proof."
    return result


def public_record(domain, row, root=None):
    """Allowlist fields. Gold patches, labels and references never enter model inputs."""
    # task_id is routing metadata, not prompt text. Do not reveal composition depth.
    identity = {"task_id": row.get("task_id", row.get("id"))}
    if domain == "codeclone":
        return {**identity, "side_a_code": row["side_a_code"], "side_b_code": row["side_b_code"]}
    if domain == "bugfixing":
        # Environment setup belongs to the trusted harness, not the model payload.
        return {**identity, "failing_tests": list(row["all_FAIL_TO_PASS"])}
    if domain == "verus":
        if root is None:
            raise ValueError("Verus source files must be downloaded first")
        source = safe_path(root, row["file"]).read_bytes()
        if hashlib.sha256(source).hexdigest() != row["sha256"]:
            raise ValueError("Verus input checksum mismatch")
        return {**identity, "source": source.decode("utf-8")}
    raise ValueError("Unknown domain")
