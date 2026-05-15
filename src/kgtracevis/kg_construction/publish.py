"""Versioned publish manifest models for RCA-KG builds."""

from __future__ import annotations

from dataclasses import dataclass

from kgtracevis.kg_construction.sources import current_utc_iso


@dataclass(frozen=True)
class PublishManifest:
    """Versioned manifest prepared before runtime KG publication."""

    kg_build_id: str
    source_ids: tuple[str, ...]
    extractor_versions: dict[str, str]
    profile_version: str
    node_count: int
    edge_count: int
    review_policy: str
    published_at: str = ""

    def model_dump(self) -> dict[str, object]:
        """Return a JSON-friendly manifest payload."""
        return {
            "artifact_type": "kg_publish_manifest_v1",
            "kg_build_id": self.kg_build_id,
            "source_ids": list(self.source_ids),
            "extractor_versions": dict(self.extractor_versions),
            "profile_version": self.profile_version,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "review_policy": self.review_policy,
            "published_at": self.published_at or current_utc_iso(),
        }
