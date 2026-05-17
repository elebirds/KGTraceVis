"""Tests for Postgres-backed run payload reconstruction helpers."""

from __future__ import annotations

import json
from pathlib import Path

from kgtracevis.service.postgres_run_payloads import detail_payload


def test_detail_payload_restores_reasoning_metadata_across_layers() -> None:
    """Persisted run payloads should restore case/summary/analysis reasoning metadata."""
    evidence = json.loads(Path("data/examples/ds_mvtec_example.json").read_text(encoding="utf-8"))
    reasoning_metadata = {
        "reasoning_profile_id": "generic_graph_path_default",
        "reasoner_adapter": "generic_graph_path",
        "selection_mode": "explicit",
        "requested_reasoning_profile_id": "generic_graph_path_default",
        "fallback_applied": False,
    }

    payload = detail_payload(
        run_row={
            "run_id": "44444444-4444-4444-4444-444444444444",
            "started_at": "2026-05-17T00:00:00+00:00",
            "mode": "records",
            "source_filename": "mvtec_records.jsonl",
            "top_k": 2,
            "run_dir": "runs/rootlens_sessions/44444444-4444-4444-4444-444444444444",
            "status": "completed",
            "dataset": "mvtec",
            "case_count": 1,
            "evidence_count": 1,
            "label": "mvtec_records.jsonl · 1 cases",
            "model_preset": None,
            "model_backend": None,
            "claim_boundary": "candidate/plausible explanation only; not a verified root-cause label",
            "summary": {
                "pipeline": {
                    **reasoning_metadata,
                    "reasoning_profile_ids": ["generic_graph_path_default"],
                    "reasoner_adapters": ["generic_graph_path"],
                    "selection_modes": ["explicit"],
                    "requested_reasoning_profile_ids": ["generic_graph_path_default"],
                    "requested_reasoner_adapters": [],
                    "tep_rca_reasoner": "generic_graph_path",
                }
            },
            "parameters": {
                "workflow_steps": [],
                "ranked_root_causes_by_case": {evidence["case_id"]: []},
                "reasoning_metadata_by_case": {evidence["case_id"]: reasoning_metadata},
                "run_reasoning_metadata": reasoning_metadata,
                "analysis_reasoning_metadata": reasoning_metadata,
            },
        },
        case_rows=[
            {
                "case_pk": "case-pk-1",
                "case_id": evidence["case_id"],
                "dataset": evidence["dataset"],
                "evidence_payload": evidence,
                "generated_evidence_path": "runs/rootlens_sessions/evidence.json",
            }
        ],
        linked_rows=[],
        consistency_rows=[],
        correction_rows=[],
        path_rows=[],
        artifact_rows=[],
    )

    assert payload["summary"]["pipeline"]["reasoning_profile_id"] == "generic_graph_path_default"
    assert payload["analysis"]["reasoning_metadata"]["selection_mode"] == "explicit"
    assert payload["cases"][0]["reasoning_metadata"]["reasoner_adapter"] == "generic_graph_path"
    assert payload["reasoning_metadata"]["requested_reasoning_profile_id"] == (
        "generic_graph_path_default"
    )
    assert payload["evidence_with_analysis"]["kg_analysis"]["reasoning_metadata"][
        "reasoning_profile_id"
    ] == "generic_graph_path_default"
