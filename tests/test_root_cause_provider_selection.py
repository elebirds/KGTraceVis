"""Tests for reusable root-cause reasoner construction."""

from __future__ import annotations

from kgtracevis.kg.graph import KGEdge, KGNode, KnowledgeGraph
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.workflows.root_cause_provider_selection import (
    build_pipeline,
    build_root_cause_reasoner,
)
from kgtracevis.workflows.tep_root_kgd import TepRootKgdRcaProvider


def test_root_cause_reasoner_is_single_tep_root_kgd_provider() -> None:
    """Pipeline construction should expose only the TEP Root-KGD reasoner."""
    provider = build_root_cause_reasoner()
    pipeline = build_pipeline()

    assert isinstance(provider, TepRootKgdRcaProvider)
    assert isinstance(pipeline.root_cause_reasoner, TepRootKgdRcaProvider)


def test_single_provider_leaves_non_tep_cases_on_generic_paths() -> None:
    """The TEP provider returns empty for non-TEP evidence, allowing generic fallback."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph(
        nodes=[
            KGNode("ScratchDefect", "Scratch defect", "Defect", "mvtec", ("scratch",)),
            KGNode("MechanicalContact", "Mechanical contact", "CandidateCause", "mvtec", ()),
        ],
        edges=[
            KGEdge(
                head="ScratchDefect",
                relation="HAS_PLAUSIBLE_CAUSE",
                tail="MechanicalContact",
                scenario="mvtec",
                source="test_root_cause_provider_selection",
                evidence="Scratch defects can be plausibly caused by contact.",
                confidence=0.7,
                weight=0.3,
                review_status="auto",
                feedback_count=0,
                accepted_count=0,
                rejected_count=0,
            ),
        ],
    )
    result = build_pipeline(graph=graph).analyze(evidence, top_k=2)

    assert result.top_k_paths
    assert result.ranked_root_causes
    assert all(
        root_cause.scoring_method != "tep_root_kgd"
        for root_cause in result.ranked_root_causes
    )
