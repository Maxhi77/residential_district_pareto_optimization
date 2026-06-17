"""Reusable preprocessing helpers for advanced investment workflows.

This module centralizes input/district preprocessing that was previously
duplicated in script-level code:
- cluster table loading and normalization
- demand table parsing
- centralized scenario discovery + de-duplication
- deterministic toy preprocessing used by block-based tutorial scripts
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ClusterTables:
    """Container for SFH/MFH cluster tables plus a combined view."""

    sfh_cluster: pd.DataFrame
    mfh_cluster: pd.DataFrame
    combined_cluster: pd.DataFrame


_REQUIRED_CLUSTER_COLUMNS = (
    "building_id",
    "buildings_in_cluster",
    "tabula_year_class",
    "net_floor_area",
    "number_of_residents",
    "number_of_apartments",
)


def normalize_cluster_table(cluster_table: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize a cluster table to deterministic dtypes/order."""
    missing = [col for col in _REQUIRED_CLUSTER_COLUMNS if col not in cluster_table.columns]
    if missing:
        raise ValueError(f"Cluster table missing required columns: {missing}.")

    out = cluster_table.copy()
    out = out.sort_values("building_id").reset_index(drop=True)
    out["building_id"] = out["building_id"].astype(str)
    out["buildings_in_cluster"] = out["buildings_in_cluster"].astype(int)
    return out


def load_cluster_tables(base_path: str | Path, ueu_directory: str) -> ClusterTables:
    """Load and normalize `sfh_cluster.pkl` and `mfh_cluster.pkl`."""
    root = Path(base_path) / ueu_directory
    sfh_path = root / "sfh_cluster.pkl"
    mfh_path = root / "mfh_cluster.pkl"
    sfh = pd.read_pickle(sfh_path)
    mfh = pd.read_pickle(mfh_path)
    sfh_n = normalize_cluster_table(sfh)
    mfh_n = normalize_cluster_table(mfh)
    combined = pd.concat([sfh_n, mfh_n], ignore_index=True)
    return ClusterTables(
        sfh_cluster=sfh_n,
        mfh_cluster=mfh_n,
        combined_cluster=combined,
    )


def tabula_year_class_to_construction_year(tabula_year_class: int) -> int:
    """Map TABULA year class to a representative construction year."""
    year_map = {
        1: 1850,
        2: 1910,
        3: 1930,
        4: 1950,
        5: 1960,
        6: 1970,
        7: 1980,
        8: 1990,
        9: 2000,
        10: 2005,
        11: 2010,
        12: 2020,
    }
    return int(year_map.get(int(tabula_year_class), 2000))


def load_building_demand_table(
    demand_directory: str | Path,
    building_id: str,
    ev_suffix: str = "no_EV",
) -> pd.DataFrame:
    """Load per-building demand table with deterministic path handling."""
    demand_path = Path(demand_directory) / f"{building_id}_demand_{ev_suffix}.pkl"
    return pd.read_pickle(demand_path)


def extract_electricity_and_warm_water_profiles(
    demand_table: pd.DataFrame,
) -> Dict[str, np.ndarray]:
    """Extract electricity/warm-water profiles from a demand table."""
    electricity_cols = [c for c in demand_table.columns if c.startswith("Electricity")]
    warm_water_cols = [c for c in demand_table.columns if c.startswith("Warm Water_")]
    if not electricity_cols:
        raise ValueError("Demand table does not contain Electricity* columns.")
    if not warm_water_cols:
        raise ValueError("Demand table does not contain Warm Water_* columns.")
    electricity = demand_table[electricity_cols].sum(axis=1).to_numpy(dtype=float) * 1000.0
    warm_water = demand_table[warm_water_cols].sum(axis=1).to_numpy(dtype=float)
    return {"electricity": electricity, "warm_water": warm_water}


def deduplicate_scenarios_by_choice(
    scenarios: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Drop duplicate scenario entries based on their `choice` mapping."""
    seen_signatures: set[frozenset[tuple[Any, Any]]] = set()
    unique: list[Mapping[str, Any]] = []
    for scenario in scenarios:
        choice = dict(scenario.get("choice", {}))
        signature = frozenset(choice.items())
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        unique.append(scenario)
    return unique


def build_centralized_scenarios(
    matching_buildings_sfh: Mapping[str, Any],
    matching_buildings_mfh: Mapping[str, Any],
    *,
    build_scenarios_fn: Callable[..., tuple[list[dict[str, Any]], Any, Any]],
    remove_duplicate_scenarios_fn: Callable[[Sequence[Mapping[str, Any]]], list[Mapping[str, Any]]],
    n_random: int = 4,
    seed: int = 1,
) -> tuple[list[Mapping[str, Any]], Any, Any]:
    """Create centralized refurbishment scenarios with stable de-duplication."""
    scenarios, buildings_all, available_by_building = build_scenarios_fn(
        matching_buildings_sfh=matching_buildings_sfh,
        matching_buildings_mfh=matching_buildings_mfh,
        n_random=n_random,
        seed=seed,
    )
    scenarios = deduplicate_scenarios_by_choice(scenarios)
    scenarios = remove_duplicate_scenarios_fn(scenarios)
    return scenarios, buildings_all, available_by_building


def _as_profile(values: Sequence[float], n_steps: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.shape[0] != n_steps:
        raise ValueError(f"Profile length mismatch: expected {n_steps}, got {arr.shape[0]}.")
    return arr


def preprocess_decentralized_toy_inputs(
    *,
    building_id: str,
    n_steps: int,
    start: str,
    freq: str,
) -> Dict[str, Any]:
    """Create deterministic toy inputs for decentralized block workflows."""
    timeindex = pd.date_range(start, periods=n_steps, freq=freq)
    profiles = {
        "air_temperature": _as_profile([5.0, 4.0, 3.0, 2.0], n_steps),
        "electricity_demand": _as_profile([4.0, 3.0, 2.5, 3.0], n_steps),
        "warm_water_demand": _as_profile([1.2, 1.0, 0.8, 0.7], n_steps),
        "space_heating_demand": _as_profile([2.5, 2.6, 2.4, 2.3], n_steps),
        "pv_profile": _as_profile([0.0, 0.2, 0.4, 0.1], n_steps),
    }
    return {
        "timeindex": timeindex,
        "building_id": building_id,
        "profiles": profiles,
    }


def preprocess_centralized_toy_inputs(
    *,
    building_ids: Sequence[str],
    n_steps: int,
    start: str,
    freq: str,
) -> Dict[str, Any]:
    """Create deterministic toy inputs for centralized block workflows."""
    timeindex = pd.date_range(start, periods=n_steps, freq=freq)
    building_profiles: Dict[str, Dict[str, np.ndarray]] = {}
    for idx, bid in enumerate(building_ids):
        shift = float(idx) * 0.1
        building_profiles[str(bid)] = {
            "electricity_demand": _as_profile(
                [3.0 + shift, 2.6 + shift, 2.4 + shift, 2.8 + shift], n_steps
            ),
            "warm_water_demand": _as_profile(
                [1.1 + shift, 0.9 + shift, 0.8 + shift, 0.7 + shift], n_steps
            ),
            "space_heating_demand": _as_profile(
                [2.2 + shift, 2.3 + shift, 2.1 + shift, 2.0 + shift], n_steps
            ),
            "pv_profile": _as_profile([0.0, 0.2, 0.4, 0.1], n_steps),
        }
    return {
        "timeindex": timeindex,
        "profiles": {
            "air_temperature": _as_profile([5.0, 4.0, 3.0, 2.0], n_steps),
            "buildings": building_profiles,
        },
    }


__all__ = [
    "ClusterTables",
    "normalize_cluster_table",
    "load_cluster_tables",
    "tabula_year_class_to_construction_year",
    "load_building_demand_table",
    "extract_electricity_and_warm_water_profiles",
    "deduplicate_scenarios_by_choice",
    "build_centralized_scenarios",
    "preprocess_decentralized_toy_inputs",
    "preprocess_centralized_toy_inputs",
]

