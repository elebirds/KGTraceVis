"""Workflow facade for the KGBuilder-style source KG compiler."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kgtracevis.source_kg_compiler.compiler import compile_source_kg
from kgtracevis.source_kg_compiler.models import (
    SourceKGArtifactPaths,
    SourceKGLLMClient,
    SourceKGProgressCallback,
)


@dataclass(frozen=True)
class SourceKGCompilerConfig:
    """Configuration for one source KG compiler run."""

    source_paths: tuple[Path, ...]
    output_dir: Path
    llm_client: SourceKGLLMClient | None = None
    default_scenario: str = "shared"
    chunk_size: int = 8000
    chunk_overlap: int = 800
    overwrite: bool = False
    source_limit: int | None = None
    progress_callback: SourceKGProgressCallback | None = None


@dataclass(frozen=True)
class SourceKGCompilerResult:
    """Structured source KG compiler result."""

    output_dir: Path
    artifact_paths: SourceKGArtifactPaths
    summary: dict[str, Any]
    qa_report: dict[str, Any]
    validation_report: dict[str, Any]


def run_source_kg_compiler_workflow(config: SourceKGCompilerConfig) -> SourceKGCompilerResult:
    """Run the source KG compiler workflow."""
    artifacts, paths, qa_report, validation_report = compile_source_kg(
        config.source_paths,
        config.output_dir,
        llm_client=config.llm_client,
        default_scenario=config.default_scenario,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        overwrite=config.overwrite,
        source_limit=config.source_limit,
        progress_callback=config.progress_callback,
    )
    summary = {
        "artifact_type": "source_kg_compiler_summary_v1",
        "output_dir": paths.output_dir.as_posix(),
        "counts": {
            "source_units": len(artifacts.source_units),
            "knowledge_cards": len(artifacts.knowledge_cards),
            "entities": len(artifacts.entities),
            "edges": len(artifacts.edges),
        },
        "qa_status": qa_report["status"],
        "validation_status": validation_report["status"],
        "strict_generated_only": validation_report["strict_generated_only"],
        "artifacts": {
            "source_units": paths.source_units.as_posix(),
            "knowledge_cards": paths.knowledge_cards.as_posix(),
            "entities": paths.entities.as_posix(),
            "edges": paths.edges.as_posix(),
            "nodes_csv": paths.nodes_csv.as_posix(),
            "edges_csv": paths.edges_csv.as_posix(),
            "qa_report": paths.qa_report.as_posix(),
            "validation_report": paths.validation_report.as_posix(),
            "domain_profiles": paths.domain_profiles.as_posix(),
            "domain_profile_report": paths.domain_profile_report.as_posix(),
            "domain_profiles_manifest": paths.domain_profiles_manifest.as_posix(),
            "runtime_views_manifest": paths.runtime_views_manifest.as_posix(),
        },
    }
    return SourceKGCompilerResult(
        output_dir=paths.output_dir,
        artifact_paths=paths,
        summary=summary,
        qa_report=qa_report,
        validation_report=validation_report,
    )
