"""Reusable backend workflow orchestration."""

from typing import Any

__all__ = [
    "MaterialKGConstructionWorkflowConfig",
    "MaterialKGConstructionWorkflowResult",
    "run_material_kg_construction_workflow",
]


def __getattr__(name: str) -> Any:
    """Lazily expose workflow helpers without creating import cycles."""
    if name in __all__:
        from kgtracevis.workflows import material_kg_construction

        return getattr(material_kg_construction, name)
    raise AttributeError(name)
