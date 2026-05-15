"""Source audit graph envelope for extracted draft knowledge."""

from __future__ import annotations

from dataclasses import dataclass

from kgtracevis.kg_construction.alignment import AlignmentResult
from kgtracevis.kg_construction.draft import DraftKG, KGConstructionSource


@dataclass(frozen=True)
class SourceAuditGraph:
    """Most provenance-rich graph layer retained for audit and drill-down."""

    sources: tuple[KGConstructionSource, ...]
    draft: DraftKG
    alignment: AlignmentResult

    def manifest(self) -> dict[str, object]:
        """Return a JSON-friendly audit graph manifest."""
        return {
            "artifact_type": "source_audit_graph_manifest_v1",
            "source_count": len(self.sources),
            "source_ids": [source.source_id for source in self.sources],
            "draft_entity_count": len(self.draft.entities),
            "draft_relation_count": len(self.draft.relations),
            "alignment": self.alignment.manifest(),
        }
