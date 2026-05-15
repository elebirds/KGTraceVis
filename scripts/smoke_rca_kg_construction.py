"""Run RCA-KG construction acceptance smoke builds."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from kgtracevis.workflows.kg_construction_smoke import (
    KGConstructionSmokeConfig,
    run_kg_construction_acceptance_smoke,
)


def parse_args() -> argparse.Namespace:
    """Parse smoke workflow arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/source_kg_smoke"),
        help="Directory for smoke build outputs.",
    )
    parser.add_argument(
        "--tep-kg-root",
        type=Path,
        default=_default_tep_kg_root(),
        help="Optional TEP_KG repository root containing data/processed artifacts.",
    )
    parser.add_argument(
        "--require-tep",
        action="store_true",
        help="Fail instead of skipping when TEP_KG artifacts are missing.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run the smoke workflow and print a JSON summary."""
    args = parse_args()
    try:
        result = run_kg_construction_acceptance_smoke(
            KGConstructionSmokeConfig(
                output_dir=args.output_dir,
                overwrite=bool(args.overwrite),
                tep_kg_root=args.tep_kg_root,
                require_tep=bool(args.require_tep),
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result.payload(), indent=2, sort_keys=True))


def _default_tep_kg_root() -> Path | None:
    value = os.environ.get("TEP_KG_ROOT", "").strip()
    return Path(value) if value else None


if __name__ == "__main__":
    main()
