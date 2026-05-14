"""Bridge TEP RCA artifacts into the unified root-cause ranking contract."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from kgtracevis.core.result import RankedRootCause, RcaRankingResult
from kgtracevis.schema.evidence_schema import Evidence

SCENARIO_ID_KEYS = ("scenario_id", "case_id", "scenario", "scenario_key")
FAULT_NUMBER_KEYS = ("fault_number", "fault_id")
SIMULATION_RUN_KEYS = ("simulation_run", "simulation_id", "run_id")


class TepRcaArtifactConfig(BaseModel):
    """Configurable paths for bridge-mode TEP RCA artifacts."""

    model_config = ConfigDict(extra="forbid")

    artifact_dir: Path | None = None
    ranking_path: Path | None = None
    contributions_path: Path | None = None
    source_name: str = "tep_rca_artifact"
    allow_global_rankings: bool = False


class TepScenarioSelector(BaseModel):
    """Deterministic keys used to match TEP evidence to RCA artifacts."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    scenario_ids: tuple[str, ...]
    fault_numbers: tuple[int, ...] = ()
    simulation_runs: tuple[int, ...] = ()


class TepRcaArtifactProvider:
    """Read small TEP RCA artifacts and emit unified root-cause rankings."""

    def __init__(self, config: TepRcaArtifactConfig | str | Path) -> None:
        """Create a provider from an artifact directory or explicit config."""
        if isinstance(config, TepRcaArtifactConfig):
            self.config = config
        else:
            self.config = TepRcaArtifactConfig(artifact_dir=Path(config))
        self.ranking_path = _resolve_ranking_path(self.config)
        self.contributions_path = _resolve_contributions_path(self.config)
        self._ranking_rows = _load_rows(self.ranking_path) if self.ranking_path else []
        self._contributions_by_scenario = (
            _load_contributions(self.contributions_path) if self.contributions_path else {}
        )

    def rank_root_causes(
        self,
        evidence: Evidence,
        *,
        top_k: int = 5,
        top_k_paths: list[dict[str, Any]] | None = None,
    ) -> list[RankedRootCause]:
        """Return artifact-backed RCA rankings for TEP evidence."""
        del top_k_paths
        if evidence.dataset != "tep" or not self._ranking_rows:
            return []
        selector = tep_scenario_selector(evidence)
        rows = [
            row
            for row in self._ranking_rows
            if _row_matches_selector(
                row,
                selector,
                allow_global_rankings=self.config.allow_global_rankings,
            )
        ]
        rows = _sort_ranking_rows(rows)
        results: list[RankedRootCause] = []
        for index, row in enumerate(rows[:top_k], start=1):
            candidate_id = _candidate_id(row)
            contribution = _matching_contribution(
                row,
                selector,
                self._contributions_by_scenario,
            )
            results.append(
                _root_cause_from_row(
                    row,
                    evidence=evidence,
                    rank=_optional_int(row.get("rank")) or index,
                    candidate_id=candidate_id,
                    contribution=contribution,
                    config=self.config,
                    selector=selector,
                    ranking_path=self.ranking_path,
                    contributions_path=self.contributions_path,
                )
            )
        results.sort(key=lambda item: (item.rank, -item.score, item.candidate_id))
        return [
            item.model_copy(update={"rank": index})
            for index, item in enumerate(results, start=1)
        ]


def run_tep_rca_bridge(
    evidence: Evidence,
    config: TepRcaArtifactConfig | str | Path,
    *,
    top_k: int = 5,
) -> RcaRankingResult:
    """Run bridge-mode TEP RCA artifact mapping for one evidence object."""
    provider = TepRcaArtifactProvider(config)
    ranked = provider.rank_root_causes(evidence, top_k=top_k)
    selector = tep_scenario_selector(evidence)
    return RcaRankingResult(
        case_id=evidence.case_id,
        ranked_root_causes=ranked,
        scoring_method="tep_artifact_bridge",
        metadata={
            "scenario_selector": selector.model_dump(mode="json"),
            "ranking_path": str(provider.ranking_path) if provider.ranking_path else None,
            "contributions_path": (
                str(provider.contributions_path) if provider.contributions_path else None
            ),
        },
    )


def _resolve_ranking_path(config: TepRcaArtifactConfig) -> Path | None:
    if config.ranking_path is not None:
        return _existing_path(config.ranking_path)
    if config.artifact_dir is None:
        return None
    candidates = [
        config.artifact_dir / "root_cause_rankings.jsonl",
        config.artifact_dir / "root_kgd_rankings.jsonl",
        config.artifact_dir / "baseline_root_scores.csv",
        config.artifact_dir / "outputs" / "rca" / "baseline_root_scores.csv",
        config.artifact_dir / "data" / "processed" / "models" / "root_cause_rankings.jsonl",
        config.artifact_dir / "data" / "processed" / "models" / "root_kgd_rankings.jsonl",
    ]
    return next((path for path in candidates if path.exists()), None)


def _resolve_contributions_path(config: TepRcaArtifactConfig) -> Path | None:
    if config.contributions_path is not None:
        return _existing_path(config.contributions_path)
    if config.artifact_dir is None:
        return None
    candidates = [
        config.artifact_dir / "rbc_contributions.jsonl",
        config.artifact_dir / "data" / "processed" / "rca" / "rbc_contributions.jsonl",
    ]
    return next((path for path in candidates if path.exists()), None)


def _existing_path(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"TEP RCA artifact path does not exist: {path}")
    return path


def _load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    payloads = _load_json_payloads(path)
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        rows.extend(_expand_ranking_payload(payload))
    return rows


def _load_contributions(path: Path) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]]
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    else:
        rows = [
            payload
            for payload in _load_json_payloads(path)
            if isinstance(payload, dict)
        ]
    by_scenario: dict[str, dict[str, Any]] = {}
    for row in rows:
        scenario_id = _scenario_id_from_row(row)
        if scenario_id:
            by_scenario.setdefault(scenario_id, row)
    return by_scenario


def _load_json_payloads(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        return payload if isinstance(payload, list) else [payload]
    payloads: list[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            payloads.append(json.loads(line))
    return payloads


def _expand_ranking_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    candidates = (
        payload.get("ranked_candidates")
        or payload.get("rankings")
        or payload.get("candidates")
    )
    if isinstance(candidates, list):
        rows: list[dict[str, Any]] = []
        scenario_context = {
            key: value
            for key, value in payload.items()
            if key not in {"ranked_candidates", "rankings", "candidates"}
        }
        for candidate in candidates:
            if isinstance(candidate, dict):
                rows.append({**scenario_context, **candidate})
        return rows
    return [payload]


def tep_scenario_selector(evidence: Evidence) -> TepScenarioSelector:
    """Build artifact matching keys from KGTraceVis TEP evidence."""
    scenario_ids = {evidence.case_id}
    fault_numbers: set[int] = set()
    simulation_runs: set[int] = set()
    extra = evidence.raw_evidence.extra
    for key in SCENARIO_ID_KEYS:
        scenario_ids.update(_text_values(extra.get(key)))
    for key in FAULT_NUMBER_KEYS:
        fault_numbers.update(_int_values(extra.get(key)))
    for key in SIMULATION_RUN_KEYS:
        simulation_runs.update(_int_values(extra.get(key)))
    for observation in evidence.observations:
        metadata = observation.metadata or {}
        for key in SCENARIO_ID_KEYS:
            scenario_ids.update(_text_values(metadata.get(key)))
        for key in FAULT_NUMBER_KEYS:
            fault_numbers.update(_int_values(metadata.get(key)))
        for key in SIMULATION_RUN_KEYS:
            simulation_runs.update(_int_values(metadata.get(key)))
        time_window = observation.time_window or {}
        for key in SCENARIO_ID_KEYS:
            scenario_ids.update(_text_values(time_window.get(key)))
        for key in SIMULATION_RUN_KEYS:
            simulation_runs.update(_int_values(time_window.get(key)))
    return TepScenarioSelector(
        case_id=evidence.case_id,
        scenario_ids=tuple(sorted(scenario_ids)),
        fault_numbers=tuple(sorted(fault_numbers)),
        simulation_runs=tuple(sorted(simulation_runs)),
    )


def _row_matches_selector(
    row: dict[str, Any],
    selector: TepScenarioSelector,
    *,
    allow_global_rankings: bool,
) -> bool:
    scenario_id = _scenario_id_from_row(row)
    if scenario_id is not None and scenario_id in selector.scenario_ids:
        return True
    if _row_matches_fault_run(row, selector):
        return True
    return scenario_id is None and not _row_has_scenario_fields(row) and allow_global_rankings


def _scenario_id_from_row(row: dict[str, Any]) -> str | None:
    for key in SCENARIO_ID_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _row_matches_fault_run(row: dict[str, Any], selector: TepScenarioSelector) -> bool:
    row_fault_numbers = _row_int_values(row, FAULT_NUMBER_KEYS)
    row_simulation_runs = _row_int_values(row, SIMULATION_RUN_KEYS)
    if not row_fault_numbers:
        return False
    if not set(selector.fault_numbers).isdisjoint(row_fault_numbers):
        if not row_simulation_runs:
            return True
        return not set(selector.simulation_runs).isdisjoint(row_simulation_runs)
    return False


def _row_has_scenario_fields(row: dict[str, Any]) -> bool:
    keys = (*SCENARIO_ID_KEYS, *FAULT_NUMBER_KEYS, *SIMULATION_RUN_KEYS)
    return any(row.get(key) not in (None, "") for key in keys)


def _row_int_values(row: dict[str, Any], keys: tuple[str, ...]) -> set[int]:
    values: set[int] = set()
    for key in keys:
        values.update(_int_values(row.get(key)))
    return values


def _sort_ranking_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            _optional_int(row.get("rank")) or 1_000_000,
            -_score_from_row(row),
            _candidate_id(row),
        ),
    )


def _root_cause_from_row(
    row: dict[str, Any],
    *,
    evidence: Evidence,
    rank: int,
    candidate_id: str,
    contribution: dict[str, Any] | None,
    config: TepRcaArtifactConfig,
    selector: TepScenarioSelector,
    ranking_path: Path | None,
    contributions_path: Path | None,
) -> RankedRootCause:
    score = _score_from_row(row)
    confidence = _confidence_from_row(row, score)
    top_affected_variables = _list_from_field(
        row.get("top_affected_variables")
        or row.get("top_variables")
        or (contribution or {}).get("top_variables")
        or (contribution or {}).get("top_channels")
    )
    supporting_paths = _support_paths_from_field(
        row.get("top_support_paths")
        or row.get("support_paths")
        or row.get("supporting_paths")
        or row.get("explanation_paths")
    )
    supporting_edges = _list_of_dicts(row.get("supporting_edges") or row.get("source_edges"))
    supporting_evidence = [
        {
            "evidence_id": f"{evidence.case_id}_{candidate_id}_ranking_row",
            "source": config.source_name,
            "artifact_path": str(ranking_path) if ranking_path else None,
            "payload": dict(row),
        }
    ]
    if contribution is not None:
        supporting_evidence.append(
            {
                "evidence_id": f"{evidence.case_id}_{candidate_id}_contributions",
                "source": config.source_name,
                "artifact_path": str(contributions_path) if contributions_path else None,
                "payload": dict(contribution),
            }
        )
    return RankedRootCause(
        ranking_id=_stable_ranking_id(evidence.case_id, candidate_id),
        rank=rank,
        candidate_id=candidate_id,
        candidate_name=str(
            row.get("candidate_name")
            or row.get("root_cause_name")
            or row.get("name")
            or candidate_id
        ),
        candidate_label=_optional_str(row.get("candidate_type") or row.get("candidate_label")),
        candidate_role=_optional_str(row.get("candidate_role") or row.get("role")),
        score=round(score, 4),
        confidence=confidence,
        evidence_match=_optional_float(row.get("evidence_match")),
        explanation_paths=supporting_paths,
        supporting_edges=supporting_edges,
        supporting_evidence=supporting_evidence,
        scoring_method="tep_artifact_bridge",
        scoring_details={
            "scenario_selector": selector.model_dump(mode="json"),
            "scenario_id": _scenario_id_from_row(row),
            "fault_number": row.get("fault_number") or (contribution or {}).get("fault_number"),
            "simulation_run": row.get("simulation_run")
            or (contribution or {}).get("simulation_run"),
            "root_score": _optional_float(row.get("root_score")),
            "ranking_score": _optional_float(row.get("ranking_score")),
            "structural_ranking_score": _optional_float(
                row.get("structural_ranking_score")
            ),
            "ranking_adjustment": _optional_float(row.get("ranking_adjustment")),
            "top_affected_variables": top_affected_variables,
            "artifact_paths": {
                "ranking": str(ranking_path) if ranking_path else None,
                "contributions": str(contributions_path) if contributions_path else None,
            },
        },
        source=config.source_name,
        review_status="auto",
    )


def _candidate_id(row: dict[str, Any]) -> str:
    for key in ("candidate_id", "candidate_entity_id", "root_cause_id", "entity_id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    name = str(row.get("candidate_name") or row.get("root_cause_name") or "candidate")
    token = "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", name) if part)
    return token or f"Candidate{hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]}"


def _score_from_row(row: dict[str, Any]) -> float:
    for key in ("ranking_score", "score", "root_score", "structural_ranking_score"):
        value = _optional_float(row.get(key))
        if value is not None:
            return value
    return 0.0


def _confidence_from_row(row: dict[str, Any], score: float) -> float | None:
    for key in ("confidence", "root_confidence"):
        value = _optional_float(row.get(key))
        if value is not None:
            return max(0.0, min(1.0, value))
    root_score = _optional_float(row.get("root_score"))
    if root_score is not None:
        return max(0.0, min(1.0, root_score))
    if 0.0 <= score <= 1.0:
        return score
    return None


def _matching_contribution(
    row: dict[str, Any],
    selector: TepScenarioSelector,
    contributions_by_scenario: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    scenario_id = _scenario_id_from_row(row)
    if scenario_id and scenario_id in contributions_by_scenario:
        return contributions_by_scenario[scenario_id]
    for key in selector.scenario_ids:
        if key in contributions_by_scenario:
            return contributions_by_scenario[key]
    for contribution in contributions_by_scenario.values():
        if _row_matches_fault_run(contribution, selector):
            return contribution
    return None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _text_values(value: Any) -> set[str]:
    value = _decoded_value(value)
    if value in (None, ""):
        return set()
    if isinstance(value, list | tuple | set):
        return {text for item in value for text in _text_values(item)}
    return {str(value)}


def _int_values(value: Any) -> set[int]:
    value = _decoded_value(value)
    if value in (None, ""):
        return set()
    if isinstance(value, list | tuple | set):
        return {number for item in value for number in _int_values(item)}
    try:
        return {int(float(str(value)))}
    except (TypeError, ValueError):
        return set()


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    value = _decoded_value(value)
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _support_paths_from_field(value: Any) -> list[dict[str, Any]]:
    value = _decoded_value(value)
    if not isinstance(value, list):
        return []
    paths: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            paths.append(dict(item))
            continue
        if isinstance(item, list):
            paths.append(
                {
                    "path_id": f"tep_support_path_{index}",
                    "nodes": [str(node_id) for node_id in item],
                    "relations": [],
                }
            )
    return paths


def _list_from_field(value: Any) -> list[Any]:
    value = _decoded_value(value)
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


def _decoded_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    if stripped[0] in "[{":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value


def _stable_ranking_id(case_id: str, candidate_id: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "_", candidate_id).strip("_").lower()
    return f"rca_{case_id}_{token or 'candidate'}"
