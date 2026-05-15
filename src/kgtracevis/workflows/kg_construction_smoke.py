"""Acceptance smoke workflow for RCA-oriented KG construction paths."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from kgtracevis.kg_construction import KGConstructionSource, load_source_library
from kgtracevis.kg_construction.models import KG_CONSTRUCTION_REQUIRED_ARTIFACT_KEYS
from kgtracevis.service.kg_materials import (
    KGMaterialExtractionState,
    KGMaterialRegisterRequest,
    register_kg_material,
)
from kgtracevis.workflows.material_kg_construction import (
    MaterialKGConstructionWorkflowConfig,
    MaterialKGConstructionWorkflowResult,
    run_material_kg_construction_workflow,
)
from kgtracevis.workflows.source_kg_construction import (
    SourceKGConstructionWorkflowConfig,
    SourceKGConstructionWorkflowResult,
    run_source_kg_construction_workflow,
)

SmokePathStatus = Literal["passed", "skipped"]


@dataclass(frozen=True)
class KGConstructionSmokeConfig:
    """Configuration for RCA-KG construction acceptance smoke builds."""

    output_dir: Path
    overwrite: bool = False
    tep_kg_root: Path | None = None
    require_tep: bool = False


@dataclass(frozen=True)
class KGConstructionSmokePath:
    """One smoke path outcome."""

    name: str
    status: SmokePathStatus
    output_dir: Path | None = None
    summary_path: Path | None = None
    manifest_path: Path | None = None
    artifacts: dict[str, str] | None = None
    metadata: dict[str, Any] | None = None
    reason: str = ""

    def payload(self) -> dict[str, Any]:
        """Return a JSON-friendly path result."""
        return {
            "name": self.name,
            "status": self.status,
            "output_dir": str(self.output_dir) if self.output_dir is not None else "",
            "summary_path": str(self.summary_path) if self.summary_path is not None else "",
            "manifest_path": str(self.manifest_path) if self.manifest_path is not None else "",
            "artifacts": dict(self.artifacts or {}),
            "metadata": dict(self.metadata or {}),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class KGConstructionSmokeResult:
    """Aggregate smoke result for toy and optional TEP construction builds."""

    output_dir: Path
    paths: tuple[KGConstructionSmokePath, ...]
    summary_path: Path

    def payload(self) -> dict[str, Any]:
        """Return a JSON-friendly smoke summary."""
        passed = sum(1 for path in self.paths if path.status == "passed")
        skipped = sum(1 for path in self.paths if path.status == "skipped")
        return {
            "artifact_type": "rca_kg_construction_smoke_result_v1",
            "output_dir": str(self.output_dir),
            "passed": passed,
            "skipped": skipped,
            "paths": [path.payload() for path in self.paths],
            "summary_path": str(self.summary_path),
        }


def run_kg_construction_acceptance_smoke(
    config: KGConstructionSmokeConfig,
) -> KGConstructionSmokeResult:
    """Run toy generic and optional TEP RCA-KG construction smoke builds."""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[KGConstructionSmokePath] = [
        _run_toy_source_library_smoke(config),
        _run_material_direct_smoke(config),
    ]
    paths.append(_run_tep_smoke(config))
    summary_path = config.output_dir / "kg_construction_smoke_summary.json"
    result = KGConstructionSmokeResult(
        output_dir=config.output_dir,
        paths=tuple(paths),
        summary_path=summary_path,
    )
    summary_path.write_text(
        json.dumps(result.payload(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def _run_toy_source_library_smoke(
    config: KGConstructionSmokeConfig,
) -> KGConstructionSmokePath:
    source_dir = config.output_dir / "toy_generic_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "toy_generic.csv"
    source_path.write_text(_toy_generic_source_csv(), encoding="utf-8")
    library_path = source_dir / "source_library.json"
    library_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "toy_generic_source",
                        "source_type": "manual_table",
                        "scenario": "shared",
                        "path": "toy_generic.csv",
                        "metadata": {"source_format": "csv"},
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    sources = tuple(record.to_construction_source() for record in load_source_library(library_path))
    result = run_source_kg_construction_workflow(
        SourceKGConstructionWorkflowConfig(
            output_dir=config.output_dir / "toy_generic",
            sources=sources,
            overwrite=config.overwrite,
            run_id="kgbuild_smoke_toy_generic",
        )
    )
    metadata = _validate_required_artifacts(result)
    metadata["source_library_path"] = str(library_path)
    return _passed_path("toy_generic", result, metadata=metadata)


def _run_tep_smoke(config: KGConstructionSmokeConfig) -> KGConstructionSmokePath:
    if config.tep_kg_root is None:
        if config.require_tep:
            raise ValueError("TEP smoke requires --tep-kg-root when --require-tep is set")
        return KGConstructionSmokePath(
            name="tep",
            status="skipped",
            reason="no TEP_KG root provided",
        )
    sources = _tep_sources(config.tep_kg_root)
    missing = _missing_tep_artifacts(config.tep_kg_root)
    if missing:
        message = "missing TEP_KG smoke artifacts: " + ", ".join(str(path) for path in missing)
        if config.require_tep:
            raise ValueError(message)
        return KGConstructionSmokePath(name="tep", status="skipped", reason=message)
    result = run_source_kg_construction_workflow(
        SourceKGConstructionWorkflowConfig(
            output_dir=config.output_dir / "tep",
            sources=sources,
            overwrite=config.overwrite,
            run_id="kgbuild_smoke_tep",
        )
    )
    metadata = _validate_required_artifacts(result)
    metadata.update(_validate_tep_rca_metadata(result.output_dir))
    return _passed_path("tep", result, metadata=metadata)


def _run_material_direct_smoke(
    config: KGConstructionSmokeConfig,
) -> KGConstructionSmokePath:
    material_root = config.output_dir / "material_library"
    source_dir = config.output_dir / "material_direct_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    records_path = source_dir / "material_records.jsonl"
    records_path.write_text(_material_direct_records_jsonl(), encoding="utf-8")
    register_kg_material(
        KGMaterialRegisterRequest(
            material_id="smoke_material_note",
            title="Smoke material note",
            source_kind="local_path",
            source_uri=str(source_dir / "material_note.txt"),
            scenario="shared",
            material_type="text",
            extraction=KGMaterialExtractionState(
                status="extracted",
                structured_records_path=str(records_path),
                source_format="jsonl",
                source_id="smoke_material_note",
                extractor_name="pre_extracted_smoke_fixture",
                extractor_version="v1",
                record_count=3,
            ),
        ),
        material_root=material_root,
        overwrite=config.overwrite,
    )
    result = run_material_kg_construction_workflow(
        MaterialKGConstructionWorkflowConfig(
            material_ids=("smoke_material_note",),
            material_root=material_root,
            output_dir=config.output_dir / "material_direct",
            overwrite=config.overwrite,
            run_id="kgbuild_smoke_material_direct",
            extraction_mode="never",
        )
    )
    metadata = _validate_required_material_artifacts(result)
    metadata["material_root"] = str(material_root)
    metadata["material_ids"] = list(result.material_ids)
    metadata["extraction_mode"] = result.summary["material_library"]["extraction_mode"]
    return _passed_path("material_direct", result, metadata=metadata)


def _tep_sources(tep_root: Path) -> tuple[KGConstructionSource, ...]:
    kg_dir = tep_root / "data" / "processed" / "kg"
    rca_dir = tep_root / "data" / "processed" / "rca"
    return (
        KGConstructionSource(
            source_id="tep_semantic_lift",
            source_type="tep_semantic_lift",
            scenario="tep",
            path=kg_dir,
        ),
        KGConstructionSource(
            source_id="tep_variable_mapping",
            source_type="tep_variable_mapping",
            scenario="tep",
            path=kg_dir / "tep_variable_mapping.jsonl",
        ),
        KGConstructionSource(
            source_id="tep_rca_graph",
            source_type="tep_rca_graph",
            scenario="tep",
            path=rca_dir,
        ),
    )


def _missing_tep_artifacts(tep_root: Path) -> list[Path]:
    kg_dir = tep_root / "data" / "processed" / "kg"
    rca_dir = tep_root / "data" / "processed" / "rca"
    required = [
        kg_dir / "semantic_lift_nodes.jsonl",
        kg_dir / "semantic_lift_edges.jsonl",
        kg_dir / "tep_variable_mapping.jsonl",
        rca_dir / "nodes.jsonl",
        rca_dir / "edges.jsonl",
    ]
    return [path for path in required if not path.is_file()]


def _passed_path(
    name: str,
    result: SourceKGConstructionWorkflowResult | MaterialKGConstructionWorkflowResult,
    *,
    metadata: dict[str, Any],
) -> KGConstructionSmokePath:
    output = dict(result.summary.get("output") or {})
    artifacts = {str(key): str(value) for key, value in output.items() if key != "output_dir"}
    return KGConstructionSmokePath(
        name=name,
        status="passed",
        output_dir=result.output_dir,
        summary_path=result.summary_path,
        manifest_path=result.manifest_path,
        artifacts=artifacts,
        metadata=metadata,
    )


def _validate_required_artifacts(
    result: SourceKGConstructionWorkflowResult,
) -> dict[str, Any]:
    return _validate_required_output_artifacts(
        output_dir=result.output_dir,
        run_id=result.run_id,
        summary=result.summary,
    )


def _validate_required_material_artifacts(
    result: MaterialKGConstructionWorkflowResult,
) -> dict[str, Any]:
    metadata = _validate_required_output_artifacts(
        output_dir=result.output_dir,
        run_id=result.run_id,
        summary=result.summary,
    )
    material_library = result.summary.get("material_library")
    if not isinstance(material_library, dict):
        raise ValueError("material smoke missing material_library summary")
    metadata["material_source_ids"] = list(material_library.get("source_ids", []))
    return metadata


def _validate_required_output_artifacts(
    *,
    output_dir: Path,
    run_id: str,
    summary: dict[str, Any],
) -> dict[str, Any]:
    output = dict(summary.get("output") or {})
    missing_keys = [
        key for key in KG_CONSTRUCTION_REQUIRED_ARTIFACT_KEYS if key not in output
    ]
    if missing_keys:
        raise ValueError(
            f"{output_dir} missing construction artifact keys: {missing_keys}"
        )
    missing_files = [
        output[key]
        for key in KG_CONSTRUCTION_REQUIRED_ARTIFACT_KEYS
        if key in output and not Path(str(output[key])).is_file()
    ]
    if missing_files:
        raise ValueError(
            f"{output_dir} missing construction artifact files: {missing_files}"
        )
    return {
        "kg_build_id": run_id,
        "node_count": summary.get("node_count", 0),
        "edge_count": summary.get("edge_count", 0),
        "source_ids": list(summary.get("source_ids", [])),
        "required_artifact_count": len(KG_CONSTRUCTION_REQUIRED_ARTIFACT_KEYS),
    }


def _validate_tep_rca_metadata(output_dir: Path) -> dict[str, Any]:
    edge_rows = _read_csv_rows(output_dir / "edges.csv")
    node_rows = _read_csv_rows(output_dir / "nodes.csv")
    fault_anchor_nodes = [
        row for row in node_rows if row.get("label") == "FaultAnchor"
    ]
    propagation_edges = [
        row for row in edge_rows if row.get("propagation_enabled") == "true"
    ]
    fault_source_edges = [
        row for row in edge_rows if row.get("relation_family") == "FAULT_SOURCE"
    ]
    if not fault_anchor_nodes:
        raise ValueError("TEP smoke did not preserve a FaultAnchor node")
    if not propagation_edges:
        raise ValueError("TEP smoke did not preserve propagation_enabled edges")
    if not fault_source_edges:
        raise ValueError("TEP smoke did not preserve FAULT_SOURCE relation family")
    return {
        "fault_anchor_count": len(fault_anchor_nodes),
        "propagation_edge_count": len(propagation_edges),
        "fault_source_edge_count": len(fault_source_edges),
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _toy_generic_source_csv() -> str:
    return "\n".join(
        [
            "id,name,label,head,relation,tail,scenario,evidence,confidence",
            "PumpA,Pump A,Equipment,,,,shared,pump row,0.82",
            "PressureSignal,Pressure signal,Variable,,,,shared,signal row,0.82",
            ",,,PumpA,MEASURES,PressureSignal,shared,pressure is observed by Pump A sensor,0.62",
            "",
        ]
    )


def _material_direct_records_jsonl() -> str:
    rows = [
        {
            "id": "MaterialCoolingAlert",
            "name": "Material cooling alert",
            "label": "Alert",
            "scenario": "shared",
            "source": "smoke_material_note",
            "evidence": "Cooling alert suggests pump seal wear.",
            "confidence": 0.62,
        },
        {
            "id": "MaterialPumpSealWear",
            "name": "Material pump seal wear",
            "label": "RootCause",
            "scenario": "shared",
            "source": "smoke_material_note",
            "evidence": "Cooling alert suggests pump seal wear.",
            "confidence": 0.62,
        },
        {
            "head": "MaterialCoolingAlert",
            "relation": "CAUSES",
            "tail": "MaterialPumpSealWear",
            "scenario": "shared",
            "source": "smoke_material_note",
            "evidence": "Cooling alert suggests pump seal wear.",
            "confidence": 0.55,
        },
    ]
    return "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
