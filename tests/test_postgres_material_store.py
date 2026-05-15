"""Tests for Postgres-backed source material persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from kgtracevis.service.kg_materials import KGMaterialRecord
from kgtracevis.service.postgres import PostgresConfig
from kgtracevis.service.postgres_material_store import PostgresMaterialStore


class FakeResult:
    def __init__(
        self,
        *,
        one: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self._one = one
        self._rows = rows or []

    def fetchone(self) -> dict[str, Any] | None:
        return self._one

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class FakeTransaction:
    def __enter__(self) -> FakeTransaction:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, Any]] = []
        self.material_row = _material_row()
        self.chunk_rows: list[dict[str, Any]] = []

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    def execute(self, sql: str, params: Any = None) -> FakeResult:
        self.executions.append((sql, params))
        if "WHERE material_id = %s" in sql and "FROM source_materials" in sql:
            return FakeResult(one=self.material_row)
        if "FROM source_materials" in sql:
            return FakeResult(rows=[self.material_row])
        if "FROM source_material_chunks" in sql:
            return FakeResult(rows=self.chunk_rows)
        if "RETURNING extraction_run_id::text" in sql:
            return FakeResult(
                one={
                    "extraction_run_id": "11111111-1111-1111-1111-111111111111",
                    "started_at": datetime(2026, 5, 15, tzinfo=timezone.utc),
                    "completed_at": datetime(2026, 5, 15, tzinfo=timezone.utc),
                }
            )
        if "RETURNING artifact_id::text" in sql:
            return FakeResult(
                one={
                    "artifact_id": "22222222-2222-2222-2222-222222222222",
                    "created_at": datetime(2026, 5, 15, tzinfo=timezone.utc),
                }
            )
        return FakeResult()


def test_postgres_material_store_saves_material_record_payload() -> None:
    """Material records should persist the file-backed JSON shape as JSONB."""
    connection = FakeConnection()
    store = PostgresMaterialStore(
        PostgresConfig(dsn="postgresql://unit-test"),
        connection_factory=lambda: connection,
    )

    record = store.save_material_record(_material_payload())

    assert isinstance(record, KGMaterialRecord)
    sql_text = "\n".join(sql for sql, _params in connection.executions)
    assert "INSERT INTO source_materials" in sql_text
    assert "ON CONFLICT (material_id) DO UPDATE" in sql_text

    params = next(
        params for sql, params in connection.executions if "INSERT INTO source_materials" in sql
    )
    assert params[0] == "tep_manual_001"
    assert params[2] == "tep"
    assert params[7] == "registered"
    assert _json_obj(params[13]) == {"source": "manual"}
    assert _json_obj(params[14])["status"] == "not_started"


def test_postgres_material_store_lists_and_gets_material_records() -> None:
    """Stored rows should round-trip to KGMaterialRecord DTOs."""
    connection = FakeConnection()
    store = PostgresMaterialStore(
        PostgresConfig(dsn="postgresql://unit-test"),
        connection_factory=lambda: connection,
    )

    listed = store.list_material_records()
    fetched = store.get_material_record("tep_manual_001")

    assert [record.material_id for record in listed] == ["tep_manual_001"]
    assert fetched.material_id == "tep_manual_001"
    assert fetched.metadata == {"source": "manual"}
    assert fetched.registered_at == "2026-05-15T00:00:00+00:00"


def test_postgres_material_store_replaces_and_lists_source_chunks() -> None:
    """Chunk persistence should keep stable chunk IDs and source ordering."""
    connection = FakeConnection()
    connection.chunk_rows = [
        {
            "chunk_id": "tep_manual_001_chunk_0000",
            "material_id": "tep_manual_001",
            "chunk_index": 0,
            "source_locator": "page=1",
            "text_content": "Compressor pressure relates to reactor faults.",
            "char_start": 0,
            "char_end": 47,
            "metadata": {"page": 1},
            "created_at": datetime(2026, 5, 15, tzinfo=timezone.utc),
        }
    ]
    store = PostgresMaterialStore(
        PostgresConfig(dsn="postgresql://unit-test"),
        connection_factory=lambda: connection,
    )

    saved = store.save_source_chunks(
        "tep_manual_001",
        [
            {
                "source_locator": "page=1",
                "text_content": "Compressor pressure relates to reactor faults.",
                "char_start": 0,
                "char_end": 47,
                "metadata": {"page": 1},
            }
        ],
    )
    listed = store.list_source_chunks("tep_manual_001")

    assert saved[0]["chunk_id"] == "tep_manual_001_chunk_0000"
    assert listed[0]["source_locator"] == "page=1"
    sql_text = "\n".join(sql for sql, _params in connection.executions)
    assert "DELETE FROM source_material_chunks" in sql_text
    assert "INSERT INTO source_material_chunks" in sql_text


def test_postgres_material_store_records_extraction_run_and_artifact() -> None:
    """Extraction state and candidate artifacts should be source-material scoped."""
    connection = FakeConnection()
    store = PostgresMaterialStore(
        PostgresConfig(dsn="postgresql://unit-test"),
        connection_factory=lambda: connection,
    )

    run = store.record_extraction_run(
        "tep_manual_001",
        {
            "status": "extracted",
            "structured_records_path": "runs/source_kg_materials/tep/records.jsonl",
            "source_id": "tep_manual_001",
            "extractor_name": "fake_ie",
            "extractor_version": "unit",
            "record_count": 2,
        },
        provider="fake",
        parameters={"max_chars": 1000},
    )
    artifact = store.save_extraction_artifact(
        material_id="tep_manual_001",
        extraction_run_id=run["extraction_run_id"],
        artifact_type="candidate_records",
        uri="runs/source_kg_materials/tep/records.jsonl",
        media_type="application/jsonl",
        payload={
            "edges": [
                {
                    "source": "tep_manual_001",
                    "evidence": "manual excerpt",
                    "confidence": 0.6,
                    "review_status": "auto",
                }
            ]
        },
    )

    assert run["status"] == "extracted"
    assert artifact["artifact_id"] == "22222222-2222-2222-2222-222222222222"
    extraction_params = next(
        params
        for sql, params in connection.executions
        if "INSERT INTO material_extraction_runs" in sql
    )
    artifact_params = next(
        params
        for sql, params in connection.executions
        if "INSERT INTO material_extraction_artifacts" in sql
    )
    assert extraction_params[1] == "tep_manual_001"
    assert extraction_params[2] == "extracted"
    assert extraction_params[3] == "fake"
    assert _json_obj(extraction_params[12]) == {"max_chars": 1000}
    assert artifact_params[1] == "tep_manual_001"
    assert artifact_params[2] == "candidate_records"
    assert _json_obj(artifact_params[5])["edges"][0]["review_status"] == "auto"


def test_postgres_material_store_rejects_empty_chunk_text() -> None:
    """Chunks without source text should fail before SQL is issued."""
    connection = FakeConnection()
    store = PostgresMaterialStore(
        PostgresConfig(dsn="postgresql://unit-test"),
        connection_factory=lambda: connection,
    )

    with pytest.raises(ValueError, match="source chunk text_content cannot be empty"):
        store.save_source_chunks("tep_manual_001", [{"text_content": " "}])

    assert connection.executions == []


def _material_payload() -> dict[str, Any]:
    return {
        "status": "registered",
        "material_id": "tep_manual_001",
        "title": "TEP operations note",
        "scenario": "tep",
        "material_type": "text",
        "source_kind": "local_path",
        "source_uri": "docs/sources/tep_note.txt",
        "metadata_path": "runs/source_kg_materials/tep_manual_001/metadata.json",
        "registered_at": "2026-05-15T00:00:00+00:00",
        "updated_at": "2026-05-15T00:00:00+00:00",
        "metadata": {"source": "manual"},
    }


def _material_row() -> dict[str, Any]:
    payload = _material_payload()
    return {
        **payload,
        "registered_at": datetime(2026, 5, 15, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 5, 15, tzinfo=timezone.utc),
        "original_filename": None,
        "content_type": None,
        "size_bytes": 0,
        "extraction": {"status": "not_started"},
        "claim_boundary": (
            "source materials are provenance inputs for candidate KG construction; "
            "registration or upload does not verify industrial facts or publish KG rows"
        ),
    }


def _json_obj(value: Any) -> Any:
    return value.obj if hasattr(value, "obj") else value
