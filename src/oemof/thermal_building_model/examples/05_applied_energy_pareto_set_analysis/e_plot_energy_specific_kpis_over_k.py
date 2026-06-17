import pickle
import re
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.ticker import FormatStrFormatter


EXAMPLES_BASE_DIR = (
    Path(__file__).resolve().parents[1] / "03_applied_energy_optimization"
)
OUTPUT_BASE_DIR = Path(__file__).resolve().parent / "energy_specific_kpi_results"
CLUSTER_FOLDER_PATTERN = re.compile(r"^(sfh|mfh)_cluster_k(\d+)$")
DEMANDS_PKL_NAME = "demands_and_pv_potential.pkl"
COLOR_ELECTRICITY = "tab:blue"
COLOR_DHW = "tab:orange"
COLOR_HEATING_NO_REF = "tab:green"
COLOR_HEATING_ADV_REF = "#1f6b1f"
COLOR_PV = "tab:red"
COLOR_TOTAL_ENERGY = "#6b7280"
HARDCODED_UEU_XTICKS: dict[str, dict[str, list[int]]] = {
    "4580": {"SFH": [1, 4, 7, 11], "MFH": [1, 4, 7, 10, 12]},
    "5101": {"SFH": [1, 2], "MFH": [1, 5, 10, 15, 20, 25]},
    "5658": {"SFH": [1, 6, 12, 18, 23], "MFH": [1, 2, 3, 4, 5, 6]},
}
HEIGHT_VARIANTS: list[tuple[str, float]] = [
    ("h100", 1.00),
    ("h90", 0.90),
    ("h80", 0.80),
    ("h70", 0.70),
    ("h60", 0.60),
]


def compute_smart_k_ticks(valid_k: np.ndarray, max_ticks: int = 5) -> np.ndarray:
    values = np.sort(np.unique(valid_k.astype(int)))
    if len(values) <= max_ticks:
        return values
    idx = np.linspace(0, len(values) - 1, max_ticks).round().astype(int)
    return np.sort(np.unique(values[idx]))


def _extract_ueu_suffix(ueu_identifier: str | None) -> str | None:
    if not ueu_identifier:
        return None

    token = str(ueu_identifier)
    match = re.search(r"SEC(\d{4})", token)
    if match and match.group(1) in HARDCODED_UEU_XTICKS:
        return match.group(1)

    match = re.search(r"(\d{4})$", token)
    if match and match.group(1) in HARDCODED_UEU_XTICKS:
        return match.group(1)

    return None


def _extract_ueu_filename_suffix(ueu_identifier: str | None) -> str:
    if not ueu_identifier:
        return "unknown_ueu"
    token = str(ueu_identifier)
    match = re.search(r"(DENI[0-9A-Za-z]+)", token)
    if match:
        return match.group(1)
    return token.replace(" ", "_")


def _resolve_k_ticks(
    valid_k: np.ndarray,
    building_type: str,
    ueu_identifier: str | None = None,
) -> np.ndarray:
    suffix = _extract_ueu_suffix(ueu_identifier)
    btype = building_type.upper()
    if suffix is not None:
        custom_ticks = HARDCODED_UEU_XTICKS.get(suffix, {}).get(btype)
        if custom_ticks:
            return np.asarray(custom_ticks, dtype=int)

    if btype == "MFH":
        return np.sort(np.unique(valid_k.astype(int)))
    return compute_smart_k_ticks(valid_k, max_ticks=4)


def _discover_cluster_roots(base_dir: Path) -> list[Path]:
    roots: list[Path] = []
    for candidate in sorted(base_dir.iterdir()):
        if not candidate.is_dir():
            continue
        has_cluster_folder = any(
            child.is_dir() and CLUSTER_FOLDER_PATTERN.match(child.name)
            for child in candidate.iterdir()
        )
        has_reference_payload = any(
            (candidate / ref_dir / DEMANDS_PKL_NAME).exists()
            for ref_dir in ("sfh_reference", "mfh_reference", "reference")
        )
        if has_cluster_folder and has_reference_payload:
            roots.append(candidate)
    return roots


def _load_pickle(path: Path) -> dict:
    with open(path, "rb") as fh:
        data = pickle.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict payload in {path}, got {type(data)}")
    return data


def _to_float_array(values) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    return arr


def _aggregate_key(
    payload: dict,
    key: str,
    weights: dict,
    building_ids: set[str] | None = None,
    default_like: np.ndarray | None = None,
) -> np.ndarray | None:
    per_building = payload.get(key, {})
    if not isinstance(per_building, dict) or not per_building:
        if default_like is None:
            return None
        return np.zeros_like(default_like, dtype=float)

    total: np.ndarray | None = None
    for building_id, values in per_building.items():
        if building_ids is not None and building_id not in building_ids:
            continue
        series = _to_float_array(values)
        if total is None:
            total = np.zeros_like(series, dtype=float)
        elif len(total) != len(series):
            raise ValueError(
                f"Length mismatch in key '{key}' for building '{building_id}': "
                f"{len(series)} vs expected {len(total)}"
            )

        weight = float(weights.get(building_id, weights.get(str(building_id), 1.0)))
        total += series * weight

    if total is None and default_like is not None:
        return np.zeros_like(default_like, dtype=float)
    return total


def _aggregate_timeseries(payload: dict, building_ids: set[str] | None = None) -> dict[str, np.ndarray]:
    required_keys = ("warm_water_demand", "building_heating_demand", "pv_potential")
    optional_keys = (
        "building_heating_demand_no_refurbishment",
        "building_heating_demand_advanced_refurbishment",
    )
    weights = payload.get("buildings_in_cluster", {})

    aggregated: dict[str, np.ndarray] = {}
    for key in required_keys:
        total = _aggregate_key(
            payload=payload,
            key=key,
            weights=weights,
            building_ids=building_ids,
            default_like=None,
        )
        if total is None:
            raise ValueError(f"No series available for key '{key}' after filtering.")
        aggregated[key] = total

    electricity_no_ev = _aggregate_key(
        payload=payload,
        key="electricity_demand_no_ev",
        weights=weights,
        building_ids=building_ids,
        default_like=None,
    )
    if electricity_no_ev is None:
        electricity_no_ev = _aggregate_key(
            payload=payload,
            key="electricity_demand",
            weights=weights,
            building_ids=building_ids,
            default_like=None,
        )
    if electricity_no_ev is None:
        raise ValueError("No electricity demand (no_ev or legacy key) available after filtering.")

    electricity_yes_ev = _aggregate_key(
        payload=payload,
        key="electricity_demand_yes_ev",
        weights=weights,
        building_ids=building_ids,
        default_like=None,
    )
    if electricity_yes_ev is None:
        electricity_yes_ev = _aggregate_key(
            payload=payload,
            key="electricity_demand",
            weights=weights,
            building_ids=building_ids,
            default_like=None,
        )
    if electricity_yes_ev is None:
        electricity_yes_ev = electricity_no_ev.copy()
    if len(electricity_no_ev) != len(electricity_yes_ev):
        raise ValueError(
            "Length mismatch between electricity_demand_no_ev and electricity_demand_yes_ev: "
            f"{len(electricity_no_ev)} vs {len(electricity_yes_ev)}"
        )
    aggregated["electricity_demand_no_ev"] = electricity_no_ev
    aggregated["electricity_demand_yes_ev"] = electricity_yes_ev
    # Legacy alias used in older analysis code paths.
    aggregated["electricity_demand"] = electricity_no_ev

    for key in optional_keys:
        aggregated[key] = _aggregate_key(
            payload=payload,
            key=key, #ich sperre meinen rechner nicht...
            weights=weights,
            building_ids=building_ids,
            default_like=aggregated["building_heating_demand"],
        )

    return aggregated


def _compute_metrics(aggregated: dict[str, np.ndarray]) -> dict[str, float]:
    electricity_no_ev = aggregated["electricity_demand_no_ev"]
    electricity_yes_ev = aggregated.get("electricity_demand_yes_ev", electricity_no_ev)
    dhw = aggregated["warm_water_demand"]
    heating = aggregated["building_heating_demand"]
    heating_no_ref = aggregated.get(
        "building_heating_demand_no_refurbishment",
        np.zeros_like(heating, dtype=float),
    )
    heating_adv_ref = aggregated.get(
        "building_heating_demand_advanced_refurbishment",
        np.zeros_like(heating, dtype=float),
    )
    pv = aggregated["pv_potential"]
    # SO ATTENTION!: total and peak total energy demand are re-computed
    # in post-processing as electricity (no EV) + DHW + heating demand (advanced refurbishment).
    total_energy = electricity_no_ev + dhw + heating_adv_ref

    return {
        "total_electricity": float(np.sum(electricity_no_ev)),
        "total_electricity_no_ev": float(np.sum(electricity_no_ev)),
        "total_electricity_yes_ev": float(np.sum(electricity_yes_ev)),
        "total_dhw": float(np.sum(dhw)),
        "total_heating": float(np.sum(heating)),
        "total_heating_no_refurbishment": float(np.sum(heating_no_ref)),
        "total_heating_advanced_refurbishment": float(np.sum(heating_adv_ref)),
        "total_energy_demand": float(np.sum(total_energy)),
        "total_pv": float(np.sum(pv)),
        "peak_electricity": float(np.max(electricity_no_ev)),
        "peak_electricity_no_ev": float(np.max(electricity_no_ev)),
        "peak_electricity_yes_ev": float(np.max(electricity_yes_ev)),
        "peak_dhw": float(np.max(dhw)),
        "peak_heating": float(np.max(heating)),
        "peak_heating_no_refurbishment": float(np.max(heating_no_ref)),
        "peak_heating_advanced_refurbishment": float(np.max(heating_adv_ref)),
        "peak_total_energy_demand": float(np.max(total_energy)),
        "peak_pv": float(np.max(pv)),
    }


def _safe_ratio(value: float, reference: float) -> float:
    if np.isclose(reference, 0.0):
        return np.nan
    return float(value / reference)


def _series_with_fallback(df: pd.DataFrame, preferred: str, fallback: str) -> pd.Series:
    if preferred in df.columns:
        return df[preferred]
    return df[fallback]


def _load_reference_building_ids(cluster_root: Path) -> dict[str, set[str]]:
    gpkg_path = cluster_root / f"{cluster_root.name}.gpkg"
    if not gpkg_path.exists():
        return {"SFH": set(), "MFH": set()}

    gdf = gpd.read_file(gpkg_path)
    if "building_id" not in gdf.columns or "tabula_building_type" not in gdf.columns:
        return {"SFH": set(), "MFH": set()}

    sfh_ids = set(gdf.loc[gdf["tabula_building_type"] == "SFH", "building_id"].astype(str))
    mfh_ids = set(gdf.loc[gdf["tabula_building_type"] == "MFH", "building_id"].astype(str))
    return {"SFH": sfh_ids, "MFH": mfh_ids}


def _resolve_reference_payload_path(cluster_root: Path, building_type: str) -> Path | None:
    type_specific = cluster_root / f"{building_type.lower()}_reference" / DEMANDS_PKL_NAME
    if type_specific.exists():
        return type_specific
    legacy = cluster_root / "reference" / DEMANDS_PKL_NAME
    if legacy.exists():
        return legacy
    return None


def _build_summary_for_building_type(cluster_root: Path, building_type: str) -> pd.DataFrame:
    type_token = building_type.lower()
    cluster_folders: list[tuple[int, Path]] = []
    for child in sorted(cluster_root.iterdir()):
        if not child.is_dir():
            continue
        match = CLUSTER_FOLDER_PATTERN.match(child.name)
        if not match:
            continue
        folder_type, k_value = match.group(1), int(match.group(2))
        if folder_type != type_token:
            continue
        payload_path = child / DEMANDS_PKL_NAME
        if payload_path.exists():
            cluster_folders.append((k_value, child))

    if not cluster_folders:
        return pd.DataFrame()

    print(
        "SO ATTENTION! Re-computing total_energy_demand and peak_total_energy_demand "
        "in post-processing as electricity + DHW + heating demand (advanced refurbishment)."
    )

    reference_payload_path = _resolve_reference_payload_path(cluster_root, building_type)
    if reference_payload_path is None:
        raise FileNotFoundError(
            "Reference payload missing. Expected one of: "
            f"{cluster_root / (building_type.lower() + '_reference') / DEMANDS_PKL_NAME} "
            f"or {cluster_root / 'reference' / DEMANDS_PKL_NAME}"
        )
    reference_payload = _load_pickle(reference_payload_path)

    reference_ids_by_type = _load_reference_building_ids(cluster_root)
    selected_ref_ids = reference_ids_by_type.get(building_type, set())
    if not selected_ref_ids:
        # fallback: if gpkg is unavailable, compare against full reference payload
        selected_ref_ids = None

    reference_aggregated = _aggregate_timeseries(reference_payload, building_ids=selected_ref_ids)
    reference_metrics = _compute_metrics(reference_aggregated)

    rows = []
    for k_value, folder in cluster_folders:
        cluster_payload = _load_pickle(folder / DEMANDS_PKL_NAME)
        cluster_aggregated = _aggregate_timeseries(cluster_payload)
        cluster_metrics = _compute_metrics(cluster_aggregated)

        row = {"k": k_value}
        for metric_name, metric_value in cluster_metrics.items():
            row[f"{metric_name}_cluster"] = metric_value
            row[f"{metric_name}_ref"] = reference_metrics[metric_name]
            row[f"{metric_name}_ratio"] = _safe_ratio(metric_value, reference_metrics[metric_name])
            row[f"{metric_name}_delta_pct"] = (row[f"{metric_name}_ratio"] - 1.0) * 100.0
        rows.append(row)

    return pd.DataFrame(rows).sort_values("k").reset_index(drop=True)


def plot_energy_kpis_over_k(
    summary_df: pd.DataFrame,
    building_type: str,
    save_path: str | None = None,
    highlight_k: int | None = None,
    ueu_identifier: str | None = None,
    font_family: str = "TeX Gyre Termes",
    font_size: int = 9,
    width_cm: float = 15.11293,
    height_cm: float = 4.8,
    marker_size: float = 2.4,
    line_width: float = 1.2,
):
    df = summary_df.copy().sort_values("k").reset_index(drop=True)

    width_inch = width_cm / 2.54
    height_inch = height_cm / 2.54

    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": font_family,
            "font.size": font_size,
            "axes.labelsize": font_size,
            "axes.titlesize": font_size,
            "xtick.labelsize": font_size,
            "ytick.labelsize": font_size,
            "legend.fontsize": font_size,
            "mathtext.fontset": "cm",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig = plt.figure(figsize=(width_inch, height_inch))
    gs = fig.add_gridspec(
        nrows=2,
        ncols=2,
        height_ratios=[0.32, 1.0],
        hspace=0.50,
        wspace=0.55,
    )

    ax_leg = fig.add_subplot(gs[0, :])
    ax_leg.axis("off")
    axes = [fig.add_subplot(gs[1, i]) for i in range(2)]

    x = df["k"].to_numpy()
    valid_mask = np.isfinite(x)
    valid_k = x[valid_mask]
    if len(valid_k) == 0:
        raise ValueError("No valid k values found.")
    x_min = valid_k.min()
    x_max = valid_k.max()

    def add_highlight(ax):
        if highlight_k is not None:
            ax.axvline(highlight_k, linestyle="--", linewidth=1.0, color="0.35")

    # Panel 1: Annual totals ratios vs reference
    ax = axes[0]
    total_electricity_no_ev_ratio = _series_with_fallback(
        df, "total_electricity_no_ev_ratio", "total_electricity_ratio"
    )
    ax.plot(
        df["k"],
        total_electricity_no_ev_ratio,
        color=COLOR_ELECTRICITY,
        marker="s",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax.plot(
        df["k"],
        df["total_dhw_ratio"],
        color=COLOR_DHW,
        marker="o",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax.plot(
        df["k"],
        df["total_heating_advanced_refurbishment_ratio"],
        color=COLOR_HEATING_ADV_REF,
        marker="^",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax.plot(
        df["k"],
        df["total_energy_demand_ratio"],
        color=COLOR_TOTAL_ENERGY,
        marker="x",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="--",
        alpha=0.95,
    )
    ax.plot(
        df["k"],
        df["total_pv_ratio"],
        color=COLOR_PV,
        marker="D",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax.axhline(1.0, color="0.35", linestyle=":", linewidth=1.0)
    add_highlight(ax)
    ax.set_title(f"{building_type}: Annual Totals")
    ax.set_ylabel("Ratio to ref in -", labelpad=6)
    ax.grid(True, alpha=0.3)

    # Panel 2: Peak ratios vs reference
    ax = axes[1]
    peak_electricity_no_ev_ratio = _series_with_fallback(
        df, "peak_electricity_no_ev_ratio", "peak_electricity_ratio"
    )
    ax.plot(
        df["k"],
        peak_electricity_no_ev_ratio,
        color=COLOR_ELECTRICITY,
        marker="s",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax.plot(
        df["k"],
        df["peak_dhw_ratio"],
        color=COLOR_DHW,
        marker="o",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax.plot(
        df["k"],
        df["peak_heating_advanced_refurbishment_ratio"],
        color=COLOR_HEATING_ADV_REF,
        marker="^",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax.plot(
        df["k"],
        df["peak_total_energy_demand_ratio"],
        color=COLOR_TOTAL_ENERGY,
        marker="x",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="--",
        alpha=0.95,
    )
    ax.plot(
        df["k"],
        df["peak_pv_ratio"],
        color=COLOR_PV,
        marker="D",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax.axhline(1.0, color="0.35", linestyle=":", linewidth=1.0)
    add_highlight(ax)
    ax.set_title(f"{building_type}: Annual Peaks")
    ax.set_ylabel("Ratio to ref in -", labelpad=6)
    ax.grid(True, alpha=0.3)

    xticks = _resolve_k_ticks(
        valid_k=valid_k,
        building_type=building_type,
        ueu_identifier=ueu_identifier,
    )

    for ax in axes:
        ax.set_xlim(x_min, x_max)
        ax.set_xticks(xticks)
        ax.set_xlabel(r"Number of clusters $k$", labelpad=1.0)
        ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
        ax.tick_params(axis="both", pad=2)

    legend_handles = [
        Line2D([0], [0], color=COLOR_ELECTRICITY, marker="s", linewidth=line_width, markersize=marker_size, label="Electricity demand"),
        Line2D([0], [0], color=COLOR_DHW, marker="o", linewidth=line_width, markersize=marker_size, label="DHW"),
        Line2D([0], [0], color=COLOR_HEATING_ADV_REF, marker="^", linewidth=line_width, linestyle="-", markersize=marker_size, label="Heating demand"),
        Line2D([0], [0], color=COLOR_TOTAL_ENERGY, marker="x", linestyle="--", linewidth=line_width, markersize=marker_size, label="Total energy demand"),
        Line2D([0], [0], color=COLOR_PV, marker="D", linewidth=line_width, markersize=marker_size, label="PV potential"),
        Line2D([0], [0], color="0.35", linestyle=":", linewidth=1.0, label="Reference ratio = 1"),
    ]
    ax_leg.legend(
        handles=legend_handles,
        loc="center",
        ncol=4,
        frameon=False,
        handlelength=1.8,
        columnspacing=1.8,
    )
    fig.subplots_adjust(left=0.09, right=0.985, bottom=0.14, top=0.95)

    if save_path is not None:
        fig.savefig(save_path)

    return fig, axes


def _plot_energy_kpi_row(
    axes_row,
    df: pd.DataFrame,
    building_type: str,
    highlight_k: int | None,
    ueu_identifier: str | None,
    marker_size: float,
    line_width: float,
    show_xlabel: bool,
):
    ax_total, ax_peak = axes_row
    x = df["k"].to_numpy()
    valid_mask = np.isfinite(x)
    valid_k = x[valid_mask]
    if len(valid_k) == 0:
        raise ValueError(f"No valid k values found for {building_type}.")

    x_min = valid_k.min()
    x_max = valid_k.max()
    xticks = _resolve_k_ticks(
        valid_k=valid_k,
        building_type=building_type,
        ueu_identifier=ueu_identifier,
    )

    def _add_highlight(ax):
        if highlight_k is not None:
            ax.axvline(highlight_k, linestyle="--", linewidth=1.0, color="0.35")

    # Totals
    total_electricity_no_ev_ratio = _series_with_fallback(
        df, "total_electricity_no_ev_ratio", "total_electricity_ratio"
    )
    ax_total.plot(
        df["k"],
        total_electricity_no_ev_ratio,
        color=COLOR_ELECTRICITY,
        marker="s",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax_total.plot(
        df["k"],
        df["total_dhw_ratio"],
        color=COLOR_DHW,
        marker="o",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax_total.plot(
        df["k"],
        df["total_heating_advanced_refurbishment_ratio"],
        color=COLOR_HEATING_ADV_REF,
        marker="^",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax_total.plot(
        df["k"],
        df["total_energy_demand_ratio"],
        color=COLOR_TOTAL_ENERGY,
        marker="x",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="--",
        alpha=0.95,
    )
    ax_total.plot(
        df["k"],
        df["total_pv_ratio"],
        color=COLOR_PV,
        marker="D",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax_total.axhline(1.0, color="0.35", linestyle=":", linewidth=1.0)
    _add_highlight(ax_total)
    ax_total.set_title(f"{building_type}: Annual Totals")
    ax_total.set_ylabel("Ratio to ref in -", labelpad=6)
    ax_total.grid(True, alpha=0.3)

    # Peaks
    peak_electricity_no_ev_ratio = _series_with_fallback(
        df, "peak_electricity_no_ev_ratio", "peak_electricity_ratio"
    )
    ax_peak.plot(
        df["k"],
        peak_electricity_no_ev_ratio,
        color=COLOR_ELECTRICITY,
        marker="s",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax_peak.plot(
        df["k"],
        df["peak_dhw_ratio"],
        color=COLOR_DHW,
        marker="o",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax_peak.plot(
        df["k"],
        df["peak_heating_advanced_refurbishment_ratio"],
        color=COLOR_HEATING_ADV_REF,
        marker="^",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax_peak.plot(
        df["k"],
        df["peak_total_energy_demand_ratio"],
        color=COLOR_TOTAL_ENERGY,
        marker="x",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="--",
        alpha=0.95,
    )
    ax_peak.plot(
        df["k"],
        df["peak_pv_ratio"],
        color=COLOR_PV,
        marker="D",
        markersize=marker_size,
        linewidth=line_width,
        linestyle="-",
        alpha=0.75,
    )
    ax_peak.axhline(1.0, color="0.35", linestyle=":", linewidth=1.0)
    _add_highlight(ax_peak)
    ax_peak.set_title(f"{building_type}: Annual Peaks")
    ax_peak.set_ylabel("Ratio to ref in -", labelpad=6)
    ax_peak.grid(True, alpha=0.3)

    for ax in (ax_total, ax_peak):
        ax.set_xlim(x_min, x_max)
        ax.set_xticks(xticks)
        ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
        ax.tick_params(axis="both", pad=2)
        if show_xlabel:
            ax.set_xlabel(r"Number of clusters $k$", labelpad=1.0)
        else:
            ax.set_xlabel("")


def plot_energy_kpis_over_k_sfh_mfh(
    sfh_summary_df: pd.DataFrame,
    mfh_summary_df: pd.DataFrame,
    save_path: str | None = None,
    highlight_sfh_k: int | None = None,
    highlight_mfh_k: int | None = None,
    ueu_identifier: str | None = None,
    font_family: str = "TeX Gyre Termes",
    font_size: int = 9,
    width_cm: float = 15.11293,
    height_cm: float = 8.2,
    marker_size: float = 2.4,
    line_width: float = 1.2,
):
    sfh_df = sfh_summary_df.copy().sort_values("k").reset_index(drop=True)
    mfh_df = mfh_summary_df.copy().sort_values("k").reset_index(drop=True)

    width_inch = width_cm / 2.54
    height_inch = height_cm / 2.54

    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": font_family,
            "font.size": font_size,
            "axes.labelsize": font_size,
            "axes.titlesize": font_size,
            "xtick.labelsize": font_size,
            "ytick.labelsize": font_size,
            "legend.fontsize": font_size,
            "mathtext.fontset": "cm",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig, axes = plt.subplots(
        nrows=2,
        ncols=2,
        figsize=(width_inch, height_inch),
        gridspec_kw={"hspace": 0.58, "wspace": 0.48},
    )

    # 1st row: SFH (totals, peaks), 2nd row: MFH (totals, peaks)
    _plot_energy_kpi_row(
        axes_row=axes[0],
        df=sfh_df,
        building_type="SFH",
        highlight_k=highlight_sfh_k,
        ueu_identifier=ueu_identifier,
        marker_size=marker_size,
        line_width=line_width,
        show_xlabel=False,
    )
    _plot_energy_kpi_row(
        axes_row=axes[1],
        df=mfh_df,
        building_type="MFH",
        highlight_k=highlight_mfh_k,
        ueu_identifier=ueu_identifier,
        marker_size=marker_size,
        line_width=line_width,
        show_xlabel=True,
    )

    legend_handles = [
        Line2D(
            [0],
            [0],
            color=COLOR_ELECTRICITY,
            marker="s",
            linewidth=line_width,
            markersize=marker_size,
            label="Electricity demand",
        ),
        Line2D(
            [0],
            [0],
            color=COLOR_DHW,
            marker="o",
            linewidth=line_width,
            markersize=marker_size,
            label="DHW",
        ),
        Line2D(
            [0],
            [0],
            color=COLOR_HEATING_ADV_REF,
            marker="^",
            linewidth=line_width,
            linestyle="-",
            markersize=marker_size,
            label="Heating demand",
        ),
        Line2D(
            [0],
            [0],
            color=COLOR_TOTAL_ENERGY,
            marker="x",
            linestyle="--",
            linewidth=line_width,
            markersize=marker_size,
            label="Total energy demand",
        ),
        Line2D(
            [0],
            [0],
            color=COLOR_PV,
            marker="D",
            linewidth=line_width,
            markersize=marker_size,
            label="PV potential",
        ),
        Line2D([0], [0], color="0.35", linestyle=":", linewidth=1.0, label="Reference ratio = 1"),
    ]
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        ncol=4,
        frameon=False,
        handlelength=1.8,
        columnspacing=1.8,
        bbox_to_anchor=(0.5, 1.01),
    )

    # Keep all labels and the figure legend inside the fixed canvas.
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.13, top=0.82)

    if save_path is not None:
        fig.savefig(save_path)

    return fig, axes


def main():
    cluster_roots = _discover_cluster_roots(EXAMPLES_BASE_DIR)
    if not cluster_roots:
        print(f"No eligible cluster roots found below: {EXAMPLES_BASE_DIR}")
        return

    OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

    for cluster_root in cluster_roots:
        print(f"processing: {cluster_root.name}")
        output_dir = OUTPUT_BASE_DIR / cluster_root.name
        output_dir.mkdir(parents=True, exist_ok=True)

        summaries: dict[str, pd.DataFrame] = {}
        for building_type in ("SFH", "MFH"):
            summary_df = _build_summary_for_building_type(cluster_root, building_type)
            if summary_df.empty:
                print(f"  - skip {building_type}: no cluster payloads found")
                continue

            csv_path = output_dir / f"energy_specific_kpi_summary_{building_type.lower()}.csv"
            summary_df.to_csv(csv_path, index=False)
            print(f"  - saved summary: {csv_path}")
            summaries[building_type] = summary_df

        if "SFH" in summaries and "MFH" in summaries:
            ueu_suffix = _extract_ueu_filename_suffix(cluster_root.name)
            base_height_cm = 8.2
            for height_suffix, height_scale in HEIGHT_VARIANTS:
                fig_path = (
                    output_dir
                    / f"energy_specific_kpi_over_k_sfh_mfh_{ueu_suffix}_{height_suffix}.pdf"
                )
                fig, _ = plot_energy_kpis_over_k_sfh_mfh(
                    sfh_summary_df=summaries["SFH"],
                    mfh_summary_df=summaries["MFH"],
                    save_path=str(fig_path),
                    ueu_identifier=cluster_root.name,
                    height_cm=base_height_cm * height_scale,
                )
                plt.close(fig)
                print(f"  - saved figure: {fig_path}")
        else:
            print("  - skip combined figure: need both SFH and MFH summaries")


if __name__ == "__main__":
    main()
