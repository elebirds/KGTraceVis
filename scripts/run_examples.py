"""Validate example evidence files and run the minimal pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.core import KGTracePipeline
from kgtracevis.schema.validators import load_evidence_json


def iter_example_files(example_dir: Path) -> list[Path]:
    """Return sorted example JSON files."""
    return sorted(example_dir.glob("*.json"))


def main() -> None:
    """Validate all example JSON files in a directory."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--example-dir", default="data/examples")
    parser.add_argument(
        "--with-neo4j",
        action="store_true",
        help="Reserved for future Neo4j checks.",
    )
    args = parser.parse_args()

    example_dir = Path(args.example_dir)
    pipeline = KGTracePipeline()
    results = []

    for path in iter_example_files(example_dir):
        evidence = load_evidence_json(path)
        result = pipeline.analyze(evidence)
        results.append(result.model_dump())
        print(f"validated {path}: case_id={evidence.case_id}")

    if not results:
        raise SystemExit(f"no example JSON files found in {example_dir}")

    print(json.dumps({"validated": len(results), "with_neo4j": args.with_neo4j}, indent=2))


if __name__ == "__main__":
    main()
