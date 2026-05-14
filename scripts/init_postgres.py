"""Initialize the KGTraceVis Postgres application-state schema."""

from __future__ import annotations

import argparse

from kgtracevis.service.postgres import (
    PostgresInitError,
    initialize_postgres_schema,
    load_postgres_schema,
    resolve_postgres_config,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="Postgres DSN. Overrides config and environment.")
    parser.add_argument("--config", default="configs/database.example.yaml")
    parser.add_argument("--schema", default="src/kgtracevis/service/postgres_schema.sql")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load the schema and print its size without connecting to Postgres.",
    )
    return parser.parse_args()


def main() -> None:
    """Initialize Postgres schema or validate the schema file in dry-run mode."""
    args = parse_args()
    if args.dry_run:
        schema_sql = load_postgres_schema(args.schema)
        print(f"Postgres schema dry run ok: {len(schema_sql)} bytes")
        return

    config = resolve_postgres_config(dsn=args.dsn, config_path=args.config)
    try:
        initialize_postgres_schema(config, schema_path=args.schema)
    except (PostgresInitError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print("Postgres schema initialized")


if __name__ == "__main__":
    main()
