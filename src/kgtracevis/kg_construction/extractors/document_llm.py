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
    SourceTextChunk,
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


class OfflineDocumentIEFixtureClient:
    """Document IE client that replays fixture payloads by chunk ID or index."""

    def __init__(self, fixture: Mapping[str, Any]) -> None:
        self.fixture = dict(fixture)

    def extract_candidates(
        self,
        chunk: SourceTextChunk,
        *,
        prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return the fixture payload for one parsed source chunk."""
        del prompt, response_schema
        payload = self._payload_for_chunk(chunk)
        if payload is None:
            return {"entities": [], "relations": []}
        return payload

    def _payload_for_chunk(self, chunk: SourceTextChunk) -> Mapping[str, Any] | None:
        if "entities" in self.fixture or "relations" in self.fixture:
            return self.fixture if chunk.index == 1 else None
        chunks = self.fixture.get("chunks")
        if isinstance(chunks, list):
            for item in chunks:
                if not isinstance(item, Mapping):
                    continue
                if str(item.get("chunk_id") or "") == chunk.chunk_id:
                    return item
                chunk_index = item.get("chunk_index", item.get("index"))
                if str(chunk_index or "") == str(chunk.index):
                    return item
        by_chunk_id = self.fixture.get("by_chunk_id")
        if isinstance(by_chunk_id, Mapping):
            item = by_chunk_id.get(chunk.chunk_id)
            if isinstance(item, Mapping):
                return item
        by_chunk_index = self.fixture.get("by_chunk_index")
        if isinstance(by_chunk_index, Mapping):
            item = by_chunk_index.get(str(chunk.index), by_chunk_index.get(chunk.index))
            if isinstance(item, Mapping):
                return item
        return None


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
