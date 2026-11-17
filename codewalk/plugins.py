"""Legacy tutorial protocol. New generator plugins extend composition.base.Backend."""
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Admission:
    atom_gate: bool
    reference_gate: bool
    evidence: dict[str, Any]

    @property
    def admitted(self):
        return self.atom_gate is True and self.reference_gate is True and bool(self.evidence)


class DomainPlugin(Protocol):
    name: str
    directed: bool

    def extract(self, source: Any) -> list[dict]: ...
    def compatible(self, left: dict, right: dict) -> bool: ...
    def compose(self, atoms: list[dict]) -> dict: ...
    def reference(self, task: dict) -> Any: ...
    def admit(self, task: dict) -> Admission: ...
    def public_task(self, task: dict) -> dict: ...
    def grade(self, task: dict, answer: Any) -> bool: ...
