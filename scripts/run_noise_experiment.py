"""Run deterministic v0 noise reproducibility checks over checked-in examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.noise_experiment import (
    NoiseExperimentConfig,
    run_noise_experiment,
)


def parse_args() -> argparse.Namespace:
    """Parse noise experiment arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--noise-config", default="configs/noise_config.yaml")
    parser.add_argument("--experiment-config", default="configs/experiment_config.yaml")
    return parser.parse_args()


def main() -> None:
    """Run the configured noise experiment and print a compact summary."""
    args = parse_args()
    result = run_noise_experiment(
        NoiseExperimentConfig(
            noise_config=Path(args.noise_config),
            experiment_config=Path(args.experiment_config),
        )
    )
    print(
        "noise experiment "
        f"name={result.summary['experiment_name']}, cases={result.summary['case_count']}, "
        f"records={len(result.records)}, output={result.output_path}"
    )
    print(json.dumps(result.summary["overall"], indent=2))


if __name__ == "__main__":
    main()
