"""Package recovered historical inputs without claiming a full paper release."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    proof = ROOT / "outputs/historical-recovery/verus-original-historical-full-v2"
    original = ROOT / "outputs/canonical-originals/verus"
    repair = ROOT / "outputs/paper-original-repair"
    report = json.loads((proof / "report.json").read_text(encoding="utf-8"))
    repair_manifest = json.loads((repair / "manifest.json").read_text(encoding="utf-8"))
    assert repair_manifest["tasks"] == 568
    repair_inputs = [json.loads(line) for line in (repair / "model_inputs/bugfixing.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(repair_inputs) == 568
    assert report["full_bank"] and report["actual_verification_performed"]
    assert report["source_hashes_match"] == report["references_verified"] == report["admitted"] == 400
    rows = report["results"]
    assert len(rows) == len({row["task_id"] for row in rows}) == 400
    for row in rows:
        task_id = row["task_id"]
        assert Path(task_id).name == task_id and task_id not in {".", ".."}
        assert row["source_matches_hf"] and row["reference_verifies"]
        assert row["unfinished_well_formed"] and row["unfinished_fails_proof"]
        assert digest(proof / task_id / "task.rs") == row["original_sha256"]
        assert digest(proof / task_id / "reference.rs") == row["reference_sha256"]

    paper_paths = [ROOT.parent / "paper/sections/experiments.tex",
                   ROOT / "outputs/historical-recovery/overleaf-preprint/sections/experiments.tex"]
    metadata = {
        "policy": "preserve_existing_paper_results_recover_original_questions",
        "complete_paper_release": False,
        "historical_model_results_bound": False,
        "expected_paper_tasks": 1706,
        "recovered_input_tasks": 968,
        "recovered": {"bugfixing": 568, "verus": 400},
        "missing_original_questions": {"codeclone": 418, "bigo": 320},
        "verus_reference_proofs_verified": 400,
        "verus_platform": "windows_x86_64; historical Linux environment not replayed",
        "repair_full_container_replay": False,
        "paper_experiment_sections": [
            {"source": "submission" if index == 0 else "preprint", "sha256": digest(path)}
            for index, path in enumerate(paper_paths)
        ],
        "raw_receipt_note": "Raw structural_evidence.reference_verified records assembly-time status. Use top-level reference_verifies and actual execution receipts for subsequent verification. Raw files are unchanged.",
    }
    destination = ROOT / "outputs/canonical-originals/historical-partial-recovery.zip"
    files = []
    for directory, prefix in [(repair, "bugfixing"), (original, "verus/original-inputs"), (proof, "verus/verification")]:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                files.append((path, prefix + "/" + path.relative_to(directory).as_posix()))
    receipt = ROOT / "outputs/toolchains/verus-historical/receipt.json"
    files.append((receipt, "verus/toolchain-receipt.json"))
    files.append((ROOT / "docs/historical-recovery.md", "RECOVERY.md"))
    metadata["file_sha256"] = {name: digest(path) for path, name in files}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            archive.write(path, name)
        archive.writestr("recovery-manifest.json", json.dumps(metadata, indent=2) + "\n")
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(files) + 1
    destination.with_suffix(".zip.sha256").write_text(digest(destination) + "  " + destination.name + "\n", encoding="utf-8")
    (destination.parent / "historical-partial-recovery.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archive": str(destination), "input_tasks": 968, "missing_original_tasks": 738, "files": len(files)}, indent=2))


if __name__ == "__main__":
    main()
