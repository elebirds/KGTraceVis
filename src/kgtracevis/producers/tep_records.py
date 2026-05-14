"""Raw Tennessee Eastman Process CSV record producer."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from kgtracevis.producers.common import filter_forbidden_outputs

TEP_RBC_BACKEND = "tep-rbc"

FAULT_FREE_TRAINING_FILENAME = "TEP_FaultFree_Training.csv"
FAULTY_TRAINING_FILENAME = "TEP_Faulty_Training.csv"
DEFAULT_TEP_FAULTS = tuple(range(1, 22))
ID_COLUMNS = ("faultNumber", "simulationRun", "sample")
CHANNEL_PREFIXES = ("xmeas_", "xmv_")


@dataclass(frozen=True)
class TepFaultFreeProfile:
    """Fault-free TEP profile used for residual contribution scoring."""

    variable_columns: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    components: np.ndarray
    n_rows: int
    row_stride: int
    max_rows: int | None


@dataclass(frozen=True)
class TepFaultWindow:
    """A fixed-size raw TEP faulty window."""

    fault_number: int
    simulation_run: int
    sample_start: int
    sample_end: int
    rows: np.ndarray


@dataclass(frozen=True)
class TepWindowContributions:
    """Residual contribution details for one TEP window."""

    channel_contributions: dict[str, float]
    residual_energy: float
    confidence: float


def build_tep_records(
    raw_data_dir: str | Path | None = None,
    *,
    fault_free_path: str | Path | None = None,
    faulty_path: str | Path | None = None,
    row_stride: int = 25,
    fault_free_max_rows: int | None = None,
    window_size: int = 100,
    faults: Sequence[int] | None = None,
    max_runs_per_fault: int = 3,
    max_cases: int | None = None,
    top_variables: int = 5,
    n_components: int | None = None,
    profile_output_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Build adapter-ready TEP records from raw fault-free and faulty CSV files."""
    if raw_data_dir is None and (fault_free_path is None or faulty_path is None):
        raw_data_dir = Path("data/raw/tep")
    data_dir = Path(raw_data_dir) if raw_data_dir is not None else None
    fault_free_csv = _resolve_tep_csv_path(
        explicit_path=fault_free_path,
        raw_data_dir=data_dir,
        filename=FAULT_FREE_TRAINING_FILENAME,
    )
    faulty_csv = _resolve_tep_csv_path(
        explicit_path=faulty_path,
        raw_data_dir=data_dir,
        filename=FAULTY_TRAINING_FILENAME,
    )
    _validate_positive("row_stride", row_stride)
    _validate_positive("window_size", window_size)
    _validate_positive("max_runs_per_fault", max_runs_per_fault)
    _validate_positive("top_variables", top_variables)
    if max_cases is not None and max_cases < 0:
        raise ValueError("max_cases must be non-negative")

    variable_columns = _variable_columns(fault_free_csv)
    _validate_faulty_columns(faulty_csv, variable_columns)
    profile = fit_tep_fault_free_profile(
        fault_free_csv,
        variable_columns=variable_columns,
        row_stride=row_stride,
        max_rows=fault_free_max_rows,
        n_components=n_components,
    )
    if profile_output_path is not None:
        _write_profile(profile, Path(profile_output_path))

    selected_faults = tuple(int(fault) for fault in (faults or DEFAULT_TEP_FAULTS))
    windows = collect_tep_fault_windows(
        faulty_csv,
        variable_columns=profile.variable_columns,
        faults=selected_faults,
        window_size=window_size,
        max_runs_per_fault=max_runs_per_fault,
        max_cases=max_cases,
    )
    return [
        _record_from_window(
            window,
            contribution=compute_tep_window_contributions(profile, window),
            faulty_path=faulty_csv,
            profile=profile,
            top_variables=top_variables,
        )
        for window in windows
    ]


def fit_tep_fault_free_profile(
    fault_free_path: str | Path,
    *,
    variable_columns: Sequence[str] | None = None,
    row_stride: int = 25,
    max_rows: int | None = None,
    n_components: int | None = None,
) -> TepFaultFreeProfile:
    """Fit a compact fault-free TEP reconstruction profile from raw CSV rows."""
    _validate_positive("row_stride", row_stride)
    if max_rows is not None and max_rows <= 0:
        raise ValueError("max_rows must be positive when provided")

    path = Path(fault_free_path)
    columns = tuple(variable_columns or _variable_columns(path))
    samples: list[list[float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require_columns(path, reader.fieldnames, columns)
        for index, row in enumerate(reader):
            if index % row_stride != 0:
                continue
            samples.append(_row_values(row, columns))
            if max_rows is not None and len(samples) >= max_rows:
                break
    if len(samples) < 2:
        raise ValueError(f"{path} must provide at least two sampled fault-free rows")

    matrix = np.asarray(samples, dtype=float)
    mean = matrix.mean(axis=0)
    scale = matrix.std(axis=0, ddof=1)
    scale = np.where(scale > 1e-12, scale, 1.0)
    standardized = (matrix - mean) / scale
    component_count = _component_count(
        requested=n_components,
        column_count=len(columns),
        row_count=len(samples),
    )
    components = _principal_components(standardized, component_count)
    return TepFaultFreeProfile(
        variable_columns=columns,
        mean=mean,
        scale=scale,
        components=components,
        n_rows=len(samples),
        row_stride=row_stride,
        max_rows=max_rows,
    )


def collect_tep_fault_windows(
    faulty_path: str | Path,
    *,
    variable_columns: Sequence[str],
    faults: Sequence[int] = DEFAULT_TEP_FAULTS,
    window_size: int = 100,
    max_runs_per_fault: int = 3,
    max_cases: int | None = None,
) -> list[TepFaultWindow]:
    """Collect fixed-size faulty windows grouped by TEP fault and simulation run."""
    _validate_positive("window_size", window_size)
    _validate_positive("max_runs_per_fault", max_runs_per_fault)
    if max_cases is not None and max_cases < 0:
        raise ValueError("max_cases must be non-negative")

    path = Path(faulty_path)
    target_faults = {int(fault) for fault in faults}
    if not target_faults:
        return []

    active_rows: dict[tuple[int, int], list[list[float]]] = defaultdict(list)
    sample_ranges: dict[tuple[int, int], list[int]] = {}
    completed_runs: dict[int, set[int]] = defaultdict(set)
    windows: list[TepFaultWindow] = []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require_columns(path, reader.fieldnames, (*ID_COLUMNS, *variable_columns))
        for row in reader:
            fault_number = _int_cell(row, "faultNumber")
            if fault_number not in target_faults:
                continue
            simulation_run = _int_cell(row, "simulationRun")
            if simulation_run in completed_runs[fault_number]:
                continue
            if len(completed_runs[fault_number]) >= max_runs_per_fault:
                continue

            key = (fault_number, simulation_run)
            rows = active_rows[key]
            if not rows:
                sample_ranges[key] = [_int_cell(row, "sample"), _int_cell(row, "sample")]
            else:
                sample_ranges[key][1] = _int_cell(row, "sample")
            rows.append(_row_values(row, variable_columns))
            if len(rows) < window_size:
                continue

            completed_runs[fault_number].add(simulation_run)
            sample_start, sample_end = sample_ranges[key]
            windows.append(
                TepFaultWindow(
                    fault_number=fault_number,
                    simulation_run=simulation_run,
                    sample_start=sample_start,
                    sample_end=sample_end,
                    rows=np.asarray(rows, dtype=float),
                )
            )
            del active_rows[key]
            del sample_ranges[key]
            if max_cases is not None and len(windows) >= max_cases:
                break
            if _all_requested_runs_collected(
                completed_runs,
                target_faults=target_faults,
                max_runs_per_fault=max_runs_per_fault,
            ):
                break
    return windows


def compute_tep_window_contributions(
    profile: TepFaultFreeProfile,
    window: TepFaultWindow,
) -> TepWindowContributions:
    """Compute normalized residual contribution mass for one faulty TEP window."""
    standardized = (window.rows - profile.mean) / profile.scale
    if profile.components.size:
        scores = standardized @ profile.components
        reconstructed = scores @ profile.components.T
        residual = standardized - reconstructed
    else:
        residual = standardized

    residual_squared = np.mean(np.square(residual), axis=0)
    total = float(residual_squared.sum())
    if total <= 1e-12:
        fallback = np.mean(np.abs(standardized), axis=0)
        total = float(fallback.sum())
        residual_squared = fallback
    if total <= 1e-12:
        contributions = np.full(len(profile.variable_columns), 1.0 / len(profile.variable_columns))
        residual_energy = 0.0
    else:
        contributions = residual_squared / total
        residual_energy = float(np.mean(np.sum(np.square(residual), axis=1)))

    return TepWindowContributions(
        channel_contributions={
            _canonical_channel_name(column): round(float(value), 8)
            for column, value in zip(profile.variable_columns, contributions, strict=True)
        },
        residual_energy=residual_energy,
        confidence=_unit_interval(residual_energy / (residual_energy + 1.0)),
    )


def _record_from_window(
    window: TepFaultWindow,
    *,
    contribution: TepWindowContributions,
    faulty_path: Path,
    profile: TepFaultFreeProfile,
    top_variables: int,
) -> dict[str, Any]:
    ranked = sorted(
        contribution.channel_contributions.items(),
        key=lambda item: (-item[1], item[0]),
    )
    top = ranked[:top_variables]
    variables = [name for name, _value in top]
    variable_contributions = {name: value for name, value in top}
    case_id = (
        f"tep_fault_{window.fault_number:02d}_run_{window.simulation_run:03d}"
        f"_samples_{window.sample_start:06d}_{window.sample_end:06d}"
    )
    record = {
        "dataset": "tep",
        "source": "tep_csv_rbc",
        "adapter": "tep",
        "case_id": case_id,
        "scenario_id": case_id,
        "object": "Tennessee Eastman Process",
        "anomaly_type": f"fault_{window.fault_number:02d}",
        "location": "process",
        "morphology": "multivariate_residual_shift",
        "severity": contribution.confidence,
        "confidence": contribution.confidence,
        "variables": variables,
        "variable_contributions": variable_contributions,
        "description": (
            f"TEP fault {window.fault_number} simulation run {window.simulation_run} "
            f"samples {window.sample_start}-{window.sample_end} residual contribution window."
        ),
        "fault_number": window.fault_number,
        "fault_id": window.fault_number,
        "simulation_run": window.simulation_run,
        "simulation_id": window.simulation_run,
        "run_id": window.simulation_run,
        "sample_start": window.sample_start,
        "sample_end": window.sample_end,
        "window": f"{window.sample_start}:{window.sample_end}",
        "window_start": window.sample_start,
        "window_end": window.sample_end,
        "window_size": int(window.rows.shape[0]),
        "raw_data_path": str(faulty_path),
        "detector": {
            "name": "tep_residual_contribution",
            "backend": TEP_RBC_BACKEND,
            "profile_rows": profile.n_rows,
            "profile_row_stride": profile.row_stride,
            "profile_max_rows": profile.max_rows,
            "n_components": int(profile.components.shape[1]) if profile.components.ndim == 2 else 0,
            "residual_energy": round(contribution.residual_energy, 8),
            "produces_root_cause": False,
        },
        "extra": {
            "channel_contributions": contribution.channel_contributions,
            "top_channels": variables,
            "source_columns": list(profile.variable_columns),
        },
    }
    return filter_forbidden_outputs(record)


def _resolve_tep_csv_path(
    *,
    explicit_path: str | Path | None,
    raw_data_dir: Path | None,
    filename: str,
) -> Path:
    path = (
        Path(explicit_path)
        if explicit_path is not None
        else (raw_data_dir / filename if raw_data_dir else None)
    )
    if path is None:
        raise ValueError(f"{filename} path is required")
    if not path.is_file():
        raise FileNotFoundError(f"TEP CSV not found: {path}")
    return path


def _variable_columns(path: Path) -> tuple[str, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"{path} is empty") from exc
    columns = tuple(
        sorted(
            (name for name in header if _is_channel_column(name)),
            key=_channel_sort_key,
        )
    )
    if not columns:
        raise ValueError(f"{path} does not contain xmeas_/xmv_ variable columns")
    return columns


def _validate_faulty_columns(path: Path, variable_columns: Sequence[str]) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require_columns(path, reader.fieldnames, (*ID_COLUMNS, *variable_columns))


def _require_columns(path: Path, fieldnames: Sequence[str] | None, columns: Iterable[str]) -> None:
    if fieldnames is None:
        raise ValueError(f"{path} is missing a CSV header")
    missing = [column for column in columns if column not in fieldnames]
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")


def _is_channel_column(name: str) -> bool:
    lower = name.lower()
    return any(lower.startswith(prefix) for prefix in CHANNEL_PREFIXES)


def _channel_sort_key(name: str) -> tuple[int, int, str]:
    lower = name.lower()
    prefix_rank = 0 if lower.startswith("xmeas_") else 1
    suffix = lower.rsplit("_", maxsplit=1)[-1]
    try:
        number = int(suffix)
    except ValueError:
        number = 10**6
    return (prefix_rank, number, lower)


def _canonical_channel_name(name: str) -> str:
    return name.strip().upper()


def _row_values(row: dict[str, str], columns: Sequence[str]) -> list[float]:
    return [_float_cell(row, column) for column in columns]


def _float_cell(row: dict[str, str], column: str) -> float:
    try:
        return float(row[column])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric value for {column}: {row.get(column)!r}") from exc


def _int_cell(row: dict[str, str], column: str) -> int:
    try:
        return int(float(row[column]))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid integer value for {column}: {row.get(column)!r}") from exc


def _component_count(
    *,
    requested: int | None,
    column_count: int,
    row_count: int,
) -> int:
    if requested is not None and requested < 0:
        raise ValueError("n_components must be non-negative")
    max_components = max(0, min(column_count - 1, row_count - 1))
    if requested is None:
        return min(6, max_components)
    return min(requested, max_components)


def _principal_components(standardized: np.ndarray, component_count: int) -> np.ndarray:
    if component_count <= 0:
        return np.empty((standardized.shape[1], 0), dtype=float)
    covariance = np.cov(standardized, rowvar=False)
    covariance = np.atleast_2d(covariance)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    return eigenvectors[:, order[:component_count]]


def _all_requested_runs_collected(
    completed_runs: dict[int, set[int]],
    *,
    target_faults: set[int],
    max_runs_per_fault: int,
) -> bool:
    return all(len(completed_runs[fault]) >= max_runs_per_fault for fault in target_faults)


def _unit_interval(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 8)


def _validate_positive(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _write_profile(profile: TepFaultFreeProfile, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "variable_columns": list(profile.variable_columns),
        "mean": profile.mean.tolist(),
        "scale": profile.scale.tolist(),
        "components": profile.components.tolist(),
        "n_rows": profile.n_rows,
        "row_stride": profile.row_stride,
        "max_rows": profile.max_rows,
    }
    output_path.write_text(
        json.dumps(filter_forbidden_outputs(payload), indent=2, sort_keys=False),
        encoding="utf-8",
    )
