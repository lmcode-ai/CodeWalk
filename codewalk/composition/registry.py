"""Register a backend once here; generate CLI choices follow this registry."""
from .python_cost import ComplexityBackend
from .java_clone import CloneBackend
from .repair import RepairBackend
from .rust_proof import VerusBackend

BACKENDS = {cls.name:cls for cls in (ComplexityBackend,CloneBackend,RepairBackend,VerusBackend)}
