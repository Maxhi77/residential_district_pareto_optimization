import ast
import os
import pickle
import re

import numpy as np
import pandas as pd

EV_SUFFIX_NO = "no_EV"
EV_SUFFIX_YES = "yes_EV"
EV_SUFFIX_YES2 = "yes_EV2"
EV_SUFFIX_TOTAL = "yes_EV_total"
EV_SUFFIX_HALF = "yes_EV_half"


def load_demand_dataframe(directory_path, building_id, ev_suffix):
    demand_path = os.path.join(directory_path, f"{building_id}_demand_{ev_suffix}.pkl")
    if not os.path.exists(demand_path):
        raise FileNotFoundError(
            f"Missing demand file for building '{building_id}' and ev suffix '{ev_suffix}': {demand_path}"
        )
    with open(demand_path, "rb") as f:
        demand = pickle.load(f)
    if isinstance(demand, pd.DataFrame):
        return demand.copy()
    return pd.DataFrame(demand)


def _is_nan_like(value):
    if isinstance(value, (list, tuple, dict, set)):
        return False
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _coerce_ev_count_like(value, context):
    if value is None or _is_nan_like(value):
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if numeric < 0 or not numeric.is_integer():
            raise ValueError(f"{context}: EV count must be a non-negative integer, got {value}")
        return int(numeric)
    token = str(value).strip().lower()
    if token in {"true", "yes", "y", "ja"}:
        return 1
    if token in {"false", "no", "n", "nein", ""}:
        return 0
    try:
        numeric = float(token)
    except Exception:
        raise ValueError(f"{context}: cannot parse EV count value '{value}'")
    if numeric < 0 or not numeric.is_integer():
        raise ValueError(f"{context}: EV count must be a non-negative integer, got {value}")
    return int(numeric)


def normalize_household_ev_counts(raw_flags, expected_households, building_id, source_name):
    values = raw_flags
    if isinstance(values, str):
        text = values.strip()
        if not text:
            values = []
        else:
            try:
                values = ast.literal_eval(text)
            except Exception:
                values = [part.strip() for part in text.split(",")]

    if hasattr(values, "tolist") and not isinstance(values, (str, bytes, dict)):
        values = values.tolist()
    if isinstance(values, tuple):
        values = list(values)
    elif not isinstance(values, list):
        values = [values]

    if len(values) < expected_households:
        print(
            f"Warning: building '{building_id}': '{source_name}' has {len(values)} entries, "
            f"but {expected_households} households are expected. Padding missing households with 0 EV."
        )
        values = values + [0] * (expected_households - len(values))
    elif len(values) > expected_households:
        print(
            f"Warning: building '{building_id}': '{source_name}' has {len(values)} entries, "
            f"but {expected_households} households are expected. Truncating to first {expected_households} entries."
        )
        values = values[:expected_households]

    ev_counts = []
    for idx, val in enumerate(values, start=1):
        ev_counts.append(
            _coerce_ev_count_like(
                val,
                context=f"building '{building_id}' {source_name}[HH{idx}]",
            )
        )
    return ev_counts


def extract_has_ev_list(building_row, expected_households, building_id, require_field):
    candidate_fields = ("has_ev_home_per_household_rep", "has_ev_home_per_household")
    for field_name in candidate_fields:
        if field_name in building_row.index:
            raw = building_row[field_name]
            if _is_nan_like(raw):
                continue
            return normalize_household_ev_counts(
                raw,
                expected_households=expected_households,
                building_id=building_id,
                source_name=field_name,
            )
    if require_field:
        raise KeyError(
            f"building '{building_id}': missing EV household list. "
            f"Expected one of {candidate_fields} in cluster row."
        )
    return [0] * expected_households


def build_even_ev_assignment(num_households, num_ev_households):
    n = int(max(0, num_households))
    k = int(max(0, num_ev_households))
    if n == 0 or k == 0:
        return [0] * n
    if k >= n:
        return [1] * n

    out = [0] * n
    for i in range(k):
        pos = int(((i + 0.5) * n) / k)
        if pos >= n:
            pos = n - 1
        out[pos] = 1
    return out


def extract_household_column_map(demand_df, prefix):
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    mapping = {}
    for col in demand_df.columns:
        match = pattern.match(str(col).strip())
        if match:
            hh_idx = int(match.group(1))
            if hh_idx in mapping:
                raise ValueError(f"Duplicate household index {hh_idx} for prefix '{prefix}'.")
            mapping[hh_idx] = col
    return mapping


def build_mixed_electricity_profile_per_household(
    building_id,
    directory_path,
    has_ev_list,
    ev_suffix_with_ev=EV_SUFFIX_YES,
    strict_car_column_for_ev_households=True,
    force_load_with_ev_file=False,
):
    demand_no_ev = load_demand_dataframe(directory_path, building_id, EV_SUFFIX_NO)

    hh_cols_no_ev = extract_household_column_map(demand_no_ev, "Electricity_HH")
    if not hh_cols_no_ev:
        raise ValueError(
            f"building '{building_id}': no household electricity columns found in no_EV file. "
            "Expected columns like 'Electricity_HH1'."
        )

    hh_indices = sorted(hh_cols_no_ev.keys())
    expected_hh_indices = list(range(1, len(hh_indices) + 1))
    if hh_indices != expected_hh_indices:
        raise ValueError(
            f"building '{building_id}': expected contiguous household columns HH1..HH{len(hh_indices)}, "
            f"got HH indices {hh_indices}."
        )

    has_ev_counts = normalize_household_ev_counts(
        has_ev_list,
        expected_households=len(hh_indices),
        building_id=building_id,
        source_name="has_ev_list",
    )
    needs_with_ev_file = force_load_with_ev_file or any(int(x) > 0 for x in has_ev_counts)

    if not needs_with_ev_file:
        mixed_electricity = pd.Series(0.0, index=demand_no_ev.index, dtype=float)
        for hh_idx in hh_indices:
            base_col = hh_cols_no_ev[hh_idx]
            base_profile = pd.to_numeric(demand_no_ev[base_col], errors="coerce").fillna(0.0)
            mixed_electricity = mixed_electricity.add(base_profile, fill_value=0.0)
        return mixed_electricity, demand_no_ev, None

    demand_with_ev = load_demand_dataframe(directory_path, building_id, ev_suffix_with_ev)
    if len(demand_no_ev) != len(demand_with_ev):
        raise ValueError(
            f"building '{building_id}': no_EV and {ev_suffix_with_ev} demand length mismatch "
            f"({len(demand_no_ev)} vs {len(demand_with_ev)})."
        )
    if not demand_no_ev.index.equals(demand_with_ev.index):
        demand_no_ev = demand_no_ev.reset_index(drop=True)
        demand_with_ev = demand_with_ev.reset_index(drop=True)

    hh_cols_with_ev = extract_household_column_map(demand_with_ev, "Electricity_HH")
    if set(hh_cols_no_ev.keys()) != set(hh_cols_with_ev.keys()):
        raise ValueError(
            f"building '{building_id}': household electricity columns differ between no_EV and {ev_suffix_with_ev}. "
            f"no_EV={sorted(hh_cols_no_ev.keys())}, {ev_suffix_with_ev}={sorted(hh_cols_with_ev.keys())}"
        )

    car_cols_with_ev = extract_household_column_map(demand_with_ev, "Electricity for Car Charging_HH")

    mixed_electricity = pd.Series(0.0, index=demand_no_ev.index, dtype=float)
    for list_pos, hh_idx in enumerate(hh_indices):
        base_col = hh_cols_no_ev[hh_idx]
        base_profile = pd.to_numeric(demand_no_ev[base_col], errors="coerce").fillna(0.0)
        mixed_electricity = mixed_electricity.add(base_profile, fill_value=0.0)

        ev_count_for_hh = int(has_ev_counts[list_pos])
        if ev_count_for_hh > 0:
            car_col = car_cols_with_ev.get(hh_idx)
            if car_col is None:
                message = (
                    f"building '{building_id}': EV household HH{hh_idx} requires "
                    f"'Electricity for Car Charging_HH{hh_idx}' in '{ev_suffix_with_ev}' demand file."
                )
                if strict_car_column_for_ev_households:
                    raise ValueError(message)
                continue
            car_profile = pd.to_numeric(demand_with_ev[car_col], errors="coerce").fillna(0.0)
            if ev_suffix_with_ev == EV_SUFFIX_YES2:
                car_multiplier = ev_count_for_hh
            else:
                car_multiplier = 1
            mixed_electricity = mixed_electricity.add(
                car_profile * float(car_multiplier),
                fill_value=0.0,
            )

    return mixed_electricity, demand_no_ev, demand_with_ev


def build_household_presence_profile(results, household_index=1, persons_per_step_factor=60.0):
    suffix = f"HH{int(household_index)}"
    outside_col = f"Person Count for  - Outside_{suffix}"
    sleeping_col = f"Person Count for  - Low_{suffix}"
    awake_col = f"Person Count for  - High_{suffix}"

    missing = [col for col in (outside_col, sleeping_col, awake_col) if col not in results.columns]
    if missing:
        raise KeyError(
            f"Missing person-count columns for household {suffix}: {missing}"
        )

    profile = pd.DataFrame(index=results.index.copy())
    profile["outside"] = pd.to_numeric(results[outside_col], errors="coerce").fillna(0.0) / float(
        persons_per_step_factor
    )
    profile["sleeping"] = pd.to_numeric(results[sleeping_col], errors="coerce").fillna(0.0) / float(
        persons_per_step_factor
    )
    profile["awake"] = pd.to_numeric(results[awake_col], errors="coerce").fillna(0.0) / float(
        persons_per_step_factor
    )
    profile["outside"] = profile["outside"].round()
    profile["sleeping"] = profile["sleeping"].round()
    profile["awake"] = profile["awake"].round()
    return profile


def calculate_min_max_nominal_air(
    results_household,
    number_of_habitant,
    mode="ems",
    reduced_temp=16.0,
    normal_temp=19.0,
):
    mode_key = str(mode).strip().lower()
    if mode_key not in {"ems", "ntr", "bau"}:
        raise ValueError(f"Unknown mode '{mode}'. Expected 'ems', 'ntr' or 'bau'.")

    sleeping_all = results_household["sleeping"] == int(number_of_habitant)
    if mode_key == "ems":
        outside_all = results_household["outside"] == int(number_of_habitant)
        min_temp = np.where(sleeping_all | outside_all, float(reduced_temp), float(normal_temp))
    elif mode_key == "bau":
        min_temp = np.full(len(results_household.index), float(normal_temp))
    else:
        min_temp = np.where(sleeping_all, float(reduced_temp), float(normal_temp))

    return min_temp.tolist()
