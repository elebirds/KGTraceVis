"""Parser layer for turning sources into extractor input records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from kgtracevis.kg_construction.document_extraction import (
    SourceTextChunk,
    chunk_source_document,
    parse_source_material,
)
from kgtracevis.kg_construction.draft import KGConstructionSource
from kgtracevis.kg_construction.source_loader import load_structured_records

ParsedContentKind = Literal["rows", "text_chunks", "source_reference"]


@dataclass(frozen=True)
class ParsedSourceContent:
    """Extractor input produced from a registered source."""

    source_id: str
    source_type: str
    scenario: str
    kind: ParsedContentKind
    rows: tuple[dict[str, Any], ...] = ()
    chunks: tuple[SourceTextChunk, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_source_for_extraction(source: KGConstructionSource) -> ParsedSourceContent:
    """Parse a source into rows or chunks without emitting KG facts."""
    if source.source_type in {"structured_records", "manual_table", "tep_variable_mapping"}:
        if source.path is None:
            raise ValueError(f"{source.source_type} source requires path: {source.source_id}")
        return ParsedSourceContent(
            source_id=source.source_id,
            source_type=source.source_type,
            scenario=source.scenario,
            kind="rows",
            rows=tuple(load_structured_records(source.path)),
            metadata=dict(source.metadata),
        )
    if source.source_type in {"document", "markdown", "txt", "html", "pdf", "web_snapshot"}:
        document = parse_source_material(source)
        return ParsedSourceContent(
            source_id=source.source_id,
            source_type=source.source_type,
            scenario=source.scenario,
            kind="text_chunks",
            chunks=chunk_source_document(document),
            metadata=dict(source.metadata),
        )
    return ParsedSourceContent(
        source_id=source.source_id,
        source_type=source.source_type,
        scenario=source.scenario,
        kind="source_reference",
        metadata=dict(source.metadata),
    )
