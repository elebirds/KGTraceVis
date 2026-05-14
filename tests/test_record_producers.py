"""Tests for model-aware producer-output record builders."""

from __future__ import annotations

import csv
import importlib.util
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pytest

import kgtracevis.producers.backends as producer_backends
from kgtracevis.adapters.batch import evidence_from_records, load_records
from kgtracevis.mask.mask_feature_extractor import summarize_mask_features
from kgtracevis.producers.backends import (
    AMAZON_PATCHCORE_BACKEND,
    ANOMALIB_OPENVINO_BACKEND,
    ANOMALIB_TORCH_BACKEND,
    SKLEARN_BACKEND,
    TORCH_RESNET_BACKEND,
    AmazonPatchCoreBackend,
    AmazonPatchCoreObjectRouter,
    AnomalibMVTecBackend,
    SklearnWM811KBackend,
    TorchWM811KBackend,
    _first_engine_prediction,
    _prepare_amazon_patchcore_runtime,
    amazon_patchcore_mvtec_artifact_dir_name,
    amazon_patchcore_prediction_to_mvtec_prediction,
    anomalib_prediction_to_mvtec_prediction,
    discover_amazon_patchcore_prepend,
    is_amazon_patchcore_artifact_collection,
    is_amazon_patchcore_artifact_dir,
    list_amazon_patchcore_artifact_dirs,
    load_trusted_sklearn_model,
    load_trusted_torch_model,
    normalize_amazon_patchcore_mvtec_object,
    resolve_amazon_patchcore_artifact_dir,
)
from kgtracevis.producers.common import (
    MVTecPrediction,
    WM811KPrediction,
    deterministic_subset,
    filter_forbidden_outputs,
    write_jsonl_records,
)
from kgtracevis.producers.mvtec_calibration import (
    calibrate_thresholds_from_records,
    threshold_config_from_mapping,
)
from kgtracevis.producers.mvtec_records import build_mvtec_records, mask_stats_from_array
from kgtracevis.producers.tep_records import TEP_RBC_BACKEND, build_tep_records
from kgtracevis.producers.wm811k_records import build_wm811k_records
from kgtracevis.workflows import dataset_records as dataset_record_workflow
from kgtracevis.workflows.tep_rca import tep_scenario_selector

BUILD_SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_dataset_records.py"


def _load_build_script() -> Any:
    spec = importlib.util.spec_from_file_location("build_dataset_records", BUILD_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_script = _load_build_script()


class FakeMVTecPredictor:
    """Deterministic anomaly predictor used by producer tests."""

    def predict(self, image_path: Path) -> MVTecPrediction:
        """Return stable fake model outputs for one image."""
        defect = image_path.parent.name
        score = 0.91 if defect == "scratch" else 0.73
        return {
            "score": score,
            "confidence": score,
            "anomaly_map": [
                [0.0, 0.0, 0.0, 0.0],
                [0.0, score, score, 0.0],
                [0.0, 0.0, 0.0, 0.0],
            ],
            "metadata": {"fixture": "mvtec"},
        }


class FakeWM811KClassifier:
    """Deterministic wafer-map classifier used by producer tests."""

    def predict(
        self,
        wafer_map: Sequence[Sequence[Any]],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> WM811KPrediction:
        """Return a stable pattern from native metadata or map density."""
        native = str((metadata or {}).get("native_failure_pattern") or "")
        pattern = native if native.lower() != "none" else "Random"
        return {
            "pattern": pattern,
            "confidence": 0.84,
            "saliency_map": [[0.1 for _value in row] for row in wafer_map],
            "metadata": {
                "fixture": "wm811k",
                "model_source": "radai-agent/radai-wm811k-defect-detection",
                "model_file": "best_radai_resnet.pt",
                "classes": ["Center", "Near-full"],
                "task": "defect_pattern_classification",
                "produces_root_cause": False,
            },
        }


class TinySklearnWaferModel:
    """Tiny sklearn-like classifier that can be serialized with joblib."""

    classes_ = np.asarray(["Random", "Near-full"])

    def predict(self, features: Any) -> np.ndarray:
        """Predict Near-full when the flattened wafer map is dense."""
        rows = np.asarray(features, dtype=float)
        return np.where(rows.sum(axis=1) > 4, "Near-full", "Random")

    def predict_proba(self, features: Any) -> np.ndarray:
        """Return deterministic class probabilities aligned with classes_."""
        rows = np.asarray(features, dtype=float)
        return np.asarray([[0.08, 0.92] if row.sum() > 4 else [0.71, 0.29] for row in rows])


class ZeroProbabilitySklearnWaferModel:
    """Sklearn-like classifier that returns a valid zero predicted-class probability."""

    classes_ = np.asarray(["Random", "Near-full"])

    def predict(self, features: Any) -> np.ndarray:
        """Always predict Near-full for shape/label plumbing tests."""
        rows = np.asarray(features, dtype=float)
        return np.asarray(["Near-full" for _row in rows])

    def predict_proba(self, features: Any) -> np.ndarray:
        """Return a zero probability for the predicted class."""
        rows = np.asarray(features, dtype=float)
        return np.asarray([[1.0, 0.0] for _row in rows])


class InjectedAnomalibInferencer:
    """Anomalib-like inferencer used without installing anomalib."""

    def predict(self, image_path: Path) -> SimpleNamespace:
        """Return an Anomalib-style prediction object."""
        return SimpleNamespace(
            pred_score=np.float32(0.67),
            pred_label="anomalous",
            anomaly_map=np.asarray([[0.1, 0.7], [0.2, 0.3]]),
        )


class InjectedAmazonPatchCoreModel:
    """Official PatchCore-like model used without installing FAISS or patchcore."""

    input_shape = (3, 320, 320)

    def __init__(self) -> None:
        self.seen_tensor = False

    def predict(self, image_tensor: Any) -> tuple[list[np.float32], list[np.ndarray]]:
        """Return the official PatchCore `(scores, segmentations)` shape."""
        self.seen_tensor = image_tensor == "tensor"
        return (
            [np.float32(0.88)],
            [np.asarray([[0.0, 0.6], [0.2, 0.9]], dtype=np.float32)],
        )


class ShapeSensitiveOpenVINOInferencer:
    """OpenVINO-like inferencer whose default predict path does not resize images."""

    input_blob = SimpleNamespace(any_name="input", shape=(1, 3, 2, 2))

    def __init__(self) -> None:
        self.last_input_shape: tuple[int, ...] | None = None

    def predict(self, _image_path: Path) -> SimpleNamespace:
        """Simulate Anomalib failing before our compatibility resize path."""
        raise RuntimeError("model input shape=[1,3,2,2] and tensor shape=(1.3.4.4) incompatible")

    def pre_process(self, image: np.ndarray) -> np.ndarray:
        """Mirror Anomalib's normalize and HWC-to-NCHW preprocessing."""
        image = image.astype(np.float32) / 255.0
        return np.expand_dims(image, axis=0).transpose(0, 3, 1, 2)

    def model(self, inputs: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Return a fake OpenVINO prediction only when the input has been resized."""
        image = inputs["input"]
        self.last_input_shape = tuple(image.shape)
        if image.shape != (1, 3, 2, 2):
            raise RuntimeError(f"unexpected input shape: {image.shape}")
        return {"output": np.asarray([[0.1, 0.8], [0.2, 0.3]], dtype=np.float32)}

    def post_process(self, predictions: Mapping[str, np.ndarray]) -> Mapping[str, np.ndarray]:
        """Return the prediction mapping as OpenVINO post-process output."""
        return predictions


def test_mvtec_producer_emits_adapter_compatible_model_records(tmp_path: Path) -> None:
    """MVTec producer should scan folders, call the predictor, and emit records."""
    root = tmp_path / "mvtec"
    _touch(root / "bottle" / "test" / "scratch" / "000.png")
    _touch(root / "bottle" / "test" / "good" / "001.png")
    _touch(root / "bottle" / "ground_truth" / "scratch" / "000_mask.png")

    records = build_mvtec_records(
        root,
        FakeMVTecPredictor(),
        output_dir=tmp_path / "generated",
        model_backend="fake",
        checkpoint=tmp_path / "checkpoint.ckpt",
        threshold=0.5,
    )

    assert len(records) == 1
    record = records[0]
    assert record["dataset"] == "mvtec"
    assert record["case_id"] == "mvtec_bottle_test_scratch_000"
    assert record["object"] == "bottle"
    assert record["defect_type"] == "scratch"
    assert record["confidence"] == 0.91
    assert record["annotation_type"] == "native_ground_truth"
    assert Path(str(record["heatmap_path"])).exists()
    assert Path(str(record["mask_path"])).exists()
    assert record["gt_mask_path"].endswith("000_mask.png")
    assert record["mask_stats"]["area_ratio"] > 0
    assert record["detector"]["backend"] == "fake"
    assert _forbidden_keys(record) == []

    evidence = evidence_from_records(records, dataset="mvtec")
    assert evidence[0].dataset == "mvtec"
    assert evidence[0].adapter is not None
    assert evidence[0].adapter.name == "mvtec"
    assert evidence[0].kg_analysis.top_k_paths == []


def test_mvtec_producer_applies_object_threshold_config(tmp_path: Path) -> None:
    """Calibrated thresholds should control label/confidence and mask generation."""
    root = tmp_path / "mvtec"
    _touch(root / "bottle" / "test" / "scratch" / "000.png")
    _touch(root / "bottle" / "test" / "good" / "001.png")
    config = threshold_config_from_mapping(
        {
            "threshold_source": "supervised_ds_mvtec_quick_calibration",
            "uses_ground_truth": True,
            "objects": {
                "bottle": {
                    "score_threshold": 0.8,
                    "map_threshold": 0.8,
                    "min_area_ratio": 0.01,
                    "method": "supervised_f1_quick",
                }
            },
        }
    )

    records = build_mvtec_records(
        root,
        FakeMVTecPredictor(),
        output_dir=tmp_path / "generated",
        model_backend="fake",
        threshold_config=config,
        include_good=True,
    )

    by_label = {record["defect_type"]: record for record in records}
    scratch = by_label["scratch"]
    good = by_label["good"]
    assert scratch["confidence"] == 1.0
    assert scratch["pred_label"] == "anomalous"
    assert scratch["detector"]["score_threshold"] == 0.8
    assert scratch["detector"]["map_threshold"] == 0.8
    assert scratch["detector"]["threshold_source"] == "supervised_ds_mvtec_quick_calibration"
    assert scratch["mask_stats"]["area_ratio"] > 0
    assert good["confidence"] == 0.0
    assert good["pred_label"] == "normal"
    assert good["mask_stats"]["area_ratio"] == 0.0


def test_calibrate_thresholds_from_records_uses_scores_and_gt_masks(tmp_path: Path) -> None:
    """Calibration helpers should produce object-specific score and map thresholds."""
    good_heatmap = tmp_path / "good_heatmap.json"
    defect_heatmap = tmp_path / "defect_heatmap.json"
    gt_mask = tmp_path / "defect_mask.png"
    good_heatmap.write_text(json.dumps([[0.1, 0.2], [0.1, 0.2]]), encoding="utf-8")
    defect_heatmap.write_text(json.dumps([[0.1, 0.9], [0.2, 0.8]]), encoding="utf-8")
    _write_mask(gt_mask, [[0, 255], [0, 255]])

    thresholds = calibrate_thresholds_from_records(
        [
            {
                "object": "bottle",
                "defect_type": "good",
                "score": 0.2,
                "heatmap_path": str(good_heatmap),
            },
            {
                "object": "bottle",
                "defect_type": "scratch",
                "score": 0.9,
                "heatmap_path": str(defect_heatmap),
                "gt_mask_path": str(gt_mask),
            },
        ],
        min_area_ratio=0.02,
    )

    assert len(thresholds) == 1
    threshold = thresholds[0]
    assert threshold.object_name == "bottle"
    assert threshold.score_threshold == pytest.approx(0.9)
    assert threshold.map_threshold is not None
    assert 0.2 < threshold.map_threshold <= 0.9
    assert threshold.min_area_ratio == 0.02
    assert threshold.uses_ground_truth is True


def test_anomalib_backend_normalizes_injected_inferencer_prediction(tmp_path: Path) -> None:
    """Anomalib wrappers should normalize predictions without importing anomalib in tests."""
    backend = AnomalibMVTecBackend(
        backend=ANOMALIB_TORCH_BACKEND,
        checkpoint=tmp_path / "exported.pt",
        device="cpu",
        inferencer=InjectedAnomalibInferencer(),
    )

    prediction = backend.predict(tmp_path / "image.png")

    assert prediction["score"] == pytest.approx(0.67)
    assert prediction["confidence"] == pytest.approx(0.67)
    assert prediction["label"] == "anomalous"
    assert prediction["anomaly_map"] == [[0.1, 0.7], [0.2, 0.3]]
    assert prediction["metadata"]["source_backend"] == ANOMALIB_TORCH_BACKEND
    assert prediction["metadata"]["device"] == "cpu"


def test_amazon_patchcore_backend_normalizes_official_prediction_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Amazon PatchCore backend should emit standard MVTec predictions."""
    checkpoint = _amazon_patchcore_artifact_dir(tmp_path / "mvtec_bottle")
    model = InjectedAmazonPatchCoreModel()
    monkeypatch.setattr(
        producer_backends,
        "_official_patchcore_image_tensor",
        lambda *_args, **_kwargs: "tensor",
    )
    backend = AmazonPatchCoreBackend(
        checkpoint=checkpoint,
        device="cpu",
        model=model,
    )

    prediction = backend.predict(tmp_path / "image.png")

    assert model.seen_tensor is True
    assert prediction["score"] == pytest.approx(0.88)
    assert prediction["confidence"] == pytest.approx(0.88)
    np.testing.assert_allclose(
        np.asarray(prediction["anomaly_map"], dtype=float),
        np.asarray([[0.0, 0.6], [0.2, 0.9]], dtype=float),
    )
    assert prediction["metadata"]["source_backend"] == AMAZON_PATCHCORE_BACKEND
    assert prediction["metadata"]["checkpoint"] == str(checkpoint)
    assert prediction["metadata"]["model_source"] == "amazon-science/patchcore-inspection"
    assert prediction["metadata"]["model_format"] == "amazon-patchcore-faiss-pkl"


def test_amazon_patchcore_backend_clamps_unbounded_scores_to_confidence() -> None:
    """Official PatchCore distance scores should not become invalid Evidence confidence."""
    prediction = amazon_patchcore_prediction_to_mvtec_prediction(
        ([3556.79], [np.asarray([[0.0, 1.0]])]),
        checkpoint="official/mvtec_bottle",
        device="cpu",
    )

    assert prediction["score"] == pytest.approx(3556.79)
    assert prediction["confidence"] == 1.0


def test_amazon_patchcore_conversion_accepts_mapping_outputs() -> None:
    """Normalization should tolerate dict-shaped official wrapper outputs."""
    prediction = amazon_patchcore_prediction_to_mvtec_prediction(
        {
            "scores": [0.72],
            "segmentations": [np.asarray([[0.1, 0.7], [0.0, 0.3]])],
        },
        checkpoint="official/mvtec_bottle",
        device="cpu",
    )

    assert prediction["score"] == pytest.approx(0.72)
    assert prediction["confidence"] == pytest.approx(0.72)
    assert prediction["anomaly_map"] == [[0.1, 0.7], [0.0, 0.3]]
    assert prediction["metadata"]["source_backend"] == AMAZON_PATCHCORE_BACKEND


def test_amazon_patchcore_artifact_validation_names_required_files(tmp_path: Path) -> None:
    """Official artifact dirs should fail clearly when files are absent."""
    with pytest.raises(FileNotFoundError, match="patchcore_params.pkl"):
        discover_amazon_patchcore_prepend(tmp_path / "missing")

    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "patchcore_params.pkl").write_bytes(b"params")

    with pytest.raises(FileNotFoundError, match="nnscorer_search_index.faiss"):
        discover_amazon_patchcore_prepend(incomplete)


def test_amazon_patchcore_object_root_resolves_mvtec_artifact_dirs(
    tmp_path: Path,
) -> None:
    """Object roots should map canonical MVTec names to official artifact dirs."""
    root = tmp_path / "models"
    bottle_dir = _amazon_patchcore_artifact_dir(root / "mvtec_bottle")
    metal_nut_dir = _amazon_patchcore_artifact_dir(root / "mvtec_metal_nut")

    assert normalize_amazon_patchcore_mvtec_object("MVTec Metal-Nut") == "metal_nut"
    assert amazon_patchcore_mvtec_artifact_dir_name("metal nut") == "mvtec_metal_nut"
    assert resolve_amazon_patchcore_artifact_dir(root, object_name="bottle") == bottle_dir
    assert resolve_amazon_patchcore_artifact_dir(root, object_name="metal nut") == metal_nut_dir
    assert list_amazon_patchcore_artifact_dirs(root) == {
        "bottle": bottle_dir,
        "metal_nut": metal_nut_dir,
    }


def test_amazon_patchcore_lfs_pointer_artifacts_are_not_available(
    tmp_path: Path,
) -> None:
    """Git LFS pointer files should not count as usable official artifacts."""
    root = tmp_path / "models"
    pointer_dir = root / "mvtec_bottle"
    _amazon_patchcore_pointer_artifact_dir(pointer_dir)

    with pytest.raises(FileNotFoundError, match="Git LFS pointer"):
        discover_amazon_patchcore_prepend(pointer_dir)
    with pytest.raises(FileNotFoundError, match="Git LFS pointer"):
        resolve_amazon_patchcore_artifact_dir(root, object_name="bottle")

    assert is_amazon_patchcore_artifact_dir(pointer_dir) is False
    assert is_amazon_patchcore_artifact_collection(root) is False
    assert list_amazon_patchcore_artifact_dirs(root) == {}


def test_amazon_patchcore_object_root_missing_object_error_is_actionable(
    tmp_path: Path,
) -> None:
    """Missing object artifacts should name the expected object directory."""
    root = tmp_path / "models"
    _amazon_patchcore_artifact_dir(root / "mvtec_bottle")

    with pytest.raises(FileNotFoundError, match="mvtec_capsule"):
        resolve_amazon_patchcore_artifact_dir(root, object_name="capsule")


def test_amazon_patchcore_object_router_lazily_routes_by_image_path(
    tmp_path: Path,
) -> None:
    """The routed predictor should instantiate one backend per encountered object."""
    root = tmp_path / "models"
    bottle_dir = _amazon_patchcore_artifact_dir(root / "mvtec_bottle")
    capsule_dir = _amazon_patchcore_artifact_dir(root / "mvtec_capsule")
    seen: list[Path] = []

    class SentinelPredictor:
        def __init__(self, checkpoint: Path) -> None:
            self.checkpoint = checkpoint

        def predict(self, _image_path: Path) -> MVTecPrediction:
            return {"score": 0.42, "metadata": {"checkpoint": str(self.checkpoint)}}

    def predictor_factory(checkpoint: Path) -> SentinelPredictor:
        seen.append(checkpoint)
        return SentinelPredictor(checkpoint)

    router = AmazonPatchCoreObjectRouter(
        checkpoint_root=root,
        predictor_factory=predictor_factory,
    )

    bottle_prediction = router.predict(tmp_path / "input" / "bottle" / "test" / "bad" / "0.png")
    capsule_prediction = router.predict(
        tmp_path / "input" / "capsule" / "test" / "bad" / "0.png"
    )
    router.predict(tmp_path / "input" / "bottle" / "test" / "bad" / "1.png")

    assert bottle_prediction["metadata"]["checkpoint"] == str(bottle_dir)
    assert capsule_prediction["metadata"]["checkpoint"] == str(capsule_dir)
    assert seen == [bottle_dir, capsule_dir]


def test_amazon_patchcore_runtime_guard_sets_macos_openmp_workaround(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The official backend should avoid macOS OpenMP aborts and thread crashes."""
    monkeypatch.setattr(producer_backends.sys, "platform", "darwin")
    for key in (
        "KMP_DUPLICATE_LIB_OK",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "OPENBLAS_NUM_THREADS",
    ):
        monkeypatch.delenv(key, raising=False)

    _prepare_amazon_patchcore_runtime()

    assert producer_backends.os.environ["KMP_DUPLICATE_LIB_OK"] == "TRUE"
    assert producer_backends.os.environ["OMP_NUM_THREADS"] == "1"
    assert producer_backends.os.environ["MKL_NUM_THREADS"] == "1"
    assert producer_backends.os.environ["VECLIB_MAXIMUM_THREADS"] == "1"
    assert producer_backends.os.environ["OPENBLAS_NUM_THREADS"] == "1"


def test_amazon_patchcore_runtime_guard_preserves_existing_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The macOS OpenMP workaround should not override explicit user settings."""
    monkeypatch.setattr(producer_backends.sys, "platform", "darwin")
    monkeypatch.setenv("KMP_DUPLICATE_LIB_OK", "FALSE")
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    monkeypatch.setenv("MKL_NUM_THREADS", "2")
    monkeypatch.setenv("VECLIB_MAXIMUM_THREADS", "2")
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "2")

    _prepare_amazon_patchcore_runtime()

    assert producer_backends.os.environ["KMP_DUPLICATE_LIB_OK"] == "FALSE"
    assert producer_backends.os.environ["OMP_NUM_THREADS"] == "2"
    assert producer_backends.os.environ["MKL_NUM_THREADS"] == "2"
    assert producer_backends.os.environ["VECLIB_MAXIMUM_THREADS"] == "2"
    assert producer_backends.os.environ["OPENBLAS_NUM_THREADS"] == "2"


def test_amazon_patchcore_runtime_guard_is_macos_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-macOS environments should not receive the FAISS/torch OpenMP workaround."""
    monkeypatch.setattr(producer_backends.sys, "platform", "linux")
    for key in (
        "KMP_DUPLICATE_LIB_OK",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "OPENBLAS_NUM_THREADS",
    ):
        monkeypatch.delenv(key, raising=False)

    _prepare_amazon_patchcore_runtime()

    assert "KMP_DUPLICATE_LIB_OK" not in producer_backends.os.environ
    assert "OMP_NUM_THREADS" not in producer_backends.os.environ
    assert "MKL_NUM_THREADS" not in producer_backends.os.environ
    assert "VECLIB_MAXIMUM_THREADS" not in producer_backends.os.environ
    assert "OPENBLAS_NUM_THREADS" not in producer_backends.os.environ


def test_first_engine_prediction_returns_first_item() -> None:
    """Engine prediction normalization should accept Anomalib's nested output lists."""
    prediction = SimpleNamespace(pred_score=0.42)

    assert _first_engine_prediction([[prediction]]) is prediction


def test_openvino_backend_resizes_static_input_after_shape_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenVINO fallback should resize uploaded images to the exported model shape."""
    inferencer = ShapeSensitiveOpenVINOInferencer()
    monkeypatch.setattr(
        producer_backends,
        "_read_rgb_image",
        lambda _image_path: np.full((4, 4, 3), 255, dtype=np.uint8),
    )
    backend = AnomalibMVTecBackend(
        backend=ANOMALIB_OPENVINO_BACKEND,
        checkpoint=tmp_path / "exported.xml",
        device="CPU",
        inferencer=inferencer,
    )

    prediction = backend.predict(tmp_path / "image.png")

    assert inferencer.last_input_shape == (1, 3, 2, 2)
    assert prediction["score"] == pytest.approx(0.8)
    assert prediction["confidence"] == pytest.approx(0.8)
    np.testing.assert_allclose(
        np.asarray(prediction["anomaly_map"], dtype=float),
        np.asarray([[0.1, 0.8], [0.2, 0.3]], dtype=float),
    )
    assert prediction["metadata"]["source_backend"] == ANOMALIB_OPENVINO_BACKEND


def test_anomalib_prediction_conversion_preserves_zero_scores() -> None:
    """Anomalib conversion should keep valid zero score/confidence values."""
    prediction = anomalib_prediction_to_mvtec_prediction(
        {
            "pred_score": np.asarray([0.0]),
            "confidence": 0.0,
            "pred_label": 0,
            "pred_mask": np.asarray([[0, 0], [0, 0]]),
        },
        backend=ANOMALIB_TORCH_BACKEND,
        checkpoint="local.pt",
        device="cpu",
    )

    assert prediction["score"] == 0.0
    assert prediction["confidence"] == 0.0
    assert prediction["label"] == "0"
    assert prediction["mask"] == [[0, 0], [0, 0]]
    assert prediction["metadata"]["checkpoint"] == "local.pt"


def test_anomalib_prediction_conversion_squeezes_spatial_singletons() -> None:
    """PatchCore-style batch/channel dimensions should not break mask geometry."""
    prediction = anomalib_prediction_to_mvtec_prediction(
        {
            "pred_score": 0.81,
            "anomaly_map": np.asarray([[[0.1, 0.9], [0.2, 0.3]]]),
            "pred_mask": np.asarray([[[False, True], [False, True]]]),
        },
        backend=ANOMALIB_TORCH_BACKEND,
        checkpoint="local.ckpt",
        device="cpu",
    )

    assert prediction["anomaly_map"] == [[0.1, 0.9], [0.2, 0.3]]
    assert prediction["mask"] == [[False, True], [False, True]]


def test_wm811k_producer_emits_adapter_compatible_model_records(tmp_path: Path) -> None:
    """WM811K producer should read a table, call the classifier, and emit records."""
    table_path = tmp_path / "wm811k.pkl"
    pd.DataFrame(
        [
            {
                "waferMap": [[2, 2, 2], [2, 0, 2], [2, 2, 2]],
                "failureType": [["Near-full"]],
                "lotName": "LotA",
                "waferIndex": 1,
            },
            {
                "waferMap": [[0, 0], [0, 0]],
                "failureType": [["none"]],
                "lotName": "LotA",
                "waferIndex": 2,
            },
        ]
    ).to_pickle(table_path)

    records = build_wm811k_records(
        table_path,
        FakeWM811KClassifier(),
        output_dir=tmp_path / "generated",
        model_backend="fake",
        checkpoint=tmp_path / "classifier.ckpt",
        threshold=0.5,
    )

    assert len(records) == 1
    record = records[0]
    assert record["dataset"] == "wafer"
    assert record["adapter"] == "wm811k"
    assert record["case_id"] == "wm811k_lota_1"
    assert record["failure_pattern"] == "Near-full"
    assert record["predicted_pattern"] == "Near-full"
    assert record["classification_confidence"] == 0.84
    assert record["native_failure_pattern"] == "Near-full"
    assert record["descriptor_stats"]["defect_density"] == 8 / 9
    assert record["annotation_type"] == "native_ground_truth"
    assert Path(str(record["saliency_path"])).exists()
    assert record["classifier"]["backend"] == "fake"
    assert record["classifier"]["model_source"] == "radai-agent/radai-wm811k-defect-detection"
    assert record["classifier"]["model_file"] == "best_radai_resnet.pt"
    assert record["classifier"]["task"] == "defect_pattern_classification"
    assert record["classifier"]["produces_root_cause"] is False
    assert record["classifier"]["classes"] == ["Center", "Near-full"]
    assert _forbidden_keys(record) == []

    evidence = evidence_from_records(records, dataset="wafer")
    assert evidence[0].dataset == "wafer"
    assert evidence[0].adapter is not None
    assert evidence[0].adapter.name == "wm811k"
    assert evidence[0].anomaly_type == "nearfull"
    assert evidence[0].kg_analysis.top_k_paths == []


def test_tep_raw_producer_emits_adapter_compatible_rbc_records(tmp_path: Path) -> None:
    """TEP producer should turn raw CSV windows into adapter-ready variable evidence."""
    raw_dir = _write_tiny_tep_csvs(tmp_path / "tep")

    records = build_tep_records(
        raw_dir,
        row_stride=1,
        window_size=4,
        faults=(1,),
        max_runs_per_fault=1,
        max_cases=1,
        top_variables=2,
        n_components=1,
    )

    assert len(records) == 1
    record = records[0]
    assert record["dataset"] == "tep"
    assert record["source"] == "tep_csv_rbc"
    assert record["fault_number"] == 1
    assert record["simulation_run"] == 1
    assert record["variables"][0] == "XMEAS_2"
    assert record["variable_contributions"]["XMEAS_2"] > 0.5
    assert record["detector"]["backend"] == TEP_RBC_BACKEND
    assert record["detector"]["produces_root_cause"] is False
    assert _forbidden_keys(record) == []

    evidence = evidence_from_records(records, dataset="tep")[0]
    selector = tep_scenario_selector(evidence)
    assert evidence.adapter is not None
    assert evidence.adapter.name == "tep"
    assert selector.fault_numbers == (1,)
    assert selector.simulation_runs == (1,)


def test_dataset_record_workflow_supports_tep_raw_producer(tmp_path: Path) -> None:
    """Unified dataset-record workflow should include the native TEP producer branch."""
    raw_dir = _write_tiny_tep_csvs(tmp_path / "tep")
    output_jsonl = tmp_path / "records" / "tep.jsonl"

    result = dataset_record_workflow.build_dataset_records(
        dataset_record_workflow.DatasetRecordBuildConfig(
            dataset="tep",
            input_root=raw_dir,
            output_jsonl=output_jsonl,
            model_backend=TEP_RBC_BACKEND,
            max_cases=1,
            overwrite=True,
            tep_faults=(1,),
            tep_window_size=4,
            tep_row_stride=1,
            tep_max_runs_per_fault=1,
            tep_top_variables=2,
            tep_n_components=1,
        )
    )

    assert result.output_path == output_jsonl
    assert result.summary["dataset"] == "tep"
    assert result.summary["record_count"] == 1
    assert result.summary["labels"] == {"1": 1}
    assert (tmp_path / "records" / "tep" / "tep_fault_free_profile.json").exists()
    assert load_records(output_jsonl)[0]["fault_number"] == 1


def test_sklearn_backend_loads_trusted_joblib_checkpoint(tmp_path: Path) -> None:
    """Sklearn WM811K backend should load a tiny local joblib model and use predict_proba."""
    checkpoint = tmp_path / "wm811k_model.joblib"
    joblib.dump(TinySklearnWaferModel(), checkpoint)
    backend = SklearnWM811KBackend(checkpoint=checkpoint)

    prediction = backend.predict([[2, 2, 2], [0, 0, 0]])

    assert prediction["pattern"] == "Near-full"
    assert prediction["confidence"] == pytest.approx(0.92)
    assert prediction["metadata"]["source_backend"] == SKLEARN_BACKEND
    assert prediction["metadata"]["classes"] == ["Random", "Near-full"]


def test_sklearn_backend_preserves_zero_probability_confidence(tmp_path: Path) -> None:
    """A valid zero predicted-class probability should not be treated as missing."""
    checkpoint = tmp_path / "wm811k_zero_model.joblib"
    joblib.dump(ZeroProbabilitySklearnWaferModel(), checkpoint)
    backend = SklearnWM811KBackend(checkpoint=checkpoint)

    prediction = backend.predict([[2, 2], [2, 2]])

    assert prediction["pattern"] == "Near-full"
    assert prediction["confidence"] == 0.0


def test_sklearn_checkpoint_load_error_names_trusted_local_boundary(tmp_path: Path) -> None:
    """Invalid checkpoint errors should explain the trusted-local file boundary."""
    checkpoint = tmp_path / "not_a_model.joblib"
    checkpoint.write_text("not a joblib or pickle model", encoding="utf-8")

    with pytest.raises(ValueError, match="trusted local sklearn checkpoint"):
        load_trusted_sklearn_model(checkpoint)


def test_cli_backend_selection_supports_real_backend_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI helper selection should map backend names without requiring real checkpoints in tests."""

    class SentinelAnomalibBackend:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def predict(self, image_path: Path) -> MVTecPrediction:
            return {"score": 0.1}

    class SentinelAmazonPatchCoreBackend:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def predict(self, image_path: Path) -> MVTecPrediction:
            return {"score": 0.2}

    class SentinelAmazonPatchCoreObjectRouter:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def predict(self, image_path: Path) -> MVTecPrediction:
            return {"score": 0.3}

    monkeypatch.setattr(
        dataset_record_workflow,
        "AnomalibMVTecBackend",
        SentinelAnomalibBackend,
    )
    monkeypatch.setattr(
        dataset_record_workflow,
        "AmazonPatchCoreBackend",
        SentinelAmazonPatchCoreBackend,
    )
    monkeypatch.setattr(
        dataset_record_workflow,
        "AmazonPatchCoreObjectRouter",
        SentinelAmazonPatchCoreObjectRouter,
    )
    mvtec_predictor = dataset_record_workflow.build_mvtec_predictor(
        model_backend=ANOMALIB_OPENVINO_BACKEND,
        checkpoint=tmp_path / "model.xml",
        device="cpu",
    )
    assert isinstance(mvtec_predictor, SentinelAnomalibBackend)
    assert mvtec_predictor.kwargs["backend"] == ANOMALIB_OPENVINO_BACKEND
    assert mvtec_predictor.kwargs["device"] == "cpu"

    amazon_predictor = dataset_record_workflow.build_mvtec_predictor(
        model_backend=AMAZON_PATCHCORE_BACKEND,
        checkpoint=tmp_path / "amazon_patchcore" / "mvtec_bottle",
        device="cpu",
    )
    assert isinstance(amazon_predictor, SentinelAmazonPatchCoreBackend)
    assert amazon_predictor.kwargs["checkpoint"] == tmp_path / "amazon_patchcore" / "mvtec_bottle"
    assert amazon_predictor.kwargs["device"] == "cpu"

    amazon_router = dataset_record_workflow.build_mvtec_predictor(
        model_backend=AMAZON_PATCHCORE_BACKEND,
        object_checkpoint_root=tmp_path / "amazon_patchcore",
        device="cpu",
    )
    assert isinstance(amazon_router, SentinelAmazonPatchCoreObjectRouter)
    assert amazon_router.kwargs["checkpoint_root"] == tmp_path / "amazon_patchcore"
    assert amazon_router.kwargs["device"] == "cpu"

    with pytest.raises(ValueError, match="cannot both be set"):
        build_script.build_mvtec_predictor(
            model_backend=AMAZON_PATCHCORE_BACKEND,
            checkpoint=tmp_path / "amazon_patchcore" / "mvtec_bottle",
            object_checkpoint_root=tmp_path / "amazon_patchcore",
        )

    with pytest.raises(ValueError, match="only supported"):
        build_script.build_mvtec_predictor(
            model_backend=ANOMALIB_OPENVINO_BACKEND,
            object_checkpoint_root=tmp_path / "amazon_patchcore",
        )

    with pytest.raises(ValueError, match="unsupported MVTec"):
        build_script.build_mvtec_predictor(model_backend="fake")

    checkpoint = tmp_path / "wm811k_model.joblib"
    joblib.dump(TinySklearnWaferModel(), checkpoint)
    wm811k_classifier = build_script.build_wm811k_classifier(
        model_backend=SKLEARN_BACKEND,
        checkpoint=checkpoint,
    )
    assert isinstance(wm811k_classifier, SklearnWM811KBackend)

    with pytest.raises(ValueError, match="unsupported WM811K"):
        build_script.build_wm811k_classifier(model_backend="fake")

    torch = pytest.importorskip("torch")
    torchvision = pytest.importorskip("torchvision")
    model = _build_torch_wm811k_model(torch, torchvision)
    torch_checkpoint = tmp_path / "wm811k_model.pt"
    torch.save({"model_state_dict": model.state_dict()}, torch_checkpoint)
    loaded_model = load_trusted_torch_model(torch_checkpoint)
    assert loaded_model is not None
    torch_classifier = build_script.build_wm811k_classifier(
        model_backend=TORCH_RESNET_BACKEND,
        checkpoint=torch_checkpoint,
        device="cpu",
        model_source_repo="radai-agent/radai-wm811k-defect-detection",
        model_source_file="best_radai_resnet.pt",
    )
    assert isinstance(torch_classifier, TorchWM811KBackend)
    assert torch_classifier.model_source == "radai-agent/radai-wm811k-defect-detection"
    assert torch_classifier.model_file == "best_radai_resnet.pt"

    with pytest.raises(ValueError, match="unsupported WM811K"):
        build_script.build_wm811k_classifier(model_backend=ANOMALIB_TORCH_BACKEND)


def test_torch_wm811k_backend_loads_trusted_checkpoint(tmp_path: Path) -> None:
    """Torch WM811K backend should load a trusted ResNet checkpoint and predict."""
    torch = pytest.importorskip("torch")
    torchvision = pytest.importorskip("torchvision")
    model = _build_torch_wm811k_model(torch, torchvision)
    checkpoint = tmp_path / "wm811k_torch.pt"
    torch.save({"model_state_dict": model.state_dict()}, checkpoint)

    backend = TorchWM811KBackend(
        checkpoint=checkpoint,
        device="cpu",
        model_source="radai-agent/radai-wm811k-defect-detection",
        model_file="best_radai_resnet.pt",
    )
    prediction = backend.predict([[2, 2, 2], [2, 0, 2], [2, 2, 2]])

    assert prediction["pattern"] == "Near-full"
    assert prediction["confidence"] > 0.99
    assert prediction["metadata"]["source_backend"] == TORCH_RESNET_BACKEND
    assert prediction["metadata"]["device"] == "cpu"
    assert prediction["metadata"]["model_source"] == "radai-agent/radai-wm811k-defect-detection"
    assert prediction["metadata"]["model_file"] == "best_radai_resnet.pt"
    assert prediction["metadata"]["task"] == "defect_pattern_classification"
    assert prediction["metadata"]["produces_root_cause"] is False


def test_producers_preserve_zero_numeric_model_outputs(tmp_path: Path) -> None:
    """A valid 0.0 score/confidence should not be treated as missing."""

    class ZeroMVTecPredictor:
        def predict(self, image_path: Path) -> MVTecPrediction:
            return {"score": 0.0, "mask": [[0, 0], [0, 0]]}

    mvtec_root = tmp_path / "mvtec"
    _touch(mvtec_root / "bottle" / "test" / "scratch" / "000.png")
    mvtec_records = build_mvtec_records(mvtec_root, ZeroMVTecPredictor())
    assert mvtec_records[0]["score"] == 0.0
    assert mvtec_records[0]["confidence"] == 0.0
    assert mvtec_records[0]["detector"]["pred_score"] == 0.0

    class ZeroWM811KClassifier:
        def predict(
            self,
            wafer_map: Sequence[Sequence[Any]],
            *,
            metadata: Mapping[str, Any] | None = None,
        ) -> WM811KPrediction:
            return {"pattern": "Random", "confidence": 0.0, "score": 0.72}

    table_path = tmp_path / "wm811k.pkl"
    pd.DataFrame(
        [
            {
                "waferMap": [[2, 0], [0, 0]],
                "failureType": [["Random"]],
                "lotName": "LotA",
                "waferIndex": 1,
            }
        ]
    ).to_pickle(table_path)
    wm811k_records = build_wm811k_records(table_path, ZeroWM811KClassifier())
    assert wm811k_records[0]["classification_confidence"] == 0.0
    assert wm811k_records[0]["classifier"]["confidence"] == 0.0


def test_mvtec_producer_clamps_unbounded_score_fallback_confidence(tmp_path: Path) -> None:
    """Unbounded anomaly scores should remain raw scores while confidence stays unit-scale."""

    class UnboundedScoreMVTecPredictor:
        def predict(self, image_path: Path) -> MVTecPrediction:
            return {"score": 12.5, "mask": [[1, 1], [0, 0]]}

    mvtec_root = tmp_path / "mvtec"
    _touch(mvtec_root / "bottle" / "test" / "crack" / "000.png")

    records = build_mvtec_records(mvtec_root, UnboundedScoreMVTecPredictor())

    assert records[0]["score"] == 12.5
    assert records[0]["confidence"] == 1.0
    assert records[0]["detector"]["pred_score"] == 12.5
    assert records[0]["detector"]["confidence"] == 1.0


def test_mvtec_producer_clamps_explicit_confidence_to_unit_scale(tmp_path: Path) -> None:
    """Producer records should not pass invalid confidence values to Evidence adapters."""

    class UnboundedConfidenceMVTecPredictor:
        def predict(self, image_path: Path) -> MVTecPrediction:
            return {"score": 12.5, "confidence": 5.0, "mask": [[1, 1], [0, 0]]}

    mvtec_root = tmp_path / "mvtec"
    _touch(mvtec_root / "bottle" / "test" / "crack" / "000.png")

    records = build_mvtec_records(mvtec_root, UnboundedConfidenceMVTecPredictor())

    assert records[0]["score"] == 12.5
    assert records[0]["confidence"] == 1.0
    assert records[0]["detector"]["confidence"] == 1.0
    assert evidence_from_records(records, dataset="mvtec")[0].confidence == 1.0


def test_wm811k_rejects_one_dimensional_wafer_maps(tmp_path: Path) -> None:
    """Malformed wafer maps should fail explicitly instead of becoming empty maps."""
    table_path = tmp_path / "wm811k.pkl"
    pd.DataFrame(
        [
            {
                "waferMap": [1, 2, 3],
                "failureType": [["Random"]],
                "lotName": "LotA",
                "waferIndex": 1,
            }
        ]
    ).to_pickle(table_path)

    with pytest.raises(ValueError, match="2-dimensional"):
        build_wm811k_records(table_path, FakeWM811KClassifier())


def test_producer_jsonl_writer_and_forbidden_filter_round_trip(tmp_path: Path) -> None:
    """Producer JSONL output should be clean and loadable by existing batch utilities."""
    dirty_record = {
        "dataset": "mvtec",
        "case_id": "dirty",
        "object": "bottle",
        "defect_type": "scratch",
        "root_cause": "not_allowed",
        "extra": {"top_k_paths": [{"path_id": "not_allowed"}], "kept": True},
    }
    output_path = write_jsonl_records([dirty_record], tmp_path / "records.jsonl")

    loaded = load_records(output_path)
    assert loaded == [
        {
            "dataset": "mvtec",
            "case_id": "dirty",
            "object": "bottle",
            "defect_type": "scratch",
            "extra": {"kept": True},
        }
    ]
    assert evidence_from_records(loaded)[0].case_id == "dirty"


def test_deterministic_subset_supports_seed_and_per_label_limits() -> None:
    """Subset selection should be reproducible and class-balanced when requested."""
    items = [
        {"id": "b2", "label": "b"},
        {"id": "a2", "label": "a"},
        {"id": "b1", "label": "b"},
        {"id": "a1", "label": "a"},
    ]

    selected = deterministic_subset(
        items,
        label=lambda item: item["label"],
        sort_key=lambda item: item["id"],
        max_per_label=1,
        seed=3,
    )

    assert [item["label"] for item in selected] == ["a", "b"]
    assert deterministic_subset(
        items,
        label=lambda item: item["label"],
        sort_key=lambda item: item["id"],
        max_per_label=1,
        seed=3,
    ) == selected


def test_mask_stats_from_array_handles_component_geometry() -> None:
    """Generated MVTec masks should provide deterministic fallback geometry."""
    stats = mask_stats_from_array([[0, 1, 1], [0, 0, 0], [1, 0, 0]])

    assert stats["area"] == 3
    assert stats["component_count"] == 2
    assert stats["image_shape"] == [3, 3]
    assert stats["bbox"] == [0, 0, 3, 3]


def test_zero_area_mask_does_not_derive_spot_morphology() -> None:
    """An empty mask should not be rewritten as a spot-like defect."""
    stats = mask_stats_from_array([[0, 0], [0, 0]])

    summary = summarize_mask_features(stats)

    assert summary["mask_stats"]["area_ratio"] == 0.0
    assert "morphology" not in summary


def test_filter_forbidden_outputs_recurses_through_records() -> None:
    """Producer boundary filtering should remove forbidden reasoning outputs."""
    filtered = filter_forbidden_outputs(
        {
            "case_id": "x",
            "kg_analysis": {"top_k_paths": []},
            "records": [{"root_cause": "bad", "safe": "ok"}],
            "array": np.asarray([{"candidate_root_cause": "bad", "safe": "array"}], dtype=object),
        }
    )

    assert filtered == {
        "case_id": "x",
        "records": [{"safe": "ok"}],
        "array": [{"safe": "array"}],
    }


def _write_tiny_tep_csvs(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    header = ["faultNumber", "simulationRun", "sample", "xmeas_1", "xmeas_2", "xmv_1"]
    fault_free_rows = [
        [0, 1, sample, sample, sample * 0.1, sample * 2.0]
        for sample in range(1, 21)
    ]
    faulty_rows = [
        [1, 1, sample, sample, sample * 0.1 + 20.0, sample * 2.0]
        for sample in range(1, 7)
    ]
    _write_csv(root / "TEP_FaultFree_Training.csv", header, fault_free_rows)
    _write_csv(root / "TEP_Faulty_Training.csv", header, faulty_rows)
    return root


def _write_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture", encoding="utf-8")


def _write_mask(path: Path, values: Sequence[Sequence[int]]) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(values, dtype=np.uint8)).save(path)


def _amazon_patchcore_artifact_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "patchcore_params.pkl").write_bytes(b"params")
    (path / "nnscorer_search_index.faiss").write_bytes(b"faiss")
    return path


def _amazon_patchcore_pointer_artifact_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    pointer = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:0123456789abcdef\n"
        b"size 123456\n"
    )
    (path / "patchcore_params.pkl").write_bytes(pointer)
    (path / "nnscorer_search_index.faiss").write_bytes(pointer)
    return path


def _build_torch_wm811k_model(torch: Any, torchvision: Any) -> Any:
    """Build a checkpoint-compatible WM811K ResNet with deterministic logits."""
    nn = torch.nn

    base = torchvision.models.resnet34(weights=None)
    base.conv1 = nn.Conv2d(1, 64, kernel_size=7, stride=2, padding=3, bias=False)
    base.fc = nn.Sequential(
        nn.Dropout(0.5),
        nn.Linear(base.fc.in_features, 8),
    )
    for parameter in base.parameters():
        parameter.data.zero_()
    base.fc[1].bias.data[7] = 10.0
    return base


def _forbidden_keys(value: object) -> list[str]:
    forbidden = {
        "root_cause",
        "root_causes",
        "candidate_root_cause",
        "candidate_root_causes",
        "ranked_causes",
        "top_k_paths",
        "kg_analysis",
    }
    found: list[str] = []

    def collect(nested: object) -> None:
        if isinstance(nested, dict):
            for key, child in nested.items():
                if key in forbidden:
                    found.append(key)
                collect(child)
        elif isinstance(nested, list):
            for child in nested:
                collect(child)

    collect(json.loads(json.dumps(value)))
    return found
