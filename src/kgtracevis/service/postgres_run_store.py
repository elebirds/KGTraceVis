"""Postgres-backed runtime storage for dashboard analysis runs."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from kgtracevis.service.postgres import PostgresConfig, resolve_postgres_config

VALID_DATASETS = {"mvtec", "tep", "wafer"}
DEFAULT_CLAIM_BOUNDARY = (
    "candidate/plausible explanation only; not a verified root-cause label"
)


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
        from kgtracevis.service.runs import RunDetail

        self.save_run(RunDetail.model_validate(detail))

    def list_runs(self) -> list[Any]:
        """Return persisted run summaries, newest first."""
        from kgtracevis.service.runs import RunSummary

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
        return [RunSummary.model_validate(_run_summary_payload(row)) for row in rows]

    def get_run_detail(self, run_id: str) -> Any:
        """Load one run detail reconstructed from normalized runtime tables."""
        from kgtracevis.service.runs import RunDetail

        run_uuid = _parse_run_uuid(run_id)
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
                SELECT case_pk, link_id, field, mention, selected_entity_id,
                       selected_entity_scenario, score, match_type, ambiguous, candidates
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

        payload = _detail_payload(
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
        run_uuid = _parse_run_uuid(run_id)
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
        run_id = _parse_run_uuid(detail.run.run_id)
        entries = _case_entries(detail)
        dataset = _run_dataset(detail, entries)
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
            request = _FeedbackRecordAdapter(request)
        run_uuid = _parse_run_uuid(request.run_id) if request.run_id else None
        target_type = _feedback_target_type(request.target_type)
        feedback = _feedback_value(request.review_action())
        note = request.review_note()
        target_id = request.target_id or request.case_id or request.run_id or request.target_type

        with self._connection() as connection:
            context = _feedback_context(connection, run_uuid, request.case_id)
            from psycopg.types.json import Jsonb

            row = connection.execute(
                """
                INSERT INTO feedback_records
                    (dataset, run_id, case_pk, target_type, target_id, feedback,
                     corrected_value, comment, reviewer)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING feedback_id, created_at
                """,
                (
                    context["dataset"],
                    run_uuid,
                    context.get("case_pk"),
                    target_type,
                    target_id,
                    feedback,
                    Jsonb(request.metadata.get("corrected_value"))
                    if isinstance(request.metadata, dict)
                    else None,
                    note,
                    request.reviewer,
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
        }
        return {"status": "recorded", "record": record}

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
        dataset = _valid_dataset(evidence.get("dataset"))
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
                Jsonb(_dict_value(evidence.get("raw_evidence"))),
                Jsonb(_dict_value(evidence.get("normalized_evidence"))),
                Jsonb(_dict_value(evidence.get("human_feedback"))),
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
                (run_id, case_pk, link_id, field, mention, selected_entity_id,
                 selected_entity_scenario, score, match_type, ambiguous, candidates)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, case_pk, link_id) DO NOTHING
            """,
            (
                run_id,
                case_pk,
                link_id,
                str(link.get("field") or "unknown"),
                str(link.get("mention") or link.get("value") or ""),
                link.get("selected_entity_id"),
                link.get("selected_entity_scenario"),
                _float_value(link.get("score")),
                str(link.get("match_type") or "unknown"),
                bool(link.get("ambiguous", False)),
                Jsonb(_list_value(link.get("candidates"))),
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
            _float_value(score),
            [str(item) for item in _list_value(entry.get("inconsistent_fields"))],
            Jsonb(_list_value(entry.get("checks"))),
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
                _optional_text(candidate.get("original_value")),
                _optional_text(candidate.get("suggested_value")),
                candidate.get("suggested_entity_id"),
                _float_value(candidate.get("score")),
                candidate.get("reason"),
                Jsonb(_list_value(candidate.get("source_edges"))),
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
        source_edges = _list_value(path.get("source_edges"))
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
                [str(item) for item in _list_value(path.get("nodes"))],
                [str(item) for item in _list_value(path.get("relations"))],
                _float_value(path.get("score")),
                _nullable_float(path.get("confidence")),
                _nullable_float(path.get("evidence_match")),
                edge_ids,
                Jsonb(_list_value(path.get("supporting_evidence"))),
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

    dataset = _valid_dataset(detail.run.dataset)
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
                _valid_dataset(item.get("dataset")),
                case_pk,
                run_id,
                "visual_evidence",
                str(preview_path),
                "image/png",
                Jsonb({"visual_evidence": item}),
            ),
        )


def _detail_payload(
    *,
    run_row: Mapping[str, Any],
    case_rows: Sequence[Mapping[str, Any]],
    linked_rows: Sequence[Mapping[str, Any]],
    consistency_rows: Sequence[Mapping[str, Any]],
    correction_rows: Sequence[Mapping[str, Any]],
    path_rows: Sequence[Mapping[str, Any]],
    artifact_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    from kgtracevis.service.runs import (
        _path_graph_from_paths,
        _review_targets,
        _unique_source_edges,
    )

    links_by_case = _rows_by_case(linked_rows, _link_payload)
    consistency_by_case = _consistency_by_case(consistency_rows)
    corrections_by_case = _rows_by_case(correction_rows, _correction_payload)
    paths_by_case = _rows_by_case(path_rows, _path_payload)

    cases: list[dict[str, Any]] = []
    aggregate_links: list[dict[str, Any]] = []
    aggregate_corrections: list[dict[str, Any]] = []
    aggregate_paths: list[dict[str, Any]] = []
    first_evidence: dict[str, Any] | None = None
    first_analysis: dict[str, Any] | None = None
    first_summary: dict[str, Any] | None = None

    for row in case_rows:
        case_pk = str(row["case_pk"])
        evidence = _dict_value(row.get("evidence_payload"))
        if not evidence:
            evidence = _evidence_from_case_row(row)
        links = links_by_case.get(case_pk, [])
        corrections = corrections_by_case.get(case_pk, [])
        paths = paths_by_case.get(case_pk, [])
        consistency = consistency_by_case.get(case_pk, {})
        source_edges = _unique_source_edges(paths)
        analysis = {
            "case_id": evidence.get("case_id") or row.get("case_id"),
            "linked_entities": links,
            "consistency_score": consistency.get("consistency_score"),
            "inconsistent_fields": consistency.get("inconsistent_fields", []),
            "correction_candidates": corrections,
            "top_k_paths": paths,
            "human_feedback": evidence.get("human_feedback"),
        }
        case_payload = {
            "case_id": evidence.get("case_id") or row.get("case_id"),
            "dataset": evidence.get("dataset") or row.get("dataset"),
            "generated_evidence": evidence,
            "generated_evidence_path": row.get("generated_evidence_path"),
            "linked_entities": links,
            "consistency_score": analysis["consistency_score"],
            "inconsistent_fields": analysis["inconsistent_fields"],
            "correction_candidates": corrections,
            "top_k_paths": paths,
            "source_edge_provenance": source_edges,
            "path_graph": _path_graph_from_paths(paths),
            "review_targets": _review_targets(
                linked_entities=links,
                correction_candidates=corrections,
                top_k_paths=paths,
                source_edges=source_edges,
            ),
        }
        cases.append(case_payload)
        aggregate_links.extend(links)
        aggregate_corrections.extend(corrections)
        aggregate_paths.extend(paths)
        if first_evidence is None:
            first_evidence = evidence
            first_analysis = analysis
            first_summary = _compact_evidence_summary(evidence)

    source_edges = _unique_source_edges(aggregate_paths)
    parameters = _dict_value(run_row.get("parameters"))
    artifacts, visual_evidence = _artifacts_payload(artifact_rows)
    evidence_with_analysis = None
    if first_evidence is not None and first_analysis is not None:
        evidence_with_analysis = dict(first_evidence)
        evidence_with_analysis["kg_analysis"] = {
            "linked_entities": first_analysis["linked_entities"],
            "consistency_score": first_analysis["consistency_score"],
            "inconsistent_fields": first_analysis["inconsistent_fields"],
            "correction_candidates": first_analysis["correction_candidates"],
            "top_k_paths": first_analysis["top_k_paths"],
        }

    return {
        "run": _run_summary_payload(run_row),
        "workflow_steps": _list_value(parameters.get("workflow_steps")),
        "claim_boundary": run_row.get("claim_boundary") or DEFAULT_CLAIM_BOUNDARY,
        "evidence": first_evidence,
        "evidence_summary": first_summary,
        "evidence_with_analysis": evidence_with_analysis,
        "analysis": first_analysis,
        "summary": _dict_value(run_row.get("summary")) or None,
        "cases": cases,
        "linked_entities": aggregate_links,
        "correction_candidates": aggregate_corrections,
        "top_k_paths": aggregate_paths,
        "path_graph": _path_graph_from_paths(aggregate_paths),
        "source_edge_provenance": source_edges,
        "review_targets": _review_targets(
            linked_entities=aggregate_links,
            correction_candidates=aggregate_corrections,
            top_k_paths=aggregate_paths,
            source_edges=source_edges,
        ),
        "artifacts": artifacts,
        "visual_evidence": visual_evidence,
    }


def _run_summary_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    created_at = row["started_at"]
    created_at_text = (
        created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    )
    return {
        "run_id": str(row["run_id"]),
        "created_at": created_at_text,
        "mode": row["mode"],
        "source_filename": row["source_filename"],
        "top_k": row["top_k"],
        "run_dir": row.get("run_dir") or "",
        "status": row.get("status") or "completed",
        "dataset": row.get("dataset"),
        "case_count": int(row.get("case_count") or 0),
        "evidence_count": int(row.get("evidence_count") or 0),
        "label": row.get("label") or "Analysis run",
        "model_preset": row.get("model_preset"),
        "model_backend": row.get("model_backend"),
    }


def _case_entries(detail: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if detail.cases:
        for case in detail.cases:
            evidence = _case_evidence_payload(case)
            if evidence is None:
                continue
            entries.append(
                {
                    "case_id": str(evidence.get("case_id") or case.get("case_id") or "unknown"),
                    "dataset": _valid_dataset(evidence.get("dataset") or case.get("dataset")),
                    "evidence": evidence,
                    "evidence_path": case.get("generated_evidence_path")
                    or case.get("evidence_path"),
                    "adapter_name": case.get("adapter") or case.get("adapter_name"),
                    "linked_entities": _list_of_dicts(case.get("linked_entities")),
                    "consistency_score": case.get("consistency_score"),
                    "inconsistent_fields": _list_value(case.get("inconsistent_fields")),
                    "checks": _list_value(case.get("checks")),
                    "correction_candidates": _list_of_dicts(case.get("correction_candidates")),
                    "top_k_paths": _list_of_dicts(case.get("top_k_paths")),
                }
            )
    if not entries and detail.evidence:
        evidence = dict(detail.evidence)
        analysis = _dict_value(detail.analysis)
        entries.append(
            {
                "case_id": str(evidence.get("case_id") or "unknown"),
                "dataset": _valid_dataset(evidence.get("dataset")),
                "evidence": evidence,
                "evidence_path": detail.artifacts.get("input_path"),
                "adapter_name": evidence.get("source"),
                "linked_entities": _list_of_dicts(analysis.get("linked_entities")),
                "consistency_score": analysis.get("consistency_score"),
                "inconsistent_fields": _list_value(analysis.get("inconsistent_fields")),
                "checks": _list_value(analysis.get("checks")),
                "correction_candidates": _list_of_dicts(analysis.get("correction_candidates")),
                "top_k_paths": _list_of_dicts(analysis.get("top_k_paths")),
            }
        )
    return entries


def _case_evidence_payload(case: Mapping[str, Any]) -> dict[str, Any] | None:
    for key in ("evidence", "generated_evidence"):
        value = case.get(key)
        if isinstance(value, Mapping):
            payload = dict(value)
            payload.setdefault("case_id", case.get("case_id", "unknown"))
            payload.setdefault("dataset", _valid_dataset(case.get("dataset")))
            payload.setdefault("raw_evidence", {})
            payload.setdefault("normalized_evidence", {})
            payload.setdefault("human_feedback", {})
            return payload
    if case.get("case_id") and case.get("dataset"):
        return {
            "case_id": case["case_id"],
            "dataset": _valid_dataset(case["dataset"]),
            "source": case.get("source", "upload"),
            "object": case.get("object", "unknown"),
            "anomaly_type": case.get("anomaly_type", "unknown"),
            "location": case.get("location"),
            "morphology": case.get("morphology"),
            "severity": case.get("severity"),
            "confidence": case.get("confidence"),
            "timestamp": case.get("timestamp"),
            "raw_evidence": {},
            "normalized_evidence": {},
            "human_feedback": {},
        }
    return None


def _run_dataset(detail: Any, entries: Sequence[Mapping[str, Any]]) -> str:
    if detail.run.dataset in VALID_DATASETS:
        return str(detail.run.dataset)
    for entry in entries:
        dataset = entry.get("dataset")
        if dataset in VALID_DATASETS:
            return str(dataset)
    return "mvtec"


def _parse_run_uuid(run_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(run_id))
    except ValueError as exc:
        raise ValueError(f"run_id must be a UUID: {run_id}") from exc


def _valid_dataset(value: object) -> str:
    dataset = str(value or "").lower()
    if dataset in VALID_DATASETS:
        return dataset
    return "mvtec"


def _rows_by_case(
    rows: Sequence[Mapping[str, Any]],
    transform: Any,
) -> dict[str, list[dict[str, Any]]]:
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("case_pk"))
        by_case.setdefault(key, []).append(transform(row))
    return by_case


def _consistency_by_case(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    by_case: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_case[str(row.get("case_pk"))] = {
            "consistency_score": row.get("consistency_score"),
            "inconsistent_fields": list(row.get("inconsistent_fields") or []),
            "checks": _list_value(row.get("checks")),
        }
    return by_case


def _link_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "link_id": row.get("link_id"),
        "field": row.get("field"),
        "mention": row.get("mention"),
        "selected_entity_id": row.get("selected_entity_id"),
        "selected_entity_scenario": row.get("selected_entity_scenario"),
        "score": row.get("score"),
        "match_type": row.get("match_type"),
        "ambiguous": row.get("ambiguous"),
        "candidates": _list_value(row.get("candidates")),
    }


def _correction_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = _dict_value(row.get("payload"))
    if payload:
        return payload
    return {
        "candidate_id": row.get("candidate_id"),
        "field": row.get("field"),
        "original_value": row.get("original_value"),
        "suggested_value": row.get("suggested_value"),
        "suggested_entity_id": row.get("suggested_entity_id"),
        "score": row.get("score"),
        "reason": row.get("reason"),
        "source_edges": _list_value(row.get("source_edges")),
    }


def _path_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = _dict_value(row.get("payload"))
    if payload:
        return payload
    return {
        "path_id": row.get("path_id"),
        "rank": row.get("rank"),
        "source_entity_id": row.get("source_entity_id"),
        "target_entity_id": row.get("target_entity_id"),
        "nodes": list(row.get("node_ids") or []),
        "relations": list(row.get("relation_ids") or []),
        "score": row.get("score"),
        "confidence": row.get("confidence"),
        "evidence_match": row.get("evidence_match"),
        "supporting_evidence": _list_value(row.get("supporting_evidence")),
        "source_edges": [],
    }


def _artifacts_payload(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    artifacts: dict[str, str] = {}
    visual_evidence: list[dict[str, Any]] = []
    for row in rows:
        metadata = _dict_value(row.get("metadata"))
        key = metadata.get("key")
        if key:
            artifacts[str(key)] = str(row.get("uri"))
        item = metadata.get("visual_evidence")
        if isinstance(item, Mapping):
            visual_evidence.append(dict(item))
    return artifacts, visual_evidence


def _feedback_context(
    connection: Any,
    run_uuid: uuid.UUID | None,
    case_id: str | None,
) -> dict[str, Any]:
    if run_uuid is not None:
        if case_id:
            row = connection.execute(
                """
                SELECT c.dataset, c.id AS case_pk
                FROM run_evidence_cases rc
                JOIN evidence_cases c ON c.id = rc.case_pk
                WHERE rc.run_id = %s
                  AND c.case_id = %s
                LIMIT 1
                """,
                (run_uuid, case_id),
            ).fetchone()
            if row is not None:
                return {"dataset": row["dataset"], "case_pk": row["case_pk"]}
        row = connection.execute(
            "SELECT dataset, case_pk FROM analysis_runs WHERE run_id = %s",
            (run_uuid,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown run session: {run_uuid}")
        return {"dataset": row["dataset"], "case_pk": row.get("case_pk")}
    if case_id:
        row = connection.execute(
            """
            SELECT id AS case_pk, dataset
            FROM evidence_cases
            WHERE case_id = %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (case_id,),
        ).fetchone()
        if row is not None:
            return {"dataset": row["dataset"], "case_pk": row["case_pk"]}
    return {"dataset": "mvtec", "case_pk": None}


class _FeedbackRecordAdapter:
    """Adapter for JSON-compatible feedback payloads used in unit tests."""

    def __init__(self, record: Mapping[str, Any]) -> None:
        self._record = dict(record)
        self.run_id = self._record.get("run_id")
        self.case_id = self._record.get("case_id")
        self.target_type = str(self._record.get("target_type") or "case")
        self.target_id = self._record.get("target_id")
        self.reviewer = self._record.get("reviewer")
        self.metadata = _dict_value(self._record.get("metadata"))

    def review_action(self) -> str:
        """Return the normalized feedback action."""
        return str(
            self._record.get("action")
            or self._record.get("decision")
            or self._record.get("feedback")
            or "uncertain"
        )

    def review_note(self) -> str | None:
        """Return the submitted feedback note/comment."""
        note = self._record.get("note")
        if note is not None:
            return str(note)
        comment = self._record.get("comment")
        return str(comment) if comment is not None else None

    def model_dump(self, *, mode: str = "json") -> dict[str, Any]:
        """Return the original JSON-compatible record."""
        return dict(self._record)


def _feedback_target_type(value: str) -> str:
    return {
        "path": "ranked_path",
        "edge": "kg_edge",
        "correction": "correction_candidate",
        "link": "entity_link",
        "entity_link": "entity_link",
        "case": "case",
    }.get(value, value)


def _feedback_value(value: str) -> str:
    return {"needs_review": "uncertain"}.get(value, value)


def _evidence_from_case_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": row.get("case_id"),
        "dataset": row.get("dataset"),
        "raw_evidence": _dict_value(row.get("raw_evidence")),
        "normalized_evidence": _dict_value(row.get("normalized_evidence")),
        "human_feedback": _dict_value(row.get("human_feedback")),
    }


def _compact_evidence_summary(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": evidence.get("case_id"),
        "dataset": evidence.get("dataset"),
        "source": evidence.get("source"),
        "object": evidence.get("object"),
        "anomaly_type": evidence.get("anomaly_type"),
        "location": evidence.get("location"),
        "morphology": evidence.get("morphology"),
        "severity": evidence.get("severity"),
        "confidence": evidence.get("confidence"),
        "observation_count": len(_list_value(evidence.get("observations"))),
    }


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, str) else []


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in _list_value(value) if isinstance(item, Mapping)]


def _float_value(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _nullable_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)
