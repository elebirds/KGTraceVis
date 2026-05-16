"""Build source-to-KG candidate CSV artifacts from registered extractor inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.kg_construction import (
    KGConstructionSource,
    load_source_library,
)
from kgtracevis.workflows.source_kg_construction import (
    SourceKGConstructionWorkflowConfig,
    run_source_kg_construction_workflow,
)


def parse_args() -> argparse.Namespace:
    """Parse source-to-KG build arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/source_kg_build"),
        help="Directory for candidate nodes/edges and summary artifacts.",
    )
    parser.add_argument(
        "--source-library",
        type=Path,
        help="CSV, JSON, or JSONL Source Library manifest to build from.",
    )
    parser.add_argument(
        "--tep-semantic-lift-dir",
        type=Path,
        help=(
            "Directory containing semantic_lift_nodes.jsonl and "
            "semantic_lift_edges.jsonl from TEP_KG."
        ),
    )
    parser.add_argument(
        "--tep-semantic-nodes",
        type=Path,
        help="Explicit TEP_KG semantic_lift_nodes.jsonl path.",
    )
    parser.add_argument(
        "--tep-semantic-edges",
        type=Path,
        help="Explicit TEP_KG semantic_lift_edges.jsonl path.",
    )
    parser.add_argument(
        "--tep-variable-mapping",
        type=Path,
        help="TEP_KG tep_variable_mapping CSV/JSON/JSONL path.",
    )
    parser.add_argument(
        "--tep-rca-graph-dir",
        type=Path,
        help="Directory containing TEP_KG RCA nodes.jsonl and edges.jsonl.",
    )
    parser.add_argument(
        "--tep-rca-nodes",
        type=Path,
        help="Explicit TEP_KG RCA nodes.jsonl path.",
    )
    parser.add_argument(
        "--tep-rca-edges",
        type=Path,
        help="Explicit TEP_KG RCA edges.jsonl path.",
    )
    parser.add_argument(
        "--toy-generic-structured-source",
        action="store_true",
        help="Build a tiny generic manual-table source for smoke tests and demos.",
    )
    parser.add_argument(
        "--toy-generic-document-source",
        action="store_true",
        help=(
            "Build a tiny generic text source with an offline document IE fixture; "
            "does not require an LLM key."
        ),
    )
    parser.add_argument(
        "--run-id",
        help="Optional deterministic KG build ID to record in manifests.",
    )
    parser.add_argument(
        "--profile-path",
        type=Path,
        help="Optional JSON RCA profile Domain Pack for semantic/RCA projection.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Build candidate KG rows from source extractor inputs."""
    args = parse_args()
    sources = _build_sources(args)
    if not sources:
        raise SystemExit(
            "No source inputs provided. Pass --tep-semantic-lift-dir, "
            "--tep-semantic-nodes/--tep-semantic-edges, --tep-variable-mapping, "
            "--tep-rca-graph-dir, --source-library, --toy-generic-structured-source, "
            "or --toy-generic-document-source."
        )

    try:
        result = run_source_kg_construction_workflow(
            SourceKGConstructionWorkflowConfig(
                output_dir=Path(args.output_dir),
                sources=tuple(sources),
                overwrite=bool(args.overwrite),
                run_id=args.run_id,
                profile_path=args.profile_path,
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result.summary, indent=2, sort_keys=True))


def _build_sources(args: argparse.Namespace) -> list[KGConstructionSource]:
    sources: list[KGConstructionSource] = []
    if args.source_library is not None:
        sources.extend(
            record.to_construction_source()
            for record in load_source_library(args.source_library)
        )
    if args.tep_semantic_lift_dir is not None:
        sources.append(
            KGConstructionSource(
                source_id="tep_semantic_lift",
                source_type="tep_semantic_lift",
                scenario="tep",
                path=args.tep_semantic_lift_dir,
            )
        )
    if args.tep_semantic_nodes is not None or args.tep_semantic_edges is not None:
        if args.tep_semantic_nodes is None or args.tep_semantic_edges is None:
            raise SystemExit(
                "--tep-semantic-nodes and --tep-semantic-edges must be provided together"
            )
        sources.append(
            KGConstructionSource(
                source_id="tep_semantic_lift",
                source_type="tep_semantic_lift",
                scenario="tep",
                metadata={
                    "nodes_path": args.tep_semantic_nodes,
                    "edges_path": args.tep_semantic_edges,
                },
            )
        )
    if args.tep_variable_mapping is not None:
        sources.append(
            KGConstructionSource(
                source_id="tep_variable_mapping",
                source_type="tep_variable_mapping",
                scenario="tep",
                path=args.tep_variable_mapping,
            )
        )
    if args.tep_rca_graph_dir is not None:
        sources.append(
            KGConstructionSource(
                source_id="tep_rca_graph",
                source_type="tep_rca_graph",
                scenario="tep",
                path=args.tep_rca_graph_dir,
            )
        )
    if args.tep_rca_nodes is not None or args.tep_rca_edges is not None:
        if args.tep_rca_nodes is None or args.tep_rca_edges is None:
            raise SystemExit("--tep-rca-nodes and --tep-rca-edges must be provided together")
        sources.append(
            KGConstructionSource(
                source_id="tep_rca_graph",
                source_type="tep_rca_graph",
                scenario="tep",
                metadata={
                    "nodes_path": args.tep_rca_nodes,
                    "edges_path": args.tep_rca_edges,
                },
            )
        )
    if args.toy_generic_structured_source:
        sources.append(
            KGConstructionSource(
                source_id="toy_generic_source",
                source_type="manual_table",
                scenario="shared",
                text=_toy_generic_source_csv(),
                metadata={"source_format": "csv"},
            )
        )
    if args.toy_generic_document_source:
        sources.append(
            KGConstructionSource(
                source_id="toy_generic_document",
                source_type="txt",
                scenario="shared",
                text=_toy_generic_document_text(),
                metadata={
                    "source_format": "txt",
                    "document_ie_payload": _toy_generic_document_ie_payload(),
                },
            )
        )
    return sources


def _toy_generic_source_csv() -> str:
    return "\n".join(
        [
            "id,name,label,head,relation,tail,scenario,evidence,confidence",
            "PumpA,Pump A,Equipment,,,,shared,pump row,0.82",
            "PressureSignal,Pressure signal,Variable,,,,shared,signal row,0.82",
            ",,,PumpA,MEASURES,PressureSignal,shared,pressure is observed by Pump A sensor,0.62",
            "",
        ]
    )


def _toy_generic_document_text() -> str:
    return (
        "Cooling alert can suggest pump seal wear. "
        "The pressure signal is observed by Pump A."
    )


def _toy_generic_document_ie_payload() -> dict[str, object]:
    return {
        "entities": [
            {
                "id": "CoolingAlert",
                "name": "Cooling alert",
                "label": "Event",
                "evidence": "Cooling alert can suggest pump seal wear.",
                "confidence": 0.56,
            },
            {
                "id": "PumpSealWear",
                "name": "Pump seal wear",
                "label": "RootCause",
                "evidence": "pump seal wear",
                "confidence": 0.52,
            },
            {
                "id": "PressureSignal",
                "name": "Pressure signal",
                "label": "Variable",
                "evidence": "pressure signal",
                "confidence": 0.58,
            },
            {
                "id": "PumpA",
                "name": "Pump A",
                "label": "Equipment",
                "evidence": "Pump A",
                "confidence": 0.58,
            },
        ],
        "relations": [
            {
                "head": "CoolingAlert",
                "relation": "SUGGESTS_ROOT_CAUSE",
                "tail": "PumpSealWear",
                "evidence": "Cooling alert can suggest pump seal wear.",
                "confidence": 0.5,
            },
        ],
    }


if __name__ == "__main__":
    main()
