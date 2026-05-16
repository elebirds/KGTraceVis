"""Parser layer for turning sources into extractor input records."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from kgtracevis.kg_construction.document_extraction import (
    SourceTextChunk,
    chunk_source_document,
    parse_source_material,
)
from kgtracevis.kg_construction.draft import KGConstructionSource
from kgtracevis.kg_construction.source_loader import (
    load_structured_record_text,
    load_structured_records,
)

ParsedContentKind = Literal["rows", "text_chunks", "source_reference"]


@dataclass(frozen=True)
class ParsedSourceContent:
    """Extractor input produced from a registered source."""

    source_id: str
    source_type: str
    scenario: str
    kind: ParsedContentKind
    parser_kind: str
    rows: tuple[dict[str, Any], ...] = ()
    chunks: tuple[SourceTextChunk, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    parser_metadata: dict[str, Any] = field(default_factory=dict)
    source_reference: str = ""


ParserOutput = ParsedSourceContent


def parsed_source_content_summary(
    parsed: ParsedSourceContent,
    *,
    source: KGConstructionSource,
) -> dict[str, Any]:
    """Return an audit-safe parsed source summary without row values or text."""
    return {
        "source_id": parsed.source_id,
        "source_type": parsed.source_type,
        "scenario": parsed.scenario,
        "kind": parsed.kind,
        "parser_kind": parsed.parser_kind,
        "row_count": len(parsed.rows),
        "chunk_count": len(parsed.chunks),
        "source_reference": parsed.source_reference or _source_reference(source),
        "safe_source": _safe_source_payload(source),
        "parser_metadata": _jsonable(parsed.parser_metadata),
    }


def parse_source_for_extraction(source: KGConstructionSource) -> ParsedSourceContent:
    """Parse a source into rows or chunks without emitting KG facts."""
    if source.source_type in {
        "structured_records",
        "manual_table",
        "mvtec_ad_catalog",
        "tep_variable_mapping",
    }:
        if source.path is not None:
            rows = tuple(load_structured_records(source.path))
            path = str(source.path)
        elif source.text is not None:
            source_format = str(source.metadata.get("source_format") or "jsonl")
            rows = tuple(
                load_structured_record_text(source.text, source_format=source_format)
            )
            path = ""
        else:
            raise ValueError(
                f"{source.source_type} source requires path or text: {source.source_id}"
            )
        return ParsedSourceContent(
            source_id=source.source_id,
            source_type=source.source_type,
            scenario=source.scenario,
            kind="rows",
            parser_kind=source.source_type,
            rows=rows,
            metadata=dict(source.metadata),
            parser_metadata={
                "columns": _record_columns(rows),
                "path": path,
                "source_format": str(source.metadata.get("source_format") or ""),
            },
            source_reference=_source_reference(source),
        )
    if source.source_type in {"document", "markdown", "txt", "html", "pdf", "web_snapshot"}:
        document = parse_source_material(source)
        chunks = chunk_source_document(document)
        return ParsedSourceContent(
            source_id=source.source_id,
            source_type=source.source_type,
            scenario=source.scenario,
            kind="text_chunks",
            parser_kind=document.parser,
            chunks=chunks,
            metadata=dict(source.metadata),
            parser_metadata={
                "chunk_ids": [chunk.chunk_id for chunk in chunks],
                "chunk_char_ranges": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                    }
                    for chunk in chunks
                ],
                "path": str(document.path) if document.path is not None else "",
            },
            source_reference=_source_reference(source),
        )
    return ParsedSourceContent(
        source_id=source.source_id,
        source_type=source.source_type,
        scenario=source.scenario,
        kind="source_reference",
        parser_kind="source_reference",
        metadata=dict(source.metadata),
        parser_metadata=_source_reference_metadata(source),
        source_reference=_source_reference(source),
    )


def _record_columns(rows: tuple[dict[str, Any], ...]) -> list[str]:
    columns: set[str] = set()
    for row in rows:
        columns.update(str(key) for key in row)
    return sorted(columns)


def _source_reference(source: KGConstructionSource) -> str:
    explicit = source.metadata.get("source_reference")
    if explicit:
        return str(explicit)
    if source.path is not None:
        return str(source.path)
    path_parts = [
        f"{key}={value}"
        for key, value in sorted(source.metadata.items())
        if _is_path_key(str(key)) and value
    ]
    return "; ".join(path_parts) if path_parts else source.source_id


def _source_reference_metadata(source: KGConstructionSource) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    path_values = {
        str(key): str(value)
        for key, value in source.metadata.items()
        if _is_path_key(str(key)) and value
    }
    if path_values:
        metadata["paths"] = path_values
    return metadata


def _safe_source_payload(source: KGConstructionSource) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_id": source.source_id,
        "source_type": source.source_type,
        "scenario": source.scenario,
        "has_text": source.text is not None,
    }
    if source.path is not None:
        payload["path"] = str(source.path)
        payload["path_name"] = source.path.name
        payload["path_kind"] = _path_kind(source.path)
    metadata_paths = {
        str(key): str(value)
        for key, value in source.metadata.items()
        if _is_path_key(str(key)) and value
    }
    if metadata_paths:
        payload["metadata_paths"] = metadata_paths
    if source.metadata.get("source_reference"):
        payload["source_reference"] = str(source.metadata["source_reference"])
    return payload


def _path_kind(path: Path) -> str:
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "path"


def _is_path_key(key: str) -> bool:
    return key == "path" or key.endswith("_path")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
