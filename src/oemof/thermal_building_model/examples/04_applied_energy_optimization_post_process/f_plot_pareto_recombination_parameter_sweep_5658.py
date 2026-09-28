import argparse
import os
import pickle
import re
from pathlib import Path
from typing import Dict, Iterable, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from e_run_pareto_recombination_parameter_sweep_5658 import (
    _hypervolume_3d_min,
    _nearest_distances,
    _normalize_pair,
    _records_to_array,
    _reference_point,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SWEEP_DIR = (
    SCRIPT_DIR
    / "pareto_recombination_parameter_sweep_5658"
    / "2026_07_30_180154"
    / "sfh_k06_mfh_k01"
)
DEFAULT_OUTPUT_DIRNAME = "plots"
DEFAULT_NET_FLOOR_AREA_M2 = 8254.1
DEFAULT_REFERENCE_VARIANT = "paper_strict_cap4000"
DEFAULT_EXCLUDE_CAPS = [8000]

PDF_EXPORT_WIDTH_CM = 11.8
PDF_EXPORT_WIDTH_INCH = PDF_EXPORT_WIDTH_CM / 2.54
DEFAULT_HEIGHT_CM = 8.3
DEFAULT_EXTRA_QUALITY_HEIGHTS_CM = (4.0, 5.0, 6.0)
DEFAULT_FONT_SIZE = 9
DEFAULT_FONT_FAMILY = "TeX Gyre Termes"
DEFAULT_DPI = 600

OBJECTIVE_COLUMNS = {
    "co2": "Ann. GWP\nin kg CO2-eq.\nper 100 m2",
    "totex": "Ann. TOTEX\nin EUR\nper 100 m2",
    "peak": "Peak grid ex. power\nin kW\nper 100 m2",
}
FRONT_PROJECTION_PAIRS = [
    ("co2", "totex"),
    ("totex", "peak"),
    ("co2", "peak"),
]
OBJECTIVE_KEYS = ("co2", "peak", "totex")
OBJECTIVE_INDEX = {objective: index for index, objective in enumerate(OBJECTIVE_KEYS)}
DEFAULT_FRONT_VARIANTS = ["all"]

VARIANT_LABELS = {
    "paper_baseline_cap2000": "Baseline cap 2000",
    "baseline_cap1000": "Baseline cap 1000",
    "baseline_cap2000": "Baseline cap 2000",
    "baseline_cap4000": "Baseline cap 4000",
    "baseline_cap8000": "Baseline cap 8000",
    "paper_relaxed_cap500": "Relaxed cap 500",
    "relaxed_bucket_cap250": "Relaxed cap 250",
    "relaxed_bucket_cap500": "Relaxed cap 500",
    "relaxed_bucket_cap2000": "Relaxed cap 2000",
    "relaxed_bucket_cap4000": "Relaxed cap 4000",
    "relaxed_bucket_cap8000": "Relaxed cap 8000",
    "very_relaxed_cap250": "Very relaxed cap 250",
    "very_relaxed_cap2000": "Very relaxed cap 2000",
    "very_relaxed_cap4000": "Very relaxed cap 4000",
    "very_relaxed_cap8000": "Very relaxed cap 8000",
    "relaxed_bucket_cap1000": "Relaxed cap 1000",
    "baseline_cap500": "Baseline cap 500",
    "baseline_cap250": "Baseline cap 250",
    "relaxed_bucket_cap750": "Relaxed cap 750",
    "very_relaxed_cap500": "Very relaxed cap 500",
    "very_relaxed_cap1000": "Very relaxed cap 1000",
    "strict_cap250": "Strict cap 250",
    "strict_cap500": "Strict cap 500",
    "strict_cap1000": "Strict cap 1000",
    "strict_cap2000": "Strict cap 2000",
    "paper_strict_cap4000": "Strict cap 4000",
    "paper_strict_cap8000": "Strict cap 8000",
}

FAMILY_ORDER = ["strict", "baseline", "relaxed", "very relaxed"]
FAMILY_LABELS = {
    "strict": "Strict",
    "baseline": "Baseline",
    "relaxed": "Relaxed",
    "very relaxed": "Very relaxed",
}
CAP_MARKERS = {
    250: "o",
    500: "s",
    1000: "^",
    2000: "D",
    4000: "P",
    8000: "X",
}
COLORBLIND_PALETTE = [
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#56B4E9",
    "#E69F00",
    "#F0E442",
]


def _to_long_path(path: Path) -> str:
    resolved = path.resolve()
    path_str = str(resolved)
    if os.name != "nt":
        return path_str
    if path_str.startswith("\\\\?\\"):
        return path_str
    if path_str.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path_str[2:]
    return "\\\\?\\" + path_str


def _savefig_fixed_pdf_width(fig, filename: Path, *args, **kwargs) -> None:
    filename.parent.mkdir(parents=True, exist_ok=True)
    if filename.suffix.lower() == ".pdf":
        height = fig.get_size_inches()[1]
        fig.set_size_inches(PDF_EXPORT_WIDTH_INCH, height, forward=False)
    fig.savefig(_to_long_path(filename), *args, **kwargs)


def _apply_style(font_size: int, font_family: str) -> None:
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


def _linebreak_after_in_label(label: str) -> str:
    return label.replace(" in ", "\nin ")


def _save_pdf_png(fig, output_dir: Path, stem: str, dpi: int) -> None:
    _savefig_fixed_pdf_width(fig, output_dir / f"{stem}.pdf", format="pdf", dpi=dpi)
    _savefig_fixed_pdf_width(fig, output_dir / f"{stem}.png", format="png", dpi=dpi)


def _safe_suffix(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(_to_long_path(path))


def _load_pickle(path: Path):
    with open(_to_long_path(path), "rb") as fh:
        return pickle.load(fh)


def _variant_family(variant: str) -> str:
    if "very_relaxed" in variant:
        return "very relaxed"
    if "relaxed" in variant:
        return "relaxed"
    if "strict" in variant:
        return "strict"
    return "baseline"


def _variant_cap(variant: str) -> int:
    match = re.search(r"cap(\d+)", variant)
    return int(match.group(1)) if match else 0


def _sort_variants(variants: Iterable[str]) -> list[str]:
    family_rank = {family: index for index, family in enumerate(FAMILY_ORDER)}
    return sorted(
        variants,
        key=lambda variant: (
            family_rank.get(_variant_family(variant), len(family_rank)),
            _variant_cap(variant),
            variant,
        ),
    )


def _variant_output_dirs(sweep_dir: Path) -> Dict[str, Path]:
    summary = _read_csv(sweep_dir / "run_summary.csv")
    return {
        str(row["variant"]): Path(str(row["output_dir"]))
        for _, row in summary.iterrows()
    }


def _load_fronts(sweep_dir: Path) -> Dict[str, Sequence[dict]]:
    fronts = {}
    for variant, output_dir in _variant_output_dirs(sweep_dir).items():
        front_file = output_dir / "combined_front.pkl"
        fronts[variant] = _load_pickle(front_file)
    return fronts


def _prepare_metrics(
    sweep_dir: Path,
    reference_variant: str,
    exclude_caps: Sequence[int] = (),
) -> pd.DataFrame:
    summary = _read_csv(sweep_dir / "run_summary.csv")
    summary["cap"] = pd.to_numeric(summary["cap"], errors="coerce")
    if exclude_caps:
        summary = summary[~summary["cap"].isin(exclude_caps)].copy()
    fronts = _load_fronts(sweep_dir)
    fronts = {
        variant: fronts[variant]
        for variant in summary["variant"].astype(str)
        if variant in fronts
    }
    if reference_variant not in fronts:
        raise ValueError(f"Reference variant not found in sweep results: {reference_variant}")

    hv_reference_point = _reference_point(fronts.values())
    hv_by_variant = {
        variant: _hypervolume_3d_min(_records_to_array(front), hv_reference_point)
        for variant, front in fronts.items()
    }
    hv_reference = hv_by_variant[reference_variant]
    reference_arr = _records_to_array(fronts[reference_variant])
    front_arrays = {
        variant: _records_to_array(front)
        for variant, front in fronts.items()
    }
    non_empty_arrays = [arr for arr in front_arrays.values() if len(arr)]
    if non_empty_arrays:
        global_minima = np.min(np.vstack(non_empty_arrays), axis=0)
    else:
        global_minima = np.full(len(OBJECTIVE_KEYS), np.nan)
    rows = []
    for variant, front in fronts.items():
        variant_arr = front_arrays[variant]
        ref_norm, var_norm = _normalize_pair(reference_arr, variant_arr)
        ref_to_var = _nearest_distances(ref_norm, var_norm)
        var_to_ref = _nearest_distances(var_norm, ref_norm)
        hv = hv_by_variant[variant]
        variant_minima = (
            np.min(variant_arr, axis=0)
            if len(variant_arr)
            else np.full(len(OBJECTIVE_KEYS), np.nan)
        )
        extreme_metrics = {}
        for objective, index in OBJECTIVE_INDEX.items():
            global_min = float(global_minima[index])
            variant_min = float(variant_minima[index])
            deviation_percent = (
                (variant_min - global_min) / abs(global_min) * 100.0
                if np.isfinite(global_min) and abs(global_min) > 1e-12
                else np.nan
            )
            extreme_metrics[f"min_{objective}"] = variant_min
            extreme_metrics[f"global_min_{objective}"] = global_min
            extreme_metrics[f"min_{objective}_deviation_percent"] = deviation_percent
        rows.append(
            {
                "reference": reference_variant,
                "variant": variant,
                "reference_front_size": len(fronts[reference_variant]),
                "variant_front_size": len(front),
                "igd_ref_to_variant_norm": float(np.mean(ref_to_var)) if len(ref_to_var) else np.nan,
                "igd_variant_to_ref_norm": float(np.mean(var_to_ref)) if len(var_to_ref) else np.nan,
                "bidirectional_igd_norm": (
                    0.5 * (float(np.mean(ref_to_var)) + float(np.mean(var_to_ref)))
                    if len(ref_to_var) and len(var_to_ref)
                    else np.nan
                ),
                "max_ref_to_variant_norm": float(np.max(ref_to_var)) if len(ref_to_var) else np.nan,
                "hv": hv,
                "hv_reference": hv_reference,
                "hv_difference": hv - hv_reference,
                "hv_relative_to_reference": hv / hv_reference if hv_reference else np.nan,
                **extreme_metrics,
            }
        )

    metrics = pd.DataFrame(rows)
    if "runtime_s" in metrics.columns:
        metrics = metrics.drop(columns=["runtime_s"])
    data = metrics.merge(
        summary[["variant", "runtime_s", "cap", "eps_each", "eps_merge"]],
        on="variant",
        how="left",
    )
    for col in [
        "runtime_s",
        "cap",
        "bidirectional_igd_norm",
        "max_ref_to_variant_norm",
        "hv_relative_to_reference",
        "min_co2_deviation_percent",
        "min_peak_deviation_percent",
        "min_totex_deviation_percent",
    ]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["hv_deviation_percent"] = (1.0 - data["hv_relative_to_reference"]) * 100.0
    data["runtime_min"] = data["runtime_s"] / 60.0
    data["family"] = data["variant"].map(_variant_family)
    data["label"] = data["variant"].map(lambda value: VARIANT_LABELS.get(value, value))
    return data


def _family_colors() -> Dict[str, tuple]:
    return {
        "baseline": COLORBLIND_PALETTE[0],
        "relaxed": COLORBLIND_PALETTE[1],
        "very relaxed": COLORBLIND_PALETTE[2],
        "strict": COLORBLIND_PALETTE[3],
    }


def _front_colors() -> Dict[str, tuple]:
    colors = {
        "paper_baseline_cap2000": (0.15, 0.15, 0.15),
        "paper_relaxed_cap500": COLORBLIND_PALETTE[1],
        "very_relaxed_cap250": COLORBLIND_PALETTE[2],
        "paper_strict_cap8000": COLORBLIND_PALETTE[0],
    }
    family_colors = _family_colors()
    for variant in VARIANT_LABELS:
        colors.setdefault(variant, family_colors[_variant_family(variant)])
    return colors


def _add_family_cap_legend(
    fig,
    colors: Dict[str, tuple],
    y_anchor: float = 0.99,
    caps: Sequence[int] | None = None,
) -> None:
    family_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor=colors[family],
            markeredgecolor="black",
            markeredgewidth=0.35,
            markersize=5.5,
            label=FAMILY_LABELS[family],
        )
        for family in FAMILY_ORDER
    ]
    cap_values = set(caps) if caps is not None else set(CAP_MARKERS)
    cap_handles = [
        Line2D(
            [0],
            [0],
            marker=marker,
            linestyle="None",
            color="black",
            markerfacecolor="white",
            markeredgecolor="black",
            markeredgewidth=0.6,
            markersize=5.5,
            label=f"{cap}",
        )
        for cap, marker in CAP_MARKERS.items()
        if cap in cap_values
    ]
    fig.legend(
        handles=family_handles + cap_handles,
        frameon=False,
        ncol=5,
        loc="upper center",
        bbox_to_anchor=(0.5, y_anchor),
        columnspacing=1.2,
        handletextpad=0.4,
    )


def _plot_quality_tradeoff(
    data: pd.DataFrame,
    output_dir: Path,
    height_cm: float,
    dpi: int,
    suffix: str,
) -> None:
    colors = _family_colors()
    caps = sorted(int(cap) for cap in data["cap"].dropna().unique())
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(PDF_EXPORT_WIDTH_INCH, height_cm / 2.54),
        sharex=True,
    )
    plot_specs = [
        ("bidirectional_igd_norm", "IGD\nin -"),
        ("hv_deviation_percent", "Delta hypervolume\nin %"),
    ]

    for ax, (column, ylabel) in zip(axes, plot_specs):
        for family in FAMILY_ORDER:
            subset = data[data["family"] == family].sort_values("runtime_min")
            if subset.empty:
                continue
            for _, row in subset.iterrows():
                ax.scatter(
                    row["runtime_min"],
                    row[column],
                    s=34,
                    marker=CAP_MARKERS.get(int(row["cap"]), "o"),
                    color=colors[family],
                    edgecolors="black",
                    linewidths=0.35,
                    zorder=3,
                )
            ax.plot(
                subset["runtime_min"],
                subset[column],
                color=colors[family],
                linewidth=1.0,
                alpha=0.65,
                zorder=2,
            )

        ax.set_xscale("log")
        ax.set_xlabel("Runtime in min")
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3, linewidth=0.6)

    _add_family_cap_legend(fig, colors, caps=caps)
    fig.subplots_adjust(left=0.14, right=0.98, bottom=0.20, top=0.80, wspace=0.36)
    _save_pdf_png(fig, output_dir, f"pareto_recombination_sweep_quality_tradeoff_{suffix}", dpi)
    plt.close(fig)


def _plot_archive_sensitivity(
    data: pd.DataFrame,
    output_dir: Path,
    height_cm: float,
    dpi: int,
    suffix: str,
) -> None:
    colors = _family_colors()
    caps = sorted(int(cap) for cap in data["cap"].dropna().unique())
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(PDF_EXPORT_WIDTH_INCH, height_cm / 2.54),
        sharex=True,
    )
    plot_specs = [
        ("bidirectional_igd_norm", "IGD\nin -"),
        ("hv_deviation_percent", "Delta hypervolume\nin %"),
    ]

    for ax, (column, ylabel) in zip(axes, plot_specs):
        for family in FAMILY_ORDER:
            subset = data[data["family"] == family].sort_values("cap")
            if subset.empty:
                continue
            ax.plot(
                subset["cap"],
                subset[column],
                color=colors[family],
                linewidth=1.0,
                alpha=0.75,
                zorder=2,
            )
            for _, row in subset.iterrows():
                ax.scatter(
                    row["cap"],
                    row[column],
                    s=34,
                    marker=CAP_MARKERS.get(int(row["cap"]), "o"),
                    color=colors[family],
                    edgecolors="black",
                    linewidths=0.35,
                    zorder=3,
                )
        ax.set_xlabel("Archive size limit")
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3, linewidth=0.6)

    _add_family_cap_legend(fig, colors, caps=caps)
    fig.subplots_adjust(left=0.14, right=0.98, bottom=0.20, top=0.80, wspace=0.36)
    _save_pdf_png(fig, output_dir, f"pareto_recombination_sweep_archive_sensitivity_{suffix}", dpi)
    plt.close(fig)


def _plot_extreme_deviations(
    data: pd.DataFrame,
    output_dir: Path,
    height_cm: float,
    dpi: int,
    suffix: str,
) -> None:
    colors = _family_colors()
    caps = sorted(int(cap) for cap in data["cap"].dropna().unique())
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(PDF_EXPORT_WIDTH_INCH, height_cm / 2.54),
        sharex=True,
    )
    plot_specs = [
        ("min_totex_deviation_percent", "Delta min\nTOTEX in %"),
        ("min_co2_deviation_percent", "Delta min\nGWP in %"),
        ("min_peak_deviation_percent", "Delta min\npeak in %"),
    ]

    for ax, (column, ylabel) in zip(axes, plot_specs):
        for family in FAMILY_ORDER:
            subset = data[data["family"] == family].sort_values("runtime_min")
            if subset.empty:
                continue
            ax.plot(
                subset["runtime_min"],
                subset[column],
                color=colors[family],
                linewidth=1.0,
                alpha=0.65,
                zorder=2,
            )
            for _, row in subset.iterrows():
                ax.scatter(
                    row["runtime_min"],
                    row[column],
                    s=30,
                    marker=CAP_MARKERS.get(int(row["cap"]), "o"),
                    color=colors[family],
                    edgecolors="black",
                    linewidths=0.35,
                    zorder=3,
                )
        ax.axhline(0.0, color="black", linewidth=0.7, alpha=0.6)
        ax.set_xscale("log")
        ax.set_xlabel("Runtime in min")
        ax.set_ylabel(ylabel)
        max_abs_value = np.nanmax(np.abs(data[column].to_numpy(dtype=float)))
        if np.isfinite(max_abs_value) and max_abs_value < 1e-6:
            ax.set_ylim(-0.01, 0.01)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)
        ax.grid(True, alpha=0.3, linewidth=0.6)

    _add_family_cap_legend(fig, colors, caps=caps)
    fig.subplots_adjust(left=0.20, right=0.98, bottom=0.22, top=0.80, wspace=0.82)
    _save_pdf_png(fig, output_dir, f"pareto_recombination_sweep_extreme_deviations_{suffix}", dpi)
    plt.close(fig)


def _front_dataframe(front: Sequence[dict], net_floor_area_m2: float) -> pd.DataFrame:
    denominator = net_floor_area_m2 / 100.0
    rows = []
    for record in front:
        rows.append(
            {
                "co2": float(record["co2"]) / denominator,
                "peak": float(record["peak"]) / denominator,
                "totex": float(record["totex"]) / denominator,
            }
        )
    return pd.DataFrame(rows)


def _selected_variant_dirs(sweep_dir: Path, variants: Iterable[str]) -> Dict[str, Path]:
    output_dirs = _variant_output_dirs(sweep_dir)
    return {variant: output_dirs[variant] for variant in variants if variant in output_dirs}


def _resolve_front_variants(
    sweep_dir: Path,
    variants: Sequence[str],
    exclude_caps: Sequence[int] = (),
) -> list[str]:
    output_dirs = _variant_output_dirs(sweep_dir)
    if any(str(variant).lower() == "all" for variant in variants):
        selected = _sort_variants(output_dirs.keys())
    else:
        selected = [variant for variant in variants if variant in output_dirs]
    if exclude_caps:
        selected = [
            variant
            for variant in selected
            if _variant_cap(variant) not in exclude_caps
        ]
    return selected


def _plot_front_projections(
    sweep_dir: Path,
    variants: Sequence[str],
    output_dir: Path,
    net_floor_area_m2: float,
    height_cm: float,
    dpi: int,
    suffix: str,
    exclude_caps: Sequence[int] = (),
) -> None:
    colors = _front_colors()
    variants = _resolve_front_variants(sweep_dir, variants, exclude_caps=exclude_caps)
    variant_dirs = _selected_variant_dirs(sweep_dir, variants)
    fronts: Dict[str, pd.DataFrame] = {}
    for variant in variants:
        variant_dir = variant_dirs.get(variant)
        if variant_dir is None:
            continue
        front_file = variant_dir / "combined_front.pkl"
        if not front_file.exists() and os.name != "nt":
            continue
        front = _load_pickle(front_file)
        fronts[variant] = _front_dataframe(front, net_floor_area_m2)

    if not fronts:
        return

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(PDF_EXPORT_WIDTH_INCH, height_cm / 2.54),
    )
    compact_legend = len(variants) > 8
    used_legend_labels = set()
    for ax, (x_col, y_col) in zip(axes, FRONT_PROJECTION_PAIRS):
        for variant in variants:
            front = fronts.get(variant)
            if front is None or front.empty:
                continue
            ordered = front.sort_values(x_col)
            if compact_legend:
                legend_label = FAMILY_LABELS[_variant_family(variant)]
            else:
                legend_label = VARIANT_LABELS.get(variant, variant)
            if legend_label in used_legend_labels:
                legend_label = "_nolegend_"
            else:
                used_legend_labels.add(legend_label)
            ax.scatter(
                ordered[x_col],
                ordered[y_col],
                s=5,
                color=colors.get(variant, "black"),
                alpha=0.24 if compact_legend else 0.42,
                linewidths=0.0,
                label=legend_label,
            )
        ax.set_xlabel(_linebreak_after_in_label(OBJECTIVE_COLUMNS[x_col]))
        ax.set_ylabel(_linebreak_after_in_label(OBJECTIVE_COLUMNS[y_col]))
        ax.grid(True, alpha=0.3, linewidth=0.6)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        frameon=False,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.99),
    )
    fig.subplots_adjust(left=0.24, right=0.98, bottom=0.33, top=0.78, wspace=1.00)
    _save_pdf_png(fig, output_dir, f"pareto_recombination_sweep_front_projections_{suffix}", dpi)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot validation results of the Pareto recombination parameter sweep."
    )
    parser.add_argument(
        "--sweep-dir",
        type=Path,
        default=DEFAULT_SWEEP_DIR,
        help="Directory containing run_summary.csv and comparison_metrics.csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to <sweep-dir>/plots.",
    )
    parser.add_argument(
        "--reference-variant",
        default=DEFAULT_REFERENCE_VARIANT,
        help="Variant used as numerical reference for IGD and HV comparison.",
    )
    parser.add_argument(
        "--net-floor-area-m2",
        type=float,
        default=DEFAULT_NET_FLOOR_AREA_M2,
        help="Net floor area used for per-100-m2 normalization of front projections.",
    )
    parser.add_argument(
        "--front-variants",
        nargs="*",
        default=DEFAULT_FRONT_VARIANTS,
        help="Variants included in the Pareto-front projection comparison. Use 'all' for all sweep variants.",
    )
    parser.add_argument(
        "--exclude-caps",
        nargs="*",
        type=int,
        default=DEFAULT_EXCLUDE_CAPS,
        help="Archive size limits excluded from all plots and recalculated metrics.",
    )
    parser.add_argument("--height-cm", type=float, default=DEFAULT_HEIGHT_CM)
    parser.add_argument(
        "--extra-quality-heights-cm",
        nargs="*",
        type=float,
        default=list(DEFAULT_EXTRA_QUALITY_HEIGHTS_CM),
        help="Additional quality-tradeoff plot heights exported with hXX suffixes. Use an empty value to disable.",
    )
    parser.add_argument("--font-size", type=int, default=DEFAULT_FONT_SIZE)
    parser.add_argument("--font-family", default=DEFAULT_FONT_FAMILY)
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument(
        "--suffix-extra",
        default="",
        help="Optional additional suffix appended to all exported plot filenames.",
    )
    parser.add_argument(
        "--skip-front-projections",
        action="store_true",
        help="Only plot CSV-based quality and archive-sensitivity figures.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sweep_dir = args.sweep_dir.resolve()
    output_dir = args.output_dir or (sweep_dir / DEFAULT_OUTPUT_DIRNAME)
    _apply_style(args.font_size, args.font_family)

    reference_suffix = f"vs_{args.reference_variant}"
    if args.exclude_caps:
        excluded = "_".join(str(cap) for cap in sorted(args.exclude_caps))
        reference_suffix = f"{reference_suffix}_without_cap{excluded}"
    if args.suffix_extra:
        reference_suffix = f"{reference_suffix}_{_safe_suffix(args.suffix_extra)}"
    data = _prepare_metrics(
        sweep_dir,
        args.reference_variant,
        exclude_caps=args.exclude_caps,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    data.to_csv(
        _to_long_path(output_dir / f"comparison_metrics_{reference_suffix}.csv"),
        index=False,
    )
    _plot_quality_tradeoff(data, output_dir, args.height_cm, args.dpi, reference_suffix)
    for extra_height_cm in args.extra_quality_heights_cm:
        height_suffix = f"{int(round(extra_height_cm * 10)):02d}"
        _plot_quality_tradeoff(
            data,
            output_dir,
            extra_height_cm,
            args.dpi,
            f"{reference_suffix}_h{height_suffix}",
        )
    _plot_archive_sensitivity(data, output_dir, args.height_cm, args.dpi, reference_suffix)
    _plot_extreme_deviations(data, output_dir, args.height_cm, args.dpi, reference_suffix)
    if not args.skip_front_projections:
        _plot_front_projections(
            sweep_dir=sweep_dir,
            variants=args.front_variants,
            output_dir=output_dir,
            net_floor_area_m2=args.net_floor_area_m2,
            height_cm=args.height_cm,
            dpi=args.dpi,
            suffix=reference_suffix,
            exclude_caps=args.exclude_caps,
        )
    print(f"Saved plots to: {output_dir}")


if __name__ == "__main__":
    main()
