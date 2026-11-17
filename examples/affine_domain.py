"""Complete tutorial plugin: exact composition of integer affine transformations.

This toy's question asks for coefficients A,B of the composite A*x+B. No benchmark
language or missing historical source is simulated. Python integers are unbounded.
"""
import json
from codewalk.graph import sample_groups
from codewalk.plugins import Admission


class AffineDomain:
    name = "affine_tutorial"
    directed = True

    def extract(self, source):
        atoms = []
        for row in source:
            if (not isinstance(row.get("id"), str) or not row["id"] or
                    any(type(row.get(k)) is not int for k in ("a", "b"))):
                raise ValueError("Expected id and integer a,b")
            atoms.append({"id": row["id"], "source_id": row["id"], "a": row["a"], "b": row["b"]})
        if len({r["id"] for r in atoms}) != len(atoms):
            raise ValueError("Duplicate atom")
        return atoms

    def compatible(self, left, right):
        return left["id"] != right["id"]  # integer -> integer

    def compose(self, atoms):
        if not atoms:
            raise ValueError("Empty composition")
        validated = self.extract(atoms)
        return {"atoms": validated, "question": "Apply these maps in order; return integer coefficients [A, B] of A*x+B."}

    def reference(self, task):
        a, b = 1, 0
        for atom in task["atoms"]:
            a, b = atom["a"] * a, atom["a"] * b + atom["b"]
        return [a, b]

    def grade(self, task, answer):
        if not isinstance(answer, list) or len(answer) != 2 or any(type(x) is not int for x in answer):
            return False
        # Independent oracle: every composition is affine, so agreement at 0 and 1
        # is an exact proof of coefficient equality in this restricted domain.
        for x in (0, 1):
            expected = x
            for atom in task["atoms"]:
                expected = atom["a"] * expected + atom["b"]
            if answer[0] * x + answer[1] != expected:
                return False
        return True

    def admit(self, task):
        nontrivial = all((r["a"], r["b"]) != (1, 0) for r in task["atoms"])
        unfinished_fails = not self.grade(task, [1, 0])
        reference_passes = self.grade(task, self.reference(task))
        return Admission(nontrivial and unfinished_fails, reference_passes,
                         {"oracle": "affine equality at 0 and 1", "unfinished_fails": unfinished_fails,
                          "reference_passes": reference_passes})

    def public_task(self, task):
        return {"question": task["question"], "maps": [{"a": r["a"], "b": r["b"]} for r in task["atoms"]]}


def main():
    plugin = AffineDomain()
    atoms = plugin.extract([{"id": "scale", "a": 2, "b": 0}, {"id": "shift", "a": 1, "b": 3}])
    group = sample_groups(atoms, plugin.compatible, level=2, count=1, seed=42, directed=True)[0]
    task = plugin.compose(group)
    admission = plugin.admit(task)
    if not admission.admitted:
        raise RuntimeError("Tutorial candidate rejected")
    print(json.dumps({"public_task": plugin.public_task(task), "admitted": admission.admitted,
                      "evidence": admission.evidence, "reference_grade": plugin.grade(task, plugin.reference(task))}, indent=2))


if __name__ == "__main__":
    main()
