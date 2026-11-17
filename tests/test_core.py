import hashlib
import tempfile
import unittest
from pathlib import Path
from codewalk.graph import sample_groups
from codewalk.domains import bugfixing
from codewalk.data import public_record, safe_path, read_jsonl
from codewalk.evaluation import parse_label, grade_label, summarize
from examples.affine_domain import AffineDomain

ROOT = Path(__file__).resolve().parents[1]


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.atoms = [{"id": x, "source_id": x} for x in "abcd"]

    def test_directed_tail_prevents_branching(self):
        edges = {("a", "b"), ("a", "c")}
        with self.assertRaises(ValueError):
            sample_groups(self.atoms, lambda a,b: (a["id"],b["id"]) in edges,
                          level=3, count=1, seed=4, directed=True, max_attempts=50)

    def test_connected_not_clique(self):
        edges = {frozenset(pair) for pair in [("a", "b"), ("b", "c"), ("b", "d")]}
        groups = sample_groups(self.atoms, lambda a,b: frozenset((a["id"],b["id"])) in edges,
                               level=4, count=1, seed=4, directed=False)
        self.assertEqual([r["id"] for r in groups[0]], list("abcd"))

    def test_reproducible_under_input_reordering(self):
        kwargs = dict(level=3, count=2, seed=42, directed=True)
        self.assertEqual(sample_groups(self.atoms, lambda a,b: True, **kwargs),
                         sample_groups(self.atoms[::-1], lambda a,b: True, **kwargs))

    def test_undirected_dedup_exhaustion(self):
        with self.assertRaises(ValueError):
            sample_groups(self.atoms[:2], lambda a,b: True, level=2, count=2,
                          seed=0, directed=False, max_attempts=20)

    def test_source_cap(self):
        atoms = [{"id": x, "source_id": "same"} for x in "ab"]
        with self.assertRaises(ValueError):
            sample_groups(atoms, lambda a,b: True, level=2, count=1, seed=0,
                          directed=True, max_per_source=1, max_attempts=10)

    def test_duplicate_and_asymmetric_rejected(self):
        for atoms, edge in [([self.atoms[0]]*2, lambda a,b: True),
                            (self.atoms, lambda a,b: a["id"] < b["id"])]:
            with self.assertRaises(ValueError):
                sample_groups(atoms, edge, level=2, count=1, seed=0, directed=False)

    def test_repair_planning(self):
        atoms = read_jsonl(ROOT / "examples/repair_atoms.jsonl")
        plan = bugfixing.plan(atoms)
        self.assertFalse(plan["admitted"])
        self.assertEqual(plan["base_commit"], "synthetic-base-a")
        self.assertEqual(plan["all_FAIL_TO_PASS"], ["test_add", "test_empty", "test_parse"])
        self.assertFalse(bugfixing.compatible(atoms[0], {**atoms[1], "repo": "different/repo"}))


class MetricsTests(unittest.TestCase):
    tasks = [{"task_id": "a", "level": 1}, {"task_id": "b", "level": 2}]
    attempts = [{"task_id": t, "sample_idx": i, "status": s} for t, i, s in
                [("a",0,"success"),("a",1,"failure"),("b",0,"success"),("b",1,"success")]]

    def test_complete_scores(self):
        out = summarize(self.tasks, self.attempts, 2)["overall"]
        self.assertEqual(out["pass_at_1"], .75)
        self.assertEqual(out["pass_at_2_coverage"], 1)

    def test_partial_and_infra_are_not_complete(self):
        for rows in [self.attempts[:-1], self.attempts[:-1]+[{**self.attempts[-1], "status":"infra_error"}]]:
            out = summarize(self.tasks, rows, 2)
            self.assertFalse(out["overall"]["complete"])
            self.assertIsNone(out["overall"]["pass_at_1"])
            self.assertTrue(out["by_level"]["1"]["complete"])

    def test_duplicate_unknown_out_of_range_rejected(self):
        for rows in [self.attempts+[self.attempts[0]], [{"task_id":"other","sample_idx":0,"status":"success"}],
                     [{"task_id":"a","sample_idx":2,"status":"success"}]]:
            with self.assertRaises(ValueError):
                summarize(self.tasks, rows, 2)

    def test_label_parser(self):
        self.assertEqual(parse_label("codeclone", "because...\nVERDICT: 1"), "equivalent")
        self.assertIsNone(parse_label("codeclone", "VERDICT: 1\nVERDICT: 0"))
        self.assertIsNone(parse_label("codeclone", "VERDICT: 1\nVERDICT: 1"))
        self.assertIsNone(parse_label("bigo", "perhaps linear"))
        self.assertEqual(grade_label("bigo", " linear ", "linear")["status"], "success")
        with self.assertRaises(ValueError):
            grade_label("codeclone", "VERDICT: 1", "invented")


class IntegrityTests(unittest.TestCase):
    def test_answer_and_depth_exclusion(self):
        row = {"id":"x", "level":3,"label":"equivalent","gold_patch":"SECRET",
               "side_a_code":"A", "side_b_code":"B", "all_FAIL_TO_PASS":["test"]}
        for domain in ("bugfixing", "codeclone"):
            result = public_record(domain, row)
            self.assertNotIn("level", result)
            self.assertNotIn("label", result)
            self.assertNotIn("gold_patch", result)
            self.assertNotIn("SECRET", str(result))

    def test_paths_and_verus_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            for bad in ("../escape", "/absolute", "C:/escape", "a\\b"):
                with self.assertRaises(ValueError):
                    safe_path(folder, bad)
            content = b"synthetic source"
            Path(folder, "task.rs").write_bytes(content)
            row = {"id":"x", "level":1,"file":"task.rs", "sha256":hashlib.sha256(content).hexdigest()}
            self.assertEqual(public_record("verus", row, folder)["source"], content.decode())
            Path(folder, "task.rs").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                public_record("verus", row, folder)


class ExtensionTests(unittest.TestCase):
    def test_admission_and_exact_oracle(self):
        plugin = AffineDomain()
        task = plugin.compose([{"id":"a","a":2,"b":1}, {"id":"b","a":3,"b":4}])
        self.assertEqual(plugin.reference(task), [6,7])
        self.assertTrue(plugin.admit(task).admitted)
        self.assertFalse(plugin.grade(task, [6,8]))
        self.assertFalse(plugin.grade(task, [True,7]))
        self.assertNotIn("reference", plugin.public_task(task))

    def test_cancelled_chain_is_rejected(self):
        plugin = AffineDomain()
        task = plugin.compose([{"id":"a","a":1,"b":1}, {"id":"b","a":1,"b":-1}])
        self.assertFalse(plugin.admit(task).admitted)

    def test_wrong_reference_is_rejected(self):
        class Broken(AffineDomain):
            def reference(self, task):
                return [999,999]
        plugin = Broken()
        task = plugin.compose([{"id":"a","a":2,"b":1}])
        self.assertFalse(plugin.admit(task).admitted)


if __name__ == "__main__":
    unittest.main()
