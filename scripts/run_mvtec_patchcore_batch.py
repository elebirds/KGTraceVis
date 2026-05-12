"""Run target-domain PatchCore fit/eval across DS-MVTec object directories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from kgtracevis.experiments.mvtec_patchcore import (
    OBJECT_SUMMARY_FILENAME,
    PatchCoreObjectRunConfig,
    batch_row_from_object_summary,
    discover_ds_mvtec_object_dirs,
    load_summary,
    run_patchcore_object,
    write_batch_outputs,
)


def parse_args() -> argparse.Namespace:
    """Parse batch PatchCore fit/evaluate options."""
    parser = argparse.ArgumentParser(
        description=(
            "Fit PatchCore on each DS-MVTec object's good images, evaluate a small "
            "subset, then summarize producer and KGTracePipeline outputs."
        )
    )
    parser.add_argument(
        "--dataset-root",
        required=True,
        type=Path,
        help="DS-MVTec root, or its parent containing a DS-MVTec/ directory.",
    )
    parser.add_argument(
        "--output-root",
        default=Path("runs/patchcore_defect_spectrum/batch_patchcore"),
        type=Path,
    )
    parser.add_argument(
        "--object",
        dest="objects",
        action="append",
        help="Object name to run. Repeat for multiple objects. Defaults to all objects.",
    )
    parser.add_argument("--max-objects", type=int)
    parser.add_argument("--max-eval-per-label", default=1, type=int)
    parser.add_argument("--top-k", default=5, type=int)
    parser.add_argument("--device", default="cpu", choices=("cpu", "mps", "gpu", "auto"))
    parser.add_argument("--normal-label", default="good")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run the batch and write top-level JSON/CSV summaries."""
    args = parse_args()
    object_dirs = discover_ds_mvtec_object_dirs(
        args.dataset_root,
        object_names=args.objects,
        max_objects=args.max_objects,
        normal_label=args.normal_label,
    )
    if not object_dirs:
        raise ValueError(f"no DS-MVTec object directories found under {args.dataset_root}")

    args.output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for index, object_dir in enumerate(object_dirs, start=1):
        object_output = args.output_root / object_dir.name
        object_summary_path = object_output / OBJECT_SUMMARY_FILENAME
        print(f"[{index}/{len(object_dirs)}] {object_dir.name}: start")

        if object_summary_path.is_file() and not args.overwrite:
            try:
                summary = load_summary(object_summary_path)
            except Exception as exc:  # noqa: BLE001 - keep batch continuation semantics.
                rows.append(
                    batch_row_from_object_summary(
                        object_name=object_dir.name,
                        status="failed",
                        object_summary_path=object_summary_path,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                print(
                    f"[{index}/{len(object_dirs)}] {object_dir.name}: "
                    f"failed reading existing summary: {exc}"
                )
            else:
                rows.append(
                    batch_row_from_object_summary(
                        object_name=object_dir.name,
                        status="skipped_existing",
                        object_summary_path=object_summary_path,
                        object_summary=summary,
                    )
                )
                print(f"[{index}/{len(object_dirs)}] {object_dir.name}: skipped existing")
            continue

        try:
            summary = run_patchcore_object(
                PatchCoreObjectRunConfig(
                    object_dir=object_dir,
                    output_root=object_output,
                    name=f"ds_mvtec_{object_dir.name}_patchcore",
                    normal_label=args.normal_label,
                    max_eval_per_label=args.max_eval_per_label,
                    top_k=args.top_k,
                    device=args.device,
                    overwrite=args.overwrite,
                )
            )
            rows.append(
                batch_row_from_object_summary(
                    object_name=object_dir.name,
                    status="ok",
                    object_summary_path=object_summary_path,
                    object_summary=summary,
                )
            )
            print(
                f"[{index}/{len(object_dirs)}] {object_dir.name}: ok "
                f"records={summary.get('record_count')}"
            )
        except Exception as exc:  # noqa: BLE001 - batch runner must continue per object.
            rows.append(
                batch_row_from_object_summary(
                    object_name=object_dir.name,
                    status="failed",
                    object_summary_path=object_summary_path,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            print(f"[{index}/{len(object_dirs)}] {object_dir.name}: failed: {exc}")

    summary_path, table_path = write_batch_outputs(
        output_root=args.output_root,
        dataset_root=args.dataset_root,
        rows=rows,
        args={
            "objects": args.objects,
            "max_objects": args.max_objects,
            "max_eval_per_label": args.max_eval_per_label,
            "device": args.device,
            "top_k": args.top_k,
            "normal_label": args.normal_label,
            "overwrite": args.overwrite,
        },
    )
    print(
        json.dumps(
            {
                "summary_path": str(summary_path),
                "table_path": str(table_path),
                "object_count": len(rows),
                "success_count": sum(1 for row in rows if row.get("status") == "ok"),
                "failed_count": sum(1 for row in rows if row.get("status") == "failed"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
