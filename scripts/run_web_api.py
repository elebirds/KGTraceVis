"""Run the KGTraceVis FastAPI web API for local development."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Start the FastAPI app with uvicorn."""
    host = os.environ.get("KGTRACE_API_HOST", "127.0.0.1")
    port = int(os.environ.get("KGTRACE_API_PORT", "8081"))
    uvicorn.run(
        "kgtracevis.service.api:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
