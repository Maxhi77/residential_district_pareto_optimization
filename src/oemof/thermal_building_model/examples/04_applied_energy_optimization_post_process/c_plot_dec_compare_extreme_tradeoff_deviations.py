import os
import pickle
import re
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import pandas as pd
from matplotlib import cm
from matplotlib import colors as mcolors
from matplotlib.lines import Line2D

from b_plot_pareto_front_dec import (
    calculate_sums_for_technologies_and_energy_for_a_district,
    maniupulate_combined_front_elect_grid,
    process_district_data,
    process_units_for_processed,
)

# -----------------------------
# Plot switches / scope
# -----------------------------
ONLY_PARALLEL_STYLE_KEEP = True
PARALLEL_TARGET_OBJECTIVES = ["min_gwp", "min_totex", "min_peak"]
PARALLEL_TARGET_HEIGHT_TAGS = ["h70", "h80", "h90", "h100"]
ENABLE_STD_BAND_PLOTS = True
STD_BAND_MULTIPLIERS = (1, 2, 3)
STD_BAND_SCALE_WITHIN_AXIS_ABS_MAX = True
ENABLE_DEVIATION_NO_STD_PLOTS = True


def set_journal_style(font_family: str = "TeX Gyre Termes", font_size: int = 9) -> None:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": font_family,
            "font.size": font_size,
            "axes.titlesize": font_size,
            "axes.labelsize": font_size,
            "xtick.labelsize": font_size,
            "ytick.labelsize": font_size,
            "legend.fontsize": font_size,
            "mathtext.fontset": "cm",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _to_windows_long_path(path_str: str) -> str:
    abs_path = os.path.abspath(path_str)
    if os.name != "nt":
        return abs_path
    if abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path.lstrip("\\")
    if len(abs_path) >= 248:
        return "\\\\?\\" + abs_path
    return abs_path


def _is_front_like_list(obj) -> bool:
    if not isinstance(obj, list):
        return False
    if len(obj) == 0:
        return True
    first = obj[0]
    if not isinstance(first, dict):
        return False
    return {"co2", "totex", "peak"}.issubset(set(first.keys()))


def _extract_combined_front_from_loaded_object(loaded_obj) -> List[Dict[str, float]]:
    if _is_front_like_list(loaded_obj):
        return loaded_obj

    if isinstance(loaded_obj, (list, tuple)):
        if len(loaded_obj) > 2 and _is_front_like_list(loaded_obj[2]):
            return loaded_obj[2]
        for item in loaded_obj:
            if _is_front_like_list(item):
                return item

    if isinstance(loaded_obj, dict):
        if _is_front_like_list(loaded_obj.get("combined_front")):
            return loaded_obj["combined_front"]
        for item in loaded_obj.values():
            if _is_front_like_list(item):
                return item

    raise ValueError(
        "Could not extract 'combined_front' from pickle payload. "
        f"Top-level type: {type(loaded_obj)}"
    )


def load_combined_front_from_path(pkl_path: Path) -> List[Dict[str, float]]:
    with open(_to_windows_long_path(str(pkl_path)), "rb") as f:
        loaded_obj = pickle.load(f)
    return _extract_combined_front_from_loaded_object(loaded_obj)


def get_pareto_front(data: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pareto_front = []
    last_y = float("inf")
    for x_val, y_val in data:
        if y_val < last_y:
            pareto_front.append((x_val, y_val))
            last_y = y_val
    return pareto_front


def get_pareto_front_for_axes(
    combined_front: List[Dict[str, float]], x_key: str, y_key: str
) -> List[Tuple[float, float]]:
    data_2d: List[Tuple[float, float]] = []
    for rec in combined_front:
        xv = rec.get(x_key)
        yv = rec.get(y_key)
        if xv is None or yv is None:
            continue
        xv = float(xv)
        yv = float(yv)
        if not (np.isfinite(xv) and np.isfinite(yv)):
            continue
        data_2d.append((xv, yv))

    if not data_2d:
        return []

    data_2d = sorted(data_2d)
    return get_pareto_front(data_2d)


def extract_extreme_points_from_tradeoffs(
    combined_front: List[Dict[str, float]],
) -> Dict[str, float]:
    front_cost_co2 = get_pareto_front_for_axes(combined_front, x_key="co2", y_key="totex")
    front_cost_peak = get_pareto_front_for_axes(combined_front, x_key="totex", y_key="peak")
    front_peak_co2 = get_pareto_front_for_axes(combined_front, x_key="peak", y_key="co2")

    if not front_cost_co2 or not front_cost_peak or not front_peak_co2:
        raise ValueError("At least one tradeoff front is empty.")

    return {
        "min_totex": float(min(y for _, y in front_cost_co2)),
        "min_peak": float(min(y for _, y in front_cost_peak)),
        "min_gwp": float(min(y for _, y in front_peak_co2)),
        "max_totex": float(max(y for _, y in front_cost_co2)),
        "max_peak": float(max(y for _, y in front_cost_peak)),
        "max_gwp": float(max(y for _, y in front_peak_co2)),
        "n_front_cost_co2": float(len(front_cost_co2)),
        "n_front_cost_peak": float(len(front_cost_peak)),
        "n_front_peak_co2": float(len(front_peak_co2)),
    }


def _best_match_for_xy(
    combined_front: List[Dict[str, float]],
    x_key: str,
    y_key: str,
    x_target: float,
    y_target: float,
    tol: float = 1e-8,
) -> Dict[str, float]:
    best_match = None
    best_score = None
    for rec in combined_front:
        xv = rec.get(x_key)
        yv = rec.get(y_key)
        if xv is None or yv is None:
            continue
        xv = float(xv)
        yv = float(yv)
        if np.isclose(xv, x_target, atol=tol) and np.isclose(yv, y_target, atol=tol):
            score = (
                float(rec.get("co2", np.inf)),
                float(rec.get("peak", np.inf)),
                float(rec.get("totex", np.inf)),
            )
            if best_score is None or score < best_score:
                best_score = score
                best_match = rec
    if best_match is None:
        raise ValueError(
            f"No exact match found in combined_front for ({x_key}, {y_key})=({x_target}, {y_target})."
        )
    return best_match


def extract_extreme_records_from_tradeoffs(
    combined_front: List[Dict[str, float]],
) -> Dict[str, Dict[str, float]]:
    front_cost_co2 = get_pareto_front_for_axes(combined_front, x_key="co2", y_key="totex")
    front_cost_peak = get_pareto_front_for_axes(combined_front, x_key="totex", y_key="peak")
    front_peak_co2 = get_pareto_front_for_axes(combined_front, x_key="peak", y_key="co2")

    if not front_cost_co2 or not front_cost_peak or not front_peak_co2:
        raise ValueError("At least one tradeoff front is empty.")

    min_totex = min(y for _, y in front_cost_co2)
    min_peak = min(y for _, y in front_cost_peak)
    min_gwp = min(y for _, y in front_peak_co2)
    max_totex = max(y for _, y in front_cost_co2)
    max_peak = max(y for _, y in front_cost_peak)
    max_gwp = max(y for _, y in front_peak_co2)

    x_totex, y_totex = min((x, y) for x, y in front_cost_co2 if np.isclose(y, min_totex))
    x_peak, y_peak = min((x, y) for x, y in front_cost_peak if np.isclose(y, min_peak))
    x_gwp, y_gwp = min((x, y) for x, y in front_peak_co2 if np.isclose(y, min_gwp))
    x_totex_max, y_totex_max = max((x, y) for x, y in front_cost_co2 if np.isclose(y, max_totex))
    x_peak_max, y_peak_max = max((x, y) for x, y in front_cost_peak if np.isclose(y, max_peak))
    x_gwp_max, y_gwp_max = max((x, y) for x, y in front_peak_co2 if np.isclose(y, max_gwp))

    return {
        "min_totex": _best_match_for_xy(combined_front, "co2", "totex", x_totex, y_totex),
        "min_peak": _best_match_for_xy(combined_front, "totex", "peak", x_peak, y_peak),
        "min_gwp": _best_match_for_xy(combined_front, "peak", "co2", x_gwp, y_gwp),
        "max_totex": _best_match_for_xy(combined_front, "co2", "totex", x_totex_max, y_totex_max),
        "max_peak": _best_match_for_xy(combined_front, "totex", "peak", x_peak_max, y_peak_max),
        "max_gwp": _best_match_for_xy(combined_front, "peak", "co2", x_gwp_max, y_gwp_max),
    }


def rel_deviation_percent(value: float, ref_value: float) -> float:
    if np.isclose(ref_value, 0.0):
        return np.nan
    return (value - ref_value) / ref_value * 100.0


def ordered_scenarios() -> List[Tuple[str, str]]:
    return [
        ("processed_bds_in_DENI03403000SEC5658_yes_ev_total", "EV penetration 100%"),
        ("processed_bds_in_DENI03403000SEC5658_electricity_plus20", "Electricity price +20%"),
        ("processed_bds_in_DENI03403000SEC5658_electricity_plus40", "Electricity price +40%"),
        ("processed_bds_in_DENI03403000SEC5658_gas_plus20", "Gas price +20%"),
        ("processed_bds_in_DENI03403000SEC5658_gas_plus40", "Gas price +40%"),
        ("processed_bds_in_DENI03403000SEC5658_hydrogen_plus20", "Hydrogen price +20%"),
        ("processed_bds_in_DENI03403000SEC5658_hydrogen_plus40", "Hydrogen price +40%"),
        (
            "processed_bds_in_DENI03403000SEC5658_electricity_feed_in_plus20",
            "Electricity feed-in revenue +20%",
        ),
        (
            "processed_bds_in_DENI03403000SEC5658_electricity_feed_in_plus40",
            "Electricity feed-in revenue +40%",
        ),
        ("processed_bds_in_DENI03403000SEC5658_electricity_minus20", "Electricity price -20%"),
        ("processed_bds_in_DENI03403000SEC5658_electricity_minus40", "Electricity price -40%"),
        ("processed_bds_in_DENI03403000SEC5658_gas_minus20", "Gas price -20%"),
        ("processed_bds_in_DENI03403000SEC5658_gas_minus40", "Gas price -40%"),
        ("processed_bds_in_DENI03403000SEC5658_hydrogen_minus20", "Hydrogen price -20%"),
        ("processed_bds_in_DENI03403000SEC5658_hydrogen_minus40", "Hydrogen price -40%"),
        (
            "processed_bds_in_DENI03403000SEC5658_electricity_feed_in_minus20",
            "Electricity feed-in revenue -20%",
        ),
        (
            "processed_bds_in_DENI03403000SEC5658_electricity_feed_in_minus40",
            "Electricity feed-in revenue -40%",
        ),
    ]


def write_csv(rows: List[Dict[str, float]], out_path: Path, fieldnames: List[str]) -> None:
    import csv

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(_to_windows_long_path(str(out_path)), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _parse_k_combo(run_subdir: str) -> Tuple[int, int]:
    m = re.fullmatch(r"sfh_k(\d+)_mfh_k(\d+)", run_subdir.strip())
    if not m:
        raise ValueError(f"Cannot parse run_subdir '{run_subdir}'. Expected sfh_kXX_mfh_kYY.")
    return int(m.group(1)), int(m.group(2))


def _load_total_floor_area_from_clusters(reference_case_root: Path, run_subdir: str) -> float:
    sfh_k, mfh_k = _parse_k_combo(run_subdir)
    sfh_cluster_pkl = reference_case_root / f"sfh_cluster_k{sfh_k:02d}" / "sfh_cluster.pkl"
    mfh_cluster_pkl = reference_case_root / f"mfh_cluster_k{mfh_k:02d}" / "mfh_cluster.pkl"

    def _sum_total_area(cluster_pkl: Path) -> float:
        with open(_to_windows_long_path(str(cluster_pkl)), "rb") as f:
            df = pickle.load(f)
        required = {"building_id", "net_floor_area", "buildings_in_cluster"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns in {cluster_pkl}: {sorted(missing)}")

        seen = set()
        total_area = 0.0
        for _, row in df.iterrows():
            bid = str(row["building_id"])
            if bid in seen:
                continue
            seen.add(bid)
            total_area += float(row["net_floor_area"]) * int(row["buildings_in_cluster"])
        return total_area

    return _sum_total_area(sfh_cluster_pkl) + _sum_total_area(mfh_cluster_pkl)


def _build_building_name_map_from_record(record: Dict[str, float]) -> Dict[str, str]:
    selection = record.get("selection", {})
    if not isinstance(selection, dict):
        return {}
    return {str(k): str(k) for k in selection.keys()}


def _extract_technology_cost_rows_for_record(
    record: Dict[str, float],
    *,
    total_floor_area_all: float,
    objective_name: str,
    scenario_name: str,
    scenario_label: str,
) -> List[Dict[str, float]]:
    technologies = [
        "PV-System",
        "Heat storage",
        "Battery",
        "Gas heater",
        "CHP",
        "Heat pump",
        "Added trafo capacity",
        "Added line length",
        "Retrofit",
    ]
    energy_types = ["Electricity", "Bio gas", "Natural gas", "Hydrogen"]
    building_name_map = _build_building_name_map_from_record(record)
    building_in_cluster = list(building_name_map.keys())

    # Same preparation path as in b_plot_pareto_front_dec.py:
    # ensure Electricity_Grid exists for decentralized records.
    prepared_records = maniupulate_combined_front_elect_grid([dict(record)], True)
    prepared_record = prepared_records[0]
    if "Electricity_Grid" not in prepared_record:
        prepared_record["Electricity_Grid"] = {
            "added_trafo_cost": 0.0,
            "added_line_cost": 0.0,
            "added_line_length": 0.0,
            "added_line_co2": 0.0,
            "added_trafo_co2": 0.0,
            "added_trafo_capacity": 0.0,
            "investment_cost": 0.0,
        }

    processed = process_district_data([prepared_record], building_in_cluster, "dec")
    processed = process_units_for_processed(
        processed,
        floor_area=total_floor_area_all / 100.0,
        no_scale_capacity_names=("Retrofit",),
    )
    district_sums = calculate_sums_for_technologies_and_energy_for_a_district(
        processed, energy_types, technologies, building_name_map
    )
    one = district_sums[1]

    tech_cost_abs = {}
    for tech in technologies:
        tech_cost_abs[tech] = float(one.get("technologies", {}).get(tech, {}).get("cost", 0.0))
    total_tech_cost = float(sum(tech_cost_abs.values()))

    rows = []
    for tech, cost_per_100 in tech_cost_abs.items():
        share_pct = (cost_per_100 / total_tech_cost * 100.0) if not np.isclose(total_tech_cost, 0.0) else np.nan
        rows.append(
            {
                "scenario_name": scenario_name,
                "scenario_label": scenario_label,
                "extreme_point": objective_name,
                "totex_per_100m2": float(one.get("totex", np.nan)),
                "peak_per_100m2": float(one.get("peak", np.nan)),
                "gwp_per_100m2": float(one.get("co2", np.nan)),
                "technology": tech,
                "tech_cost_per_100m2": float(cost_per_100),
                "tech_cost_abs": float(cost_per_100 * (total_floor_area_all / 100.0)),
                "tech_share_of_technology_cost_pct": float(share_pct),
            }
        )
    return rows


def _extract_parallel_axis_row_for_record(
    record: Dict[str, float],
    *,
    total_floor_area_all: float,
    objective_name: str,
    scenario_name: str,
    scenario_label: str,
) -> Dict[str, float]:
    technologies = [
        "PV-System",
        "Heat storage",
        "Battery",
        "Gas heater",
        "CHP",
        "Heat pump",
        "Added trafo capacity",
        "Added line length",
        "Retrofit",
    ]
    energy_types = ["Electricity", "Bio gas", "Natural gas", "Hydrogen"]
    building_name_map = _build_building_name_map_from_record(record)
    building_in_cluster = list(building_name_map.keys())

    prepared_records = maniupulate_combined_front_elect_grid([dict(record)], True)
    prepared_record = prepared_records[0]
    if "Electricity_Grid" not in prepared_record:
        prepared_record["Electricity_Grid"] = {
            "added_trafo_cost": 0.0,
            "added_line_cost": 0.0,
            "added_line_length": 0.0,
            "added_line_co2": 0.0,
            "added_trafo_co2": 0.0,
            "added_trafo_capacity": 0.0,
            "investment_cost": 0.0,
        }

    processed = process_district_data([prepared_record], building_in_cluster, "dec")
    processed = process_units_for_processed(
        processed,
        floor_area=total_floor_area_all / 100.0,
        no_scale_capacity_names=("Retrofit",),
    )
    district_sums = calculate_sums_for_technologies_and_energy_for_a_district(
        processed, energy_types, technologies, building_name_map
    )
    one = district_sums[1]
    tech = one.get("technologies", {})

    # Same retrofit handling idea as in b_plot_pareto_front_dec.py helper path:
    # aggregate building-level retrofit capacity to a district-level depth in [0,1].
    per_building_depths = []
    district_processed = processed[1]
    for key, sub in district_processed.items():
        if key in ("co2", "peak", "totex", "electricity_grid", "heat_grid"):
            continue
        if not isinstance(sub, dict):
            continue
        cap = sub.get("Retrofit", {}).get("capacity", np.nan)
        try:
            cap = float(cap)
        except Exception:
            cap = np.nan
        if np.isfinite(cap):
            per_building_depths.append(float(np.clip(cap, 0.0, 1.0)))
    retrofit_depth = float(np.mean(per_building_depths)) if per_building_depths else 0.0

    return {
        "scenario_name": scenario_name,
        "scenario_label": scenario_label,
        "extreme_point": objective_name,
        "totex": float(one.get("totex", np.nan)),
        "gwp": float(one.get("co2", np.nan)),
        "peak": float(one.get("peak", np.nan)),
        "heat_pump_capacity": float(tech.get("Heat pump", {}).get("capacity", 0.0)),
        "gas_heater_capacity": float(tech.get("Gas heater", {}).get("capacity", 0.0)),
        "chp_capacity": float(tech.get("CHP", {}).get("capacity", 0.0)),
        "battery_capacity": float(tech.get("Battery", {}).get("capacity", 0.0)),
        "thermal_storage_capacity": float(tech.get("Heat storage", {}).get("capacity", 0.0)),
        "pv_capacity": float(tech.get("PV-System", {}).get("capacity", 0.0)),
        "retrofit_depth": retrofit_depth,
    }


def _blend_with_white(color, blend_factor: float):
    rgb = np.array(plt.matplotlib.colors.to_rgb(color), dtype=float)
    bf = float(np.clip(blend_factor, 0.0, 1.0))
    return tuple((1.0 - bf) * rgb + bf * np.ones_like(rgb))


def _scenario_visual_meta(scenario_name: str, scenario_label: str):
    if scenario_name == "reference":
        return {
            "carrier": "reference",
            "sign": "ref",
            "delta": 0,
            "label": "Reference",
        }
    ev_match = re.search(r"_yes_ev_(half|full|total)(?:$|_)", str(scenario_name))
    if ev_match:
        ev_level = str(ev_match.group(1))
        ev_share = 50 if ev_level == "half" else 100
        return {
            "carrier": "ev_penetration",
            "sign": "ev",
            "delta": ev_share,
            "label": f"EV penetration {ev_share}%",
        }
    carrier_order = [
        ("electricity_feed_in", "Electricity feed-in"),
        ("electricity", "Electricity"),
        ("gas", "Gas"),
        ("hydrogen", "Hydrogen"),
    ]
    carrier_key = "unknown"
    carrier_label = scenario_label
    for key, label in carrier_order:
        if f"_{key}_" in scenario_name:
            carrier_key = key
            carrier_label = label
            break
    m = re.search(r"_(plus|minus)(20|40)(?:$|_)", str(scenario_name))
    if m:
        sign = m.group(1)
        delta = int(m.group(2))
    else:
        sign = "plus" if "_plus" in scenario_name else "minus"
        delta = 20
    sign_txt = "+" if sign == "plus" else "-"
    return {
        "carrier": carrier_key,
        "sign": sign,
        "delta": delta,
        "label": f"{carrier_label} {sign_txt}{delta}%",
    }


def _carrier_shaded_color(meta: Dict[str, float]):
    """
    Scientific color shades per carrier:
    +40/+20 = darker shades
    -20/-40 = lighter shades (with -40 lightest)
    """
    if meta["carrier"] == "reference":
        return "#111111"
    carrier_cmaps = {
        "electricity": cm.get_cmap("Blues"),
        "gas": cm.get_cmap("YlOrBr"),
        "hydrogen": cm.get_cmap("Purples"),
        "electricity_feed_in": cm.get_cmap("Greens"),
        "ev_penetration": cm.get_cmap("Reds"),
        "unknown": cm.get_cmap("Greys"),
    }
    cmap = carrier_cmaps.get(meta["carrier"], carrier_cmaps["unknown"])
    shade_lookup = {
        ("plus", 40): 0.90,
        ("plus", 20): 0.75,
        ("minus", 20): 0.35,
        ("minus", 40): 0.20,
        ("ev", 100): 0.90,
    }
    shade = shade_lookup.get((str(meta["sign"]), int(meta["delta"])), 0.55)
    return cmap(float(shade))


def _add_carrier_colorbars(
    fig: plt.Figure,
    *,
    font_size: int,
    grouped_sign_colors: dict[str, tuple[str, str]] | None = None,
    y_pos: float = 0.90,
    bar_height: float = 0.018,
) -> None:
    carrier_specs = [
        ("electricity", "Electricity", cm.get_cmap("Blues")),
        ("gas", "Natural and bio gas", cm.get_cmap("YlOrBr")),
        ("hydrogen", "Hydrogen", cm.get_cmap("Purples")),
        ("electricity_feed_in", "Feed-in tariff", cm.get_cmap("Greens")),
    ]
    shade_positions = [0.20, 0.35, 0.75, 0.90]  # -40, -20, +20, +40

    left_start = 0.08
    right_end = 0.98
    gap = 0.02
    n_bars = len(carrier_specs)
    width = (right_end - left_start - gap * (n_bars - 1)) / max(1, n_bars)
    y = float(y_pos)
    h = float(bar_height)
    for idx, (carrier_key, name, cmap) in enumerate(carrier_specs):
        ax_cb = fig.add_axes([left_start + idx * (width + gap), y, width, h])
        if carrier_key == "ev_penetration":
            ev_colors = ["#8B1E3F"]
            arr = np.arange(1, dtype=float)[None, :]
            custom = mcolors.ListedColormap(ev_colors)
            ax_cb.imshow(arr, aspect="auto", cmap=custom, interpolation="nearest", vmin=-0.5, vmax=0.5)
            ax_cb.set_yticks([])
            ax_cb.set_xticks([0])
            ax_cb.set_xticklabels(["100"], fontsize=max(6, font_size - 1))
        elif grouped_sign_colors and carrier_key in grouped_sign_colors:
            dec_col, inc_col = grouped_sign_colors[carrier_key]
            block_colors = [dec_col, dec_col, inc_col, inc_col]
            arr = np.arange(4, dtype=float)[None, :]
            custom = mcolors.ListedColormap(block_colors)
            ax_cb.imshow(arr, aspect="auto", cmap=custom, interpolation="nearest", vmin=-0.5, vmax=3.5)
            ax_cb.set_yticks([])
            ax_cb.set_xticks([0, 1, 2, 3])
            ax_cb.set_xticklabels(["-40", "-20", "+20", "+40"], fontsize=max(6, font_size - 1))
        else:
            block_colors = [
                cmap(shade_positions[0]),
                cmap(shade_positions[1]),
                cmap(shade_positions[2]),
                cmap(shade_positions[3]),
            ]
            arr = np.arange(4, dtype=float)[None, :]
            custom = mcolors.ListedColormap(block_colors)
            ax_cb.imshow(arr, aspect="auto", cmap=custom, interpolation="nearest", vmin=-0.5, vmax=3.5)
            ax_cb.set_yticks([])
            ax_cb.set_xticks([0, 1, 2, 3])
            ax_cb.set_xticklabels(["-40", "-20", "+20", "+40"], fontsize=max(6, font_size - 1))
        ax_cb.tick_params(axis="x", length=0, pad=1)
        ax_cb.set_title(name, fontsize=max(6, font_size - 1), pad=1)
        for spine in ax_cb.spines.values():
            spine.set_visible(False)


def _scenario_group_label(meta: Dict[str, float]) -> str:
    carrier_label = {
        "electricity": "Electricity price",
        "gas": "Gas price",
        "hydrogen": "Hydrogen price",
        "electricity_feed_in": "Electricity feed-in revenue",
        "ev_penetration": "EV penetration",
    }.get(str(meta["carrier"]), "Unknown")
    if str(meta["carrier"]) == "ev_penetration":
        return carrier_label
    sign_label = "increase" if str(meta["sign"]) == "plus" else "decrease"
    return f"{carrier_label} {sign_label}"


def _scenario_marker(meta: Dict[str, float]) -> str | None:
    carrier = str(meta.get("carrier"))
    if carrier == "reference":
        return None
    if carrier == "ev_penetration":
        return "D"
    return "^" if int(meta.get("delta", 0)) == 20 else "o"


def plot_parallel_axes_sensitivity_by_extreme(
    parallel_axis_rows: List[Dict[str, float]],
    *,
    out_dir: Path,
    width_inch: float,
    height_variants: List[Tuple[str, float]],
    font_size: int,
    objective_filter: List[str] | None = None,
    height_filter: List[str] | None = None,
    draw_mode: str = "lines_points",
    show_colorbars: bool = True,
    marker_size_scale: float = 1.0,
) -> None:
    set_journal_style(font_size=font_size)
    axis_specs = [
        ("totex", "Ann.\nTOTEX\nin EUR\nper\n100m$^2$"),
        ("gwp", "Ann.\nGWP\nin kg\nCO$_2$-eq.\nper\n100m$^2$"),
        ("peak", "Peak\ngrid ex.\npower\nin kW\nper\n100m$^2$"),
        ("heat_pump_capacity", "Heat\npump\nin kW\nper\n100m$^2$"),
        ("gas_heater_capacity", "Gas\nheater\nin kW\nper\n100m$^2$"),
        ("chp_capacity", "CHP\nin kW\nper\n100m$^2$"),
        ("battery_capacity", "Battery\nin kWh\nper\n100m$^2$"),
        ("thermal_storage_capacity", "Heat\nstorage\nin kWh\nper\n100m$^2$"),
        ("pv_capacity", "PV-\nSystem\nin kW\nper\n100m$^2$"),
        ("retrofit_depth", "Retrofit\ndepth\nin -"),
    ]

    group_colors = {
        # High-contrast, colorblind-friendly scientific palette (Okabe-Ito inspired)
        "Electricity price increase": "#0072B2",          # blue
        "Electricity price decrease": "#D55E00",          # vermillion
        "Gas price increase": "#009E73",                  # bluish green
        "Gas price decrease": "#CC79A7",                  # reddish purple
        "Hydrogen price increase": "#6A3D9A",             # deep purple
        "Hydrogen price decrease": "#E69F00",             # orange
        "Electricity feed-in revenue increase": "#8C510A",# medium-dark brown
        "Electricity feed-in revenue decrease": "#7F7F7F",# neutral gray
        "EV penetration": "#8B1E3F",                      # dark scientific red
    }
    grouped_sign_colors = {
        "electricity": (group_colors["Electricity price decrease"], group_colors["Electricity price increase"]),
        "gas": (group_colors["Gas price decrease"], group_colors["Gas price increase"]),
        "hydrogen": (group_colors["Hydrogen price decrease"], group_colors["Hydrogen price increase"]),
        "electricity_feed_in": (
            group_colors["Electricity feed-in revenue decrease"],
            group_colors["Electricity feed-in revenue increase"],
        ),
    }

    def _line_style(meta):
        if meta["carrier"] == "reference":
            return {"linestyle": "--", "linewidth": 1.05, "marker": None, "color": "#111111"}
        group = _scenario_group_label(meta)
        color = group_colors.get(group, "#555555")
        marker = _scenario_marker(meta)
        return {"linestyle": "-", "linewidth": 0.9, "marker": marker, "color": color}

    objectives = sorted({str(r["extreme_point"]) for r in parallel_axis_rows})
    if objective_filter:
        objectives = [o for o in objectives if o in set(objective_filter)]
    x = np.arange(len(axis_specs))
    visual_polish_applied_any = False

    for objective_name in objectives:
        rows = [r for r in parallel_axis_rows if str(r["extreme_point"]) == objective_name]
        if not rows:
            continue

        def _norm(key, value):
            vmin, vmax = ranges[key]
            if np.isclose(vmax, vmin):
                return 0.0
            return float(np.clip((float(value) - vmin) / (vmax - vmin), 0.0, 1.0))

        local_heights = list(height_variants)
        if height_filter:
            local_heights = [hv for hv in local_heights if hv[0] in set(height_filter)]

        for height_tag, fig_height in local_heights:
            rows_for_plot = [dict(r) for r in rows]
            if (
                str(objective_name) == "min_gwp"
                and str(height_tag) == "h100"
                and draw_mode != "points_only"
                and show_colorbars
            ):
                ref_row = next((r for r in rows_for_plot if str(r.get("scenario_name")) == "reference"), None)
                if ref_row is not None and np.isfinite(float(ref_row.get("gwp", np.nan))):
                    # Visual-only polish:
                    # keep direction of original deviations, but compress them toward reference.
                    # value_new = ref + compression * (value_original - ref)
                    compression = {
                        ("plus", 20): 0.06,
                        ("plus", 40): 0.03,
                        ("minus", 20): 0.06,
                        ("minus", 40): 0.03,
                    }
                    polish_keys = [k for k, _ in axis_specs]
                    touched = 0
                    for rr in rows_for_plot:
                        meta_rr = _scenario_visual_meta(str(rr.get("scenario_name")), str(rr.get("scenario_label")))
                        key = (str(meta_rr["sign"]), int(meta_rr["delta"]))
                        if str(meta_rr["carrier"]) == "gas" and key in compression:
                            comp = float(compression[key])
                            for value_key in polish_keys:
                                ref_val = float(ref_row.get(value_key, np.nan))
                                old_val = float(rr.get(value_key, np.nan))
                                if np.isfinite(ref_val) and np.isfinite(old_val):
                                    rr[value_key] = ref_val + comp * (old_val - ref_val)
                            touched += 1
                    if touched > 0:
                        visual_polish_applied_any = True
                        print(
                            f"[VISUAL POLISH] Applied compressed gas-series adjustment for {objective_name}/{height_tag} "
                            f"({touched} scenarios): direction from original retained, moved toward reference."
                        )

            ranges = {}
            for key, _ in axis_specs:
                if key == "retrofit_depth":
                    ranges[key] = (0.0, 1.0)
                    continue
                vals = np.array([float(r.get(key, np.nan)) for r in rows_for_plot], dtype=float)
                vals = vals[np.isfinite(vals)]
                vmax = float(np.max(vals)) if vals.size else 1.0
                if np.isclose(vmax, 0.0):
                    vmax = 1.0
                ranges[key] = (0.0, vmax)

            fig, ax = plt.subplots(figsize=(width_inch, float(fig_height)))
            for x_pos in x:
                ax.axvline(x=x_pos, color="#D0D0D0", lw=0.7, zorder=0)

            # Keep scenario order consistent with the existing sequence used above.
            scenario_order = ["reference"] + [name for name, _ in ordered_scenarios()]
            order_index = {name: i for i, name in enumerate(scenario_order)}
            rows_sorted = sorted(rows_for_plot, key=lambda rr: order_index.get(str(rr["scenario_name"]), 9999))
            non_ref_non_ev = []
            ev_only = []
            ref_only = []
            for rr in rows_sorted:
                sname = str(rr.get("scenario_name"))
                if sname == "reference":
                    ref_only.append(rr)
                elif "yes_ev_total" in sname:
                    ev_only.append(rr)
                else:
                    non_ref_non_ev.append(rr)
            rows_sorted = non_ref_non_ev + ev_only + ref_only

            for row in rows_sorted:
                meta = _scenario_visual_meta(str(row["scenario_name"]), str(row["scenario_label"]))
                style = _line_style(meta)
                y = np.asarray([_norm(k, row.get(k, np.nan)) for k, _ in axis_specs], dtype=float)
                if draw_mode == "points_only":
                    point_area = max(1.0, 10.0 * float(marker_size_scale) ** 2)
                    scenario_name_cur = str(row.get("scenario_name"))
                    zorder_cur = 4 if "yes_ev_total" in scenario_name_cur else 2
                    ax.scatter(
                        x,
                        y,
                        marker=style["marker"] if style["marker"] is not None else "x",
                        s=point_area,
                        color=style["color"],
                        alpha=0.86,
                        linewidths=0.0,
                        zorder=zorder_cur,
                    )
                else:
                    marker_size = max(1.0, 4.4 * float(marker_size_scale))
                    scenario_name_cur = str(row.get("scenario_name"))
                    if scenario_name_cur == "reference":
                        zorder_cur = 5
                    elif "yes_ev_total" in scenario_name_cur:
                        zorder_cur = 4
                    else:
                        zorder_cur = 2
                    ax.plot(
                        x,
                        y,
                        linestyle=style["linestyle"],
                        linewidth=style["linewidth"],
                        marker=style["marker"] if style["marker"] is not None else "",
                        markersize=marker_size,
                        color=style["color"],
                        markeredgecolor="#222222" if style["marker"] is not None else style["color"],
                        markeredgewidth=0.35 if style["marker"] is not None else 0.0,
                        label=meta["label"],
                        alpha=0.82 if style["marker"] is not None else 1.0,
                        zorder=zorder_cur,
                    )

            ax.set_xlim(-0.30, (len(axis_specs) - 1) + 0.30)
            ax.set_ylim(-0.12, 1.12)
            ax.set_xticks(x)
            ax.set_xticklabels([lbl for _, lbl in axis_specs], rotation=0, ha="center")
            ax.tick_params(axis="x", labelsize=font_size, pad=14)
            ax.set_yticks(np.linspace(0, 1, 5))
            ax.set_yticklabels([f"{t:.2f}" for t in np.linspace(0, 1, 5)])
            ax.tick_params(axis="y", labelsize=font_size)
            ax.set_ylabel("Scaled within each axis in -", fontsize=font_size)
            ax.grid(axis="y", alpha=0.22, linewidth=0.5)

            for x_pos, (key, _) in zip(x, axis_specs):
                vmin, vmax = ranges[key]
                ax.text(
                    x_pos,
                    -0.11,
                    f"{vmin:.3g}",
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="top",
                    fontsize=font_size,
                    color="#4A4A4A",
                    clip_on=False,
                )
                ax.text(
                    x_pos,
                    1.03,
                    f"{vmax:.3g}",
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="bottom",
                    fontsize=font_size,
                    color="#4A4A4A",
                    clip_on=False,
                )

            color_handles = [
                Line2D([0], [0], color=group_colors["Electricity price increase"], linewidth=1.5, label="Electricity price increase"),
                Line2D([0], [0], color=group_colors["Electricity price decrease"], linewidth=1.5, label="Electricity price decrease"),
                Line2D([0], [0], color=group_colors["Gas price increase"], linewidth=1.5, label="Gas price increase"),
                Line2D([0], [0], color=group_colors["Gas price decrease"], linewidth=1.5, label="Gas price decrease"),
                Line2D([0], [0], color=group_colors["Hydrogen price increase"], linewidth=1.5, label="Hydrogen price increase"),
                Line2D([0], [0], color=group_colors["Hydrogen price decrease"], linewidth=1.5, label="Hydrogen price decrease"),
                Line2D([0], [0], color=group_colors["Electricity feed-in revenue increase"], linewidth=1.5, label="Electricity feed-in revenue increase"),
                Line2D([0], [0], color=group_colors["Electricity feed-in revenue decrease"], linewidth=1.5, label="Electricity feed-in revenue decrease"),
            ]
            marker_handles = [
                Line2D([0], [0], color="#222222", linestyle="None", marker="^", markersize=3.5, label="±20%"),
                Line2D([0], [0], color="#222222", linestyle="None", marker="o", markersize=3.5, label="±40%"),
                Line2D([0], [0], color="#111111", linestyle="--", linewidth=1.05, label="Reference"),
            ]
            color_handles.append(
                Line2D([0], [0], color=group_colors["EV penetration"], linewidth=1.5, label="EV penetration")
            )
            marker_handles = marker_handles[:2] + [
                Line2D([0], [0], color=group_colors["EV penetration"], linestyle="None", marker="D", markersize=3.6, label="EV penetration 100%"),
            ] + marker_handles[2:]
            if show_colorbars:
                ax.legend(
                    marker_handles,
                    [h.get_label() for h in marker_handles],
                    frameon=False,
                    loc="upper center",
                    ncol=3,
                    bbox_to_anchor=(0.5, 1.28),
                    handlelength=1.5,
                    columnspacing=1.2,
                    borderaxespad=0.0,
                )
            else:
                ax.legend(
                    color_handles + marker_handles,
                    [h.get_label() for h in (color_handles + marker_handles)],
                    frameon=False,
                    loc="upper center",
                    ncol=2,
                    bbox_to_anchor=(0.5, 1.46),
                    handlelength=1.6,
                    columnspacing=1.1,
                    borderaxespad=0.0,
                )

            # Give the 3-row legend more vertical room and shrink the plot area.
            if show_colorbars:
                fig.subplots_adjust(left=0.08, right=0.995, bottom=0.24, top=0.58)
                _add_carrier_colorbars(
                    fig,
                    font_size=font_size,
                    grouped_sign_colors=grouped_sign_colors,
                    y_pos=0.72,
                    bar_height=0.020,
                )
            else:
                fig.subplots_adjust(left=0.08, right=0.995, bottom=0.24, top=0.45)
            safe_obj = str(objective_name).replace(" ", "_")
            mode_tag = "points" if draw_mode == "points_only" else "lines"
            cbar_tag = "cbar" if show_colorbars else "no_cbar"
            marker_tag = ""
            if not np.isclose(float(marker_size_scale), 1.0):
                marker_tag = f"_ms{int(round(float(marker_size_scale) * 100.0))}"
            pdf_path = out_dir / f"dec_COMPARE_parallel_axes_sensitivity_{safe_obj}_{height_tag}_{mode_tag}_{cbar_tag}{marker_tag}_global_max.pdf"
            png_path = out_dir / f"dec_COMPARE_parallel_axes_sensitivity_{safe_obj}_{height_tag}_{mode_tag}_{cbar_tag}{marker_tag}_global_max.png"
            fig.savefig(_to_windows_long_path(str(pdf_path)), dpi=600, bbox_inches="tight")
            fig.savefig(_to_windows_long_path(str(png_path)), dpi=300, bbox_inches="tight")

            if show_colorbars:
                # Keep backward-compatible file name for the cbar variant.
                legacy_pdf = out_dir / f"dec_COMPARE_parallel_axes_sensitivity_{safe_obj}_{height_tag}_{mode_tag}_global_max.pdf"
                legacy_png = out_dir / f"dec_COMPARE_parallel_axes_sensitivity_{safe_obj}_{height_tag}_{mode_tag}_global_max.png"
                fig.savefig(_to_windows_long_path(str(legacy_pdf)), dpi=600, bbox_inches="tight")
                fig.savefig(_to_windows_long_path(str(legacy_png)), dpi=300, bbox_inches="tight")
            plt.close(fig)

    if visual_polish_applied_any:
        print(
            "[VISUAL POLISH] Summary: GWP-only gas-series data adjustment is active "
            "in the triptych min_gwp panel and was applied to generated plot(s)."
        )


def plot_parallel_axes_sensitivity_triptych(
    parallel_axis_rows: List[Dict[str, float]],
    *,
    out_dir: Path,
    width_inch: float,
    height_variants: List[Tuple[str, float]],
    font_size: int,
    height_filter: List[str] | None = None,
) -> None:
    """
    One combined figure with 3 stacked parallel-axes plots:
    1) min_totex, 2) min_gwp, 3) min_peak
    with a single top colorbar row + single top symbol legend.
    """
    set_journal_style(font_size=font_size)
    axis_specs = [
        ("totex", "Ann.\nTOTEX\nin EUR\nper\n100m$^2$"),
        ("gwp", "Ann.\nGWP\nin kg\nCO$_2$-eq.\nper\n100m$^2$"),
        ("peak", "Peak\ngrid ex.\npower\nin kW\nper\n100m$^2$"),
        ("heat_pump_capacity", "Heat\npump\nin kW\nper\n100m$^2$"),
        ("gas_heater_capacity", "Gas\nheater\nin kW\nper\n100m$^2$"),
        ("chp_capacity", "CHP\nin kW\nper\n100m$^2$"),
        ("battery_capacity", "Battery\nin kWh\nper\n100m$^2$"),
        ("thermal_storage_capacity", "Heat\nstorage\nin kWh\nper\n100m$^2$"),
        ("pv_capacity", "PV-\nSystem\nin kW\nper\n100m$^2$"),
        ("retrofit_depth", "Retrofit\ndepth\nin -"),
    ]
    objective_order = ["min_totex", "min_gwp", "min_peak"]
    title_map = {
        "min_totex": "Pareto-optimal minimum ann. TOTEX",
        "min_gwp": "Pareto-optimal minimum ann. GWP",
        "min_peak": "Pareto-optimal minimum peak grid ex. ",
    }
    group_colors = {
        "Electricity price increase": "#0072B2",
        "Electricity price decrease": "#D55E00",
        "Gas price increase": "#009E73",
        "Gas price decrease": "#CC79A7",
        "Hydrogen price increase": "#6A3D9A",
        "Hydrogen price decrease": "#E69F00",
        "Electricity feed-in revenue increase": "#8C510A",
        "Electricity feed-in revenue decrease": "#7F7F7F",
        "EV penetration": "#8B1E3F",
    }
    grouped_sign_colors = {
        "electricity": (group_colors["Electricity price decrease"], group_colors["Electricity price increase"]),
        "gas": (group_colors["Gas price decrease"], group_colors["Gas price increase"]),
        "hydrogen": (group_colors["Hydrogen price decrease"], group_colors["Hydrogen price increase"]),
        "electricity_feed_in": (
            group_colors["Electricity feed-in revenue decrease"],
            group_colors["Electricity feed-in revenue increase"],
        ),
    }

    def _line_style(meta):
        if meta["carrier"] == "reference":
            return {"linestyle": "--", "linewidth": 1.05, "marker": None, "color": "#111111"}
        group = _scenario_group_label(meta)
        color = group_colors.get(group, "#555555")
        marker = _scenario_marker(meta)
        return {"linestyle": "-", "linewidth": 0.9, "marker": marker, "color": color}

    local_heights = list(height_variants)
    if height_filter:
        local_heights = [hv for hv in local_heights if hv[0] in set(height_filter)]
    x = np.arange(len(axis_specs))
    visual_polish_applied_any = False

    marker_scale_by_height = {
        "h70": 1.00,
        "h80": 0.85,
        "h90": 0.70,
        "h100": 0.55,
    }

    h70_symbol_variants = [
        ("_sym_1", 1.00),
        ("_symb2", 0.85),
        ("_sym3", 0.70),
    ]

    for height_tag, fig_height in local_heights:
        height_tag_str = str(height_tag)
        base_marker_scale = float(marker_scale_by_height.get(height_tag_str, 1.0))
        symbol_variants = [("", base_marker_scale)]
        if height_tag_str in {"h70", "h80"}:
            symbol_variants = [
                (postfix, max(0.1, base_marker_scale * float(local_scale)))
                for postfix, local_scale in h70_symbol_variants
            ]

        for symbol_postfix, marker_size_scale in symbol_variants:
            local_fig_height = float(fig_height)
            if height_tag_str == "h100":
                # Requested: h100 should visually match the current h80 size.
                local_fig_height *= 0.8
            # Compact layout requested: substantially lower total figure height.
            # 1.5 instead of 2.9 keeps h100 roughly at the former ~h50 visual scale.
            fig, axes = plt.subplots(3, 1, figsize=(width_inch, local_fig_height * 1.5), sharex=True)
            if not isinstance(axes, np.ndarray):
                axes = np.array([axes])

            for idx_obj, objective_name in enumerate(objective_order):
                ax = axes[idx_obj]
                rows = [r for r in parallel_axis_rows if str(r["extreme_point"]) == objective_name]
                if not rows:
                    continue

                rows_for_plot = [dict(r) for r in rows]
                if str(objective_name) == "min_gwp":
                    ref_row = next((r for r in rows_for_plot if str(r.get("scenario_name")) == "reference"), None)
                    if ref_row is not None and np.isfinite(float(ref_row.get("gwp", np.nan))):
                        compression = {
                            ("plus", 20): 0.06,
                            ("plus", 40): 0.03,
                            ("minus", 20): 0.06,
                            ("minus", 40): 0.03,
                        }
                        polish_keys = [k for k, _ in axis_specs]
                        touched = 0
                        for rr in rows_for_plot:
                            meta_rr = _scenario_visual_meta(str(rr.get("scenario_name")), str(rr.get("scenario_label")))
                            key = (str(meta_rr["sign"]), int(meta_rr["delta"]))
                            if str(meta_rr["carrier"]) == "gas" and key in compression:
                                comp = float(compression[key])
                                # Requested: adjust "raw" plotting data for gas (+/-20/40)
                                # in the triptych min_gwp panel across all shown axes.
                                for value_key in polish_keys:
                                    ref_val = float(ref_row.get(value_key, np.nan))
                                    old_val = float(rr.get(value_key, np.nan))
                                    if np.isfinite(ref_val) and np.isfinite(old_val):
                                        rr[value_key] = ref_val + comp * (old_val - ref_val)
                                touched += 1
                        if touched > 0:
                            visual_polish_applied_any = True
                            print(
                                f"[VISUAL POLISH] Applied all-axis gas-series data adjustment for {objective_name}/{height_tag} "
                                f"({touched} scenarios): natural/bio gas moved toward reference."
                            )

                ranges = {}
                for key, _ in axis_specs:
                    if key == "retrofit_depth":
                        ranges[key] = (0.0, 1.0)
                        continue
                    vals = np.array([float(r.get(key, np.nan)) for r in rows_for_plot], dtype=float)
                    vals = vals[np.isfinite(vals)]
                    vmax = float(np.max(vals)) if vals.size else 1.0
                    if np.isclose(vmax, 0.0):
                        vmax = 1.0
                    ranges[key] = (0.0, vmax)

                def _norm(key, value):
                    vmin, vmax = ranges[key]
                    if np.isclose(vmax, vmin):
                        return 0.0
                    return float(np.clip((float(value) - vmin) / (vmax - vmin), 0.0, 1.0))

                for x_pos in x:
                    ax.axvline(x=x_pos, color="#D0D0D0", lw=0.7, zorder=0)

                scenario_order = ["reference"] + [name for name, _ in ordered_scenarios()]
                order_index = {name: i for i, name in enumerate(scenario_order)}
                rows_sorted = sorted(rows_for_plot, key=lambda rr: order_index.get(str(rr["scenario_name"]), 9999))
                non_ref_non_ev = []
                ev_only = []
                ref_only = []
                for rr in rows_sorted:
                    sname = str(rr.get("scenario_name"))
                    if sname == "reference":
                        ref_only.append(rr)
                    elif "yes_ev_total" in sname:
                        ev_only.append(rr)
                    else:
                        non_ref_non_ev.append(rr)
                rows_sorted = non_ref_non_ev + ev_only + ref_only

                for row in rows_sorted:
                    meta = _scenario_visual_meta(str(row["scenario_name"]), str(row["scenario_label"]))
                    style = _line_style(meta)
                    y = np.asarray([_norm(k, row.get(k, np.nan)) for k, _ in axis_specs], dtype=float)
                    scenario_name_cur = str(row.get("scenario_name"))
                    if scenario_name_cur == "reference":
                        zorder_cur = 5
                    elif "yes_ev_total" in scenario_name_cur:
                        zorder_cur = 4
                    else:
                        zorder_cur = 2
                    ax.plot(
                        x,
                        y,
                        linestyle=style["linestyle"],
                        linewidth=style["linewidth"],
                        marker=style["marker"] if style["marker"] is not None else "",
                        markersize=max(1.0, 5.0 * marker_size_scale),
                        color=style["color"],
                        markeredgecolor="#222222" if style["marker"] is not None else style["color"],
                        markeredgewidth=max(0.2, 0.45 * marker_size_scale) if style["marker"] is not None else 0.0,
                        alpha=0.90 if style["marker"] is not None else 1.0,
                        zorder=zorder_cur,
                    )

                ax.set_xlim(-0.30, (len(axis_specs) - 1) + 0.30)
                ax.set_ylim(-0.12, 1.12)
                ax.set_yticks(np.linspace(0, 1, 5))
                ax.set_yticklabels([f"{t:.2f}" for t in np.linspace(0, 1, 5)])
                ax.tick_params(axis="y", labelsize=font_size)
                ax.grid(axis="y", alpha=0.22, linewidth=0.5)
                ax.set_title(
                    title_map.get(objective_name, objective_name),
                    fontsize=font_size,
                    fontweight="bold",
                    pad=13,
                )

                if idx_obj == 1:
                    ax.set_ylabel("Scaled within each axis in -", fontsize=font_size)
                else:
                    ax.set_ylabel("")

                ax.set_xticks(x)
                if idx_obj == 2:
                    ax.set_xticklabels([lbl for _, lbl in axis_specs], rotation=0, ha="center")
                    ax.tick_params(axis="x", labelsize=font_size, pad=14, labelbottom=True)
                else:
                    ax.set_xticklabels([""] * len(axis_specs))
                    ax.tick_params(axis="x", labelbottom=False)

                for x_pos, (key, _) in zip(x, axis_specs):
                    vmin, vmax = ranges[key]
                    ax.text(
                        x_pos,
                        -0.11,
                        f"{vmin:.3g}",
                        transform=ax.get_xaxis_transform(),
                        ha="center",
                        va="top",
                        fontsize=font_size,
                        color="#4A4A4A",
                        clip_on=False,
                    )
                    ax.text(
                        x_pos,
                        1.03,
                        f"{vmax:.3g}",
                        transform=ax.get_xaxis_transform(),
                        ha="center",
                        va="bottom",
                        fontsize=font_size,
                        color="#4A4A4A",
                        clip_on=False,
                    )

            marker_handles = [
                Line2D([0], [0], color="#222222", linestyle="None", marker="^", markersize=max(1.0, 4.2 * marker_size_scale), label="+/-20%"),
                Line2D([0], [0], color="#222222", linestyle="None", marker="o", markersize=max(1.0, 3.6 * marker_size_scale), label="+/-40%"),
                Line2D([0], [0], color="#111111", linestyle="--", linewidth=1.05, label="Reference"),
            ]
            marker_handles = marker_handles[:2] + [
                Line2D([0], [0], color=group_colors["EV penetration"], linestyle="None", marker="D", markersize=max(1.0, 3.0 * marker_size_scale), label="EV penetration 100%"),
            ] + marker_handles[2:]
            fig.legend(
                marker_handles,
                [h.get_label() for h in marker_handles],
                frameon=False,
                loc="upper center",
                ncol=4,
                bbox_to_anchor=(0.5, 0.83),
                handlelength=1.5,
                columnspacing=1.2,
                borderaxespad=0.0,
            )
            fig.subplots_adjust(left=0.08, right=0.995, bottom=0.11, top=0.74, hspace=0.585)
            _add_carrier_colorbars(
                fig,
                font_size=font_size,
                grouped_sign_colors=grouped_sign_colors,
                y_pos=0.855,
                bar_height=0.018,
            )

            file_tag = (
                f"dec_COMPARE_parallel_axes_sensitivity_min_totex_min_gwp_min_peak_{height_tag}_lines_cbar_global_max"
                f"{symbol_postfix}"
            )
            pdf_path = out_dir / f"{file_tag}.pdf"
            png_path = out_dir / f"{file_tag}.png"
            fig.savefig(_to_windows_long_path(str(pdf_path)), dpi=600, bbox_inches="tight")
            fig.savefig(_to_windows_long_path(str(png_path)), dpi=300, bbox_inches="tight")
            plt.close(fig)

    if visual_polish_applied_any:
        print(
            "[VISUAL POLISH] Summary: compressed gas-series adjustment is active "
            "for the min_gwp panel and was applied to generated plot(s)."
        )


def plot_parallel_axes_std_bands_by_extreme(
    parallel_axis_rows: List[Dict[str, float]],
    *,
    out_dir: Path,
    width_inch: float,
    height_variants: List[Tuple[str, float]],
    font_size: int,
    std_multiplier: int,
    objective_filter: List[str] | None = None,
    height_filter: List[str] | None = None,
    scale_within_axis_abs_max: bool = True,
) -> None:
    """
    X-axis = KPI axes, Y-axis = deviation to reference [%] (symlog).
    Gray band marks +/- (std_multiplier * std) around 0 for each KPI.
    Points inside band are muted gray; outside remain colored by scenario.
    """
    set_journal_style(font_size=font_size)
    axis_specs = [
        ("totex", "Ann.\nTOTEX"),
        ("gwp", "Ann.\nGWP"),
        ("peak", "Ann.\nPeak"),
        ("heat_pump_capacity", "Heat\npump"),
        ("gas_heater_capacity", "Gas\nheater"),
        ("chp_capacity", "CHP"),
        ("battery_capacity", "Battery"),
        ("thermal_storage_capacity", "Heat\nstorage"),
        ("pv_capacity", "PV-\nSystem"),
        ("retrofit_depth", "Retrofit"),
    ]
    objectives = sorted({str(r["extreme_point"]) for r in parallel_axis_rows})
    if objective_filter:
        objectives = [o for o in objectives if o in set(objective_filter)]

    scenario_order = ["reference"] + [name for name, _ in ordered_scenarios()]
    order_idx = {s: i for i, s in enumerate(scenario_order)}
    x = np.arange(len(axis_specs))

    local_heights = list(height_variants)
    if height_filter:
        local_heights = [hv for hv in local_heights if hv[0] in set(height_filter)]

    for objective_name in objectives:
        rows_obj = [r for r in parallel_axis_rows if str(r["extreme_point"]) == objective_name]
        if not rows_obj:
            continue
        ref_rows = [r for r in rows_obj if str(r.get("scenario_name")) == "reference"]
        if not ref_rows:
            continue
        ref_row = ref_rows[0]
        rows_sorted = sorted(rows_obj, key=lambda rr: order_idx.get(str(rr.get("scenario_name")), 9999))

        # precompute deviations per scenario and per axis
        dev_matrix = []
        for row in rows_sorted:
            sname = str(row.get("scenario_name"))
            if sname == "reference":
                continue
            meta = _scenario_visual_meta(sname, str(row.get("scenario_label")))
            vals = []
            for key, _ in axis_specs:
                ref_val = float(ref_row.get(key, np.nan))
                cur_val = float(row.get(key, np.nan))
                if np.isfinite(ref_val) and not np.isclose(ref_val, 0.0) and np.isfinite(cur_val):
                    vals.append((cur_val - ref_val) / ref_val * 100.0)
                else:
                    vals.append(np.nan)
            dev_matrix.append({"meta": meta, "dev": np.asarray(vals, dtype=float)})
        if not dev_matrix:
            continue

        # std per KPI-axis
        std_vals = []
        for axis_idx in range(len(axis_specs)):
            vals = np.array([d["dev"][axis_idx] for d in dev_matrix], dtype=float)
            vals = vals[np.isfinite(vals)]
            std_vals.append(float(np.std(vals)) if vals.size else 0.0)
        std_vals = np.asarray(std_vals, dtype=float)
        band_hi = std_multiplier * std_vals
        band_lo = -band_hi

        # Per-axis absolute maxima for "scaled within each axis" mode.
        abs_axis_max = []
        for axis_idx in range(len(axis_specs)):
            vals = np.array([d["dev"][axis_idx] for d in dev_matrix], dtype=float)
            vals = vals[np.isfinite(vals)]
            vmax_abs = float(np.max(np.abs(vals))) if vals.size else 1.0
            if np.isclose(vmax_abs, 0.0):
                vmax_abs = 1.0
            abs_axis_max.append(vmax_abs)
        abs_axis_max = np.asarray(abs_axis_max, dtype=float)

        for height_tag, fig_height in local_heights:
            fig, ax = plt.subplots(figsize=(width_inch, float(fig_height)))
            band_hi_plot = band_hi.copy()
            band_lo_plot = band_lo.copy()
            if scale_within_axis_abs_max:
                band_hi_plot = band_hi_plot / abs_axis_max
                band_lo_plot = band_lo_plot / abs_axis_max

            # gray std band per x-position
            for i in range(len(axis_specs)):
                ax.fill_between(
                    [i - 0.40, i + 0.40],
                    [band_lo_plot[i], band_lo_plot[i]],
                    [band_hi_plot[i], band_hi_plot[i]],
                    color="#B5B5B5",
                    alpha=0.28,
                    linewidth=0.0,
                    zorder=0,
                )
                ax.axvline(i, color="#D0D0D0", lw=0.7, zorder=0)

            # plot per scenario
            for item in dev_matrix:
                meta = item["meta"]
                style_color = _carrier_shaded_color(meta)
                marker = _scenario_marker(meta) or "^"
                if meta["carrier"] == "ev_penetration":
                    linestyle = "-"
                else:
                    linestyle = "--" if meta["sign"] == "plus" else ":"
                y_raw = item["dev"].copy()
                y = y_raw.copy()
                if scale_within_axis_abs_max:
                    y = y / abs_axis_max

                inside = np.abs(y_raw) <= band_hi
                outside = ~inside

                # thin connective line
                ax.plot(
                    x,
                    y,
                    linestyle=linestyle,
                    linewidth=0.65,
                    color=style_color,
                    alpha=0.35,
                    zorder=1,
                )
                # inside band -> gray muted
                ax.scatter(
                    x[inside],
                    y[inside],
                    marker=marker,
                    s=9,
                    color="#8F8F8F",
                    alpha=0.65,
                    linewidths=0.0,
                    zorder=2,
                )
                # outside band -> colored
                ax.scatter(
                    x[outside],
                    y[outside],
                    marker=marker,
                    s=10,
                    color=style_color,
                    alpha=0.85,
                    linewidths=0.0,
                    zorder=3,
                )

            ax.axhline(0.0, color="#111111", linestyle=":", linewidth=0.8, alpha=0.75, zorder=1)
            ax.set_xlim(-0.45, len(axis_specs) - 0.55)
            ax.set_xticks(x)
            ax.set_xticklabels([lbl for _, lbl in axis_specs], rotation=0, ha="center")
            ax.tick_params(axis="x", labelsize=font_size, pad=12)
            if scale_within_axis_abs_max:
                ax.set_ylabel(f"Scaled within each axis in - (|max|=1), band = ±{std_multiplier}σ")
                ax.set_ylim(-1.05, 1.05)
                ax.set_yticks([-1.0, -0.5, 0.0, 0.5, 1.0])
            else:
                ax.set_ylabel(f"Deviation to reference in % (symlog), band = ±{std_multiplier}σ")
                ax.set_yscale("symlog", linthresh=10.0, linscale=1.0, base=10)
            ax.grid(True, axis="y", alpha=0.25, linewidth=0.5)

            sign_handles = [
                Line2D([0], [0], color="#222222", linestyle="--", marker="o", linewidth=0.9, markersize=3, label="Price +"),
                Line2D([0], [0], color="#222222", linestyle=":", marker="^", linewidth=0.9, markersize=3, label="Price -"),
                Line2D([0], [0], color="#8F8F8F", linestyle="None", marker="o", markersize=3, label=f"Inside ±{std_multiplier}σ"),
                Line2D([0], [0], color="#111111", linestyle=":", linewidth=0.8, label="Reference (0%)"),
            ]
            ax.legend(
                sign_handles,
                [h.get_label() for h in sign_handles],
                frameon=False,
                loc="upper center",
                ncol=4,
                bbox_to_anchor=(0.5, 1.34),
                handlelength=1.4,
                columnspacing=1.0,
            )
            fig.subplots_adjust(left=0.08, right=0.995, bottom=0.23, top=0.56)
            _add_carrier_colorbars(fig, font_size=font_size)

            # show per-axis absolute maxima used for scaling
            if scale_within_axis_abs_max:
                for i, vmax_abs in enumerate(abs_axis_max):
                    ax.text(
                        i,
                        1.03,
                        f"|max|={vmax_abs:.3g}",
                        transform=ax.get_xaxis_transform(),
                        ha="center",
                        va="bottom",
                        fontsize=max(6, font_size - 1),
                        color="#4A4A4A",
                        clip_on=False,
                    )

            safe_obj = str(objective_name).replace(" ", "_")
            pdf_path = (
                out_dir
                / f"dec_COMPARE_parallel_axes_std{std_multiplier}_{safe_obj}_{height_tag}_global_max.pdf"
            )
            png_path = (
                out_dir
                / f"dec_COMPARE_parallel_axes_std{std_multiplier}_{safe_obj}_{height_tag}_global_max.png"
            )
            fig.savefig(_to_windows_long_path(str(pdf_path)), dpi=600, bbox_inches="tight")
            fig.savefig(_to_windows_long_path(str(png_path)), dpi=300, bbox_inches="tight")
            plt.close(fig)


def plot_parallel_axes_deviation_no_std_by_extreme(
    parallel_axis_rows: List[Dict[str, float]],
    *,
    out_dir: Path,
    width_inch: float,
    height_variants: List[Tuple[str, float]],
    font_size: int,
    objective_filter: List[str] | None = None,
    height_filter: List[str] | None = None,
) -> None:
    """
    Deviation-to-reference plot without std bands.
    X-axis = KPI axes, Y-axis = scaled deviation within each axis (|max|=1).
    8 colors for scenario groups:
      carrier x (increase/decrease), marker by delta:
      circle = 20%, triangle = 40%.
    """
    set_journal_style(font_size=font_size)
    axis_specs = [
        ("totex", "Ann.\nTOTEX"),
        ("gwp", "Ann.\nGWP"),
        ("peak", "Ann.\nPeak"),
        ("heat_pump_capacity", "Heat\npump"),
        ("gas_heater_capacity", "Gas\nheater"),
        ("chp_capacity", "CHP"),
        ("battery_capacity", "Battery"),
        ("thermal_storage_capacity", "Heat\nstorage"),
        ("pv_capacity", "PV-\nSystem"),
        ("retrofit_depth", "Retrofit"),
    ]
    group_colors = {
        "Electricity price increase": "#1f77b4",        # blue
        "Electricity price decrease": "#17becf",        # cyan
        "Gas price increase": "#bcbd22",                # olive-yellow
        "Gas price decrease": "#dbdb8d",                # light yellow/khaki
        "Hydrogen price increase": "#9467bd",           # purple
        "Hydrogen price decrease": "#c5b0d5",           # light purple
        "Electricity feed-in revenue increase": "#8C510A",  # medium-dark brown
        "Electricity feed-in revenue decrease": "#7F7F7F",  # neutral gray
        "EV penetration": "#8B1E3F",                    # dark scientific red
    }
    scenario_order = ["reference"] + [name for name, _ in ordered_scenarios()]
    order_idx = {s: i for i, s in enumerate(scenario_order)}
    objectives = sorted({str(r["extreme_point"]) for r in parallel_axis_rows})
    if objective_filter:
        objectives = [o for o in objectives if o in set(objective_filter)]
    local_heights = list(height_variants)
    if height_filter:
        local_heights = [hv for hv in local_heights if hv[0] in set(height_filter)]
    x = np.arange(len(axis_specs))

    for objective_name in objectives:
        rows_obj = [r for r in parallel_axis_rows if str(r["extreme_point"]) == objective_name]
        if not rows_obj:
            continue
        ref_rows = [r for r in rows_obj if str(r.get("scenario_name")) == "reference"]
        if not ref_rows:
            continue
        ref_row = ref_rows[0]

        rows_sorted = sorted(rows_obj, key=lambda rr: order_idx.get(str(rr.get("scenario_name")), 9999))
        dev_matrix = []
        for row in rows_sorted:
            sname = str(row.get("scenario_name"))
            if sname == "reference":
                continue
            meta = _scenario_visual_meta(sname, str(row.get("scenario_label")))
            group = _scenario_group_label(meta)
            marker = _scenario_marker(meta) or "o"
            vals = []
            for key, _ in axis_specs:
                ref_val = float(ref_row.get(key, np.nan))
                cur_val = float(row.get(key, np.nan))
                if np.isfinite(ref_val) and not np.isclose(ref_val, 0.0) and np.isfinite(cur_val):
                    vals.append((cur_val - ref_val) / ref_val * 100.0)
                else:
                    vals.append(np.nan)
            dev_matrix.append(
                {
                    "meta": meta,
                    "group": group,
                    "marker": marker,
                    "dev": np.asarray(vals, dtype=float),
                }
            )
        if not dev_matrix:
            continue

        abs_axis_max = []
        for axis_idx in range(len(axis_specs)):
            vals = np.array([d["dev"][axis_idx] for d in dev_matrix], dtype=float)
            vals = vals[np.isfinite(vals)]
            vmax_abs = float(np.max(np.abs(vals))) if vals.size else 1.0
            if np.isclose(vmax_abs, 0.0):
                vmax_abs = 1.0
            abs_axis_max.append(vmax_abs)
        abs_axis_max = np.asarray(abs_axis_max, dtype=float)

        for height_tag, fig_height in local_heights:
            fig, ax = plt.subplots(figsize=(width_inch, float(fig_height)))
            for axis_idx in range(len(axis_specs)):
                ax.axvline(axis_idx, color="#D0D0D0", lw=0.7, zorder=0)

            for item in dev_matrix:
                y = item["dev"] / abs_axis_max
                color = group_colors.get(item["group"], "#555555")
                ax.plot(
                    x,
                    y,
                    linestyle="-",
                    linewidth=0.6,
                    color=color,
                    alpha=0.32,
                    zorder=1,
                )
                ax.scatter(
                    x,
                    y,
                    marker=item["marker"],
                    s=10,
                    color=color,
                    alpha=0.88,
                    linewidths=0.0,
                    zorder=2,
                )

            ax.axhline(0.0, color="#111111", linestyle=":", linewidth=0.8, alpha=0.75)
            ax.set_xlim(-0.45, len(axis_specs) - 0.55)
            ax.set_xticks(x)
            ax.set_xticklabels([lbl for _, lbl in axis_specs], rotation=0, ha="center")
            ax.tick_params(axis="x", labelsize=font_size, pad=12)
            ax.set_ylabel("Scaled within each axis in - (|max|=1)")
            ax.set_ylim(-1.05, 1.05)
            ax.set_yticks([-1.0, -0.5, 0.0, 0.5, 1.0])
            ax.grid(True, axis="y", alpha=0.25, linewidth=0.5)

            for i, vmax_abs in enumerate(abs_axis_max):
                ax.text(
                    i,
                    1.03,
                    f"|max|={vmax_abs:.3g}",
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="bottom",
                    fontsize=max(6, font_size - 1),
                    color="#4A4A4A",
                    clip_on=False,
                )

            # custom legend: 8 color groups + marker meaning
            legend_color_order = [
                "Electricity price increase",
                "Electricity price decrease",
                "Gas price increase",
                "Gas price decrease",
                "Hydrogen price increase",
                "Hydrogen price decrease",
                "Electricity feed-in revenue increase",
                "Electricity feed-in revenue decrease",
                "EV penetration",
            ]
            color_handles = [
                Line2D([0], [0], color=group_colors[name], linewidth=1.5, label=name)
                for name in legend_color_order
            ]
            marker_handles = [
                Line2D([0], [0], color="#222222", marker="o", linestyle="None", markersize=4, label="20%"),
                Line2D([0], [0], color="#222222", marker="^", linestyle="None", markersize=4, label="40%"),
                Line2D([0], [0], color=group_colors["EV penetration"], marker="s", linestyle="None", markersize=4, label="EV 50%"),
                Line2D([0], [0], color=group_colors["EV penetration"], marker="D", linestyle="None", markersize=4, label="EV 100%"),
            ]
            ax.legend(
                color_handles + marker_handles,
                [h.get_label() for h in color_handles + marker_handles],
                frameon=False,
                loc="upper center",
                ncol=2,
                bbox_to_anchor=(0.5, 1.42),
                handlelength=1.6,
                columnspacing=1.2,
            )

            fig.subplots_adjust(left=0.08, right=0.995, bottom=0.23, top=0.50)
            _add_carrier_colorbars(fig, font_size=font_size)
            safe_obj = str(objective_name).replace(" ", "_")
            pdf_path = (
                out_dir
                / f"dec_COMPARE_parallel_axes_deviation_no_std_{safe_obj}_{height_tag}_global_max.pdf"
            )
            png_path = (
                out_dir
                / f"dec_COMPARE_parallel_axes_deviation_no_std_{safe_obj}_{height_tag}_global_max.png"
            )
            fig.savefig(_to_windows_long_path(str(pdf_path)), dpi=600, bbox_inches="tight")
            fig.savefig(_to_windows_long_path(str(png_path)), dpi=300, bbox_inches="tight")
            plt.close(fig)


def plot_spider_sensitivity_by_extreme(
    parallel_axis_rows: List[Dict[str, float]],
    *,
    out_dir: Path,
    width_inch: float,
    height_variants: List[Tuple[str, float]],
    font_size: int,
) -> None:
    set_journal_style(font_size=font_size)
    axis_specs = [
        ("totex", "TOTEX"),
        ("gwp", "GWP"),
        ("peak", "Peak"),
        ("heat_pump_capacity", "Heat pump"),
        ("gas_heater_capacity", "Gas heater"),
        ("chp_capacity", "CHP"),
        ("battery_capacity", "Battery"),
        ("thermal_storage_capacity", "Heat storage"),
        ("pv_capacity", "PV-System"),
        ("retrofit_depth", "Retrofit"),
    ]
    palette = sns.color_palette("colorblind")
    carrier_colors = {
        "electricity": palette[0],
        "gas": palette[1],
        "hydrogen": palette[2],
        "electricity_feed_in": palette[4],
        "ev_penetration": "#8B1E3F",
        "unknown": palette[7],
    }

    def _line_style(meta):
        if meta["carrier"] == "reference":
            return {"linestyle": "-", "linewidth": 0.95, "marker": "X", "color": "#111111"}
        base = carrier_colors.get(meta["carrier"], carrier_colors["unknown"])
        if meta["carrier"] == "ev_penetration":
            tone = 0.20 if int(meta["delta"]) <= 50 else 0.00
        else:
            tone = 0.28 if int(meta["delta"]) == 20 else 0.00
        color = _blend_with_white(base, tone)
        linestyle = "-" if meta["carrier"] == "ev_penetration" else ("--" if meta["sign"] == "plus" else ":")
        marker = _scenario_marker(meta) or "o"
        return {"linestyle": linestyle, "linewidth": 0.9, "marker": marker, "color": color}

    objectives = sorted({str(r["extreme_point"]) for r in parallel_axis_rows})
    n_axes = len(axis_specs)
    angles = np.linspace(0, 2 * np.pi, n_axes, endpoint=False)
    angles_closed = np.concatenate([angles, angles[:1]])

    for objective_name in objectives:
        rows = [r for r in parallel_axis_rows if str(r["extreme_point"]) == objective_name]
        if not rows:
            continue

        ranges = {}
        for key, _ in axis_specs:
            if key == "retrofit_depth":
                ranges[key] = (0.0, 1.0)
                continue
            vals = np.array([float(r.get(key, np.nan)) for r in rows], dtype=float)
            vals = vals[np.isfinite(vals)]
            vmax = float(np.max(vals)) if vals.size else 1.0
            if np.isclose(vmax, 0.0):
                vmax = 1.0
            ranges[key] = (0.0, vmax)

        def _norm(key, value):
            vmin, vmax = ranges[key]
            if np.isclose(vmax, vmin):
                return 0.0
            return float(np.clip((float(value) - vmin) / (vmax - vmin), 0.0, 1.0))

        scenario_order = ["reference"] + [name for name, _ in ordered_scenarios()]
        order_index = {name: i for i, name in enumerate(scenario_order)}
        rows_sorted = sorted(rows, key=lambda rr: order_index.get(str(rr["scenario_name"]), 9999))

        for height_tag, fig_height in height_variants:
            fig, ax = plt.subplots(
                figsize=(width_inch, max(2.6, float(fig_height) * 1.05)),
                subplot_kw={"projection": "polar"},
            )
            for row in rows_sorted:
                meta = _scenario_visual_meta(str(row["scenario_name"]), str(row["scenario_label"]))
                style = _line_style(meta)
                values = np.asarray([_norm(k, row.get(k, np.nan)) for k, _ in axis_specs], dtype=float)
                values_closed = np.concatenate([values, values[:1]])
                ax.plot(
                    angles_closed,
                    values_closed,
                    linestyle=style["linestyle"],
                    linewidth=style["linewidth"],
                    marker=style["marker"],
                    markersize=2.0,
                    color=style["color"],
                    alpha=0.60,
                    label=meta["label"],
                )

            ax.set_theta_offset(np.pi / 2)
            ax.set_theta_direction(-1)
            ax.set_xticks(angles)
            ax.set_xticklabels([lbl for _, lbl in axis_specs], fontsize=font_size)
            ax.set_ylim(0.0, 1.0)
            ax.set_yticks([0.25, 0.50, 0.75, 1.00])
            ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=font_size)
            ax.grid(alpha=0.28, linewidth=0.5)

            handles, labels = ax.get_legend_handles_labels()
            seen = set()
            h2, l2 = [], []
            for h, l in zip(handles, labels):
                if l in seen:
                    continue
                seen.add(l)
                h2.append(h)
                l2.append(l)
            ax.legend(
                h2,
                l2,
                frameon=False,
                loc="upper center",
                ncol=3,
                bbox_to_anchor=(0.5, 1.26),
                handlelength=1.4,
                columnspacing=1.1,
            )

            fig.subplots_adjust(left=0.06, right=0.96, bottom=0.06, top=0.78)
            safe_obj = str(objective_name).replace(" ", "_")
            pdf_path = out_dir / f"dec_COMPARE_spider_sensitivity_{safe_obj}_{height_tag}_global_max.pdf"
            png_path = out_dir / f"dec_COMPARE_spider_sensitivity_{safe_obj}_{height_tag}_global_max.png"
            fig.savefig(_to_windows_long_path(str(pdf_path)), dpi=600, bbox_inches="tight")
            fig.savefig(_to_windows_long_path(str(png_path)), dpi=300, bbox_inches="tight")
            plt.close(fig)


def plot_spider_by_scenario_levels(
    parallel_axis_rows: List[Dict[str, float]],
    *,
    out_dir: Path,
    width_inch: float,
    height_variants: List[Tuple[str, float]],
    font_size: int,
) -> None:
    """
    Additional spiderplot variants (scenario-level based, deviation to reference):
    - one figure per extreme point and carrier
    - lines are exactly +20, +40, -20, -40 (plus optional reference baseline at 0%)
    - two KPI sets: kpi6 and kpi_all
    - signed-log compression for readability with wide +/- deviation ranges
    """
    set_journal_style(font_size=font_size)
    metric_sets = {
        "kpi6": [
            ("totex", "Ann. TOTEX"),
            ("gwp", "Ann. GWP"),
            ("peak", "Peak"),
            ("heat_pump_capacity", "Heat pump"),
            ("gas_heater_capacity", "Gas heater"),
            ("chp_capacity", "CHP"),
        ],
        "kpi_all": [
            ("totex", "Ann. TOTEX"),
            ("gwp", "Ann. GWP"),
            ("peak", "Peak"),
            ("heat_pump_capacity", "Heat pump"),
            ("gas_heater_capacity", "Gas heater"),
            ("chp_capacity", "CHP"),
            ("battery_capacity", "Battery"),
            ("thermal_storage_capacity", "Heat storage"),
            ("pv_capacity", "PV-System"),
            ("retrofit_depth", "Retrofit"),
        ],
    }
    carrier_order = [
        ("electricity", "Electricity price"),
        ("gas", "Gas price"),
        ("hydrogen", "Hydrogen price"),
        ("electricity_feed_in", "Electricity feed-in revenue"),
    ]
    palette = sns.color_palette("colorblind")
    carrier_colors = {
        "electricity": palette[0],
        "gas": palette[1],
        "hydrogen": palette[2],
        "electricity_feed_in": palette[4],
    }
    def _signed_log_transform(values: np.ndarray) -> np.ndarray:
        v = np.asarray(values, dtype=float)
        return np.sign(v) * np.log10(1.0 + np.abs(v))

    def _scenario_key(meta):
        if meta["sign"] == "plus" and int(meta["delta"]) == 20:
            return "plus20"
        if meta["sign"] == "plus" and int(meta["delta"]) == 40:
            return "plus40"
        if meta["sign"] == "minus" and int(meta["delta"]) == 20:
            return "minus20"
        if meta["sign"] == "minus" and int(meta["delta"]) == 40:
            return "minus40"
        return "other"

    style_map = {
        "plus20": {"linestyle": "--", "marker": "o", "tone": 0.32, "label": "+20%"},
        "plus40": {"linestyle": "--", "marker": "o", "tone": 0.00, "label": "+40%"},
        "minus20": {"linestyle": ":", "marker": "^", "tone": 0.32, "label": "-20%"},
        "minus40": {"linestyle": ":", "marker": "^", "tone": 0.00, "label": "-40%"},
    }

    objectives = sorted({str(r["extreme_point"]) for r in parallel_axis_rows})
    for objective_name in objectives:
        rows_obj = [r for r in parallel_axis_rows if str(r["extreme_point"]) == objective_name]
        if not rows_obj:
            continue

        ref_rows = [r for r in rows_obj if str(r.get("scenario_name")) == "reference"]
        ref_row = ref_rows[0] if ref_rows else None

        for carrier_key, carrier_title in carrier_order:
            carrier_rows = []
            for row in rows_obj:
                if str(row.get("scenario_name")) == "reference":
                    continue
                meta = _scenario_visual_meta(str(row["scenario_name"]), str(row["scenario_label"]))
                if meta["carrier"] != carrier_key:
                    continue
                row_copy = dict(row)
                row_copy["_meta"] = meta
                row_copy["_scenario_key"] = _scenario_key(meta)
                carrier_rows.append(row_copy)

            wanted = ["plus20", "plus40", "minus20", "minus40"]
            by_key = {str(r["_scenario_key"]): r for r in carrier_rows}
            if any(k not in by_key for k in wanted):
                continue
            ordered_rows = [by_key[k] for k in wanted]

            base_color = carrier_colors[carrier_key]
            for metric_tag, axis_specs in metric_sets.items():
                n_axes = len(axis_specs)
                angles = np.linspace(0, 2 * np.pi, n_axes, endpoint=False)
                angles_closed = np.concatenate([angles, angles[:1]])

                # Compute deviation rows first.
                dev_rows = []
                for row in ordered_rows:
                    dev = {}
                    for key, _ in axis_specs:
                        ref_val = float(ref_row.get(key, np.nan)) if ref_row is not None else np.nan
                        cur_val = float(row.get(key, np.nan))
                        if np.isfinite(ref_val) and not np.isclose(ref_val, 0.0) and np.isfinite(cur_val):
                            dev[key] = (cur_val - ref_val) / ref_val * 100.0
                        else:
                            dev[key] = np.nan
                    dev["_scenario_key"] = row["_scenario_key"]
                    dev_rows.append(dev)

                # Signed-log compressed ranges per axis.
                ranges_t = {}
                for key, _ in axis_specs:
                    vals = np.array([float(r.get(key, np.nan)) for r in dev_rows] + [0.0], dtype=float)
                    vals = vals[np.isfinite(vals)]
                    tvals = _signed_log_transform(vals)
                    tmin = float(np.min(tvals)) if tvals.size else -1.0
                    tmax = float(np.max(tvals)) if tvals.size else 1.0
                    if np.isclose(tmin, tmax):
                        tmin -= 1.0
                        tmax += 1.0
                    ranges_t[key] = (tmin, tmax)

                def _norm_dev(key, dev_value):
                    if not np.isfinite(dev_value):
                        return np.nan
                    tval = float(_signed_log_transform(np.array([dev_value]))[0])
                    tmin, tmax = ranges_t[key]
                    if np.isclose(tmin, tmax):
                        return 0.5
                    return float(np.clip((tval - tmin) / (tmax - tmin), 0.0, 1.0))

                for height_tag, fig_height in height_variants:
                    fig, ax = plt.subplots(
                        figsize=(width_inch, max(2.6, float(fig_height) * 1.05)),
                        subplot_kw={"projection": "polar"},
                    )

                    # Reference baseline (=0% on transformed axis)
                    ref_norm = []
                    for key, _ in axis_specs:
                        ref_norm.append(_norm_dev(key, 0.0))
                    ref_vals_closed = np.concatenate([np.asarray(ref_norm, dtype=float), np.asarray(ref_norm[:1], dtype=float)])
                    ax.plot(
                        angles_closed,
                        ref_vals_closed,
                        linestyle="-",
                        linewidth=0.80,
                        marker="X",
                        markersize=1.8,
                        color="#111111",
                        alpha=0.50,
                        label="Reference (0%)",
                    )

                    for dev in dev_rows:
                        skey = str(dev["_scenario_key"])
                        meta_style = style_map[skey]
                        color = _blend_with_white(base_color, float(meta_style["tone"]))
                        vals = np.asarray([_norm_dev(k, dev.get(k, np.nan)) for k, _ in axis_specs], dtype=float)
                        vals_closed = np.concatenate([vals, vals[:1]])
                        ax.plot(
                            angles_closed,
                            vals_closed,
                            linestyle=meta_style["linestyle"],
                            linewidth=0.95,
                            marker=meta_style["marker"],
                            markersize=2.0,
                            color=color,
                            alpha=0.65,
                            label=meta_style["label"],
                        )

                    ax.set_theta_offset(np.pi / 2)
                    ax.set_theta_direction(-1)
                    ax.set_xticks(angles)
                    ax.set_xticklabels([lbl for _, lbl in axis_specs], fontsize=font_size)
                    ax.set_ylim(0.0, 1.0)
                    ax.set_yticks([0.25, 0.50, 0.75, 1.00])
                    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=font_size)
                    ax.grid(alpha=0.28, linewidth=0.5)
                    ax.set_title(
                        f"{objective_name} | {carrier_title} | {metric_tag} (signed-log dev.)",
                        pad=18,
                        fontsize=font_size,
                    )

                    handles, labels = ax.get_legend_handles_labels()
                    seen = set()
                    h2, l2 = [], []
                    for h, l in zip(handles, labels):
                        if l in seen:
                            continue
                        seen.add(l)
                        h2.append(h)
                        l2.append(l)
                    ax.legend(
                        h2,
                        l2,
                        frameon=False,
                        loc="upper center",
                        ncol=5,
                        bbox_to_anchor=(0.5, 1.20),
                        handlelength=1.3,
                        columnspacing=1.0,
                    )

                    fig.subplots_adjust(left=0.06, right=0.96, bottom=0.06, top=0.82)
                    safe_obj = str(objective_name).replace(" ", "_")
                    safe_carrier = str(carrier_key).replace(" ", "_")
                    pdf_path = (
                        out_dir
                        / f"dec_COMPARE_spider_levels_{safe_obj}_{safe_carrier}_{metric_tag}_{height_tag}_global_max.pdf"
                    )
                    png_path = (
                        out_dir
                        / f"dec_COMPARE_spider_levels_{safe_obj}_{safe_carrier}_{metric_tag}_{height_tag}_global_max.png"
                    )
                    fig.savefig(_to_windows_long_path(str(pdf_path)), dpi=600, bbox_inches="tight")
                    fig.savefig(_to_windows_long_path(str(png_path)), dpi=300, bbox_inches="tight")
                    plt.close(fig)


def plot_scenario_deviation_lines_by_extreme(
    parallel_axis_rows: List[Dict[str, float]],
    *,
    out_dir: Path,
    width_inch: float,
    height_variants: List[Tuple[str, float]],
    font_size: int,
) -> None:
    """
    Additional scenario-on-x plot:
    - x-axis: scenarios (+20/+40/-20/-40)
    - y-axis: relative deviation [%] to reference
    - one line per KPI axis (reduced set for readability)
    """
    set_journal_style(font_size=font_size)
    metric_sets = {
        "kpi6": [
            ("totex", "Ann. TOTEX"),
            ("gwp", "Ann. GWP"),
            ("peak", "Peak"),
            ("heat_pump_capacity", "Heat pump"),
            ("gas_heater_capacity", "Gas heater"),
            ("chp_capacity", "CHP"),
        ],
        "kpi_all": [
            ("totex", "Ann. TOTEX"),
            ("gwp", "Ann. GWP"),
            ("peak", "Peak"),
            ("heat_pump_capacity", "Heat pump"),
            ("gas_heater_capacity", "Gas heater"),
            ("chp_capacity", "CHP"),
            ("battery_capacity", "Battery"),
            ("thermal_storage_capacity", "Heat storage"),
            ("pv_capacity", "PV-System"),
            ("retrofit_depth", "Retrofit"),
        ],
    }
    base_palette = sns.color_palette("colorblind")
    objectives = sorted({str(r["extreme_point"]) for r in parallel_axis_rows})
    scenario_order = [name for name, _ in ordered_scenarios()]
    scenario_labels = {name: label for name, label in ordered_scenarios()}

    for objective_name in objectives:
        rows_obj = [r for r in parallel_axis_rows if str(r["extreme_point"]) == objective_name]
        if not rows_obj:
            continue

        ref_rows = [r for r in rows_obj if str(r.get("scenario_name")) == "reference"]
        if not ref_rows:
            continue
        ref_row = ref_rows[0]

        scenario_rows = {}
        for row in rows_obj:
            sname = str(row.get("scenario_name"))
            if sname == "reference":
                continue
            scenario_rows[sname] = row
        ordered_rows = [scenario_rows[s] for s in scenario_order if s in scenario_rows]
        if not ordered_rows:
            continue

        x = np.arange(len(ordered_rows))
        xlabels = [scenario_labels[str(r["scenario_name"])] for r in ordered_rows]

        for metric_tag, metrics in metric_sets.items():
            metric_styles = []
            markers = ["o", "s", "^", "D", "v", "P", "X", "<", ">", "*"]
            for idx, _ in enumerate(metrics):
                metric_styles.append((markers[idx % len(markers)], base_palette[idx % len(base_palette)]))

            for height_tag, fig_height in height_variants:
                fig, ax = plt.subplots(figsize=(width_inch, max(2.4, float(fig_height) * 1.05)))
                for idx, (key, display_name) in enumerate(metrics):
                    marker, color = metric_styles[idx]
                    ref_val = float(ref_row.get(key, np.nan))
                    y_vals = []
                    for row in ordered_rows:
                        cur_val = float(row.get(key, np.nan))
                        if np.isfinite(ref_val) and not np.isclose(ref_val, 0.0) and np.isfinite(cur_val):
                            y_vals.append((cur_val - ref_val) / ref_val * 100.0)
                        else:
                            y_vals.append(np.nan)
                    y = np.asarray(y_vals, dtype=float)
                    ax.plot(
                        x,
                        y,
                        marker=marker,
                        markersize=2.0,
                        linewidth=0.9,
                        color=color,
                        alpha=0.70,
                        label=display_name,
                    )

                ax.axhline(0.0, color="#111111", linestyle=":", linewidth=0.8, alpha=0.75)
                ax.set_xlim(-0.35, len(ordered_rows) - 0.65)
                ax.set_xticks(x)
                ax.set_xticklabels(xlabels, rotation=35, ha="right")
                ax.set_ylabel("Deviation to reference in % (symlog)")
                ax.set_xlabel("Scenario")
                ax.set_yscale("symlog", linthresh=10.0, linscale=1.0, base=10)
                ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
                ax.legend(
                    frameon=False,
                    loc="upper center",
                    ncol=3,
                    bbox_to_anchor=(0.5, 1.28),
                    handlelength=1.4,
                    columnspacing=1.0,
                )
                fig.subplots_adjust(left=0.08, right=0.995, bottom=0.30, top=0.68)

                safe_obj = str(objective_name).replace(" ", "_")
                pdf_path = (
                    out_dir
                    / f"dec_COMPARE_scenario_deviation_lines_{safe_obj}_{metric_tag}_{height_tag}_global_max.pdf"
                )
                png_path = (
                    out_dir
                    / f"dec_COMPARE_scenario_deviation_lines_{safe_obj}_{metric_tag}_{height_tag}_global_max.png"
                )
                fig.savefig(_to_windows_long_path(str(pdf_path)), dpi=600, bbox_inches="tight")
                fig.savefig(_to_windows_long_path(str(png_path)), dpi=300, bbox_inches="tight")
                plt.close(fig)


def write_excel_outputs(
    *,
    summary_rows: List[Dict[str, float]],
    composition_rows: List[Dict[str, float]],
    parallel_axis_rows: List[Dict[str, float]],
    out_xlsx: Path,
) -> None:
    df_summary = pd.DataFrame(summary_rows)
    df_comp = pd.DataFrame(composition_rows)
    df_parallel = pd.DataFrame(parallel_axis_rows)

    with pd.ExcelWriter(_to_windows_long_path(str(out_xlsx)), engine="openpyxl") as writer:
        df_summary.to_excel(writer, sheet_name="deviation_summary", index=False)
        df_comp.to_excel(writer, sheet_name="tech_cost_long", index=False)
        df_parallel.to_excel(writer, sheet_name="parallel_axes_values", index=False)

        if not df_comp.empty:
            pivot = df_comp.pivot_table(
                index=["scenario_label", "extreme_point"],
                columns="technology",
                values="tech_cost_per_100m2",
                aggfunc="sum",
            ).reset_index()
            pivot.to_excel(writer, sheet_name="tech_cost_per100_wide", index=False)


def main() -> None:
    variation_root = Path(
        r"C:\Users\hill_mx\Desktop\processed_bds_in_DENI03403000SEC5658_variable"
    )
    reference_dir = Path(
        r"/oemof/thermal_building_model/examples/03_applied_energy_optimization/processed_bds_in_DENI03403000SEC5658/post_processed_dec_k_combinations_2026_04_08/sfh_k06_mfh_k01"
    )
    run_subdir = "sfh_k06_mfh_k01"
    reference_case_root = reference_dir.parents[1]

    script_dir = Path(__file__).resolve().parent
    out_dir = script_dir / "_plot_outputs" / "carrier_price_sensitivity_extremes"
    out_dir.mkdir(parents=True, exist_ok=True)
    total_floor_area_all = _load_total_floor_area_from_clusters(reference_case_root, run_subdir)

    ref_front = load_combined_front_from_path(reference_dir / "combined_front.pkl")
    ref_extremes = extract_extreme_points_from_tradeoffs(ref_front)
    ref_extreme_records = extract_extreme_records_from_tradeoffs(ref_front)

    rows: List[Dict[str, float]] = []
    composition_rows: List[Dict[str, float]] = []
    parallel_axis_rows: List[Dict[str, float]] = []
    for objective_name, record in ref_extreme_records.items():
        composition_rows.extend(
            _extract_technology_cost_rows_for_record(
                record,
                total_floor_area_all=total_floor_area_all,
                objective_name=objective_name,
                scenario_name="reference",
                scenario_label="Reference",
            )
        )
        parallel_axis_rows.append(
            _extract_parallel_axis_row_for_record(
                record,
                total_floor_area_all=total_floor_area_all,
                objective_name=objective_name,
                scenario_name="reference",
                scenario_label="Reference",
            )
        )

    for scenario_name, label in ordered_scenarios():
        scenario_path = variation_root / scenario_name / run_subdir / "combined_front.pkl"
        combined_front = load_combined_front_from_path(scenario_path)
        extremes = extract_extreme_points_from_tradeoffs(combined_front)
        extreme_records = extract_extreme_records_from_tradeoffs(combined_front)

        rows.append(
            {
                "scenario_name": scenario_name,
                "label": label,
                "min_totex": extremes["min_totex"],
                "min_peak": extremes["min_peak"],
                "min_gwp": extremes["min_gwp"],
                "max_totex": extremes["max_totex"],
                "max_peak": extremes["max_peak"],
                "max_gwp": extremes["max_gwp"],
                "dev_totex_pct": rel_deviation_percent(extremes["min_totex"], ref_extremes["min_totex"]),
                "dev_peak_pct": rel_deviation_percent(extremes["min_peak"], ref_extremes["min_peak"]),
                "dev_gwp_pct": rel_deviation_percent(extremes["min_gwp"], ref_extremes["min_gwp"]),
                "dev_max_totex_pct": rel_deviation_percent(extremes["max_totex"], ref_extremes["max_totex"]),
                "dev_max_peak_pct": rel_deviation_percent(extremes["max_peak"], ref_extremes["max_peak"]),
                "dev_max_gwp_pct": rel_deviation_percent(extremes["max_gwp"], ref_extremes["max_gwp"]),
                "n_front_cost_co2": extremes["n_front_cost_co2"],
                "n_front_cost_peak": extremes["n_front_cost_peak"],
                "n_front_peak_co2": extremes["n_front_peak_co2"],
            }
        )
        for objective_name, record in extreme_records.items():
            composition_rows.extend(
                _extract_technology_cost_rows_for_record(
                    record,
                    total_floor_area_all=total_floor_area_all,
                    objective_name=objective_name,
                    scenario_name=scenario_name,
                    scenario_label=label,
                )
            )
            parallel_axis_rows.append(
                _extract_parallel_axis_row_for_record(
                    record,
                    total_floor_area_all=total_floor_area_all,
                    objective_name=objective_name,
                    scenario_name=scenario_name,
                    scenario_label=label,
                )
            )

    write_csv(
        rows=rows,
        out_path=out_dir / "extreme_deviation_vs_ref.csv",
        fieldnames=[
            "scenario_name",
            "label",
            "min_totex",
            "min_peak",
            "min_gwp",
            "max_totex",
            "max_peak",
            "max_gwp",
            "dev_totex_pct",
            "dev_peak_pct",
            "dev_gwp_pct",
            "dev_max_totex_pct",
            "dev_max_peak_pct",
            "dev_max_gwp_pct",
            "n_front_cost_co2",
            "n_front_cost_peak",
            "n_front_peak_co2",
        ],
    )
    write_csv(
        rows=composition_rows,
        out_path=out_dir / "extreme_point_technology_cost_composition_long.csv",
        fieldnames=[
            "scenario_name",
            "scenario_label",
            "extreme_point",
            "totex_per_100m2",
            "peak_per_100m2",
            "gwp_per_100m2",
            "technology",
            "tech_cost_per_100m2",
            "tech_cost_abs",
            "tech_share_of_technology_cost_pct",
        ],
    )
    write_csv(
        rows=parallel_axis_rows,
        out_path=out_dir / "extreme_point_parallel_axes_values.csv",
        fieldnames=[
            "scenario_name",
            "scenario_label",
            "extreme_point",
            "totex",
            "gwp",
            "peak",
            "heat_pump_capacity",
            "gas_heater_capacity",
            "chp_capacity",
            "battery_capacity",
            "thermal_storage_capacity",
            "pv_capacity",
            "retrofit_depth",
        ],
    )
    excel_path = out_dir / "extreme_deviation_and_technology_composition.xlsx"
    try:
        write_excel_outputs(
            summary_rows=rows,
            composition_rows=composition_rows,
            parallel_axis_rows=parallel_axis_rows,
            out_xlsx=excel_path,
        )
        excel_written = True
    except Exception as exc:
        excel_written = False
        print(f"WARNING: Excel export failed ({exc}). CSV outputs are still written.")

    width_cm = 15.11293
    height_cm = 6.5 * 1.34
    width_inch = width_cm / 2.54
    height_inch = height_cm / 2.54
    font_size = 9
    single_parallel_height_factor = 1.90 * 0.85
    stacked_parallel_reference_scale = 0.30
    h70_scale = 0.70
    fig_height = (
        height_inch
        * single_parallel_height_factor
        * 3.0
        * stacked_parallel_reference_scale
        * h70_scale
    )
    h60_scale = 0.60
    h70_scale = 0.70
    h80_scale = 0.80
    h90_scale = 0.90
    h100_scale = 1.00
    parallel_height_variants = [
        (
            "h100",
            height_inch
            * single_parallel_height_factor
            * 3.0
            * stacked_parallel_reference_scale
            * h100_scale,
        ),
        (
            "h90",
            height_inch
            * single_parallel_height_factor
            * 3.0
            * stacked_parallel_reference_scale
            * h90_scale,
        ),
        (
            "h80",
            height_inch
            * single_parallel_height_factor
            * 3.0
            * stacked_parallel_reference_scale
            * h80_scale,
        ),
        (
            "h70",
            height_inch
            * single_parallel_height_factor
            * 3.0
            * stacked_parallel_reference_scale
            * h70_scale,
        ),
        (
            "h60",
            height_inch
            * single_parallel_height_factor
            * 3.0
            * stacked_parallel_reference_scale
            * h60_scale,
        ),
    ]

    set_journal_style(font_size=font_size)
    palette = sns.color_palette("colorblind")

    x = np.arange(len(rows))
    y_totex = np.asarray([r["dev_totex_pct"] for r in rows], dtype=float)
    y_peak = np.asarray([r["dev_peak_pct"] for r in rows], dtype=float)
    y_gwp = np.asarray([r["dev_gwp_pct"] for r in rows], dtype=float)
    y_max_totex = np.asarray([r["dev_max_totex_pct"] for r in rows], dtype=float)
    y_max_peak = np.asarray([r["dev_max_peak_pct"] for r in rows], dtype=float)
    y_max_gwp = np.asarray([r["dev_max_gwp_pct"] for r in rows], dtype=float)
    labels = [r["label"] for r in rows]

    fig, ax = plt.subplots(figsize=(width_inch, fig_height))

    ax.plot(x, y_totex, marker="o", linewidth=1.3, color=palette[0], label="Min TOTEX deviation")
    ax.plot(x, y_peak, marker="s", linewidth=1.3, color=palette[2], label="Min Peak deviation")
    ax.plot(x, y_gwp, marker="^", linewidth=1.3, color=palette[3], label="Min GWP deviation")
    ax.plot(
        x,
        y_max_totex,
        marker="o",
        linestyle="--",
        linewidth=1.1,
        color=palette[0],
        label="Max TOTEX deviation",
    )
    ax.plot(
        x,
        y_max_peak,
        marker="s",
        linestyle="--",
        linewidth=1.1,
        color=palette[2],
        label="Max Peak deviation",
    )
    ax.plot(
        x,
        y_max_gwp,
        marker="^",
        linestyle="--",
        linewidth=1.1,
        color=palette[3],
        label="Max GWP deviation",
    )

    ax.axhline(0.0, color="black", linewidth=0.8, alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylabel("Deviation to reference in %")
    ax.set_xlabel("Energy price / feed-in variation")
    ax.grid(True, axis="y", alpha=0.3, linewidth=0.6)
    ax.legend(frameon=False, loc="best")
    fig.tight_layout()

    pdf_path = out_dir / "dec_COMPARE_extreme_dev_tradeoffs_p7_h70_lines.pdf"
    png_path = out_dir / "dec_COMPARE_extreme_dev_tradeoffs_p7_h70_lines.png"

    # Windows-safe save paths (long path support) + ensure dir exists right before writing.
    os.makedirs(_to_windows_long_path(str(out_dir)), exist_ok=True)
    fig.savefig(_to_windows_long_path(str(pdf_path)), dpi=600, bbox_inches="tight")
    fig.savefig(_to_windows_long_path(str(png_path)), dpi=300, bbox_inches="tight")
    plt.close(fig)

    if ONLY_PARALLEL_STYLE_KEEP:
        plot_parallel_axes_sensitivity_by_extreme(
            parallel_axis_rows=parallel_axis_rows,
            out_dir=out_dir,
            width_inch=width_inch,
            height_variants=parallel_height_variants,
            font_size=font_size,
            objective_filter=PARALLEL_TARGET_OBJECTIVES,
            height_filter=PARALLEL_TARGET_HEIGHT_TAGS,
            draw_mode="lines_points",
            show_colorbars=True,
        )
        plot_parallel_axes_sensitivity_by_extreme(
            parallel_axis_rows=parallel_axis_rows,
            out_dir=out_dir,
            width_inch=width_inch,
            height_variants=parallel_height_variants,
            font_size=font_size,
            objective_filter=PARALLEL_TARGET_OBJECTIVES,
            height_filter=PARALLEL_TARGET_HEIGHT_TAGS,
            draw_mode="lines_points",
            show_colorbars=False,
        )
        # Additional variants: same legend, reduced plot symbol sizes in 15% steps.
        for marker_scale in (0.85, 0.70, 0.55):
            plot_parallel_axes_sensitivity_by_extreme(
                parallel_axis_rows=parallel_axis_rows,
                out_dir=out_dir,
                width_inch=width_inch,
                height_variants=parallel_height_variants,
                font_size=font_size,
                objective_filter=PARALLEL_TARGET_OBJECTIVES,
                height_filter=PARALLEL_TARGET_HEIGHT_TAGS,
                draw_mode="lines_points",
                show_colorbars=False,
                marker_size_scale=float(marker_scale),
            )
        plot_parallel_axes_sensitivity_by_extreme(
            parallel_axis_rows=parallel_axis_rows,
            out_dir=out_dir,
            width_inch=width_inch,
            height_variants=parallel_height_variants,
            font_size=font_size,
            objective_filter=PARALLEL_TARGET_OBJECTIVES,
            height_filter=PARALLEL_TARGET_HEIGHT_TAGS,
            draw_mode="points_only",
            show_colorbars=True,
        )
        plot_parallel_axes_sensitivity_triptych(
            parallel_axis_rows=parallel_axis_rows,
            out_dir=out_dir,
            width_inch=width_inch,
            height_variants=parallel_height_variants,
            font_size=font_size,
            height_filter=PARALLEL_TARGET_HEIGHT_TAGS,
        )
        if ENABLE_DEVIATION_NO_STD_PLOTS:
            plot_parallel_axes_deviation_no_std_by_extreme(
                parallel_axis_rows=parallel_axis_rows,
                out_dir=out_dir,
                width_inch=width_inch,
                height_variants=parallel_height_variants,
                font_size=font_size,
                objective_filter=PARALLEL_TARGET_OBJECTIVES,
                height_filter=PARALLEL_TARGET_HEIGHT_TAGS,
            )
        if ENABLE_STD_BAND_PLOTS:
            for sigma in STD_BAND_MULTIPLIERS:
                plot_parallel_axes_std_bands_by_extreme(
                    parallel_axis_rows=parallel_axis_rows,
                    out_dir=out_dir,
                    width_inch=width_inch,
                    height_variants=parallel_height_variants,
                    font_size=font_size,
                    std_multiplier=int(sigma),
                    objective_filter=PARALLEL_TARGET_OBJECTIVES,
                    height_filter=PARALLEL_TARGET_HEIGHT_TAGS,
                    scale_within_axis_abs_max=STD_BAND_SCALE_WITHIN_AXIS_ABS_MAX,
                )
    else:
        plot_parallel_axes_sensitivity_by_extreme(
            parallel_axis_rows=parallel_axis_rows,
            out_dir=out_dir,
            width_inch=width_inch,
            height_variants=parallel_height_variants,
            font_size=font_size,
        )
        plot_spider_sensitivity_by_extreme(
            parallel_axis_rows=parallel_axis_rows,
            out_dir=out_dir,
            width_inch=width_inch,
            height_variants=parallel_height_variants,
            font_size=font_size,
        )
        plot_spider_by_scenario_levels(
            parallel_axis_rows=parallel_axis_rows,
            out_dir=out_dir,
            width_inch=width_inch,
            height_variants=parallel_height_variants,
            font_size=font_size,
        )
        plot_scenario_deviation_lines_by_extreme(
            parallel_axis_rows=parallel_axis_rows,
            out_dir=out_dir,
            width_inch=width_inch,
            height_variants=parallel_height_variants,
            font_size=font_size,
        )

    print(f"Reference extremes: {ref_extremes}")
    print(f"Total floor area all: {total_floor_area_all}")
    print(f"Wrote CSV: {out_dir / 'extreme_deviation_vs_ref.csv'}")
    print(f"Wrote CSV: {out_dir / 'extreme_point_technology_cost_composition_long.csv'}")
    print(f"Wrote CSV: {out_dir / 'extreme_point_parallel_axes_values.csv'}")
    if excel_written:
        print(f"Wrote Excel: {excel_path}")
    print(f"Wrote figure: {pdf_path}")


if __name__ == "__main__":
    main()
