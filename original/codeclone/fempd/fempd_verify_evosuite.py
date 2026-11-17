"""
Option (b): reuse FEMPD's own EvoSuite-generated test suites instead of generating
fresh type-driven tests. For pair (L, R): take L's own Target_ESTest (which encodes
L's actual behavior via hardcoded assertions) and run it against R's code wrapped as
the `Target` class (dataset convention: renamed to `__target__`); then do the reverse
(R's tests against L's code). VERIFIED only if both directions pass with zero
failures; MISLABELED if either direction has any test failure; UNVERIFIABLE if
either side lacks EvoSuite tests, isn't compilable, or the harness itself fails
(missing runtime deps, JVM/module errors unrelated to the code under test).

Requires: ./lib/evosuite-standalone-runtime-1.0.6.jar, junit-4.13.2.jar,
hamcrest-core-1.3.jar (see fempd/lib/), downloaded from Maven Central.
"""
import json
import os
import re
import subprocess
import sys
import time

from fempd_common import connect, load_verifiedpairs, load_method

WORK_DIR = "fempd_verify_work_evosuite"
LIB_DIR = "lib"
COMPILE_TIMEOUT = 30
RUN_TIMEOUT = 60

JVM_OPENS = [
    "--add-opens", "java.base/java.lang=ALL-UNNAMED",
    "--add-opens", "java.base/java.lang.reflect=ALL-UNNAMED",
    "--add-opens", "java.base/java.lang.invoke=ALL-UNNAMED",
    "--add-opens", "java.base/java.util=ALL-UNNAMED",
    "--add-opens", "java.base/java.util.concurrent=ALL-UNNAMED",
    "--add-opens", "java.base/java.io=ALL-UNNAMED",
    "--add-opens", "java.base/java.net=ALL-UNNAMED",
    "--add-opens", "java.base/java.nio=ALL-UNNAMED",
    "--add-opens", "java.base/java.nio.file=ALL-UNNAMED",
    "--add-opens", "java.base/java.text=ALL-UNNAMED",
    "--add-opens", "java.base/java.time=ALL-UNNAMED",
    "--add-opens", "java.base/java.security=ALL-UNNAMED",
    "--add-opens", "java.base/java.util.regex=ALL-UNNAMED",
    "--add-opens", "java.desktop/java.awt=ALL-UNNAMED",
    "--add-opens", "java.desktop/javax.swing=ALL-UNNAMED",
    "--add-opens", "java.desktop/sun.awt=ALL-UNNAMED",
    "--add-exports", "java.base/sun.net.util=ALL-UNNAMED",
    "--add-opens", "java.base/sun.net.util=ALL-UNNAMED",
]


def classpath(extra_dir):
    jars = [
        os.path.join(LIB_DIR, "evosuite-standalone-runtime-1.0.6.jar"),
        os.path.join(LIB_DIR, "junit-4.13.2.jar"),
        os.path.join(LIB_DIR, "hamcrest-core-1.3.jar"),
    ]
    return extra_dir + ":" + ":".join(jars)


COMMON_IMPORTS = """import java.util.*;
import java.security.*;
import java.math.*;
import java.text.*;
import java.io.*;
import java.nio.charset.*;
"""


def rename_to_target(rtext):
    m = re.search(r"(\w[\w<>\[\],\s]*?)\s+(\w+)(\s*\()", rtext)
    if not m:
        return None
    return rtext[:m.start()] + m.group(1) + " __target__" + m.group(3) + rtext[m.end():]


def run_direction(code_method_id, code_rtext, test_owner_id, target_estest, scaffolding, tag):
    """Wrap code_rtext as Target, compile against test_owner's Target_ESTest +
    scaffolding, run. Returns dict with status/passed/failed/total."""
    wrapped = rename_to_target(code_rtext)
    if wrapped is None:
        return {"status": "unverifiable", "reason": "rename_failed"}

    target_src = f"{COMMON_IMPORTS}\npublic class Target {{\n{wrapped}\n}}\n"
    attempt_dir = os.path.join(WORK_DIR, tag)
    os.makedirs(attempt_dir, exist_ok=True)
    with open(os.path.join(attempt_dir, "Target.java"), "w") as f:
        f.write(target_src)
    with open(os.path.join(attempt_dir, "Target_ESTest.java"), "w") as f:
        f.write(target_estest)
    with open(os.path.join(attempt_dir, "Target_ESTest_scaffolding.java"), "w") as f:
        f.write(scaffolding)

    cp = classpath(attempt_dir)
    try:
        compile_proc = subprocess.run(
            ["javac", "--release", "8", "-cp", cp, "-d", attempt_dir,
             os.path.join(attempt_dir, "Target.java"),
             os.path.join(attempt_dir, "Target_ESTest_scaffolding.java"),
             os.path.join(attempt_dir, "Target_ESTest.java")],
            capture_output=True, text=True, timeout=COMPILE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"status": "unverifiable", "reason": "compile_timeout"}
    if compile_proc.returncode != 0:
        return {"status": "unverifiable", "reason": f"compile_error:{compile_proc.stderr.strip()[:300]}"}

    try:
        run_proc = subprocess.run(
            ["java", *JVM_OPENS, "-cp", cp, "org.junit.runner.JUnitCore", "Target_ESTest"],
            capture_output=True, text=True, timeout=RUN_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"status": "unverifiable", "reason": "run_timeout"}

    out = run_proc.stdout + run_proc.stderr
    m = re.search(r"OK \((\d+) tests?\)", out)
    if m:
        return {"status": "ok", "total": int(m.group(1)), "failed": 0}
    m = re.search(r"Tests run: (\d+),\s*Failures: (\d+)", out)
    if m:
        total, failed = int(m.group(1)), int(m.group(2))
        if total == 0:
            return {"status": "unverifiable", "reason": f"harness_error:{out[-300:]}"}
        return {"status": "ok", "total": total, "failed": failed}
    return {"status": "unverifiable", "reason": f"unparseable_output:{out[-300:]}"}


def verify_pair_evosuite(left_id, right_id, m_left, m_right):
    if m_left is None or m_right is None:
        return {"verdict": "UNVERIFIABLE", "reason": "method_missing"}
    for m in (m_left, m_right):
        if m["compilable"] != 1:
            return {"verdict": "UNVERIFIABLE", "reason": f"not_compilable:{m['compilable']}"}
        if not m["target_estest"] or not m["scaffolding"]:
            return {"verdict": "UNVERIFIABLE", "reason": "no_evosuite_tests"}

    # direction 1: right's code against left's tests
    d1 = run_direction(right_id, m_right["rtext"], left_id, m_left["target_estest"],
                        m_left["scaffolding"], f"{left_id}_{right_id}_Ltests_on_R")
    # direction 2: left's code against right's tests
    d2 = run_direction(left_id, m_left["rtext"], right_id, m_right["target_estest"],
                        m_right["scaffolding"], f"{left_id}_{right_id}_Rtests_on_L")

    if d1["status"] != "ok" or d2["status"] != "ok":
        return {
            "verdict": "UNVERIFIABLE",
            "reason_d1": d1.get("reason") if d1["status"] != "ok" else None,
            "reason_d2": d2.get("reason") if d2["status"] != "ok" else None,
        }

    if d1["failed"] == 0 and d2["failed"] == 0:
        verdict = "VERIFIED"
    else:
        verdict = "MISLABELED"
    return {
        "verdict": verdict,
        "d1_total": d1["total"], "d1_failed": d1["failed"],
        "d2_total": d2["total"], "d2_failed": d2["failed"],
    }


def _worker(e):
    # each worker opens its own connection -- sqlite3 connections aren't
    # shared safely across threads
    conn = connect()
    m_left = load_method(conn, e["left"], cache={})
    m_right = load_method(conn, e["right"], cache={})
    res = verify_pair_evosuite(e["left"], e["right"], m_left, m_right)
    return {"pairid": e["pairid"], "left": e["left"], "right": e["right"],
            "consensus": e["consensus"], **res}


def main():
    import concurrent.futures

    conn = connect()
    edges = load_verifiedpairs(conn)
    edges.sort(key=lambda e: -e["consensus"])

    start = time.time()
    n_workers = 8
    n_done = 0
    with open("fempd_evosuite_results.jsonl", "w") as out, \
         concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = [pool.submit(_worker, e) for e in edges]
        for fut in concurrent.futures.as_completed(futures):
            row = fut.result()
            out.write(json.dumps(row) + "\n")
            out.flush()
            n_done += 1
            if n_done % 50 == 0:
                elapsed = time.time() - start
                print(f"  [{n_done}/{len(edges)}] elapsed={elapsed:.0f}s", file=sys.stderr)

    print(f"done: {len(edges)} pairs in {time.time()-start:.0f}s")


if __name__ == "__main__":
    main()
