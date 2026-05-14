"""Service layer for API clients."""

from typing import Any

__all__ = ["create_app"]


def __getattr__(name: str) -> Any:
    """Import the FastAPI app factory only when callers request it."""
    if name == "create_app":
        from kgtracevis.service.api import create_app

        return create_app
    raise AttributeError(name)
