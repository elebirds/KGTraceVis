"""Tests for source material parsing and document IE draft KG extraction."""

from __future__ import annotations

import builtins
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from kgtracevis.kg_construction.document_extraction import (
    DEFAULT_DOCUMENT_IE_PROMPT_VERSION,
    OpenAICompatibleKGExtractionClient,
    SourceTextChunk,
    chunk_source_document,
    extract_draft_kg_from_chunks,
    extract_draft_kg_from_chunks_with_report,
    extract_draft_kg_from_source_material,
    extraction_response_schema,
    parse_source_material,
)
from kgtracevis.kg_construction.draft import KGConstructionSource


def test_parse_html_and_chunk_ids_are_deterministic() -> None:
    """HTML source material is parsed with stdlib fallback and stable chunk IDs."""
    source = KGConstructionSource(
        source_id="html_unit",
        source_type="html",
        scenario="tep",
        text=(
            "<html><head><style>.x{}</style><script>ignore()</script></head>"
            "<body><h1>Fault note</h1><p>Pump vibration is high.</p>"
            "<p>Seal wear is observed.</p></body></html>"
        ),
    )

    document = parse_source_material(source)
    chunks_a = chunk_source_document(document, max_chars=45, overlap_chars=5)
    chunks_b = chunk_source_document(document, max_chars=45, overlap_chars=5)

    assert "ignore" not in document.text
    assert "Fault note" in document.text
    assert len(chunks_a) >= 2
    assert [chunk.chunk_id for chunk in chunks_a] == [chunk.chunk_id for chunk in chunks_b]
    assert chunks_a[0].chunk_id.startswith("html_unit:chunk:0001:")


def test_parse_web_snapshot_json_extracts_visible_text() -> None:
    """Web snapshot JSON should parse title, URL, and HTML/text fields."""
    source = KGConstructionSource(
        source_id="snapshot_unit",
        source_type="web_snapshot",
        scenario="shared",
        text=(
            '{"title":"Maintenance note","url":"https://example.test/doc",'
            '"html":"<article><p>Cooling water flow dropped.</p></article>"}'
        ),
    )

    document = parse_source_material(source)

    assert document.parser == "web_snapshot"
    assert "Maintenance note" in document.text
    assert "https://example.test/doc" in document.text
    assert "Cooling water flow dropped." in document.text


def test_pdf_parsing_fails_clearly_without_optional_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF parsing is optional and reports the missing parser dependency."""
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "pypdf":
            raise ImportError("blocked optional parser")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError, match="pypdf"):
        parse_source_material(
            KGConstructionSource(
                source_id="pdf_unit",
                source_type="pdf",
                scenario="shared",
                path=pdf_path,
            )
        )


def test_fake_ie_client_converts_source_grounded_candidates_to_draft_kg() -> None:
    """External IE clients can be faked and converted into DraftKG candidates."""
    client = FakeIEClient(
        {
            "entities": [
                {
                    "id": "PumpCavitation",
                    "name": "Pump cavitation",
                    "label": "FaultEvent",
                    "aliases": "cavitation|pump cavitation",
                    "evidence": "Pump cavitation indicates seal wear.",
                    "confidence": 0.62,
                },
                {
                    "id": "SealWear",
                    "name": "Seal wear",
                    "label": "RootCause",
                    "evidence": "seal wear",
                },
            ],
            "relations": [
                {
                    "head": "PumpCavitation",
                    "relation": "suggests root cause",
                    "tail": "SealWear",
                    "evidence": "Pump cavitation indicates seal wear.",
                    "confidence": 0.58,
                }
            ],
        }
    )

    draft = extract_draft_kg_from_source_material(
        KGConstructionSource(
            source_id="maintenance_note",
            source_type="plain_text",
            scenario="tep",
            text="Pump cavitation indicates seal wear. Operators noted vibration.",
        ),
        client,
    )

    assert len(draft.entities) == 2
    assert len(draft.relations) == 1
    assert draft.entities[0].source_id == "maintenance_note"
    assert draft.entities[0].status == "draft"
    assert draft.entities[0].aliases == ("cavitation", "pump cavitation")
    relation = draft.relations[0]
    assert relation.source_id == "maintenance_note"
    assert relation.relation == "SUGGESTS_ROOT_CAUSE"
    assert relation.evidence == "Pump cavitation indicates seal wear."
    assert relation.confidence == 0.58
    assert relation.status == "draft"
    candidate = relation.to_candidate_triple()
    assert candidate.review_status == "auto"
    assert candidate.source == "maintenance_note"
    assert client.calls[0]["schema"]["title"] == "ExtractedKGPayload"


def test_extract_draft_kg_from_chunks_reuses_parser_output() -> None:
    """Document IE can run from already parsed chunks without reparsing sources."""
    chunk = SourceTextChunk(
        chunk_id="maintenance_note:chunk:0001:abc",
        source_id="maintenance_note",
        source_type="txt",
        scenario="shared",
        text="Cooling alert can suggest pump seal wear.",
        start_char=0,
        end_char=len("Cooling alert can suggest pump seal wear."),
        index=1,
    )
    client = FakeIEClient(
        {
            "entities": [
                {
                    "id": "CoolingAlert",
                    "name": "Cooling alert",
                    "label": "Event",
                    "evidence": "Cooling alert can suggest pump seal wear.",
                },
                {
                    "id": "PumpSealWear",
                    "name": "Pump seal wear",
                    "label": "RootCause",
                    "evidence": "pump seal wear",
                },
            ],
            "relations": [
                {
                    "head": "CoolingAlert",
                    "relation": "SUGGESTS_ROOT_CAUSE",
                    "tail": "PumpSealWear",
                    "evidence": "Cooling alert can suggest pump seal wear.",
                }
            ],
        }
    )

    draft = extract_draft_kg_from_chunks((chunk,), client)

    assert len(draft.entities) == 2
    assert len(draft.relations) == 1
    assert client.calls[0]["chunk_id"] == "maintenance_note:chunk:0001:abc"
    assert "Source text:" in client.calls[0]["prompt"]
    assert DEFAULT_DOCUMENT_IE_PROMPT_VERSION in client.calls[0]["prompt"]
    assert draft.relations[0].evidence_span == (
        f"maintenance_note:chunk:0001:abc:0-{len(chunk.text)}"
    )
    assert draft.relations[0].metadata["prompt_version"] == DEFAULT_DOCUMENT_IE_PROMPT_VERSION


def test_extract_draft_kg_from_chunks_with_report_summarizes_chunk_outcomes() -> None:
    """Product-facing audit reports stay separate from DraftKG candidates."""
    chunk = SourceTextChunk(
        chunk_id="maintenance_note:chunk:0001:abc",
        source_id="maintenance_note",
        source_type="txt",
        scenario="shared",
        text="Cooling alert can suggest pump seal wear.",
        start_char=0,
        end_char=len("Cooling alert can suggest pump seal wear."),
        index=1,
    )
    client = FakeIEClient(
        {
            "entities": [
                {
                    "id": "CoolingAlert",
                    "name": "Cooling alert",
                    "label": "Event",
                    "evidence": "Cooling alert",
                }
            ],
            "relations": [],
        }
    )

    result = extract_draft_kg_from_chunks_with_report(
        (chunk,),
        client,
        prompt_version="unit_prompt_v2",
    )

    assert len(result.draft.entities) == 1
    assert result.chunk_count == 1
    assert result.error_count == 0
    assert result.prompt_version == "unit_prompt_v2"
    assert result.chunk_summaries[0].status == "extracted"
    assert result.chunk_summaries[0].entity_count == 1
    assert result.draft.entities[0].metadata["prompt_version"] == "unit_prompt_v2"


def test_extract_draft_kg_from_chunks_with_report_can_continue_after_chunk_error() -> None:
    """Partial extraction failures should be visible without publishing facts."""
    chunks = (
        SourceTextChunk(
            chunk_id="maintenance_note:chunk:0001:abc",
            source_id="maintenance_note",
            source_type="txt",
            scenario="shared",
            text="Cooling alert can suggest pump seal wear.",
            start_char=0,
            end_char=39,
            index=1,
        ),
        SourceTextChunk(
            chunk_id="maintenance_note:chunk:0002:def",
            source_id="maintenance_note",
            source_type="txt",
            scenario="shared",
            text="This chunk will fail.",
            start_char=40,
            end_char=61,
            index=2,
        ),
    )
    client = FailingSecondChunkIEClient()

    result = extract_draft_kg_from_chunks_with_report(
        chunks,
        client,
        continue_on_chunk_error=True,
    )

    assert len(result.draft.entities) == 1
    assert result.error_count == 1
    assert [summary.status for summary in result.chunk_summaries] == ["extracted", "failed"]
    assert "simulated chunk failure" in str(result.chunk_summaries[1].error_message)


def test_strict_grounding_rejects_relation_without_source_evidence() -> None:
    """Ungrounded IE output should fail before becoming a reviewable relation."""
    client = FakeIEClient(
        {
            "entities": [],
            "relations": [
                {
                    "head": "A",
                    "relation": "CAUSES",
                    "tail": "B",
                    "evidence": "not in the source",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="not grounded"):
        extract_draft_kg_from_source_material(
            KGConstructionSource(
                source_id="strict_unit",
                source_type="plain_text",
                scenario="shared",
                text="Only grounded source text is here.",
            ),
            client,
        )


def test_document_ie_coerces_entity_ids_and_scenarios_before_draft_kg() -> None:
    """IE IDs are normalized to KG-safe node references before DraftKG conversion."""
    client = FakeIEClient(
        {
            "entities": [
                {
                    "id": "pump cavitation",
                    "name": "Pump cavitation",
                    "label": "FaultEvent",
                    "scenario": "TEP",
                    "evidence": "Pump cavitation indicates seal wear.",
                }
            ],
            "relations": [
                {
                    "head": "pump cavitation",
                    "relation": "suggests root cause",
                    "tail": "seal wear",
                    "scenario": "TEP",
                    "evidence": "Pump cavitation indicates seal wear.",
                }
            ],
        }
    )

    draft = extract_draft_kg_from_source_material(
        KGConstructionSource(
            source_id="coerce_unit",
            source_type="plain_text",
            scenario="TEP",
            text="Pump cavitation indicates seal wear.",
        ),
        client,
    )

    assert draft.entities[0].entity_id_suggestion == "PumpCavitation"
    assert draft.entities[0].scenario == "tep"
    assert draft.relations[0].head == "PumpCavitation"
    assert draft.relations[0].tail == "SealWear"
    assert draft.relations[0].relation == "SUGGESTS_ROOT_CAUSE"
    assert draft.relations[0].scenario == "tep"


def test_document_ie_rejects_invalid_scenario() -> None:
    """Scenario values must stay within the shared KG scenario contract."""
    client = FakeIEClient({"entities": [], "relations": []})

    with pytest.raises(ValueError, match="invalid scenario"):
        extract_draft_kg_from_source_material(
            KGConstructionSource(
                source_id="scenario_unit",
                source_type="plain_text",
                scenario="general_factory",
                text="Pump cavitation indicates seal wear.",
            ),
            client,
        )


def test_document_ie_rejects_out_of_scope_relation() -> None:
    """Document IE cannot pass arbitrary ungrounded vocabulary into DraftKG."""
    client = FakeIEClient(
        {
            "entities": [],
            "relations": [
                {
                    "head": "PumpCavitation",
                    "relation": "mentions",
                    "tail": "SealWear",
                    "evidence": "Pump cavitation indicates seal wear.",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="out-of-scope relation"):
        extract_draft_kg_from_source_material(
            KGConstructionSource(
                source_id="relation_unit",
                source_type="plain_text",
                scenario="tep",
                text="Pump cavitation indicates seal wear.",
            ),
            client,
        )


def test_openai_compatible_client_uses_json_schema_response_format() -> None:
    """The OpenAI wrapper can be tested through an injected fake client."""
    fake_openai = FakeOpenAIChatClient()
    chunk = SourceTextChunk(
        chunk_id="source:chunk:0001:abc",
        source_id="source",
        source_type="plain_text",
        scenario="shared",
        text="A source sentence.",
        start_char=0,
        end_char=18,
        index=1,
    )
    client = OpenAICompatibleKGExtractionClient(
        api_key="unit-key",
        model="unit-model",
        client=fake_openai,
        use_json_schema=True,
    )

    payload = client.extract_candidates(
        chunk,
        prompt="Extract.",
        response_schema=extraction_response_schema(),
    )

    assert payload == {"entities": [], "relations": []}
    request = fake_openai.requests[0]
    assert request["model"] == "unit-model"
    assert request["temperature"] == 0.0
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["name"] == "kgtracevis_document_ie"


def test_openai_compatible_deepseek_ie_disables_thinking_by_default() -> None:
    """Source-grounded IE should use fast deterministic DeepSeek defaults."""
    fake_openai = FakeOpenAIChatClient()
    chunk = SourceTextChunk(
        chunk_id="source:chunk:0001:abc",
        source_id="source",
        source_type="plain_text",
        scenario="shared",
        text="A source sentence.",
        start_char=0,
        end_char=18,
        index=1,
    )
    client = OpenAICompatibleKGExtractionClient(
        api_key="unit-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        client=fake_openai,
        use_json_schema=False,
    )

    client.extract_candidates(
        chunk,
        prompt="Extract.",
        response_schema=extraction_response_schema(),
    )

    request = fake_openai.requests[0]
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}


def test_openai_compatible_deepseek_thinking_can_use_provider_default() -> None:
    """Open-ended stages can opt out of forcing DeepSeek thinking disabled."""
    fake_openai = FakeOpenAIChatClient()
    chunk = SourceTextChunk(
        chunk_id="source:chunk:0001:abc",
        source_id="source",
        source_type="plain_text",
        scenario="shared",
        text="A source sentence.",
        start_char=0,
        end_char=18,
        index=1,
    )
    client = OpenAICompatibleKGExtractionClient(
        api_key="unit-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        client=fake_openai,
        use_json_schema=False,
        deepseek_thinking="default",
    )

    client.extract_candidates(
        chunk,
        prompt="Extract.",
        response_schema=extraction_response_schema(),
    )

    assert "extra_body" not in fake_openai.requests[0]


def test_chunk_ie_continue_on_error_skips_invalid_candidates() -> None:
    """Malformed candidates should be audited without failing the whole chunk."""
    chunk = SourceTextChunk(
        chunk_id="source:chunk:0001:abc",
        source_id="source",
        source_type="plain_text",
        scenario="shared",
        text="Pump cavitation indicates seal wear.",
        start_char=0,
        end_char=36,
        index=1,
    )
    client = FakeIEClient(
        {
            "entities": [
                {"text": "bad shape"},
                {
                    "id": "PumpCavitation",
                    "name": "Pump cavitation",
                    "label": "FaultEvent",
                    "evidence": "Pump cavitation",
                },
            ],
            "relations": [],
        }
    )

    result = extract_draft_kg_from_chunks_with_report(
        (chunk,),
        client,
        continue_on_chunk_error=True,
    )

    assert len(result.draft.entities) == 1
    assert result.chunk_summaries[0].status == "partial"
    assert "skipped 1 invalid IE candidate" in (
        result.chunk_summaries[0].error_message or ""
    )


class FakeIEClient:
    def __init__(self, payload: dict[str, Any] | str) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def extract_candidates(
        self,
        chunk: SourceTextChunk,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any] | str:
        self.calls.append({"chunk_id": chunk.chunk_id, "prompt": prompt, "schema": response_schema})
        return self.payload


class FailingSecondChunkIEClient:
    def extract_candidates(
        self,
        chunk: SourceTextChunk,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        del prompt, response_schema
        if chunk.index == 2:
            raise ValueError("simulated chunk failure")
        return {
            "entities": [
                {
                    "id": "CoolingAlert",
                    "name": "Cooling alert",
                    "label": "Event",
                    "evidence": "Cooling alert",
                }
            ],
            "relations": [],
        }


class FakeOpenAIChatClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"entities":[],"relations":[]}')
                )
            ]
        )
