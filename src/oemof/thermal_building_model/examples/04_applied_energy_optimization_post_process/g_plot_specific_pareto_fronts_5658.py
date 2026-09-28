import argparse
import os
import pickle
from pathlib import Path
from typing import Sequence

import matplotlib
import numpy as np
from matplotlib.lines import Line2D

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SWEEP_DIR = (
    SCRIPT_DIR
    / "pareto_recombination_parameter_sweep_5658"
    / "2026_07_30_180154"
    / "sfh_k06_mfh_k01"
)
DEFAULT_OUTPUT_DIR = DEFAULT_SWEEP_DIR / "plots"
DEFAULT_OUTPUT_STEM = "specific_pareto_fronts_DENI03403000SEC5658_strict4000_relaxed4000_baseline2000"
DEFAULT_NET_FLOOR_AREA_M2 = 8254.1

PDF_EXPORT_WIDTH_CM = 11.8
DEFAULT_HEIGHT_CM = 7.0
DEFAULT_HEIGHT_VARIANTS_CM = (4.0, 5.0, 6.0, 7.0, 8.0, 9.0)
DEFAULT_DPI = 600
FONT_FAMILY = "TeX Gyre Termes"
FONT_SIZE = 9
AXIS_FONT_SIZE = 9
TICK_FONT_SIZE = 9

OBJECTIVE_ORDER = ("co2", "peak", "totex")
OBJECTIVE_INDEX = {key: idx for idx, key in enumerate(OBJECTIVE_ORDER)}
PAIR_DEFS = [
    ("co2", "totex"),
    ("totex", "peak"),
    ("co2", "peak"),
]
AXIS_LABELS = {
    "co2": {
        "x": r"Ann. GWP" + "\n" + r"in kg CO$_2$-eq." + "\n" + r"per 100 m$^2$",
        "y": r"Ann. GWP in kg" + "\n" + r"CO$_2$-eq. per 100 m$^2$",
    },
    "totex": {
        "x": r"Ann. TOTEX" + "\n" + r"in EUR" + "\n" + r"per 100 m$^2$",
        "y": r"Ann. TOTEX in EUR" + "\n" + r"per 100 m$^2$",
    },
    "peak": {
        "x": r"Peak grid ex. power" + "\n" + r"in kW" + "\n" + r"per 100 m$^2$",
        "y": r"Peak grid ex. power" + "\n" + r"in kW per 100 m$^2$",
    },
}
VARIANTS = [
    {
        "name": "paper_strict_cap4000",
        "label": "Strict Pareto-front (4000)",
        "color": "#009E73",
        "linestyle": "-",
    },
    {
        "name": "relaxed_bucket_cap4000",
        "label": "Relaxed Pareto-front (4000)",
        "color": "#D55E00",
        "linestyle": "--",
    },
    {
        "name": "paper_baseline_cap2000",
        "label": "Baseline Pareto-front (2000)",
        "color": "#0072B2",
        "linestyle": ":",
    },
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


def _apply_style() -> None:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": FONT_FAMILY,
            "font.size": FONT_SIZE,
            "axes.titlesize": FONT_SIZE,
            "axes.labelsize": AXIS_FONT_SIZE,
            "xtick.labelsize": TICK_FONT_SIZE,
            "ytick.labelsize": TICK_FONT_SIZE,
            "legend.fontsize": FONT_SIZE,
            "mathtext.fontset": "cm",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _load_pickle(path: Path):
    with open(_to_long_path(path), "rb") as fh:
        return pickle.load(fh)


def _records_to_array(records: Sequence[dict], net_floor_area_m2: float) -> np.ndarray:
    denominator = net_floor_area_m2 / 100.0
    rows = []
    for record in records:
        rows.append(
            [
                float(record["co2"]) / denominator,
                float(record["peak"]) / denominator,
                float(record["totex"]) / denominator,
            ]
        )
    return np.asarray(rows, dtype=float)


def _pareto_front_2d(points: np.ndarray) -> np.ndarray:
    points = points[np.isfinite(points).all(axis=1)]
    if len(points) == 0:
        return points
    order = np.lexsort((points[:, 1], points[:, 0]))
    sorted_points = points[order]
    keep = []
    best_y = np.inf
    for point in sorted_points:
        if point[1] < best_y - 1e-12:
            keep.append(point)
            best_y = point[1]
    return np.asarray(keep, dtype=float)


def _load_variant_fronts(sweep_dir: Path, net_floor_area_m2: float) -> list[dict]:
    fronts = []
    for variant in VARIANTS:
        front_path = sweep_dir / next(
            folder.name
            for folder in sweep_dir.iterdir()
            if folder.is_dir() and folder.name.endswith(variant["name"])
        ) / "combined_front.pkl"
        records = _load_pickle(front_path)
        fronts.append(
            {
                **variant,
                "points": _records_to_array(records, net_floor_area_m2),
                "source": front_path,
            }
        )
    return fronts


def _plot_specific_fronts(
    fronts: list[dict],
    output_dir: Path,
    output_stem: str,
    height_cm: float,
    dpi: int,
) -> None:
    _apply_style()
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(PDF_EXPORT_WIDTH_CM / 2.54, height_cm / 2.54),
    )

    for ax, (x_key, y_key) in zip(axes, PAIR_DEFS):
        x_idx = OBJECTIVE_INDEX[x_key]
        y_idx = OBJECTIVE_INDEX[y_key]
        for front in fronts:
            points = front["points"][:, [x_idx, y_idx]]
            pareto = _pareto_front_2d(points)
            ax.scatter(
                points[:, 0],
                points[:, 1],
                color=front["color"],
                marker="o",
                s=2.2,
                alpha=0.075,
                linewidths=0.0,
                zorder=2,
            )
            ax.plot(
                pareto[:, 0],
                pareto[:, 1],
                color=front["color"],
                linestyle=front["linestyle"],
                linewidth=1.65,
                alpha=0.95,
                zorder=3,
            )
        ax.set_xlabel(AXIS_LABELS[x_key]["x"])
        ax.set_ylabel(AXIS_LABELS[y_key]["y"], labelpad=5.0)
        ax.grid(True, alpha=0.3, linewidth=0.6)
        ax.tick_params(axis="both", which="major", pad=1.5)

    handles = [
        Line2D(
            [0],
            [0],
            color="0.45",
            marker="o",
            linestyle="None",
            markerfacecolor="0.45",
            markeredgewidth=0.0,
            markersize=3.6,
            alpha=0.35,
            label="Solution points",
        )
    ]
    for front in fronts:
        handles.append(
            Line2D(
                [0],
                [0],
                color=front["color"],
                linestyle=front["linestyle"],
                linewidth=1.85,
                label=front["label"],
            )
        )
    fig.legend(
        handles=handles,
        frameon=False,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        columnspacing=1.0,
        handletextpad=0.5,
        prop={"size": FONT_SIZE},
    )
    axes[0].yaxis.set_label_coords(-0.34, 0.5)
    fig.subplots_adjust(left=0.16, right=0.992, bottom=0.34, top=0.75, wspace=0.55)

    output_dir.mkdir(parents=True, exist_ok=True)
    for suffix, save_kwargs in {
        "pdf": {"format": "pdf", "dpi": dpi},
        "png": {"format": "png", "dpi": dpi},
    }.items():
        path = output_dir / f"{output_stem}.{suffix}"
        if suffix == "pdf":
            fig.set_size_inches(PDF_EXPORT_WIDTH_CM / 2.54, height_cm / 2.54, forward=False)
        fig.savefig(_to_long_path(path), **save_kwargs)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot selected Pareto recombination fronts for UEU 5658."
    )
    parser.add_argument("--sweep-dir", type=Path, default=DEFAULT_SWEEP_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-stem", default=DEFAULT_OUTPUT_STEM)
    parser.add_argument("--net-floor-area-m2", type=float, default=DEFAULT_NET_FLOOR_AREA_M2)
    parser.add_argument("--height-cm", type=float, default=DEFAULT_HEIGHT_CM)
    parser.add_argument(
        "--height-variants-cm",
        nargs="*",
        type=float,
        default=list(DEFAULT_HEIGHT_VARIANTS_CM),
        help="Height variants exported with hXX suffixes. Use an empty value to disable.",
    )
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fronts = _load_variant_fronts(args.sweep_dir.resolve(), args.net_floor_area_m2)
    _plot_specific_fronts(
        fronts=fronts,
        output_dir=args.output_dir.resolve(),
        output_stem=args.output_stem,
        height_cm=args.height_cm,
        dpi=args.dpi,
    )
    for height_cm in args.height_variants_cm:
        height_suffix = f"h{int(round(height_cm * 10)):02d}"
        _plot_specific_fronts(
            fronts=fronts,
            output_dir=args.output_dir.resolve(),
            output_stem=f"{args.output_stem}_{height_suffix}",
            height_cm=height_cm,
            dpi=args.dpi,
        )
    print(f"Saved selected Pareto-front projections to: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
