"""Tests for the Phase 4 RootLens acceptance-bundle script."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, cast


def _load_script_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_rootlens_phase4_acceptance_bundle",
        Path("scripts/build_rootlens_phase4_acceptance_bundle.py"),
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load build_rootlens_phase4_acceptance_bundle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(ModuleType, module)


def test_build_acceptance_bundle_writes_section_manifests(tmp_path: Path) -> None:
    """The acceptance bundle script should write Section 5 assets and notes."""
    script = _load_script_module()
    output_dir = tmp_path / "acceptance_bundle"

    manifest = script.build_acceptance_bundle(
        output_dir=output_dir,
        example_path=Path("data/examples/records/mvtec_records.jsonl"),
        top_k=2,
        overwrite=True,
    )

    assert manifest["artifact_type"] == "rootlens_phase4_acceptance_bundle"
    assert manifest["sections"]["5.1"]["status"] in {"supported", "partial"}
    assert manifest["sections"]["5.2"]["status"] in {"supported", "partial"}
    assert manifest["sections"]["5.3"]["status"] in {"supported", "partial"}

    manifest_path = output_dir / "manifest.json"
    acceptance_md = output_dir / "paper_section5_acceptance.md"
    notes_path = output_dir / "notes.md"
    assert manifest_path.is_file()
    assert acceptance_md.is_file()
    assert notes_path.is_file()

    assert (output_dir / "section_5_1" / "run_detail.json").is_file()
    assert (output_dir / "section_5_2" / "reasoning_focus.json").is_file()
    assert (output_dir / "section_5_3" / "feedback_ledger.json").is_file()
    assert (output_dir / "section_5_3" / "material_chunks.json").is_file()
    assert (output_dir / "section_5_3" / "kg_draft_history.json").is_file()
