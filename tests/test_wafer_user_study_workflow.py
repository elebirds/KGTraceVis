"""Tests for wafer user-study asset preparation workflow."""

from __future__ import annotations

import json
from pathlib import Path

from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS, KnowledgeGraph
from kgtracevis.service.kg_studio import kg_studio_payload
from kgtracevis.service.run_models import RunDetail
from kgtracevis.service.run_store import configure_run_store_for_testing
from kgtracevis.workflows.root_cause_provider_selection import build_pipeline
from kgtracevis.workflows.wafer_user_study import (
    DEFAULT_WAFER_USER_STUDY_BASELINE_PATH,
    DEFAULT_WAFER_USER_STUDY_EVIDENCE_PATH,
    WaferUserStudyConfig,
    prepare_wafer_user_study,
)


class InMemoryRunStore:
    """Minimal run-store test double for user-study workflow tests."""

    def __init__(self) -> None:
        self.details: dict[str, RunDetail] = {}

    def save_run(self, detail: RunDetail) -> RunDetail:
        self.details[detail.run.run_id] = detail
        return detail


def test_prepare_wafer_user_study_materializes_kg_studio_graph(tmp_path: Path) -> None:
    """Preparing the wafer user-study graph should yield a KG Studio-readable directory."""
    config = WaferUserStudyConfig(
        evidence_path=DEFAULT_WAFER_USER_STUDY_EVIDENCE_PATH,
        baseline_path=DEFAULT_WAFER_USER_STUDY_BASELINE_PATH,
        graph_output_dir=tmp_path / "wafer_user_study_graph",
        manifest_path=tmp_path / "wafer_user_study_manifest.json",
        create_run=False,
        import_runtime_kg=False,
        overwrite=True,
    )

    result = prepare_wafer_user_study(config)

    assert result.run_id is None
    assert result.graph_summary["status"] == "ready"
    assert Path(result.graph_summary["nodes_path"]).is_file()
    assert Path(result.graph_summary["edges_path"]).is_file()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["case"]["case_id"] == "wafer_user_study_nearfull_001"
    assert manifest["run_id"] is None

    payload = kg_studio_payload(
        candidate_dirs=(config.graph_output_dir,),
        source_registry_path=tmp_path / "missing_sources.csv",
        source_docs_dir=tmp_path / "missing_docs",
    )
    assert payload.status == "ok"
    assert payload.node_count == 42
    assert payload.edge_count == 81
    assert payload.scenario_counts["wafer"] == 81
    assert any(node.node_id == "NearfullDefect" for node in payload.graph_nodes)
    assert any(edge.tail == "GlueRemovalInsufficient" for edge in payload.graph_edges)
    assert result.graph_summary["graph_scope"] == "full_runtime"


def test_prepare_wafer_user_study_can_persist_a_wafer_run_with_testing_store(
    tmp_path: Path,
) -> None:
    """The workflow should be able to create one persisted wafer test run."""
    store = InMemoryRunStore()
    configure_run_store_for_testing(store)
    try:
        graph = KnowledgeGraph.from_paths(DEFAULT_NODE_PATHS, DEFAULT_EDGE_PATHS, skip_missing=True)
        config = WaferUserStudyConfig(
            evidence_path=DEFAULT_WAFER_USER_STUDY_EVIDENCE_PATH,
            baseline_path=DEFAULT_WAFER_USER_STUDY_BASELINE_PATH,
            graph_output_dir=tmp_path / "wafer_user_study_graph",
            manifest_path=tmp_path / "wafer_user_study_manifest.json",
            run_artifact_root=tmp_path / "rootlens_sessions",
            create_run=True,
            import_runtime_kg=False,
            overwrite=True,
            top_k=3,
        )

        result = prepare_wafer_user_study(config, pipeline=build_pipeline(graph=graph))

        assert result.run_id is not None
        assert result.run_id in store.details
        detail = store.details[result.run_id]
        assert detail.run.dataset == "wafer"
        assert detail.run.mode == "evidence"
        assert detail.run.case_count == 1
        assert detail.summary is not None
        assert detail.summary["pipeline"]["reasoning_profile_id"] == "generic_graph_path_default"
        assert detail.cases[0]["case_id"] == "wafer_user_study_nearfull_001"
        assert detail.cases[0]["reasoning_metadata"]["reasoner_adapter"] == "generic_graph_path"
        assert len(detail.top_k_paths) >= 1
        assert len(detail.review_targets) >= 1
    finally:
        configure_run_store_for_testing(None)
