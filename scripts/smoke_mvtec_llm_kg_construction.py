"""Smoke-test MVTec raw-material to reviewable KG construction."""

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
from kgtracevis.workflows.mvtec_llm_source_pack import (
    MVTecLLMSourcePackConfig,
    build_mvtec_llm_source_pack,
)

Provider = Literal["offline_fixture", "openai"]


def parse_args() -> argparse.Namespace:
    """Parse MVTec LLM construction smoke arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/mvtec_llm_kg_construction_smoke"),
        help="Output directory for source pack, material library, and KG build.",
    )
    parser.add_argument(
        "--source-pack",
        type=Path,
        help="Existing mvtec_llm_source_pack.json. If omitted, one is built locally.",
    )
    parser.add_argument(
        "--provider",
        choices=("offline_fixture", "openai"),
        default="offline_fixture",
        help="Use offline fixtures for no-key smoke or OpenAI-compatible live LLM calls.",
    )
    parser.add_argument(
        "--document-understanding-mode",
        choices=("long_context", "agentic"),
        default="agentic",
    )
    parser.add_argument("--max-materials", type=int, help="Limit material count for live runs.")
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
    request = _extraction_request(
        provider=args.provider,
        document_understanding_mode=args.document_understanding_mode,
    )
    result = run_material_kg_construction_workflow(
        MaterialKGConstructionWorkflowConfig(
            material_ids=tuple(material_ids),
            material_root=material_root,
            output_dir=args.output_dir / "build",
            overwrite=True,
            run_id="kgbuild_mvtec_llm_smoke",
            extraction_mode="always",
            extraction_request=request,
        ),
        client=_MVTecOfflineDocumentIEClient() if args.provider == "offline_fixture" else None,
    )
    payload = _validate_result(
        result,
        source_pack_path=source_pack_path,
        provider=args.provider,
    )
    summary_path = args.output_dir / "mvtec_llm_kg_construction_smoke_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["summary_path"] = str(summary_path)
    print(json.dumps(payload, indent=2, sort_keys=True))


def _build_source_pack(output_dir: Path) -> Path:
    result = build_mvtec_llm_source_pack(
        MVTecLLMSourcePackConfig(
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
) -> KGMaterialExtractionRunRequest:
    kwargs: dict[str, Any] = {
        "provider": provider,
        "max_chars": 6_000,
        "overlap_chars": 400,
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
    published_relations = {
        row.get("relation")
        for row in _read_csv_rows(result.published_edges_path)
    }
    profile_manifest = json.loads(result.profile_manifest_path.read_text(encoding="utf-8"))
    brainstorm_manifest = json.loads(
        result.hypothesis_brainstorming_manifest_path.read_text(encoding="utf-8")
    )
    document_manifest = json.loads(
        result.document_understanding_manifest_path.read_text(encoding="utf-8")
    )
    brainstorm_review_types = {
        "hypothesis_candidate",
        "causal_chain_candidate",
        "missing_evidence_request",
        "profile_gap_candidate",
        "semantic_policy_candidate",
    }
    if not (brainstorm_review_types & set(item_types)):
        raise ValueError("MVTec LLM smoke did not produce brainstorming review items")
    if "HAS_PLAUSIBLE_CAUSE" in published_relations or "SUGGESTS_ROOT_CAUSE" in published_relations:
        raise ValueError("MVTec LLM smoke published RCA-like edges before review")
    if profile_manifest.get("ontology") != "mvtec_rca_v1":
        raise ValueError("MVTec LLM smoke did not select mvtec_rca_v1 profile")
    if not Path(str(result.document_map_path)).is_file():
        raise ValueError("MVTec LLM smoke did not write document_map.json")
    if not Path(str(result.brainstorm_hypotheses_path)).is_file():
        raise ValueError("MVTec LLM smoke did not write brainstorm_hypotheses.jsonl")

    return {
        "artifact_type": "mvtec_llm_kg_construction_smoke_result_v1",
        "provider": provider,
        "source_pack_path": str(source_pack_path),
        "material_ids": list(result.material_ids),
        "run_id": result.run_id,
        "output_dir": str(result.output_dir),
        "node_count": result.summary.get("node_count", 0),
        "edge_count": result.summary.get("edge_count", 0),
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


class _MVTecOfflineDocumentIEClient:
    """Small no-key IE client for testing the raw-material construction path."""

    def extract_candidates(
        self,
        chunk: SourceTextChunk,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        del prompt, response_schema
        entities: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        text = chunk.text
        mvtec = _find_text(text, ("MVTec", "DS-MVTec"))
        if mvtec:
            entities.append(
                {
                    "id": "MVTecADBenchmark",
                    "name": "MVTec AD benchmark",
                    "label": "Product",
                    "evidence": mvtec,
                    "confidence": 0.72,
                }
            )
        bottle = _find_text(text, ("bottle",))
        broken_large = _find_text(text, ("broken_large", "broken large"))
        if bottle:
            entities.append(
                {
                    "id": "BottleObject",
                    "name": "Bottle",
                    "label": "Object",
                    "evidence": bottle,
                    "confidence": 0.68,
                }
            )
        if broken_large:
            entities.append(
                {
                    "id": "BottleBrokenLargeDefect",
                    "name": "Bottle broken large defect",
                    "label": "AnomalyType",
                    "evidence": broken_large,
                    "confidence": 0.64,
                }
            )
        if bottle and broken_large:
            relations.append(
                {
                    "head": "BottleObject",
                    "relation": "HAS_ANOMALY",
                    "tail": "BottleBrokenLargeDefect",
                    "evidence": broken_large,
                    "confidence": 0.58,
                }
            )
        return {"entities": entities, "relations": relations}


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
                "MVTec documents describe anomaly detection/localization materials, "
                "not verified industrial RCA facts"
            ),
            "entity_inventory": [
                {
                    "entity_id": "MVTecADBenchmark",
                    "label": "Product",
                    "name": "MVTec AD benchmark",
                    "chunk_ids": [],
                }
            ],
            "relation_hints": [
                {
                    "relation": "HAS_ANOMALY",
                    "rationale": "Dataset documentation lists object/defect labels.",
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
                    "MVTec materials can suggest visual inspection mechanisms, but "
                    "verified factory root-cause evidence is missing."
                ),
                "supporting_spans": [
                    {
                        "chunk_id": "mvtec:source",
                        "text": "defect classes",
                    }
                ],
                "missing_evidence": [
                    "factory process logs",
                    "reviewed causal annotation",
                ],
                "risk": "medium",
                "recommended_review_action": "request_more_evidence",
            }
        ],
        "profile_gaps": [
            {
                "suggestion_type": "semantic_policy_gap_candidate",
                "rationale": "MVTec needs visual-defect and mask-region concepts.",
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
