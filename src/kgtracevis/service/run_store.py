"""Runtime run-store provider for service helpers."""

from __future__ import annotations

import uuid
from typing import Any

_RUN_STORE_OVERRIDE: Any | None = None


def configure_run_store_for_testing(store: Any | None) -> None:
    """Override the runtime run store in tests."""
    global _RUN_STORE_OVERRIDE
    _RUN_STORE_OVERRIDE = store


def build_run_id() -> str:
    """Return a public UUID run identifier."""
    return str(uuid.uuid4())


def run_store() -> Any:
    """Return the configured runtime run store."""
    if _RUN_STORE_OVERRIDE is not None:
        return _RUN_STORE_OVERRIDE
    from kgtracevis.service.postgres_run_store import PostgresRunStore

    return PostgresRunStore.from_environment()
