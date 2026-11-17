"""Archive exactly the staged Git index; works before the first commit."""
import hashlib
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not (ROOT / ".git").is_dir():
        raise SystemExit("Run from the independent prepared Git repository")
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    names = [name for name in names if name]
    if not names:
        raise SystemExit("Stage release files first")
    destination = ROOT / "outputs/codewalk-release-preparation.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            if any(x in {"data", "outputs", "private", ".git", ".venv"} or x.startswith(".env") for x in Path(name).parts):
                raise ValueError(f"Excluded file staged: {name}")
            content = subprocess.check_output(["git", "show", ":" + name], cwd=ROOT)
            entry = zipfile.ZipInfo("codewalk-release/" + name, date_time=(2026, 11, 6, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
    print(f"Archived {len(names)} staged files: {destination.name}")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    main()
