"""Model-aware producer-output record builders."""

from kgtracevis.producers.backends import (
    ANOMALIB_OPENVINO_BACKEND,
    ANOMALIB_TORCH_BACKEND,
    SKLEARN_BACKEND,
    TORCH_RESNET_BACKEND,
    AnomalibMVTecBackend,
    SklearnWM811KBackend,
    TorchWM811KBackend,
    anomalib_prediction_to_mvtec_prediction,
    flatten_wafer_map_features,
    load_trusted_sklearn_model,
    load_trusted_torch_model,
)
from kgtracevis.producers.common import (
    MVTecAnomalyPredictor,
    MVTecPrediction,
    WM811KClassifier,
    WM811KPrediction,
    deterministic_subset,
    filter_forbidden_outputs,
    write_jsonl_records,
)
from kgtracevis.producers.mvtec_records import build_mvtec_records
from kgtracevis.producers.wm811k_records import build_wm811k_records

__all__ = [
    "ANOMALIB_OPENVINO_BACKEND",
    "ANOMALIB_TORCH_BACKEND",
    "MVTecAnomalyPredictor",
    "MVTecPrediction",
    "SKLEARN_BACKEND",
    "TORCH_RESNET_BACKEND",
    "AnomalibMVTecBackend",
    "SklearnWM811KBackend",
    "TorchWM811KBackend",
    "WM811KClassifier",
    "WM811KPrediction",
    "anomalib_prediction_to_mvtec_prediction",
    "build_mvtec_records",
    "build_wm811k_records",
    "deterministic_subset",
    "filter_forbidden_outputs",
    "flatten_wafer_map_features",
    "load_trusted_sklearn_model",
    "load_trusted_torch_model",
    "write_jsonl_records",
]
