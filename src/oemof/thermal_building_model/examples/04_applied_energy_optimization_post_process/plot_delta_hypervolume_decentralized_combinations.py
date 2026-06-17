import argparse
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


DEFAULT_UEU_CASE = "processed_bds_in_DENI03403000SEC5658"
POST_PROCESS_ROOT_PATTERN = "post_processed_dec_k_combinations_*"
DEFAULT_DELTA_CSV_CANDIDATES = [
    "delta_hypervolume_vs_reference.csv",
    "delta_hv_vs_ref.csv",
]
DEFAULT_IGD_CSV_CANDIDATES = [
    "igd_vs_reference.csv",
    "igd_vs_ref.csv",
]
JOURNAL_FONT_FAMILY = "TeX Gyre Termes"
JOURNAL_FONT_SIZE = 9
JOURNAL_FIGSIZE = (6, 4)
JOURNAL_DPI = 600
JOURNAL_CMAP = "viridis"


def _set_journal_style(font_family: str = JOURNAL_FONT_FAMILY, font_size: int = JOURNAL_FONT_SIZE) -> None:
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


def _parse_date_suffix(folder_name: str) -> Tuple[int, int, int] | None:
    match = re.search(r"(\d{4})_(\d{2})_(\d{2})$", folder_name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _to_long_path(path: Path) -> str:
    resolved = path.resolve()
    path_str = str(resolved)
    if os.name == "nt":
        if path_str.startswith("\\\\?\\"):
            return path_str
        if path_str.startswith("\\\\"):
            return "\\\\?\\UNC\\" + path_str[2:]
        return "\\\\?\\" + path_str
    return path_str


def _path_exists(path: Path) -> bool:
    try:
        if path.exists():
            return True
    except OSError:
        pass
    try:
        return os.path.exists(_to_long_path(path))
    except OSError:
        return False


def _is_reference_token(token: str) -> bool:
    return str(token).lower() == "reference"


def _token_sort_value(token: str) -> int:
    token = str(token)
    if _is_reference_token(token):
        return 10**9
    return int(token[1:])


def _token_label(token: str) -> str:
    token = str(token)
    if _is_reference_token(token):
        return "reference"
    return str(int(token[1:]))


def _discover_latest_post_process_root(base_dir: Path, ueu_case: str) -> Path:
    cluster_root = Path(str(ueu_case)) if Path(str(ueu_case)).is_absolute() else (base_dir / ueu_case)
    if not cluster_root.exists():
        raise FileNotFoundError(f"UEU folder not found: {cluster_root}")

    candidates = [p for p in sorted(cluster_root.glob(POST_PROCESS_ROOT_PATTERN)) if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No post-process folders found below: {cluster_root}")

    dated = [p for p in candidates if _parse_date_suffix(p.name) is not None]
    if dated:
        candidates = sorted(dated, key=lambda p: _parse_date_suffix(p.name))
    return candidates[-1]


def _resolve_metric_csv(
    explicit_csv: str | None,
    analysis_dir: str | None,
    post_process_root: str | None,
    base_dir: str,
    ueu_case: str,
    candidate_files: List[str],
    metric_label: str,
) -> Path:
    if explicit_csv:
        out = Path(explicit_csv)
        if not _path_exists(out):
            raise FileNotFoundError(f"{metric_label} csv not found: {out}")
        return out

    def _find_in_dir(root: Path) -> Path | None:
        for name in candidate_files:
            p = root / name
            if _path_exists(p):
                return p
        return None

    if analysis_dir:
        analysis_root = Path(analysis_dir)
        found = _find_in_dir(analysis_root)
        if found is not None:
            return found
        raise FileNotFoundError(
            f"No supported {metric_label} CSV found in: {analysis_root}. "
            f"Tried: {', '.join(candidate_files)}"
        )

    if post_process_root:
        post_root = Path(post_process_root)
    else:
        post_root = _discover_latest_post_process_root(Path(base_dir), ueu_case)

    legacy_analysis_root = post_root / "hypervolume_analysis"
    found = _find_in_dir(legacy_analysis_root)
    if found is not None:
        return found

    ueu_folder_name = post_root.parent.name
    modern_analysis_root = (
        Path(__file__).resolve().parents[1]
        / "05_applied_energy_pareto_set_analysis"
        / "hypervolume_results"
        / ueu_folder_name
        / post_root.name
    )
    found = _find_in_dir(modern_analysis_root)
    if found is not None:
        return found

    raise FileNotFoundError(
        f"{metric_label} csv not found in expected locations. "
        f"Tried file names: {', '.join(candidate_files)}"
    )


def _resolve_delta_csv(
    delta_csv: str | None,
    analysis_dir: str | None,
    post_process_root: str | None,
    base_dir: str,
    ueu_case: str,
) -> Path:
    return _resolve_metric_csv(
        explicit_csv=delta_csv,
        analysis_dir=analysis_dir,
        post_process_root=post_process_root,
        base_dir=base_dir,
        ueu_case=ueu_case,
        candidate_files=list(DEFAULT_DELTA_CSV_CANDIDATES),
        metric_label="delta",
    )


def _resolve_igd_csv(
    igd_csv: str | None,
    analysis_dir: str | None,
    post_process_root: str | None,
    base_dir: str,
    ueu_case: str,
) -> Path:
    return _resolve_metric_csv(
        explicit_csv=igd_csv,
        analysis_dir=analysis_dir,
        post_process_root=post_process_root,
        base_dir=base_dir,
        ueu_case=ueu_case,
        candidate_files=list(DEFAULT_IGD_CSV_CANDIDATES),
        metric_label="igd",
    )


def _prepare_plot_df(df: pd.DataFrame, metric: str) -> Tuple[pd.DataFrame, str]:
    if "sfh_k_token" not in df.columns or "mfh_k_token" not in df.columns:
        raise ValueError("CSV must contain 'sfh_k_token' and 'mfh_k_token'.")

    if metric == "delta":
        if "delta_hv_vs_ref_rel_pct" in df.columns:
            value_col = "delta_hv_vs_ref_rel_pct"
        elif "delta_hv_vs_ref" in df.columns:
            value_col = "delta_hv_vs_ref"
        else:
            raise ValueError(
                "Delta CSV must contain one of: delta_hv_vs_ref or delta_hv_vs_ref_rel_pct."
            )
    elif metric == "igd":
        if "igd_vs_ref" in df.columns:
            value_col = "igd_vs_ref"
        elif "igd_vs_ref_normalized" in df.columns:
            value_col = "igd_vs_ref_normalized"
        else:
            raise ValueError("IGD CSV must contain 'igd_vs_ref' or 'igd_vs_ref_normalized'.")
    else:
        raise ValueError(f"Unsupported metric: {metric}")

    work = df.copy()
    work = work[pd.notna(work[value_col])].copy()
    if work.empty:
        raise ValueError("No finite values to plot.")

    work["sfh_k_token"] = work["sfh_k_token"].astype(str)
    work["mfh_k_token"] = work["mfh_k_token"].astype(str)
    return work, value_col


def _plot_3d(
    plot_df: pd.DataFrame,
    value_col: str,
    output_png: Path,
    high_to_low: bool,
    y_label: str,
    title: str,
    cbar_label: str,
) -> None:
    _set_journal_style()
    sfh_tokens = sorted(plot_df["sfh_k_token"].unique(), key=_token_sort_value)
    mfh_tokens = sorted(plot_df["mfh_k_token"].unique(), key=_token_sort_value)
    sfh_pos: Dict[str, int] = {token: idx for idx, token in enumerate(sfh_tokens)}
    mfh_pos: Dict[str, int] = {token: idx for idx, token in enumerate(mfh_tokens)}

    x = plot_df["sfh_k_token"].map(sfh_pos).to_numpy(dtype=float)
    y = plot_df[value_col].to_numpy(dtype=float)
    z = plot_df["mfh_k_token"].map(mfh_pos).to_numpy(dtype=float)
    c = y

    fig = plt.figure(figsize=JOURNAL_FIGSIZE)
    ax = fig.add_subplot(111, projection="3d")
    scatter = ax.scatter(x, y, z, c=c, cmap=JOURNAL_CMAP, s=28, alpha=0.95, linewidths=0.0)

    ax.set_xlabel("SFH k")
    ax.set_ylabel(y_label)
    ax.set_zlabel("MFH k")
    ax.set_title(title)
    ax.grid(True, alpha=0.3, linewidth=0.6)

    ax.set_xticks(list(sfh_pos.values()))
    ax.set_xticklabels([_token_label(t) for t in sfh_tokens])
    ax.set_zticks(list(mfh_pos.values()))
    ax.set_zticklabels([_token_label(t) for t in mfh_tokens])

    if high_to_low:
        ax.set_xlim(max(sfh_pos.values()), min(sfh_pos.values()))
        ax.set_zlim(max(mfh_pos.values()), min(mfh_pos.values()))
    else:
        ax.set_xlim(min(sfh_pos.values()), max(sfh_pos.values()))
        ax.set_zlim(min(mfh_pos.values()), max(mfh_pos.values()))

    cbar = fig.colorbar(scatter, ax=ax, pad=0.15, shrink=0.75)
    cbar.set_label(cbar_label)
    cbar.ax.tick_params(labelsize=JOURNAL_FONT_SIZE)
    fig.tight_layout()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(_to_long_path(output_png), dpi=JOURNAL_DPI, bbox_inches="tight")
    plt.close(fig)


def _plot_heatmap(
    plot_df: pd.DataFrame,
    value_col: str,
    output_png: Path,
    high_to_low: bool,
    title: str,
    cbar_label: str,
) -> None:
    _set_journal_style()
    sfh_tokens = sorted(plot_df["sfh_k_token"].unique(), key=_token_sort_value)
    mfh_tokens = sorted(plot_df["mfh_k_token"].unique(), key=_token_sort_value)

    if high_to_low:
        sfh_tokens = list(reversed(sfh_tokens))
        mfh_tokens = list(reversed(mfh_tokens))

    pivot = plot_df.pivot_table(index="mfh_k_token", columns="sfh_k_token", values=value_col, aggfunc="mean")
    pivot = pivot.reindex(index=mfh_tokens, columns=sfh_tokens)

    fig, ax = plt.subplots(figsize=JOURNAL_FIGSIZE)
    im = ax.imshow(pivot.values.astype(float), cmap=JOURNAL_CMAP, aspect="auto")
    ax.set_xlabel("SFH k")
    ax.set_ylabel("MFH k")
    ax.set_title(title)
    ax.set_xticks(np.arange(len(sfh_tokens)))
    ax.set_xticklabels([_token_label(t) for t in sfh_tokens], rotation=45, ha="right")
    ax.set_yticks(np.arange(len(mfh_tokens)))
    ax.set_yticklabels([_token_label(t) for t in mfh_tokens])
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(cbar_label)
    cbar.ax.tick_params(labelsize=JOURNAL_FONT_SIZE)
    ax.grid(False)
    fig.tight_layout()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(_to_long_path(output_png), dpi=JOURNAL_DPI, bbox_inches="tight")
    plt.close(fig)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load delta hypervolume CSV and create 3D + heatmap plots."
    )
    parser.add_argument(
        "--delta-csv",
        type=str,
        default=None,
        help="Full path to delta CSV (e.g. delta_hypervolume_vs_reference.csv).",
    )
    parser.add_argument(
        "--igd-csv",
        type=str,
        default=None,
        help="Full path to IGD CSV (e.g. igd_vs_reference.csv).",
    )
    parser.add_argument(
        "--analysis-dir",
        type=str,
        default=None,
        help="Directory containing delta_hypervolume_from_origin_grid.csv.",
    )
    parser.add_argument(
        "--post-process-root",
        type=str,
        default=None,
        help="Path to post_processed_dec_k_combinations_YYYY_MM_DD folder.",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=str(Path(__file__).resolve().parent),
        help="Base directory containing UEU folders.",
    )
    parser.add_argument(
        "--ueu-case",
        type=str,
        default=DEFAULT_UEU_CASE,
        help="UEU folder name (used when no explicit CSV/path is provided).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output folder for plots. Default: CSV parent folder.",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="delta_hypervolume",
        help="Prefix for output plot filenames.",
    )
    parser.add_argument(
        "--low-to-high",
        action="store_true",
        help="Use low->high order on SFH/MFH axes (default is high->low).",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()

    delta_csv_path = _resolve_delta_csv(
        delta_csv=args.delta_csv,
        analysis_dir=args.analysis_dir,
        post_process_root=args.post_process_root,
        base_dir=args.base_dir,
        ueu_case=args.ueu_case,
    )
    delta_df = pd.read_csv(_to_long_path(delta_csv_path))
    delta_plot_df, delta_value_col = _prepare_plot_df(delta_df, metric="delta")

    output_dir = Path(args.output_dir) if args.output_dir else delta_csv_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    high_to_low = not bool(args.low_to_high)

    out_3d = output_dir / f"{args.prefix}_3d_sfh_x_mfh_z.png"
    out_heatmap = output_dir / f"{args.prefix}_heatmap.png"

    delta_label = "Delta hypervolume"
    _plot_3d(
        delta_plot_df,
        delta_value_col,
        out_3d,
        high_to_low=high_to_low,
        y_label=delta_label,
        title=f"{delta_label} over SFH/MFH combinations",
        cbar_label=delta_label,
    )
    _plot_heatmap(
        delta_plot_df,
        delta_value_col,
        out_heatmap,
        high_to_low=high_to_low,
        title=f"{delta_label} heatmap",
        cbar_label=delta_label,
    )

    print(f"loaded delta: {delta_csv_path}")
    print(f"delta value column: {delta_value_col}")
    print(f"saved: {out_3d}")
    print(f"saved: {out_heatmap}")

    try:
        igd_csv_path = _resolve_igd_csv(
            igd_csv=args.igd_csv,
            analysis_dir=args.analysis_dir,
            post_process_root=args.post_process_root,
            base_dir=args.base_dir,
            ueu_case=args.ueu_case,
        )
        igd_df = pd.read_csv(_to_long_path(igd_csv_path))
        igd_plot_df, igd_value_col = _prepare_plot_df(igd_df, metric="igd", use_abs=False)
        out_igd = output_dir / f"{args.prefix}_igd_vs_reference_heatmap.png"
        _plot_heatmap(
            igd_plot_df,
            igd_value_col,
            out_igd,
            high_to_low=high_to_low,
            title="IGD vs reference heatmap",
            cbar_label="IGD vs reference",
        )
        print(f"loaded igd: {igd_csv_path}")
        print(f"igd value column: {igd_value_col}")
        print(f"saved: {out_igd}")
    except FileNotFoundError as exc:
        print(f"skip igd plot: {exc}")


if __name__ == "__main__":
    main()
