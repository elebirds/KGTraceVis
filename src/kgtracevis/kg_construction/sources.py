"""Source library records for RCA-oriented KG generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kgtracevis.kg_construction.draft import KGConstructionSource


@dataclass(frozen=True)
class SourceLibraryRecord:
    """Registered source material before parsing or extraction."""

    source_id: str
    source_type: str
    scenario: str
    path: Path | None = None
    url: str = ""
    text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    provenance_policy: str = "source_grounded_candidate"

    def to_construction_source(self) -> KGConstructionSource:
        """Convert the library record into the extractor source contract."""
        metadata = dict(self.metadata)
        if self.url:
            metadata["url"] = self.url
        metadata["provenance_policy"] = self.provenance_policy
        metadata["created_at"] = self.created_at or current_utc_iso()
        return KGConstructionSource(
            source_id=self.source_id,
            source_type=self.source_type,
            scenario=self.scenario,
            path=self.path,
            text=self.text,
            metadata=metadata,
        )


def current_utc_iso() -> str:
    """Return the current UTC timestamp in JSON-friendly ISO format."""
    return datetime.now(timezone.utc).isoformat()
