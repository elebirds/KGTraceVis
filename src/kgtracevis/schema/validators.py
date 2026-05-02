"""Validation helpers for project data files."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.schema.evidence_schema import Evidence

CANONICAL_REASONING_FACETS = {
    "object",
    "anomaly_type",
    "location",
    "morphology",
    "variable",
    "log_event",
}


def load_evidence_json(
    path: str | Path,
    *,
    require_canonical_observations: bool = False,
) -> Evidence:
    """Load and validate one evidence JSON file."""
    evidence = Evidence.model_validate_json(Path(path).read_text(encoding="utf-8"))
    if require_canonical_observations:
        validate_canonical_observations(evidence)
    return evidence


def validate_canonical_observations(evidence: Evidence) -> None:
    """Raise when observed reasoning fields are missing canonical observations."""
    missing_facets = missing_canonical_observation_facets(evidence)
    if missing_facets:
        joined = ", ".join(missing_facets)
        raise ValueError(
            "evidence payload relies on deprecated legacy reasoning fields; "
            f"add observations for: {joined}"
        )


def missing_canonical_observation_facets(evidence: Evidence) -> list[str]:
    """Return observed facets still represented only by deprecated fields."""
    observed_facets = {
        observation.facet
        for observation in evidence.observations
        if observation.facet in CANONICAL_REASONING_FACETS and observation.name.strip()
    }
    required_facets = _present_reasoning_facets(evidence)
    return sorted(required_facets - observed_facets)


def legacy_compatibility_warnings(evidence: Evidence) -> list[str]:
    """Return deprecation warnings for payloads that rely on legacy fields."""
    missing_facets = missing_canonical_observation_facets(evidence)
    if not missing_facets:
        return []
    joined = ", ".join(missing_facets)
    return [
        "deprecated legacy reasoning fields are compatibility-only; "
        f"add canonical observations for: {joined}"
    ]


def _present_reasoning_facets(evidence: Evidence) -> set[str]:
    facets = {"object", "anomaly_type"}
    if evidence.location:
        facets.add("location")
    if evidence.morphology:
        facets.add("morphology")
    if evidence.raw_evidence.variables:
        facets.add("variable")
    if evidence.raw_evidence.log_events:
        facets.add("log_event")
    return facets
