"""Run TEP raw/record RCA evaluation through the unified KGTracePipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.tep_evaluation import (
    TepRcaEvaluationConfig,
    run_tep_rca_evaluation,
)


def parse_args() -> argparse.Namespace:
    """Parse TEP RCA evaluation arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--raw-data-dir", default=Path("data/raw/tep"), type=Path)
    parser.add_argument(
        "--input-records",
        type=Path,
        help="Optional existing TEP producer JSONL. If omitted, raw CSV records are built first.",
    )
    parser.add_argument("--faults", default="1,2,6")
    parser.add_argument("--max-runs-per-fault", default=2, type=int)
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--window-size", default=100, type=int)
    parser.add_argument("--row-stride", default=200, type=int)
    parser.add_argument("--fault-free-max-rows", default=1000, type=int)
    parser.add_argument("--top-variables", default=8, type=int)
    parser.add_argument("--n-components", default=6, type=int)
    parser.add_argument("--top-k", default=5, type=int)
    parser.add_argument(
        "--kg-node-path",
        action="append",
        default=[],
        type=Path,
        help="TEP KG node CSV overlay. Defaults to data/kg/tep_nodes.csv.",
    )
    parser.add_argument(
        "--kg-edge-path",
        action="append",
        default=[],
        type=Path,
        help="TEP KG edge CSV overlay. Defaults to data/kg/tep_edges.csv.",
    )
    parser.add_argument(
        "--use-neo4j-runtime",
        action="store_true",
        help="Use the configured Neo4j runtime instead of explicit CSV overlays.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run the evaluation and print a compact JSON result."""
    args = parse_args()
    output = run_tep_rca_evaluation(
        TepRcaEvaluationConfig(
            output_dir=args.output_dir,
            raw_data_dir=args.raw_data_dir,
            input_records_path=args.input_records,
            faults=_parse_faults(args.faults),
            max_runs_per_fault=args.max_runs_per_fault,
            max_cases=args.max_cases,
            window_size=args.window_size,
            row_stride=args.row_stride,
            fault_free_max_rows=args.fault_free_max_rows,
            top_variables=args.top_variables,
            n_components=args.n_components,
            top_k=args.top_k,
            kg_node_paths=tuple(args.kg_node_path or [Path("data/kg/tep_nodes.csv")]),
            kg_edge_paths=tuple(args.kg_edge_path or [Path("data/kg/tep_edges.csv")]),
            use_neo4j_runtime=args.use_neo4j_runtime,
            overwrite=args.overwrite,
        )
    )
    print(
        json.dumps(
            {
                "summary_path": str(output.summary_path),
                "table_path": str(output.table_path),
                "records_path": str(output.records_path),
                "adapter_summary_path": str(output.adapter_summary_path),
                "metrics": output.summary["metrics"],
            },
            indent=2,
        )
    )


def _parse_faults(raw: str | None) -> tuple[int, ...]:
    if raw is None or raw.strip() == "":
        return ()
    return tuple(int(part.strip()) for part in raw.split(",") if part.strip())


if __name__ == "__main__":
    main()
