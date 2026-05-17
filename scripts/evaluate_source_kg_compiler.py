"""Run source KG compiler parity and generated-only sample analysis."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from kgtracevis.source_kg_compiler import DEFAULT_LLM_CONCURRENCY, OpenAICompatibleSourceKGLLM
from kgtracevis.source_kg_compiler.models import SourceKGProgressCallback
from kgtracevis.workflows.source_kg_compiler_evaluation import (
    DEFAULT_KGBUILDER_MATERIALS_DIR,
    DEFAULT_KGBUILDER_OUTPUTS_DIR,
    DEFAULT_SAMPLE_PATHS,
    SourceKGCompilerEvaluationConfig,
    run_source_kg_compiler_evaluation,
)


def parse_args() -> argparse.Namespace:
    """Parse compiler evaluation arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--materials-dir",
        type=Path,
        default=DEFAULT_KGBUILDER_MATERIALS_DIR,
        help="KGBuilder materials directory used when --source is not provided.",
    )
    parser.add_argument(
        "--source",
        dest="sources",
        type=Path,
        action="append",
        default=[],
        help="Source file or directory. May be provided multiple times.",
    )
    parser.add_argument(
        "--baseline-output-dir",
        type=Path,
        default=DEFAULT_KGBUILDER_OUTPUTS_DIR,
        help="Existing KGBuilder outputs directory to compare without rerunning KGBuilder.",
    )
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Skip KGBuilder artifact comparison.",
    )
    parser.add_argument(
        "--sample",
        dest="samples",
        type=Path,
        action="append",
        default=[],
        help="Evidence JSON sample to analyze. Defaults to the four checked-in examples.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for compiled artifacts and evaluation report.",
    )
    parser.add_argument(
        "--scenario",
        default="shared",
        choices=["shared", "mvtec", "tep", "wafer"],
        help="Default scenario for source units without an explicit SCENARIO line.",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--api-key", help="OpenAI-compatible API key. Defaults to env.")
    parser.add_argument("--base-url", help="OpenAI-compatible base URL. Defaults to env.")
    parser.add_argument("--model", help="OpenAI-compatible model name.")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--chunk-size", type=int, default=8000)
    parser.add_argument("--chunk-overlap", type=int, default=800)
    parser.add_argument(
        "--llm-concurrency",
        type=int,
        default=DEFAULT_LLM_CONCURRENCY,
        help="Maximum concurrent LLM calls within independent compiler stages.",
    )
    parser.add_argument(
        "--limit-sources",
        type=int,
        default=None,
        help="Limit loaded source files for quick smoke runs.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress default progress logs. Final JSON summary is still printed.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the evaluation workflow and print a concise summary."""
    args = parse_args()
    output_dir = args.output_dir or _default_output_dir()
    progress_callback = None if args.quiet else make_progress_logger(sys.stderr)
    llm_client = OpenAICompatibleSourceKGLLM(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    try:
        result = run_source_kg_compiler_evaluation(
            SourceKGCompilerEvaluationConfig(
                output_dir=output_dir,
                llm_client=llm_client,
                materials_dir=args.materials_dir.expanduser(),
                source_paths=tuple(path.expanduser() for path in args.sources),
                baseline_output_dir=(
                    None if args.no_baseline else args.baseline_output_dir.expanduser()
                ),
                sample_paths=tuple(args.samples) if args.samples else DEFAULT_SAMPLE_PATHS,
                default_scenario=args.scenario,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
                llm_concurrency=args.llm_concurrency,
                top_k=args.top_k,
                overwrite=bool(args.overwrite),
                source_limit=args.limit_sources,
                progress_callback=progress_callback,
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "report_path": result.report_path.as_posix(),
                "compiled_output_dir": result.compiled_output_dir.as_posix(),
                "summary": result.report["summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )


def _default_output_dir() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("runs") / "source_kg_compiler_evaluation" / timestamp


def make_progress_logger(stream: TextIO) -> SourceKGProgressCallback:
    """Return a concise stderr-style progress callback for long evaluation runs."""

    def log(event: dict[str, Any]) -> None:
        stage = str(event.get("stage") or "unknown")
        event_name = str(event.get("event") or "progress")
        elapsed = float(event.get("elapsed_seconds") or 0.0)
        parts = [f"[source-kg-eval] {elapsed:8.1f}s", event_name, f"stage={stage}"]
        item = event.get("item")
        if item:
            parts.append(f"item={item}")
        if event_name.startswith("llm_"):
            parts.extend(
                [
                    f"calls={int(event.get('llm_calls') or 0)}",
                    f"tokens={int(event.get('llm_total_tokens') or 0)}",
                ]
            )
            if "llm_elapsed_seconds" in event:
                parts.append(f"llm_elapsed={float(event['llm_elapsed_seconds']):.1f}s")
        for key in (
            "source_path_count",
            "source_limit",
            "source_unit_count",
            "knowledge_card_count",
            "entity_count",
            "edge_count",
            "sample_count",
            "status",
        ):
            value = event.get(key)
            if value is not None:
                parts.append(f"{key}={value}")
        if stage == "evaluation_config":
            parts.append(
                "smoke_hint='use --limit-sources N or --source PATH for quick checks'"
            )
            for key in (
                "output_dir",
                "compiled_output_dir",
                "baseline_output_dir",
                "default_scenario",
                "chunk_size",
                "chunk_overlap",
                "llm_concurrency",
                "top_k",
                "overwrite",
            ):
                value = event.get(key)
                if value is not None:
                    parts.append(f"{key}={value}")
        if stage == "report_written":
            report_path = event.get("report_path")
            compiled_output_dir = event.get("compiled_output_dir")
            if report_path:
                parts.append(f"report_path={report_path}")
            if compiled_output_dir:
                parts.append(f"compiled_output_dir={compiled_output_dir}")
        print(" ".join(parts), file=stream, flush=True)

    return log


if __name__ == "__main__":
    main()
