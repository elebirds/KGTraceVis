"""Build a Section 5 acceptance bundle for RootLens backend-mode validation."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

from kgtracevis.service import api as service_api
from kgtracevis.service import handlers as service_handlers
from kgtracevis.service import kg_drafts as service_kg_drafts
from kgtracevis.service import kg_materials as service_kg_materials
from kgtracevis.service import runs as service_runs

DEFAULT_EXAMPLE = Path("data/examples/records/mvtec_records.jsonl")
DEFAULT_OUTPUT_DIR = Path("runs/rootlens_phase4_acceptance")
CLAIM_BOUNDARY = "candidate/plausible explanation only; not a verified root-cause label"


class _SectionPaths:
    def __init__(self, root: Path, notes_path: Path) -> None:
        self.root = root
        self.notes_path = notes_path


class _AcceptanceIEClient:
    def extract_candidates(
        self,
        chunk: Any,
        *,
        prompt: str,
        response_schema: dict[str, object],
    ) -> dict[str, object]:
        del prompt, response_schema
        return {
            "entities": [
                {
                    "id": "PumpCavitation",
                    "name": "Pump cavitation",
                    "label": "FaultEvent",
                    "evidence": "Pump cavitation",
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
                    "relation": "SUGGESTS_ROOT_CAUSE",
                    "tail": "SealWear",
                    "evidence": chunk.text,
                    "confidence": 0.55,
                }
            ],
        }


class _AcceptanceRunStore:
    def __init__(self) -> None:
        self.details: dict[str, service_runs.RunDetail] = {}

    def save_run(self, detail: service_runs.RunDetail) -> service_runs.RunDetail:
        self.details[detail.run.run_id] = detail
        return detail

    def list_runs(self) -> list[service_runs.RunSummary]:
        return sorted(
            [detail.run for detail in self.details.values()],
            key=lambda item: item.created_at,
            reverse=True,
        )

    def get_run_detail(self, run_id: str) -> service_runs.RunDetail:
        if run_id not in self.details:
            raise ValueError(f"unknown run session: {run_id}")
        return self.details[run_id]

    def get_artifact_path(self, run_id: str, artifact_name: str) -> str:
        detail = self.get_run_detail(run_id)
        artifact_path = Path(detail.run.run_dir) / "artifacts" / artifact_name
        if not artifact_path.is_file():
            raise ValueError(f"unknown run artifact: {artifact_name}")
        return str(artifact_path)


class _AcceptanceFeedbackStore:
    def __init__(self, ledger_path: Path) -> None:
        self.records: list[dict[str, object]] = []
        self.ledger_path = ledger_path

    def record_feedback(self, request: service_handlers.FeedbackRequest) -> dict[str, object]:
        target_id = request.target_id or request.case_id or request.run_id or request.target_type
        metadata = dict(request.metadata or {})
        record = {
            "feedback_id": f"feedback-{len(self.records) + 1}",
            "created_at": datetime.now(UTC).isoformat(),
            "run_id": request.run_id,
            "case_id": request.case_id,
            "target_type": request.target_type,
            "target_id": target_id,
            "target_key": str(metadata.get("target_key") or f"{request.target_type}:{target_id}"),
            "action": request.review_action(),
            "note": request.review_note(),
            "reviewer": request.reviewer,
            "source": request.source or "rootlens-phase4-acceptance",
            "metadata": metadata or None,
        }
        self.records.insert(0, record)
        self._write_jsonl()
        return {"status": "recorded", "record": record}

    def list_feedback(self, request: service_handlers.ReviewLedgerListRequest) -> dict[str, object]:
        filtered = [
            record
            for record in self.records
            if (request.run_id is None or record.get("run_id") == request.run_id)
            and (request.case_id is None or record.get("case_id") == request.case_id)
            and (request.target_type is None or record.get("target_type") == request.target_type)
            and (request.target_id is None or record.get("target_id") == request.target_id)
        ]
        paged = filtered[request.offset : request.offset + request.limit]
        return {
            "records": paged,
            "total_count": len(filtered),
            "returned_count": len(paged),
            "offset": request.offset,
            "limit": request.limit,
            "claim_boundary": CLAIM_BOUNDARY,
        }

    def _write_jsonl(self) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in self.records),
            encoding="utf-8",
        )


def build_acceptance_bundle(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    example_path: Path = DEFAULT_EXAMPLE,
    top_k: int = 3,
    overwrite: bool = False,
) -> dict[str, Any]:
    if not example_path.is_file():
        raise FileNotFoundError(f"example upload file not found: {example_path}")
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    if output_dir.exists():
        if not overwrite:
            raise ValueError(f"output_dir already exists; pass overwrite=true: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_dir = output_dir / "runtime_runs"
    material_root = output_dir / "materials"
    draft_path = output_dir / "kg_drafts.jsonl"
    feedback_ledger_path = output_dir / "feedback_ledger.jsonl"
    section_51 = _ensure_section(output_dir / "section_5_1")
    section_52 = _ensure_section(output_dir / "section_5_2")
    section_53 = _ensure_section(output_dir / "section_5_3")

    run_store = _AcceptanceRunStore()
    feedback_store = _AcceptanceFeedbackStore(feedback_ledger_path)

    previous_runs_dir = service_runs.DEFAULT_RUNS_DIR
    previous_material_root = service_kg_materials.DEFAULT_SOURCE_KG_MATERIAL_DIR
    previous_record_kg_draft = service_api.record_kg_draft
    previous_list_kg_drafts = service_api.list_kg_drafts
    previous_extract_material = service_api.extract_kg_material_to_structured_records
    previous_feedback_store = service_handlers._default_feedback_store

    service_runs.DEFAULT_RUNS_DIR = runtime_dir
    service_kg_materials.DEFAULT_SOURCE_KG_MATERIAL_DIR = material_root
    service_runs.configure_run_store_for_testing(run_store)
    service_kg_materials.configure_material_store_for_testing(
        service_kg_materials.FileKGMaterialStore(material_root)
    )

    def record_kg_draft_to_bundle(
        request: service_kg_drafts.KGDraftRequest,
    ) -> dict[str, object]:
        return service_kg_drafts.record_kg_draft(request, output_path=draft_path)

    def list_kg_drafts_from_bundle(
        request: service_kg_drafts.KGDraftListRequest,
    ) -> service_kg_drafts.KGDraftListResponse:
        return service_kg_drafts.list_kg_drafts(request, input_path=draft_path)

    def extract_material_with_acceptance_ie(
        material_id: str,
        request: service_kg_materials.KGMaterialExtractionRunRequest | None = None,
    ) -> service_kg_materials.KGMaterialExtractionRunResponse:
        return service_kg_materials.extract_kg_material_to_structured_records(
            material_id,
            request or service_kg_materials.KGMaterialExtractionRunRequest(),
            client=_AcceptanceIEClient(),
        )

    service_api.record_kg_draft = record_kg_draft_to_bundle
    service_api.list_kg_drafts = list_kg_drafts_from_bundle
    service_api.extract_kg_material_to_structured_records = extract_material_with_acceptance_ie
    service_handlers._default_feedback_store = lambda: feedback_store

    try:
        client = TestClient(service_api.create_app())
        bootstrap = _expect_ok(client.get("/api/dashboard/bootstrap"), "bootstrap")
        kg_studio = _expect_ok(client.get("/api/kg/studio"), "kg studio")

        kg_target = _select_kg_draft_target(kg_studio)
        kg_draft_post = _expect_ok(
            client.post(
                "/api/kg/drafts",
                json={
                    "target_type": "edge",
                    "target_id": kg_target["target_id"],
                    "target_key": kg_target["target_key"],
                    "draft_action": "revise",
                    "proposed_confidence": 0.5,
                    "note": "phase 4 acceptance draft",
                    "source": "rootlens-phase4-acceptance",
                },
            ),
            "kg draft post",
        )
        kg_draft_history = _expect_ok(
            client.get(
                "/api/kg/drafts",
                params={"target_key": kg_target["target_key"], "limit": 20},
            ),
            "kg draft history",
        )
        source_draft_preview = _expect_ok(
            client.post(
                "/api/kg/source-draft",
                json={
                    "source_id": "phase4_source",
                    "source_text": (
                        "ScratchDefect,SUGGESTS_PLAUSIBLE_MECHANISM,"
                        "MechanicalContact,mvtec,phase 4 preview evidence"
                    ),
                    "provider": "heuristic",
                    "default_scenario": "mvtec",
                    "confidence": 0.55,
                },
            ),
            "source draft preview",
        )

        material_upload = _expect_ok(
            client.post(
                "/api/kg/materials/upload",
                files={
                    "file": (
                        "pump_note.txt",
                        "Pump cavitation indicates seal wear.",
                        "text/plain",
                    )
                },
                data={
                    "title": "Pump note",
                    "scenario": "tep",
                    "source_type": "text",
                    "material_id": "pump_note",
                },
            ),
            "material upload",
        )
        material_extract = _expect_ok(
            client.post(
                "/api/kg/materials/pump_note/extract",
                json={"overwrite": True},
            ),
            "material extract",
        )
        material_chunks = _expect_ok(
            client.get("/api/kg/materials/pump_note/chunks"),
            "material chunks",
        )
        material_extractions = _expect_ok(
            client.get("/api/kg/materials/pump_note/extractions"),
            "material extractions",
        )
        material_artifacts = _expect_ok(
            client.get("/api/kg/materials/pump_note/artifacts"),
            "material artifacts",
        )
        material_build_sources = _expect_ok(
            client.post(
                "/api/kg/materials/build-sources",
                json={
                    "material_ids": ["pump_note"],
                    "output_name": "phase4_material_build",
                    "overwrite": True,
                },
            ),
            "material build-sources",
        )

        with example_path.open("rb") as handle:
            upload = _expect_ok(
                client.post(
                    "/api/runs/upload",
                    data={"mode": "records", "top_k": str(top_k)},
                    files={"file": (example_path.name, handle, "application/jsonl")},
                ),
                "records upload",
            )
        runs = _expect_ok(client.get("/api/runs"), "run history")
        run_id = upload["run"]["run_id"]
        run_detail = _expect_ok(client.get(f"/api/runs/{run_id}"), "run detail")
        active_case = run_detail["cases"][0]
        candidate = (active_case.get("ranked_root_causes") or run_detail.get("ranked_root_causes") or [None])[0]
        path = (active_case.get("path_graph", {}).get("paths") or run_detail.get("path_graph", {}).get("paths") or [None])[0]
        feedback_target = _select_feedback_target(run_detail)
        feedback_post = _expect_ok(
            client.post(
                "/api/feedback",
                json={
                    "run_id": run_id,
                    "case_id": active_case["case_id"],
                    "target_type": feedback_target["target_type"],
                    "target_id": feedback_target["target_id"],
                    "action": "needs_review",
                    "note": "phase 4 acceptance review",
                    "reviewer": "acceptance-analyst",
                    "source": "rootlens-phase4-acceptance",
                    "metadata": {"target_key": feedback_target["target_key"]},
                },
            ),
            "feedback post",
        )
        feedback_ledger = _expect_ok(
            client.get(
                "/api/feedback",
                params={"run_id": run_id, "case_id": active_case["case_id"], "limit": 20},
            ),
            "feedback ledger",
        )
    finally:
        service_api.record_kg_draft = previous_record_kg_draft
        service_api.list_kg_drafts = previous_list_kg_drafts
        service_api.extract_kg_material_to_structured_records = previous_extract_material
        service_handlers._default_feedback_store = previous_feedback_store
        service_runs.DEFAULT_RUNS_DIR = previous_runs_dir
        service_kg_materials.DEFAULT_SOURCE_KG_MATERIAL_DIR = previous_material_root
        service_runs.configure_run_store_for_testing(None)
        service_kg_materials.configure_material_store_for_testing(None)

    section_51_files = {
        "bootstrap": _write_json(section_51.root / "bootstrap.json", bootstrap),
        "runs": _write_json(section_51.root / "runs.json", runs),
        "run_detail": _write_json(section_51.root / "run_detail.json", run_detail),
        "evidence_focus": _write_json(
            section_51.root / "evidence_focus.json",
            {
                "run_id": run_id,
                "case_id": active_case["case_id"],
                "case_label": active_case.get("case_label"),
                "visual_evidence": active_case.get("visual_evidence", []),
                "frontend_route": "/evidence",
            },
        ),
    }
    section_52_files = {
        "run_detail": _write_json(section_52.root / "run_detail.json", run_detail),
        "reasoning_focus": _write_json(
            section_52.root / "reasoning_focus.json",
            {
                "run_id": run_id,
                "case_id": active_case["case_id"],
                "candidate": candidate,
                "path": path,
                "review_target": feedback_target,
                "frontend_route": "/graphs",
            },
        ),
    }
    section_53_files = {
        "feedback_post": _write_json(section_53.root / "feedback_post.json", feedback_post),
        "feedback_ledger": _write_json(section_53.root / "feedback_ledger.json", feedback_ledger),
        "kg_draft_post": _write_json(section_53.root / "kg_draft_post.json", kg_draft_post),
        "kg_draft_history": _write_json(section_53.root / "kg_draft_history.json", kg_draft_history),
        "source_draft_preview": _write_json(section_53.root / "source_draft_preview.json", source_draft_preview),
        "material_upload": _write_json(section_53.root / "material_upload.json", material_upload),
        "material_extract": _write_json(section_53.root / "material_extract.json", material_extract),
        "material_chunks": _write_json(section_53.root / "material_chunks.json", material_chunks),
        "material_extractions": _write_json(section_53.root / "material_extractions.json", material_extractions),
        "material_artifacts": _write_json(section_53.root / "material_artifacts.json", material_artifacts),
        "material_build_sources": _write_json(section_53.root / "material_build_sources.json", material_build_sources),
    }

    section_51_status = _section_status(
        bool(run_detail.get("cases"))
        and bool(run_detail.get("visual_evidence"))
        and bool(active_case.get("generated_evidence")),
    )
    section_52_status = _section_status(
        bool(run_detail.get("review_targets"))
        and bool(run_detail.get("path_graph", {}).get("paths"))
        and bool(run_detail.get("ranked_root_causes")),
    )
    section_53_status = _section_status(
        bool(feedback_ledger.get("records"))
        and bool(kg_draft_history.get("records"))
        and bool(material_chunks.get("chunks"))
        and bool(material_extractions.get("runs"))
        and bool(material_artifacts.get("artifacts"))
        and bool(material_build_sources.get("sources")),
    )

    section_51_notes = _write_markdown(
        section_51.notes_path,
        _section_notes_51(run_id=run_id, case=active_case, files=section_51_files, status=section_51_status),
    )
    section_52_notes = _write_markdown(
        section_52.notes_path,
        _section_notes_52(
            run_id=run_id,
            case=active_case,
            candidate=candidate,
            path=path,
            files=section_52_files,
            status=section_52_status,
        ),
    )
    section_53_notes = _write_markdown(
        section_53.notes_path,
        _section_notes_53(
            run_id=run_id,
            case=active_case,
            target=feedback_target,
            files=section_53_files,
            status=section_53_status,
        ),
    )

    manifest = {
        "artifact_type": "rootlens_phase4_acceptance_bundle",
        "artifact_scope": "backend_mode_acceptance_bundle",
        "created_at": datetime.now(UTC).isoformat(),
        "claim_boundary": CLAIM_BOUNDARY,
        "example_path": str(example_path),
        "top_k": top_k,
        "bundle_root": str(output_dir),
        "sections": {
            "5.1": {
                "title": "Evidence Overview and Detection Details",
                "status": section_51_status,
                "frontend_route": "/evidence",
                "context": {
                    "run_id": run_id,
                    "case_id": active_case["case_id"],
                    "case_label": active_case.get("case_label"),
                },
                "files": {name: _relative(path, output_dir) for name, path in section_51_files.items()},
                "notes_path": _relative(section_51_notes, output_dir),
                "screenshot_hints": [
                    "Evidence workspace hero with run/case context.",
                    "Observation list plus visual evidence preview.",
                ],
            },
            "5.2": {
                "title": "Knowledge Graph Reasoning View",
                "status": section_52_status,
                "frontend_route": "/graphs",
                "context": {
                    "run_id": run_id,
                    "case_id": active_case["case_id"],
                    "candidate_id": candidate.get("ranking_id") if isinstance(candidate, dict) else None,
                    "path_id": path.get("path_id") if isinstance(path, dict) else None,
                },
                "files": {name: _relative(path, output_dir) for name, path in section_52_files.items()},
                "notes_path": _relative(section_52_notes, output_dir),
                "screenshot_hints": [
                    "Graphs workspace with candidate list and linked path graph.",
                    "Trace/recurrence views can be derived from the bundled run detail.",
                ],
            },
            "5.3": {
                "title": "Provenance and Human Feedback",
                "status": section_53_status,
                "frontend_routes": ["/graphs", "/materials"],
                "context": {
                    "run_id": run_id,
                    "case_id": active_case["case_id"],
                    "feedback_target_key": feedback_target["target_key"],
                    "material_id": "pump_note",
                    "draft_target_key": kg_target["target_key"],
                },
                "files": {name: _relative(path, output_dir) for name, path in section_53_files.items()},
                "notes_path": _relative(section_53_notes, output_dir),
                "screenshot_hints": [
                    "Graphs workspace ledger/provenance panel after feedback submission.",
                    "Materials workspace after extract with chunks/extractions/artifacts and build-sources preview.",
                ],
            },
        },
        "smoke": {
            "command": "uv run python scripts/smoke_rootlens_dashboard.py --persist-runs runs/rootlens_smoke",
            "note": "Dashboard smoke validates the same backend-mode contract using TestClient.",
        },
    }

    manifest_path = _write_json(output_dir / "manifest.json", manifest)
    top_level_notes = _write_markdown(
        output_dir / "notes.md",
        _bundle_notes(manifest, manifest_path=manifest_path),
    )
    acceptance_md = _write_markdown(
        output_dir / "paper_section5_acceptance.md",
        _acceptance_markdown(manifest),
    )
    manifest["manifest_path"] = str(manifest_path)
    manifest["notes_path"] = str(top_level_notes)
    manifest["acceptance_markdown_path"] = str(acceptance_md)
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def _ensure_section(path: Path) -> _SectionPaths:
    path.mkdir(parents=True, exist_ok=True)
    return _SectionPaths(root=path, notes_path=path / "notes.md")


def _expect_ok(response: Any, label: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise RuntimeError(f"{label} failed: {response.text}")
    return response.json()


def _select_kg_draft_target(kg_studio_payload: dict[str, Any]) -> dict[str, str]:
    targets = kg_studio_payload.get("review_targets") if isinstance(kg_studio_payload, dict) else None
    if isinstance(targets, list) and targets:
        first = targets[0]
        return {
            "target_type": str(first.get("target_type") or "edge"),
            "target_id": str(first.get("target_id") or "AcceptanceEdge|BELONGS_TO|Fallback|shared"),
            "target_key": str(first.get("target_key") or "edge:AcceptanceEdge|BELONGS_TO|Fallback|shared"),
        }
    fallback_edge = "AcceptanceEdge|BELONGS_TO|FallbackCandidate|shared"
    return {
        "target_type": "edge",
        "target_id": fallback_edge,
        "target_key": f"edge:{fallback_edge}",
    }


def _select_feedback_target(run_detail: dict[str, Any]) -> dict[str, str]:
    for target in run_detail.get("review_targets", []):
        if target.get("target_type") in {"path", "edge", "root_cause_candidate"}:
            return {
                "target_type": str(target["target_type"]),
                "target_id": str(target["target_id"]),
                "target_key": str(target["target_key"]),
            }
    raise RuntimeError("run detail did not return a suitable feedback target")


def _section_status(condition: bool) -> str:
    return "supported" if condition else "partial"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def _write_markdown(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def _section_notes_51(*, run_id: str, case: dict[str, Any], files: dict[str, Path], status: str) -> str:
    return f"""# Section 5.1 Acceptance Notes

- Status: **{status}**
- Frontend route: `/evidence`
- Run ID: `{run_id}`
- Case ID: `{case['case_id']}`
- Case label: `{case.get('case_label') or case['case_id']}`

## Recommended screenshots

1. Evidence workspace hero with selected run/case.
2. Observation list with visual evidence preview.

## Backend assets

- Bootstrap: `{files['bootstrap'].name}`
- Run list: `{files['runs'].name}`
- Run detail: `{files['run_detail'].name}`
- Evidence focus: `{files['evidence_focus'].name}`
"""


def _section_notes_52(
    *,
    run_id: str,
    case: dict[str, Any],
    candidate: dict[str, Any] | None,
    path: dict[str, Any] | None,
    files: dict[str, Path],
    status: str,
) -> str:
    candidate_id = candidate.get("ranking_id") if isinstance(candidate, dict) else None
    path_id = path.get("path_id") if isinstance(path, dict) else None
    return f"""# Section 5.2 Acceptance Notes

- Status: **{status}**
- Frontend route: `/graphs`
- Run ID: `{run_id}`
- Case ID: `{case['case_id']}`
- Candidate ID: `{candidate_id}`
- Path ID: `{path_id}`

## Recommended screenshots

1. Candidate list plus linked path graph.
2. Context panel derived from bundled reasoning focus.

## Backend assets

- Run detail: `{files['run_detail'].name}`
- Reasoning focus: `{files['reasoning_focus'].name}`
"""


def _section_notes_53(
    *,
    run_id: str,
    case: dict[str, Any],
    target: dict[str, str],
    files: dict[str, Path],
    status: str,
) -> str:
    return f"""# Section 5.3 Acceptance Notes

- Status: **{status}**
- Frontend routes: `/graphs`, `/materials`
- Run ID: `{run_id}`
- Case ID: `{case['case_id']}`
- Feedback target key: `{target['target_key']}`
- Material ID: `pump_note`

## Recommended screenshots

1. Feedback ledger / provenance panel after review submission.
2. Materials workspace after extract with chunks, extraction runs, artifacts, and build-sources preview.

## Backend assets

- Feedback post: `{files['feedback_post'].name}`
- Feedback ledger: `{files['feedback_ledger'].name}`
- KG draft post: `{files['kg_draft_post'].name}`
- KG draft history: `{files['kg_draft_history'].name}`
- Source-draft preview: `{files['source_draft_preview'].name}`
- Material upload: `{files['material_upload'].name}`
- Material extract: `{files['material_extract'].name}`
- Material chunks: `{files['material_chunks'].name}`
- Material extractions: `{files['material_extractions'].name}`
- Material artifacts: `{files['material_artifacts'].name}`
- Build-sources: `{files['material_build_sources'].name}`
"""


def _bundle_notes(manifest: dict[str, Any], *, manifest_path: Path) -> str:
    lines = [
        "# RootLens Phase 4 Acceptance Bundle",
        "",
        f"- Manifest: `{manifest_path.name}`",
        f"- Claim boundary: `{manifest['claim_boundary']}`",
        f"- Example input: `{manifest['example_path']}`",
        "",
        "## Section status",
        "",
    ]
    for section_id, section in manifest["sections"].items():
        lines.append(f"- {section_id} `{section['title']}`: **{section['status']}**")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "This bundle is backend-mode evidence for Section 5 acceptance. It does not generate screenshots itself; instead it fixes the run/material/draft/feedback context and the exact backend payloads that a frontend/backend-mode walkthrough should use.",
        ]
    )
    return "\n".join(lines) + "\n"


def _acceptance_markdown(manifest: dict[str, Any]) -> str:
    rows = []
    for section_id, section in manifest["sections"].items():
        route = section.get("frontend_route") or ", ".join(section.get("frontend_routes", []))
        rows.append(
            f"| {section_id} | {section['title']} | {section['status']} | `{route}` | `{section['notes_path']}` |"
        )
    return (
        "# Paper Section 5 Acceptance Snapshot\n\n"
        "This generated file summarizes which backend-mode assets currently support Section 5 claims.\n\n"
        "| Section | Title | Status | Frontend route(s) | Notes |\n"
        "| --- | --- | --- | --- | --- |\n"
        + "\n".join(rows)
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example", type=Path, default=DEFAULT_EXAMPLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    manifest = build_acceptance_bundle(
        output_dir=args.output_dir,
        example_path=args.example,
        top_k=args.top_k,
        overwrite=args.overwrite,
    )
    print(
        "RootLens Phase 4 acceptance bundle created: "
        f"manifest={manifest['manifest_path']}, section_5_1={manifest['sections']['5.1']['status']}, "
        f"section_5_2={manifest['sections']['5.2']['status']}, section_5_3={manifest['sections']['5.3']['status']}"
    )


if __name__ == "__main__":
    main()
