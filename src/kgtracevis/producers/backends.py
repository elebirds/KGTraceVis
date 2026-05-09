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
TORCH_RESNET_BACKEND = "torch-resnet34"
WM811K_CLASSES = [
    "Center",
    "Donut",
    "Edge-Loc",
    "Edge-Ring",
    "Loc",
    "Random",
    "Scratch",
    "Near-full",
]


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
        try:
            raw_prediction = self.inferencer.predict(image_path)
        except TypeError as exc:
            if self.backend != ANOMALIB_OPENVINO_BACKEND:
                raise
            raw_prediction = self._predict_openvino_compat(image_path, exc)
        except RuntimeError as exc:
            if self.backend != ANOMALIB_OPENVINO_BACKEND:
                raise
            try:
                raw_prediction = self._predict_openvino_compat(image_path, exc)
            except Exception as fallback_exc:
                raise ValueError(
                    "OpenVINO MVTec inference failed. The uploaded image may be "
                    "incompatible with the exported model input shape."
                ) from fallback_exc
        return anomalib_prediction_to_mvtec_prediction(
            raw_prediction,
            backend=self.backend,
            checkpoint=self.checkpoint,
            device=self.device,
        )

    def _predict_openvino_compat(
        self,
        image_path: Path,
        original_error: Exception,
    ) -> MVTecPrediction:
        """Run OpenVINO inference while tolerating older Anomalib output schemas."""
        del original_error
        if not all(
            hasattr(self.inferencer, attribute)
            for attribute in ("pre_process", "post_process", "model", "input_blob")
        ):
            raise TypeError("OpenVINO inferencer does not expose the required compatibility hooks")
        image = _read_rgb_image(image_path)
        image = _resize_to_openvino_input(image, self.inferencer.input_blob)
        image = self.inferencer.pre_process(image)
        predictions = self.inferencer.model({self.inferencer.input_blob.any_name: image})
        pred_dict = dict(self.inferencer.post_process(predictions))
        if "output" in pred_dict and "anomaly_map" not in pred_dict:
            output = np.squeeze(np.asarray(pred_dict.pop("output")))
            pred_dict["anomaly_map"] = output
            if output.size:
                score = float(np.max(output))
                pred_dict.setdefault("score", score)
                pred_dict.setdefault("confidence", score)
        pred_dict.setdefault(
            "metadata",
            {
                "source_backend": self.backend,
                "checkpoint": str(self.checkpoint) if self.checkpoint is not None else None,
                "device": self.device,
                "fallback": "openvino_compat",
            },
        )
        return pred_dict

    def _load_inferencer(self) -> Any:
        if self.checkpoint is None:
            raise ValueError(f"--checkpoint is required for --model-backend {self.backend}")
        try:
            from anomalib.deploy import OpenVINOInferencer, TorchInferencer
        except ImportError as exc:
            raise ImportError(
                "Anomalib is required for --model-backend "
                f"{self.backend}; install it in the local runtime"
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


class TorchWM811KBackend:
    """Wrap a trusted local PyTorch classifier checkpoint as a WM811K predictor."""

    def __init__(
        self,
        *,
        checkpoint: str | Path | None = None,
        model: Any | None = None,
        device: str | None = None,
    ) -> None:
        """Create a classifier backend from an injected model or trusted checkpoint."""
        if model is None and checkpoint is None:
            raise ValueError("--checkpoint is required for --model-backend torch-resnet34")
        self.checkpoint = Path(checkpoint) if checkpoint is not None else None
        self.device = _resolve_torch_device(device)
        self.model = model if model is not None else load_trusted_torch_model(self.checkpoint)
        self.model.to(self.device)
        self.model.eval()

    def predict(
        self,
        wafer_map: Sequence[Sequence[Any]],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> WM811KPrediction:
        """Resize one wafer map, call torch predict, and normalize output."""
        del metadata
        features = _wafer_map_tensor(wafer_map, device=self.device)
        import torch

        with torch.inference_mode():
            logits = self.model(features)
            if logits.ndim != 2 or logits.shape[0] == 0 or logits.shape[1] == 0:
                raise ValueError("WM811K torch classifier must return a [batch, classes] tensor")
            probabilities = torch.softmax(logits, dim=1)
            pred_idx = int(torch.argmax(logits, dim=1).item())
            confidence = float(probabilities[0, pred_idx].item())

        label = WM811K_CLASSES[pred_idx] if pred_idx < len(WM811K_CLASSES) else "unknown"
        return {
            "pattern": label,
            "score": confidence,
            "confidence": confidence,
            "metadata": {
                "source_backend": TORCH_RESNET_BACKEND,
                "checkpoint": str(self.checkpoint) if self.checkpoint is not None else None,
                "device": str(self.device),
                "classes": WM811K_CLASSES,
            },
        }


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


def load_trusted_torch_model(checkpoint: str | Path | None) -> Any:
    """Load a trusted local PyTorch classifier checkpoint."""
    if checkpoint is None:
        raise ValueError("checkpoint path is required")
    path = Path(checkpoint)
    if not path.is_file():
        raise FileNotFoundError(f"torch checkpoint does not exist: {path}")
    try:
        import torch
        import torch.nn as nn
        from torchvision import models
    except ImportError as exc:  # pragma: no cover - depends on optional extra.
        raise ImportError(
            "PyTorch and torchvision are required for --model-backend torch-resnet34"
        ) from exc

    checkpoint_obj = torch.load(path, map_location="cpu")
    state_dict = _extract_state_dict(checkpoint_obj)
    model = _build_radai_resnet(models, nn)
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    if missing or unexpected:
        raise ValueError(
            "failed to load trusted local torch checkpoint "
            f"{path}; missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    return model


def flatten_wafer_map_features(wafer_map: Sequence[Sequence[Any]]) -> np.ndarray:
    """Flatten a 2D wafer map into one sklearn feature row."""
    array = np.asarray(wafer_map, dtype=float)
    if array.ndim != 2:
        raise ValueError("wafer map must be 2-dimensional for sklearn inference")
    return array.reshape(1, -1)


def _build_radai_resnet(models: Any, nn: Any) -> Any:
    """Return the WM811K classifier architecture used by the public checkpoint."""
    base = models.resnet34(weights=None)
    base.conv1 = nn.Conv2d(1, 64, kernel_size=7, stride=2, padding=3, bias=False)
    base.fc = nn.Sequential(
        nn.Dropout(0.5),
        nn.Linear(base.fc.in_features, len(WM811K_CLASSES)),
    )
    return _RadaiResNet(base)


class _RadaiResNet:
    """Lightweight wrapper around the checkpoint-compatible ResNet34 body."""

    def __init__(self, base: Any) -> None:
        self.base = base

    def to(self, device: Any) -> _RadaiResNet:
        self.base.to(device)
        return self

    def eval(self) -> _RadaiResNet:
        self.base.eval()
        return self

    def load_state_dict(
        self,
        state_dict: Mapping[str, Any],
        strict: bool = True,
    ) -> tuple[list[str], list[str]]:
        cleaned = _clean_state_dict(state_dict)
        result = self.base.load_state_dict(cleaned, strict=strict)
        return list(result.missing_keys), list(result.unexpected_keys)

    def __call__(self, features: Any) -> Any:
        return self.base(features)


def _clean_state_dict(state_dict: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = dict(state_dict)
    for prefix in ("module.", "model.", "base."):
        if cleaned and all(isinstance(key, str) and key.startswith(prefix) for key in cleaned):
            cleaned = {key[len(prefix) :]: value for key, value in cleaned.items()}
    return cleaned


def _extract_state_dict(checkpoint_obj: Any) -> Mapping[str, Any]:
    if isinstance(checkpoint_obj, Mapping):
        for key in ("model_state_dict", "state_dict", "model", "net"):
            nested = checkpoint_obj.get(key)
            if isinstance(nested, Mapping):
                return nested
        if all(isinstance(key, str) for key in checkpoint_obj):
            return checkpoint_obj
    raise ValueError("torch checkpoint must contain a state_dict or model_state_dict mapping")


def _wafer_map_tensor(wafer_map: Sequence[Sequence[Any]], *, device: Any) -> Any:
    import torch
    import torch.nn.functional as F

    array = np.asarray(wafer_map, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError("wafer map must be 2-dimensional for torch inference")
    if array.size == 0:
        raise ValueError("wafer map must not be empty")
    maximum = float(array.max()) if array.size else 0.0
    if maximum > 0:
        array = array / maximum
    tensor = torch.from_numpy(array).unsqueeze(0).unsqueeze(0)
    if tensor.shape[-2:] != (64, 64):
        tensor = F.interpolate(tensor, size=(64, 64), mode="bilinear", align_corners=False)
    return tensor.to(device)


def _resolve_torch_device(device: str | None) -> Any:
    import torch

    if device is None or device == "auto":
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(device)


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


def _read_rgb_image(image_path: Path) -> np.ndarray:
    """Read an image path into an RGB numpy array for OpenVINO compatibility inference."""
    try:
        from PIL import Image
    except ImportError:
        pass
    else:
        with Image.open(image_path) as pil_image:
            return np.asarray(pil_image.convert("RGB"))

    try:
        import cv2
    except ImportError as exc:
        raise ImportError("Pillow or OpenCV is required to read uploaded images") from exc
    bgr_image = cv2.imread(str(image_path))
    if bgr_image is None:
        raise ValueError(f"failed to read image for OpenVINO inference: {image_path}")
    return cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)


def _resize_to_openvino_input(image: np.ndarray, input_blob: Any) -> np.ndarray:
    """Resize an RGB image to a static OpenVINO NCHW/NHWC input shape when available."""
    target = _openvino_input_hw(input_blob)
    if target is None:
        return image
    height, width = target
    if image.shape[:2] == (height, width):
        return image
    return _resize_image_array(image, height=height, width=width)


def _openvino_input_hw(input_blob: Any) -> tuple[int, int] | None:
    shape = getattr(input_blob, "shape", None)
    if shape is None and hasattr(input_blob, "get_shape"):
        shape = input_blob.get_shape()
    if shape is None:
        return None
    dims = [_static_dimension(dim) for dim in shape]
    if len(dims) != 4 or any(dim is None for dim in dims):
        return None
    batch, channels_first, height_first, width_first = dims
    del batch
    if channels_first in {1, 3} and height_first and width_first:
        return height_first, width_first
    height_last, width_last, channels_last = dims[1], dims[2], dims[3]
    if channels_last in {1, 3} and height_last and width_last:
        return height_last, width_last
    return None


def _static_dimension(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _resize_image_array(image: np.ndarray, *, height: int, width: int) -> np.ndarray:
    try:
        from PIL import Image

        resampling = getattr(Image, "Resampling", Image).BILINEAR
        resized = Image.fromarray(image).resize((width, height), resample=resampling)
        return np.asarray(resized)
    except ImportError:
        y_idx = np.linspace(0, image.shape[0] - 1, height).round().astype(int)
        x_idx = np.linspace(0, image.shape[1] - 1, width).round().astype(int)
        return image[y_idx][:, x_idx]


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
