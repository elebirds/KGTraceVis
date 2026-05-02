"""Deterministic field-level noise injection."""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from collections.abc import Callable
from math import ceil

from kgtracevis.schema.evidence_schema import Evidence

NoiseType = str

SUPPORTED_NOISE_TYPES = {
    "anomaly_type_replacement",
    "location_replacement",
    "morphology_replacement",
    "variable_deletion",
    "variable_name_perturbation",
    "log_event_deletion",
    "synonym_substitution",
    "contradiction_injection",
}

_ANOMALY_REPLACEMENTS = {
    "mvtec": ("color", "crack", "contamination", "squeeze"),
    "tep": ("unknown_process_fault",),
    "wafer": ("scratch", "process_fault"),
}
_LOCATION_REPLACEMENTS = {
    "mvtec": ("reactor", "wafer_surface"),
    "tep": ("wafer_surface", "feed disturbance"),
    "wafer": ("reactor", "surface"),
}
_MORPHOLOGY_REPLACEMENTS = {
    "mvtec": ("dense_particles", "surface"),
    "tep": ("linear", "dense_particles"),
    "wafer": ("linear", "wafer_surface"),
}
_SYNONYMS = {
    "scratch": "scratch defect",
    "surface": "outer surface",
    "linear": "line-shaped",
    "process_fault": "fault",
    "reactor": "reactor unit",
    "XMEAS_1": "xmeas1",
    "nearfull": "dense wafer contamination",
    "dense_particles": "dense particles",
    "wafer_surface": "wafer surface",
    "example_alarm": "example alarm",
}


def inject_noise(
    evidence: Evidence,
    noise_type: NoiseType,
    noise_level: float,
    *,
    seed: int = 42,
) -> Evidence:
    """Return a noisy copy of evidence with metadata in ``raw_evidence.extra``."""
    if noise_type not in SUPPORTED_NOISE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_NOISE_TYPES))
        raise ValueError(f"unsupported noise_type {noise_type!r}; expected one of: {supported}")
    if not 0 <= noise_level <= 1:
        raise ValueError("noise_level must be in [0, 1]")

    clean_reference = evidence.model_dump(mode="json")
    noisy = evidence.model_copy(deep=True)
    rng = _rng_for(evidence, noise_type, noise_level, seed)

    handlers: dict[NoiseType, Callable[[Evidence, random.Random, float], list[str]]] = {
        "anomaly_type_replacement": _replace_anomaly_type,
        "location_replacement": _replace_location,
        "morphology_replacement": _replace_morphology,
        "variable_deletion": _delete_variable,
        "variable_name_perturbation": _perturb_variable_name,
        "log_event_deletion": _delete_log_event,
        "synonym_substitution": _substitute_synonym,
        "contradiction_injection": _inject_contradiction,
    }
    corrupted_fields = handlers[noise_type](noisy, rng, noise_level)

    existing_extra = dict(noisy.raw_evidence.extra)
    existing_extra.update(
        {
            "is_noisy": bool(corrupted_fields),
            "noise_level": noise_level,
            "noise_type": noise_type,
            "corrupted_fields": corrupted_fields,
            "clean_reference": clean_reference,
        }
    )
    noisy.raw_evidence.extra = existing_extra
    return Evidence.model_validate(noisy.model_dump(mode="json"))


def _replace_anomaly_type(evidence: Evidence, rng: random.Random, _: float) -> list[str]:
    original = evidence.anomaly_type
    replacement = _replacement(
        original,
        _ANOMALY_REPLACEMENTS.get(evidence.dataset, ()),
        rng,
    )
    if replacement is None:
        return []
    evidence.anomaly_type = replacement
    _replace_observation_name(evidence, "anomaly_type", original, replacement)
    return ["anomaly_type"]


def _replace_location(evidence: Evidence, rng: random.Random, _: float) -> list[str]:
    original = evidence.location
    replacement = _replacement(
        original,
        _LOCATION_REPLACEMENTS.get(evidence.dataset, ()),
        rng,
    )
    if replacement is None:
        return []
    evidence.location = replacement
    _replace_observation_name(evidence, "location", original, replacement)
    return ["location"]


def _replace_morphology(evidence: Evidence, rng: random.Random, _: float) -> list[str]:
    original = evidence.morphology
    replacement = _replacement(
        original,
        _MORPHOLOGY_REPLACEMENTS.get(evidence.dataset, ()),
        rng,
    )
    if replacement is None:
        return []
    evidence.morphology = replacement
    _replace_observation_name(evidence, "morphology", original, replacement)
    return ["morphology"]


def _delete_variable(evidence: Evidence, rng: random.Random, noise_level: float) -> list[str]:
    variables = list(evidence.raw_evidence.variables)
    if not variables:
        return []
    delete_count = _level_count(len(variables), noise_level)
    delete_indexes = set(rng.sample(range(len(variables)), delete_count))
    remaining = [value for index, value in enumerate(variables) if index not in delete_indexes]
    evidence.raw_evidence.variables = remaining
    evidence.raw_evidence.variable_contributions = {
        variable: score
        for variable, score in evidence.raw_evidence.variable_contributions.items()
        if variable in remaining
    }
    _sync_list_observations(evidence, "variable", remaining)
    return ["raw_evidence.variables", "raw_evidence.variable_contributions"]


def _perturb_variable_name(evidence: Evidence, rng: random.Random, _: float) -> list[str]:
    variables = list(evidence.raw_evidence.variables)
    if not variables:
        return []
    index = rng.randrange(len(variables))
    original = variables[index]
    perturbed = _perturb_token(original)
    variables[index] = perturbed
    evidence.raw_evidence.variables = variables
    contributions = dict(evidence.raw_evidence.variable_contributions)
    if original in contributions:
        contributions[perturbed] = contributions.pop(original)
        evidence.raw_evidence.variable_contributions = contributions
    _replace_observation_name(evidence, "variable", original, perturbed)
    return ["raw_evidence.variables", "raw_evidence.variable_contributions"]


def _delete_log_event(evidence: Evidence, rng: random.Random, noise_level: float) -> list[str]:
    events = list(evidence.raw_evidence.log_events)
    if not events:
        return []
    delete_count = _level_count(len(events), noise_level)
    delete_indexes = set(rng.sample(range(len(events)), delete_count))
    evidence.raw_evidence.log_events = [
        value for index, value in enumerate(events) if index not in delete_indexes
    ]
    _sync_list_observations(evidence, "log_event", evidence.raw_evidence.log_events)
    return ["raw_evidence.log_events"]


def _substitute_synonym(evidence: Evidence, rng: random.Random, _: float) -> list[str]:
    field_values: list[tuple[str, str]] = [
        ("anomaly_type", evidence.anomaly_type),
        ("location", evidence.location or ""),
        ("morphology", evidence.morphology or ""),
        *[("raw_evidence.variables", value) for value in evidence.raw_evidence.variables],
        *[("raw_evidence.log_events", value) for value in evidence.raw_evidence.log_events],
    ]
    candidates = [
        (field, value, _SYNONYMS[value])
        for field, value in field_values
        if value in _SYNONYMS
    ]
    if not candidates:
        return []
    field, original, replacement = rng.choice(candidates)
    if field == "anomaly_type":
        evidence.anomaly_type = replacement
        _replace_observation_name(evidence, "anomaly_type", original, replacement)
    elif field == "location":
        evidence.location = replacement
        _replace_observation_name(evidence, "location", original, replacement)
    elif field == "morphology":
        evidence.morphology = replacement
        _replace_observation_name(evidence, "morphology", original, replacement)
    elif field == "raw_evidence.variables":
        evidence.raw_evidence.variables = [
            replacement if value == original else value for value in evidence.raw_evidence.variables
        ]
        if original in evidence.raw_evidence.variable_contributions:
            contributions = dict(evidence.raw_evidence.variable_contributions)
            contributions[replacement] = contributions.pop(original)
            evidence.raw_evidence.variable_contributions = contributions
        _replace_observation_name(evidence, "variable", original, replacement)
    elif field == "raw_evidence.log_events":
        evidence.raw_evidence.log_events = [
            replacement if value == original else value
            for value in evidence.raw_evidence.log_events
        ]
        _replace_observation_name(evidence, "log_event", original, replacement)
    return [field]


def _inject_contradiction(evidence: Evidence, rng: random.Random, _: float) -> list[str]:
    if evidence.dataset == "tep" and evidence.raw_evidence.variables:
        original = evidence.location
        evidence.location = "feed disturbance"
        _replace_observation_name(evidence, "location", original, evidence.location)
        return ["location"]
    if evidence.dataset == "wafer":
        original = evidence.morphology
        evidence.morphology = "wafer_surface"
        _replace_observation_name(evidence, "morphology", original, evidence.morphology)
        return ["morphology"]
    if evidence.morphology:
        original = evidence.morphology
        evidence.morphology = "surface"
        _replace_observation_name(evidence, "morphology", original, evidence.morphology)
        return ["morphology"]
    return _replace_location(evidence, rng, 1.0)


def _replace_observation_name(
    evidence: Evidence,
    facet: str,
    original: str | None,
    replacement: str,
) -> None:
    if original is None:
        return
    for observation in evidence.observations:
        if observation.facet == facet and observation.name == original:
            observation.name = replacement
            if observation.display_name == original:
                observation.display_name = replacement
            return


def _sync_list_observations(evidence: Evidence, facet: str, remaining: list[str]) -> None:
    remaining_counts = Counter(remaining)
    synced = []
    for observation in evidence.observations:
        if observation.facet != facet:
            synced.append(observation)
            continue
        if remaining_counts[observation.name] > 0:
            remaining_counts[observation.name] -= 1
            synced.append(observation)
    evidence.observations = synced


def _replacement(
    current: str | None,
    pool: tuple[str, ...],
    rng: random.Random,
) -> str | None:
    candidates = [value for value in pool if value != current]
    if not candidates:
        return None
    return rng.choice(candidates)


def _level_count(total: int, noise_level: float) -> int:
    if total <= 0 or noise_level <= 0:
        return 0
    return min(total, max(1, ceil(total * noise_level)))


def _perturb_token(value: str) -> str:
    if "_" in value:
        return value.replace("_", "", 1)
    return f"{value}_perturbed"


def _rng_for(evidence: Evidence, noise_type: str, noise_level: float, seed: int) -> random.Random:
    key = f"{seed}|{evidence.case_id}|{noise_type}|{noise_level:.8f}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))
