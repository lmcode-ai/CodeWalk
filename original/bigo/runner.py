"""
runner.py -- run a Python program on some stdin text, with a cache.

Every run is  `python -c <source>`  with <stdin text> fed to standard input.
Results are saved in an SQLite file keyed by a hash of (source, stdin), so running the
pipeline again only executes programs it has not seen before.

Snippets from the dataset are executed for real: use a sandbox if you do not trust the data.
"""
import hashlib
import sqlite3
import subprocess
import sys
import tempfile
import threading

TIMEOUT = 3.0          # seconds allowed per run
MAX_OUTPUT = 2000      # a run that prints more characters than this counts as a failure

# Snippets run inside an empty temporary folder, so stray file writes do not land in your files.
_WORK_DIR = tempfile.mkdtemp(prefix="chains_run_")


class Cache:
    """Remembers (succeeded, stdout) for every (source, stdin) pair. Safe to use from many threads."""

    def __init__(self, path=None):
        self.memory = {}
        self.lock = threading.Lock()
        self.db = None
        self.unsaved = 0
        if path:
            self.db = sqlite3.connect(path, check_same_thread=False)
            self.db.execute("CREATE TABLE IF NOT EXISTS runs (k TEXT PRIMARY KEY, ok INTEGER, out TEXT)")
            for key, ok, out in self.db.execute("SELECT k, ok, out FROM runs"):
                self.memory[key] = (bool(ok), out)

    def get(self, key):
        return self.memory.get(key)

    def put(self, key, result):
        with self.lock:
            self.memory[key] = result
            if self.db:
                self.db.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?)", (key, int(result[0]), result[1]))
                self.unsaved += 1
                if self.unsaved >= 500:          # write to disk every 500 new results
                    self.save()

    def save(self):
        if self.db:
            self.db.commit()
            self.unsaved = 0


cache = Cache()        # in-memory only until open_cache() is called


def open_cache(path):
    """Use (and fill) the on-disk cache at `path`."""
    global cache
    cache = Cache(path)


def run(source, stdin_text, timeout=None):
    """Run `source` with `stdin_text` as its input. Returns (succeeded, stdout).

    A run succeeds if it exits normally within the time limit and prints at most MAX_OUTPUT characters.
    """
    key = hashlib.sha1((source + "\x00" + stdin_text).encode("utf-8", "replace")).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        proc = subprocess.run([sys.executable, "-W", "ignore", "-c", source], input=stdin_text,
                              capture_output=True, text=True, errors="replace",
                              timeout=timeout or TIMEOUT, cwd=_WORK_DIR)
        ok = proc.returncode == 0 and len(proc.stdout) <= MAX_OUTPUT
        result = (ok, proc.stdout if ok else "")    # the output of a failed run is never used
    except Exception:                        # timed out, or the OS refused to start it
        result = (False, "")
    cache.put(key, result)
    return result


# ------------------------------------------------------------------ reading outputs
def as_int(text):
    """The output as an integer if it is exactly one integer, else None."""
    parts = text.split()
    if len(parts) != 1:
        return None
    try:
        return int(parts[0])
    except ValueError:
        return None


def tidy(text):
    """Output with spacing normalised: single spaces inside lines, no blank edges."""
    return "\n".join(" ".join(line.split()) for line in text.strip().splitlines())


def same_output(a, b):
    """Do two outputs mean the same thing? Words must match; numbers may differ by tiny float error."""
    words_a, words_b = a.split(), b.split()
    if len(words_a) != len(words_b):
        return False
    for x, y in zip(words_a, words_b):
        if x == y:
            continue
        try:
            fx, fy = float(x), float(y)
        except ValueError:
            return False                     # different words
        if "." not in x + y and "e" not in (x + y).lower():
            return False                     # two different integers
        if abs(fx - fy) > 1e-4 * max(1, abs(fx), abs(fy)):
            return False
    return True
