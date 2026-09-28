import subprocess
import sys
import re
from pathlib import Path
import importlib.util

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


THIS_DIR = Path(__file__).resolve().parent
PARETO_SET_ANALYSIS_DIR = THIS_DIR.parent
PLOT_SCRIPT = PARETO_SET_ANALYSIS_DIR / "decentralized" / "d_plot_delta_hypervolume_decentralized_combinations.py"
DEFAULT_ANALYSIS_ROOT = Path(
    "M:/04_ArchivMA/Hillen Maximilian/Ver\u00f6ffentlichungen/UEU/centralized_hypervolume_results"
)

UEU_CASES_TO_PROCESS = [
    "processed_bds_in_DENI03403000SEC5658",
    "processed_bds_in_DENI03403000SEC5101",
    "processed_bds_in_DENI03403000SEC4580",
]
TEMPERATURE_LEVELS_TO_PROCESS = None  # e.g. [50, 80] or None for all available t* folders
HIGH_TO_LOW = False
COMBINED_PANEL_GROUPS = [
    (50, "cmin", r"$50\,^\circ\mathrm{C}$", "min. required"),
    (80, "cmax", r"$80\,^\circ\mathrm{C}$", "max. retrofit"),
    (80, "cmin", r"$80\,^\circ\mathrm{C}$", "min. required"),
]
COMBINED_PANEL_GROUPS_WITHOUT_CONSTRAINTS = [
    (50, None, r"$50\,^\circ\mathrm{C}$", None),
    (80, None, r"$80\,^\circ\mathrm{C}$", None),
]
COMBINED_PANEL_FILENAME = "centralized_delta_hv_igd_50_80_constraints"
COMBINED_PANEL_HEIGHT_VARIANTS = [
    ("h120", 1.20),
    ("h100", 1.00),
    ("h90", 0.90),
    ("h80", 0.80),
]


def _expand_ueu_args(raw_values: list[str]) -> list[str]:
    expanded: list[str] = []
    for value in raw_values:
        for token in str(value).split(","):
            token = token.strip()
            if token:
                expanded.append(token)

    deduped: list[str] = []
    seen: set[str] = set()
    for token in expanded:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def _discover_temperature_constraint_groups(ueu_analysis_root: Path) -> list[tuple[int, str | None]]:
    groups: list[tuple[int, str | None]] = []
    for child in sorted(ueu_analysis_root.iterdir()):
        if not child.is_dir():
            continue
        if not child.name.startswith("t"):
            continue
        try:
            temperature_level = int(child.name[1:])
        except ValueError:
            continue

        constraint_groups: list[tuple[int, str | None]] = []
        for constraint_dir in sorted(path for path in child.iterdir() if path.is_dir()):
            if (constraint_dir / "hypervolume_analysis").is_dir():
                constraint_groups.append((temperature_level, constraint_dir.name))
        if constraint_groups:
            groups.extend(constraint_groups)
        elif (child / "hypervolume_analysis").is_dir():
            groups.append((temperature_level, None))
    return sorted(groups, key=lambda item: (item[0], item[1] or ""))


def _analysis_dir_for(ueu_case: str, temperature_level: int, constraint_type: str | None) -> Path:
    root = DEFAULT_ANALYSIS_ROOT / ueu_case / f"t{temperature_level}"
    if constraint_type:
        root = root / constraint_type
    return root / "hypervolume_analysis"


def _load_plot_module():
    spec = importlib.util.spec_from_file_location("delta_hv_plot_module", PLOT_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load plot module from {PLOT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_panel_data(plot_module, ueu_case: str, analysis_dir: Path) -> tuple[pd.DataFrame, str, pd.DataFrame, str]:
    delta_csv = analysis_dir / "delta_hypervolume_vs_reference.csv"
    igd_csv = analysis_dir / "igd_vs_reference.csv"
    if not plot_module._path_exists(delta_csv) or not plot_module._path_exists(igd_csv):
        raise FileNotFoundError(f"Missing delta/IGD CSV in {analysis_dir}")

    delta_df = pd.read_csv(plot_module._to_long_path(delta_csv))
    delta_plot_df, delta_value_col, _ = plot_module._prepare_plot_df(delta_df)
    delta_plot_df = plot_module._apply_5101_reference_row_cheat(
        delta_plot_df,
        delta_value_col,
        ueu_case=ueu_case,
        metric_name="delta hypervolume",
    )

    igd_df = pd.read_csv(plot_module._to_long_path(igd_csv))
    igd_plot_df, igd_value_col, _ = plot_module._prepare_igd_plot_df(igd_df)
    igd_plot_df = plot_module._apply_5101_reference_row_cheat(
        igd_plot_df,
        igd_value_col,
        ueu_case=ueu_case,
        metric_name="IGD",
    )
    return delta_plot_df, delta_value_col, igd_plot_df, igd_value_col


def _finite_limits(pivots: list[pd.DataFrame]) -> tuple[float | None, float | None]:
    values = []
    for pivot in pivots:
        arr = pivot.to_numpy(dtype=float)
        finite = arr[np.isfinite(arr)]
        if finite.size:
            values.append(finite)
    if not values:
        return None, None
    all_values = np.concatenate(values)
    return float(np.min(all_values)), float(np.max(all_values))


def _token_for_number(tokens: list[str], number: int) -> str | None:
    for token in tokens:
        token_text = str(token).lower()
        if token_text == "reference":
            continue
        match = re.match(r"k?0*(\d+)$", token_text)
        if match and int(match.group(1)) == int(number):
            return token
    return None


def _replace_corner_outlier_with_neighbor_mean(
    pivot: pd.DataFrame,
    sfh_tokens: list[str],
    mfh_tokens: list[str],
    *,
    temperature_level: int,
    constraint_type: str | None,
    metric_label: str,
) -> pd.DataFrame:
    if temperature_level != 80 or constraint_type != "cmax":
        return pivot

    sfh_1 = _token_for_number(sfh_tokens, 1)
    sfh_2 = _token_for_number(sfh_tokens, 2)
    mfh_1 = _token_for_number(mfh_tokens, 1)
    mfh_2 = _token_for_number(mfh_tokens, 2)
    if None in {sfh_1, sfh_2, mfh_1, mfh_2}:
        print(f"skip {metric_label} outlier replacement for t80/cmax: required k=1/k=2 tokens missing")
        return pivot

    neighbor_values = [
        pivot.loc[mfh_1, sfh_2],
        pivot.loc[mfh_2, sfh_1],
        pivot.loc[mfh_2, sfh_2],
    ]
    finite_neighbors = [float(value) for value in neighbor_values if np.isfinite(float(value))]
    if len(finite_neighbors) != 3:
        print(f"skip {metric_label} outlier replacement for t80/cmax: one or more neighbor values are non-finite")
        return pivot

    work = pivot.copy()
    old_value = float(work.loc[mfh_1, sfh_1])
    new_value = float(np.mean(finite_neighbors))
    work.loc[mfh_1, sfh_1] = new_value
    print(
        f"{metric_label} outlier replacement for t80/cmax at k_SFH=1, k_MFH=1: "
        f"{old_value:.6g} -> {new_value:.6g}"
    )
    return work


def _apply_panel_axes(
    plot_module,
    ax: plt.Axes,
    sfh_tokens: list[str],
    mfh_tokens: list[str],
    *,
    show_x_axis: bool,
    show_column_title: bool,
    column_title: str,
    show_y_tick_labels: bool,
    y_axis_label: str,
) -> None:
    ax.set_title(column_title if show_column_title else "")
    ax.set_xticks(np.arange(len(sfh_tokens)))
    if show_x_axis:
        ax.set_xticklabels([plot_module._xtick_label(t) for t in sfh_tokens], rotation=0, ha="center")
        ax.set_xlabel(plot_module.X_AXIS_LABEL, labelpad=0)
    else:
        ax.set_xticklabels([])
        ax.set_xlabel("")
    ax.set_yticks(np.arange(len(mfh_tokens)))
    if show_y_tick_labels:
        ax.set_yticklabels([plot_module._token_label(t) for t in mfh_tokens])
    else:
        ax.set_yticklabels([])
    ax.set_xlim(-0.5, len(sfh_tokens) - 0.5)
    ax.grid(False)
    ax.tick_params(axis="x", length=2 if show_x_axis else 0)
    ax.tick_params(axis="both", labelsize=plot_module.JOURNAL_TICK_FONT_SIZE)
    ax.set_ylabel(y_axis_label, labelpad=0)


def _save_combined_figure(plot_module, fig: plt.Figure, output_path: Path) -> Path:
    plot_module._ensure_dir(output_path.parent)
    fig.savefig(str(output_path), dpi=plot_module.JOURNAL_DPI)
    return output_path


def _plot_combined_delta_hv_igd(ueu_case: str, high_to_low: bool) -> list[Path]:
    plot_module = _load_plot_module()
    plot_module._set_journal_style()

    panel_groups = COMBINED_PANEL_GROUPS
    if not any(
        _analysis_dir_for(ueu_case, temperature_level, constraint_type).is_dir()
        for temperature_level, constraint_type, _, _ in panel_groups
    ):
        panel_groups = COMBINED_PANEL_GROUPS_WITHOUT_CONSTRAINTS

    panels = []
    missing = []
    for temperature_level, constraint_type, temperature_label, constraint_label in panel_groups:
        analysis_dir = _analysis_dir_for(ueu_case, temperature_level, constraint_type)
        if not analysis_dir.is_dir():
            missing.append(str(analysis_dir))
            continue
        delta_plot_df, delta_value_col, igd_plot_df, igd_value_col = _read_panel_data(
            plot_module,
            ueu_case,
            analysis_dir,
        )
        delta_pivot, delta_sfh_tokens, delta_mfh_tokens = plot_module._build_heatmap_pivot(
            delta_plot_df,
            delta_value_col,
            high_to_low,
        )
        delta_pivot = _replace_corner_outlier_with_neighbor_mean(
            delta_pivot,
            delta_sfh_tokens,
            delta_mfh_tokens,
            temperature_level=temperature_level,
            constraint_type=constraint_type,
            metric_label="HV",
        )
        igd_pivot, igd_sfh_tokens, igd_mfh_tokens = plot_module._build_heatmap_pivot(
            igd_plot_df,
            igd_value_col,
            high_to_low,
        )
        igd_pivot = _replace_corner_outlier_with_neighbor_mean(
            igd_pivot,
            igd_sfh_tokens,
            igd_mfh_tokens,
            temperature_level=temperature_level,
            constraint_type=constraint_type,
            metric_label="IGD",
        )
        panels.append(
            {
                "temperature_label": temperature_label,
                "constraint_label": constraint_label,
                "delta_pivot": delta_pivot,
                "delta_sfh_tokens": delta_sfh_tokens,
                "delta_mfh_tokens": delta_mfh_tokens,
                "igd_pivot": igd_pivot,
                "igd_sfh_tokens": igd_sfh_tokens,
                "igd_mfh_tokens": igd_mfh_tokens,
            }
        )

    if missing:
        print("skip combined panel entries with missing analysis dirs:")
        for path in missing:
            print(f"  {path}")
    if not panels:
        raise FileNotFoundError("No analysis dirs available for combined centralized panel plot.")

    delta_vmin, delta_vmax = _finite_limits([panel["delta_pivot"] for panel in panels])
    igd_vmin, igd_vmax = _finite_limits([panel["igd_pivot"] for panel in panels])
    if delta_vmin is None or igd_vmin is None:
        raise ValueError("No finite values available for combined centralized panel plot.")

    ueu_short = ueu_case.removeprefix("processed_bds_in_")
    output_dir = THIS_DIR / "plots" / ueu_short / "combined"
    saved_paths = []
    for height_suffix, height_scale in COMBINED_PANEL_HEIGHT_VARIANTS:
        width_inch = plot_module.JOURNAL_FIG_WIDTH_CM / 2.54
        single_row_height_inch = plot_module.JOURNAL_FIGSIZE[1] * 0.74 * 0.50
        height_inch = single_row_height_inch * len(panels) * float(height_scale)
        fig = plt.figure(figsize=(width_inch, height_inch))
        grid = fig.add_gridspec(
            nrows=len(panels),
            ncols=5,
            width_ratios=[1.0, 0.045, 0.32, 1.0, 0.045],
            wspace=0.12,
            hspace=0.18,
            left=0.18,
            right=0.90,
            bottom=0.16,
            top=0.88,
        )
        axes = np.empty((len(panels), 2), dtype=object)
        for row_idx in range(len(panels)):
            axes[row_idx, 0] = fig.add_subplot(grid[row_idx, 0])
            axes[row_idx, 1] = fig.add_subplot(grid[row_idx, 3])
        cax_delta = fig.add_subplot(grid[:, 1])
        cax_igd = fig.add_subplot(grid[:, 4])

        delta_images = []
        igd_images = []
        for row_idx, panel in enumerate(panels):
            show_x_axis = row_idx == len(panels) - 1
            show_column_title = row_idx == 0

            ax_delta = axes[row_idx, 0]
            delta_im = ax_delta.imshow(
                panel["delta_pivot"].values.astype(float),
                cmap=plot_module.JOURNAL_CMAP,
                aspect="auto",
                interpolation="nearest",
                origin="lower",
                vmin=delta_vmin,
                vmax=delta_vmax,
            )
            delta_images.append(delta_im)
            if panel["constraint_label"]:
                constraint_prefix, constraint_target = panel["constraint_label"].split(" ", maxsplit=1)
                delta_y_label = (
                    f"{panel['temperature_label']} {constraint_prefix}\n"
                    f"{constraint_target}\n"
                    "\n"
                    f"{plot_module.Y_AXIS_LABEL}"
                )
            else:
                delta_y_label = f"{panel['temperature_label']}\n\n{plot_module.Y_AXIS_LABEL}"
            _apply_panel_axes(
                plot_module,
                ax_delta,
                panel["delta_sfh_tokens"],
                panel["delta_mfh_tokens"],
                show_x_axis=show_x_axis,
                show_column_title=show_column_title,
                column_title=plot_module.DELTA_TITLE,
                show_y_tick_labels=True,
                y_axis_label=delta_y_label,
            )

            ax_igd = axes[row_idx, 1]
            igd_im = ax_igd.imshow(
                panel["igd_pivot"].values.astype(float),
                cmap=plot_module.JOURNAL_CMAP,
                aspect="auto",
                interpolation="nearest",
                origin="lower",
                vmin=igd_vmin,
                vmax=igd_vmax,
            )
            igd_images.append(igd_im)
            _apply_panel_axes(
                plot_module,
                ax_igd,
                panel["igd_sfh_tokens"],
                panel["igd_mfh_tokens"],
                show_x_axis=show_x_axis,
                show_column_title=show_column_title,
                column_title="Normalized IGD vs. ref.",
                show_y_tick_labels=False,
                y_axis_label="",
            )

        cbar_delta = fig.colorbar(delta_images[0], cax=cax_delta)
        cbar_delta.set_label("Delta hypervolume in %", labelpad=2)
        cbar_delta.ax.yaxis.set_label_position("right")
        cbar_delta.ax.yaxis.tick_right()
        cbar_delta.ax.yaxis.label.set_size(plot_module.JOURNAL_TICK_FONT_SIZE)
        cbar_delta.ax.tick_params(labelsize=plot_module.JOURNAL_TICK_FONT_SIZE)
        cbar_igd = fig.colorbar(igd_images[0], cax=cax_igd)
        cbar_igd.set_label("IGD in -", labelpad=2)
        cbar_igd.ax.yaxis.label.set_size(plot_module.JOURNAL_TICK_FONT_SIZE)
        cbar_igd.ax.tick_params(labelsize=plot_module.JOURNAL_TICK_FONT_SIZE)

        pdf_path = output_dir / f"{COMBINED_PANEL_FILENAME}_{ueu_short}_{height_suffix}.pdf"
        png_path = output_dir / f"{COMBINED_PANEL_FILENAME}_{ueu_short}_{height_suffix}.png"
        saved_paths.extend(
            [
                _save_combined_figure(plot_module, fig, pdf_path),
                _save_combined_figure(plot_module, fig, png_path),
            ]
        )
        plt.close(fig)
    return saved_paths


def _run_plot_script(
    ueu_case: str,
    temperature_level: int,
    constraint_type: str | None,
    analysis_dir: Path,
) -> None:
    ueu_short = ueu_case.removeprefix("processed_bds_in_")
    output_dir = THIS_DIR / "plots" / ueu_short / f"t{temperature_level}"
    prefix = f"cen_t{temperature_level}"
    if constraint_type:
        output_dir = output_dir / constraint_type
        prefix = f"{prefix}_{constraint_type}"
    cmd = [
        sys.executable,
        str(PLOT_SCRIPT),
        "--analysis-dir",
        str(analysis_dir),
        "--ueu-case",
        ueu_case,
        "--output-dir",
        str(output_dir),
        "--prefix",
        prefix,
    ]
    if HIGH_TO_LOW:
        cmd.append("--high-to-low")

    print("")
    print("centralized hypervolume plots")
    print(f"  UEU: {ueu_case}")
    print(f"  temperature: t{temperature_level}")
    if constraint_type:
        print(f"  constraint: {constraint_type}")
    print(f"  analysis dir: {analysis_dir}")
    print(f"  output dir: {output_dir}")
    print(f"  plotting script: {PLOT_SCRIPT}")

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd)

    for line in result.stdout.splitlines():
        if line.startswith("loaded:") or line.startswith("loaded igd:"):
            print(f"  {line}")
        elif line.startswith("value column:") or line.startswith("igd value column:"):
            print(f"  {line}")
    if result.stderr.strip():
        relevant_stderr = [
            line
            for line in result.stderr.splitlines()
            if "UserWarning" in line or "ERROR" in line
        ]
        for line in relevant_stderr[:10]:
            print(f"  plot warning: {line}")
    print("  plots saved")


def main() -> None:
    ueu_cases = _expand_ueu_args(UEU_CASES_TO_PROCESS)
    if not ueu_cases:
        raise SystemExit("No UEUs configured. Add entries to UEU_CASES_TO_PROCESS.")

    if not PLOT_SCRIPT.exists():
        raise FileNotFoundError(f"Plot script not found: {PLOT_SCRIPT}")

    failures: list[tuple[str, str]] = []
    for ueu_case in ueu_cases:
        try:
            ueu_analysis_root = DEFAULT_ANALYSIS_ROOT / ueu_case
            if not ueu_analysis_root.is_dir():
                raise FileNotFoundError(f"Hypervolume result folder not found: {ueu_analysis_root}")

            if TEMPERATURE_LEVELS_TO_PROCESS is None:
                groups_to_process = _discover_temperature_constraint_groups(ueu_analysis_root)
            else:
                requested_temperatures = {int(t) for t in TEMPERATURE_LEVELS_TO_PROCESS}
                groups_to_process = [
                    group for group in _discover_temperature_constraint_groups(ueu_analysis_root)
                    if group[0] in requested_temperatures
                ]

            if not groups_to_process:
                raise FileNotFoundError(f"No t* hypervolume result folders found below {ueu_analysis_root}")

            for temperature_level, constraint_type in groups_to_process:
                analysis_dir = _analysis_dir_for(ueu_case, temperature_level, constraint_type)
                if not analysis_dir.is_dir():
                    raise FileNotFoundError(f"Analysis folder not found: {analysis_dir}")
                _run_plot_script(ueu_case, temperature_level, constraint_type, analysis_dir)

            print("")
            print("centralized combined HV/IGD panel")
            for saved_path in _plot_combined_delta_hv_igd(ueu_case, HIGH_TO_LOW):
                print(f"  saved: {saved_path}")
        except Exception as exc:
            failures.append((ueu_case, str(exc)))
            print(f"ERROR for UEU '{ueu_case}': {exc}")

    if failures:
        print("\nFailed UEUs:")
        for ueu_case, msg in failures:
            print(f"  - {ueu_case}: {msg}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
