"""Focused tests for DS-MVTec PatchCore experiment helpers."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from kgtracevis.experiments.mvtec_calibrated_pipeline import (
    MVTecCalibratedPipelineConfig,
    run_mvtec_calibrated_pipeline,
)
from kgtracevis.experiments.mvtec_patchcore import (
    batch_row_from_object_summary,
    build_ds_mvtec_subset_input,
    build_mvtec_like_eval_root,
    discover_ds_mvtec_object_dirs,
    summarize_records,
    write_batch_outputs,
)
from kgtracevis.producers.common import MVTecPrediction


def test_discover_ds_mvtec_object_dirs_filters_valid_objects(tmp_path: Path) -> None:
    """Object discovery should accept a DS-MVTec parent and skip incomplete dirs."""
    root = tmp_path / "Defect_Spectrum" / "DS-MVTec"
    _touch(root / "capsule" / "image" / "good" / "000.png")
    _touch(root / "bottle" / "image" / "good" / "000.png")
    _touch(root / "broken" / "image" / "crack" / "000.png")

    discovered = discover_ds_mvtec_object_dirs(tmp_path / "Defect_Spectrum", max_objects=1)

    assert [path.name for path in discovered] == ["bottle"]


def test_build_mvtec_like_eval_root_uses_valid_links_for_relative_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Eval-root construction should work when callers pass relative paths."""
    monkeypatch.chdir(tmp_path)
    object_dir = Path("DS-MVTec") / "capsule"
    _touch(object_dir / "image" / "good" / "000.png", content=b"image")
    _touch(object_dir / "image" / "crack" / "001.png", content=b"defect")
    _touch(object_dir / "mask" / "crack" / "001_mask.png", content=b"mask")

    input_root = build_mvtec_like_eval_root(
        object_dir=object_dir,
        output_root=Path("runs") / "eval_input",
        object_name="capsule",
        normal_label="good",
        labels=["crack"],
        max_per_label=1,
    )

    assert (input_root / "capsule" / "test" / "good" / "000.png").read_bytes() == b"image"
    assert (input_root / "capsule" / "test" / "crack" / "001.png").read_bytes() == b"defect"
    assert (
        input_root / "capsule" / "ground_truth" / "crack" / "001_mask.png"
    ).read_bytes() == b"mask"


def test_build_ds_mvtec_subset_input_samples_good_and_defects(tmp_path: Path) -> None:
    """Shared DS-MVTec subset builder should create a standard MVTec-like input tree."""
    root = tmp_path / "Defect_Spectrum" / "DS-MVTec"
    _touch(root / "bottle" / "image" / "good" / "000.png", content=b"good")
    _touch(root / "bottle" / "image" / "crack" / "001.png", content=b"defect")
    _touch(root / "bottle" / "mask" / "crack" / "001_mask.png", content=b"mask")

    input_root, manifest = build_ds_mvtec_subset_input(
        dataset_root=tmp_path / "Defect_Spectrum",
        output_root=tmp_path / "pipeline_input",
        max_good=1,
        max_defect_per_label=1,
    )

    assert (input_root / "bottle" / "test" / "good" / "000.png").read_bytes() == b"good"
    assert (input_root / "bottle" / "test" / "crack" / "001.png").read_bytes() == b"defect"
    assert (
        input_root / "bottle" / "ground_truth" / "crack" / "001_mask.png"
    ).read_bytes() == b"mask"
    assert [row["label"] for row in manifest] == ["good", "crack"]


def test_run_mvtec_calibrated_pipeline_writes_records_and_adapter_outputs(
    tmp_path: Path,
) -> None:
    """The one-command pipeline should connect producer records to KGTracePipeline."""
    root = tmp_path / "Defect_Spectrum" / "DS-MVTec"
    _touch(root / "bottle" / "image" / "good" / "000.png", content=b"good")
    _touch(root / "bottle" / "image" / "scratch" / "001.png", content=b"defect")
    threshold_config = tmp_path / "thresholds.json"
    threshold_config.write_text(
        json.dumps(
            {
                "threshold_source": "test_supervised",
                "uses_ground_truth": True,
                "objects": {
                    "bottle": {
                        "score_threshold": 0.8,
                        "map_threshold": 0.8,
                        "min_area_ratio": 0.01,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    output = run_mvtec_calibrated_pipeline(
        MVTecCalibratedPipelineConfig(
            dataset_root=tmp_path / "Defect_Spectrum",
            artifact_root=tmp_path / "artifacts",
            threshold_config=threshold_config,
            output_root=tmp_path / "pipeline",
            max_good=1,
            max_defect_per_label=1,
            overwrite=True,
        ),
        predictor=_FakeCalibratedPredictor(),
    )

    assert output.summary["record_count"] == 2
    assert output.summary["adapter_case_count"] == 2
    assert output.records_path.is_file()
    assert output.adapter_summary_path.is_file()
    assert output.adapter_table_path.is_file()
    assert output.summary["sanity"]["defect_pred_anomalous_count"] == 1
    assert output.summary["sanity"]["good_pred_normal_count"] == 1


def test_summarize_records_reports_detection_ranges_and_iou(tmp_path: Path) -> None:
    """Record summaries should be deterministic and not require Anomalib."""
    predicted_mask = tmp_path / "pred_mask.json"
    gt_mask = tmp_path / "gt_mask.png"
    predicted_mask.write_text(json.dumps([[1, 0], [1, 0]]), encoding="utf-8")
    Image.fromarray(np.asarray([[255, 0], [0, 0]], dtype=np.uint8)).save(gt_mask)
    records = [
        {
            "case_id": "mvtec_bottle_test_good_000",
            "defect_type": "good",
            "score": 0.1,
            "detector": {"raw_pred_label": "tensor([False])"},
            "mask_stats": {"area_ratio": 0.0},
        },
        {
            "case_id": "mvtec_bottle_test_crack_000",
            "defect_type": "crack",
            "score": 0.9,
            "detector": {"raw_pred_label": "tensor([True])"},
            "mask_stats": {"area_ratio": 0.5},
            "mask_path": str(predicted_mask),
            "gt_mask_path": str(gt_mask),
        },
    ]

    summary = summarize_records(records)

    assert summary["record_count"] == 2
    assert summary["defect_pred_anomalous_count"] == 1
    assert summary["good_pred_normal_count"] == 1
    assert summary["score_min"] == 0.1
    assert summary["score_max"] == 0.9
    assert summary["mask_area_min"] == 0.0
    assert summary["mask_area_max"] == 0.5
    assert summary["mean_iou"] == 0.5


def test_summarize_records_treats_abnormal_label_as_anomalous() -> None:
    """The text label parser should not classify 'abnormal' as normal."""
    summary = summarize_records(
        [
            {
                "case_id": "mvtec_bottle_test_crack_001",
                "defect_type": "crack",
                "score": 0.2,
                "detector": {"raw_pred_label": "abnormal"},
            }
        ]
    )

    assert summary["defect_pred_anomalous_count"] == 1
    assert summary["defect_pred_normal_count"] == 0


def test_summarize_records_prefers_calibrated_top_level_prediction() -> None:
    """Calibrated producer labels should drive pipeline sanity summaries."""
    summary = summarize_records(
        [
            {
                "case_id": "mvtec_bottle_test_good_001",
                "defect_type": "good",
                "score": 2.0,
                "pred_label": "normal",
                "detector": {"raw_pred_label": None, "pred_label": "normal"},
            }
        ]
    )

    assert summary["good_pred_normal_count"] == 1
    assert summary["good_pred_anomalous_count"] == 0


def test_batch_outputs_include_failed_object_rows(tmp_path: Path) -> None:
    """Batch summary JSON and CSV should preserve per-object status and errors."""
    object_summary = {
        "record_count": 2,
        "records_path": "records.jsonl",
        "adapter_summary": "adapter.json",
        "sanity": {
            "record_count": 2,
            "defect_count": 1,
            "good_count": 1,
            "defect_pred_anomalous_count": 1,
            "good_pred_normal_count": 1,
            "score_min": 0.1,
            "score_max": 0.9,
        },
    }
    rows = [
        batch_row_from_object_summary(
            object_name="bottle",
            status="ok",
            object_summary_path=tmp_path / "bottle" / "summary.json",
            object_summary=object_summary,
        ),
        batch_row_from_object_summary(
            object_name="capsule",
            status="failed",
            error="RuntimeError: failed fit",
        ),
    ]

    summary_path, table_path = write_batch_outputs(
        output_root=tmp_path,
        dataset_root=tmp_path / "DS-MVTec",
        rows=rows,
        args={"max_eval_per_label": 1},
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    csv_text = table_path.read_text(encoding="utf-8")
    assert summary["success_count"] == 1
    assert summary["failed_count"] == 1
    assert "capsule,failed" in csv_text


def _touch(path: Path, *, content: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class _FakeCalibratedPredictor:
    """Deterministic MVTec predictor for calibrated pipeline tests."""

    def predict(self, image_path: Path) -> MVTecPrediction:
        label = image_path.parent.name
        score = 0.9 if label != "good" else 0.2
        return {
            "score": score,
            "confidence": score,
            "anomaly_map": [[0.1, score], [0.2, score]],
            "metadata": {"fixture": "calibrated_pipeline"},
        }
