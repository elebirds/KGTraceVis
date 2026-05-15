"""Document IE extractor boundary.

LLM-backed document extraction is intentionally isolated from the core pipeline:
it can emit source-grounded DraftKG candidates, but it cannot publish facts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kgtracevis.kg_construction.document_extraction import (
    DocumentIEClient,
    OfflineDocumentIEFixtureClient,
    extract_draft_kg_from_chunks,
    extract_draft_kg_from_source_material,
)
from kgtracevis.kg_construction.draft import DraftKG, KGConstructionSource
from kgtracevis.kg_construction.parsers import ParsedSourceContent, parse_source_for_extraction

DOCUMENT_SOURCE_TYPES: tuple[str, ...] = (
    "document",
    "markdown",
    "txt",
    "html",
    "pdf",
    "web_snapshot",
)


class LLMDocumentIEExtractor:
    """Extractor wrapper for source-grounded document IE clients."""

    name = "llm_document_ie"
    version = "v1"
    supported_source_types: tuple[str, ...] = DOCUMENT_SOURCE_TYPES

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

    def extract_from_parsed(
        self,
        parsed: ParsedSourceContent,
        *,
        source: KGConstructionSource,
    ) -> DraftKG:
        """Extract candidate DraftKG rows from parsed document chunks."""
        del source
        if parsed.kind != "text_chunks":
            raise ValueError(f"document IE requires text chunk parser output: {parsed.source_id}")
        return extract_draft_kg_from_chunks(
            parsed.chunks,
            self.client,
            extractor_name=self.name,
            extractor_version=self.version,
            strict_grounding=True,
        )


class OfflineDocumentIEExtractor:
    """Replay a source-grounded document IE fixture without an LLM key."""

    name = "offline_document_ie"
    version = "v1"
    supported_source_types: tuple[str, ...] = DOCUMENT_SOURCE_TYPES

    def extract(self, source: KGConstructionSource) -> DraftKG:
        """Parse one document source and replay its IE fixture."""
        parsed = parse_source_for_extraction(source)
        return self.extract_from_parsed(parsed, source=source)

    def extract_from_parsed(
        self,
        parsed: ParsedSourceContent,
        *,
        source: KGConstructionSource,
    ) -> DraftKG:
        """Extract candidate DraftKG rows from parsed chunks using a fixture."""
        if parsed.kind != "text_chunks":
            raise ValueError(
                f"offline document IE requires text chunk parser output: {parsed.source_id}"
            )
        fixture = _load_offline_fixture(source)
        client = OfflineDocumentIEFixtureClient(fixture)
        return extract_draft_kg_from_chunks(
            parsed.chunks,
            client,
            extractor_name=self.name,
            extractor_version=self.version,
            default_confidence=0.5,
            strict_grounding=True,
        )


def _load_offline_fixture(source: KGConstructionSource) -> Mapping[str, Any]:
    inline = source.metadata.get("document_ie_payload") or source.metadata.get(
        "document_ie_fixture"
    )
    if isinstance(inline, Mapping):
        return inline
    fixture_path = source.metadata.get("document_ie_fixture_path")
    if fixture_path:
        payload = json.loads(Path(str(fixture_path)).read_text(encoding="utf-8"))
        if isinstance(payload, Mapping):
            return payload
        raise ValueError(f"document IE fixture must be a JSON object: {fixture_path}")
    raise ValueError(
        "offline document IE requires source.metadata['document_ie_payload'] "
        "or source.metadata['document_ie_fixture_path']"
    )
