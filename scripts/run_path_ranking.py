"""Run relation-weighted path ranking for checked-in evidence examples."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kgtracevis.core import KGTracePipeline
from kgtracevis.schema.evidence_schema import Evidence
from kgtracevis.schema.validators import load_evidence_json

DEFAULT_EXAMPLE_DIR = Path("data/examples")
DEFAULT_OUTPUT_DIR = Path("outputs/path_ranking_v0")
DEFAULT_TOP_K = 5


def main() -> None:
    """Run the pipeline on one evidence file or all checked-in examples."""
    parser = _build_parser()
    args = parser.parse_args()

    top_k = _positive_int(args.top_k, "--top-k")
    paths = resolve_evidence_paths(args.evidence, Path(args.example_dir))
    records = analyze_evidence_files(paths, top_k=top_k)

    for record in records:
        print_case_summary(record)

    if args.write_json:
        output_path = write_json_output(
            records,
            evidence_path=args.evidence,
            example_dir=Path(args.example_dir),
            output_dir=Path(args.output_dir),
            top_k=top_k,
            command_args=sys.argv[1:],
        )
        print(f"path ranking output={output_path}")


def resolve_evidence_paths(evidence_path: Path | None, example_dir: Path) -> list[Path]:
    """Resolve the requested evidence file set."""
    if evidence_path is not None:
        if not evidence_path.is_file():
            raise SystemExit(f"evidence file not found: {evidence_path}")
        return [evidence_path]

    paths = sorted(example_dir.glob("*.json"))
    if not paths:
        raise SystemExit(f"no example JSON files found in {example_dir}")
    return paths


def analyze_evidence_files(paths: list[Path], *, top_k: int) -> list[dict[str, Any]]:
    """Validate evidence files and return compact path ranking records."""
    pipeline = KGTracePipeline()
    records: list[dict[str, Any]] = []
    for path in paths:
        evidence = load_evidence_json(path)
        result = pipeline.analyze(evidence, top_k=top_k)
        records.append(_case_record(path, evidence, result.model_dump(mode="json"), top_k=top_k))
    return records


def build_output_payload(
    records: list[dict[str, Any]],
    *,
    evidence_path: Path | None,
    example_dir: Path,
    output_dir: Path,
    top_k: int,
    command_args: list[str],
) -> dict[str, Any]:
    """Build the JSON payload written by the optional output mode."""
    input_mode = "single_evidence" if evidence_path is not None else "examples"
    return {
        "artifact_type": "path_ranking_v0",
        "artifact_scope": "generated_reproducibility_output",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "command": " ".join(("python", "scripts/run_path_ranking.py", *command_args)),
            "input_mode": input_mode,
            "evidence_path": str(evidence_path) if evidence_path is not None else None,
            "example_dir": str(example_dir),
            "output_dir": str(output_dir),
            "top_k": top_k,
            "pipeline": "KGTracePipeline",
            "kg_backend": "neo4j_runtime",
        },
        "note": (
            "Generated path rankings are v0 reproducibility outputs over checked-in examples; "
            "they are not paper-grade root-cause metric claims."
        ),
        "case_count": len(records),
        "cases": records,
    }


def write_json_output(
    records: list[dict[str, Any]],
    *,
    evidence_path: Path | None,
    example_dir: Path,
    output_dir: Path,
    top_k: int,
    command_args: list[str],
) -> Path:
    """Write the optional JSON payload under the ignored outputs directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_output_payload(
        records,
        evidence_path=evidence_path,
        example_dir=example_dir,
        output_dir=output_dir,
        top_k=top_k,
        command_args=command_args,
    )
    output_path = output_dir / "path_ranking_summary.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def print_case_summary(record: dict[str, Any]) -> None:
    """Print a concise path ranking summary for one case."""
    print(
        "path ranking "
        f"{record['evidence_path']}: case_id={record['case_id']}, "
        f"dataset={record['dataset']}, linked={record['linked_count']}, "
        f"consistency={record['consistency_score']}, paths={len(record['top_k_paths'])}"
    )
    for index, path in enumerate(record["top_k_paths"], start=1):
        source = path["source_entity_id"]
        target = path["target_entity_id"]
        relations = " > ".join(path["relations"])
        print(
            f"  {index}. {path['path_id']} "
            f"score={path['score']} {source}->{target} relations={relations}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run KGTracePipeline path ranking for one evidence file or all examples."
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=None,
        help="Optional path to one evidence JSON file. Defaults to all examples.",
    )
    parser.add_argument(
        "--example-dir",
        default=str(DEFAULT_EXAMPLE_DIR),
        help="Directory of example JSON files used when --evidence is omitted.",
    )
    parser.add_argument(
        "--top-k",
        default=DEFAULT_TOP_K,
        type=int,
        help="Number of ranked paths to print and include in JSON output.",
    )
    parser.add_argument(
        "--write-json",
        action="store_true",
        help="Write a provenance-rich JSON summary under outputs/.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory used with --write-json.",
    )
    return parser


def _case_record(
    path: Path,
    evidence: Evidence,
    result: dict[str, Any],
    *,
    top_k: int,
) -> dict[str, Any]:
    paths = list(result["top_k_paths"][:top_k])
    return {
        "evidence_path": str(path),
        "case_id": evidence.case_id,
        "dataset": evidence.dataset,
        "source": evidence.source,
        "object": evidence.object,
        "anomaly_type": evidence.anomaly_type,
        "linked_count": len(result["linked_entities"]),
        "consistency_score": result["consistency_score"],
        "inconsistent_fields": result["inconsistent_fields"],
        "correction_candidate_count": len(result["correction_candidates"]),
        "top_k_paths": paths,
    }


def _positive_int(value: int, flag_name: str) -> int:
    if value < 1:
        raise SystemExit(f"{flag_name} must be >= 1")
    return value


if __name__ == "__main__":
    main()
