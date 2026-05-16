"""Tests for the KGBuilder-style source KG compiler."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from threading import Lock

import pytest

from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.source_kg_compiler import (
    SourceKGCompilerConfig,
    run_source_kg_compiler_workflow,
)


class FakeKGBuilderLLM:
    """Deterministic fake for the three KGBuilder LLM stages."""

    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        self.input_tokens += len(user_prompt.split())
        self.output_tokens += 12
        if "knowledge cards" in system_prompt:
            return json.dumps(
                {
                    "cards": [
                        {
                            "card_id": "llm_card",
                            "scenario": "mvtec",
                            "claim": "ScratchDefect HAS_MORPHOLOGY LinearMorphology",
                            "entities_mentioned": ["ScratchDefect", "LinearMorphology"],
                            "relation_hints": [
                                "ScratchDefect HAS_MORPHOLOGY LinearMorphology"
                            ],
                            "source_chunk_id": "ignored",
                            "source_material_ids": ["mvtec_notes"],
                            "evidence_text": (
                                "Scratch defects appear as linear morphology in this source."
                            ),
                        }
                    ]
                }
            )
        if "canonical entities" in system_prompt:
            return json.dumps(
                {
                    "entities": [
                        {
                            "entity_id": "ScratchDefect",
                            "canonical_name": "ScratchDefect",
                            "entity_type": "Defect",
                            "aliases": ["scratch"],
                            "description": "Surface scratch defect.",
                            "scenario": "mvtec",
                            "source_card_ids": ["card_0001", "card_0002"],
                        },
                        {
                            "entity_id": "LinearMorphology",
                            "canonical_name": "LinearMorphology",
                            "entity_type": "Morphology",
                            "aliases": [],
                            "description": "Linear visual morphology.",
                            "scenario": "mvtec",
                            "source_card_ids": ["card_0002"],
                        },
                        {
                            "entity_id": "MechanicalContact",
                            "canonical_name": "MechanicalContact",
                            "entity_type": "CandidateCause",
                            "aliases": [],
                            "description": "Possible mechanical contact cause.",
                            "scenario": "mvtec",
                            "source_card_ids": ["card_0003"],
                        },
                    ]
                }
            )
        if "construct edges" in system_prompt:
            return json.dumps(
                {
                    "edges": [
                        {
                            "edge_id": "edge_0001",
                            "source": "ScratchDefect",
                            "relation": "HAS_MORPHOLOGY",
                            "target": "LinearMorphology",
                            "scenario": "mvtec",
                            "evidence": (
                                "Scratch defects appear as linear morphology in this source."
                            ),
                            "source_card_ids": ["card_0002"],
                            "confidence": 0.82,
                            "review_status": "auto",
                        },
                        {
                            "edge_id": "edge_0002",
                            "source": "ScratchDefect",
                            "relation": "HAS_PLAUSIBLE_CAUSE",
                            "target": "MechanicalContact",
                            "scenario": "mvtec",
                            "evidence": (
                                "Mechanical contact is a plausible investigation target."
                            ),
                            "source_card_ids": ["card_0003"],
                            "confidence": 0.64,
                            "review_status": "auto",
                        },
                    ]
                }
            )
        if "reasoning profiles" in system_prompt:
            return json.dumps(
                {
                    "profiles": {
                        "mvtec": {
                            "object_defect_profiles": [
                                {
                                    "object_id": "CableObject",
                                    "defect_id": "ScratchDefect",
                                    "candidate_causes": ["MechanicalContact"],
                                    "morphologies": ["LinearMorphology"],
                                    "locations": [],
                                    "evidence_requirements": [],
                                    "source_edge_ids": ["edge_0001"],
                                }
                            ]
                        }
                    }
                }
            )
        raise AssertionError(system_prompt)

    def repair_json(self, broken_json: str, error: str) -> str:
        return broken_json


class ConcurrencyTrackingLLM:
    """Fake LLM that records active calls while emitting an empty LLM graph."""

    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.active_calls = 0
        self.max_active_calls = 0
        self._lock = Lock()

    @property
    def total_tokens(self) -> int:
        with self._lock:
            return self.input_tokens + self.output_tokens

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        with self._lock:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            time.sleep(0.02)
            with self._lock:
                self.calls += 1
                self.input_tokens += len(user_prompt.split())
                self.output_tokens += 4
            if "knowledge cards" in system_prompt:
                return json.dumps({"cards": []})
            if "canonical entities" in system_prompt:
                return json.dumps({"entities": []})
            if "construct edges" in system_prompt:
                return json.dumps({"edges": []})
            if "reasoning profiles" in system_prompt:
                return json.dumps({"profiles": {}})
            raise AssertionError(system_prompt)
        finally:
            with self._lock:
                self.active_calls -= 1

    def repair_json(self, broken_json: str, error: str) -> str:
        return broken_json


def test_source_kg_compiler_writes_llm_artifact_chain(tmp_path: Path) -> None:
    """LLM cards/entities/edges should produce generated-only KG artifacts."""
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "mvtec_notes.md").write_text(
        "\n".join(
            [
                "SCENARIO: mvtec",
                "ENTITY: Scratch defect | label=Defect | aliases=scratch",
                (
                    "RELATION: ScratchDefect | has plausible cause | MechanicalContact "
                    "| head_label=Defect | tail_label=CandidateCause | confidence=0.61 "
                    "| evidence=Mechanical contact is a plausible investigation target."
                ),
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "compiled"
    llm = FakeKGBuilderLLM()

    result = run_source_kg_compiler_workflow(
        SourceKGCompilerConfig(
            source_paths=(source_dir,),
            output_dir=output_dir,
            llm_client=llm,
        )
    )

    expected_files = [
        "source_units.jsonl",
        "knowledge_cards.jsonl",
        "entities.jsonl",
        "edges.jsonl",
        "nodes.csv",
        "edges.csv",
        "qa_report.json",
        "validation_report.json",
        "domain_profiles.json",
        "domain_profile_report.json",
        "domain_profiles/manifest.json",
        "runtime_views/manifest.json",
    ]
    assert all((output_dir / relative).is_file() for relative in expected_files)
    assert result.summary["counts"] == {
        "source_units": 1,
        "knowledge_cards": 3,
        "entities": 3,
        "edges": 2,
    }
    assert result.summary["strict_generated_only"] is True

    nodes = _read_csv_rows(output_dir / "nodes.csv")
    edges = _read_csv_rows(output_dir / "edges.csv")
    assert {row["id"] for row in nodes} == {
        "LinearMorphology",
        "MechanicalContact",
        "ScratchDefect",
    }
    assert {row["relation"] for row in edges} == {
        "HAS_MORPHOLOGY",
        "HAS_PLAUSIBLE_CAUSE",
    }
    assert {row["scenario"] for row in edges} == {"mvtec"}
    assert all(row["review_status"] == "auto" for row in edges)
    assert all(row["feedback_count"] == "0" for row in edges)

    graph = KnowledgeGraph.from_csv(output_dir / "nodes.csv", output_dir / "edges.csv")
    assert graph.has_edge("ScratchDefect", "HAS_MORPHOLOGY", "LinearMorphology")
    assert graph.has_edge("ScratchDefect", "HAS_PLAUSIBLE_CAUSE", "MechanicalContact")

    qa_report = json.loads((output_dir / "qa_report.json").read_text(encoding="utf-8"))
    validation_report = json.loads(
        (output_dir / "validation_report.json").read_text(encoding="utf-8")
    )
    assert qa_report["status"] == "passed"
    assert qa_report["errors"] == []
    assert validation_report["status"] == "passed"
    assert validation_report["strict_generated_only"] is True
    assert validation_report["default_kg_layers_loaded"] is False
    assert validation_report["metrics"]["mode"] == "llm_kgbuilder_style"
    assert validation_report["metrics"]["llm_calls"] == 4
    assert validation_report["metrics"]["llm_total_tokens"] == llm.total_tokens
    domain_profiles = json.loads(
        (output_dir / "domain_profiles.json").read_text(encoding="utf-8")
    )
    domain_manifest = json.loads(
        (output_dir / "domain_profiles" / "manifest.json").read_text(encoding="utf-8")
    )
    assert domain_profiles["llm_profile_extraction_ok"] is True
    assert domain_manifest["status"] == "generated"


def test_source_kg_compiler_caps_parallel_llm_calls(tmp_path: Path) -> None:
    """Independent LLM calls should run concurrently up to the configured cap."""
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    for index in range(8):
        (source_dir / f"source_{index}.md").write_text(
            f"SCENARIO: mvtec\nENTITY: GeneratedThing{index} | label=Other\n",
            encoding="utf-8",
        )
    llm = ConcurrencyTrackingLLM()

    result = run_source_kg_compiler_workflow(
        SourceKGCompilerConfig(
            source_paths=(source_dir,),
            output_dir=tmp_path / "compiled",
            llm_client=llm,
            llm_concurrency=2,
        )
    )

    assert llm.max_active_calls == 2
    assert result.summary["llm_concurrency"] == 2
    assert result.validation_report["metrics"]["llm_calls"] == llm.calls


def test_source_kg_compiler_requires_llm_client(tmp_path: Path) -> None:
    """The compiler should not expose a standalone deterministic production mode."""
    source_path = tmp_path / "source.txt"
    source_path.write_text(
        "RELATION: A | related to | B | evidence=A related to B.",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="requires an LLM client"):
        run_source_kg_compiler_workflow(
            SourceKGCompilerConfig(source_paths=(source_path,), output_dir=tmp_path / "out")
        )


def test_source_kg_compiler_is_stable_across_runs_with_same_llm(tmp_path: Path) -> None:
    """Stable source inputs and stable LLM outputs should produce stable artifacts."""
    source_path = tmp_path / "mvtec.txt"
    source_path.write_text(
        "RELATION: ScratchDefect | has plausible cause | MechanicalContact "
        "| scenario=mvtec | head_label=Defect | tail_label=CandidateCause "
        "| confidence=0.61 | evidence=Mechanical contact is plausible.",
        encoding="utf-8",
    )
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"

    run_source_kg_compiler_workflow(
        SourceKGCompilerConfig(
            source_paths=(source_path,),
            output_dir=first_output,
            llm_client=FakeKGBuilderLLM(),
        )
    )
    run_source_kg_compiler_workflow(
        SourceKGCompilerConfig(
            source_paths=(source_path,),
            output_dir=second_output,
            llm_client=FakeKGBuilderLLM(),
        )
    )

    stable_artifacts = [
        "knowledge_cards.jsonl",
        "entities.jsonl",
        "edges.jsonl",
        "nodes.csv",
        "edges.csv",
    ]
    for artifact_name in stable_artifacts:
        assert (first_output / artifact_name).read_text(encoding="utf-8") == (
            second_output / artifact_name
        ).read_text(encoding="utf-8")


def test_source_kg_compiler_preserves_kgbuilder_relation_lines(tmp_path: Path) -> None:
    """KGBuilder source-note bullets should augment, not replace, the LLM path."""
    source_path = tmp_path / "kgbuilder_mvtec_notes.md"
    source_path.write_text(
        "\n".join(
            [
                "Scenario: mvtec",
                "- ScratchDefect HAS_PLAUSIBLE_CAUSE MechanicalContact.",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "compiled"
    llm = FakeKGBuilderLLM()

    result = run_source_kg_compiler_workflow(
        SourceKGCompilerConfig(
            source_paths=(source_path,),
            output_dir=output_dir,
            llm_client=llm,
        )
    )

    edges = _read_csv_rows(output_dir / "edges.csv")
    assert result.validation_report["metrics"]["llm_calls"] == 4
    assert {row["relation"] for row in edges} == {
        "HAS_MORPHOLOGY",
        "HAS_PLAUSIBLE_CAUSE",
    }


def test_source_kg_compiler_rejects_empty_existing_output_dir(tmp_path: Path) -> None:
    """Existing output artifacts require explicit overwrite."""
    source_path = tmp_path / "source.txt"
    source_path.write_text(
        "RELATION: A | related to | B | evidence=A related to B.",
        encoding="utf-8",
    )
    output_dir = tmp_path / "compiled"
    output_dir.mkdir()
    (output_dir / "old.txt").write_text("old", encoding="utf-8")

    with pytest.raises(ValueError, match="output directory is not empty"):
        run_source_kg_compiler_workflow(
            SourceKGCompilerConfig(
                source_paths=(source_path,),
                output_dir=output_dir,
                llm_client=FakeKGBuilderLLM(),
            )
        )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
