#!/usr/bin/env python3
"""Analyze merged Sobol result files for simple, co2 and peak datasets."""

from __future__ import annotations

import argparse
import csv
import pickle
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

try:
    from SALib.analyze import sobol
    from SALib.sample import saltelli
except ModuleNotFoundError:
    sobol = None
    saltelli = None

try:
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    plt = None


DEFAULT_INPUT_DIR = Path(
    r"C:\Users\hill_mx\Desktop\Paper UEC UEU\Ergebnisse und Präsentationen\Sobol_MFH_Simple_rresults"
)

DEFAULT_DATASET_FILES = {
    "simple": "simple_sobol_simple_merged.pkl",
    "co2": "simple_sobol_co2_merged.pkl",
    "peak": "simple_sobol_peak_merged.pkl",
}

DATASET_TITLES = {
    "simple": "Scenario A:\nReference case",
    "co2": "Scenario B:\n50% CO$_2$-eq. reduction",
    "peak": "Scenario C:\n50% CO$_2$-eq. and total peak reduction",
}

PLOT_PARAMETER_NAMES = [
    "Floor area",
    "Floor to roof area ratio",
    "Tabula construction period",
    "Number of Residents",
    "Azimuth",
    "Tilt",
]

DEFAULT_FONT_FAMILY = "TeX Gyre Termes"
DEFAULT_FONT_SIZE = 9
DEFAULT_WIDTH_CM = 15.11293
DEFAULT_HEIGHT_CM = 6.5 * 1.8


def apply_plot_style(font_family: str, font_size: float) -> None:
    if plt is None:
        return
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


def build_problem() -> dict[str, Any]:
    return {
        "num_vars": 6,
        "names": [
            "net_floor_area",
            "floor_to_roof_area_ratio",
            "tabula_year_class",
            "number_of_residents",
            "azimuth",
            "tilt",
        ],
        "bounds": [
            [0, 1],
            [0, 1],
            [1, 11],
            [0, 1],
            [0, 180],
            [30, 60],
        ],
    }


def load_pickle_dict(path: Path) -> dict[Any, Any]:
    with path.open("rb") as f:
        loaded = pickle.load(f)
    if not isinstance(loaded, dict):
        raise TypeError(f"{path.name}: expected dict, got {type(loaded).__name__}")
    return loaded


def as_counter(key: Any) -> int | None:
    if isinstance(key, bool):
        return None
    if isinstance(key, int):
        return key
    if isinstance(key, str) and key.isdigit():
        return int(key)
    return None


def as_peak_pair(value: Any) -> tuple[float | None, float | None]:
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        # Legacy fallback: only one peak value known -> interpreted as from-grid.
        return None, float(value)
    if isinstance(value, (tuple, list)):
        if len(value) == 0:
            return None, None
        peak_into = float(value[0]) if value[0] is not None else None
        peak_from = float(value[1]) if len(value) > 1 and value[1] is not None else None
        return peak_into, peak_from
    return None, None


def extract_arrays(
    data: dict[Any, Any], max_counter: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int, int]:
    co2_array = np.full(max_counter, np.nan, dtype=float)
    totex_array = np.full(max_counter, np.nan, dtype=float)
    peak_into_array = np.full(max_counter, np.nan, dtype=float)
    peak_from_array = np.full(max_counter, np.nan, dtype=float)

    skipped_invalid = 0
    skipped_out_of_range = 0

    for raw_key, entry in data.items():
        counter = as_counter(raw_key)
        if counter is None:
            skipped_invalid += 1
            continue
        if counter < 0 or counter >= max_counter:
            skipped_out_of_range += 1
            continue
        if not isinstance(entry, dict):
            skipped_invalid += 1
            continue

        co2 = entry.get("co2")
        totex = entry.get("totex")
        peak_into, peak_from = as_peak_pair(entry.get("peak"))

        if co2 is not None:
            co2_array[counter] = float(co2)
        if totex is not None:
            totex_array[counter] = float(totex)
        if peak_into is not None:
            peak_into_array[counter] = float(peak_into)
        if peak_from is not None:
            peak_from_array[counter] = float(peak_from)

    return (
        co2_array,
        totex_array,
        peak_into_array,
        peak_from_array,
        skipped_invalid,
        skipped_out_of_range,
    )


def impute_with_mean(array: np.ndarray) -> tuple[np.ndarray, int]:
    missing_mask = np.isnan(array)
    missing_count = int(np.sum(missing_mask))
    if missing_count == 0:
        return array, 0

    observed_mask = ~missing_mask
    if not np.any(observed_mask):
        raise ValueError("Cannot impute array: all values are missing.")

    mean_value = float(np.mean(array[observed_mask]))
    filled = array.copy()
    filled[missing_mask] = mean_value
    return filled, missing_count


def save_indices_csv(
    output_csv: Path,
    parameter_names: list[str],
    sobol_result: dict[str, np.ndarray],
) -> None:
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["parameter", "S1", "S1_conf", "ST", "ST_conf"])
        for i, name in enumerate(parameter_names):
            writer.writerow(
                [
                    name,
                    sobol_result["S1"][i],
                    sobol_result["S1_conf"][i],
                    sobol_result["ST"][i],
                    sobol_result["ST_conf"][i],
                ]
            )


def plot_bars_with_ci(
    sobol_result: dict[str, np.ndarray],
    title: str,
    parameter_names: list[str],
    output_path: Path,
    figsize: tuple[float, float],
    font_size: float,
) -> None:
    if plt is None:
        return
    x = np.arange(len(parameter_names))
    width = 0.38

    fig, ax = plt.subplots(figsize=figsize)
    ax.bar(
        x - width / 2,
        sobol_result["S1"],
        width=width,
        yerr=sobol_result["S1_conf"],
        capsize=4,
        label="S1",
    )
    ax.bar(
        x + width / 2,
        sobol_result["ST"],
        width=width,
        yerr=sobol_result["ST_conf"],
        capsize=4,
        label="ST",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(parameter_names, rotation=30, ha="right", rotation_mode="anchor")
    ax.set_ylabel("Sobol index")
    ax.set_title(title)
    ax.set_ylim(bottom=0)
    ax.legend()
    ax.tick_params(axis="x", labelsize=font_size)
    ax.tick_params(axis="y", labelsize=font_size)
    fig.subplots_adjust(bottom=0.34)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_heatmap(
    sobol_co2: dict[str, np.ndarray],
    sobol_totex: dict[str, np.ndarray],
    sobol_peak_into: dict[str, np.ndarray],
    sobol_peak_from: dict[str, np.ndarray],
    parameter_names: list[str],
    title: str,
    output_path: Path,
    figsize: tuple[float, float],
    font_size: float,
) -> None:
    if plt is None:
        return
    matrix = np.vstack(
        [
            sobol_co2["S1"],
            sobol_co2["ST"],
            sobol_totex["S1"],
            sobol_totex["ST"],
            sobol_peak_into["S1"],
            sobol_peak_into["ST"],
            sobol_peak_from["S1"],
            sobol_peak_from["ST"],
        ]
    )
    row_labels = [
        "CO$_2$-eq. S1",
        "CO$_2$-eq. ST",
        "TOTEX S1",
        "TOTEX ST",
        "Peak grid export S1",
        "Peak grid export ST",
        "Peak grid import S1",
        "Peak grid import ST",
    ]

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(matrix, cmap="coolwarm", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(np.arange(len(parameter_names)))
    ax.set_xticklabels(parameter_names, rotation=30, ha="right", rotation_mode="anchor")
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_yticklabels(row_labels)
    ax.set_title(title)

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(
                j,
                i,
                f"{matrix[i, j]:.2f}",
                ha="center",
                va="center",
                color="black",
                fontsize=max(font_size - 1, 6),
            )

    cbar = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.04)
    cbar.set_ticks(np.linspace(0, 1, 6))
    cbar.set_label("Sobol index")
    cbar.ax.tick_params(labelsize=font_size)
    fig.subplots_adjust(bottom=0.34, right=0.90)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_compare_scenarios_st(
    scenario_results: dict[str, dict[str, dict[str, np.ndarray]]],
    parameter_names: list[str],
    output_path: Path,
    figsize: tuple[float, float],
    font_size: float,
    index_key: str = "ST",
) -> None:
    if plt is None or not scenario_results:
        return
    if index_key not in ("S1", "ST"):
        raise ValueError(f"Unsupported Sobol index key: {index_key}")

    order = [k for k in ("simple", "co2", "peak") if k in scenario_results]
    if not order:
        return

    row_labels = ["CO$_2$-eq.", "TOTEX", "Peak grid export", "Peak grid import"]
    fig, axes = plt.subplots(
        1,
        len(order),
        figsize=figsize,
        squeeze=False,
        gridspec_kw={"wspace": 0.05},
    )
    axes = axes[0]
    im = None

    for idx, dataset_key in enumerate(order):
        res = scenario_results[dataset_key]
        matrix = np.vstack(
            [
                res["co2"][index_key],
                res["totex"][index_key],
                res["peak_into"][index_key],
                res["peak_from"][index_key],
            ]
        )

        ax = axes[idx]
        im = ax.imshow(matrix, cmap="coolwarm", vmin=0, vmax=1, aspect="auto")
        ax.set_title(DATASET_TITLES.get(dataset_key, dataset_key), fontsize=font_size)
        ax.set_xticks(np.arange(len(parameter_names)))
        ax.set_xticklabels(parameter_names, rotation=30, ha="right", rotation_mode="anchor")
        if idx == 0:
            ax.set_yticks(np.arange(len(row_labels)))
            ax.set_yticklabels(row_labels)
        else:
            ax.set_yticks(np.arange(len(row_labels)))
            ax.set_yticklabels([])

        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                ax.text(
                    j,
                    i,
                    f"{matrix[i, j]:.2f}",
                    ha="center",
                    va="center",
                    color="black",
                    fontsize=max(font_size - 1, 6),
                )

    fig.subplots_adjust(left=0.11, right=0.88, bottom=0.34, top=0.89, wspace=0.05)
    if im is not None:
        pos = axes[0].get_position()
        cax = fig.add_axes([0.895, pos.y0, 0.015, pos.height])
        cbar = fig.colorbar(im, cax=cax)
        cbar.set_ticks(np.linspace(0, 1, 6))
        if index_key == "ST":
            cbar.set_label("Total-order Sobol index (ST)")
        else:
            cbar.set_label("First-order Sobol index (S1)")
        cbar.ax.tick_params(labelsize=font_size)

    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def analyze_one_dataset(
    dataset_key: str,
    file_path: Path,
    output_dir: Path,
    problem: dict[str, Any],
    parameter_plot_names: list[str],
    base_sample_size: int,
    calc_second_order: bool,
    write_plots: bool,
    figsize: tuple[float, float],
    font_size: float,
) -> dict[str, dict[str, np.ndarray]] | None:
    scenario_title = DATASET_TITLES.get(dataset_key, dataset_key)

    print(f"\n=== Start analysis: {dataset_key} ===")
    print(f"Scenario: {scenario_title}")
    print(f"Input file: {file_path}")

    data = load_pickle_dict(file_path)
    param_values = saltelli.sample(problem, base_sample_size, calc_second_order=calc_second_order)
    max_counter = len(param_values)

    (
        co2_array,
        totex_array,
        peak_into_array,
        peak_from_array,
        skipped_invalid,
        skipped_out_of_range,
    ) = extract_arrays(data, max_counter=max_counter)

    try:
        co2_array, imputed_co2 = impute_with_mean(co2_array)
        totex_array, imputed_totex = impute_with_mean(totex_array)
        peak_into_array, imputed_peak_into = impute_with_mean(peak_into_array)
        peak_from_array, imputed_peak_from = impute_with_mean(peak_from_array)
    except ValueError as err:
        print(f"Skipped: {err}")
        return None

    sobol_co2 = sobol.analyze(problem, co2_array, calc_second_order=calc_second_order)
    sobol_totex = sobol.analyze(problem, totex_array, calc_second_order=calc_second_order)
    sobol_peak_into = sobol.analyze(
        problem, peak_into_array, calc_second_order=calc_second_order
    )
    sobol_peak_from = sobol.analyze(
        problem, peak_from_array, calc_second_order=calc_second_order
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    save_indices_csv(output_dir / f"sobol_{dataset_key}_co2_indices.csv", problem["names"], sobol_co2)
    save_indices_csv(
        output_dir / f"sobol_{dataset_key}_totex_indices.csv", problem["names"], sobol_totex
    )
    save_indices_csv(
        output_dir / f"sobol_{dataset_key}_peak_into_indices.csv", problem["names"], sobol_peak_into
    )
    save_indices_csv(
        output_dir / f"sobol_{dataset_key}_peak_from_indices.csv", problem["names"], sobol_peak_from
    )

    if write_plots:
        plot_bars_with_ci(
            sobol_co2,
            f"{scenario_title} - CO₂-eq. emissions",
            parameter_plot_names,
            output_dir / f"sobol_{dataset_key}_co2_bars.pdf",
            figsize,
            font_size,
        )
        plot_bars_with_ci(
            sobol_totex,
            f"{scenario_title} - Total expenditure (TOTEX)",
            parameter_plot_names,
            output_dir / f"sobol_{dataset_key}_totex_bars.pdf",
            figsize,
            font_size,
        )
        plot_bars_with_ci(
            sobol_peak_into,
            f"{scenario_title} - Peak grid export",
            parameter_plot_names,
            output_dir / f"sobol_{dataset_key}_peak_into_bars.pdf",
            figsize,
            font_size,
        )
        plot_bars_with_ci(
            sobol_peak_from,
            f"{scenario_title} - Peak grid import",
            parameter_plot_names,
            output_dir / f"sobol_{dataset_key}_peak_from_bars.pdf",
            figsize,
            font_size,
        )
        plot_heatmap(
            sobol_co2,
            sobol_totex,
            sobol_peak_into,
            sobol_peak_from,
            parameter_plot_names,
            f"{scenario_title} - First- and total-order Sobol indices",
            output_dir / f"sobol_{dataset_key}_heatmap.pdf",
            figsize,
            font_size,
        )

    print(f"Valid samples used: {len(co2_array)} / {max_counter}")
    print(f"Skipped invalid records: {skipped_invalid}")
    print(f"Skipped out-of-range counters: {skipped_out_of_range}")
    print(
        f"Imputed missing values with mean: "
        f"co2={imputed_co2}, totex={imputed_totex}, "
        f"peak_into={imputed_peak_into}, peak_from={imputed_peak_from}"
    )
    print(f"Saved outputs in: {output_dir}")
    return {
        "co2": sobol_co2,
        "totex": sobol_totex,
        "peak_into": sobol_peak_into,
        "peak_from": sobol_peak_from,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Sobol analysis for merged simple/co2/peak result files."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Directory containing merged pickle files (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for plots and CSVs (default: <input-dir>/sobol_analysis_outputs).",
    )
    parser.add_argument(
        "--base-sample-size",
        type=int,
        default=1024,
        help="Base Saltelli sample size used during simulation (default: 1024).",
    )
    parser.add_argument(
        "--calc-second-order",
        action="store_true",
        help="Use second-order Sobol indices. Must match simulation setup.",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=("simple", "co2", "peak"),
        default=("simple", "co2", "peak"),
        help="Which merged datasets to analyze (default: all three).",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Only write Sobol index CSV files (skip PDF plots).",
    )
    parser.add_argument(
        "--font-family",
        type=str,
        default=DEFAULT_FONT_FAMILY,
        help=f"Matplotlib font family (default: {DEFAULT_FONT_FAMILY}).",
    )
    parser.add_argument(
        "--font-size",
        type=float,
        default=DEFAULT_FONT_SIZE,
        help=f"Base font size (default: {DEFAULT_FONT_SIZE}).",
    )
    parser.add_argument(
        "--fig-width-cm",
        type=float,
        default=DEFAULT_WIDTH_CM,
        help=f"Figure width in cm (default: {DEFAULT_WIDTH_CM}).",
    )
    parser.add_argument(
        "--fig-height-cm",
        type=float,
        default=DEFAULT_HEIGHT_CM,
        help=f"Figure height in cm (default: {DEFAULT_HEIGHT_CM}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir: Path = args.input_dir
    output_dir = args.output_dir or (input_dir / "sobol_analysis_outputs")

    if np is None or sobol is None or saltelli is None:
        print("Missing dependencies. Please install/activate: numpy, SALib")
        return 5

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Input directory does not exist: {input_dir}")
        return 2

    problem = build_problem()

    write_plots = not args.no_plots
    if plt is None and write_plots:
        print("matplotlib not found -> plots disabled, CSV files only.")
        write_plots = False
    if write_plots:
        apply_plot_style(font_family=args.font_family, font_size=args.font_size)

    figsize = (args.fig_width_cm / 2.54, args.fig_height_cm / 2.54)
    comparison_figsize = (figsize[0] * 1.52, figsize[1] * 0.95)
    parameter_plot_names = PLOT_PARAMETER_NAMES if len(PLOT_PARAMETER_NAMES) == len(problem["names"]) else problem["names"]

    scenario_results: dict[str, dict[str, dict[str, np.ndarray]]] = {}

    total = len(args.datasets)
    for i, dataset in enumerate(args.datasets, start=1):
        merged_file = input_dir / DEFAULT_DATASET_FILES[dataset]
        print(f"\n[{i}/{total}] Dataset '{dataset}'")
        if not merged_file.exists():
            print(f"File missing, skipped: {merged_file}")
            continue
        result = analyze_one_dataset(
            dataset_key=dataset,
            file_path=merged_file,
            output_dir=output_dir,
            problem=problem,
            parameter_plot_names=parameter_plot_names,
            base_sample_size=args.base_sample_size,
            calc_second_order=args.calc_second_order,
            write_plots=write_plots,
            figsize=figsize,
            font_size=args.font_size,
        )
        if result is not None:
            scenario_results[dataset] = result

    if write_plots and len(scenario_results) >= 2:
        plot_compare_scenarios_st(
            scenario_results=scenario_results,
            parameter_names=parameter_plot_names,
            output_path=output_dir / "sobol_scenarios_st_comparison_heatmap.pdf",
            figsize=comparison_figsize,
            font_size=args.font_size,
            index_key="ST",
        )
        plot_compare_scenarios_st(
            scenario_results=scenario_results,
            parameter_names=parameter_plot_names,
            output_path=output_dir / "sobol_scenarios_s1_comparison_heatmap.pdf",
            figsize=comparison_figsize,
            font_size=args.font_size,
            index_key="S1",
        )
        print(f"Saved cross-scenario comparison plots (ST and S1) in: {output_dir}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
