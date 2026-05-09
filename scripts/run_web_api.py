"""Run the KGTraceVis FastAPI web API for local development."""

from __future__ import annotations

import uvicorn


def main() -> None:
    """Start the FastAPI app with uvicorn."""
    uvicorn.run(
        "kgtracevis.service.api:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
