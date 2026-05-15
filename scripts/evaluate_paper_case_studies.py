"""Build paper-facing MVTec object-selection and WM811K traceability summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.paper_case_studies import (
    PaperCaseStudyEvaluationConfig,
    run_paper_case_study_evaluation,
)


def parse_args() -> argparse.Namespace:
    """Parse paper case-study evaluation summary arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Summarize generated MVTec and WM811K artifacts for bounded Section 6 "
            "case-study reporting."
        )
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mvtec-records", required=True, type=Path)
    parser.add_argument("--mvtec-adapter-summary", required=True, type=Path)
    parser.add_argument("--mvtec-pipeline-summary", type=Path)
    parser.add_argument("--wm811k-records", required=True, type=Path)
    parser.add_argument("--wm811k-adapter-summary", required=True, type=Path)
    parser.add_argument("--wm811k-stratified-records", type=Path)
    parser.add_argument("--wm811k-stratified-adapter-summary", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run the reusable workflow and print generated artifact paths."""
    args = parse_args()
    output = run_paper_case_study_evaluation(
        PaperCaseStudyEvaluationConfig(
            output_dir=args.output_dir,
            mvtec_records_path=args.mvtec_records,
            mvtec_adapter_summary_path=args.mvtec_adapter_summary,
            mvtec_pipeline_summary_path=args.mvtec_pipeline_summary,
            wm811k_records_path=args.wm811k_records,
            wm811k_adapter_summary_path=args.wm811k_adapter_summary,
            wm811k_stratified_records_path=args.wm811k_stratified_records,
            wm811k_stratified_adapter_summary_path=args.wm811k_stratified_adapter_summary,
            overwrite=args.overwrite,
        )
    )
    print(
        json.dumps(
            {
                "summary_path": str(output.summary_path),
                "mvtec_object_table": str(output.mvtec_object_table_path),
                "wm811k_pattern_table": str(output.wm811k_pattern_table_path),
                "wm811k_stratified_pattern_table": (
                    str(output.wm811k_stratified_pattern_table_path)
                    if output.wm811k_stratified_pattern_table_path is not None
                    else None
                ),
                "selected_mvtec_object": output.summary["mvtec"]["selected_object"],
                "wm811k_observed_pattern_count": output.summary["wm811k"]["observed_pattern_count"],
                "wm811k_exact_pattern_accuracy": output.summary["wm811k"]["exact_pattern_accuracy"],
                "wm811k_stratified_observed_pattern_count": (
                    output.summary["wm811k_stratified"]["observed_pattern_count"]
                    if output.summary["wm811k_stratified"] is not None
                    else None
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
