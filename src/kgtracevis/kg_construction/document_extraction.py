"""Document parsing, chunking, and LLM-assisted draft KG extraction."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha1
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kgtracevis.kg_construction.draft import (
    DraftEntity,
    DraftKG,
    DraftRelation,
    KGConstructionSource,
)
from kgtracevis.kg_construction.triple_cleaner import VALID_SCENARIOS

DEFAULT_DOCUMENT_CHUNK_MAX_CHARS = 2_000
DEFAULT_DOCUMENT_CHUNK_OVERLAP_CHARS = 200
DEFAULT_DOCUMENT_EXTRACTOR_NAME = "llm_document_ie"
DEFAULT_DOCUMENT_EXTRACTOR_VERSION = "v1"
DEFAULT_DOCUMENT_IE_PROMPT_VERSION = "document_ie_prompt_v1"

ALLOWED_DOCUMENT_IE_RELATIONS = frozenset(
    {
        "AFFECTS",
        "AFFECTS_VARIABLE",
        "ALIGNS_TO",
        "ASSOCIATED_WITH_EVENT",
        "BELONGS_TO",
        "BELONGS_TO_UNIT",
        "CAUSES",
        "HAS_ANOMALY",
        "HAS_LOCATION",
        "HAS_MORPHOLOGY",
        "HAS_PLAUSIBLE_CAUSE",
        "HAS_SPATIAL_SIGNATURE",
        "INDICATES",
        "MEASURED_IN",
        "OCCURS_ON",
        "SUGGESTS_PLAUSIBLE_MECHANISM",
        "SUGGESTS_ROOT_CAUSE",
    }
)

DOCUMENT_IE_RELATION_ALIASES = {
    "AFFECTS": "AFFECTS",
    "AFFECTS_VARIABLE": "AFFECTS_VARIABLE",
    "ALIGNMENT": "ALIGNS_TO",
    "ALIGNS_TO": "ALIGNS_TO",
    "ASSOCIATED_WITH_EVENT": "ASSOCIATED_WITH_EVENT",
    "BELONGS_TO": "BELONGS_TO",
    "BELONGS_TO_UNIT": "BELONGS_TO_UNIT",
    "CAUSE": "CAUSES",
    "CAUSED_BY": "HAS_PLAUSIBLE_CAUSE",
    "CAUSES": "CAUSES",
    "HAS_ANOMALY": "HAS_ANOMALY",
    "HAS_LOCATION": "HAS_LOCATION",
    "HAS_MORPHOLOGY": "HAS_MORPHOLOGY",
    "HAS_PLAUSIBLE_CAUSE": "HAS_PLAUSIBLE_CAUSE",
    "HAS_SPATIAL_SIGNATURE": "HAS_SPATIAL_SIGNATURE",
    "INDICATES": "INDICATES",
    "INDICATES_FAULT": "INDICATES",
    "MEASURED_IN": "MEASURED_IN",
    "OCCURS_IN": "OCCURS_ON",
    "OCCURS_ON": "OCCURS_ON",
    "SUGGESTS_PLAUSIBLE_MECHANISM": "SUGGESTS_PLAUSIBLE_MECHANISM",
    "SUGGESTS_ROOT_CAUSE": "SUGGESTS_ROOT_CAUSE",
}


@dataclass(frozen=True)
class ParsedSourceDocument:
    """Text parsed from one source material record."""

    source_id: str
    source_type: str
    scenario: str
    text: str
    parser: str
    path: Path | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceTextChunk:
    """Deterministic source text chunk used as an IE prompt boundary."""

    chunk_id: str
    source_id: str
    source_type: str
    scenario: str
    text: str
    start_char: int
    end_char: int
    index: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentIEChunkExtractionSummary:
    """Audit summary for candidate extraction over one source text chunk."""

    chunk_id: str
    source_id: str
    chunk_index: int
    status: str
    entity_count: int = 0
    relation_count: int = 0
    error_message: str | None = None


@dataclass(frozen=True)
class DocumentIEExtractionResult:
    """DraftKG plus product-facing audit metadata for document IE runs."""

    draft: DraftKG
    chunk_summaries: tuple[DocumentIEChunkExtractionSummary, ...]
    extractor_name: str
    extractor_version: str
    prompt_version: str
    default_confidence: float
    strict_grounding: bool

    @property
    def chunk_count(self) -> int:
        """Return the number of attempted source chunks."""
        return len(self.chunk_summaries)

    @property
    def error_count(self) -> int:
        """Return the number of chunks that failed extraction."""
        return sum(1 for summary in self.chunk_summaries if summary.status == "failed")


class DocumentIEClient(Protocol):
    """Protocol for fake, external, or OpenAI-compatible IE clients."""

    def extract_candidates(
        self,
        chunk: SourceTextChunk,
        *,
        prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any] | str:
        """Return extracted candidate entities and relations for one chunk."""


class ExtractedEntityPayload(BaseModel):
    """Entity candidate returned by a document IE client."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    entity_id: str | None = None
    node_id: str | None = None
    name: str | None = None
    label: str | None = None
    aliases: list[str] | str | None = None
    description: str | None = None
    evidence: str | None = None
    scenario: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ExtractedRelationPayload(BaseModel):
    """Relation candidate returned by a document IE client."""

    model_config = ConfigDict(extra="allow")

    head: str | None = None
    subject: str | None = None
    source_node: str | None = None
    relation: str | None = None
    predicate: str | None = None
    edge_type: str | None = None
    tail: str | None = None
    object: str | None = None
    target_node: str | None = None
    evidence: str | None = None
    scenario: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ExtractedKGPayload(BaseModel):
    """Candidate KG payload returned by a document IE client."""

    model_config = ConfigDict(extra="allow")

    entities: list[ExtractedEntityPayload] = Field(default_factory=list)
    relations: list[ExtractedRelationPayload] = Field(default_factory=list)


def extraction_response_schema() -> dict[str, Any]:
    """Return the JSON schema requested from OpenAI-compatible IE clients."""
    return ExtractedKGPayload.model_json_schema()


def parse_source_material(
    source: KGConstructionSource,
    *,
    max_bytes: int = 2_000_000,
) -> ParsedSourceDocument:
    """Parse text, HTML, web snapshot, or PDF source material into plain text."""
    scenario = _normalize_scenario(source.scenario, candidate=f"source {source.source_id}")
    parser = _select_parser(source)
    raw_text: str | None = source.text

    if parser == "pdf":
        text = _parse_pdf_source(source)
    else:
        if raw_text is None:
            if source.path is None:
                raise ValueError(f"source {source.source_id} requires text or path")
            raw_text = _read_source_text(source.path, max_bytes=max_bytes)
        if parser == "html":
            text = _parse_html_text(raw_text)
        elif parser == "web_snapshot":
            text = _parse_web_snapshot_text(raw_text)
        else:
            text = _normalize_plain_text(raw_text)

    if not text.strip():
        raise ValueError(f"source {source.source_id} produced empty parsed text")
    return ParsedSourceDocument(
        source_id=source.source_id,
        source_type=source.source_type,
        scenario=scenario,
        text=text,
        parser=parser,
        path=source.path,
        metadata=dict(source.metadata),
    )


def chunk_source_document(
    document: ParsedSourceDocument,
    *,
    max_chars: int = DEFAULT_DOCUMENT_CHUNK_MAX_CHARS,
    overlap_chars: int = DEFAULT_DOCUMENT_CHUNK_OVERLAP_CHARS,
) -> tuple[SourceTextChunk, ...]:
    """Split parsed source text into deterministic chunks with stable IDs."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be non-negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    text = document.text.strip()
    chunks: list[SourceTextChunk] = []
    start = 0
    index = 1
    while start < len(text):
        end = _choose_chunk_end(text, start=start, max_chars=max_chars)
        chunk_start, chunk_end, chunk_text = _trim_chunk_text(text, start, end)
        if chunk_text:
            chunk_id = _chunk_id(document.source_id, index, chunk_text)
            chunks.append(
                SourceTextChunk(
                    chunk_id=chunk_id,
                    source_id=document.source_id,
                    source_type=document.source_type,
                    scenario=document.scenario,
                    text=chunk_text,
                    start_char=chunk_start,
                    end_char=chunk_end,
                    index=index,
                    metadata={
                        "parser": document.parser,
                        "path": str(document.path) if document.path is not None else "",
                    },
                )
            )
            index += 1
        if end >= len(text):
            break
        next_start = max(end - overlap_chars, start + 1)
        start = _advance_to_non_whitespace(text, next_start)

    if not chunks:
        raise ValueError(f"source {document.source_id} produced no text chunks")
    return tuple(chunks)


def extract_draft_kg_from_source_material(
    source: KGConstructionSource,
    client: DocumentIEClient,
    *,
    max_chars: int = DEFAULT_DOCUMENT_CHUNK_MAX_CHARS,
    overlap_chars: int = DEFAULT_DOCUMENT_CHUNK_OVERLAP_CHARS,
    extractor_name: str = DEFAULT_DOCUMENT_EXTRACTOR_NAME,
    extractor_version: str = DEFAULT_DOCUMENT_EXTRACTOR_VERSION,
    default_confidence: float = 0.55,
    strict_grounding: bool = True,
    prompt_version: str = DEFAULT_DOCUMENT_IE_PROMPT_VERSION,
) -> DraftKG:
    """Parse, chunk, and extract a source-constrained candidate DraftKG."""
    document = parse_source_material(source)
    chunks = chunk_source_document(
        document,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )
    return extract_draft_kg_from_chunks(
        chunks,
        client,
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        default_confidence=default_confidence,
        strict_grounding=strict_grounding,
        prompt_version=prompt_version,
    )


def extract_draft_kg_from_chunks(
    chunks: Sequence[SourceTextChunk],
    client: DocumentIEClient,
    *,
    extractor_name: str = DEFAULT_DOCUMENT_EXTRACTOR_NAME,
    extractor_version: str = DEFAULT_DOCUMENT_EXTRACTOR_VERSION,
    default_confidence: float = 0.55,
    strict_grounding: bool = True,
    prompt_version: str = DEFAULT_DOCUMENT_IE_PROMPT_VERSION,
) -> DraftKG:
    """Extract draft KG candidates from already parsed source text chunks."""
    result = extract_draft_kg_from_chunks_with_report(
        chunks,
        client,
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        default_confidence=default_confidence,
        strict_grounding=strict_grounding,
        prompt_version=prompt_version,
    )
    return result.draft


def extract_draft_kg_from_chunks_with_report(
    chunks: Sequence[SourceTextChunk],
    client: DocumentIEClient,
    *,
    extractor_name: str = DEFAULT_DOCUMENT_EXTRACTOR_NAME,
    extractor_version: str = DEFAULT_DOCUMENT_EXTRACTOR_VERSION,
    default_confidence: float = 0.55,
    strict_grounding: bool = True,
    prompt_version: str = DEFAULT_DOCUMENT_IE_PROMPT_VERSION,
    continue_on_chunk_error: bool = False,
) -> DocumentIEExtractionResult:
    """Extract DraftKG candidates and chunk-level audit summaries.

    The report is for review/audit UX only. Extractor output still enters the
    pipeline as unreviewed DraftKG candidates.
    """
    schema = extraction_response_schema()
    entities: list[DraftEntity] = []
    relations: list[DraftRelation] = []
    summaries: list[DocumentIEChunkExtractionSummary] = []
    for chunk in chunks:
        try:
            prompt = build_document_ie_prompt(chunk, prompt_version=prompt_version)
            response = client.extract_candidates(chunk, prompt=prompt, response_schema=schema)
            payload = _coerce_extracted_payload(response, chunk_id=chunk.chunk_id)
            chunk_entities = [
                _entity_to_draft(
                    entity,
                    chunk=chunk,
                    index=index,
                    extractor_name=extractor_name,
                    extractor_version=extractor_version,
                    default_confidence=default_confidence,
                    strict_grounding=strict_grounding,
                    prompt_version=prompt_version,
                )
                for index, entity in enumerate(payload.entities, start=1)
            ]
            chunk_relations = [
                _relation_to_draft(
                    relation,
                    chunk=chunk,
                    index=index,
                    extractor_name=extractor_name,
                    extractor_version=extractor_version,
                    default_confidence=default_confidence,
                    strict_grounding=strict_grounding,
                    prompt_version=prompt_version,
                )
                for index, relation in enumerate(payload.relations, start=1)
            ]
        except Exception as exc:
            if not continue_on_chunk_error:
                raise
            summaries.append(
                DocumentIEChunkExtractionSummary(
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    chunk_index=chunk.index,
                    status="failed",
                    error_message=str(exc),
                )
            )
            continue

        entities.extend(chunk_entities)
        relations.extend(chunk_relations)
        summaries.append(
            DocumentIEChunkExtractionSummary(
                chunk_id=chunk.chunk_id,
                source_id=chunk.source_id,
                chunk_index=chunk.index,
                status="extracted",
                entity_count=len(chunk_entities),
                relation_count=len(chunk_relations),
            )
        )
    return DocumentIEExtractionResult(
        draft=DraftKG(entities=tuple(entities), relations=tuple(relations)),
        chunk_summaries=tuple(summaries),
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        prompt_version=prompt_version,
        default_confidence=default_confidence,
        strict_grounding=strict_grounding,
    )


def build_document_ie_prompt(
    chunk: SourceTextChunk,
    *,
    prompt_version: str = DEFAULT_DOCUMENT_IE_PROMPT_VERSION,
) -> str:
    """Build a source-constrained IE prompt for one text chunk."""
    return (
        f"Prompt version: {prompt_version}.\n"
        "Extract only candidate industrial KG entities and relations explicitly "
        "supported by the source text chunk. Do not infer causal facts beyond the "
        "text. Use concise evidence copied from the chunk for every candidate.\n\n"
        "Allowed relation values are: "
        f"{', '.join(sorted(ALLOWED_DOCUMENT_IE_RELATIONS))}.\n\n"
        f"source_id: {chunk.source_id}\n"
        f"chunk_id: {chunk.chunk_id}\n"
        f"scenario: {chunk.scenario}\n\n"
        "Return JSON with keys `entities` and `relations`.\n\n"
        f"Source text:\n{chunk.text}"
    )


class OpenAICompatibleKGExtractionClient:
    """OpenAI-compatible chat-completions client for document IE."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        use_json_schema: bool = True,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL")
        self.model = model if model is not None else os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        self.temperature = temperature
        self.use_json_schema = use_json_schema
        self._client = client

    def extract_candidates(
        self,
        chunk: SourceTextChunk,
        *,
        prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any] | str:
        """Call an OpenAI-compatible model and return its JSON IE payload."""
        client = self._resolved_client()
        response_format = self._response_format(response_schema)
        completion = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract source-grounded draft knowledge graph candidates. "
                        "Return JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format=response_format,
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError(f"OpenAI-compatible IE returned empty content for {chunk.chunk_id}")
        return json.loads(content)

    def _resolved_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI-compatible document IE")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ImportError(
                "OpenAI-compatible document IE requires the optional `openai` dependency. "
                "Install the project with the `llm` extra."
            ) from exc
        kwargs: dict[str, str] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    def _response_format(self, response_schema: Mapping[str, Any]) -> dict[str, Any]:
        if self.use_json_schema:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "kgtracevis_document_ie",
                    "schema": dict(response_schema),
                    "strict": False,
                },
            }
        return {"type": "json_object"}


def _select_parser(source: KGConstructionSource) -> str:
    hint = " ".join(
        str(value).lower()
        for value in (
            source.source_type,
            source.metadata.get("content_type", ""),
            source.metadata.get("format", ""),
            source.path.suffix if source.path is not None else "",
        )
        if value
    )
    if "pdf" in hint:
        return "pdf"
    if "html" in hint or "htm" in hint:
        return "html"
    if "snapshot" in hint or "web" in hint:
        return "web_snapshot"
    return "text"


def _read_source_text(path: Path, *, max_bytes: int) -> str:
    with path.open("rb") as handle:
        content = handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"source file is larger than max_bytes: {path}")
    return content.decode("utf-8")


def _parse_pdf_source(source: KGConstructionSource) -> str:
    if source.path is None:
        raise ValueError(f"PDF source {source.source_id} requires source.path")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError(
            "PDF source parsing requires optional dependency `pypdf`; "
            "install it or pre-convert the PDF to text/HTML."
        ) from exc
    reader = PdfReader(str(source.path))
    text_parts = [page.extract_text() or "" for page in reader.pages]
    return _normalize_plain_text("\n\n".join(text_parts))


def _parse_html_text(raw_text: str) -> str:
    parser = _VisibleHTMLTextExtractor()
    parser.feed(raw_text)
    parser.close()
    return _normalize_plain_text(parser.text())


def _parse_web_snapshot_text(raw_text: str) -> str:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        if _looks_like_html(raw_text):
            return _parse_html_text(raw_text)
        return _normalize_plain_text(raw_text)
    if isinstance(payload, Mapping):
        return _normalize_plain_text(_snapshot_strings(payload))
    if isinstance(payload, list):
        return _normalize_plain_text("\n\n".join(_snapshot_strings(item) for item in payload))
    return _normalize_plain_text(str(payload))


def _snapshot_strings(payload: object) -> str:
    if isinstance(payload, str):
        return _parse_html_text(payload) if _looks_like_html(payload) else payload
    if isinstance(payload, Mapping):
        preferred_parts: list[str] = []
        for key in ("title", "url", "text", "markdown", "content", "html", "body"):
            value = payload.get(key)
            if value is None:
                continue
            preferred_parts.append(_snapshot_strings(value))
        if preferred_parts:
            return "\n\n".join(part for part in preferred_parts if part.strip())
        return "\n\n".join(_snapshot_strings(value) for value in payload.values())
    if isinstance(payload, list):
        return "\n\n".join(_snapshot_strings(item) for item in payload)
    return ""


def _normalize_plain_text(text: str) -> str:
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    normalized_lines: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if normalized_lines and not previous_blank:
                normalized_lines.append("")
            previous_blank = True
            continue
        normalized_lines.append(line)
        previous_blank = False
    return "\n".join(normalized_lines).strip()


class _VisibleHTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag in {"br", "p", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        return " ".join(self._parts)


def _looks_like_html(text: str) -> bool:
    sample = text[:500].lower()
    return any(tag in sample for tag in ("<html", "<body", "<div", "<p", "<table"))


def _choose_chunk_end(text: str, *, start: int, max_chars: int) -> int:
    hard_end = min(start + max_chars, len(text))
    if hard_end >= len(text):
        return hard_end
    min_end = start + max(max_chars // 2, 1)
    paragraph_break = text.rfind("\n\n", min_end, hard_end)
    if paragraph_break > start:
        return paragraph_break
    line_break = text.rfind("\n", min_end, hard_end)
    if line_break > start:
        return line_break
    whitespace = max(text.rfind(" ", min_end, hard_end), text.rfind("\t", min_end, hard_end))
    if whitespace > start:
        return whitespace
    return hard_end


def _trim_chunk_text(text: str, start: int, end: int) -> tuple[int, int, str]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end, text[start:end]


def _advance_to_non_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _chunk_id(source_id: str, index: int, chunk_text: str) -> str:
    digest = sha1(f"{source_id}\n{index}\n{chunk_text}".encode()).hexdigest()[:12]
    return f"{source_id}:chunk:{index:04d}:{digest}"


def _coerce_extracted_payload(
    response: Mapping[str, Any] | str,
    *,
    chunk_id: str,
) -> ExtractedKGPayload:
    try:
        payload = json.loads(response) if isinstance(response, str) else dict(response)
        return ExtractedKGPayload.model_validate(payload)
    except (TypeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid IE payload for {chunk_id}") from exc


def _entity_to_draft(
    entity: ExtractedEntityPayload,
    *,
    chunk: SourceTextChunk,
    index: int,
    extractor_name: str,
    extractor_version: str,
    default_confidence: float,
    strict_grounding: bool,
    prompt_version: str,
) -> DraftEntity:
    raw_entity_id = _first_text(entity.id, entity.entity_id, entity.node_id)
    entity_id = _coerce_entity_id(raw_entity_id, candidate=f"entity candidate in {chunk.chunk_id}")
    name = _first_text(entity.name)
    label = _first_text(entity.label)
    if not entity_id or not name or not label:
        raise ValueError(f"entity candidate in {chunk.chunk_id} missing id/name/label")
    scenario = _normalize_scenario(
        _first_text(entity.scenario) or chunk.scenario,
        candidate=f"entity candidate {entity_id} in {chunk.chunk_id}",
    )
    evidence, evidence_span = _ground_evidence(
        entity.evidence,
        chunk=chunk,
        strict_grounding=strict_grounding,
    )
    return DraftEntity(
        draft_id=f"{chunk.chunk_id}:entity:{index}",
        source_id=chunk.source_id,
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        scenario=scenario,
        entity_id_suggestion=entity_id,
        name=name,
        label=label,
        aliases=_aliases_tuple(entity.aliases),
        description=_first_text(entity.description),
        evidence=evidence,
        evidence_span=evidence_span,
        confidence=_confidence(entity.confidence, default_confidence),
        status="draft",
        metadata={
            "chunk_id": chunk.chunk_id,
            "chunk_index": chunk.index,
            "prompt_version": prompt_version,
            "raw_entity_id": raw_entity_id,
        },
    )


def _relation_to_draft(
    relation: ExtractedRelationPayload,
    *,
    chunk: SourceTextChunk,
    index: int,
    extractor_name: str,
    extractor_version: str,
    default_confidence: float,
    strict_grounding: bool,
    prompt_version: str,
) -> DraftRelation:
    raw_head = _first_text(relation.head, relation.subject, relation.source_node)
    head = _coerce_entity_id(raw_head, candidate=f"relation head in {chunk.chunk_id}")
    relation_name = _normalize_relation_name(
        _first_text(relation.relation, relation.predicate, relation.edge_type),
        chunk_id=chunk.chunk_id,
    )
    raw_tail = _first_text(relation.tail, relation.object, relation.target_node)
    tail = _coerce_entity_id(raw_tail, candidate=f"relation tail in {chunk.chunk_id}")
    if not head or not relation_name or not tail:
        raise ValueError(f"relation candidate in {chunk.chunk_id} missing head/relation/tail")
    scenario = _normalize_scenario(
        _first_text(relation.scenario) or chunk.scenario,
        candidate=f"relation candidate {head}|{relation_name}|{tail} in {chunk.chunk_id}",
    )
    evidence, evidence_span = _ground_evidence(
        relation.evidence,
        chunk=chunk,
        strict_grounding=strict_grounding,
    )
    return DraftRelation(
        draft_id=f"{chunk.chunk_id}:relation:{index}",
        source_id=chunk.source_id,
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        scenario=scenario,
        head=head,
        relation=relation_name,
        tail=tail,
        evidence=evidence,
        evidence_span=evidence_span,
        confidence=_confidence(relation.confidence, default_confidence),
        status="draft",
        metadata={
            "chunk_id": chunk.chunk_id,
            "chunk_index": chunk.index,
            "prompt_version": prompt_version,
            "raw_head": raw_head,
            "raw_tail": raw_tail,
        },
    )


def _ground_evidence(
    evidence: str | None,
    *,
    chunk: SourceTextChunk,
    strict_grounding: bool,
) -> tuple[str, str]:
    text = _first_text(evidence)
    if not text:
        if strict_grounding:
            raise ValueError(f"candidate in {chunk.chunk_id} missing source evidence")
        text = chunk.text[:500]
    start = chunk.text.find(text)
    if start >= 0:
        span_start = chunk.start_char + start
        span_end = span_start + len(text)
        return text, f"{chunk.chunk_id}:{span_start}-{span_end}"
    if strict_grounding and _squashed(text) not in _squashed(chunk.text):
        raise ValueError(f"candidate evidence is not grounded in source chunk {chunk.chunk_id}")
    return text, chunk.chunk_id


def _squashed(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _first_text(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _aliases_tuple(value: list[str] | str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = re.split(r"[|;,]", value)
    else:
        parts = [str(item) for item in value]
    return tuple(dict.fromkeys(part.strip() for part in parts if part.strip()))


def _confidence(value: float | None, default: float) -> float:
    resolved = default if value is None else value
    return max(0.0, min(1.0, float(resolved)))


def _normalize_scenario(value: str, *, candidate: str) -> str:
    scenario = value.strip().lower()
    if scenario not in VALID_SCENARIOS:
        raise ValueError(
            f"{candidate} has invalid scenario {value!r}; "
            f"expected one of {', '.join(sorted(VALID_SCENARIOS))}"
        )
    return scenario


def _coerce_entity_id(value: str, *, candidate: str) -> str:
    if not value:
        return ""
    normalized = value.strip()
    if re.fullmatch(r"[A-Z][A-Za-z0-9]*", normalized):
        return normalized
    words = re.findall(r"[A-Za-z0-9]+", normalized)
    if not words:
        raise ValueError(f"{candidate} has invalid entity id {value!r}")
    return "".join(word[:1].upper() + word[1:] for word in words)


def _normalize_relation_name(value: str, *, chunk_id: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    relation = DOCUMENT_IE_RELATION_ALIASES.get(text.upper(), text.upper())
    if not relation:
        raise ValueError(f"relation candidate in {chunk_id} missing relation")
    if relation not in ALLOWED_DOCUMENT_IE_RELATIONS:
        raise ValueError(
            f"relation candidate in {chunk_id} uses out-of-scope relation {relation!r}; "
            f"expected one of {', '.join(sorted(ALLOWED_DOCUMENT_IE_RELATIONS))}"
        )
    return relation
