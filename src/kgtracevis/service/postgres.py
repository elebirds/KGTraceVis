"""Postgres configuration and schema initialization helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]

DEFAULT_POSTGRES_CONFIG_PATH = Path("configs/database.example.yaml")
DEFAULT_POSTGRES_SCHEMA_PATH = Path("src/kgtracevis/service/postgres_schema.sql")
DEFAULT_POSTGRES_ENV = {
    "dsn": "KGTRACE_POSTGRES_DSN",
    "host": "POSTGRES_HOST",
    "port": "POSTGRES_PORT",
    "database": "POSTGRES_DB",
    "user": "POSTGRES_USER",
    "password": "POSTGRES_PASSWORD",
}


@dataclass(frozen=True)
class PostgresConfig:
    """Resolved Postgres connection settings."""

    dsn: str


class PostgresInitError(RuntimeError):
    """Raised when Postgres initialization cannot complete."""


def resolve_postgres_config(
    *,
    dsn: str | None = None,
    env: Mapping[str, str] | None = None,
    config_path: str | Path = DEFAULT_POSTGRES_CONFIG_PATH,
) -> PostgresConfig:
    """Resolve Postgres settings from CLI values, environment, then YAML defaults."""
    config_data = _load_config(config_path)
    env_data = _load_env(env or os.environ)
    resolved_dsn = _first_present(
        dsn,
        env_data.get("dsn"),
        _dsn_from_parts(env_data),
        config_data.get("dsn"),
        _dsn_from_parts(config_data),
    )
    return PostgresConfig(dsn=resolved_dsn)


def load_postgres_schema(schema_path: str | Path = DEFAULT_POSTGRES_SCHEMA_PATH) -> str:
    """Load the application-state schema SQL."""
    path = Path(schema_path)
    if not path.is_file():
        raise ValueError(f"Postgres schema file does not exist: {path}")
    return path.read_text(encoding="utf-8")


def initialize_postgres_schema(
    config: PostgresConfig,
    *,
    schema_path: str | Path = DEFAULT_POSTGRES_SCHEMA_PATH,
) -> None:
    """Apply the Postgres schema to an explicitly configured database."""
    if not config.dsn:
        raise PostgresInitError(
            "Postgres initialization requires a DSN. Provide --dsn, "
            "KGTRACE_POSTGRES_DSN, POSTGRES_* environment variables, or a config YAML file."
        )
    schema_sql = load_postgres_schema(schema_path)
    try:
        import psycopg

        with psycopg.connect(config.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(schema_sql)
            connection.commit()
    except Exception as exc:  # pragma: no cover - exercised by deployment scripts.
        raise PostgresInitError(
            "Postgres schema initialization failed. Check that Postgres is running, "
            f"credentials are correct, and the target database exists. Original error: {exc}"
        ) from exc


def _load_config(config_path: str | Path) -> dict[str, str]:
    path = Path(config_path)
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a mapping")

    raw_config = loaded.get("postgres", loaded)
    if not isinstance(raw_config, dict):
        raise ValueError(f"{path} postgres config must contain a mapping")
    return {
        key: str(value)
        for key, value in raw_config.items()
        if key in DEFAULT_POSTGRES_ENV and value is not None
    }


def _load_env(env: Mapping[str, str]) -> dict[str, str]:
    return {
        key: env[env_name]
        for key, env_name in DEFAULT_POSTGRES_ENV.items()
        if env.get(env_name)
    }


def _dsn_from_parts(values: Mapping[str, str]) -> str:
    if not all(values.get(key) for key in ("host", "database", "user", "password")):
        return ""
    port = values.get("port", "5432")
    return (
        f"postgresql://{values['user']}:{values['password']}"
        f"@{values['host']}:{port}/{values['database']}"
    )


def _first_present(*values: str | None) -> str:
    for value in values:
        if value:
            return value
    return ""
