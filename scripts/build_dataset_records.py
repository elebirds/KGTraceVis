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
    TORCH_RESNET_BACKEND,
    AnomalibMVTecBackend,
    MVTecAnomalyPredictor,
    SklearnWM811KBackend,
    TorchWM811KBackend,
    WM811KClassifier,
    write_jsonl_records,
)
from kgtracevis.producers.mvtec_records import build_mvtec_records
from kgtracevis.producers.wm811k_records import build_wm811k_records

MVTEC_BACKENDS = (ANOMALIB_TORCH_BACKEND, ANOMALIB_OPENVINO_BACKEND)
WM811K_BACKENDS = (SKLEARN_BACKEND, TORCH_RESNET_BACKEND)
MODEL_BACKENDS = (*MVTEC_BACKENDS, *WM811K_BACKENDS)


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
        required=True,
        choices=MODEL_BACKENDS,
        help=(
            "Real inference backend. MVTec supports anomalib-torch and "
            "anomalib-openvino. WM811K supports sklearn and torch-resnet34."
        ),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help=(
            "Model checkpoint path. Required for all real backends; sklearn "
            "joblib/pickle files must be trusted local files."
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
        if args.model_backend not in MVTEC_BACKENDS:
            raise ValueError(
                "--model-backend for --dataset mvtec must be one of "
                f"{MVTEC_BACKENDS}"
            )
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
        if args.model_backend not in WM811K_BACKENDS:
            raise ValueError(
                "--model-backend for --dataset wm811k/wafer must be one of "
                f"{WM811K_BACKENDS}"
            )
        classifier = build_wm811k_classifier(
            model_backend=args.model_backend,
            checkpoint=args.checkpoint,
            device=args.device,
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
    device: str | None = None,
) -> WM811KClassifier:
    """Return the selected WM811K classifier backend."""
    if model_backend == SKLEARN_BACKEND:
        return SklearnWM811KBackend(checkpoint=checkpoint)
    if model_backend == TORCH_RESNET_BACKEND:
        return TorchWM811KBackend(checkpoint=checkpoint, device=device)
    raise ValueError(
        f"unsupported WM811K --model-backend {model_backend!r}; expected one of {WM811K_BACKENDS}"
    )


def _label_counts(records: Sequence[Mapping[str, Any]]) -> Counter[str]:
    return Counter(
        str(record.get("defect_type") or record.get("failure_pattern") or "unknown")
        for record in records
    )


if __name__ == "__main__":
    main()
