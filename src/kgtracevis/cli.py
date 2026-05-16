"""Command entry points for KGTraceVis."""

from __future__ import annotations


def build_kg() -> None:
    """Compile source files into KG CSV files."""
    from scripts.compile_source_kg import main

    main()


def import_kg() -> None:
    """Import KG CSV files into Neo4j."""
    from scripts.import_kg import main

    main()
