"""Run the consolidated v0 local experiment suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.experiments import run_experiment_suite


def main() -> None:
    """Run local v0 checks and write one consolidated suite summary."""
    args = _parse_args()
    result = run_experiment_suite(
        suite_name=args.suite_name,
        output_root=args.output_root,
        experiment_config_path=args.experiment_config,
        noise_config_path=args.noise_config,
        continue_on_failure=args.continue_on_failure,
    )
    summary_path = Path(args.output_root) / args.suite_name / "summary.json"
    table_path = Path(args.output_root) / args.suite_name / "table_summary.csv"
    print(
        "experiment suite "
        f"name={args.suite_name}, commands={len(result.commands)}, "
        f"passed={result.passed}, output={summary_path}, table={table_path}"
    )
    print(
        json.dumps(
            {
                "passed": result.passed,
                "command_count": len(result.commands),
                "summary_path": str(summary_path),
                "table_path": str(table_path),
            },
            indent=2,
        )
    )
    if not result.passed:
        raise SystemExit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-name", default="v0_experiment_suite")
    parser.add_argument("--output-root", default="runs")
    parser.add_argument("--experiment-config", default="configs/experiment_config.yaml")
    parser.add_argument("--noise-config", default="configs/noise_config.yaml")
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue running later commands after a command fails.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
