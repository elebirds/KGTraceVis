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


def test_download_wm811k_resnet_reports_public_checkpoint_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """WM811K public ResNet downloads should report source and defect-only metadata."""
    captured: dict[str, object] = {}

    def _patched_download_hf_file(repo_id, filename, destination_dir, *, force=False):
        captured.update(
            {
                "repo_id": repo_id,
                "filename": filename,
                "destination_dir": Path(destination_dir),
                "force": force,
            }
        )
        destination = Path(destination_dir) / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"checkpoint")
        return destination

    monkeypatch.setattr(model_assets, "_download_hf_file", _patched_download_hf_file)

    summary = model_assets.download_wm811k_resnet(
        destination_dir=tmp_path / "wm811k" / "checkpoints",
        force=True,
    )

    assert captured == {
        "repo_id": "radai-agent/radai-wm811k-defect-detection",
        "filename": "best_radai_resnet.pt",
        "destination_dir": tmp_path / "wm811k" / "checkpoints",
        "force": True,
    }
    assert summary["preset"] == "wm811k-resnet"
    assert summary["backend"] == "torch-resnet34"
    assert summary["filename"] == "best_radai_resnet.pt"
    assert summary["task"] == "defect_pattern_classification"
    assert summary["produces_root_cause"] is False
    assert "Near-full" in summary["classes"]


def test_download_wm811k_input_table_reports_public_dataset_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """WM811K data downloads should report portable table source metadata."""
    captured: dict[str, object] = {}

    def _patched_download_hf_file(
        repo_id,
        filename,
        destination_dir,
        *,
        force=False,
        repo_type=None,
    ):
        captured.update(
            {
                "repo_id": repo_id,
                "filename": filename,
                "destination_dir": Path(destination_dir),
                "force": force,
                "repo_type": repo_type,
            }
        )
        destination = Path(destination_dir) / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"table")
        return destination

    monkeypatch.setattr(model_assets, "_download_hf_file", _patched_download_hf_file)

    summary = model_assets.download_wm811k_input_table(
        destination_dir=tmp_path / "wm811k" / "input_tables",
        force=True,
    )

    assert captured == {
        "repo_id": "lslattery/wafer-defect-detection",
        "filename": "test.pkl",
        "destination_dir": tmp_path / "wm811k" / "input_tables",
        "force": True,
        "repo_type": "dataset",
    }
    assert summary["dataset"] == "wm811k"
    assert summary["source_repo"] == "lslattery/wafer-defect-detection"
    assert summary["filename"] == "test.pkl"
    assert summary["repo_type"] == "dataset"
    assert summary["input_table"].endswith("test.pkl")
    assert "root-cause" in summary["claim_boundary"]


def test_download_selected_model_assets_can_include_wm811k_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Selected asset summaries should keep WM811K model and data channels separate."""

    def _patched_download_wm811k_resnet(**_kwargs):
        return {"preset": "wm811k-resnet", "checkpoint": "checkpoint.pt"}

    def _patched_download_wm811k_input_table(**kwargs):
        return {
            "source_repo": kwargs["repo_id"],
            "filename": kwargs["filename"],
            "repo_type": kwargs["repo_type"],
            "input_table": "test.pkl",
        }

    monkeypatch.setattr(model_assets, "download_wm811k_resnet", _patched_download_wm811k_resnet)
    monkeypatch.setattr(
        model_assets,
        "download_wm811k_input_table",
        _patched_download_wm811k_input_table,
    )

    summary = model_assets.download_selected_model_assets(
        models=("wm811k-resnet",),
        assets_root=tmp_path / "assets",
        include_wm811k_data=True,
        wm811k_input_repo="custom/wafer",
        wm811k_input_file="public.pkl",
        wm811k_input_repo_type="dataset",
    )

    assert summary["assets"]["wm811k_resnet"]["preset"] == "wm811k-resnet"
    assert summary["data_assets"]["wm811k_input_table"] == {
        "source_repo": "custom/wafer",
        "filename": "public.pkl",
        "repo_type": "dataset",
        "input_table": "test.pkl",
    }


def test_download_selected_model_assets_rejects_unknown_model() -> None:
    """Only configured trusted assets should be accepted by the reusable helper."""
    with pytest.raises(ValueError, match="model asset must be one of"):
        model_assets.download_selected_model_assets(
            models=("unknown",),  # type: ignore[arg-type]
        )
