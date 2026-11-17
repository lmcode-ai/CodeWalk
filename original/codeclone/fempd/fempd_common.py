"""Shared FEMPD SQLite access helpers."""
import sqlite3

DB_PATH = "ijadataset.db"


def connect():
    conn = sqlite3.connect(DB_PATH)
    # some text columns (e.g. verifiedpairs.reason) contain invalid UTF-8 byte
    # sequences that crash sqlite3's default str auto-decoding -- return raw
    # bytes everywhere and decode manually with errors="replace" downstream.
    conn.text_factory = bytes
    return conn


def _dec(b):
    return b.decode("utf-8", errors="replace") if isinstance(b, bytes) else b


def load_verifiedpairs(conn):
    """Return list of dicts: pairid, left, right, consensus, reason,
    reviewera/b/c -- joined against pairs for the method ids."""
    cur = conn.cursor()
    cur.execute("""
        SELECT vp.pairid, p.leftMethodID, p.rightMethodID, vp.consensus,
               vp.reviewera, vp.reviewerb, vp.reviewerc, vp.reason
        FROM verifiedpairs vp
        JOIN pairs p ON vp.pairid = p.id
    """)
    rows = []
    for pairid, left, right, consensus, ra, rb, rc, reason in cur.fetchall():
        rows.append({
            "pairid": pairid, "left": left, "right": right, "consensus": consensus,
            "reviewera": ra, "reviewerb": rb, "reviewerc": rc,
            "reason": _dec(reason),
        })
    return rows


def load_method(conn, method_id, cache={}):
    if method_id in cache:
        return cache[method_id]
    cur = conn.cursor()
    cur.execute("""
        SELECT rtext, compilable, tests, Target_ESTest, Target_ESTest_scaffolding, name
        FROM methods WHERE id = ?
    """, (method_id,))
    row = cur.fetchone()
    if row is None:
        cache[method_id] = None
        return None
    rtext, compilable, tests, target_estest, scaffolding, name = row
    result = {
        "rtext": _dec(rtext),
        "compilable": compilable,
        "tests": tests,
        "target_estest": _dec(target_estest),
        "scaffolding": _dec(scaffolding),
        "name": _dec(name),
    }
    cache[method_id] = result
    return result
