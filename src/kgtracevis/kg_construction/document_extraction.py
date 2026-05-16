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
from typing import Any, Literal, Protocol

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
DEFAULT_DOCUMENT_UNDERSTANDING_PROMPT_VERSION = "document_understanding_prompt_v1"
DocumentUnderstandingMode = Literal["chunk", "long_context", "agentic"]
DeepSeekThinkingPolicy = Literal["default", "disabled"]
AGENTIC_DOCUMENT_READER_STEPS = (
    "outline",
    "glossary",
    "entity_inventory",
    "relation_hints",
    "cross_chunk_proposals",
)
DOCUMENT_READER_MAX_STEP_CHUNKS = 3
DOCUMENT_READER_SUMMARY_MAX_CHARS = 140

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

DOCUMENT_IE_LABEL_ALIASES = {
    "DEFECT CLASS": "DefectType",
    "DEFECTCLASS": "DefectType",
    "DEFECT PATTERN": "DefectType",
    "DEFECTPATTERN": "DefectType",
    "DEFECT TYPE": "DefectType",
    "FAILURE PATTERN": "DefectType",
    "PATTERN": "DefectType",
    "PROCESS": "ProcessUnit",
    "PROCESS CONDITION": "ProcessCondition",
    "WAFER MAP": "Wafer",
    "WAFERMAP": "Wafer",
}

CAUSAL_SUGGESTION_RELATIONS = frozenset(
    {
        "CAUSES",
        "HAS_PLAUSIBLE_CAUSE",
        "SUGGESTS_PLAUSIBLE_MECHANISM",
        "SUGGESTS_ROOT_CAUSE",
    }
)

CAUSAL_CAUSE_PHRASE_PATTERNS = (
    re.compile(
        r"\barises?\s+due\s+to\s+(?:problems?\s+in\s+(?:the\s+)?)?"
        r"(?P<cause>[^.;:\n()]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bis\s+due\s+to\s+(?:problems?\s+in\s+(?:the\s+)?)?"
        r"(?P<cause>[^.;:\n()]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bdue\s+to\s+(?:problems?\s+in\s+(?:the\s+)?)?"
        r"(?P<cause>[^.;:\n()]+)",
        re.IGNORECASE,
    ),
    re.compile(r"\bresult\s+of\s+(?P<cause>[^.;:\n()]+)", re.IGNORECASE),
    re.compile(r"\bcaused\s+by\s+(?P<cause>[^.;:\n()]+)", re.IGNORECASE),
)


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
class DocumentReadingChunkSummary:
    """Compact, deterministic summary for one parsed source chunk."""

    chunk_id: str
    chunk_index: int
    char_start: int
    char_end: int
    summary: str
    keywords: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        """Return JSON-serializable audit metadata for this chunk summary."""
        return {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "summary": self.summary,
            "keywords": list(self.keywords),
        }


@dataclass(frozen=True)
class DocumentReadingStepPlan:
    """Selected chunk group for one deterministic reader step."""

    step_name: str
    selected_chunk_ids: tuple[str, ...]
    retrieval_strategy: str
    query_terms: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        """Return JSON-serializable audit metadata for this step plan."""
        return {
            "step_name": self.step_name,
            "selected_chunk_ids": list(self.selected_chunk_ids),
            "retrieval_strategy": self.retrieval_strategy,
            "query_terms": list(self.query_terms),
        }


@dataclass(frozen=True)
class DocumentReadingPlan:
    """Reusable retrieval/index plan for advisory document reading."""

    source_id: str
    strategy: str
    chunk_summaries: tuple[DocumentReadingChunkSummary, ...]
    step_plans: tuple[DocumentReadingStepPlan, ...]

    def step_for(self, step_name: str) -> DocumentReadingStepPlan:
        """Return the configured step plan for a reader step."""
        for step_plan in self.step_plans:
            if step_plan.step_name == step_name:
                return step_plan
        raise ValueError(f"unknown document reader step: {step_name}")

    def to_payload(self) -> dict[str, Any]:
        """Return JSON-serializable audit metadata for this reading plan."""
        return {
            "source_id": self.source_id,
            "strategy": self.strategy,
            "chunk_count": len(self.chunk_summaries),
            "chunk_summaries": [summary.to_payload() for summary in self.chunk_summaries],
            "step_plans": [step_plan.to_payload() for step_plan in self.step_plans],
        }


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


class DocumentUnderstandingClient(Protocol):
    """Protocol for advisory document-map clients used before chunk IE."""

    def understand_document(
        self,
        document: ParsedSourceDocument,
        chunks: Sequence[SourceTextChunk],
        *,
        mode: DocumentUnderstandingMode,
        step_name: str,
        prompt: str,
        response_schema: Mapping[str, Any],
        prior_steps: Sequence[Mapping[str, Any]] = (),
    ) -> Mapping[str, Any] | str:
        """Return an advisory document-map or step payload."""


class OfflineDocumentIEFixtureClient:
    """Document IE client that replays source-grounded fixture payloads."""

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


class OfflineDocumentUnderstandingFixtureClient:
    """Document-understanding client that replays deterministic map fixtures."""

    def __init__(self, fixture: Mapping[str, Any]) -> None:
        self.fixture = dict(fixture)
        self.calls: list[dict[str, Any]] = []

    def understand_document(
        self,
        document: ParsedSourceDocument,
        chunks: Sequence[SourceTextChunk],
        *,
        mode: DocumentUnderstandingMode,
        step_name: str,
        prompt: str,
        response_schema: Mapping[str, Any],
        prior_steps: Sequence[Mapping[str, Any]] = (),
    ) -> Mapping[str, Any] | str:
        """Return a fixture document-map payload or a named step payload."""
        del response_schema
        self.calls.append(
            {
                "source_id": document.source_id,
                "chunk_count": len(chunks),
                "mode": mode,
                "step_name": step_name,
                "prompt": prompt,
                "prior_step_count": len(prior_steps),
            }
        )
        steps = self.fixture.get("steps")
        if isinstance(steps, Mapping):
            step_payload = steps.get(step_name)
            if isinstance(step_payload, (Mapping, str)):
                return step_payload
        document_map = self.fixture.get("document_map")
        if isinstance(document_map, (Mapping, str)):
            return document_map
        return self.fixture


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


class DocumentUnderstandingMapPayload(BaseModel):
    """Advisory document-map payload returned by a DU client."""

    model_config = ConfigDict(extra="allow")

    artifact_type: str | None = None
    mode: DocumentUnderstandingMode | None = None
    source_id: str | None = None
    source_type: str | None = None
    scenario: str | None = None
    parser: str | None = None
    sections: list[dict[str, Any]] = Field(default_factory=list)
    glossary: list[dict[str, Any]] = Field(default_factory=list)
    entity_inventory: list[dict[str, Any]] = Field(default_factory=list)
    relation_hints: list[dict[str, Any]] = Field(default_factory=list)
    ontology_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    cross_chunk_proposals: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_questions: list[dict[str, Any]] = Field(default_factory=list)
    review_hints: list[str] = Field(default_factory=list)
    agent_steps: list[dict[str, Any]] = Field(default_factory=list)
    claim_boundary: str | None = None


def extraction_response_schema() -> dict[str, Any]:
    """Return the JSON schema requested from OpenAI-compatible IE clients."""
    return ExtractedKGPayload.model_json_schema()


def document_understanding_response_schema() -> dict[str, Any]:
    """Return the JSON schema requested from document-understanding clients."""
    return DocumentUnderstandingMapPayload.model_json_schema()


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
                        **{
                            str(key): str(value)
                            for key, value in document.metadata.items()
                            if isinstance(value, str | int | float | bool)
                        },
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
    document_context: Mapping[str, Any] | None = None,
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
        document_context=document_context,
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
    document_context: Mapping[str, Any] | None = None,
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
            prompt = build_document_ie_prompt(
                chunk,
                prompt_version=prompt_version,
                document_context=document_context,
            )
            response = client.extract_candidates(chunk, prompt=prompt, response_schema=schema)
            payload = _coerce_extracted_payload(response, chunk_id=chunk.chunk_id)
            if continue_on_chunk_error:
                chunk_entities, entity_errors = _coerce_entity_candidates_for_chunk(
                    payload.entities,
                    chunk=chunk,
                    extractor_name=extractor_name,
                    extractor_version=extractor_version,
                    default_confidence=default_confidence,
                    strict_grounding=strict_grounding,
                    prompt_version=prompt_version,
                )
                chunk_relations, relation_errors = _coerce_relation_candidates_for_chunk(
                    payload.relations,
                    chunk=chunk,
                    extractor_name=extractor_name,
                    extractor_version=extractor_version,
                    default_confidence=default_confidence,
                    strict_grounding=strict_grounding,
                    prompt_version=prompt_version,
                )
            else:
                entity_errors = []
                relation_errors = []
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
                status="partial" if entity_errors or relation_errors else "extracted",
                entity_count=len(chunk_entities),
                relation_count=len(chunk_relations),
                error_message=_skipped_candidate_error_message(
                    entity_errors + relation_errors
                ),
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
    document_context: Mapping[str, Any] | None = None,
) -> str:
    """Build a source-constrained IE prompt for one text chunk."""
    context = _document_context_prompt(document_context, chunk_id=chunk.chunk_id)
    role_guidance = _source_role_prompt(chunk)
    return (
        f"Prompt version: {prompt_version}.\n"
        "Extract only candidate industrial KG entities and relations explicitly "
        "supported by the source text chunk. Do not infer causal facts beyond the "
        "text. Use concise evidence copied from the chunk for every candidate.\n\n"
        f"{context}"
        f"{role_guidance}"
        "Allowed relation values are: "
        f"{', '.join(sorted(ALLOWED_DOCUMENT_IE_RELATIONS))}.\n\n"
        f"source_id: {chunk.source_id}\n"
        f"chunk_id: {chunk.chunk_id}\n"
        f"scenario: {chunk.scenario}\n\n"
        "Return compact JSON with keys `entities` and `relations`. Each entity "
        "must include id, name, label, and evidence. Each relation must include "
        "head, relation, tail, and evidence. Use label, not type, for entity "
        "category. Limit output to at most 12 entities and 16 relations; do not "
        "expand long defect dictionaries exhaustively.\n\n"
        f"Source text:\n{chunk.text}"
    )


def _source_role_prompt(chunk: SourceTextChunk) -> str:
    role = str(chunk.metadata.get("source_pack_role") or "").strip()
    if not role:
        return ""
    lines = [f"Source role: {role}."]
    if any(token in role for token in ("root_cause", "cause_table", "mechanism")):
        lines.append(
            "This source is root-cause/mechanism context. When the chunk explicitly "
            "states a defect, symptom, or anomaly and its cause, prioritize "
            "`DefectOrAnomaly HAS_PLAUSIBLE_CAUSE CauseOrMechanism` candidates. "
            "Use the source wording for cause entity names instead of generic IDs, "
            "label causes as RootCause or CauseCategory, label symptoms as Defect "
            "or AnomalyType, and copy the exact defect/cause phrase as evidence."
        )
    if "wafer" in role or "wm811k" in role:
        lines.append(
            "This source is wafer-map context. Extract wafer pattern, spatial "
            "location, morphology/signature, and explicitly stated process-condition "
            "candidates. Prefer `Pattern HAS_LOCATION Location`, "
            "`Pattern HAS_MORPHOLOGY Morphology`, `Pattern HAS_SPATIAL_SIGNATURE "
            "Morphology`, and `Pattern HAS_PLAUSIBLE_CAUSE ProcessCondition` only "
            "when the chunk states the link."
        )
    elif any(token in role for token in ("taxonomy", "defect_label", "dataset")):
        lines.append(
            "This source is taxonomy/context material. Extract object, defect, "
            "morphology, and location candidates when explicitly listed, but do "
            "not infer process root causes unless the chunk states them."
        )
    return "\n".join(lines) + "\n\n"


def build_document_understanding_map(
    document: ParsedSourceDocument,
    chunks: Sequence[SourceTextChunk],
    *,
    mode: DocumentUnderstandingMode,
    client: DocumentUnderstandingClient | None = None,
    prompt_version: str = DEFAULT_DOCUMENT_UNDERSTANDING_PROMPT_VERSION,
) -> dict[str, Any]:
    """Build an advisory document-level map for review and prompt context.

    The map is not a fact extractor. It records terminology and review hints so
    downstream IE can use document context while still grounding every candidate
    in the current chunk.
    """
    if mode == "chunk":
        raise ValueError("document understanding map is only produced for non-chunk modes")
    if mode == "agentic":
        return AgenticDocumentReader(
            client=client,
            prompt_version=prompt_version,
        ).read(document, chunks)

    fallback = _deterministic_document_understanding_map(document, chunks, mode=mode)
    if client is None:
        return {
            **fallback,
            "reader_type": "deterministic_fallback",
            "document_understanding_prompt_version": prompt_version,
        }
    prompt = build_document_understanding_prompt(
        document,
        chunks,
        mode=mode,
        step_name="long_context_document_map",
        prompt_version=prompt_version,
    )
    response = client.understand_document(
        document,
        chunks,
        mode=mode,
        step_name="long_context_document_map",
        prompt=prompt,
        response_schema=document_understanding_response_schema(),
    )
    return _normalize_document_understanding_map(
        response,
        document=document,
        chunks=chunks,
        mode=mode,
        fallback=fallback,
        reader_type="long_context_llm",
        prompt_version=prompt_version,
    )


def build_document_reading_plan(
    document: ParsedSourceDocument,
    chunks: Sequence[SourceTextChunk],
    *,
    max_step_chunks: int = DOCUMENT_READER_MAX_STEP_CHUNKS,
) -> DocumentReadingPlan:
    """Build a deterministic chunk index and retrieval plan for agentic DU."""
    if max_step_chunks <= 0:
        raise ValueError("max_step_chunks must be positive")
    chunk_tuple = tuple(chunks)
    summaries = tuple(_chunk_reading_summary(chunk) for chunk in chunk_tuple)
    step_plans = tuple(
        _reading_step_plan(
            step_name,
            summaries=summaries,
            max_step_chunks=max_step_chunks,
        )
        for step_name in AGENTIC_DOCUMENT_READER_STEPS
    )
    return DocumentReadingPlan(
        source_id=document.source_id,
        strategy="deterministic_chunk_summary_keyword_retrieval_v1",
        chunk_summaries=summaries,
        step_plans=step_plans,
    )


class AgenticDocumentReader:
    """Multi-step advisory reader for document-understanding mode."""

    def __init__(
        self,
        *,
        client: DocumentUnderstandingClient | None = None,
        prompt_version: str = DEFAULT_DOCUMENT_UNDERSTANDING_PROMPT_VERSION,
    ) -> None:
        self.client = client
        self.prompt_version = prompt_version

    def read(
        self,
        document: ParsedSourceDocument,
        chunks: Sequence[SourceTextChunk],
    ) -> dict[str, Any]:
        """Run named planning steps and return one normalized document map."""
        reading_plan = build_document_reading_plan(document, chunks)
        fallback = _deterministic_document_understanding_map(document, chunks, mode="agentic")
        if self.client is None:
            return {
                **fallback,
                "reader_type": "agentic_deterministic_fallback",
                "document_understanding_prompt_version": self.prompt_version,
                "document_reading_plan": reading_plan.to_payload(),
                "agent_steps": [
                    {
                        "step_name": step_name,
                        "status": "deterministic_fallback",
                        "output_keys": [],
                        **reading_plan.step_for(step_name).to_payload(),
                    }
                    for step_name in AGENTIC_DOCUMENT_READER_STEPS
                ],
            }

        step_outputs: list[dict[str, Any]] = []
        agent_steps: list[dict[str, Any]] = []
        merged_payload: dict[str, Any] = {}
        for step_name in AGENTIC_DOCUMENT_READER_STEPS:
            step_plan = reading_plan.step_for(step_name)
            selected_chunks = _chunks_for_step(chunks, step_plan)
            prompt = build_document_understanding_prompt(
                document,
                selected_chunks,
                mode="agentic",
                step_name=step_name,
                prompt_version=self.prompt_version,
                prior_steps=step_outputs,
                reading_plan=reading_plan,
                step_plan=step_plan,
            )
            response = self.client.understand_document(
                document,
                selected_chunks,
                mode="agentic",
                step_name=step_name,
                prompt=prompt,
                response_schema=document_understanding_response_schema(),
                prior_steps=step_outputs,
            )
            step_payload = _coerce_document_understanding_payload(
                response,
                source_id=document.source_id,
                step_name=step_name,
            )
            step_output = step_payload.model_dump(mode="json", exclude_none=True)
            step_outputs.append({"step_name": step_name, **step_output})
            output_keys = sorted(
                key
                for key, value in step_output.items()
                if key
                not in {
                    "artifact_type",
                    "mode",
                    "source_id",
                    "source_type",
                    "scenario",
                    "parser",
                    "claim_boundary",
                }
                and value not in (None, [], {}, "")
            )
            agent_steps.append(
                {
                    "step_name": step_name,
                    "status": "completed",
                    "output_keys": output_keys,
                    **step_plan.to_payload(),
                    "response_sha1": sha1(
                        json.dumps(step_output, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                }
            )
            _merge_document_understanding_step(merged_payload, step_output)

        merged_payload["agent_steps"] = agent_steps
        merged_payload["document_reading_plan"] = reading_plan.to_payload()
        return _normalize_document_understanding_map(
            merged_payload,
            document=document,
            chunks=chunks,
            mode="agentic",
            fallback=fallback,
            reader_type="agentic_multi_step",
            prompt_version=self.prompt_version,
        )


def build_document_understanding_prompt(
    document: ParsedSourceDocument,
    chunks: Sequence[SourceTextChunk],
    *,
    mode: DocumentUnderstandingMode,
    step_name: str,
    prompt_version: str = DEFAULT_DOCUMENT_UNDERSTANDING_PROMPT_VERSION,
    prior_steps: Sequence[Mapping[str, Any]] = (),
    reading_plan: DocumentReadingPlan | None = None,
    step_plan: DocumentReadingStepPlan | None = None,
) -> str:
    """Build the advisory prompt for long-context and agentic DU clients."""
    chunk_blocks = "\n\n".join(
        (
            f"chunk_id: {chunk.chunk_id}\n"
            f"chunk_index: {chunk.index}\n"
            f"char_span: {chunk.start_char}-{chunk.end_char}\n"
            f"text:\n{chunk.text}"
        )
        for chunk in chunks
    )
    retrieval_context = ""
    if reading_plan is not None and step_plan is not None:
        retrieval_context = (
            "Document reading plan JSON:\n"
            + json.dumps(
                {
                    "strategy": reading_plan.strategy,
                    "step": step_plan.to_payload(),
                    "chunk_index": [
                        {
                            "chunk_id": summary.chunk_id,
                            "chunk_index": summary.chunk_index,
                            "char_start": summary.char_start,
                            "char_end": summary.char_end,
                        }
                        for summary in reading_plan.chunk_summaries
                    ],
                },
                sort_keys=True,
            )
            + "\n"
        )
    prior_summary = ""
    if prior_steps:
        prior_summary = (
            "\nPrior completed steps JSON:\n"
            + json.dumps(list(prior_steps), sort_keys=True)
            + "\n"
        )
    return (
        f"Prompt version: {prompt_version}.\n"
        f"Document understanding mode: {mode}.\n"
        f"Reader step: {step_name}.\n"
        "Produce advisory document-map JSON only. This output may guide review "
        "and chunk prompts, but it must not assert reviewed KG facts. If you "
        "suggest cross-chunk relations, include at least two supporting_spans "
        "with chunk_id and copied text/evidence. Use allowed document IE "
        f"relations only: {', '.join(sorted(ALLOWED_DOCUMENT_IE_RELATIONS))}.\n"
        "Keep all evidence snippets traceable to chunk text. Return one compact "
        "top-level JSON object with only these list fields when relevant: "
        "sections, glossary, entity_inventory, relation_hints, "
        "ontology_suggestions, cross_chunk_proposals, unresolved_questions, "
        "review_hints. Do not nest output under document_map, do not emit "
        "chunk_maps, and keep each list to at most 5 concise items. "
        "Use objects for unresolved_questions, for example "
        "{\"question\":\"...\",\"rationale\":\"...\"}.\n"
        f"{prior_summary}\n"
        f"source_id: {document.source_id}\n"
        f"source_type: {document.source_type}\n"
        f"scenario: {document.scenario}\n"
        f"parser: {document.parser}\n\n"
        f"{retrieval_context}"
        f"Selected document chunks:\n{chunk_blocks}"
    )


def _chunk_reading_summary(chunk: SourceTextChunk) -> DocumentReadingChunkSummary:
    normalized = " ".join(chunk.text.split())
    sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0].strip()
    summary = (sentence or normalized)[:DOCUMENT_READER_SUMMARY_MAX_CHARS]
    return DocumentReadingChunkSummary(
        chunk_id=chunk.chunk_id,
        chunk_index=chunk.index,
        char_start=chunk.start_char,
        char_end=chunk.end_char,
        summary=summary,
        keywords=_chunk_keywords(normalized),
    )


def _chunk_keywords(text: str, *, limit: int = 8) -> tuple[str, ...]:
    candidates = re.findall(r"\b[A-Za-z][A-Za-z0-9_-]{2,}\b", text)
    stopwords = {
        "and",
        "are",
        "for",
        "from",
        "into",
        "the",
        "this",
        "that",
        "with",
    }
    keywords: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.lower()
        if normalized in stopwords or normalized in seen:
            continue
        if candidate[:1].isupper() or len(candidate) >= 7:
            seen.add(normalized)
            keywords.append(candidate[:40])
        if len(keywords) >= limit:
            break
    return tuple(keywords)


def _reading_step_plan(
    step_name: str,
    *,
    summaries: Sequence[DocumentReadingChunkSummary],
    max_step_chunks: int,
) -> DocumentReadingStepPlan:
    if not summaries:
        return DocumentReadingStepPlan(
            step_name=step_name,
            selected_chunk_ids=(),
            retrieval_strategy="empty_document",
        )
    if step_name == "outline":
        selected = _spread_chunk_ids(summaries, limit=max_step_chunks)
        return DocumentReadingStepPlan(
            step_name=step_name,
            selected_chunk_ids=selected,
            retrieval_strategy="section_spread_first_middle_last",
            query_terms=("section", "overview", "heading"),
        )
    query_terms = _step_query_terms(step_name)
    selected = _keyword_selected_chunk_ids(
        summaries,
        query_terms=query_terms,
        limit=max_step_chunks,
    )
    return DocumentReadingStepPlan(
        step_name=step_name,
        selected_chunk_ids=selected,
        retrieval_strategy="keyword_summary_top_k",
        query_terms=query_terms,
    )


def _step_query_terms(step_name: str) -> tuple[str, ...]:
    if step_name == "glossary":
        return ("abbreviation", "term", "definition", "alias", "called")
    if step_name == "entity_inventory":
        return ("equipment", "fault", "variable", "process", "defect", "event")
    if step_name == "relation_hints":
        return ("cause", "causes", "indicates", "affects", "associated", "mechanism")
    if step_name == "cross_chunk_proposals":
        return ("cause", "root", "mechanism", "downstream", "upstream", "because")
    return ()


def _keyword_selected_chunk_ids(
    summaries: Sequence[DocumentReadingChunkSummary],
    *,
    query_terms: Sequence[str],
    limit: int,
) -> tuple[str, ...]:
    scored: list[tuple[int, int, str]] = []
    normalized_terms = tuple(term.lower() for term in query_terms)
    for summary in summaries:
        haystack = " ".join((summary.summary, *summary.keywords)).lower()
        score = sum(1 for term in normalized_terms if term in haystack)
        if score:
            scored.append((-score, summary.chunk_index, summary.chunk_id))
    if not scored:
        return _spread_chunk_ids(summaries, limit=limit)
    return tuple(chunk_id for _, _, chunk_id in sorted(scored)[:limit])


def _spread_chunk_ids(
    summaries: Sequence[DocumentReadingChunkSummary],
    *,
    limit: int,
) -> tuple[str, ...]:
    if len(summaries) <= limit:
        return tuple(summary.chunk_id for summary in summaries)
    candidate_indexes = [0, len(summaries) - 1]
    if limit >= 3:
        candidate_indexes.insert(1, len(summaries) // 2)
    selected: list[str] = []
    for index in candidate_indexes:
        chunk_id = summaries[index].chunk_id
        if chunk_id not in selected:
            selected.append(chunk_id)
        if len(selected) >= limit:
            break
    return tuple(selected)


def _chunks_for_step(
    chunks: Sequence[SourceTextChunk],
    step_plan: DocumentReadingStepPlan,
) -> tuple[SourceTextChunk, ...]:
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    selected = tuple(
        by_id[chunk_id]
        for chunk_id in step_plan.selected_chunk_ids
        if chunk_id in by_id
    )
    return selected or tuple(chunks[:1])


def _deterministic_document_understanding_map(
    document: ParsedSourceDocument,
    chunks: Sequence[SourceTextChunk],
    *,
    mode: DocumentUnderstandingMode,
) -> dict[str, Any]:
    text = document.text
    chunk_tuple = tuple(chunks)
    inventory = _document_entity_inventory(text, chunk_tuple)
    return {
        "artifact_type": "document_understanding_map_v1",
        "mode": mode,
        "source_id": document.source_id,
        "source_type": document.source_type,
        "scenario": document.scenario,
        "parser": document.parser,
        "text_sha1": sha1(text.encode("utf-8")).hexdigest(),
        "chunk_count": len(chunk_tuple),
        "claim_boundary": (
            "Document understanding output is planning, terminology, and review "
            "context only; it is not DraftKG, reviewed KG, or published KG."
        ),
        "sections": _document_sections(text, chunk_tuple),
        "glossary": _document_glossary(text, chunk_tuple),
        "entity_inventory": inventory,
        "relation_hints": _document_relation_hints(text, chunk_tuple),
        "ontology_suggestions": _ontology_suggestions(inventory),
        "cross_chunk_proposals": [],
        "unresolved_questions": [
            {
                "question": (
                    "Which document-level terms require human-approved canonical IDs "
                    "before semantic projection?"
                ),
                "reason": "document-level terminology is advisory until aligned and reviewed",
            }
        ],
        "review_hints": [
            "Use this map to inspect aliases, terminology, and chunk coverage.",
            "Do not accept relations unless their evidence appears in the candidate chunk.",
            "Cross-chunk proposals must enter review separately before publication.",
        ],
    }


def build_chunk_prompt_context_records(
    chunks: Sequence[SourceTextChunk],
    document_context: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return audit-safe prompt context rows injected for each chunk."""
    if not document_context:
        return []
    mode = str(document_context.get("mode") or "unknown")
    rows: list[dict[str, Any]] = []
    for chunk in chunks:
        glossary = _context_items_for_chunk(
            document_context.get("glossary", []),
            chunk.chunk_id,
            limit=8,
        )
        inventory = _context_items_for_chunk(
            document_context.get("entity_inventory", []),
            chunk.chunk_id,
            limit=12,
        )
        relation_hints = _context_items_for_chunk(
            document_context.get("relation_hints", []),
            chunk.chunk_id,
            limit=8,
        )
        rows.append(
            {
                "source_id": chunk.source_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.index,
                "mode": mode,
                "glossary_terms": [
                    str(item.get("term"))
                    for item in glossary
                    if isinstance(item, Mapping) and item.get("term")
                ],
                "entity_terms": [
                    str(item.get("term"))
                    for item in inventory
                    if isinstance(item, Mapping) and item.get("term")
                ],
                "relation_hint_families": [
                    str(item.get("relation_family"))
                    for item in relation_hints
                    if isinstance(item, Mapping) and item.get("relation_family")
                ],
                "claim_boundary": (
                    "Prompt context is advisory terminology only; extracted "
                    "candidate evidence must still be quoted from this chunk."
                ),
            }
        )
    return rows


def _normalize_document_understanding_map(
    response: Mapping[str, Any] | str,
    *,
    document: ParsedSourceDocument,
    chunks: Sequence[SourceTextChunk],
    mode: DocumentUnderstandingMode,
    fallback: Mapping[str, Any],
    reader_type: str,
    prompt_version: str,
) -> dict[str, Any]:
    payload = _coerce_document_understanding_payload(
        response,
        source_id=document.source_id,
        step_name=reader_type,
    )
    raw = payload.model_dump(mode="json", exclude_none=True)
    normalized = dict(fallback)
    for key in (
        "sections",
        "glossary",
        "entity_inventory",
        "relation_hints",
        "ontology_suggestions",
        "cross_chunk_proposals",
        "unresolved_questions",
        "review_hints",
        "agent_steps",
        "document_reading_plan",
    ):
        if key == "document_reading_plan":
            if isinstance(raw.get(key), Mapping):
                normalized[key] = dict(raw[key])
        elif key in raw:
            normalized[key] = _json_list(raw.get(key))
    normalized.update(
        {
            "artifact_type": "document_understanding_map_v1",
            "mode": mode,
            "source_id": document.source_id,
            "source_type": document.source_type,
            "scenario": document.scenario,
            "parser": document.parser,
            "text_sha1": sha1(document.text.encode("utf-8")).hexdigest(),
            "chunk_count": len(chunks),
            "reader_type": reader_type,
            "document_understanding_prompt_version": prompt_version,
            "claim_boundary": (
                str(raw.get("claim_boundary") or fallback.get("claim_boundary") or "").strip()
                or (
                    "Document understanding output is planning, terminology, and review "
                    "context only; it is not DraftKG, reviewed KG, or published KG."
                )
            ),
        }
    )
    normalized["cross_chunk_proposals"] = _dedupe_cross_chunk_proposals(
        [
            *_json_list(normalized.get("cross_chunk_proposals")),
            *_cross_chunk_proposals_from_relation_hints(
                _json_list(normalized.get("relation_hints"))
            ),
        ]
    )
    return normalized


def _coerce_document_understanding_payload(
    response: Mapping[str, Any] | str,
    *,
    source_id: str,
    step_name: str,
) -> DocumentUnderstandingMapPayload:
    try:
        if isinstance(response, str):
            payload = json.loads(response)
        elif isinstance(response, Mapping):
            payload = dict(response)
        else:
            raise TypeError(type(response).__name__)
        if not isinstance(payload, Mapping):
            raise TypeError(type(payload).__name__)
        payload = _normalize_document_understanding_response(payload)
        return DocumentUnderstandingMapPayload.model_validate(payload)
    except (TypeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            "invalid document understanding payload "
            f"(source_id={source_id!r}, step_name={step_name!r}): "
            "expected a JSON object matching document_understanding_map_v1"
        ) from exc


def _normalize_document_understanding_response(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize common LLM document-map shapes before schema validation."""
    normalized = dict(payload)
    if (
        "document_map" in normalized
        and isinstance(normalized["document_map"], Mapping)
        and not any(
            key in normalized
            for key in (
                "sections",
                "glossary",
                "entity_inventory",
                "relation_hints",
                "ontology_suggestions",
                "cross_chunk_proposals",
                "unresolved_questions",
                "review_hints",
            )
        )
    ):
        normalized = dict(normalized["document_map"])
    mapping_list_keys = {
        "sections": "title",
        "glossary": "term",
        "entity_inventory": "name",
        "relation_hints": "rationale",
        "ontology_suggestions": "label",
        "cross_chunk_proposals": "rationale",
        "unresolved_questions": "question",
        "agent_steps": "step_name",
    }
    for key, text_key in mapping_list_keys.items():
        if key in normalized:
            normalized[key] = _document_understanding_mapping_list(
                normalized.get(key),
                text_key=text_key,
            )
    if "review_hints" in normalized:
        normalized["review_hints"] = [
            _document_understanding_text(item)
            for item in _json_list(normalized.get("review_hints"))
            if _document_understanding_text(item)
        ]
    return normalized


def _document_understanding_mapping_list(
    value: Any,
    *,
    text_key: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _json_list(value):
        if isinstance(item, Mapping):
            rows.append(dict(item))
            continue
        text = _document_understanding_text(item)
        if text:
            rows.append({text_key: text})
    return rows


def _document_understanding_text(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("text", "question", "hint", "term", "name", "title", "rationale"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value).strip()


def _merge_document_understanding_step(
    merged_payload: dict[str, Any],
    step_output: Mapping[str, Any],
) -> None:
    for key in (
        "sections",
        "glossary",
        "entity_inventory",
        "relation_hints",
        "ontology_suggestions",
        "cross_chunk_proposals",
        "unresolved_questions",
        "review_hints",
    ):
        if key not in step_output:
            continue
        values = _json_list(step_output.get(key))
        if key == "review_hints":
            existing_hints = [
                str(item)
                for item in merged_payload.get(key, [])
                if isinstance(item, (str, int, float))
            ]
            for value in values:
                text = str(value)
                if text and text not in existing_hints:
                    existing_hints.append(text)
            merged_payload[key] = existing_hints
        else:
            merged_payload.setdefault(key, [])
            if isinstance(merged_payload[key], list):
                merged_payload[key].extend(values)


def _json_list(value: object) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return list(value)


def _cross_chunk_proposals_from_relation_hints(
    relation_hints: Sequence[Any],
) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for hint in relation_hints:
        if not isinstance(hint, Mapping):
            continue
        head = _first_text(hint.get("head"), hint.get("subject"), hint.get("source_node"))
        tail = _first_text(hint.get("tail"), hint.get("object"), hint.get("target_node"))
        relation = _first_text(hint.get("relation"), hint.get("predicate"))
        spans = hint.get("supporting_spans", hint.get("spans"))
        if not head or not tail or not relation or not isinstance(spans, list):
            continue
        proposals.append(
            {
                "head": head,
                "relation": relation,
                "tail": tail,
                "confidence": hint.get("confidence", 0.45),
                "relation_family": _first_text(hint.get("relation_family")) or relation,
                "supporting_spans": spans,
                "why_hint_only": (
                    _first_text(hint.get("why_hint_only"), hint.get("reason"))
                    or "derived from document-level relation hint"
                ),
            }
        )
    return proposals


def _dedupe_cross_chunk_proposals(proposals: Sequence[Any]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for proposal in proposals:
        if not isinstance(proposal, Mapping):
            continue
        payload = {str(key): value for key, value in proposal.items()}
        key = json.dumps(payload, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(payload)
    return deduped


class OpenAICompatibleKGExtractionClient:
    """OpenAI-compatible chat-completions client for document IE."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        use_json_schema: bool = True,
        client: Any | None = None,
        deepseek_thinking: DeepSeekThinkingPolicy | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL")
        self.model = model if model is not None else os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        self.temperature = temperature
        self.max_tokens = _openai_compatible_max_tokens(max_tokens)
        self.use_json_schema = use_json_schema
        self.deepseek_thinking = _stage_deepseek_thinking_policy(
            env_name="KGTRACEVIS_DOCUMENT_IE_DEEPSEEK_THINKING",
            default=deepseek_thinking or "disabled",
        )
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
        request_kwargs: dict[str, Any] = {}
        if response_format is not None:
            request_kwargs["response_format"] = response_format
        completion = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
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
            **request_kwargs,
            **_openai_compatible_request_options(
                model=self.model,
                base_url=self.base_url,
                deepseek_thinking=self.deepseek_thinking,
            ),
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError(f"OpenAI-compatible IE returned empty content for {chunk.chunk_id}")
        return _loads_json_object_payload(content)

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
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    def _response_format(self, response_schema: Mapping[str, Any]) -> dict[str, Any] | None:
        return _openai_compatible_response_format(
            response_schema=response_schema,
            schema_name="kgtracevis_document_ie",
            model=self.model,
            base_url=self.base_url,
            use_json_schema=self.use_json_schema,
        )


class OpenAICompatibleDocumentUnderstandingClient:
    """OpenAI-compatible chat-completions client for document understanding."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        use_json_schema: bool = True,
        client: Any | None = None,
        deepseek_thinking: DeepSeekThinkingPolicy | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL")
        self.model = model if model is not None else os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        self.temperature = temperature
        self.max_tokens = _openai_compatible_max_tokens(max_tokens)
        self.use_json_schema = use_json_schema
        self.deepseek_thinking = _stage_deepseek_thinking_policy(
            env_name="KGTRACEVIS_DOCUMENT_UNDERSTANDING_DEEPSEEK_THINKING",
            default=deepseek_thinking or "disabled",
        )
        self._client = client

    def understand_document(
        self,
        document: ParsedSourceDocument,
        chunks: Sequence[SourceTextChunk],
        *,
        mode: DocumentUnderstandingMode,
        step_name: str,
        prompt: str,
        response_schema: Mapping[str, Any],
        prior_steps: Sequence[Mapping[str, Any]] = (),
    ) -> Mapping[str, Any] | str:
        """Call an OpenAI-compatible model and return advisory DU JSON."""
        del chunks, mode, prior_steps
        client = self._resolved_client()
        response_format = self._response_format(response_schema)
        request_kwargs: dict[str, Any] = {}
        if response_format is not None:
            request_kwargs["response_format"] = response_format
        completion = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You produce advisory document-understanding maps for "
                        "source-grounded KG construction. Return JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            **request_kwargs,
            **_openai_compatible_request_options(
                model=self.model,
                base_url=self.base_url,
                deepseek_thinking=self.deepseek_thinking,
            ),
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError(
                "OpenAI-compatible document understanding returned empty content "
                f"for {document.source_id}:{step_name}"
            )
        return _loads_json_object_payload(content)

    def _resolved_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for OpenAI-compatible document understanding"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ImportError(
                "OpenAI-compatible document understanding requires the optional "
                "`openai` dependency. Install the project with the `llm` extra."
            ) from exc
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    def _response_format(self, response_schema: Mapping[str, Any]) -> dict[str, Any] | None:
        return _openai_compatible_response_format(
            response_schema=response_schema,
            schema_name="kgtracevis_document_understanding",
            model=self.model,
            base_url=self.base_url,
            use_json_schema=self.use_json_schema,
        )


def _openai_compatible_response_format(
    *,
    response_schema: Mapping[str, Any],
    schema_name: str,
    model: str,
    base_url: str | None,
    use_json_schema: bool,
) -> dict[str, Any] | None:
    """Return a provider-compatible response_format payload when supported."""
    if _is_deepseek_compatible(model=model, base_url=base_url):
        return {"type": "json_object"}
    if use_json_schema:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": dict(response_schema),
                "strict": False,
            },
        }
    return {"type": "json_object"}


def _openai_compatible_max_tokens(explicit: int | None) -> int:
    if explicit is not None:
        return max(1, int(explicit))
    raw = os.environ.get("OPENAI_MAX_TOKENS") or os.environ.get(
        "KGTRACEVIS_OPENAI_MAX_TOKENS"
    )
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            return 4096
    return 4096


def _is_deepseek_compatible(*, model: str, base_url: str | None) -> bool:
    provider_hint = f"{model} {base_url or ''}".lower()
    return "deepseek" in provider_hint


def _openai_compatible_request_options(
    *,
    model: str,
    base_url: str | None,
    deepseek_thinking: DeepSeekThinkingPolicy,
) -> dict[str, Any]:
    if not _is_deepseek_compatible(model=model, base_url=base_url):
        return {}
    if deepseek_thinking != "disabled":
        return {}
    return {"extra_body": {"thinking": {"type": "disabled"}}}


def _stage_deepseek_thinking_policy(
    *,
    env_name: str,
    default: DeepSeekThinkingPolicy,
) -> DeepSeekThinkingPolicy:
    raw = os.environ.get(env_name) or os.environ.get("KGTRACEVIS_DEEPSEEK_THINKING")
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"", "default", "provider_default", "none", "auto"}:
        return "default"
    if normalized == "disabled":
        return "disabled"
    raise ValueError(
        f"{env_name} must be one of default or disabled; got {raw!r}"
    )


def _loads_json_object_payload(content: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating fenced or prefaced model output."""
    try:
        payload = json.loads(content)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        try:
            payload = json.loads("\n".join(lines))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    candidate = _first_balanced_json_object(stripped)
    if candidate is not None:
        payload = json.loads(candidate)
        if isinstance(payload, dict):
            return payload
    snippet = stripped.replace("\n", " ")[:300]
    raise ValueError(
        "OpenAI-compatible response did not contain a JSON object"
        f"; response_prefix={snippet!r}"
    )


def _first_balanced_json_object(content: str) -> str | None:
    start = content.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(content[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[start : index + 1]
    return None


def _document_context_prompt(
    document_context: Mapping[str, Any] | None,
    *,
    chunk_id: str | None = None,
) -> str:
    if not document_context:
        return ""
    inventory_value = document_context.get("entity_inventory", [])
    glossary_value = document_context.get("glossary", [])
    hints_value = document_context.get("relation_hints", [])
    if chunk_id:
        inventory_items = _context_items_for_chunk(inventory_value, chunk_id, limit=12)
        glossary_items = _context_items_for_chunk(glossary_value, chunk_id, limit=8)
        hint_items = _context_items_for_chunk(hints_value, chunk_id, limit=8)
    else:
        inventory_items = [
            item for item in inventory_value if isinstance(item, Mapping)
        ][:12] if isinstance(inventory_value, Sequence) and not isinstance(
            inventory_value, (str, bytes)
        ) else []
        glossary_items = [
            item for item in glossary_value if isinstance(item, Mapping)
        ][:8] if isinstance(glossary_value, Sequence) and not isinstance(
            glossary_value, (str, bytes)
        ) else []
        hint_items = [
            item for item in hints_value if isinstance(item, Mapping)
        ][:8] if isinstance(hints_value, Sequence) and not isinstance(
            hints_value, (str, bytes)
        ) else []
    terms = [
        str(item.get("term"))
        for item in inventory_items
        if isinstance(item, Mapping) and item.get("term")
    ]
    glossary = [
        f"{item.get('term')}={item.get('expansion')}"
        for item in glossary_items
        if isinstance(item, Mapping) and item.get("term") and item.get("expansion")
    ]
    hints = [
        str(item.get("relation_family"))
        for item in hint_items
        if isinstance(item, Mapping) and item.get("relation_family")
    ]
    parts: list[str] = []
    if terms:
        parts.append(f"candidate terminology: {', '.join(terms)}")
    if glossary:
        parts.append(f"glossary hints: {'; '.join(glossary)}")
    if hints:
        parts.append(f"relation hint families: {', '.join(dict.fromkeys(hints))}")
    if not parts:
        return ""
    return (
        "Document-level context for terminology only. It may help resolve "
        "aliases, but every extracted entity/relation must still quote evidence "
        "from the current source text chunk.\n"
        + "\n".join(parts)
        + "\n\n"
    )


def _context_items_for_chunk(
    value: object,
    chunk_id: str,
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    scoped: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        item_chunk_ids = item.get("chunk_ids")
        if isinstance(item_chunk_ids, Sequence) and not isinstance(item_chunk_ids, (str, bytes)):
            if chunk_id in {str(candidate) for candidate in item_chunk_ids}:
                scoped.append(item)
    return scoped[:limit]


def _document_sections(
    text: str,
    chunks: Sequence[SourceTextChunk],
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for match in re.finditer(r"(?m)^(#{1,6}\s+)?([A-Z][^\n]{2,100})$", text):
        title = re.sub(r"^#{1,6}\s+", "", match.group(0)).strip()
        if not title or title.endswith("."):
            continue
        sections.append(
            {
                "title": title[:120],
                "char_start": match.start(),
                "char_end": match.end(),
                "chunk_ids": _chunk_ids_for_span(chunks, match.start(), match.end()),
            }
        )
        if len(sections) >= 12:
            break
    if sections:
        return sections
    return [
        {
            "title": f"chunk {chunk.index}",
            "char_start": chunk.start_char,
            "char_end": chunk.end_char,
            "chunk_ids": [chunk.chunk_id],
        }
        for chunk in chunks[:12]
    ]


def _document_glossary(
    text: str,
    chunks: Sequence[SourceTextChunk],
) -> list[dict[str, Any]]:
    glossary: list[dict[str, Any]] = []
    seen: set[str] = set()
    pattern = re.compile(r"\b([A-Z][A-Za-z][A-Za-z0-9 /-]{3,80})\s+\(([A-Z][A-Z0-9-]{1,12})\)")
    for match in pattern.finditer(text):
        expansion = match.group(1).strip()
        term = match.group(2).strip()
        if term in seen:
            continue
        seen.add(term)
        glossary.append(
            {
                "term": term,
                "expansion": expansion,
                "char_start": match.start(2),
                "char_end": match.end(2),
                "chunk_ids": _chunk_ids_for_span(chunks, match.start(), match.end()),
            }
        )
        if len(glossary) >= 20:
            break
    return glossary


def _document_entity_inventory(
    text: str,
    chunks: Sequence[SourceTextChunk],
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"\b(?:XMEAS|XMV|MV)\s*\d+\b|\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,3}\b"
    )
    for match in pattern.finditer(text):
        term = re.sub(r"\s+", " ", match.group(0)).strip()
        normalized = _squashed(term)
        if len(normalized) < 3 or normalized in {"the", "and", "for"}:
            continue
        item = candidates.setdefault(
            normalized,
            {
                "term": term[:100],
                "normalized": normalized,
                "occurrence_count": 0,
                "chunk_ids": [],
            },
        )
        item["occurrence_count"] += 1
        for chunk_id in _chunk_ids_for_span(chunks, match.start(), match.end()):
            if chunk_id not in item["chunk_ids"]:
                item["chunk_ids"].append(chunk_id)
    ranked = sorted(
        candidates.values(),
        key=lambda item: (-int(item["occurrence_count"]), str(item["term"]).lower()),
    )
    return ranked[:40]


def _document_relation_hints(
    text: str,
    chunks: Sequence[SourceTextChunk],
) -> list[dict[str, Any]]:
    patterns = {
        "CAUSES": r"\b(cause|causes|caused|root cause|due to|because of)\b",
        "OBSERVATION": r"\b(measure|measured|observed|sensor|signal|indicator)\b",
        "AFFECTS": r"\b(affect|affects|impact|impacts|influence|influences)\b",
        "DEPENDS_ON": r"\b(depend|depends|requires|upstream|downstream)\b",
    }
    hints: list[dict[str, Any]] = []
    for family, pattern in patterns.items():
        matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
        if not matches:
            continue
        chunk_ids: list[str] = []
        for match in matches[:8]:
            for chunk_id in _chunk_ids_for_span(chunks, match.start(), match.end()):
                if chunk_id not in chunk_ids:
                    chunk_ids.append(chunk_id)
        hints.append(
            {
                "relation_family": family,
                "mention_count": len(matches),
                "chunk_ids": chunk_ids,
                "review_status": "hint_only",
                "requires_chunk_evidence": True,
            }
        )
    return hints


def _ontology_suggestions(inventory: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for item in inventory[:20]:
        term = str(item.get("term") or "")
        label = _suggest_label(term)
        if label:
            suggestions.append(
                {
                    "term": term,
                    "suggested_label": label,
                    "review_status": "hint_only",
                }
            )
    return suggestions


def _suggest_label(term: str) -> str:
    lowered = term.lower()
    if re.search(r"\b(xmeas|xmv|mv)\s*\d+\b", lowered):
        return "Variable"
    if any(word in lowered for word in ("fault", "failure", "alarm", "alert")):
        return "Fault"
    if any(word in lowered for word in ("sensor", "signal", "measurement")):
        return "Signal"
    if any(word in lowered for word in ("pump", "reactor", "valve", "compressor")):
        return "Equipment"
    return ""


def _chunk_ids_for_span(
    chunks: Sequence[SourceTextChunk],
    start: int,
    end: int,
) -> list[str]:
    return [
        chunk.chunk_id
        for chunk in chunks
        if start < chunk.end_char and end > chunk.start_char
    ]


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
        payload = _normalize_extracted_payload_shape(payload)
        return ExtractedKGPayload.model_validate(payload)
    except (TypeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid IE payload for {chunk_id}") from exc


def _normalize_extracted_payload_shape(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize common LLM IE aliases before Pydantic validation."""
    normalized = dict(payload)
    entities = _json_list(
        normalized.get("entities")
        or normalized.get("nodes")
        or normalized.get("candidate_entities")
    )
    relations = _json_list(
        normalized.get("relations")
        or normalized.get("edges")
        or normalized.get("triples")
        or normalized.get("candidate_relations")
    )
    normalized_entities: list[dict[str, Any]] = []
    reference_map: dict[str, str] = {}
    for item in entities:
        if not isinstance(item, Mapping):
            continue
        entity = _normalize_extracted_entity_shape(item)
        normalized_entities.append(entity)
        normalized_ref = str(entity.get("id") or "").strip()
        for key in ("id", "entity_id", "node_id", "entity", "node", "value", "name"):
            raw_ref = str(item.get(key) or "").strip()
            if raw_ref and normalized_ref:
                reference_map[raw_ref] = normalized_ref
    normalized_relations = [
        _normalize_extracted_relation_shape(item, reference_map=reference_map)
        for item in relations
        if isinstance(item, Mapping)
    ]
    normalized_entities, normalized_relations = _repair_extracted_causal_self_links(
        normalized_entities,
        normalized_relations,
    )
    normalized["entities"] = normalized_entities
    normalized["relations"] = normalized_relations
    return normalized


def _normalize_extracted_entity_shape(item: Mapping[str, Any]) -> dict[str, Any]:
    entity = dict(item)
    entity.setdefault("id", entity.get("entity") or entity.get("node") or entity.get("value"))
    entity.setdefault("name", entity.get("text") or entity.get("id"))
    if _is_weak_extracted_entity_id(entity.get("id")):
        entity["id"] = entity.get("name")
    entity.setdefault("label", entity.get("type") or entity.get("category"))
    return entity


def _normalize_extracted_relation_shape(
    item: Mapping[str, Any],
    *,
    reference_map: Mapping[str, str],
) -> dict[str, Any]:
    relation = dict(item)
    relation.setdefault("head", relation.get("source") or relation.get("from"))
    relation.setdefault("tail", relation.get("target") or relation.get("to"))
    relation.setdefault("relation", relation.get("predicate") or relation.get("type"))
    head = str(relation.get("head") or "").strip()
    tail = str(relation.get("tail") or "").strip()
    if head in reference_map:
        relation["head"] = reference_map[head]
    if tail in reference_map:
        relation["tail"] = reference_map[tail]
    return relation


def _repair_extracted_causal_self_links(
    entities: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Turn source-grounded self-causal IE slips into reviewable cause candidates."""
    repaired_entities = [dict(entity) for entity in entities]
    repaired_relations: list[dict[str, Any]] = []
    entity_by_id = {
        str(entity.get("id") or "").strip(): dict(entity)
        for entity in repaired_entities
        if str(entity.get("id") or "").strip()
    }
    for relation_item in relations:
        relation = dict(relation_item)
        relation_name = _relation_alias_for_repair(relation.get("relation"))
        if relation_name not in CAUSAL_SUGGESTION_RELATIONS:
            repaired_relations.append(relation)
            continue

        head = str(relation.get("head") or "").strip()
        tail = str(relation.get("tail") or "").strip()
        if not _looks_like_causal_self_link(head, tail, entity_by_id=entity_by_id):
            repaired_relations.append(relation)
            continue

        cause_phrase = _extract_cause_phrase_from_evidence(relation.get("evidence"))
        if cause_phrase is None:
            repaired_relations.append(relation)
            continue

        cause_name = _cause_entity_name(cause_phrase)
        cause_id = _coerce_entity_id(
            cause_name,
            candidate="causal self-link repair entity",
        )
        if cause_id and cause_id not in entity_by_id:
            cause_entity = {
                "id": cause_id,
                "name": cause_name,
                "label": _cause_entity_label(cause_phrase),
                "evidence": cause_phrase,
                "confidence": relation.get("confidence"),
            }
            repaired_entities.append(cause_entity)
            entity_by_id[cause_id] = cause_entity
        if cause_id:
            relation["tail"] = cause_id
            relation["normalization_note"] = "causal_self_link_tail_repaired_from_evidence"
        repaired_relations.append(relation)
    return repaired_entities, repaired_relations


def _relation_alias_for_repair(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "")).strip("_").upper()
    return DOCUMENT_IE_RELATION_ALIASES.get(text, text)


def _looks_like_causal_self_link(
    head: str,
    tail: str,
    *,
    entity_by_id: Mapping[str, Mapping[str, Any]],
) -> bool:
    if not head or not tail:
        return False
    if _squashed(head) == _squashed(tail):
        return True
    head_entity = entity_by_id.get(head, {})
    tail_entity = entity_by_id.get(tail, {})
    head_name = str(head_entity.get("name") or head).strip()
    tail_name = str(tail_entity.get("name") or tail).strip()
    if _squashed(head_name) == _squashed(tail_name):
        return True
    return False


def _extract_cause_phrase_from_evidence(value: Any) -> str | None:
    evidence = str(value or "").strip()
    if not evidence:
        return None
    for pattern in CAUSAL_CAUSE_PHRASE_PATTERNS:
        match = pattern.search(evidence)
        if match is None:
            continue
        phrase = _clean_cause_phrase(match.group("cause"))
        if phrase is not None:
            return phrase
    return None


def _clean_cause_phrase(value: str) -> str | None:
    phrase = re.sub(r"\s+", " ", value).strip(" \t\r\n,")
    phrase = re.sub(r"^(?:the|a|an)\s+", "", phrase, flags=re.IGNORECASE)
    phrase = re.sub(
        r"\s+(?:and|or|which|that|when|where|because)\b.*$",
        "",
        phrase,
        flags=re.IGNORECASE,
    ).strip(" \t\r\n,")
    if not phrase or len(phrase) > 100:
        return None
    if not any(char.isalpha() for char in phrase):
        return None
    return phrase


def _cause_entity_name(cause_phrase: str) -> str:
    problem_pattern = r"\b(?:problem|problems|issue|issues|fault|faults|failure|failures)\b"
    if re.search(problem_pattern, cause_phrase, re.IGNORECASE):
        return cause_phrase
    return f"{cause_phrase} issue"


def _cause_entity_label(cause_phrase: str) -> str:
    if re.search(r"\bstep\b", cause_phrase, re.IGNORECASE):
        return "ProcessStep"
    if re.search(r"\b(?:machine|equipment|tool)\b", cause_phrase, re.IGNORECASE):
        return "Equipment"
    return "ProcessCondition"


def _is_weak_extracted_entity_id(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or not any(char.isalpha() for char in text):
        return True
    return re.fullmatch(r"(?i)(?:e|n|id|node|entity)\d{1,5}", text) is not None


def _normalize_extracted_entity_label(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return DOCUMENT_IE_LABEL_ALIASES.get(text.upper(), text)


def _normalize_extracted_entity_label_for_name(value: str, *, name: str, entity_id: str) -> str:
    label = _normalize_extracted_entity_label(value)
    normalized_name = _squashed(f"{name} {entity_id}")
    if re.search(r"\bwafer(?:\s*map)?\b", normalized_name):
        return "Wafer"
    return label


def _coerce_entity_candidates_for_chunk(
    candidate_entities: Sequence[ExtractedEntityPayload],
    *,
    chunk: SourceTextChunk,
    extractor_name: str,
    extractor_version: str,
    default_confidence: float,
    strict_grounding: bool,
    prompt_version: str,
) -> tuple[list[DraftEntity], list[str]]:
    entities: list[DraftEntity] = []
    errors: list[str] = []
    for index, entity in enumerate(candidate_entities, start=1):
        try:
            entities.append(
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
            )
        except ValueError as exc:
            errors.append(str(exc))
    return entities, errors


def _coerce_relation_candidates_for_chunk(
    candidate_relations: Sequence[ExtractedRelationPayload],
    *,
    chunk: SourceTextChunk,
    extractor_name: str,
    extractor_version: str,
    default_confidence: float,
    strict_grounding: bool,
    prompt_version: str,
) -> tuple[list[DraftRelation], list[str]]:
    relations: list[DraftRelation] = []
    errors: list[str] = []
    for index, relation in enumerate(candidate_relations, start=1):
        try:
            relations.append(
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
            )
        except ValueError as exc:
            errors.append(str(exc))
    return relations, errors


def _skipped_candidate_error_message(errors: Sequence[str]) -> str | None:
    if not errors:
        return None
    unique_errors = list(dict.fromkeys(errors))
    preview = "; ".join(unique_errors[:3])
    suffix = f"; +{len(unique_errors) - 3} more" if len(unique_errors) > 3 else ""
    return f"skipped {len(errors)} invalid IE candidate(s): {preview}{suffix}"


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
    label = _normalize_extracted_entity_label_for_name(
        _first_text(entity.label),
        name=name,
        entity_id=entity_id,
    )
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
