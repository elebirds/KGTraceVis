"""Local model backend wrappers for producer-output inference."""

from __future__ import annotations

import pickle
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from kgtracevis.producers.common import MVTecPrediction, WM811KPrediction

ANOMALIB_TORCH_BACKEND = "anomalib-torch"
ANOMALIB_OPENVINO_BACKEND = "anomalib-openvino"
SKLEARN_BACKEND = "sklearn"


class AnomalibMVTecBackend:
    """Wrap an Anomalib exported inferencer as an MVTec producer predictor."""

    def __init__(
        self,
        *,
        backend: str,
        checkpoint: str | Path | None = None,
        device: str | None = None,
        inferencer: Any | None = None,
    ) -> None:
        """Create a backend, optionally with an injected inferencer for tests."""
        if backend not in {ANOMALIB_TORCH_BACKEND, ANOMALIB_OPENVINO_BACKEND}:
            raise ValueError(f"unsupported Anomalib backend: {backend}")
        self.backend = backend
        self.checkpoint = Path(checkpoint) if checkpoint is not None else None
        self.device = device
        self.inferencer = inferencer if inferencer is not None else self._load_inferencer()

    def predict(self, image_path: Path) -> MVTecPrediction:
        """Run Anomalib inference for one image and normalize the prediction shape."""
        raw_prediction = self.inferencer.predict(image_path)
        return anomalib_prediction_to_mvtec_prediction(
            raw_prediction,
            backend=self.backend,
            checkpoint=self.checkpoint,
            device=self.device,
        )

    def _load_inferencer(self) -> Any:
        if self.checkpoint is None:
            raise ValueError(f"--checkpoint is required for --model-backend {self.backend}")
        try:
            from anomalib.deploy import OpenVINOInferencer, TorchInferencer
        except ImportError as exc:
            raise ImportError(
                "Anomalib is required for --model-backend "
                f"{self.backend}; install it in the local runtime or use --model-backend fake"
            ) from exc

        inferencer_cls = (
            TorchInferencer if self.backend == ANOMALIB_TORCH_BACKEND else OpenVINOInferencer
        )
        return _instantiate_anomalib_inferencer(
            inferencer_cls,
            checkpoint=self.checkpoint,
            device=self.device,
        )


def anomalib_prediction_to_mvtec_prediction(
    prediction: Any,
    *,
    backend: str,
    checkpoint: str | Path | None = None,
    device: str | None = None,
) -> MVTecPrediction:
    """Convert an Anomalib prediction object or mapping into `MVTecPrediction`."""
    score = _float_or_none(_first_prediction_value(prediction, ("pred_score", "score")))
    confidence = _float_or_none(_first_prediction_value(prediction, ("confidence",)))
    if confidence is None:
        confidence = score
    label = _text_or_none(_first_prediction_value(prediction, ("pred_label", "label")))
    anomaly_map = _first_prediction_value(prediction, ("anomaly_map",))
    mask = _first_prediction_value(prediction, ("pred_mask", "mask"))

    normalized: MVTecPrediction = {
        "metadata": {
            "source_backend": backend,
            "checkpoint": str(checkpoint) if checkpoint is not None else None,
            "device": device,
            "raw_pred_label": label,
        }
    }
    if score is not None:
        normalized["score"] = score
    if confidence is not None:
        normalized["confidence"] = confidence
    if label is not None:
        normalized["label"] = label
    if anomaly_map is not None:
        normalized["anomaly_map"] = _array_like_to_jsonable(anomaly_map)
    if mask is not None:
        normalized["mask"] = _array_like_to_jsonable(mask)
    return normalized


class SklearnWM811KBackend:
    """Wrap a trusted local sklearn/joblib classifier as a WM811K predictor."""

    def __init__(self, *, checkpoint: str | Path | None = None, model: Any | None = None) -> None:
        """Create a classifier backend from an injected model or trusted checkpoint."""
        if model is None and checkpoint is None:
            raise ValueError("--checkpoint is required for --model-backend sklearn")
        self.checkpoint = Path(checkpoint) if checkpoint is not None else None
        self.model = model if model is not None else load_trusted_sklearn_model(self.checkpoint)

    def predict(
        self,
        wafer_map: Sequence[Sequence[Any]],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> WM811KPrediction:
        """Flatten one wafer map, call sklearn predict/proba, and normalize output."""
        del metadata
        features = flatten_wafer_map_features(wafer_map)
        predicted = self.model.predict(features)
        label = _first_sequence_value(predicted)
        label_text = _text_or_none(label) or "unknown"
        confidence = _sklearn_prediction_confidence(self.model, features, label_text)
        classes = _classes_as_text(getattr(self.model, "classes_", None))
        prediction: WM811KPrediction = {
            "pattern": label_text,
            "metadata": {
                "source_backend": SKLEARN_BACKEND,
                "checkpoint": str(self.checkpoint) if self.checkpoint is not None else None,
                "classes": classes,
            },
        }
        if confidence is not None:
            prediction["confidence"] = confidence
        return prediction


def load_trusted_sklearn_model(checkpoint: str | Path | None) -> Any:
    """Load a trusted local sklearn-compatible model from joblib or pickle."""
    if checkpoint is None:
        raise ValueError("checkpoint path is required")
    path = Path(checkpoint)
    if not path.is_file():
        raise FileNotFoundError(f"sklearn checkpoint does not exist: {path}")
    errors: list[str] = []
    try:
        import joblib

        return joblib.load(path)
    except ImportError as exc:
        errors.append(f"joblib unavailable: {exc}")
    except Exception as exc:
        errors.append(f"joblib load failed: {exc}")
    try:
        with path.open("rb") as handle:
            return pickle.load(handle)
    except Exception as exc:
        details = "; ".join(errors + [f"pickle load failed: {exc}"])
        raise ValueError(
            "failed to load trusted local sklearn checkpoint "
            f"{path}; only load joblib/pickle model files from trusted local paths. {details}"
        ) from exc


def flatten_wafer_map_features(wafer_map: Sequence[Sequence[Any]]) -> np.ndarray:
    """Flatten a 2D wafer map into one sklearn feature row."""
    array = np.asarray(wafer_map, dtype=float)
    if array.ndim != 2:
        raise ValueError("wafer map must be 2-dimensional for sklearn inference")
    return array.reshape(1, -1)


def _instantiate_anomalib_inferencer(
    inferencer_cls: Any,
    *,
    checkpoint: Path,
    device: str | None,
) -> Any:
    kwargs: dict[str, Any] = {"path": checkpoint}
    if device is not None:
        kwargs["device"] = device
    try:
        return inferencer_cls(**kwargs)
    except TypeError:
        if device is not None:
            try:
                return inferencer_cls(checkpoint, device=device)
            except TypeError:
                pass
        return inferencer_cls(checkpoint)


def _sklearn_prediction_confidence(model: Any, features: np.ndarray, label: str) -> float | None:
    if not hasattr(model, "predict_proba"):
        return None
    probabilities = np.asarray(model.predict_proba(features), dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[0] == 0 or probabilities.shape[1] == 0:
        return None
    classes = _classes_as_text(getattr(model, "classes_", None))
    if classes and label in classes:
        label_index = classes.index(label)
        if label_index < probabilities.shape[1]:
            return float(probabilities[0, label_index])
    return float(np.max(probabilities[0]))


def _first_prediction_value(prediction: Any, keys: Sequence[str]) -> Any:
    if isinstance(prediction, Mapping):
        for key in keys:
            if key in prediction and prediction[key] is not None:
                return prediction[key]
        return None
    for key in keys:
        value = getattr(prediction, key, None)
        if value is not None:
            return value
    return None


def _array_like_to_jsonable(value: Any) -> Any:
    if hasattr(value, "tolist") and callable(value.tolist):
        return value.tolist()
    return value


def _first_sequence_value(value: Any) -> Any:
    if hasattr(value, "tolist") and callable(value.tolist):
        value = value.tolist()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value[0] if value else None
    return value


def _classes_as_text(classes: Any) -> list[str]:
    if classes is None:
        return []
    if hasattr(classes, "tolist") and callable(classes.tolist):
        classes = classes.tolist()
    if isinstance(classes, Sequence) and not isinstance(classes, (str, bytes, bytearray)):
        return [str(item) for item in classes]
    return [str(classes)]


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip() == "":
            return None
        return float(value)
    if hasattr(value, "item") and callable(value.item):
        try:
            return float(value.item())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "tolist") and callable(value.tolist):
        value = value.tolist()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) == 0:
            return None
        if len(value) == 1:
            return _float_or_none(value[0])
        raise ValueError("numeric prediction value must be scalar")
    return float(value)


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
