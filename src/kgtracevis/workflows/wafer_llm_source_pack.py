"""Build wafer/WM811K source packs for LLM-assisted KG construction."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

MaterialType = Literal["pdf", "webpage", "text", "markdown", "csv", "jsonl", "other"]
SourceKind = Literal["url", "local_path"]

DEFAULT_WAFER_RECORDS_PATH = Path("data/examples/records/wm811k_records.jsonl")


@dataclass(frozen=True)
class WaferSourceMaterialSpec:
    """One raw or near-raw material candidate for wafer KG construction."""

    material_id: str
    title: str
    source_uri: str
    source_kind: SourceKind
    material_type: MaterialType
    provenance_role: str
    local_path: Path | None = None


@dataclass(frozen=True)
class WaferLLMSourcePackConfig:
    """Configuration for building a wafer/WM811K source pack."""

    output_dir: Path
    wm811k_records_path: Path = DEFAULT_WAFER_RECORDS_PATH
    overwrite: bool = False
    include_wm811k_records: bool = True


@dataclass(frozen=True)
class WaferLLMSourcePackResult:
    """Result paths and payload for one wafer LLM source pack."""

    output_dir: Path
    source_pack_path: Path
    material_manifest_path: Path
    copied_source_dir: Path
    material_count: int
    manifest: dict[str, Any]


def build_wafer_llm_source_pack(
    config: WaferLLMSourcePackConfig,
) -> WaferLLMSourcePackResult:
    """Copy local wafer materials and write a material registration manifest."""
    if config.output_dir.exists() and any(config.output_dir.iterdir()) and not config.overwrite:
        raise ValueError(f"{config.output_dir} already exists; pass overwrite=true to replace")
    if config.output_dir.exists() and config.overwrite:
        shutil.rmtree(config.output_dir)
    source_dir = config.output_dir / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)

    materials: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for spec in _default_material_specs(config):
        if spec.source_kind == "local_path":
            if spec.local_path is None or not spec.local_path.is_file():
                skipped.append(
                    {
                        "material_id": spec.material_id,
                        "path": str(spec.local_path or ""),
                        "reason": "missing",
                    }
                )
                continue
            copied_path = _copy_material_source(spec, source_dir)
            materials.append(_material_registration_payload(spec, source_uri=str(copied_path)))
            continue
        materials.append(_material_registration_payload(spec, source_uri=spec.source_uri))

    if not materials:
        raise ValueError("no wafer source materials found")

    manifest = {
        "artifact_type": "wafer_llm_source_pack_v1",
        "claim_boundary": (
            "Wafer/WM811K source materials support spatial-pattern KG candidates "
            "and reviewable process hypotheses; public WM811K labels are not "
            "verified process RCA labels."
        ),
        "construction_goal": (
            "raw/near-raw wafer documents and records -> document understanding -> "
            "chunk IE -> brainstorming -> reviewable KG candidates"
        ),
        "source_policy": {
            "allowed": (
                "open-access wafer-map papers/pages, WM811K adapter records, and "
                "prose documentation"
            ),
            "excluded": "prebuilt KG files and generated node/edge tables",
        },
        "materials": materials,
        "skipped": skipped,
    }
    source_pack_path = config.output_dir / "wafer_llm_source_pack.json"
    material_manifest_path = config.output_dir / "material_registration.json"
    _write_json(source_pack_path, manifest)
    _write_json(
        material_manifest_path,
        {
            "artifact_type": "kg_material_registration_manifest_v1",
            "materials": materials,
        },
    )
    return WaferLLMSourcePackResult(
        output_dir=config.output_dir,
        source_pack_path=source_pack_path,
        material_manifest_path=material_manifest_path,
        copied_source_dir=source_dir,
        material_count=len(materials),
        manifest=manifest,
    )


def _default_material_specs(
    config: WaferLLMSourcePackConfig,
) -> tuple[WaferSourceMaterialSpec, ...]:
    specs = [
        WaferSourceMaterialSpec(
            material_id="wafer_defect_frontiers_2023",
            title="Wafer defect recognition method based on multi-scale feature fusion",
            source_uri=(
                "https://www.frontiersin.org/articles/10.3389/"
                "fnins.2023.1202985/full"
            ),
            source_kind="url",
            material_type="webpage",
            provenance_role="wafer_pattern_taxonomy_context",
        ),
    ]
    if config.include_wm811k_records:
        specs.append(
            WaferSourceMaterialSpec(
                material_id="wm811k_example_records",
                title="WM811K adapter example records",
                source_uri=str(config.wm811k_records_path),
                source_kind="local_path",
                material_type="jsonl",
                provenance_role="wm811k_adapter_evidence_context",
                local_path=config.wm811k_records_path,
            )
        )
    specs.append(
        WaferSourceMaterialSpec(
            material_id="wafer_map_scientific_reports_2023",
            title="Wafer map failure pattern classification paper",
            source_uri="https://www.nature.com/articles/s41598-023-34147-2",
            source_kind="url",
            material_type="webpage",
            provenance_role="wafer_ml_method_context",
        )
    )
    return tuple(specs)


def _copy_material_source(spec: WaferSourceMaterialSpec, source_dir: Path) -> Path:
    if spec.local_path is None:
        raise ValueError(f"wafer material {spec.material_id} has no local path")
    suffix = "".join(spec.local_path.suffixes) or ".txt"
    destination = source_dir / f"{spec.material_id}{suffix}"
    shutil.copyfile(spec.local_path, destination)
    return destination


def _material_registration_payload(
    spec: WaferSourceMaterialSpec,
    *,
    source_uri: str,
) -> dict[str, Any]:
    return {
        "material_id": spec.material_id,
        "title": spec.title,
        "source_uri": source_uri,
        "source_kind": spec.source_kind,
        "scenario": "wafer",
        "material_type": spec.material_type,
        "metadata": {
            "source_pack_role": spec.provenance_role,
            "original_path": str(spec.local_path or ""),
            "source_pack_policy": "raw_or_near_raw_material_only",
            "excludes_prebuilt_kg": True,
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
