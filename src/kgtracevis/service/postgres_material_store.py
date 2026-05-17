"""Postgres-backed storage for source material library records."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from kgtracevis.service.kg_materials import KGMaterialExtractionState, KGMaterialRecord
from kgtracevis.service.postgres import PostgresConfig, resolve_postgres_config


@dataclass(frozen=True)
class PostgresMaterialStore:
    """Persist source material, chunk, and extraction state in Postgres."""

    config: PostgresConfig
    connection_factory: Any | None = None

    @classmethod
    def from_environment(cls) -> PostgresMaterialStore:
        """Create a store using configured Postgres environment/YAML settings."""
        return cls(resolve_postgres_config())

    def save_material_record(
        self,
        material: KGMaterialRecord | Mapping[str, Any],
    ) -> KGMaterialRecord:
        """Upsert one material-library record and return the validated record."""
        record = _material_record(material)
        payload = record.model_dump(mode="json")
        from psycopg.types.json import Jsonb

        with self._connection() as connection:
            with connection.transaction():
                connection.execute(
                    """
                    INSERT INTO source_materials
                        (material_id, title, scenario, material_type, source_kind,
                         source_uri, metadata_path, status, registered_at, updated_at,
                         original_filename, content_type, size_bytes, metadata,
                         extraction, claim_boundary)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                         %s, %s, %s)
                    ON CONFLICT (material_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        scenario = EXCLUDED.scenario,
                        material_type = EXCLUDED.material_type,
                        source_kind = EXCLUDED.source_kind,
                        source_uri = EXCLUDED.source_uri,
                        metadata_path = EXCLUDED.metadata_path,
                        status = EXCLUDED.status,
                        registered_at = EXCLUDED.registered_at,
                        updated_at = EXCLUDED.updated_at,
                        original_filename = EXCLUDED.original_filename,
                        content_type = EXCLUDED.content_type,
                        size_bytes = EXCLUDED.size_bytes,
                        metadata = EXCLUDED.metadata,
                        extraction = EXCLUDED.extraction,
                        claim_boundary = EXCLUDED.claim_boundary
                    """,
                    (
                        record.material_id,
                        record.title,
                        record.scenario,
                        record.material_type,
                        record.source_kind,
                        record.source_uri,
                        record.metadata_path,
                        record.status,
                        record.registered_at,
                        record.updated_at,
                        record.original_filename,
                        record.content_type,
                        record.size_bytes,
                        Jsonb(payload["metadata"]),
                        Jsonb(payload["extraction"]),
                        record.claim_boundary,
                    ),
                )
        return record

    def list_material_records(self) -> list[KGMaterialRecord]:
        """Return persisted source material records, newest first."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT material_id, title, scenario, material_type, source_kind,
                       source_uri, metadata_path, status, registered_at, updated_at,
                       original_filename, content_type, size_bytes, metadata,
                       extraction, claim_boundary
                FROM source_materials
                ORDER BY updated_at DESC, material_id ASC
                """
            ).fetchall()
        return [_record_from_row(row) for row in rows]

    def get_material_record(self, material_id: str) -> KGMaterialRecord:
        """Return one persisted source material record."""
        material_id = _require_material_id(material_id)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT material_id, title, scenario, material_type, source_kind,
                       source_uri, metadata_path, status, registered_at, updated_at,
                       original_filename, content_type, size_bytes, metadata,
                       extraction, claim_boundary
                FROM source_materials
                WHERE material_id = %s
                """,
                (material_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown material_id: {material_id}")
        return _record_from_row(row)

    def save_source_chunks(
        self,
        material_id: str,
        chunks: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Replace stored source chunks for one material and return stored payloads."""
        material_id = _require_material_id(material_id)
        normalized = [
            _chunk_payload(material_id, index, chunk)
            for index, chunk in enumerate(chunks)
        ]
        from psycopg.types.json import Jsonb

        with self._connection() as connection:
            with connection.transaction():
                connection.execute(
                    "DELETE FROM source_material_chunks WHERE material_id = %s",
                    (material_id,),
                )
                for chunk in normalized:
                    connection.execute(
                        """
                        INSERT INTO source_material_chunks
                            (chunk_id, material_id, chunk_index, source_locator,
                             text_content, char_start, char_end, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            chunk["chunk_id"],
                            material_id,
                            chunk["chunk_index"],
                            chunk.get("source_locator"),
                            chunk["text_content"],
                            chunk.get("char_start"),
                            chunk.get("char_end"),
                            Jsonb(chunk.get("metadata", {})),
                        ),
                    )
        return normalized

    def list_source_chunks(self, material_id: str) -> list[dict[str, Any]]:
        """Return stored chunks for one material in source order."""
        material_id = _require_material_id(material_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, material_id, chunk_index, source_locator, text_content,
                       char_start, char_end, metadata, created_at
                FROM source_material_chunks
                WHERE material_id = %s
                ORDER BY chunk_index ASC, chunk_id ASC
                """,
                (material_id,),
            ).fetchall()
        return [_chunk_from_row(row) for row in rows]

    def record_extraction_run(
        self,
        material_id: str,
        extraction: KGMaterialExtractionState | Mapping[str, Any],
        *,
        extraction_run_id: str | uuid.UUID | None = None,
        provider: str | None = None,
        parameters: Mapping[str, Any] | None = None,
        result_summary: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one extraction-state record for a material."""
        material_id = _require_material_id(material_id)
        state = _extraction_state(extraction)
        run_id = uuid.UUID(str(extraction_run_id)) if extraction_run_id else uuid.uuid4()
        from psycopg.types.json import Jsonb

        with self._connection() as connection:
            with connection.transaction():
                row = connection.execute(
                    """
                    INSERT INTO material_extraction_runs
                        (extraction_run_id, material_id, status, provider, source_format,
                         structured_records_path, source_id, extractor_name,
                         extractor_version, record_count, error_message,
                         completed_at, parameters, result_summary)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                         CASE WHEN %s IN ('extracted', 'failed') THEN now() ELSE NULL END,
                         %s, %s)
                    ON CONFLICT (extraction_run_id) DO UPDATE SET
                        material_id = EXCLUDED.material_id,
                        status = EXCLUDED.status,
                        provider = EXCLUDED.provider,
                        source_format = EXCLUDED.source_format,
                        structured_records_path = EXCLUDED.structured_records_path,
                        source_id = EXCLUDED.source_id,
                        extractor_name = EXCLUDED.extractor_name,
                        extractor_version = EXCLUDED.extractor_version,
                        record_count = EXCLUDED.record_count,
                        error_message = EXCLUDED.error_message,
                        completed_at = EXCLUDED.completed_at,
                        parameters = EXCLUDED.parameters,
                        result_summary = EXCLUDED.result_summary
                    RETURNING extraction_run_id::text, started_at, completed_at
                    """,
                    (
                        run_id,
                        material_id,
                        state.status,
                        provider,
                        state.source_format,
                        state.structured_records_path,
                        state.source_id,
                        state.extractor_name,
                        state.extractor_version,
                        state.record_count,
                        state.error_message,
                        state.status,
                        Jsonb(dict(parameters or {})),
                        Jsonb(dict(result_summary or {})),
                    ),
                ).fetchone()
        return {
            "extraction_run_id": str(row["extraction_run_id"]) if row else str(run_id),
            "material_id": material_id,
            "status": state.status,
            "provider": provider,
            "extraction": state.model_dump(mode="json"),
            "parameters": dict(parameters or {}),
            "result_summary": dict(result_summary or {}),
            "started_at": _iso_or_none(row.get("started_at")) if row else None,
            "completed_at": _iso_or_none(row.get("completed_at")) if row else None,
        }

    def list_extraction_runs(self, material_id: str) -> list[dict[str, Any]]:
        """Return stored extraction runs for one material, newest first."""
        material_id = _require_material_id(material_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT extraction_run_id::text, material_id, status, provider, source_format,
                       structured_records_path, source_id, extractor_name,
                       extractor_version, record_count, error_message,
                       started_at, completed_at, parameters, result_summary
                FROM material_extraction_runs
                WHERE material_id = %s
                ORDER BY started_at DESC, extraction_run_id ASC
                """,
                (material_id,),
            ).fetchall()
        return [_extraction_run_from_row(row) for row in rows]

    def save_extraction_artifact(
        self,
        *,
        material_id: str,
        artifact_type: str,
        extraction_run_id: str | uuid.UUID | None = None,
        uri: str | None = None,
        media_type: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one extraction artifact reference or candidate payload."""
        material_id = _require_material_id(material_id)
        artifact_type = artifact_type.strip()
        if not artifact_type:
            raise ValueError("artifact_type cannot be empty")
        run_id = uuid.UUID(str(extraction_run_id)) if extraction_run_id else None
        from psycopg.types.json import Jsonb

        with self._connection() as connection:
            with connection.transaction():
                row = connection.execute(
                    """
                    INSERT INTO material_extraction_artifacts
                        (extraction_run_id, material_id, artifact_type, uri, media_type, payload)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING artifact_id::text, created_at
                    """,
                    (
                        run_id,
                        material_id,
                        artifact_type,
                        uri,
                        media_type,
                        Jsonb(dict(payload or {})),
                    ),
                ).fetchone()
        return {
            "artifact_id": str(row["artifact_id"]),
            "material_id": material_id,
            "extraction_run_id": str(run_id) if run_id else None,
            "artifact_type": artifact_type,
            "uri": uri,
            "media_type": media_type,
            "payload": dict(payload or {}),
            "created_at": _iso_or_none(row.get("created_at")),
        }

    def list_extraction_artifacts(self, material_id: str) -> list[dict[str, Any]]:
        """Return stored extraction artifacts for one material, newest first."""
        material_id = _require_material_id(material_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT artifact_id::text, material_id, extraction_run_id::text,
                       artifact_type, uri, media_type, payload, created_at
                FROM material_extraction_artifacts
                WHERE material_id = %s
                ORDER BY created_at DESC, artifact_id ASC
                """,
                (material_id,),
            ).fetchall()
        return [_artifact_from_row(row) for row in rows]

    def _connection(self) -> Any:
        if self.connection_factory is not None:
            return self.connection_factory()
        if not self.config.dsn:
            raise RuntimeError(
                "Postgres material storage requires KGTRACE_POSTGRES_DSN or POSTGRES_* settings."
            )
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.config.dsn, row_factory=dict_row)


def _material_record(material: KGMaterialRecord | Mapping[str, Any]) -> KGMaterialRecord:
    if isinstance(material, KGMaterialRecord):
        return material
    return KGMaterialRecord.model_validate(dict(material))


def _extraction_state(
    extraction: KGMaterialExtractionState | Mapping[str, Any],
) -> KGMaterialExtractionState:
    if isinstance(extraction, KGMaterialExtractionState):
        return extraction
    return KGMaterialExtractionState.model_validate(dict(extraction))


def _record_from_row(row: Mapping[str, Any]) -> KGMaterialRecord:
    return KGMaterialRecord.model_validate(
        {
            "status": row["status"],
            "material_id": row["material_id"],
            "title": row["title"],
            "scenario": row["scenario"],
            "material_type": row["material_type"],
            "source_kind": row["source_kind"],
            "source_uri": row["source_uri"],
            "metadata_path": row["metadata_path"],
            "registered_at": _iso_or_none(row["registered_at"]),
            "updated_at": _iso_or_none(row["updated_at"]),
            "original_filename": row.get("original_filename"),
            "content_type": row.get("content_type"),
            "size_bytes": row.get("size_bytes") or 0,
            "metadata": row.get("metadata") or {},
            "extraction": row.get("extraction") or {},
            "claim_boundary": row["claim_boundary"],
        }
    )


def _chunk_payload(
    material_id: str,
    index: int,
    chunk: Mapping[str, Any],
) -> dict[str, Any]:
    text = str(chunk.get("text_content") or chunk.get("text") or "").strip()
    if not text:
        raise ValueError("source chunk text_content cannot be empty")
    chunk_id = str(chunk.get("chunk_id") or f"{material_id}_chunk_{index:04d}")
    return {
        "chunk_id": chunk_id,
        "material_id": material_id,
        "chunk_index": int(chunk.get("chunk_index", index)),
        "source_locator": chunk.get("source_locator"),
        "text_content": text,
        "char_start": chunk.get("char_start"),
        "char_end": chunk.get("char_end"),
        "metadata": dict(cast(Mapping[str, Any], chunk.get("metadata") or {})),
    }


def _chunk_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": row["chunk_id"],
        "material_id": row["material_id"],
        "chunk_index": row["chunk_index"],
        "source_locator": row.get("source_locator"),
        "text_content": row["text_content"],
        "char_start": row.get("char_start"),
        "char_end": row.get("char_end"),
        "metadata": row.get("metadata") or {},
        "created_at": _iso_or_none(row.get("created_at")),
    }


def _extraction_run_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "extraction_run_id": str(row["extraction_run_id"]),
        "material_id": row["material_id"],
        "status": row["status"],
        "provider": row.get("provider"),
        "source_format": row.get("source_format"),
        "structured_records_path": row.get("structured_records_path"),
        "source_id": row.get("source_id"),
        "extractor_name": row.get("extractor_name"),
        "extractor_version": row.get("extractor_version"),
        "record_count": row.get("record_count"),
        "error_message": row.get("error_message"),
        "started_at": _iso_or_none(row.get("started_at")),
        "completed_at": _iso_or_none(row.get("completed_at")),
        "parameters": row.get("parameters") or {},
        "result_summary": row.get("result_summary") or {},
    }


def _artifact_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": str(row["artifact_id"]),
        "material_id": row["material_id"],
        "extraction_run_id": row.get("extraction_run_id"),
        "artifact_type": row["artifact_type"],
        "uri": row.get("uri"),
        "media_type": row.get("media_type"),
        "payload": row.get("payload") or {},
        "created_at": _iso_or_none(row.get("created_at")),
    }


def _require_material_id(material_id: str) -> str:
    material_id = material_id.strip()
    if not material_id:
        raise ValueError("material_id cannot be empty")
    return material_id


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


__all__ = ["PostgresMaterialStore"]
