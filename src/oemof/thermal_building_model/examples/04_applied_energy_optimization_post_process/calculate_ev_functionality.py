from __future__ import annotations

import csv
import pickle
import re
from numbers import Real
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RUN_SUBDIR = "sfh_k06_mfh_k01"

EV_HALF_BASE = Path(
    r"C:\Users\hill_mx\Desktop\processed_bds_in_DENI03403000SEC5658_variable"
    r"\processed_bds_in_DENI03403000SEC5658_yes_ev_half\sfh_k06_mfh_k01"
)
EV_TOTAL_BASE = Path(
    r"C:\Users\hill_mx\Desktop\processed_bds_in_DENI03403000SEC5658_variable"
    r"\processed_bds_in_DENI03403000SEC5658_yes_ev_total\sfh_k06_mfh_k01"
)
REFERENCE_BASE = Path(
    r"/oemof/thermal_building_model/examples/03_applied_energy_optimization"
    r"\processed_bds_in_DENI03403000SEC5658\post_processed_dec_k_combinations_2026_04_08"
    r"\sfh_k06_mfh_k01"
)
DEMAND_DIRECTORY = Path(
    r"/oemof/thermal_building_model/examples/03_applied_energy_optimization"
    r"\processed_bds_in_DENI03403000SEC5658"
)
SFH_CLUSTER_K = 6
MFH_CLUSTER_K = 1
# Optional override. If None, the first building id from the reference selection is used.
BUILDING_ID_FOR_TIMESERIES: str | None = "DENILD1100004rqi"


def _resolve_run_dir(path: Path) -> Path:
    if (path / "combined_front.pkl").exists():
        return path
    if path.name == RUN_SUBDIR:
        return path
    candidate = path / RUN_SUBDIR
    if (candidate / "combined_front.pkl").exists():
        return candidate
    return candidate


def _is_front_like_list(obj: Any) -> bool:
    if not isinstance(obj, list):
        return False
    if len(obj) == 0:
        return True
    first = obj[0]
    return isinstance(first, dict) and {"co2", "totex", "peak"}.issubset(first.keys())


def _extract_combined_front(loaded_obj: Any) -> list[dict[str, Any]]:
    if _is_front_like_list(loaded_obj):
        return loaded_obj

    if isinstance(loaded_obj, (tuple, list)):
        for item in loaded_obj:
            if _is_front_like_list(item):
                return item

    if isinstance(loaded_obj, dict):
        direct = loaded_obj.get("combined_front")
        if _is_front_like_list(direct):
            return direct
        for item in loaded_obj.values():
            if _is_front_like_list(item):
                return item

    raise ValueError(f"Could not extract combined front from payload type: {type(loaded_obj)}")


def _load_combined_front_from_run_dir(run_dir: Path) -> list[dict[str, Any]]:
    pkl_path = run_dir / "combined_front.pkl"
    if not pkl_path.exists():
        raise FileNotFoundError(f"Missing file: {pkl_path}")
    with pkl_path.open("rb") as fh:
        loaded = pickle.load(fh)
    front = _extract_combined_front(loaded)
    if len(front) == 0:
        raise ValueError(f"combined_front is empty in: {pkl_path}")
    return front


def _pareto_front(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid = []
    for rec in records:
        co2 = rec.get("co2")
        totex = rec.get("totex")
        if co2 is None or totex is None:
            continue
        co2 = float(co2)
        totex = float(totex)
        if not (np.isfinite(co2) and np.isfinite(totex)):
            continue
        valid.append(rec)

    valid.sort(key=lambda r: (float(r["co2"]), float(r["totex"])))
    out: list[dict[str, Any]] = []
    best_totex = float("inf")
    for rec in valid:
        cur_totex = float(rec["totex"])
        if cur_totex < best_totex:
            out.append(rec)
            best_totex = cur_totex
    return out


def _iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_dicts(value)


def _sum_key_recursive(record: dict[str, Any], key: str) -> float:
    total = 0.0
    for dct in _iter_dicts(record):
        if key in dct:
            value = dct[key]
            if isinstance(value, Real):
                total += float(value)
    return total


def _sum_e_demand_recursive(obj: Any) -> float:
    total = 0.0
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str) and key.startswith("e_demand_") and isinstance(value, dict):
                sum_value = value.get("sum")
                if isinstance(sum_value, Real):
                    total += float(sum_value)
            total += _sum_e_demand_recursive(value)
    elif isinstance(obj, list):
        for value in obj:
            total += _sum_e_demand_recursive(value)
    return total


def _electricity_demand_for_point(record: dict[str, Any]) -> float:
    # Prefer explicit selection payload if present.
    selection = record.get("selection")
    if isinstance(selection, dict):
        return _sum_e_demand_recursive(selection)
    return _sum_e_demand_recursive(record)


def _summarise_case(name: str, records: list[dict[str, Any]]) -> dict[str, float]:
    demand = np.asarray([_electricity_demand_for_point(rec) for rec in records], dtype=float)
    return {
        "case": name,
        "n_points": float(len(records)),
        "electricity_demand_min": float(np.nanmin(demand)),
        "electricity_demand_mean": float(np.nanmean(demand)),
        "electricity_demand_max": float(np.nanmax(demand)),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _load_demand_dataframe(directory_path: Path, building_id: str, ev_suffix: str) -> pd.DataFrame:
    demand_path = directory_path / f"{building_id}_demand_{ev_suffix}.pkl"
    if not demand_path.exists():
        raise FileNotFoundError(f"Missing demand file: {demand_path}")
    with demand_path.open("rb") as fh:
        demand = pickle.load(fh)
    if isinstance(demand, pd.DataFrame):
        return demand.copy()
    return pd.DataFrame(demand)


def _extract_household_column_map(demand_df: pd.DataFrame, prefix: str) -> dict[int, str]:
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    mapping: dict[int, str] = {}
    for col in demand_df.columns:
        match = pattern.match(str(col).strip())
        if match:
            idx = int(match.group(1))
            mapping[idx] = str(col)
    return mapping


def _build_even_assignment(num_households: int, num_ev_households: int) -> list[int]:
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


def _build_ev_demand_timeseries_for_building(
    *,
    demand_dir: Path,
    building_id: str,
    mode: str,
) -> pd.Series:
    demand_no_ev = _load_demand_dataframe(demand_dir, building_id, "no_EV")
    demand_yes_ev = _load_demand_dataframe(demand_dir, building_id, "yes_EV")
    if len(demand_no_ev) != len(demand_yes_ev):
        raise ValueError(
            f"{building_id}: no_EV and yes_EV demand length mismatch "
            f"({len(demand_no_ev)} vs {len(demand_yes_ev)})."
        )

    hh_no_ev = _extract_household_column_map(demand_no_ev, "Electricity_HH")
    hh_yes_ev = _extract_household_column_map(demand_yes_ev, "Electricity_HH")
    car_yes_ev = _extract_household_column_map(demand_yes_ev, "Electricity for Car Charging_HH")

    hh_indices = sorted(hh_no_ev.keys())
    if not hh_indices:
        raise ValueError(f"{building_id}: no household electricity columns found in no_EV demand.")
    if sorted(hh_yes_ev.keys()) != hh_indices:
        raise ValueError(f"{building_id}: household electricity columns differ between no_EV and yes_EV.")

    if mode == "reference":
        assignment = [0] * len(hh_indices)
    elif mode == "ev_half":
        assignment = _build_even_assignment(len(hh_indices), int(round(len(hh_indices) / 2.0)))
    elif mode == "ev_total":
        assignment = [1] * len(hh_indices)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    total = pd.Series(0.0, index=demand_no_ev.index, dtype=float)
    for list_pos, hh_idx in enumerate(hh_indices):
        base_col = hh_no_ev[hh_idx]
        base_profile = pd.to_numeric(demand_no_ev[base_col], errors="coerce").fillna(0.0)
        total = total.add(base_profile, fill_value=0.0)

        if int(assignment[list_pos]) > 0:
            car_col = car_yes_ev.get(hh_idx)
            if car_col is None:
                raise ValueError(
                    f"{building_id}: missing 'Electricity for Car Charging_HH{hh_idx}' in yes_EV demand file."
                )
            car_profile = pd.to_numeric(demand_yes_ev[car_col], errors="coerce").fillna(0.0)
            total = total.add(car_profile, fill_value=0.0)

    # Keep the same scaling used in 17_decentralized process_cluster.
    return total * 1000.0


def _find_default_building_id(reference_front: list[dict[str, Any]]) -> str:
    for rec in reference_front:
        selection = rec.get("selection")
        if isinstance(selection, dict) and selection:
            return sorted(str(k) for k in selection.keys())[0]
    raise ValueError("Could not infer a building id from reference selection.")


def _load_building_ids_from_cluster_pickle(cluster_pickle_path: Path) -> list[str]:
    if not cluster_pickle_path.exists():
        raise FileNotFoundError(f"Missing cluster pickle: {cluster_pickle_path}")
    with cluster_pickle_path.open("rb") as fh:
        obj = pickle.load(fh)
    df = obj if isinstance(obj, pd.DataFrame) else pd.DataFrame(obj)
    if "building_id" not in df.columns:
        raise ValueError(f"Column 'building_id' missing in {cluster_pickle_path}")
    out: list[str] = []
    seen: set[str] = set()
    for value in df["building_id"].tolist():
        bid = str(value)
        if bid not in seen:
            seen.add(bid)
            out.append(bid)
    return out


def _get_sfh_mfh_building_ids_for_run(demand_dir: Path) -> tuple[list[str], list[str]]:
    sfh_path = demand_dir / f"sfh_cluster_k{SFH_CLUSTER_K:02d}" / "sfh_cluster.pkl"
    mfh_path = demand_dir / f"mfh_cluster_k{MFH_CLUSTER_K:02d}" / "mfh_cluster.pkl"
    sfh_ids = _load_building_ids_from_cluster_pickle(sfh_path)
    mfh_ids = _load_building_ids_from_cluster_pickle(mfh_path)
    return sfh_ids, mfh_ids


def _plot_pareto_compare(cases: dict[str, list[dict[str, Any]]], out_file: Path) -> None:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": "TeX Gyre Termes",
            "font.size": 9,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    colors = {
        "Reference": "#4c78a8",
        "EV 50%": "#f58518",
        "EV 100%": "#54a24b",
    }
    markers = {
        "Reference": "o",
        "EV 50%": "s",
        "EV 100%": "^",
    }

    for case_name, front in cases.items():
        co2 = np.asarray([float(r["co2"]) for r in front], dtype=float)
        totex = np.asarray([float(r["totex"]) for r in front], dtype=float)
        ax.scatter(
            co2,
            totex,
            s=12,
            alpha=0.22,
            color=colors[case_name],
            marker=markers[case_name],
        )

        pf = _pareto_front(front)
        pf_co2 = np.asarray([float(r["co2"]) for r in pf], dtype=float)
        pf_totex = np.asarray([float(r["totex"]) for r in pf], dtype=float)
        order = np.argsort(pf_co2)
        ax.plot(
            pf_co2[order],
            pf_totex[order],
            linewidth=1.6,
            color=colors[case_name],
            label=f"{case_name} Pareto",
        )

    ax.set_xlabel("Ann. CO$_2$-eq.")
    ax.set_ylabel("Ann. TOTEX")
    ax.grid(True, alpha=0.25, linewidth=0.6)
    ax.legend(frameon=False, loc="best")
    fig.tight_layout()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=450, bbox_inches="tight")
    fig.savefig(out_file.with_suffix(".png"), dpi=250, bbox_inches="tight")
    plt.close(fig)


def _plot_single_building_ev_demand_profiles(
    *,
    demand_dir: Path,
    building_id: str,
    out_file: Path,
) -> None:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": "TeX Gyre Termes",
            "font.size": 9,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    ts_ref = _build_ev_demand_timeseries_for_building(
        demand_dir=demand_dir, building_id=building_id, mode="reference"
    )
    ts_half = _build_ev_demand_timeseries_for_building(
        demand_dir=demand_dir, building_id=building_id, mode="ev_half"
    )
    ts_total = _build_ev_demand_timeseries_for_building(
        demand_dir=demand_dir, building_id=building_id, mode="ev_total"
    )

    x = np.arange(len(ts_ref), dtype=int)
    y_ref = np.asarray(ts_ref, dtype=float)
    y_half = np.asarray(ts_half, dtype=float)
    y_total = np.asarray(ts_total, dtype=float)

    fig, axes = plt.subplots(nrows=3, ncols=1, sharex=True, figsize=(10.0, 8.0))

    axes[0].plot(x, y_ref, linewidth=0.9, color="#4c78a8")
    axes[0].set_ylabel("Reference")
    axes[0].grid(True, alpha=0.25, linewidth=0.6)

    axes[1].plot(x, y_half, linewidth=0.9, color="#f58518")
    axes[1].set_ylabel("EV half")
    axes[1].grid(True, alpha=0.25, linewidth=0.6)

    axes[2].plot(x, y_total, linewidth=0.9, color="#54a24b")
    axes[2].set_ylabel("EV total")
    axes[2].set_xlabel("Time step (hour of year)")
    axes[2].grid(True, alpha=0.25, linewidth=0.6)

    axes[0].set_title(f"Building {building_id}: yearly electricity demand (17_decentralized EV logic)")
    fig.tight_layout()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=450, bbox_inches="tight")
    fig.savefig(out_file.with_suffix(".png"), dpi=250, bbox_inches="tight")
    plt.close(fig)


def _plot_e_demand_compare(cases: dict[str, list[dict[str, Any]]], out_file: Path) -> None:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": "TeX Gyre Termes",
            "font.size": 9,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    colors = {
        "Reference": "#4c78a8",
        "EV 50%": "#f58518",
        "EV 100%": "#54a24b",
    }
    markers = {
        "Reference": "o",
        "EV 50%": "s",
        "EV 100%": "^",
    }

    for case_name, records in cases.items():
        points = []
        for rec in records:
            co2 = rec.get("co2")
            if co2 is None:
                continue
            co2 = float(co2)
            if not np.isfinite(co2):
                continue
            points.append((co2, _electricity_demand_for_point(rec)))
        points.sort(key=lambda t: t[0])
        if not points:
            continue

        y = np.asarray([p[1] for p in points], dtype=float)
        x = np.arange(len(y))
        ax.plot(
            x,
            y,
            color=colors[case_name],
            marker=markers[case_name],
            markersize=2.8,
            linewidth=1.2,
            alpha=0.9,
            label=case_name,
        )

    ax.set_xlabel("Punktindex (nach CO$_2$ sortiert)")
    ax.set_ylabel("Strombedarf aus e_demand (sum)")
    ax.grid(True, alpha=0.25, linewidth=0.6)
    ax.legend(frameon=False, loc="best")
    fig.tight_layout()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=450, bbox_inches="tight")
    fig.savefig(out_file.with_suffix(".png"), dpi=250, bbox_inches="tight")
    plt.close(fig)


def _plot_multi_building_ev_demand_sums(
    *,
    demand_dir: Path,
    sfh_building_ids: list[str],
    mfh_building_ids: list[str],
    out_file: Path,
) -> list[dict[str, Any]]:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": "TeX Gyre Termes",
            "font.size": 9,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    building_rows: list[dict[str, Any]] = []
    building_ids = sfh_building_ids + mfh_building_ids
    sfh_set = set(sfh_building_ids)

    for bid in building_ids:
        ts_ref = _build_ev_demand_timeseries_for_building(
            demand_dir=demand_dir, building_id=bid, mode="reference"
        )
        ts_half = _build_ev_demand_timeseries_for_building(
            demand_dir=demand_dir, building_id=bid, mode="ev_half"
        )
        ts_total = _build_ev_demand_timeseries_for_building(
            demand_dir=demand_dir, building_id=bid, mode="ev_total"
        )
        building_rows.append(
            {
                "building_id": bid,
                "cluster_type": "SFH" if bid in sfh_set else "MFH",
                "sum_reference": float(np.nansum(np.asarray(ts_ref, dtype=float))),
                "sum_ev_half": float(np.nansum(np.asarray(ts_half, dtype=float))),
                "sum_ev_total": float(np.nansum(np.asarray(ts_total, dtype=float))),
            }
        )

    x = np.arange(len(building_rows), dtype=float)
    width = 0.26
    y_ref = np.asarray([r["sum_reference"] for r in building_rows], dtype=float)
    y_half = np.asarray([r["sum_ev_half"] for r in building_rows], dtype=float)
    y_total = np.asarray([r["sum_ev_total"] for r in building_rows], dtype=float)
    xlabels = [r["building_id"] for r in building_rows]

    fig, ax = plt.subplots(figsize=(max(11.5, len(building_rows) * 1.2), 5.0))
    ax.bar(x - width, y_ref, width=width, color="#4c78a8", label="Reference")
    ax.bar(x, y_half, width=width, color="#f58518", label="EV half")
    ax.bar(x + width, y_total, width=width, color="#54a24b", label="EV total")
    ax.set_ylabel("Annual electricity demand sum")
    ax.set_xlabel(f"Buildings from sfh_k{SFH_CLUSTER_K:02d} and mfh_k{MFH_CLUSTER_K:02d}")
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, rotation=45, ha="right")
    ax.grid(True, axis="y", alpha=0.25, linewidth=0.6)
    ax.legend(frameon=False, loc="best")
    fig.tight_layout()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=450, bbox_inches="tight")
    fig.savefig(out_file.with_suffix(".png"), dpi=250, bbox_inches="tight")
    plt.close(fig)

    return building_rows


def _plot_multi_building_ev_demand_peaks(
    *,
    demand_dir: Path,
    sfh_building_ids: list[str],
    mfh_building_ids: list[str],
    out_file: Path,
) -> list[dict[str, Any]]:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": "TeX Gyre Termes",
            "font.size": 9,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    building_rows: list[dict[str, Any]] = []
    building_ids = sfh_building_ids + mfh_building_ids
    sfh_set = set(sfh_building_ids)

    for bid in building_ids:
        ts_ref = _build_ev_demand_timeseries_for_building(
            demand_dir=demand_dir, building_id=bid, mode="reference"
        )
        ts_half = _build_ev_demand_timeseries_for_building(
            demand_dir=demand_dir, building_id=bid, mode="ev_half"
        )
        ts_total = _build_ev_demand_timeseries_for_building(
            demand_dir=demand_dir, building_id=bid, mode="ev_total"
        )
        building_rows.append(
            {
                "building_id": bid,
                "cluster_type": "SFH" if bid in sfh_set else "MFH",
                "peak_reference": float(np.nanmax(np.asarray(ts_ref, dtype=float))),
                "peak_ev_half": float(np.nanmax(np.asarray(ts_half, dtype=float))),
                "peak_ev_total": float(np.nanmax(np.asarray(ts_total, dtype=float))),
            }
        )

    x = np.arange(len(building_rows), dtype=float)
    width = 0.26
    y_ref = np.asarray([r["peak_reference"] for r in building_rows], dtype=float)
    y_half = np.asarray([r["peak_ev_half"] for r in building_rows], dtype=float)
    y_total = np.asarray([r["peak_ev_total"] for r in building_rows], dtype=float)
    xlabels = [r["building_id"] for r in building_rows]

    fig, ax = plt.subplots(figsize=(max(11.5, len(building_rows) * 1.2), 5.0))
    ax.bar(x - width, y_ref, width=width, color="#4c78a8", label="Reference")
    ax.bar(x, y_half, width=width, color="#f58518", label="EV half")
    ax.bar(x + width, y_total, width=width, color="#54a24b", label="EV total")
    ax.set_ylabel("Annual electricity demand peak")
    ax.set_xlabel(f"Buildings from sfh_k{SFH_CLUSTER_K:02d} and mfh_k{MFH_CLUSTER_K:02d}")
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, rotation=45, ha="right")
    ax.grid(True, axis="y", alpha=0.25, linewidth=0.6)
    ax.legend(frameon=False, loc="best")
    fig.tight_layout()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=450, bbox_inches="tight")
    fig.savefig(out_file.with_suffix(".png"), dpi=250, bbox_inches="tight")
    plt.close(fig)

    return building_rows


def _estimate_ev_energy_and_cost_from_annual_sums(
    *,
    building_sum_rows: list[dict[str, Any]],
    electricity_price_eur_per_kwh: float = 0.31,
) -> dict[str, float]:
    sum_ref = float(sum(float(r["sum_reference"]) for r in building_sum_rows))
    sum_half = float(sum(float(r["sum_ev_half"]) for r in building_sum_rows))
    sum_total = float(sum(float(r["sum_ev_total"]) for r in building_sum_rows))

    # In process_cluster, demand_electricity is scaled with *1000.
    # Therefore annual sums here are in Wh; convert to kWh for costs.
    delta_half_kwh = (sum_half - sum_ref) / 1000.0
    delta_total_kwh = (sum_total - sum_ref) / 1000.0

    return {
        "electricity_price_eur_per_kwh": float(electricity_price_eur_per_kwh),
        "additional_ev_half_kwh_per_year": float(delta_half_kwh),
        "additional_ev_total_kwh_per_year": float(delta_total_kwh),
        "additional_ev_half_cost_eur_per_year": float(delta_half_kwh * electricity_price_eur_per_kwh),
        "additional_ev_total_cost_eur_per_year": float(delta_total_kwh * electricity_price_eur_per_kwh),
    }


def _front_xy(records: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    pf = _pareto_front(records)
    xy = []
    for rec in pf:
        co2 = float(rec["co2"])
        totex = float(rec["totex"])
        if np.isfinite(co2) and np.isfinite(totex):
            xy.append((co2, totex))
    if not xy:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    xy.sort(key=lambda t: t[0])
    x = np.asarray([t[0] for t in xy], dtype=float)
    y = np.asarray([t[1] for t in xy], dtype=float)
    x_unique, idx = np.unique(x, return_index=True)
    y_unique = y[idx]
    return x_unique, y_unique


def _plot_ref_vs_ev_total_front_and_deviation(
    *,
    reference_records: list[dict[str, Any]],
    ev_total_records: list[dict[str, Any]],
    out_file: Path,
) -> list[dict[str, float]]:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": "TeX Gyre Termes",
            "font.size": 9,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    x_ref, y_ref = _front_xy(reference_records)
    x_ev, y_ev = _front_xy(ev_total_records)
    if len(x_ref) < 2 or len(x_ev) < 2:
        raise ValueError("Need at least two Pareto-front points in both cases for deviation plot.")

    x_min = max(float(np.min(x_ref)), float(np.min(x_ev)))
    x_max = min(float(np.max(x_ref)), float(np.max(x_ev)))
    if not (np.isfinite(x_min) and np.isfinite(x_max)) or x_max <= x_min:
        raise ValueError("No overlapping CO2 range between reference and EV-total fronts.")

    x_common = np.linspace(x_min, x_max, 250)
    y_ref_i = np.interp(x_common, x_ref, y_ref)
    y_ev_i = np.interp(x_common, x_ev, y_ev)
    with np.errstate(divide="ignore", invalid="ignore"):
        dev_pct = (y_ev_i - y_ref_i) / y_ref_i * 100.0

    fig, axes = plt.subplots(nrows=2, ncols=1, sharex=True, figsize=(8.2, 6.0))
    axes[0].plot(x_ref, y_ref, color="#4c78a8", linewidth=1.4, label="Reference Pareto")
    axes[0].plot(x_ev, y_ev, color="#54a24b", linewidth=1.4, label="EV total Pareto")
    axes[0].set_ylabel("Ann. TOTEX")
    axes[0].grid(True, alpha=0.25, linewidth=0.6)
    axes[0].legend(frameon=False, loc="best")
    axes[0].set_title("Reference vs EV total: Pareto fronts and deviation")

    axes[1].plot(x_common, dev_pct, color="#111111", linewidth=1.2)
    axes[1].axhline(0.0, color="#666666", linestyle="--", linewidth=0.9)
    axes[1].set_xlabel("Ann. CO$_2$-eq.")
    axes[1].set_ylabel("TOTEX deviation [%]\n(EV total vs Ref)")
    axes[1].grid(True, alpha=0.25, linewidth=0.6)

    fig.tight_layout()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=450, bbox_inches="tight")
    fig.savefig(out_file.with_suffix(".png"), dpi=250, bbox_inches="tight")
    plt.close(fig)

    rows: list[dict[str, float]] = []
    for co2, ref_v, ev_v, dev in zip(x_common, y_ref_i, y_ev_i, dev_pct):
        rows.append(
            {
                "co2": float(co2),
                "totex_reference_interp": float(ref_v),
                "totex_ev_total_interp": float(ev_v),
                "totex_deviation_pct_ev_total_vs_ref": float(dev),
            }
        )
    return rows


def main() -> None:
    ev_half_dir = _resolve_run_dir(EV_HALF_BASE)
    ev_total_dir = _resolve_run_dir(EV_TOTAL_BASE)
    reference_dir = _resolve_run_dir(REFERENCE_BASE)

    for p in (ev_half_dir, ev_total_dir, reference_dir):
        if not p.exists():
            raise FileNotFoundError(f"Folder not found: {p}")

    fronts = {
        "Reference": _load_combined_front_from_run_dir(reference_dir),
        "EV 50%": _load_combined_front_from_run_dir(ev_half_dir),
        "EV 100%": _load_combined_front_from_run_dir(ev_total_dir),
    }
    sfh_ids, mfh_ids = _get_sfh_mfh_building_ids_for_run(DEMAND_DIRECTORY)
    building_id = BUILDING_ID_FOR_TIMESERIES or _find_default_building_id(fronts["Reference"])

    script_dir = Path(__file__).resolve().parent
    out_dir = script_dir / "_plot_outputs" / "ev_functionality"
    out_dir.mkdir(parents=True, exist_ok=True)

    _plot_pareto_compare(fronts, out_dir / "ev_pareto_front_compare.pdf")
    ref_ev_dev_rows = _plot_ref_vs_ev_total_front_and_deviation(
        reference_records=fronts["Reference"],
        ev_total_records=fronts["EV 100%"],
        out_file=out_dir / "ev_pareto_front_reference_vs_ev_total_with_deviation.pdf",
    )
    _plot_e_demand_compare(fronts, out_dir / "ev_strombedarf_from_e_demand_compare.pdf")
    _plot_single_building_ev_demand_profiles(
        demand_dir=DEMAND_DIRECTORY,
        building_id=building_id,
        out_file=out_dir / f"ev_single_building_year_profile_{building_id}.pdf",
    )
    building_sum_rows = _plot_multi_building_ev_demand_sums(
        demand_dir=DEMAND_DIRECTORY,
        sfh_building_ids=sfh_ids,
        mfh_building_ids=mfh_ids,
        out_file=out_dir / "ev_multi_building_annual_sums_sfh06_mfh01.pdf",
    )
    building_peak_rows = _plot_multi_building_ev_demand_peaks(
        demand_dir=DEMAND_DIRECTORY,
        sfh_building_ids=sfh_ids,
        mfh_building_ids=mfh_ids,
        out_file=out_dir / "ev_multi_building_annual_peaks_sfh06_mfh01.pdf",
    )

    summary_rows = []
    detail_rows = []
    for case_name, records in fronts.items():
        summary_rows.append(_summarise_case(case_name, records))
        for idx, rec in enumerate(records):
            detail_rows.append(
                {
                    "case": case_name,
                    "point_idx": idx,
                    "co2": float(rec.get("co2", np.nan)),
                    "totex": float(rec.get("totex", np.nan)),
                    "peak": float(rec.get("peak", np.nan)),
                    "electricity_demand": _electricity_demand_for_point(rec),
                }
            )

    _write_csv(
        out_dir / "ev_electricity_demand_summary.csv",
        summary_rows,
        [
            "case",
            "n_points",
            "electricity_demand_min",
            "electricity_demand_mean",
            "electricity_demand_max",
        ],
    )
    _write_csv(
        out_dir / "ev_electricity_demand_per_point.csv",
        detail_rows,
        [
            "case",
            "point_idx",
            "co2",
            "totex",
            "peak",
            "electricity_demand",
        ],
    )
    _write_csv(
        out_dir / "ev_multi_building_annual_sums_sfh06_mfh01.csv",
        building_sum_rows,
        [
            "building_id",
            "cluster_type",
            "sum_reference",
            "sum_ev_half",
            "sum_ev_total",
        ],
    )
    _write_csv(
        out_dir / "ev_multi_building_annual_peaks_sfh06_mfh01.csv",
        building_peak_rows,
        [
            "building_id",
            "cluster_type",
            "peak_reference",
            "peak_ev_half",
            "peak_ev_total",
        ],
    )
    _write_csv(
        out_dir / "ev_pareto_front_reference_vs_ev_total_deviation.csv",
        ref_ev_dev_rows,
        [
            "co2",
            "totex_reference_interp",
            "totex_ev_total_interp",
            "totex_deviation_pct_ev_total_vs_ref",
        ],
    )
    ev_estimate = _estimate_ev_energy_and_cost_from_annual_sums(
        building_sum_rows=building_sum_rows,
        electricity_price_eur_per_kwh=0.31,
    )
    _write_csv(
        out_dir / "ev_additional_energy_and_cost_estimate.csv",
        [ev_estimate],
        [
            "electricity_price_eur_per_kwh",
            "additional_ev_half_kwh_per_year",
            "additional_ev_total_kwh_per_year",
            "additional_ev_half_cost_eur_per_year",
            "additional_ev_total_cost_eur_per_year",
        ],
    )

    print("\n=== EV Strombedarf aus e_demand (sum) ===")
    for row in summary_rows:
        print(
            f"{row['case']:>9s}: "
            f"electricity_demand[min/mean/max]={row['electricity_demand_min']:.2f} / "
            f"{row['electricity_demand_mean']:.2f} / {row['electricity_demand_max']:.2f}"
        )

    print(f"\nWrote plot: {out_dir / 'ev_pareto_front_compare.pdf'}")
    print(f"Wrote plot: {out_dir / 'ev_pareto_front_reference_vs_ev_total_with_deviation.pdf'}")
    print(f"Wrote plot: {out_dir / 'ev_strombedarf_from_e_demand_compare.pdf'}")
    print(f"Wrote plot: {out_dir / f'ev_single_building_year_profile_{building_id}.pdf'}")
    print(f"Wrote plot: {out_dir / 'ev_multi_building_annual_sums_sfh06_mfh01.pdf'}")
    print(f"Wrote plot: {out_dir / 'ev_multi_building_annual_peaks_sfh06_mfh01.pdf'}")
    print(f"Wrote CSV:  {out_dir / 'ev_electricity_demand_summary.csv'}")
    print(f"Wrote CSV:  {out_dir / 'ev_electricity_demand_per_point.csv'}")
    print(f"Wrote CSV:  {out_dir / 'ev_multi_building_annual_sums_sfh06_mfh01.csv'}")
    print(f"Wrote CSV:  {out_dir / 'ev_multi_building_annual_peaks_sfh06_mfh01.csv'}")
    print(f"Wrote CSV:  {out_dir / 'ev_pareto_front_reference_vs_ev_total_deviation.csv'}")
    print(f"Wrote CSV:  {out_dir / 'ev_additional_energy_and_cost_estimate.csv'}")

    print("\n=== EV Strom- und Kostenabschätzung (Annual sums) ===")
    print(
        f"Preisannahme: {ev_estimate['electricity_price_eur_per_kwh']:.2f} EUR/kWh "
        f"(= {ev_estimate['electricity_price_eur_per_kwh']*100:.0f} ct/kWh)"
    )
    print(
        f"Mehrbedarf EV half vs Reference: {ev_estimate['additional_ev_half_kwh_per_year']:.0f} kWh/a "
        f"-> {ev_estimate['additional_ev_half_cost_eur_per_year']:.0f} EUR/a"
    )
    print(
        f"Mehrbedarf EV total vs Reference: {ev_estimate['additional_ev_total_kwh_per_year']:.0f} kWh/a "
        f"-> {ev_estimate['additional_ev_total_cost_eur_per_year']:.0f} EUR/a"
    )


if __name__ == "__main__":
    main()
