"""Tests for model-aware producer-output record builders."""

from __future__ import annotations

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

from kgtracevis.adapters.batch import evidence_from_records, load_records
from kgtracevis.producers.backends import (
    ANOMALIB_OPENVINO_BACKEND,
    ANOMALIB_TORCH_BACKEND,
    SKLEARN_BACKEND,
    TORCH_RESNET_BACKEND,
    AnomalibMVTecBackend,
    SklearnWM811KBackend,
    TorchWM811KBackend,
    anomalib_prediction_to_mvtec_prediction,
    load_trusted_sklearn_model,
    load_trusted_torch_model,
)
from kgtracevis.producers.common import (
    MVTecPrediction,
    WM811KPrediction,
    deterministic_subset,
    filter_forbidden_outputs,
    write_jsonl_records,
)
from kgtracevis.producers.mvtec_records import build_mvtec_records, mask_stats_from_array
from kgtracevis.producers.wm811k_records import build_wm811k_records

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
            "metadata": {"fixture": "wm811k"},
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
    assert _forbidden_keys(record) == []

    evidence = evidence_from_records(records, dataset="wafer")
    assert evidence[0].dataset == "wafer"
    assert evidence[0].adapter is not None
    assert evidence[0].adapter.name == "wm811k"
    assert evidence[0].anomaly_type == "nearfull"
    assert evidence[0].kg_analysis.top_k_paths == []


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

    monkeypatch.setattr(build_script, "AnomalibMVTecBackend", SentinelAnomalibBackend)
    mvtec_predictor = build_script.build_mvtec_predictor(
        model_backend=ANOMALIB_OPENVINO_BACKEND,
        checkpoint=tmp_path / "model.xml",
        device="cpu",
    )
    assert isinstance(mvtec_predictor, SentinelAnomalibBackend)
    assert mvtec_predictor.kwargs["backend"] == ANOMALIB_OPENVINO_BACKEND
    assert mvtec_predictor.kwargs["device"] == "cpu"

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
    )
    assert isinstance(torch_classifier, TorchWM811KBackend)

    with pytest.raises(ValueError, match="unsupported WM811K"):
        build_script.build_wm811k_classifier(model_backend=ANOMALIB_TORCH_BACKEND)


def test_torch_wm811k_backend_loads_trusted_checkpoint(tmp_path: Path) -> None:
    """Torch WM811K backend should load a trusted ResNet checkpoint and predict."""
    torch = pytest.importorskip("torch")
    torchvision = pytest.importorskip("torchvision")
    model = _build_torch_wm811k_model(torch, torchvision)
    checkpoint = tmp_path / "wm811k_torch.pt"
    torch.save({"model_state_dict": model.state_dict()}, checkpoint)

    backend = TorchWM811KBackend(checkpoint=checkpoint, device="cpu")
    prediction = backend.predict([[2, 2, 2], [2, 0, 2], [2, 2, 2]])

    assert prediction["pattern"] == "Near-full"
    assert prediction["confidence"] > 0.99
    assert prediction["metadata"]["source_backend"] == TORCH_RESNET_BACKEND
    assert prediction["metadata"]["device"] == "cpu"


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


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture", encoding="utf-8")


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
