"""Smoke-test wafer/WM811K source materials to reviewable KG construction."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from pathlib import Path
from typing import Any, Literal

from kgtracevis.kg_construction.document_extraction import SourceTextChunk
from kgtracevis.service.kg_materials import (
    KGMaterialExtractionRunRequest,
    KGMaterialRegisterRequest,
    register_kg_material,
)
from kgtracevis.workflows.material_kg_construction import (
    MaterialKGConstructionWorkflowConfig,
    run_material_kg_construction_workflow,
)
from kgtracevis.workflows.wafer_llm_source_pack import (
    WaferLLMSourcePackConfig,
    build_wafer_llm_source_pack,
)

Provider = Literal["offline_fixture", "openai"]


def parse_args() -> argparse.Namespace:
    """Parse wafer LLM construction smoke arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/wafer_llm_kg_construction_smoke"),
    )
    parser.add_argument(
        "--source-pack",
        type=Path,
        help="Existing wafer_llm_source_pack.json. If omitted, one is built locally.",
    )
    parser.add_argument(
        "--provider",
        choices=("offline_fixture", "openai"),
        default="offline_fixture",
    )
    parser.add_argument(
        "--document-understanding-mode",
        choices=("long_context", "agentic"),
        default="agentic",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=12_000,
        help="Chunk size for document IE. Larger values preserve paper/table context.",
    )
    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=1_200,
        help="Chunk overlap for document IE.",
    )
    parser.add_argument("--max-materials", type=int)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run the smoke and print a compact JSON result."""
    args = parse_args()
    _load_dotenv_files()
    if args.output_dir.exists() and args.overwrite:
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    source_pack_path = args.source_pack or _build_source_pack(args.output_dir)
    source_pack = json.loads(source_pack_path.read_text(encoding="utf-8"))
    materials = list(source_pack.get("materials") or [])
    if args.max_materials is not None:
        if args.max_materials < 1:
            raise ValueError("--max-materials must be >= 1")
        materials = materials[: args.max_materials]
    if not materials:
        raise ValueError(f"source pack has no materials: {source_pack_path}")

    material_root = args.output_dir / "material_library"
    material_ids = _register_materials(materials, material_root=material_root)
    result = run_material_kg_construction_workflow(
        MaterialKGConstructionWorkflowConfig(
            material_ids=tuple(material_ids),
            material_root=material_root,
            output_dir=args.output_dir / "build",
            overwrite=True,
            run_id="kgbuild_wafer_llm_smoke",
            extraction_mode="always",
            extraction_request=_extraction_request(
                provider=args.provider,
                document_understanding_mode=args.document_understanding_mode,
                max_chars=args.max_chars,
                overlap_chars=args.overlap_chars,
            ),
        ),
        client=_WaferOfflineDocumentIEClient()
        if args.provider == "offline_fixture"
        else None,
    )
    payload = _validate_result(
        result,
        source_pack_path=source_pack_path,
        provider=args.provider,
    )
    summary_path = args.output_dir / "wafer_llm_kg_construction_smoke_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["summary_path"] = str(summary_path)
    print(json.dumps(payload, indent=2, sort_keys=True))


def _build_source_pack(output_dir: Path) -> Path:
    result = build_wafer_llm_source_pack(
        WaferLLMSourcePackConfig(
            output_dir=output_dir / "source_pack",
            overwrite=True,
        )
    )
    return result.source_pack_path


def _register_materials(
    materials: list[dict[str, Any]],
    *,
    material_root: Path,
) -> list[str]:
    material_ids: list[str] = []
    for payload in materials:
        request = KGMaterialRegisterRequest(**payload)
        register_kg_material(request, material_root=material_root, overwrite=True)
        material_ids.append(request.material_id)
    return material_ids


def _extraction_request(
    *,
    provider: Provider,
    document_understanding_mode: str,
    max_chars: int,
    overlap_chars: int,
) -> KGMaterialExtractionRunRequest:
    kwargs: dict[str, Any] = {
        "provider": provider,
        "max_chars": max_chars,
        "overlap_chars": overlap_chars,
        "document_understanding_mode": document_understanding_mode,
        "document_understanding_provider": provider,
        "hypothesis_mode": "brainstorm",
        "hypothesis_provider": provider,
        "hypothesis_influence": "review_only",
        "continue_on_chunk_error": provider == "openai",
        "overwrite": True,
    }
    if provider == "offline_fixture":
        kwargs["document_understanding_payload"] = _offline_document_understanding_payload()
        kwargs["hypothesis_payload"] = _offline_hypothesis_payload()
    return KGMaterialExtractionRunRequest(**kwargs)


def _validate_result(
    result: Any,
    *,
    source_pack_path: Path,
    provider: Provider,
) -> dict[str, Any]:
    review_queue = json.loads(result.review_queue_path.read_text(encoding="utf-8"))
    item_types = sorted({str(item.get("item_type")) for item in review_queue})
    profile_manifest = json.loads(result.profile_manifest_path.read_text(encoding="utf-8"))
    brainstorm_manifest = json.loads(
        result.hypothesis_brainstorming_manifest_path.read_text(encoding="utf-8")
    )
    document_manifest = json.loads(
        result.document_understanding_manifest_path.read_text(encoding="utf-8")
    )
    edges = _read_csv_rows(result.edges_path)
    edge_relations = {row.get("relation") for row in edges}
    published_relations = {
        row.get("relation")
        for row in _read_csv_rows(result.published_edges_path)
    }
    if profile_manifest.get("ontology") != "wafer_rca_v1":
        raise ValueError("Wafer LLM smoke did not select wafer_rca_v1 profile")
    if not {"HAS_LOCATION", "HAS_MORPHOLOGY", "HAS_SPATIAL_SIGNATURE"} & edge_relations:
        raise ValueError("Wafer LLM smoke did not produce spatial pattern support edges")
    if {"CAUSES", "HAS_PLAUSIBLE_CAUSE", "SUGGESTS_ROOT_CAUSE"} & published_relations:
        raise ValueError("Wafer LLM smoke published RCA-like edges before review")

    return {
        "artifact_type": "wafer_llm_kg_construction_smoke_result_v1",
        "provider": provider,
        "source_pack_path": str(source_pack_path),
        "material_ids": list(result.material_ids),
        "run_id": result.run_id,
        "output_dir": str(result.output_dir),
        "node_count": result.summary.get("node_count", 0),
        "edge_count": result.summary.get("edge_count", 0),
        "edge_relations": sorted(edge_relations),
        "profile_version": result.summary.get("profile_version", ""),
        "review_item_types": item_types,
        "published_edge_count": len(_read_csv_rows(result.published_edges_path)),
        "document_understanding": {
            "artifact_type": document_manifest.get("artifact_type"),
            "document_map_count": document_manifest.get("document_map_count", 0),
        },
        "brainstorming": {
            "artifact_type": brainstorm_manifest.get("artifact_type"),
            "hypothesis_count": brainstorm_manifest.get("hypothesis_count", 0),
            "review_item_count": brainstorm_manifest.get("review_item_count", 0),
        },
        "artifacts": dict(result.artifacts),
    }


class _WaferOfflineDocumentIEClient:
    """Small no-key IE client for wafer source-pack smoke testing."""

    def extract_candidates(
        self,
        chunk: SourceTextChunk,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        del prompt, response_schema
        text = chunk.text
        entities: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        for pattern, entity_id in (
            ("center", "CenterPattern"),
            ("edge-loc", "EdgeLocPattern"),
            ("ring", "RingPattern"),
            ("scratch", "ScratchPattern"),
            ("near-full", "NearFullPattern"),
            ("random", "RandomPattern"),
        ):
            evidence = _find_text(text, (pattern, pattern.replace("-", " ")))
            if evidence:
                entities.append(
                    {
                        "id": entity_id,
                        "name": pattern.title().replace("-", " ") + " pattern",
                        "label": "DefectType",
                        "evidence": evidence,
                        "confidence": 0.66,
                    }
                )
        if _has_entity(entities, "CenterPattern"):
            center_evidence = _find_text(text, ("center",))
            if center_evidence:
                entities.append(
                    _entity("WaferCenter", "Wafer center", "Location", center_evidence)
                )
                relations.append(
                    _relation(
                        "CenterPattern",
                        "HAS_LOCATION",
                        "WaferCenter",
                        center_evidence,
                    )
                )
            deposition_evidence = _find_text(
                text,
                ("thin-film deposition", "thin film deposition"),
            )
            if deposition_evidence:
                entities.append(
                    _entity(
                        "ThinFilmDepositionIssue",
                        "Thin-film deposition issue",
                        "ProcessCondition",
                        deposition_evidence,
                    )
                )
                relations.append(
                    _relation(
                        "CenterPattern",
                        "HAS_PLAUSIBLE_CAUSE",
                        "ThinFilmDepositionIssue",
                        deposition_evidence,
                    )
                )
        if _has_entity(entities, "EdgeLocPattern"):
            edge_evidence = _find_text(text, ("edge-loc", "edge loc", "edge"))
            if edge_evidence:
                entities.append(_entity("WaferEdge", "Wafer edge", "Location", edge_evidence))
                relations.append(
                    _relation("EdgeLocPattern", "HAS_LOCATION", "WaferEdge", edge_evidence)
                )
            heating_evidence = _find_text(
                text,
                ("uneven heating during the diffusion process", "uneven heating"),
            )
            if heating_evidence:
                entities.append(
                    _entity(
                        "UnevenHeatingDiffusionProcess",
                        "Uneven heating during diffusion",
                        "ProcessCondition",
                        heating_evidence,
                    )
                )
                relations.append(
                    _relation(
                        "EdgeLocPattern",
                        "HAS_PLAUSIBLE_CAUSE",
                        "UnevenHeatingDiffusionProcess",
                        heating_evidence,
                    )
                )
        if _has_entity(entities, "ScratchPattern"):
            entities.append(
                _entity(
                    "LinearScratchSignature",
                    "Linear scratch signature",
                    "Morphology",
                    "scratch",
                )
            )
            relations.append(
                _relation(
                    "ScratchPattern",
                    "HAS_MORPHOLOGY",
                    "LinearScratchSignature",
                    "scratch",
                )
            )
        if _has_entity(entities, "RingPattern"):
            entities.append(_entity("RingSignature", "Ring signature", "Morphology", "ring"))
            relations.append(
                _relation("RingPattern", "HAS_SPATIAL_SIGNATURE", "RingSignature", "ring")
            )
        if _has_entity(entities, "NearFullPattern"):
            entities.append(
                _entity(
                    "DenseFullWaferSignature",
                    "Dense full-wafer signature",
                    "Morphology",
                    "near-full",
                )
            )
            relations.append(
                _relation(
                    "NearFullPattern",
                    "HAS_SPATIAL_SIGNATURE",
                    "DenseFullWaferSignature",
                    "near-full",
                )
            )
        return {"entities": entities, "relations": relations}


def _entity(entity_id: str, name: str, label: str, evidence: str) -> dict[str, Any]:
    return {
        "id": entity_id,
        "name": name,
        "label": label,
        "evidence": evidence,
        "confidence": 0.62,
    }


def _relation(head: str, relation: str, tail: str, evidence: str) -> dict[str, Any]:
    return {
        "head": head,
        "relation": relation,
        "tail": tail,
        "evidence": evidence,
        "confidence": 0.58,
    }


def _has_entity(entities: list[dict[str, Any]], entity_id: str) -> bool:
    return any(entity.get("id") == entity_id for entity in entities)


def _find_text(text: str, candidates: tuple[str, ...]) -> str:
    lower_text = text.lower()
    for candidate in candidates:
        index = lower_text.find(candidate.lower())
        if index >= 0:
            return text[index : index + len(candidate)]
    return ""


def _offline_document_understanding_payload() -> dict[str, Any]:
    return {
        "document_map": {
            "artifact_type": "document_understanding_map_v1",
            "claim_boundary": (
                "Wafer documents describe spatial-pattern evidence and process "
                "hypotheses, not reviewed fab root-cause facts."
            ),
            "entity_inventory": [
                {
                    "entity_id": "CenterPattern",
                    "label": "DefectType",
                    "name": "Center pattern",
                    "chunk_ids": [],
                }
            ],
            "relation_hints": [
                {
                    "relation": "HAS_LOCATION",
                    "rationale": "Wafer-map pattern classes encode spatial locations.",
                }
            ],
        }
    }


def _offline_hypothesis_payload() -> dict[str, Any]:
    return {
        "hypotheses": [
            {
                "hypothesis_type": "missing_evidence",
                "claim": (
                    "WM811K public labels can support wafer spatial traceability, "
                    "but fab process logs are required for verified RCA."
                ),
                "supporting_spans": [{"chunk_id": "wafer:source", "text": "WM-811K"}],
                "missing_evidence": ["lot history", "tool/chamber logs"],
                "risk": "medium",
                "recommended_review_action": "request_more_evidence",
            }
        ],
        "profile_gaps": [
            {
                "suggestion_type": "semantic_policy_gap_candidate",
                "rationale": "Wafer profiles need spatial signatures and process conditions.",
                "risk": "low",
            }
        ],
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_dotenv_files() -> None:
    for path in (Path(".env.local"), Path(".env")):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", maxsplit=1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if __name__ == "__main__":
    main()
