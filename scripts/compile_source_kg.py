"""Compile source files into KGBuilder-style LLM KG artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.source_kg_compiler import (
    DEFAULT_LLM_CONCURRENCY,
    OpenAICompatibleSourceKGLLM,
    SourceKGCompilerConfig,
    run_source_kg_compiler_workflow,
)


def parse_args() -> argparse.Namespace:
    """Parse source KG compiler arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        dest="sources",
        type=Path,
        action="append",
        required=True,
        help="Source file or directory. May be provided multiple times.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for generated compiler artifacts.",
    )
    parser.add_argument(
        "--scenario",
        default="shared",
        choices=["shared", "mvtec", "tep", "wafer"],
        help="Default scenario for source units without an explicit SCENARIO line.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--api-key",
        help="OpenAI-compatible API key. Defaults to env files/env vars.",
    )
    parser.add_argument(
        "--base-url",
        help="OpenAI-compatible base URL. Defaults to DeepSeek/OpenAI env.",
    )
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
    return parser.parse_args()


def main() -> None:
    """Run the source KG compiler workflow."""
    args = parse_args()
    llm_client = OpenAICompatibleSourceKGLLM(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    try:
        result = run_source_kg_compiler_workflow(
            SourceKGCompilerConfig(
                source_paths=tuple(args.sources),
                output_dir=args.output_dir,
                llm_client=llm_client,
                default_scenario=args.scenario,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
                llm_concurrency=args.llm_concurrency,
                overwrite=bool(args.overwrite),
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result.summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
