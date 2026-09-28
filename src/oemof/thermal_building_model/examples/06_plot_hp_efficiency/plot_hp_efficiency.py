import argparse
import sys
from pathlib import Path
from typing import Iterable

import matplotlib
import numpy as np

if "--show" not in sys.argv:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator, PercentFormatter


JOURNAL_FONT_FAMILY = "TeX Gyre Termes"
JOURNAL_FONT_SIZE = 9
JOURNAL_DPI = 600
JOURNAL_FIG_WIDTH_CM = 11.8
JOURNAL_FIGSIZE = (JOURNAL_FIG_WIDTH_CM / 2.54, 2.8)
# PDF export contract: every saved PDF page from this plot script must be 11.8 cm wide.
# Do not pass bbox_inches="tight" for PDF output; it changes the final PDF bounding box.
DEFAULT_SIZE_SCALES = (0.9, 0.8, 0.7, 0.6)

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "plot_outputs"


DATA = {
    "external_temperature_mid_c": np.array([-12.5, -7.5, -2.5, 2.5, 7.5, 12.5]),
    "share_annual_work": np.array([0.06, 0.09, 0.21, 0.35, 0.22, 0.07]),
    "gas_heater_90_70": np.array([0.93, 0.95, 1.00, 1.07, 1.11, 1.11]),
    "gas_heater_40_30": np.array([1.11, 1.11, 1.11, 1.11, 1.11, 1.11]),
    "air_hp_55_45": np.array([1.18, 1.42, 1.71, 2.12, 2.63, 3.03]),
    "air_hp_45_35": np.array([1.53, 1.81, 2.20, 2.81, 3.50, 4.00]),
    "air_hp_35_25": np.array([2.02, 2.54, 3.05, 3.73, 4.51, 5.18]),
}


def _savefig_fixed_pdf_width(fig, filename, *args, **kwargs):
    file_suffix = Path(filename).suffix.lower() if filename is not None else ""
    fmt = str(kwargs.get("format", "")).lower()
    if file_suffix == ".pdf" or fmt == "pdf":
        height = fig.get_size_inches()[1]
        fig.set_size_inches(JOURNAL_FIG_WIDTH_CM / 2.54, height, forward=False)
        kwargs.pop("bbox_inches", None)
        kwargs["format"] = "pdf"
    fig.savefig(filename, *args, **kwargs)


SERIES = [
    {
        "key": "air_hp_55_45",
        "label": r"ASHP (55/45 $^\circ$C)",
        "print_label": "ASHP 55/45 degC",
        "color": "#7FCDBB",
        "linestyle": (0, (4, 4)),
    },
    {
        "key": "air_hp_35_25",
        "label": r"ASHP (35/25 $^\circ$C)",
        "print_label": "ASHP 35/25 degC",
        "color": "#006D2C",
        "linestyle": (0, (1, 2)),
    },
    {
        "key": "air_hp_45_35",
        "label": r"ASHP (45/35 $^\circ$C)",
        "print_label": "ASHP 45/35 degC",
        "color": "#31A354",
        "linestyle": "--",
    },
    {
        "key": "gas_heater_40_30",
        "label": r"Gas heater (40/30 $^\circ$C)",
        "print_label": "Gas heater 40/30 degC",
        "color": "#0072B2",
        "linestyle": "-",
        "linewidth": 1.8,
    },
    {
        "key": "gas_heater_90_70",
        "label": r"Gas heater (90/70 $^\circ$C)",
        "print_label": "Gas heater 90/70 degC",
        "color": "#56B4E9",
        "linestyle": (0, (0.6, 2.0)),
        "linewidth": 1.2,
    },
]


def _set_journal_style(
    font_family: str = JOURNAL_FONT_FAMILY,
    font_size: int = JOURNAL_FONT_SIZE,
) -> None:
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


def _format_decimal_comma(value: float, _position: int | None = None) -> str:
    if np.isclose(value, round(value)):
        return f"{int(round(value))},0"
    return f"{value:.1f}".replace(".", ",")


def _format_temperature(value: float, _position: int | None = None) -> str:
    if np.isclose(value, round(value)):
        return str(int(round(value)))
    return f"{value:.1f}".replace(".", ",")


def _weighted_mean(values: np.ndarray, shares: np.ndarray) -> float:
    return float(np.sum(values * shares) / np.sum(shares))


def _weighted_efficiencies() -> dict[str, float]:
    shares = DATA["share_annual_work"]
    return {
        item["print_label"]: _weighted_mean(DATA[item["key"]], shares)
        for item in SERIES
    }


def plot_hp_efficiency(
    output_dir: Path,
    filename_stem: str = "hp_efficiency_by_external_temperature",
    formats: Iterable[str] = ("pdf", "png"),
    figsize: tuple[float, float] = JOURNAL_FIGSIZE,
    font_size: int = JOURNAL_FONT_SIZE,
    font_family: str = JOURNAL_FONT_FAMILY,
    show: bool = False,
    label_bars: bool = False,
    legend_ncol: int = 3,
    legend_bbox_y: float = 0.99,
    layout_top: float = 0.86,
    efficiency_tick_step: float = 0.5,
    share_tick_step: float = 5.0,
) -> list[Path]:
    _set_journal_style(font_family=font_family, font_size=font_size)

    temperatures = DATA["external_temperature_mid_c"]
    shares = DATA["share_annual_work"]

    fig, ax_eff = plt.subplots(figsize=figsize)
    ax_share = ax_eff.twinx()

    ax_eff.set_zorder(ax_share.get_zorder() + 1)
    ax_eff.patch.set_visible(False)

    bar_color = "#7F8C8D"
    bar_edge = "#5F6A6A"
    bars = ax_share.bar(
        temperatures,
        shares * 100.0,
        width=2.0,
        color=bar_color,
        edgecolor=bar_edge,
        linewidth=0.5,
        label="Share annual work",
        zorder=1,
    )

    line_handles = []
    for item in SERIES:
        (line,) = ax_eff.plot(
            temperatures,
            DATA[item["key"]],
            color=item["color"],
            linestyle=item["linestyle"],
            linewidth=item.get("linewidth", 2.0),
            solid_capstyle="round",
            dash_capstyle="round",
            label=item["label"],
            zorder=3,
        )
        line_handles.append(line)

    ax_eff.set_xlabel(r"External temperature in $^\circ$C")
    ax_eff.set_ylabel("Efficiency in -")
    ax_share.set_ylabel("Share of annual work for\nexternal temperature in %")

    ax_eff.set_xlim(-15, 15)
    ax_eff.set_ylim(0, 5.5)
    ax_share.set_ylim(0, 40)

    ax_eff.set_xticks(temperatures)
    ax_eff.yaxis.set_major_locator(MultipleLocator(efficiency_tick_step))
    ax_share.yaxis.set_major_locator(MultipleLocator(share_tick_step))

    ax_eff.xaxis.set_major_formatter(FuncFormatter(_format_temperature))
    ax_eff.yaxis.set_major_formatter(FuncFormatter(_format_decimal_comma))
    ax_share.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))

    ax_eff.grid(True, color="#b7b7b7", linewidth=0.6, alpha=0.8)
    ax_eff.set_axisbelow(True)

    if label_bars:
        y_left_max = ax_eff.get_ylim()[1]
        y_right_max = ax_share.get_ylim()[1]
        for temperature, share in zip(temperatures, shares):
            label_y = (share * 100.0 / y_right_max) * y_left_max
            ax_eff.annotate(
                f"{share:.0%}",
                xy=(temperature, label_y),
                xytext=(0, -8),
                textcoords="offset points",
                ha="center",
                va="top",
                fontsize=font_size,
                bbox={
                    "boxstyle": "square,pad=0.25",
                    "facecolor": "#E8ECEC",
                    "edgecolor": "none",
                },
                color="black",
                zorder=5,
            )

    handles = [bars] + line_handles
    labels = [handle.get_label() for handle in handles]
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, legend_bbox_y),
        frameon=False,
        ncol=legend_ncol,
        columnspacing=1.2,
        handlelength=2.0,
    )

    fig.tight_layout(rect=[0, 0, 1, layout_top])

    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths = []
    for file_format in formats:
        suffix = file_format.lower().lstrip(".")
        save_path = output_dir / f"{filename_stem}.{suffix}"
        _savefig_fixed_pdf_width(fig, save_path, dpi=JOURNAL_DPI)
        written_paths.append(save_path)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return written_paths


def plot_size_variants(
    output_dir: Path,
    filename_stem: str,
    formats: Iterable[str],
    size_scales: Iterable[float],
    show: bool = False,
    label_bars: bool = False,
) -> list[Path]:
    written_paths = []
    for scale in size_scales:
        scale_float = float(scale)
        scale_tag = f"s{int(round(scale_float * 100))}"
        figsize = (
            JOURNAL_FIGSIZE[0] * scale_float,
            JOURNAL_FIGSIZE[1] * scale_float,
        )
        if scale_float >= 0.8:
            legend_ncol = 3
            layout_top = 0.82
        elif scale_float >= 0.7:
            legend_ncol = 2
            layout_top = 0.74
        else:
            legend_ncol = 2
            layout_top = 0.68
        efficiency_tick_step = 1.0
        share_tick_step = 10.0
        written_paths.extend(
            plot_hp_efficiency(
                output_dir=output_dir,
                filename_stem=f"{filename_stem}_{scale_tag}",
                formats=formats,
                figsize=figsize,
                show=show,
                label_bars=label_bars,
                legend_ncol=legend_ncol,
                layout_top=layout_top,
                efficiency_tick_step=efficiency_tick_step,
                share_tick_step=share_tick_step,
            )
        )
    return written_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot heating-system efficiency and annual work shares."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for exported figure files.",
    )
    parser.add_argument(
        "--filename-stem",
        default="hp_efficiency_by_external_temperature",
        help="Filename without extension.",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["pdf", "png"],
        help="Output formats, e.g. pdf png svg.",
    )
    parser.add_argument("--show", action="store_true", help="Open an interactive plot window.")
    parser.add_argument(
        "--bar-labels",
        action="store_true",
        help="Show percentage labels inside the annual-work bars.",
    )
    parser.add_argument(
        "--size-scales",
        nargs="+",
        type=float,
        default=list(DEFAULT_SIZE_SCALES),
        help="Figure size scales relative to JOURNAL_FIGSIZE, e.g. 0.8 0.7 0.6.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_paths = plot_size_variants(
        output_dir=args.output_dir,
        filename_stem=args.filename_stem,
        formats=args.formats,
        size_scales=args.size_scales,
        show=args.show,
        label_bars=args.bar_labels,
    )

    print("Weighted annual efficiencies:")
    for label, value in _weighted_efficiencies().items():
        print(f"  {label}: {value:.2f}")
    print("Written files:")
    for path in output_paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
