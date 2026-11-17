"""Co-located repair: shared-file graph and a common snapshot candidate."""
from datetime import datetime
from .common import candidate

DIRECTED = False


def compatible(a, b):
    return bool(a.get("repo")) and a["repo"] == b.get("repo") and bool(
        set(a.get("modified_files", [])) & set(b.get("modified_files", [])))


def _fix_time(atom):
    value = datetime.fromisoformat(atom["fix_time"].replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("fix_time must include a time zone")
    return value


def plan(atoms):
    if len({a["repo"] for a in atoms}) != 1:
        raise ValueError("A repair group must use one repository")
    first = min(atoms, key=lambda a: (_fix_time(a), a["id"]))
    if not first.get("base_commit"):
        raise ValueError("Base commit missing")
    if any(not a.get("FAIL_TO_PASS") for a in atoms):
        raise ValueError("Every bug requires nonempty FAIL_TO_PASS")
    return candidate("bugfixing", atoms, repo=first["repo"], base_commit=first["base_commit"],
        all_FAIL_TO_PASS=sorted({t for a in atoms for t in a["FAIL_TO_PASS"]}),
        composition="checkout candidate base; apply all test patches; keep gold patches in verifier only",
        admission_required=["every bug's target tests fail at the common snapshot",
                            "all target tests pass after applying the joint gold patches"],
        warning="Fix-date ordering proposes a snapshot; it does not prove bug coexistence.")
