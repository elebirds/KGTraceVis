"""Postgres-backed runtime storage for dashboard analysis runs."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from kgtracevis.service.postgres import PostgresConfig, resolve_postgres_config
from kgtracevis.service.postgres_run_payloads import (
    FeedbackRecordAdapter,
    api_feedback_target_type,
    api_feedback_value,
    case_entries,
    detail_payload,
    dict_value,
    feedback_context,
    feedback_target_key,
    feedback_target_type,
    feedback_value,
    float_value,
    list_value,
    nullable_float,
    optional_text,
    parse_run_uuid,
    run_dataset,
    run_summary_payload,
    valid_dataset,
)
from kgtracevis.service.run_models import RunDetail, RunSummary


@dataclass(frozen=True)
class PostgresRunStore:
    """Persist and load dashboard run state from Postgres structured tables."""

    config: PostgresConfig
    connection_factory: Any | None = None

    @classmethod
    def from_environment(cls) -> PostgresRunStore:
        """Create a store using configured Postgres environment/YAML settings."""
        return cls(resolve_postgres_config())

    def list_run_summaries(self) -> list[dict[str, Any]]:
        """Return run summaries as JSON-compatible payloads."""
        return [run.model_dump(mode="json") for run in self.list_runs()]

    def persist_run_detail(self, detail: Mapping[str, Any]) -> None:
        """Persist a JSON-compatible run detail payload."""
        self.save_run(RunDetail.model_validate(detail))

    def list_runs(self) -> list[Any]:
        """Return persisted run summaries, newest first."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT run_id, started_at, mode, source_filename, top_k, run_dir,
                       status, dataset, case_count, evidence_count, label,
                       model_preset, model_backend
                FROM analysis_runs
                ORDER BY started_at DESC
                """
            ).fetchall()
        return [RunSummary.model_validate(run_summary_payload(row)) for row in rows]

    def get_run_detail(self, run_id: str) -> Any:
        """Load one run detail reconstructed from normalized runtime tables."""
        run_uuid = parse_run_uuid(run_id)
        with self._connection() as connection:
            run_row = connection.execute(
                """
                SELECT run_id, started_at, mode, source_filename, top_k, run_dir,
                       status, dataset, case_count, evidence_count, label,
                       model_preset, model_backend, claim_boundary, parameters, summary
                FROM analysis_runs
                WHERE run_id = %s
                """,
                (run_uuid,),
            ).fetchone()
            if run_row is None:
                raise ValueError(f"unknown run session: {run_id}")
            case_rows = connection.execute(
                """
                SELECT c.id AS case_pk, c.case_id, c.dataset, c.evidence_payload,
                       c.raw_evidence, c.normalized_evidence, c.human_feedback,
                       rc.case_order, rc.generated_evidence_path, rc.adapter_name
                FROM run_evidence_cases rc
                JOIN evidence_cases c ON c.id = rc.case_pk
                WHERE rc.run_id = %s
                ORDER BY rc.case_order ASC, c.case_id ASC
                """,
                (run_uuid,),
            ).fetchall()
            linked_rows = connection.execute(
                """
                SELECT case_pk, link_id, field, mention, obs_id, facet,
                       selected_entity_id, selected_entity_name, selected_entity_scenario,
                       score, match_type, ambiguous, ambiguity_margin, candidates
                FROM linked_entities
                WHERE run_id = %s
                ORDER BY field ASC, link_id ASC
                """,
                (run_uuid,),
            ).fetchall()
            consistency_rows = connection.execute(
                """
                SELECT case_pk, consistency_score, inconsistent_fields, checks
                FROM consistency_checks
                WHERE run_id = %s
                ORDER BY created_at ASC
                """,
                (run_uuid,),
            ).fetchall()
            correction_rows = connection.execute(
                """
                SELECT case_pk, candidate_id, field, original_value, suggested_value,
                       suggested_entity_id, score, reason, source_edges, payload
                FROM correction_candidates
                WHERE run_id = %s
                ORDER BY field ASC, candidate_id ASC
                """,
                (run_uuid,),
            ).fetchall()
            path_rows = connection.execute(
                """
                SELECT case_pk, path_id, rank, source_entity_id, target_entity_id,
                       node_ids, relation_ids, score, confidence, evidence_match,
                       source_edge_ids, supporting_evidence, payload
                FROM ranked_paths
                WHERE run_id = %s
                ORDER BY rank ASC, path_id ASC
                """,
                (run_uuid,),
            ).fetchall()
            artifact_rows = connection.execute(
                """
                SELECT artifact_type, uri, media_type, metadata
                FROM artifacts
                WHERE run_id = %s
                ORDER BY artifact_type ASC, uri ASC
                """,
                (run_uuid,),
            ).fetchall()

        payload = detail_payload(
            run_row=run_row,
            case_rows=case_rows,
            linked_rows=linked_rows,
            consistency_rows=consistency_rows,
            correction_rows=correction_rows,
            path_rows=path_rows,
            artifact_rows=artifact_rows,
        )
        return RunDetail.model_validate(payload)

    def get_artifact_path(self, run_id: str, artifact_name: str) -> str:
        """Return the stored local path for a run artifact filename."""
        run_uuid = parse_run_uuid(run_id)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT uri
                FROM artifacts
                WHERE run_id = %s
                  AND uri LIKE %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (run_uuid, f"%/{artifact_name}"),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown run artifact: {artifact_name}")
        return str(row["uri"])

    def save_run(self, detail: Any) -> Any:
        """Persist a newly created run detail and return it unchanged."""
        run_id = parse_run_uuid(detail.run.run_id)
        entries = case_entries(detail)
        dataset = run_dataset(detail, entries)
        primary_case_pk: uuid.UUID | None = None

        with self._connection() as connection:
            with connection.transaction():
                case_pks: dict[tuple[str, str], uuid.UUID] = {}
                run_cases: list[tuple[uuid.UUID, int, str | None, str | None]] = []
                for order, entry in enumerate(entries):
                    case_pk = self._upsert_evidence_case(connection, entry["evidence"])
                    case_pks[(entry["dataset"], entry["case_id"])] = case_pk
                    if primary_case_pk is None:
                        primary_case_pk = case_pk
                    run_cases.append(
                        (
                            case_pk,
                            order,
                            cast(str | None, entry.get("evidence_path")),
                            cast(str | None, entry.get("adapter_name")),
                        )
                    )

                from psycopg.types.json import Jsonb

                parameters = {
                    "workflow_steps": [
                        step.model_dump(mode="json") for step in detail.workflow_steps
                    ],
                    "source_dataset_label": detail.run.dataset,
                    "ranked_root_causes_by_case": {
                        str(entry["case_id"]): entry.get("ranked_root_causes", [])
                        for entry in entries
                    },
                }
                connection.execute(
                    """
                    INSERT INTO analysis_runs
                        (run_id, case_pk, dataset, mode, source_filename, top_k,
                         run_dir, case_count, evidence_count, label, claim_boundary,
                         model_preset, model_backend, status, started_at, completed_at,
                         parameters, summary)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                         %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                        case_pk = EXCLUDED.case_pk,
                        dataset = EXCLUDED.dataset,
                        mode = EXCLUDED.mode,
                        source_filename = EXCLUDED.source_filename,
                        top_k = EXCLUDED.top_k,
                        run_dir = EXCLUDED.run_dir,
                        case_count = EXCLUDED.case_count,
                        evidence_count = EXCLUDED.evidence_count,
                        label = EXCLUDED.label,
                        claim_boundary = EXCLUDED.claim_boundary,
                        model_preset = EXCLUDED.model_preset,
                        model_backend = EXCLUDED.model_backend,
                        status = EXCLUDED.status,
                        completed_at = EXCLUDED.completed_at,
                        parameters = EXCLUDED.parameters,
                        summary = EXCLUDED.summary
                    """,
                    (
                        run_id,
                        primary_case_pk,
                        dataset,
                        detail.run.mode,
                        detail.run.source_filename,
                        detail.run.top_k,
                        detail.run.run_dir,
                        detail.run.case_count,
                        detail.run.evidence_count,
                        detail.run.label,
                        detail.claim_boundary,
                        detail.run.model_preset,
                        detail.run.model_backend,
                        detail.run.status,
                        detail.run.created_at,
                        detail.run.created_at,
                        Jsonb(parameters),
                        Jsonb(detail.summary or {}),
                    ),
                )
                connection.execute("DELETE FROM run_evidence_cases WHERE run_id = %s", (run_id,))
                for case_pk, order, evidence_path, adapter_name in run_cases:
                    connection.execute(
                        """
                        INSERT INTO run_evidence_cases
                            (run_id, case_pk, case_order, generated_evidence_path, adapter_name)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (run_id, case_pk) DO UPDATE SET
                            case_order = EXCLUDED.case_order,
                            generated_evidence_path = EXCLUDED.generated_evidence_path,
                            adapter_name = EXCLUDED.adapter_name
                        """,
                        (run_id, case_pk, order, evidence_path, adapter_name),
                    )
                self._replace_run_children(connection, run_id)
                for entry in entries:
                    case_pk = case_pks[(entry["dataset"], entry["case_id"])]
                    _insert_linked_entities(connection, run_id, case_pk, entry["linked_entities"])
                    _insert_consistency_check(connection, run_id, case_pk, entry)
                    _insert_corrections(connection, run_id, case_pk, entry["correction_candidates"])
                    _insert_paths(connection, run_id, case_pk, entry["top_k_paths"])
                _insert_artifacts(connection, run_id, primary_case_pk, detail)
        return detail

    def record_feedback(self, request: Any) -> dict[str, Any]:
        """Persist one feedback record in Postgres and return an API receipt."""
        if isinstance(request, Mapping):
            request = FeedbackRecordAdapter(request)
        run_uuid = parse_run_uuid(request.run_id) if request.run_id else None
        target_type = feedback_target_type(request.target_type)
        feedback = feedback_value(request.review_action())
        note = request.review_note()
        target_id = request.target_id or request.case_id or request.run_id or request.target_type
        metadata = dict(request.metadata) if isinstance(request.metadata, dict) else {}
        source = optional_text(getattr(request, "source", None)) or "unknown"

        with self._connection() as connection:
            context = feedback_context(connection, run_uuid, request.case_id)
            from psycopg.types.json import Jsonb

            row = connection.execute(
                """
                INSERT INTO feedback_records
                    (dataset, run_id, case_pk, target_type, target_id, feedback,
                     corrected_value, comment, reviewer, source, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING feedback_id, created_at
                """,
                (
                    context["dataset"],
                    run_uuid,
                    context.get("case_pk"),
                    target_type,
                    target_id,
                    feedback,
                    Jsonb(metadata.get("corrected_value")) if metadata else None,
                    note,
                    request.reviewer,
                    source,
                    Jsonb(metadata),
                ),
            ).fetchone()
            connection.commit()

        record = {
            "feedback_id": str(row["feedback_id"]),
            "created_at": row["created_at"].isoformat(),
            **request.model_dump(mode="json"),
            "action": request.review_action(),
            "note": note,
            "target_type": request.target_type,
            "target_id": target_id,
            "target_key": feedback_target_key(request.target_type, target_id, metadata),
            "source": source,
            "metadata": metadata,
        }
        return {"status": "recorded", "record": record}

    def list_feedback(self, request: Any) -> dict[str, Any]:
        """Return append-only feedback records using dashboard-friendly fields."""
        run_id = request.get("run_id") if isinstance(request, Mapping) else request.run_id
        case_id = request.get("case_id") if isinstance(request, Mapping) else request.case_id
        target_type = (
            request.get("target_type") if isinstance(request, Mapping) else request.target_type
        )
        target_id = request.get("target_id") if isinstance(request, Mapping) else request.target_id
        offset = request.get("offset", 0) if isinstance(request, Mapping) else request.offset
        limit = request.get("limit", 50) if isinstance(request, Mapping) else request.limit

        run_uuid = parse_run_uuid(run_id) if run_id else None
        target_type_filter = feedback_target_type(target_type) if target_type else None
        normalized_case_id = optional_text(case_id)
        normalized_target_id = optional_text(target_id)
        normalized_offset = int(offset)
        normalized_limit = int(limit)

        conditions: list[str] = []
        params: list[Any] = []
        if run_uuid is not None:
            conditions.append("fr.run_id = %s")
            params.append(run_uuid)
        if normalized_case_id is not None:
            conditions.append("ec.case_id = %s")
            params.append(normalized_case_id)
        if target_type_filter is not None:
            conditions.append("fr.target_type = %s")
            params.append(target_type_filter)
        if normalized_target_id is not None:
            conditions.append("fr.target_id = %s")
            params.append(normalized_target_id)

        sql = """
                SELECT fr.feedback_id, fr.created_at, fr.run_id, ec.case_id,
                       fr.target_type, fr.target_id, fr.feedback, fr.comment,
                       fr.reviewer, fr.source, fr.metadata
                FROM feedback_records fr
                LEFT JOIN evidence_cases ec ON ec.id = fr.case_pk
                """
        if conditions:
            sql += "\n                WHERE " + "\n                  AND ".join(conditions)
        sql += "\n                ORDER BY fr.created_at DESC\n                "
        with self._connection() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()

        records = []
        for row in rows:
            metadata = dict_value(row.get("metadata"))
            stored_target_type = str(row.get("target_type") or "case")
            api_target_type = api_feedback_target_type(stored_target_type)
            stored_target_id = str(row.get("target_id") or "")
            created_at = row.get("created_at")
            records.append(
                {
                    "feedback_id": str(row.get("feedback_id")),
                    "created_at": created_at.isoformat()
                    if hasattr(created_at, "isoformat")
                    else str(created_at),
                    "run_id": str(row.get("run_id")) if row.get("run_id") is not None else None,
                    "case_id": optional_text(row.get("case_id")),
                    "target_type": api_target_type,
                    "target_id": stored_target_id,
                    "target_key": feedback_target_key(
                        stored_target_type,
                        stored_target_id,
                        metadata,
                    ),
                    "action": api_feedback_value(str(row.get("feedback") or "uncertain")),
                    "note": optional_text(row.get("comment")),
                    "reviewer": optional_text(row.get("reviewer")),
                    "source": optional_text(row.get("source")) or "unknown",
                    "metadata": metadata or None,
                }
            )

        paged_records = records[normalized_offset : normalized_offset + normalized_limit]
        return {
            "records": paged_records,
            "total_count": len(records),
            "returned_count": len(paged_records),
            "offset": normalized_offset,
            "limit": normalized_limit,
            "claim_boundary": (
                "candidate/plausible explanation only; not a verified root-cause label"
            ),
        }

    def _connection(self) -> Any:
        if self.connection_factory is not None:
            return self.connection_factory()
        if not self.config.dsn:
            raise RuntimeError(
                "Postgres runtime storage requires KGTRACE_POSTGRES_DSN or POSTGRES_* settings."
            )
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.config.dsn, row_factory=dict_row)

    def _upsert_evidence_case(self, connection: Any, evidence: Mapping[str, Any]) -> uuid.UUID:
        from psycopg.types.json import Jsonb

        case_id = str(evidence.get("case_id") or "unknown")
        dataset = valid_dataset(evidence.get("dataset"))
        row = connection.execute(
            """
            INSERT INTO evidence_cases
                (case_id, dataset, object_name, anomaly_type, source, timestamp,
                 evidence_payload, raw_evidence, normalized_evidence, human_feedback)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dataset, case_id) DO UPDATE SET
                object_name = EXCLUDED.object_name,
                anomaly_type = EXCLUDED.anomaly_type,
                source = EXCLUDED.source,
                timestamp = EXCLUDED.timestamp,
                evidence_payload = EXCLUDED.evidence_payload,
                raw_evidence = EXCLUDED.raw_evidence,
                normalized_evidence = EXCLUDED.normalized_evidence,
                human_feedback = EXCLUDED.human_feedback,
                updated_at = now()
            RETURNING id
            """,
            (
                case_id,
                dataset,
                evidence.get("object"),
                evidence.get("anomaly_type"),
                evidence.get("source"),
                evidence.get("timestamp"),
                Jsonb(dict(evidence)),
                Jsonb(dict_value(evidence.get("raw_evidence"))),
                Jsonb(dict_value(evidence.get("normalized_evidence"))),
                Jsonb(dict_value(evidence.get("human_feedback"))),
            ),
        ).fetchone()
        return cast(uuid.UUID, row["id"])

    def _replace_run_children(self, connection: Any, run_id: uuid.UUID) -> None:
        for table in (
            "linked_entities",
            "consistency_checks",
            "correction_candidates",
            "ranked_paths",
            "artifacts",
        ):
            connection.execute(f"DELETE FROM {table} WHERE run_id = %s", (run_id,))


def _insert_linked_entities(
    connection: Any,
    run_id: uuid.UUID,
    case_pk: uuid.UUID,
    links: Sequence[Mapping[str, Any]],
) -> None:
    from psycopg.types.json import Jsonb

    for index, link in enumerate(links):
        link_id = str(link.get("link_id") or f"{link.get('field', 'field')}_{index}")
        connection.execute(
            """
            INSERT INTO linked_entities
                (run_id, case_pk, link_id, field, mention, obs_id, facet,
                 selected_entity_id, selected_entity_name, selected_entity_scenario,
                 score, match_type, ambiguous, ambiguity_margin, candidates)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, case_pk, link_id) DO NOTHING
            """,
            (
                run_id,
                case_pk,
                link_id,
                str(link.get("field") or "unknown"),
                str(link.get("mention") or link.get("value") or ""),
                optional_text(link.get("obs_id")),
                optional_text(link.get("facet")),
                link.get("selected_entity_id"),
                optional_text(link.get("selected_entity_name")),
                link.get("selected_entity_scenario"),
                float_value(link.get("score")),
                str(link.get("match_type") or "unknown"),
                bool(link.get("ambiguous", False)),
                nullable_float(link.get("ambiguity_margin")),
                Jsonb(list_value(link.get("candidates"))),
            ),
        )


def _insert_consistency_check(
    connection: Any,
    run_id: uuid.UUID,
    case_pk: uuid.UUID,
    entry: Mapping[str, Any],
) -> None:
    from psycopg.types.json import Jsonb

    score = entry.get("consistency_score")
    if score is None:
        return
    connection.execute(
        """
        INSERT INTO consistency_checks
            (run_id, case_pk, consistency_score, inconsistent_fields, checks)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            run_id,
            case_pk,
            float_value(score),
            [str(item) for item in list_value(entry.get("inconsistent_fields"))],
            Jsonb(list_value(entry.get("checks"))),
        ),
    )


def _insert_corrections(
    connection: Any,
    run_id: uuid.UUID,
    case_pk: uuid.UUID,
    candidates: Sequence[Mapping[str, Any]],
) -> None:
    from psycopg.types.json import Jsonb

    for index, candidate in enumerate(candidates):
        candidate_id = str(candidate.get("candidate_id") or f"candidate_{index}")
        connection.execute(
            """
            INSERT INTO correction_candidates
                (run_id, case_pk, candidate_id, field, original_value, suggested_value,
                 suggested_entity_id, score, reason, source_edges, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, case_pk, candidate_id) DO NOTHING
            """,
            (
                run_id,
                case_pk,
                candidate_id,
                str(candidate.get("field") or "unknown"),
                optional_text(candidate.get("original_value")),
                optional_text(candidate.get("suggested_value")),
                candidate.get("suggested_entity_id"),
                float_value(candidate.get("score")),
                candidate.get("reason"),
                Jsonb(list_value(candidate.get("source_edges"))),
                Jsonb(dict(candidate)),
            ),
        )


def _insert_paths(
    connection: Any,
    run_id: uuid.UUID,
    case_pk: uuid.UUID,
    paths: Sequence[Mapping[str, Any]],
) -> None:
    from psycopg.types.json import Jsonb

    for index, path in enumerate(paths):
        source_edges = list_value(path.get("source_edges"))
        edge_ids = [
            str(edge.get("edge_id"))
            for edge in source_edges
            if isinstance(edge, Mapping) and edge.get("edge_id")
        ]
        path_id = str(path.get("path_id") or f"path_{index}")
        connection.execute(
            """
            INSERT INTO ranked_paths
                (run_id, case_pk, path_id, rank, source_entity_id, target_entity_id,
                 node_ids, relation_ids, score, confidence, evidence_match,
                 source_edge_ids, supporting_evidence, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, case_pk, path_id) DO NOTHING
            """,
            (
                run_id,
                case_pk,
                path_id,
                int(path.get("rank") or index + 1),
                path.get("source_entity_id"),
                path.get("target_entity_id"),
                [str(item) for item in list_value(path.get("nodes"))],
                [str(item) for item in list_value(path.get("relations"))],
                float_value(path.get("score")),
                nullable_float(path.get("confidence")),
                nullable_float(path.get("evidence_match")),
                edge_ids,
                Jsonb(list_value(path.get("supporting_evidence"))),
                Jsonb(dict(path)),
            ),
        )


def _insert_artifacts(
    connection: Any,
    run_id: uuid.UUID,
    case_pk: uuid.UUID | None,
    detail: Any,
) -> None:
    from psycopg.types.json import Jsonb

    dataset = valid_dataset(detail.run.dataset)
    for key, uri in detail.artifacts.items():
        connection.execute(
            """
            INSERT INTO artifacts
                (dataset, case_pk, run_id, artifact_type, uri, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (dataset, case_pk, run_id, str(key), str(uri), Jsonb({"key": key})),
        )
    for item in detail.visual_evidence:
        preview_path = item.get("preview_path")
        if not preview_path:
            continue
        connection.execute(
            """
            INSERT INTO artifacts
                (dataset, case_pk, run_id, artifact_type, uri, media_type, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                valid_dataset(item.get("dataset")),
                case_pk,
                run_id,
                "visual_evidence",
                str(preview_path),
                "image/png",
                Jsonb({"visual_evidence": item}),
            ),
        )
