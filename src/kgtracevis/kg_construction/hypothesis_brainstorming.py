"""Advisory RCA hypothesis brainstorming for source-constrained KG construction."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha1
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kgtracevis.kg_construction.document_extraction import (
    ALLOWED_DOCUMENT_IE_RELATIONS,
    DeepSeekThinkingPolicy,
    ParsedSourceDocument,
    SourceTextChunk,
    _loads_json_object_payload,
    _openai_compatible_request_options,
    _stage_deepseek_thinking_policy,
)
from kgtracevis.kg_construction.draft import DraftKG
from kgtracevis.kg_construction.review_queue import ReviewQueueItem

HypothesisMode = Literal["none", "brainstorm"]
HypothesisProvider = Literal["none", "openai", "offline_fixture"]
HypothesisInfluence = Literal["review_only", "prompt_context", "profile_suggestions"]

DEFAULT_HYPOTHESIS_BRAINSTORMING_PROMPT_VERSION = "hypothesis_brainstorming_prompt_v1"

HYPOTHESIS_REVIEW_ITEM_TYPES = frozenset(
    {
        "hypothesis_candidate",
        "causal_chain_candidate",
        "missing_evidence_request",
        "profile_gap_candidate",
        "alias_mapping_candidate",
        "variable_mapping_candidate",
        "semantic_policy_candidate",
        "rca_policy_candidate",
    }
)


class SupportingSpanPayload(BaseModel):
    """A copied source span supporting an advisory suggestion."""

    model_config = ConfigDict(extra="allow")

    chunk_id: str | None = None
    text: str | None = None
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)


class CandidateRelationPayload(BaseModel):
    """Relation proposed inside an advisory hypothesis."""

    model_config = ConfigDict(extra="allow")

    head: str
    relation: str
    tail: str
    relation_family: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class HypothesisPayload(BaseModel):
    """One RCA-oriented hypothesis, never a published KG fact."""

    model_config = ConfigDict(extra="allow")

    hypothesis_id: str | None = None
    hypothesis_type: str = "mechanism"
    claim: str
    candidate_entities: list[dict[str, Any]] = Field(default_factory=list)
    candidate_relations: list[CandidateRelationPayload] = Field(default_factory=list)
    supporting_spans: list[SupportingSpanPayload] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    rationale: str = ""
    risk: Literal["low", "medium", "high"] = "medium"
    recommended_review_action: str = "accept_as_hypothesis"
    validation_status: str = "review_required"


class SuggestionPayload(BaseModel):
    """Advisory alignment or semantic/profile suggestion."""

    model_config = ConfigDict(extra="allow")

    suggestion_id: str | None = None
    suggestion_type: str
    source_id: str | None = None
    candidate_alias: str | None = None
    candidate_canonical_id: str | None = None
    candidate_canonical_label: str | None = None
    edge_key: str | None = None
    proposed_relation_family: str | None = None
    proposed_propagation_enabled: bool | None = None
    proposed_propagation_direction: str | None = None
    proposed_rca_score: float | None = Field(default=None, ge=0.0, le=1.0)
    supporting_spans: list[SupportingSpanPayload] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    risk: Literal["low", "medium", "high"] = "medium"
    validation_status: str = "review_required"


class EvidenceTaskPayload(BaseModel):
    """Evidence collection task proposed by brainstorming."""

    model_config = ConfigDict(extra="allow")

    task_id: str | None = None
    task_type: str = "missing_evidence"
    question: str
    target_entities: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    rationale: str = ""
    risk: Literal["low", "medium", "high"] = "medium"
    recommended_review_action: str = "request_more_evidence"
    validation_status: str = "review_required"


class BrainstormingPayload(BaseModel):
    """Normalized brainstorming response payload."""

    model_config = ConfigDict(extra="allow")

    hypotheses: list[HypothesisPayload] = Field(default_factory=list)
    evidence_tasks: list[EvidenceTaskPayload] = Field(default_factory=list)
    profile_gaps: list[SuggestionPayload] = Field(default_factory=list)
    alignment_suggestions: list[SuggestionPayload] = Field(default_factory=list)
    semantic_layer_suggestions: list[SuggestionPayload] = Field(default_factory=list)
    review_items: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class HypothesisBrainstormingResult:
    """Normalized brainstorming artifacts and review items."""

    hypotheses: tuple[dict[str, Any], ...]
    evidence_tasks: tuple[dict[str, Any], ...]
    profile_gaps: tuple[dict[str, Any], ...]
    alignment_suggestions: tuple[dict[str, Any], ...]
    semantic_layer_suggestions: tuple[dict[str, Any], ...]
    review_items: tuple[ReviewQueueItem, ...]
    manifest: dict[str, Any]


class HypothesisBrainstormingClient(Protocol):
    """Protocol for deterministic, fixture, or OpenAI-compatible brainstorming."""

    def brainstorm(
        self,
        document: ParsedSourceDocument,
        chunks: Sequence[SourceTextChunk],
        *,
        document_map: Mapping[str, Any] | None,
        draft_kg: DraftKG | None,
        semantic_context: Mapping[str, Any] | None,
        prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any] | str:
        """Return advisory hypotheses and suggestions."""


class OfflineHypothesisFixtureClient:
    """Brainstorming client that replays a JSON fixture payload."""

    def __init__(self, fixture: Mapping[str, Any]) -> None:
        self.fixture = dict(fixture)
        self.calls: list[dict[str, Any]] = []

    def brainstorm(
        self,
        document: ParsedSourceDocument,
        chunks: Sequence[SourceTextChunk],
        *,
        document_map: Mapping[str, Any] | None,
        draft_kg: DraftKG | None,
        semantic_context: Mapping[str, Any] | None,
        prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any] | str:
        """Return the fixture payload and record call metadata for tests."""
        del response_schema
        self.calls.append(
            {
                "source_id": document.source_id,
                "chunk_count": len(chunks),
                "has_document_map": document_map is not None,
                "draft_entity_count": len(draft_kg.entities) if draft_kg is not None else 0,
                "semantic_context_keys": sorted((semantic_context or {}).keys()),
                "prompt": prompt,
            }
        )
        return self.fixture


class OpenAICompatibleHypothesisBrainstormingClient:
    """OpenAI-compatible chat-completions client for advisory brainstorming."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        use_json_schema: bool = True,
        client: Any | None = None,
        deepseek_thinking: DeepSeekThinkingPolicy | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL")
        self.model = model if model is not None else os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        self.temperature = temperature
        self.use_json_schema = use_json_schema
        self.deepseek_thinking = _stage_deepseek_thinking_policy(
            env_name="KGTRACEVIS_HYPOTHESIS_DEEPSEEK_THINKING",
            default=deepseek_thinking or "default",
        )
        self._client = client

    def brainstorm(
        self,
        document: ParsedSourceDocument,
        chunks: Sequence[SourceTextChunk],
        *,
        document_map: Mapping[str, Any] | None,
        draft_kg: DraftKG | None,
        semantic_context: Mapping[str, Any] | None,
        prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any] | str:
        """Call an OpenAI-compatible model and return advisory JSON."""
        del chunks, document_map, draft_kg, semantic_context
        client = self._resolved_client()
        completion = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You brainstorm review-only RCA KG hypotheses. Output "
                        "hypotheses and review items, never published KG facts."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format=self._response_format(response_schema),
            **_openai_compatible_request_options(
                model=self.model,
                base_url=self.base_url,
                deepseek_thinking=self.deepseek_thinking,
            ),
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError(
                "OpenAI-compatible hypothesis brainstorming returned empty "
                f"content for {document.source_id}"
            )
        return _loads_json_object_payload(content)

    def _resolved_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for hypothesis brainstorming")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "OpenAI-compatible hypothesis brainstorming requires the optional "
                "`openai` dependency. Install the project with the `llm` extra."
            ) from exc
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    def _response_format(self, response_schema: Mapping[str, Any]) -> dict[str, Any]:
        if self.use_json_schema:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "kgtracevis_hypothesis_brainstorming",
                    "schema": dict(response_schema),
                    "strict": False,
                },
            }
        return {"type": "json_object"}


def hypothesis_brainstorming_response_schema() -> dict[str, Any]:
    """Return the JSON schema requested from brainstorming clients."""
    return BrainstormingPayload.model_json_schema()


def run_hypothesis_brainstorming(
    document: ParsedSourceDocument,
    chunks: Sequence[SourceTextChunk],
    *,
    mode: HypothesisMode,
    provider: HypothesisProvider,
    influence: HypothesisInfluence,
    client: HypothesisBrainstormingClient | None = None,
    document_map: Mapping[str, Any] | None = None,
    draft_kg: DraftKG | None = None,
    semantic_context: Mapping[str, Any] | None = None,
    prompt_version: str = DEFAULT_HYPOTHESIS_BRAINSTORMING_PROMPT_VERSION,
) -> HypothesisBrainstormingResult:
    """Run optional advisory RCA brainstorming and normalize review artifacts."""
    if mode == "none":
        return _empty_result(
            document,
            chunks,
            mode=mode,
            provider=provider,
            influence=influence,
            prompt_version=prompt_version,
        )
    prompt = build_hypothesis_brainstorming_prompt(
        document,
        chunks,
        document_map=document_map,
        draft_kg=draft_kg,
        semantic_context=semantic_context,
        influence=influence,
        prompt_version=prompt_version,
    )
    if client is None and provider == "none":
        payload = _deterministic_brainstorming_payload(document, chunks)
        generator_type = "deterministic_fallback"
    else:
        if client is None:
            raise ValueError("hypothesis brainstorming client is required for provider")
        response = client.brainstorm(
            document,
            chunks,
            document_map=document_map,
            draft_kg=draft_kg,
            semantic_context=semantic_context,
            prompt=prompt,
            response_schema=hypothesis_brainstorming_response_schema(),
        )
        payload = _coerce_brainstorming_payload(response, source_id=document.source_id)
        generator_type = "client"
    return _normalized_result(
        document,
        chunks,
        payload=payload,
        mode=mode,
        provider=provider,
        influence=influence,
        prompt_version=prompt_version,
        generator_type=generator_type,
    )


def build_hypothesis_brainstorming_prompt(
    document: ParsedSourceDocument,
    chunks: Sequence[SourceTextChunk],
    *,
    document_map: Mapping[str, Any] | None,
    draft_kg: DraftKG | None,
    semantic_context: Mapping[str, Any] | None,
    influence: HypothesisInfluence,
    prompt_version: str = DEFAULT_HYPOTHESIS_BRAINSTORMING_PROMPT_VERSION,
) -> str:
    """Build a prompt that keeps brainstorming outside KG publication."""
    chunk_index = [
        {
            "chunk_id": chunk.chunk_id,
            "chunk_index": chunk.index,
            "char_span": f"{chunk.start_char}-{chunk.end_char}",
            "text_preview": " ".join(chunk.text.split())[:400],
        }
        for chunk in chunks
    ]
    draft_summary = {
        "entity_count": len(draft_kg.entities) if draft_kg is not None else 0,
        "relation_count": len(draft_kg.relations) if draft_kg is not None else 0,
    }
    return (
        f"Prompt version: {prompt_version}.\n"
        "Brainstorm RCA-oriented KG construction hypotheses for human review. "
        "Every output is a suggestion, not a fact. Do not write or imply "
        "published KG edges. Include supporting_spans copied from chunk text or "
        "explicit missing_evidence. Mark risk and recommended review action. "
        "Relation suggestions must use allowed relation values when proposing "
        f"candidate edges: {', '.join(sorted(ALLOWED_DOCUMENT_IE_RELATIONS))}.\n"
        f"Hypothesis influence mode: {influence}; this first implementation is "
        "review-queue bounded and must not alter extraction prompts with "
        "hypothesis claims.\n\n"
        f"source_id: {document.source_id}\n"
        f"source_type: {document.source_type}\n"
        f"scenario: {document.scenario}\n"
        f"parser: {document.parser}\n\n"
        "Document map JSON:\n"
        f"{json.dumps(document_map or {}, sort_keys=True)}\n\n"
        "Draft KG summary JSON:\n"
        f"{json.dumps(draft_summary, sort_keys=True)}\n\n"
        "Semantic context JSON:\n"
        f"{json.dumps(semantic_context or {}, sort_keys=True)}\n\n"
        "Chunk index JSON:\n"
        f"{json.dumps(chunk_index, sort_keys=True)}"
    )


def _coerce_brainstorming_payload(
    response: Mapping[str, Any] | str,
    *,
    source_id: str,
) -> BrainstormingPayload:
    try:
        if isinstance(response, str):
            raw = json.loads(response)
        elif isinstance(response, Mapping):
            raw = dict(response)
        else:
            raise TypeError(type(response).__name__)
        if not isinstance(raw, Mapping):
            raise TypeError(type(raw).__name__)
        raw = _normalize_brainstorming_response(raw)
        return BrainstormingPayload.model_validate(raw)
    except (TypeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            "invalid hypothesis brainstorming payload "
            f"(source_id={source_id!r}): expected a JSON object matching "
            "hypothesis_brainstorming_v1"
        ) from exc


def _normalize_brainstorming_response(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize common JSON-object LLM shapes before schema validation."""
    normalized = dict(raw)
    normalized["hypotheses"] = _normalize_mapping_list(
        raw.get("hypotheses"),
        normalizer=_normalize_hypothesis_row,
    )
    normalized["evidence_tasks"] = _normalize_mapping_list(
        raw.get("evidence_tasks"),
        normalizer=_normalize_evidence_task_row,
    )
    normalized["profile_gaps"] = _normalize_mapping_list(
        raw.get("profile_gaps"),
        normalizer=lambda row: _normalize_suggestion_row(row, "profile_gap"),
    )
    normalized["alignment_suggestions"] = _normalize_mapping_list(
        raw.get("alignment_suggestions"),
        normalizer=lambda row: _normalize_suggestion_row(row, "alias_mapping"),
    )
    normalized["semantic_layer_suggestions"] = _normalize_mapping_list(
        raw.get("semantic_layer_suggestions"),
        normalizer=lambda row: _normalize_suggestion_row(
            row, "semantic_policy_gap_candidate"
        ),
    )
    if raw.get("review_items") is None:
        normalized["review_items"] = []
    return normalized


def _normalize_mapping_list(
    value: Any,
    *,
    normalizer: Any,
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(type(value).__name__)
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            rows.append(normalizer(dict(item)))
    return rows


def _normalize_hypothesis_row(row: dict[str, Any]) -> dict[str, Any]:
    claim = _first_non_empty(
        row.get("claim"),
        row.get("hypothesis"),
        row.get("hypothesis_claim"),
        row.get("hypothesis_statement"),
        row.get("proposed_hypothesis"),
        row.get("description"),
        row.get("summary"),
        row.get("title"),
        row.get("mechanism"),
        row.get("rationale"),
    )
    row["claim"] = str(
        claim
        or _claim_from_relation_preview(row.get("candidate_relations"))
        or _claim_from_span_preview(row.get("supporting_spans"))
        or "Unspecified LLM brainstorming hypothesis; review source payload before use."
    )
    row.setdefault("hypothesis_type", "mechanism")
    row["supporting_spans"] = _normalize_spans(row.get("supporting_spans"))
    row["missing_evidence"] = _normalize_string_list(row.get("missing_evidence"))
    row["candidate_entities"] = _normalize_candidate_entities(
        row.get("candidate_entities")
    )
    row["candidate_relations"] = _normalize_candidate_relations(
        row.get("candidate_relations")
    )
    row["risk"] = _normalize_risk(row.get("risk"))
    row["recommended_review_action"] = str(
        _first_non_empty(
            row.get("recommended_review_action"),
            row.get("recommended_action"),
            row.get("suggested_review_action"),
            "accept_as_hypothesis",
        )
    )
    row.setdefault("validation_status", "review_required")
    return row


def _normalize_evidence_task_row(row: dict[str, Any]) -> dict[str, Any]:
    question = _first_non_empty(
        row.get("question"),
        row.get("claim"),
        row.get("description"),
        row.get("summary"),
        row.get("rationale"),
    )
    if question:
        row["question"] = question
    row["missing_evidence"] = _normalize_string_list(row.get("missing_evidence"))
    row["risk"] = _normalize_risk(row.get("risk"))
    row["recommended_review_action"] = str(
        _first_non_empty(row.get("recommended_review_action"), "request_more_evidence")
    )
    row.setdefault("validation_status", "review_required")
    return row


def _normalize_suggestion_row(row: dict[str, Any], default_type: str) -> dict[str, Any]:
    row["suggestion_type"] = str(
        _first_non_empty(row.get("suggestion_type"), row.get("type"), default_type)
    )
    row["supporting_spans"] = _normalize_spans(row.get("supporting_spans"))
    row["missing_evidence"] = _normalize_string_list(row.get("missing_evidence"))
    row["risk"] = _normalize_risk(row.get("risk"))
    row.setdefault("validation_status", "review_required")
    return row


def _normalize_spans(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        value = [value]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        value = [value]
    spans: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            span = dict(item)
            text = _first_non_empty(span.get("text"), span.get("evidence"), span.get("quote"))
            if text:
                span["text"] = str(text)
            spans.append(span)
        else:
            text = str(item).strip()
            if text:
                spans.append({"text": text})
    return spans


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"none", "none.", "n/a", "na"}:
            return []
        return [stripped]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        value = [value]
    items: list[str] = []
    for item in value:
        stripped = str(item).strip()
        if stripped and stripped.lower() not in {"none", "none.", "n/a", "na"}:
            items.append(stripped)
    return items


def _normalize_candidate_entities(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        value = [value]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        value = [value]
    entities: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            entities.append(dict(item))
        else:
            text = str(item).strip()
            if text:
                entities.append({"name": text})
    return entities


def _normalize_candidate_relations(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        value = [value]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    relations: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        relation = dict(item)
        relation.setdefault("head", relation.get("source") or relation.get("from"))
        relation.setdefault("tail", relation.get("target") or relation.get("to"))
        relation.setdefault(
            "relation",
            relation.get("predicate") or relation.get("relation_type") or "RELATED_TO",
        )
        if relation.get("head") and relation.get("tail") and relation.get("relation"):
            relations.append(relation)
    return relations


def _claim_from_relation_preview(value: Any) -> str | None:
    relations = _normalize_candidate_relations(value)
    if not relations:
        return None
    relation = relations[0]
    return (
        f"{relation.get('head')} {relation.get('relation')} {relation.get('tail')}"
    )


def _claim_from_span_preview(value: Any) -> str | None:
    spans = _normalize_spans(value)
    for span in spans:
        text = str(span.get("text") or "").strip()
        if text:
            return text[:240]
    return None


def _normalize_risk(value: Any) -> Literal["low", "medium", "high"]:
    normalized = str(value or "medium").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized  # type: ignore[return-value]
    return "medium"


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
        else:
            return value
    return None


def _deterministic_brainstorming_payload(
    document: ParsedSourceDocument,
    chunks: Sequence[SourceTextChunk],
) -> BrainstormingPayload:
    del chunks
    return BrainstormingPayload(
        evidence_tasks=[
            EvidenceTaskPayload(
                question=(
                    "Review whether source-specific RCA hypotheses are needed for "
                    f"{document.source_id} before enabling propagation."
                ),
                missing_evidence=[
                    "human-reviewed source spans supporting any proposed RCA edge"
                ],
                rationale=(
                    "No external hypothesis provider was configured; this fallback "
                    "records a review-only evidence task instead of inventing facts."
                ),
                risk="low",
            )
        ]
    )


def _normalized_result(
    document: ParsedSourceDocument,
    chunks: Sequence[SourceTextChunk],
    *,
    payload: BrainstormingPayload,
    mode: HypothesisMode,
    provider: HypothesisProvider,
    influence: HypothesisInfluence,
    prompt_version: str,
    generator_type: str,
) -> HypothesisBrainstormingResult:
    hypotheses = tuple(
        _hypothesis_record(item, document=document, index=index)
        for index, item in enumerate(payload.hypotheses, start=1)
    )
    evidence_tasks = tuple(
        _evidence_task_record(item, document=document, index=index)
        for index, item in enumerate(payload.evidence_tasks, start=1)
    )
    profile_gaps = tuple(
        _suggestion_record(item, document=document, index=index, default_type="profile_gap")
        for index, item in enumerate(payload.profile_gaps, start=1)
    )
    alignment_suggestions = tuple(
        _suggestion_record(item, document=document, index=index, default_type="alias_mapping")
        for index, item in enumerate(payload.alignment_suggestions, start=1)
    )
    semantic_layer_suggestions = tuple(
        _suggestion_record(
            item,
            document=document,
            index=index,
            default_type="semantic_policy_gap_candidate",
        )
        for index, item in enumerate(payload.semantic_layer_suggestions, start=1)
    )
    review_items = [
        *_review_items_from_hypotheses(hypotheses),
        *_review_items_from_evidence_tasks(evidence_tasks),
        *_review_items_from_suggestions(profile_gaps),
        *_review_items_from_suggestions(alignment_suggestions),
        *_review_items_from_suggestions(semantic_layer_suggestions),
        *_explicit_review_items(payload.review_items, document=document),
    ]
    manifest = {
        "artifact_type": "hypothesis_brainstorming_manifest_v1",
        "source_id": document.source_id,
        "scenario": document.scenario,
        "mode": mode,
        "provider": provider,
        "influence": influence,
        "prompt_version": prompt_version,
        "generator_type": generator_type,
        "chunk_count": len(chunks),
        "hypothesis_count": len(hypotheses),
        "evidence_task_count": len(evidence_tasks),
        "profile_gap_count": len(profile_gaps),
        "alignment_suggestion_count": len(alignment_suggestions),
        "semantic_layer_suggestion_count": len(semantic_layer_suggestions),
        "review_item_count": len(review_items),
        "claim_boundary": (
            "Hypothesis brainstorming output is review-only advisory input. It "
            "does not write DraftKG, SemanticKG, PublishedKG, or RCA propagation "
            "policy without explicit review."
        ),
    }
    return HypothesisBrainstormingResult(
        hypotheses=hypotheses,
        evidence_tasks=evidence_tasks,
        profile_gaps=profile_gaps,
        alignment_suggestions=alignment_suggestions,
        semantic_layer_suggestions=semantic_layer_suggestions,
        review_items=tuple(review_items),
        manifest=manifest,
    )


def _empty_result(
    document: ParsedSourceDocument,
    chunks: Sequence[SourceTextChunk],
    *,
    mode: HypothesisMode,
    provider: HypothesisProvider,
    influence: HypothesisInfluence,
    prompt_version: str,
) -> HypothesisBrainstormingResult:
    return _normalized_result(
        document,
        chunks,
        payload=BrainstormingPayload(),
        mode=mode,
        provider=provider,
        influence=influence,
        prompt_version=prompt_version,
        generator_type="disabled",
    )


def _hypothesis_record(
    item: HypothesisPayload,
    *,
    document: ParsedSourceDocument,
    index: int,
) -> dict[str, Any]:
    record = item.model_dump(mode="json", exclude_none=True)
    record.setdefault(
        "hypothesis_id",
        _stable_id("hyp", document.source_id, index, record),
    )
    record["source_id"] = document.source_id
    record["scenario"] = document.scenario
    record["validation_status"] = _validated_hypothesis_status(record)
    record.setdefault("claim_boundary", "hypothesis only; not a reviewed KG fact")
    return record


def _evidence_task_record(
    item: EvidenceTaskPayload,
    *,
    document: ParsedSourceDocument,
    index: int,
) -> dict[str, Any]:
    record = item.model_dump(mode="json", exclude_none=True)
    record.setdefault("task_id", _stable_id("evidence_task", document.source_id, index, record))
    record["source_id"] = document.source_id
    record["scenario"] = document.scenario
    record["validation_status"] = (
        "review_required" if record.get("question") else "rejected"
    )
    return record


def _suggestion_record(
    item: SuggestionPayload,
    *,
    document: ParsedSourceDocument,
    index: int,
    default_type: str,
) -> dict[str, Any]:
    record = item.model_dump(mode="json", exclude_none=True)
    record.setdefault("suggestion_type", default_type)
    record.setdefault("suggestion_id", _stable_id("suggestion", document.source_id, index, record))
    record.setdefault("source_id", document.source_id)
    record["scenario"] = document.scenario
    record.setdefault("validation_status", "review_required")
    record.setdefault("claim_boundary", "suggestion only; profile/policy remains authoritative")
    return record


def _validated_hypothesis_status(record: Mapping[str, Any]) -> str:
    if record.get("supporting_spans") or record.get("missing_evidence"):
        return str(record.get("validation_status") or "review_required")
    return "rejected"


def _review_items_from_hypotheses(
    hypotheses: Sequence[Mapping[str, Any]],
) -> list[ReviewQueueItem]:
    items: list[ReviewQueueItem] = []
    for hypothesis in hypotheses:
        if hypothesis.get("validation_status") != "review_required":
            continue
        hypothesis_type = str(hypothesis.get("hypothesis_type") or "mechanism")
        item_type = (
            "causal_chain_candidate"
            if hypothesis_type == "causal_chain" or hypothesis.get("candidate_relations")
            else "hypothesis_candidate"
        )
        items.append(
            _review_item(
                target_key=f"{item_type}:{hypothesis['hypothesis_id']}",
                item_type=item_type,
                priority=86 if item_type == "causal_chain_candidate" else 72,
                reason="brainstormed RCA hypothesis requires review before any KG use",
                payload=dict(hypothesis),
                source=str(hypothesis.get("source_id") or "hypothesis_brainstorming"),
                scenario=str(hypothesis.get("scenario") or "shared"),
                evidence=_record_evidence(hypothesis),
                confidence=_record_confidence(hypothesis),
                relation_family="HYPOTHESIS",
                graph_impact=(
                    "can stage reviewed edges only if endpoints, relation, and evidence validate"
                    if item_type == "causal_chain_candidate"
                    else "records an accepted hypothesis without mutating KG edges"
                ),
                recommended_action=str(
                    hypothesis.get("recommended_review_action") or "accept_or_reject"
                ),
            )
        )
    return items


def _review_items_from_evidence_tasks(
    evidence_tasks: Sequence[Mapping[str, Any]],
) -> list[ReviewQueueItem]:
    items: list[ReviewQueueItem] = []
    for task in evidence_tasks:
        if task.get("validation_status") != "review_required":
            continue
        items.append(
            _review_item(
                target_key=f"missing_evidence_request:{task['task_id']}",
                item_type="missing_evidence_request",
                priority=60,
                reason="brainstorming identified missing evidence needed before KG changes",
                payload=dict(task),
                source=str(task.get("source_id") or "hypothesis_brainstorming"),
                scenario=str(task.get("scenario") or "shared"),
                evidence="; ".join(task.get("missing_evidence") or []) or str(task["question"]),
                confidence=0.0,
                relation_family="EVIDENCE_TASK",
                graph_impact="records evidence task; does not write KG edges",
                recommended_action=str(
                    task.get("recommended_review_action") or "request_more_evidence"
                ),
            )
        )
    return items


def _review_items_from_suggestions(
    suggestions: Sequence[Mapping[str, Any]],
) -> list[ReviewQueueItem]:
    items: list[ReviewQueueItem] = []
    for suggestion in suggestions:
        if suggestion.get("validation_status") != "review_required":
            continue
        item_type = _suggestion_item_type(str(suggestion.get("suggestion_type") or ""))
        items.append(
            _review_item(
                target_key=f"{item_type}:{suggestion['suggestion_id']}",
                item_type=item_type,
                priority=_suggestion_priority(item_type),
                reason="LLM-assisted construction suggestion requires human review",
                payload=dict(suggestion),
                source=str(suggestion.get("source_id") or "hypothesis_brainstorming"),
                scenario=str(suggestion.get("scenario") or "shared"),
                evidence=_record_evidence(suggestion),
                confidence=_record_confidence(suggestion),
                relation_family=_suggestion_relation_family(item_type),
                graph_impact=_suggestion_graph_impact(item_type),
                recommended_action="accept_or_reject_review_only",
            )
        )
    return items


def _explicit_review_items(
    rows: Sequence[Mapping[str, Any]],
    *,
    document: ParsedSourceDocument,
) -> list[ReviewQueueItem]:
    items: list[ReviewQueueItem] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        item_type = str(row.get("item_type") or "").strip()
        if item_type not in HYPOTHESIS_REVIEW_ITEM_TYPES:
            continue
        target_key = str(row.get("target_key") or "").strip()
        if not target_key:
            review_id = _stable_id(
                "review",
                document.source_id,
                len(items) + 1,
                row,
            )
            target_key = f"{item_type}:{review_id}"
        payload = row.get("candidate_payload")
        if not isinstance(payload, Mapping):
            payload = dict(row)
        items.append(
            _review_item(
                target_key=target_key,
                item_type=item_type,
                priority=int(row.get("priority") or 70),
                reason=str(row.get("reason") or "advisory brainstorming review item"),
                payload=dict(payload),
                source=str(row.get("source") or document.source_id),
                scenario=str(row.get("scenario") or document.scenario),
                evidence=str(row.get("evidence") or _record_evidence(payload)),
                confidence=_record_confidence(row),
                relation_family=str(row.get("relation_family") or "HYPOTHESIS"),
                graph_impact=str(row.get("graph_impact") or "review-only suggestion"),
                recommended_action=str(row.get("recommended_action") or "accept_or_reject"),
            )
        )
    return items


def _review_item(
    *,
    target_key: str,
    item_type: str,
    priority: int,
    reason: str,
    payload: dict[str, Any],
    source: str,
    scenario: str,
    evidence: str,
    confidence: float,
    relation_family: str,
    graph_impact: str,
    recommended_action: str,
) -> ReviewQueueItem:
    payload.setdefault("target_key", target_key)
    payload.setdefault("item_type", item_type)
    return ReviewQueueItem(
        target_key=target_key,
        item_type=item_type,
        priority=priority,
        reason=reason,
        candidate_payload=payload,
        source=source,
        evidence=evidence,
        confidence=confidence,
        review_status="auto",
        scenario=scenario,
        relation_family=relation_family,
        graph_impact=graph_impact,
        recommended_action=recommended_action,
    )


def _suggestion_item_type(suggestion_type: str) -> str:
    normalized = suggestion_type.strip().lower()
    if normalized in {"alias_mapping", "canonical_entity_mapping"}:
        return "alias_mapping_candidate"
    if normalized == "variable_mapping":
        return "variable_mapping_candidate"
    if normalized in {"relation_family_candidate", "semantic_policy_gap_candidate"}:
        return "semantic_policy_candidate"
    if normalized == "rca_policy_candidate":
        return "rca_policy_candidate"
    return "profile_gap_candidate"


def _suggestion_priority(item_type: str) -> int:
    return {
        "alias_mapping_candidate": 82,
        "variable_mapping_candidate": 82,
        "semantic_policy_candidate": 84,
        "rca_policy_candidate": 88,
        "profile_gap_candidate": 70,
    }.get(item_type, 65)


def _suggestion_relation_family(item_type: str) -> str:
    if item_type in {"alias_mapping_candidate", "variable_mapping_candidate"}:
        return "ALIGNMENT"
    if item_type in {"semantic_policy_candidate", "rca_policy_candidate"}:
        return "SEMANTIC_POLICY"
    return "PROFILE_GAP"


def _suggestion_graph_impact(item_type: str) -> str:
    if item_type in {"alias_mapping_candidate", "variable_mapping_candidate"}:
        return "records accepted mapping override for future rerun; current KG is unchanged"
    if item_type in {"semantic_policy_candidate", "rca_policy_candidate"}:
        return "can update existing reviewed edge policy only after whitelist and cap checks"
    return "records accepted profile gap; profile file is unchanged"


def _record_evidence(record: Mapping[str, Any]) -> str:
    spans = record.get("supporting_spans")
    parts: list[str] = []
    if isinstance(spans, Sequence) and not isinstance(spans, (str, bytes)):
        for span in spans:
            if not isinstance(span, Mapping):
                continue
            text = str(span.get("text") or span.get("evidence") or "").strip()
            if text:
                parts.append(text)
    if not parts:
        missing = record.get("missing_evidence")
        if isinstance(missing, Sequence) and not isinstance(missing, (str, bytes)):
            parts.extend(str(item) for item in missing if str(item).strip())
    return "; ".join(dict.fromkeys(parts)) or str(record.get("rationale") or "")


def _record_confidence(record: Mapping[str, Any]) -> float:
    value = record.get("confidence", record.get("proposed_rca_score", 0.0))
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _stable_id(prefix: str, source_id: str, index: int, payload: Mapping[str, Any]) -> str:
    digest = sha1(
        json.dumps(
            {"source_id": source_id, "index": index, "payload": dict(payload)},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"{prefix}_{digest}"
