"""Source audit graph envelope for extracted draft knowledge."""

from __future__ import annotations

from dataclasses import dataclass

from kgtracevis.kg_construction.alignment import AlignmentResult
from kgtracevis.kg_construction.draft import DraftKG, KGConstructionSource
from kgtracevis.kg_construction.parsers import (
    ParsedSourceContent,
    parsed_source_content_summary,
)


@dataclass(frozen=True)
class SourceAuditGraph:
    """Most provenance-rich graph layer retained for audit and drill-down."""

    sources: tuple[KGConstructionSource, ...]
    draft: DraftKG
    alignment: AlignmentResult
    parsed_sources: tuple[ParsedSourceContent, ...] = ()

    def manifest(self) -> dict[str, object]:
        """Return a JSON-friendly audit graph manifest."""
        sources_by_id = {source.source_id: source for source in self.sources}
        return {
            "artifact_type": "source_audit_graph_manifest_v1",
            "source_count": len(self.sources),
            "source_ids": [source.source_id for source in self.sources],
            "parsed_source_count": len(self.parsed_sources),
            "parsed_sources": [
                parsed_source_content_summary(
                    parsed,
                    source=sources_by_id.get(
                        parsed.source_id,
                        KGConstructionSource(
                            source_id=parsed.source_id,
                            source_type=parsed.source_type,
                            scenario=parsed.scenario,
                        ),
                    ),
                )
                for parsed in self.parsed_sources
            ],
            "draft_entity_count": len(self.draft.entities),
            "draft_relation_count": len(self.draft.relations),
            "alignment": self.alignment.manifest(),
        }
