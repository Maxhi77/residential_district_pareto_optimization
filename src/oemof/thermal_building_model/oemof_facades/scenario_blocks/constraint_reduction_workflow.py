"""Reusable CO2/peak tightening workflow helpers for advanced investment runs."""

from __future__ import annotations

import math
import pickle
from pathlib import Path
from typing import Any, Callable, Dict, Hashable, Iterable, Optional, Sequence


RunCase = Callable[[Optional[float], Optional[float]], tuple[Any, ...]]
ResultKeyBuilder = Callable[[float, float, str, bool], Hashable]


def compute_co2_target(co2_reference: float, reduction_factor: float) -> float:
    """Compute a CO2 target while preserving legacy handling of negative values."""
    if co2_reference > 0:
        return float(co2_reference * reduction_factor)
    return float(co2_reference * (2.0 - reduction_factor))


def compute_peak_target(peak_reference: float, reduction_factor: float) -> float:
    """Compute a peak target from a reference and reduction factor."""
    return float(peak_reference * reduction_factor)


def _default_co2_factors() -> list[float]:
    return [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]


def _default_peak_factors() -> list[float]:
    return [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]


def _default_key_builder(
    co2_factor: float,
    peak_factor: float,
    reference_label: str,
    is_baseline: bool,
) -> Hashable:
    if is_baseline:
        return (co2_factor, peak_factor)
    return (co2_factor, peak_factor, reference_label)


def _load_existing_pickle(path: Path) -> Dict[Hashable, Dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        loaded = pickle.load(fh)
    if isinstance(loaded, dict):
        return loaded
    return {}


def _save_pickle(path: Path, data: Dict[Hashable, Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump(data, fh)


def _extract_peak(final_results: Dict[str, Any]) -> Optional[float]:
    electricity = final_results.get("Electricity")
    if not isinstance(electricity, dict):
        return None
    peak_from = electricity.get("peak_from_grid")
    peak_into = electricity.get("peak_into_grid")
    values = []
    for val in (peak_from, peak_into):
        if val is None:
            continue
        val_f = float(val)
        if math.isfinite(val_f):
            values.append(val_f)
    if not values:
        return None
    return float(max(values))


def _parse_run_result(raw: tuple[Any, ...]) -> tuple[Any, Any, Any, Optional[str]]:
    """Normalize run return tuple to (results, co2, wall_time, termination)."""
    if len(raw) >= 4:
        return raw[0], raw[1], raw[2], None if raw[3] is None else str(raw[3]).lower()
    if len(raw) == 3:
        return raw[0], raw[1], raw[2], None
    raise ValueError("run_case must return at least (results, co2, wall_time).")


def run_stepwise_co2_peak_reduction(
    run_case: RunCase,
    *,
    reference_label: str = "co2",
    co2_reduction_factors: Optional[Sequence[float]] = None,
    peak_reduction_factors: Optional[Sequence[float]] = None,
    key_builder: Optional[ResultKeyBuilder] = None,
    output_path: str | Path | None = None,
    static_entry_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run baseline + stepwise CO2/peak tightening and optionally persist results.

    `run_case` must accept `(co2_limit, peak_limit)` and return:
    `(final_results, co2_value, wall_time)` or
    `(final_results, co2_value, wall_time, termination)`.
    """

    co2_factors = list(co2_reduction_factors or _default_co2_factors())
    peak_factors = list(peak_reduction_factors or _default_peak_factors())
    build_key = key_builder or _default_key_builder
    static_fields = dict(static_entry_fields or {})
    out: Dict[Hashable, Dict[str, Any]] = {}
    run_log: list[Dict[str, Any]] = []

    baseline_raw = run_case(None, None)
    baseline_results, baseline_co2, baseline_time, baseline_termination = _parse_run_result(
        baseline_raw
    )
    if baseline_results is None:
        raise RuntimeError("Baseline run failed; cannot start reduction workflow.")

    baseline_peak = _extract_peak(baseline_results)
    if baseline_peak is None:
        raise RuntimeError("Baseline run did not expose peak_from_grid/peak_into_grid.")
    baseline_objective = baseline_results.get("totex")
    baseline_entry = {
        "results": baseline_results,
        "co2": None if baseline_co2 is None else float(baseline_co2),
        "peak_reduction_factor": 1.0,
        "totex": None if baseline_objective is None else float(baseline_objective),
        "peak": float(baseline_peak),
        "peak_from_grid": float(baseline_results["Electricity"]["peak_from_grid"]),
        "peak_into_grid": float(baseline_results["Electricity"]["peak_into_grid"]),
        "time": None if baseline_time is None else float(baseline_time),
        "termination": baseline_termination,
    }
    baseline_entry.update(static_fields)
    baseline_key = build_key(1.0, 1.0, reference_label, True)
    out[baseline_key] = baseline_entry
    run_log.append(
        {
            "co2_reduction_factor": 1.0,
            "peak_reduction_factor": 1.0,
            "co2_target": None,
            "peak_target": None,
            "success": True,
            "key": baseline_key,
        }
    )

    co2_reference = float(baseline_co2)
    peak_reference_initial = float(baseline_peak)

    for co2_factor in co2_factors:
        co2_target = compute_co2_target(co2_reference, float(co2_factor))
        first_peak_run_for_co2 = True
        peak_reference = peak_reference_initial
        for peak_factor in peak_factors:
            if first_peak_run_for_co2:
                peak_target = None
            else:
                peak_target = compute_peak_target(peak_reference, float(peak_factor))

            success = True
            termination = None
            final_results = None
            co2_value = None
            wall_time = None
            try:
                raw = run_case(co2_target, peak_target)
                final_results, co2_value, wall_time, termination = _parse_run_result(raw)
            except Exception:
                success = False

            key = build_key(float(co2_factor), float(peak_factor), reference_label, False)
            if not success or final_results is None:
                entry = {
                    "results": None,
                    "co2": None,
                    "peak_reduction_factor": None,
                    "totex": None,
                    "peak": None,
                    "peak_from_grid": None,
                    "peak_into_grid": None,
                    "time": None,
                    "termination": termination,
                }
                entry.update(static_fields)
                out[key] = entry
                run_log.append(
                    {
                        "co2_reduction_factor": float(co2_factor),
                        "peak_reduction_factor": float(peak_factor),
                        "co2_target": float(co2_target),
                        "peak_target": peak_target,
                        "success": False,
                        "key": key,
                    }
                )
                if first_peak_run_for_co2:
                    first_peak_run_for_co2 = False
                    peak_reference = 0.0
                break

            peak_value = _extract_peak(final_results)
            objective = final_results.get("totex")
            entry = {
                "results": final_results,
                "co2": None if co2_value is None else float(co2_value),
                "peak_reduction_factor": float(peak_factor),
                "totex": None if objective is None else float(objective),
                "peak": peak_value,
                "peak_from_grid": float(final_results["Electricity"]["peak_from_grid"]),
                "peak_into_grid": float(final_results["Electricity"]["peak_into_grid"]),
                "time": None if wall_time is None else float(wall_time),
                "termination": termination,
            }
            entry.update(static_fields)
            out[key] = entry
            run_log.append(
                {
                    "co2_reduction_factor": float(co2_factor),
                    "peak_reduction_factor": float(peak_factor),
                    "co2_target": float(co2_target),
                    "peak_target": peak_target,
                    "success": True,
                    "key": key,
                }
            )

            if first_peak_run_for_co2:
                first_peak_run_for_co2 = False
                if peak_value is not None:
                    peak_reference = float(peak_value)

    saved_path = None
    if output_path is not None:
        out_path = Path(output_path)
        existing = _load_existing_pickle(out_path)
        existing.update(out)
        _save_pickle(out_path, existing)
        saved_path = str(out_path)

    return {
        "baseline_key": baseline_key,
        "co2_reference": co2_reference,
        "peak_reference": peak_reference_initial,
        "results_by_key": out,
        "run_log": run_log,
        "saved_path": saved_path,
    }


__all__ = [
    "compute_co2_target",
    "compute_peak_target",
    "run_stepwise_co2_peak_reduction",
]

