"""Document IE extractor boundary.

LLM-backed document extraction is intentionally isolated from the core pipeline:
it can emit source-grounded DraftKG candidates, but it cannot publish facts.
"""

from __future__ import annotations

from kgtracevis.kg_construction.document_extraction import (
    DocumentIEClient,
    extract_draft_kg_from_source_material,
)
from kgtracevis.kg_construction.draft import DraftKG, KGConstructionSource


class LLMDocumentIEExtractor:
    """Extractor wrapper for source-grounded document IE clients."""

    name = "llm_document_ie"
    version = "v1"
    supported_source_types: tuple[str, ...] = (
        "document",
        "markdown",
        "txt",
        "html",
        "pdf",
        "web_snapshot",
    )

    def __init__(self, client: DocumentIEClient) -> None:
        self.client = client

    def extract(self, source: KGConstructionSource) -> DraftKG:
        """Extract candidate DraftKG rows from one document source."""
        return extract_draft_kg_from_source_material(
            source,
            self.client,
            extractor_name=self.name,
            extractor_version=self.version,
            strict_grounding=True,
        )
