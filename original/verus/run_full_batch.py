"""Run an isolated, resumable AutoVerus batch and the existing gold scorer.

python3 run_full_batch.py --config /absolute/config.json --output-dir results_new
Use --limit 1 for a smoke test in a separate output directory.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time


HERE = Path(__file__).resolve().parent
AV = HERE / "vps/autoverus"
PYTHON = HERE / "avenv/bin/python"
VERUS = HERE / "tools/verus-x86-linux/verus"
TASK_TIMEOUT = 4800
VERIFY_TIMEOUT = 600
VERIFIED = re.compile(r"verification results:+\s*\d+ verified,\s*0 errors\b")
API_BLOCK = re.compile(r"error code:\s*(?:401|402)\b|invalid api key|invalid_api_key|"
                       r"insufficient credits|credit limit", re.IGNORECASE)
STOP = threading.Event()
BLOCK_REASON = None
PROCESSES = set()
PROCESS_LOCK = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def stop(signum, frame):
    STOP.set()
    with PROCESS_LOCK:
        for process in list(PROCESSES):
            kill_group(process)


def run_process(command, cwd, env, log_prefix, timeout):
    global BLOCK_REASON
    with log_prefix.with_suffix(".stdout.log").open("w") as stdout, \
            log_prefix.with_suffix(".stderr.log").open("w") as stderr:
        with PROCESS_LOCK:
            if STOP.is_set():
                raise InterruptedError("batch interrupted")
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout,
                                       stderr=stderr, start_new_session=True)
            PROCESSES.add(process)
        try:
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    returncode = process.wait(timeout=min(10, remaining))
                except subprocess.TimeoutExpired:
                    returncode = None
                for suffix in ("stdout", "stderr"):
                    with log_prefix.with_suffix(f".{suffix}.log").open("rb") as log:
                        log.seek(max(0, log.seek(0, os.SEEK_END) - 65536))
                        tail = log.read().decode(errors="replace")
                    if API_BLOCK.search(tail):
                        BLOCK_REASON = "API authentication or credit limit; inspect task logs"
                        stop(None, None)
                if returncode is not None:
                    return returncode
        finally:
            # Also remove grandchildren left behind when their parent exits.
            kill_group(process)
            process.wait()
            with PROCESS_LOCK:
                PROCESSES.discard(process)


def run_task(item, args, env):
    if STOP.is_set():
        return None
    filename = item["file"]
    task_dir = args.output_dir / "task_runs" / Path(filename).stem
    task_dir.mkdir(parents=True, exist_ok=True)
    attempts = [p for p in task_dir.glob("attempt_*") if p.is_dir()]
    work = task_dir / f"attempt_{len(attempts) + 1:03d}"
    work.mkdir()
    # Lynette's cargo command uses ../utils relative to the task's cwd.
    utils_link = task_dir / "utils"
    if not utils_link.exists():
        utils_link.symlink_to(AV.parent / "utils", target_is_directory=True)
    output = args.output_dir / f"sol_{filename}"
    candidate = work / "solution.rs"
    task_env = dict(env, AV_USAGE_LOG=str(work / "usage.jsonl"))
    started = time.monotonic()
    record = {"file": filename, "level": item["level"], "verified": False,
              "started_at": now(), "attempt_dir": str(work)}
    write_json(work / "status.json", {"state": "running", **record})
    print(f"START {filename} {work.name}", flush=True)
    try:
        record["returncode"] = run_process(
            [str(PYTHON), str(AV / "main.py"), "--config", str(args.config),
             "--input", str(args.tasks_dir / filename), "--output", str(candidate),
             "--disable-safe"], work, task_env, work / "autoverus", TASK_TIMEOUT)
        if candidate.exists():
            candidate.replace(output)
            record["solution_sha256"] = digest(output)
            verify_code = run_process([str(VERUS), str(output)], work, task_env,
                                      work / "verifier", VERIFY_TIMEOUT)
            record["verifier_returncode"] = verify_code
            verifier_text = "\n".join(
                (work / f"verifier.{suffix}.log").read_text(errors="replace")
                for suffix in ("stdout", "stderr"))
            record["verified"] = verify_code == 0 and bool(VERIFIED.search(verifier_text))
            if not record["verified"]:
                record["error"] = "verification failed"
        else:
            record["error"] = "no output"
        if record["returncode"] != 0:
            record["verified"] = False
            record["error"] = f"autoverus exited {record['returncode']}"
    except subprocess.TimeoutExpired as error:
        record["error"] = "timeout" if error.timeout == TASK_TIMEOUT else "verifier timeout"
    except Exception as error:
        # Exception text from SDKs can contain credentials; logs carry diagnostics.
        record["error"] = type(error).__name__
    record["seconds"] = round(time.monotonic() - started, 2)
    record["finished_at"] = now()
    if STOP.is_set():
        write_json(work / "status.json", {
            "state": "blocked" if BLOCK_REASON else "interrupted", **record})
        return None
    write_json(task_dir / "result.json", record)
    write_json(work / "status.json", {"state": "complete", **record})
    return record


def summarize(rows):
    return {str(level): {
        "total": len(group),
        "verified": sum(bool(row.get("verified")) for row in group),
        "gold_ok": sum(bool(row.get("gold_ok")) for row in group),
        "errors": dict(Counter(row.get("error", "none") for row in group)),
        "gold_kinds": dict(Counter(row.get("gold_kind", "pending") for row in group)),
        "seconds": round(sum(row.get("seconds", 0) for row in group), 2),
    } for level in sorted({row["level"] for row in rows})
        for group in [[row for row in rows if row["level"] == level]]}


def run_batch(args):
    manifest = args.tasks_dir / "tasks.json"
    items = json.loads(manifest.read_text())
    if args.limit is not None:
        items = items[:args.limit]
    elif Counter(item["level"] for item in items) != {1: 100, 2: 100, 3: 100}:
        raise ValueError("full batch must contain 100 tasks at each of levels 1, 2, 3")
    if not items or len({item["file"] for item in items}) != len(items):
        raise ValueError("empty manifest or duplicate task filenames")
    for item in items:
        if Path(item["file"]).name != item["file"]:
            raise ValueError("task filename must be a basename")
    config = json.loads(args.config.read_text())
    for name in ("verus_path", "example_path", "lemma_path", "util_path"):
        if name in config and not Path(config[name]).is_absolute():
            raise ValueError(f"config {name} must be absolute for isolated working directories")
    identity = {
        "config_path": str(args.config), "config_sha256": digest(args.config),
        "tasks_dir": str(args.tasks_dir), "manifest_sha256": digest(manifest),
        "tasks_sha256": {item["file"]: digest(args.tasks_dir / item["file"]) for item in items},
        "source_sha256": {str(path.relative_to(HERE)): digest(path) for path in
                          sorted(AV.glob("*.py")) + [Path(__file__).resolve(), HERE / "rescore.py"]},
        "verifier_sha256": digest(VERUS), "task_timeout": TASK_TIMEOUT,
        "verifier_timeout": VERIFY_TIMEOUT, "av_loop_n": 1, "disable_safe": True,
        "max_token": config.get("max_token"), "limit": args.limit,
    }
    metadata_path = args.output_dir / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        if metadata["identity"] != identity:
            raise ValueError("resume identity changed; use a new output directory")
    else:
        if (args.output_dir / "results.json").exists():
            raise ValueError("cannot resume results without this runner's metadata")
        metadata = {"created_at": now(), "identity": identity,
                    "level_counts": dict(Counter(item["level"] for item in items))}
    metadata.update(last_started_at=now(), pid=os.getpid(), workers=args.workers)
    write_json(metadata_path, metadata)
    env = dict(os.environ)
    env["PATH"] = f"{VERUS.parent}:{Path.home() / '.cargo/bin'}:{env.get('PATH', '')}"
    env["AV_LOOP_N"] = "1"
    results_path = args.output_dir / "results.json"
    completed = {}
    for item in items:
        record_path = args.output_dir / "task_runs" / Path(item["file"]).stem / "result.json"
        if record_path.exists():
            record = json.loads(record_path.read_text())
            if record["file"] != item["file"] or record["level"] != item["level"]:
                raise ValueError(f"resume record mismatch: {item['file']}")
            if record.get("verified") and digest(args.output_dir / f"sol_{item['file']}") != record["solution_sha256"]:
                raise ValueError(f"resume solution changed: {item['file']}")
            completed[item["file"]] = record

    def checkpoint(state):
        rows = [completed[item["file"]] for item in items if item["file"] in completed]
        write_json(results_path, rows)
        write_json(args.output_dir / "status.json", {
            "state": "blocked" if BLOCK_REASON else state,
            "blocked_reason": BLOCK_REASON, "updated_at": now(), "pid": os.getpid(),
            "completed": len(rows), "total": len(items), "workers": args.workers})
        return rows

    checkpoint("running")
    print(f"BATCH total={len(items)} done={len(completed)} workers={args.workers}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_task, item, args, env)
                   for item in items if item["file"] not in completed]
        for future in as_completed(futures):
            record = future.result()
            if record is not None:
                completed[record["file"]] = record
                checkpoint("running")
                print(f"DONE {len(completed)}/{len(items)} {record['file']} "
                      f"verified={record['verified']} seconds={record['seconds']} "
                      f"error={record.get('error', '')}", flush=True)
    rows = checkpoint("interrupted" if STOP.is_set() else "scoring")
    if STOP.is_set():
        return 130
    # Let the unchanged scorer write in staging, then publish its result atomically.
    staging = args.output_dir / "gold_scoring"
    staging.mkdir(exist_ok=True)
    write_json(staging / "results.json", rows)
    for row in rows:
        if row.get("verified"):
            link = staging / f"sol_{row['file']}"
            if not link.exists():
                link.symlink_to(args.output_dir / link.name)
    timeout = (math.ceil(sum(bool(row.get("verified")) for row in rows) / 12) + 1) * 900 + 60
    returncode = run_process(
        [str(PYTHON), str(HERE / "rescore.py"), "full_batch", str(args.tasks_dir), str(staging)],
        staging, env, staging / "scorer", timeout)
    if STOP.is_set():
        checkpoint("interrupted")
        return 130
    if returncode != 0:
        raise RuntimeError(f"gold scoring exited {returncode}; inspect gold_scoring logs")
    gold = json.loads((staging / "results_gold.json").read_text())
    if [row["file"] for row in gold] != [row["file"] for row in rows]:
        raise ValueError("gold scorer output does not match batch")
    write_json(args.output_dir / "results_gold.json", gold)
    summary = summarize(gold)
    write_json(args.output_dir / "summary.json", summary)
    checkpoint("complete")
    print("ALL DONE " + json.dumps(summary, sort_keys=True), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tasks-dir", type=Path, default=HERE / "tasks")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if not args.config.is_absolute():
        parser.error("--config must be an absolute path")
    if args.workers < 1 or (args.limit is not None and args.limit < 1):
        parser.error("workers and limit must be positive")
    args.config = args.config.resolve()
    args.output_dir = args.output_dir.resolve()
    args.tasks_dir = args.tasks_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / ".runner.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("another runner holds this output directory")
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            return run_batch(args)
        except Exception as error:
            write_json(args.output_dir / "status.json", {
                "state": "blocked" if BLOCK_REASON else ("interrupted" if STOP.is_set() else "failed"),
                "blocked_reason": BLOCK_REASON,
                "updated_at": now(), "pid": os.getpid(), "error": type(error).__name__})
            raise


if __name__ == "__main__":
    raise SystemExit(main())
