"""Tests for trusted model asset download helpers."""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from kgtracevis.producers import model_assets


def test_download_mvtec_stfpm_extracts_openvino_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """MVTec STFPM download should extract a safe tar and report the XML checkpoint."""
    source_tar = tmp_path / "source.tar"
    source_xml = tmp_path / "stfpm_capsule.xml"
    source_xml.write_text("<xml />", encoding="utf-8")
    with tarfile.open(source_tar, "w") as archive:
        archive.add(source_xml, arcname="nested/stfpm_capsule.xml")

    def _patched_download_hf_file(*_args, **_kwargs) -> Path:
        return source_tar

    monkeypatch.setattr(model_assets, "_download_hf_file", _patched_download_hf_file)

    summary = model_assets.download_mvtec_stfpm(
        repo_id="example/repo",
        filename="openvino_model.tar",
        destination_dir=tmp_path / "checkpoints",
    )

    checkpoint = Path(str(summary["checkpoint"]))
    assert checkpoint.is_file()
    assert checkpoint.name == "stfpm_capsule.xml"
    assert summary["preset"] == "stfpm"


def test_download_mvtec_torch_checkpoint_uses_configured_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Configurable MVTec torch presets should be copied to their default names."""
    source_checkpoint = tmp_path / "source.pt"
    source_checkpoint.write_bytes(b"checkpoint")

    def _patched_download_hf_file(*_args, output_name=None, **_kwargs) -> Path:
        destination = tmp_path / str(output_name)
        destination.write_bytes(source_checkpoint.read_bytes())
        return destination

    monkeypatch.setattr(model_assets, "_download_hf_file", _patched_download_hf_file)

    summary = model_assets.download_mvtec_torch_checkpoint(
        preset="patchcore",
        repo_id="trusted/repo",
        filename="custom_patchcore.pt",
        destination_dir=tmp_path / "checkpoints",
        default_filename="mvtec_patchcore.ckpt",
        env="KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT",
    )

    assert summary["preset"] == "patchcore"
    assert summary["repo_id"] == "trusted/repo"
    assert summary["checkpoint"].endswith("mvtec_patchcore.ckpt")


def test_download_mvtec_torch_checkpoint_requires_source() -> None:
    """PatchCore/EfficientAD downloads should not invent unsupported public sources."""
    with pytest.raises(ValueError, match="No default public download source"):
        model_assets.download_mvtec_torch_checkpoint(
            preset="efficientad",
            repo_id="",
            filename="mvtec_efficientad.pt",
            default_filename="mvtec_efficientad.pt",
            env="KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT",
        )


def test_download_selected_model_assets_rejects_unknown_model() -> None:
    """Only configured trusted assets should be accepted by the reusable helper."""
    with pytest.raises(ValueError, match="model asset must be one of"):
        model_assets.download_selected_model_assets(
            models=("unknown",),  # type: ignore[arg-type]
        )
