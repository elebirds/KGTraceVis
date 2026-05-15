"""Tests for Postgres configuration and schema helpers."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.service.postgres import (
    PostgresConfig,
    load_postgres_schema,
    resolve_postgres_config,
)


def test_resolve_postgres_config_precedence(tmp_path: Path) -> None:
    """CLI DSN should override environment and YAML defaults."""
    config_path = tmp_path / "database.yaml"
    config_path.write_text(
        "\n".join(
            [
                "postgres:",
                "  dsn: postgresql://yaml:yaml@localhost:5432/yaml",
            ]
        ),
        encoding="utf-8",
    )

    config = resolve_postgres_config(
        dsn="postgresql://cli:cli@localhost:5432/cli",
        env={"KGTRACE_POSTGRES_DSN": "postgresql://env:env@localhost:5432/env"},
        config_path=config_path,
    )

    assert config == PostgresConfig(dsn="postgresql://cli:cli@localhost:5432/cli")


def test_resolve_postgres_config_builds_dsn_from_parts() -> None:
    """POSTGRES_* environment variables should form a DSN for Docker Compose."""
    config = resolve_postgres_config(
        env={
            "POSTGRES_HOST": "postgres",
            "POSTGRES_PORT": "5433",
            "POSTGRES_DB": "kgtracevis",
            "POSTGRES_USER": "kgtracevis",
            "POSTGRES_PASSWORD": "secret",
        },
        config_path="missing.yaml",
    )

    assert config.dsn == "postgresql://kgtracevis:secret@postgres:5433/kgtracevis"


def test_load_postgres_schema_contains_core_tables() -> None:
    """Tracked schema should contain the application-state tables."""
    schema_sql = load_postgres_schema()

    assert "CREATE TABLE IF NOT EXISTS evidence_cases" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS analysis_runs" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS run_evidence_cases" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS feedback_records" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS kg_versions" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS source_materials" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS source_material_chunks" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS material_extraction_runs" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS material_extraction_artifacts" in schema_sql
    assert "idx_source_materials_scenario_updated" in schema_sql
    assert "idx_material_extraction_runs_material" in schema_sql
    assert "external_run_id" not in schema_sql
    assert "run_details" not in schema_sql
