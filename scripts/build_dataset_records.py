"""Build producer-output dataset records from local raw/subset data."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from kgtracevis.producers import (
    ANOMALIB_OPENVINO_BACKEND,
    ANOMALIB_TORCH_BACKEND,
    SKLEARN_BACKEND,
    AnomalibMVTecBackend,
    MVTecAnomalyPredictor,
    MVTecPrediction,
    SklearnWM811KBackend,
    WM811KClassifier,
    WM811KPrediction,
    write_jsonl_records,
)
from kgtracevis.producers.mvtec_records import build_mvtec_records
from kgtracevis.producers.wm811k_records import build_wm811k_records

FAKE_BACKEND = "fake"
MVTEC_BACKENDS = (FAKE_BACKEND, ANOMALIB_TORCH_BACKEND, ANOMALIB_OPENVINO_BACKEND)
WM811K_BACKENDS = (FAKE_BACKEND, SKLEARN_BACKEND)


class FakeMVTecPredictor:
    """Deterministic checkpoint-free predictor for tests and smoke runs."""

    def predict(self, image_path: Path) -> MVTecPrediction:
        """Return stable fake anomaly outputs from the image path."""
        is_good = "good" in {part.lower() for part in image_path.parts}
        score = 0.05 if is_good else 0.82
        mask = [[0, 0, 0], [0, 0 if is_good else 1, 0], [0, 0, 0]]
        return {
            "score": score,
            "confidence": score,
            "anomaly_map": [[score / 2, score / 2, score / 2], [score / 2, score, score / 2]],
            "mask": mask,
            "metadata": {"fake_backend": True},
        }


class FakeWM811KClassifier:
    """Deterministic checkpoint-free WM811K classifier for tests and smoke runs."""

    def predict(
        self,
        wafer_map: Sequence[Sequence[Any]],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> WM811KPrediction:
        """Return the native pattern when available, otherwise a density-based label."""
        native = str((metadata or {}).get("native_failure_pattern") or "").strip()
        failed = sum(1 for row in wafer_map for value in row if _failed_die(value))
        total = sum(len(row) for row in wafer_map)
        density = failed / total if total else 0.0
        pattern = (
            native
            if native and native.lower() != "none"
            else ("Near-full" if density > 0.5 else "Random")
        )
        return {
            "pattern": pattern,
            "confidence": 0.8 if native else 0.55,
            "metadata": {"fake_backend": True},
        }


def parse_args() -> argparse.Namespace:
    """Parse producer record build arguments."""
    parser = argparse.ArgumentParser(
        description="Build normalized producer-output records for adapter ingestion."
    )
    parser.add_argument("--dataset", required=True, choices=("mvtec", "wm811k", "wafer"))
    parser.add_argument("--input-root", type=Path, help="MVTec-like input directory root.")
    parser.add_argument("--input", type=Path, help="WM811K pandas-readable input table.")
    parser.add_argument("--output-jsonl", required=True, type=Path)
    parser.add_argument(
        "--model-backend",
        default="fake",
        help=(
            "Inference backend. MVTec supports fake, anomalib-torch, and "
            "anomalib-openvino. WM811K supports fake and sklearn."
        ),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help=(
            "Model checkpoint path. Required for anomalib-* and sklearn backends; "
            "sklearn joblib/pickle files must be trusted local files."
        ),
    )
    parser.add_argument("--threshold", default=0.5, type=float)
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--max-per-label", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--device",
        help="Optional device passed to supported local model inferencers.",
    )
    parser.add_argument(
        "--include-good",
        action="store_true",
        help="Include MVTec good/normal samples in the produced record subset.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing JSONL output.")
    return parser.parse_args()


def main() -> None:
    """Build records and print a compact JSON summary."""
    args = parse_args()
    artifact_dir = args.output_jsonl.with_suffix("")

    if args.dataset == "mvtec":
        if args.input_root is None:
            raise ValueError("--input-root is required for --dataset mvtec")
        predictor = build_mvtec_predictor(
            model_backend=args.model_backend,
            checkpoint=args.checkpoint,
            device=args.device,
        )
        records = build_mvtec_records(
            args.input_root,
            predictor,
            output_dir=artifact_dir,
            model_backend=args.model_backend,
            checkpoint=args.checkpoint,
            threshold=args.threshold,
            max_cases=args.max_cases,
            max_per_label=args.max_per_label,
            seed=args.seed,
            include_good=args.include_good,
        )
    else:
        if args.input is None:
            raise ValueError("--input is required for --dataset wm811k/wafer")
        classifier = build_wm811k_classifier(
            model_backend=args.model_backend,
            checkpoint=args.checkpoint,
        )
        records = build_wm811k_records(
            args.input,
            classifier,
            output_dir=artifact_dir,
            model_backend=args.model_backend,
            checkpoint=args.checkpoint,
            threshold=args.threshold,
            max_cases=args.max_cases,
            max_per_label=args.max_per_label,
            seed=args.seed,
        )

    output_path = write_jsonl_records(records, args.output_jsonl, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "dataset": args.dataset,
                "record_count": len(records),
                "labels": dict(sorted(_label_counts(records).items())),
                "output_jsonl": str(output_path),
                "artifact_dir": str(artifact_dir),
                "claim_boundary": (
                    "producer records contain observed model outputs and native labels only; "
                    "root causes and ranked paths are KGTracePipeline runtime outputs"
                ),
            },
            indent=2,
        )
        )


def build_mvtec_predictor(
    *,
    model_backend: str,
    checkpoint: Path | None = None,
    device: str | None = None,
) -> MVTecAnomalyPredictor:
    """Return the selected MVTec predictor backend."""
    if model_backend == FAKE_BACKEND:
        return FakeMVTecPredictor()
    if model_backend in {ANOMALIB_TORCH_BACKEND, ANOMALIB_OPENVINO_BACKEND}:
        return AnomalibMVTecBackend(
            backend=model_backend,
            checkpoint=checkpoint,
            device=device,
        )
    raise ValueError(
        f"unsupported MVTec --model-backend {model_backend!r}; expected one of {MVTEC_BACKENDS}"
    )


def build_wm811k_classifier(
    *,
    model_backend: str,
    checkpoint: Path | None = None,
) -> WM811KClassifier:
    """Return the selected WM811K classifier backend."""
    if model_backend == FAKE_BACKEND:
        return FakeWM811KClassifier()
    if model_backend == SKLEARN_BACKEND:
        return SklearnWM811KBackend(checkpoint=checkpoint)
    raise ValueError(
        f"unsupported WM811K --model-backend {model_backend!r}; expected one of {WM811K_BACKENDS}"
    )


def _label_counts(records: Sequence[Mapping[str, Any]]) -> Counter[str]:
    return Counter(
        str(record.get("defect_type") or record.get("failure_pattern") or "unknown")
        for record in records
    )


def _failed_die(value: Any) -> bool:
    try:
        return float(value) > 1
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    main()
