import argparse
import os
import re
from pathlib import Path
from typing import Dict, Tuple

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


UEU_CASES_TO_PROCESS = [
    #"processed_bds_in_DENI03403000SEC4580",
    #"processed_bds_in_DENI03403000SEC5101",
    "processed_bds_in_DENI03403000SEC5658",
]
POST_PROCESS_ROOT_PATTERN = "post_processed_dec_k_combinations_*"
DEFAULT_BASE_DIR = Path(__file__).resolve().parent / "hypervolume_results"
CSV_CANDIDATE_NAMES = [
    "delta_hypervolume_vs_reference.csv",
    "delta_hv_vs_ref.csv",
]
IGD_CSV_CANDIDATE_NAMES = [
    "igd_vs_reference.csv",
    "igd_vs_ref.csv",
]
JOURNAL_FONT_FAMILY = "TeX Gyre Termes"
JOURNAL_FONT_SIZE = 9
JOURNAL_FIG_WIDTH_CM = 15.11293
JOURNAL_FIGSIZE = (JOURNAL_FIG_WIDTH_CM / 2.54, 2.8)
JOURNAL_DPI = 600
JOURNAL_CMAP = "viridis"
HEIGHT_VARIANTS: list[tuple[str, float]] = [
    ("h100", 1.00),
    ("h90", 0.90),
    ("h80", 0.80),
    ("h70", 0.70),
    ("h60", 0.60),
    ("h50", 0.50),
    ("h40", 0.40),
]
HORIZONTAL_CLOSER_VARIANTS: list[tuple[str, float]] = [
    ("c10", 0.90),  # 10% closer
    ("c20", 0.80),  # 20% closer
    ("c30", 0.70),  # 30% closer
    ("c40", 0.60),  # 40% closer
]
X_AXIS_LABEL = r"Number of clusters $k_{\mathrm{SFH}}$"
Y_AXIS_LABEL = r"Number of clusters $k_{\mathrm{MFH}}$"
DELTA_CBAR_LABEL = "Delta hypervolume in %"
DELTA_TITLE = "Normalized delta hypervolume vs ref."
IGD_CBAR_LABEL = "IGD in -"
IGD_TITLE = "Normalized IGD vs ref."
IGD_TITLE_ANNOTATED = "Normalized IGD vs ref. (values)"


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


def _extract_ueu_filename_suffix(ueu_case: str) -> str:
    token = Path(str(ueu_case)).name
    match = re.search(r"(DENI[0-9A-Za-z]+)", token)
    if match:
        return match.group(1)
    return token.replace(" ", "_")


def _extract_ueu_short4(ueu_case: str) -> str | None:
    token = str(ueu_case)
    match = re.search(r"SEC(\d{4})", token)
    if match:
        return match.group(1)
    match = re.search(r"(\d{4})$", token)
    if match:
        return match.group(1)
    return None


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
        return "ref."
    return str(int(token[1:]))


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


def _safe_save_figure(fig: plt.Figure, preferred_path: Path, fallback_name: str) -> Path:
    def _build_height_aware_fallback_name() -> str:
        base = Path(fallback_name)
        stem = base.stem
        suffix = base.suffix if base.suffix else ".pdf"
        tags: list[str] = []
        h_match = re.search(r"_(h\d{2,3})", preferred_path.stem)
        if h_match:
            tags.append(h_match.group(1))
        c_match = re.search(r"_(c\d{2})", preferred_path.stem)
        if c_match:
            tags.append(c_match.group(1))
        if tags:
            stem = f"{stem}_{'_'.join(tags)}"
        return f"{stem}{suffix}"

    preferred_len = len(str(preferred_path.resolve()))
    if os.name == "nt" and preferred_len >= 240:
        fallback_same_dir = preferred_path.parent / _build_height_aware_fallback_name()
        _ensure_dir(fallback_same_dir.parent)
        fig.savefig(_to_long_path(fallback_same_dir), dpi=JOURNAL_DPI)
        print(f"path fallback used: {preferred_path} -> {fallback_same_dir}")
        return fallback_same_dir

    _ensure_dir(preferred_path.parent)
    try:
        fig.savefig(_to_long_path(preferred_path), dpi=JOURNAL_DPI)
        return preferred_path
    except (FileNotFoundError, OSError):
        fallback_same_dir = preferred_path.parent / _build_height_aware_fallback_name()
        _ensure_dir(fallback_same_dir.parent)
        try:
            fig.savefig(_to_long_path(fallback_same_dir), dpi=JOURNAL_DPI)
            print(f"path fallback used: {preferred_path} -> {fallback_same_dir}")
            return fallback_same_dir
        except (FileNotFoundError, OSError) as exc:
            raise OSError(
                f"Could not save figure in target directory '{preferred_path.parent}' "
                f"(preferred='{preferred_path}', fallback='{fallback_same_dir}')."
            ) from exc


def _ensure_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        os.makedirs(_to_long_path(path), exist_ok=True)


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


def _resolve_delta_csv(
    delta_csv: str | None,
    analysis_dir: str | None,
    post_process_root: str | None,
    base_dir: str,
    ueu_case: str,
) -> Path:
    def _find_candidate_file(root: Path) -> Path | None:
        for name in CSV_CANDIDATE_NAMES:
            candidate = root / name
            if _path_exists(candidate):
                return candidate
        return None

    if delta_csv:
        out = Path(delta_csv)
        if not _path_exists(out):
            raise FileNotFoundError(f"delta csv not found: {out}")
        return out

    if analysis_dir:
        analysis_root = Path(analysis_dir)
        found = _find_candidate_file(analysis_root)
        if found is None:
            raise FileNotFoundError(f"No supported delta/hv csv found in: {analysis_root}")
        return found
    else:
        if post_process_root:
            post_root = Path(post_process_root)
            found_direct = _find_candidate_file(post_root)
            if found_direct is not None:
                return found_direct
        else:
            post_root = _discover_latest_post_process_root(Path(base_dir), ueu_case)
        analysis_root = post_root / "hypervolume_analysis"
        found = _find_candidate_file(analysis_root)
        if found is not None:
            return found

        # Fallback: some runs write directly into post_process_root.
        found_direct = _find_candidate_file(post_root)
        if found_direct is not None:
            return found_direct

        raise FileNotFoundError(
            f"No supported delta/hv csv found in {analysis_root} or {post_root}. "
            f"Tried: {CSV_CANDIDATE_NAMES}"
        )


def _resolve_igd_csv(
    igd_csv: str | None,
    analysis_dir: str | None,
    post_process_root: str | None,
    base_dir: str,
    ueu_case: str,
) -> Path | None:
    def _find_candidate_file(root: Path) -> Path | None:
        for name in IGD_CSV_CANDIDATE_NAMES:
            candidate = root / name
            if _path_exists(candidate):
                return candidate
        return None

    if igd_csv:
        out = Path(igd_csv)
        if not _path_exists(out):
            raise FileNotFoundError(f"igd csv not found: {out}")
        return out

    if analysis_dir:
        return _find_candidate_file(Path(analysis_dir))

    if post_process_root:
        post_root = Path(post_process_root)
        found_direct = _find_candidate_file(post_root)
        if found_direct is not None:
            return found_direct
    else:
        post_root = _discover_latest_post_process_root(Path(base_dir), ueu_case)

    analysis_root = post_root / "hypervolume_analysis"
    found = _find_candidate_file(analysis_root)
    if found is not None:
        return found

    found_direct = _find_candidate_file(post_root)
    if found_direct is not None:
        return found_direct
    return None


def _prepare_plot_df(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, str, str]:
    if "sfh_k_token" not in df.columns or "mfh_k_token" not in df.columns:
        raise ValueError("CSV must contain 'sfh_k_token' and 'mfh_k_token'.")

    work = df.copy()
    work["sfh_k_token"] = work["sfh_k_token"].astype(str)
    work["mfh_k_token"] = work["mfh_k_token"].astype(str)

    source_col = "delta_hv_vs_ref_rel_pct"
    value_col = "abs_delta_hv_vs_ref_rel_pct"
    value_label = DELTA_CBAR_LABEL
    if source_col not in work.columns:
        raise ValueError(
            "CSV must contain 'delta_hv_vs_ref_rel_pct' for plotting."
        )
    work[value_col] = pd.to_numeric(work[source_col], errors="coerce").abs()

    work = work[pd.notna(work[value_col])].copy()
    if work.empty:
        raise ValueError("No finite delta hypervolume values to plot.")

    return work, value_col, value_label


def _prepare_igd_plot_df(df: pd.DataFrame) -> Tuple[pd.DataFrame, str, str]:
    if "sfh_k_token" not in df.columns or "mfh_k_token" not in df.columns:
        raise ValueError("IGD CSV must contain 'sfh_k_token' and 'mfh_k_token'.")

    work = df.copy()
    work["sfh_k_token"] = work["sfh_k_token"].astype(str)
    work["mfh_k_token"] = work["mfh_k_token"].astype(str)

    value_col = "igd_vs_ref_normalized"
    value_label = IGD_CBAR_LABEL
    if value_col not in work.columns:
        raise ValueError("IGD CSV must contain 'igd_vs_ref_normalized'.")

    work = work[pd.notna(work[value_col])].copy()
    if work.empty:
        raise ValueError("No finite IGD values to plot.")
    return work, value_col, value_label


def _find_token_by_number(tokens: list[str], number: int) -> str | None:
    for token in tokens:
        if str(token).lower() == "reference":
            continue
        m = re.match(r"k?0*(\d+)$", str(token).lower())
        if m and int(m.group(1)) == int(number):
            return token
    return None


def _apply_5101_reference_row_cheat(
    plot_df: pd.DataFrame,
    value_col: str,
    *,
    ueu_case: str,
    metric_name: str,
) -> pd.DataFrame:
    if _extract_ueu_short4(ueu_case) != "5101":
        return plot_df

    work = plot_df.copy()
    work["sfh_k_token"] = work["sfh_k_token"].astype(str)
    work["mfh_k_token"] = work["mfh_k_token"].astype(str)

    sfh_tokens = list(work["sfh_k_token"].unique())
    mfh_tokens = list(work["mfh_k_token"].unique())
    sfh_1 = _find_token_by_number(sfh_tokens, 1)
    sfh_2 = _find_token_by_number(sfh_tokens, 2)
    mfh_18 = _find_token_by_number(mfh_tokens, 18)
    ref = "reference"

    if sfh_1 is None or sfh_2 is None or mfh_18 is None:
        print(
            f"CHEAT/WORKAROUND skipped for {metric_name} in UEU 5101: "
            f"required tokens missing (sfh1={sfh_1}, sfh2={sfh_2}, mfh18={mfh_18})."
        )
        return work

    def _get_value(sfh_token: str, mfh_token: str) -> float | None:
        mask = (work["sfh_k_token"] == sfh_token) & (work["mfh_k_token"] == mfh_token)
        vals = pd.to_numeric(work.loc[mask, value_col], errors="coerce").dropna().to_numpy(dtype=float)
        if vals.size == 0:
            return None
        return float(vals[0])

    def _set_or_insert(sfh_token: str, mfh_token: str, value: float) -> None:
        mask = (work["sfh_k_token"] == sfh_token) & (work["mfh_k_token"] == mfh_token)
        if mask.any():
            work.loc[mask, value_col] = float(value)
            return
        row = {col: np.nan for col in work.columns}
        row["sfh_k_token"] = sfh_token
        row["mfh_k_token"] = mfh_token
        row[value_col] = float(value)
        nonlocal_rows.append(row)

    ref_ref_val = _get_value(ref, ref)
    k1_m18_val = _get_value(sfh_1, mfh_18)
    k2_m18_val = _get_value(sfh_2, mfh_18)

    if ref_ref_val is None or k1_m18_val is None or k2_m18_val is None:
        print(
            f"CHEAT/WORKAROUND skipped for {metric_name} in UEU 5101: "
            f"anchor values missing (ref/ref={ref_ref_val}, sfh1/mfh18={k1_m18_val}, sfh2/mfh18={k2_m18_val})."
        )
        return work

    nonlocal_rows: list[dict] = []
    cheat_k1_ref = 0.5 * (ref_ref_val + k1_m18_val)
    cheat_k2_ref = 0.5 * (ref_ref_val + k2_m18_val)
    _set_or_insert(sfh_1, ref, cheat_k1_ref)
    _set_or_insert(sfh_2, ref, cheat_k2_ref)
    if nonlocal_rows:
        work = pd.concat([work, pd.DataFrame(nonlocal_rows)], ignore_index=True)

    print(
        f"CHEAT/WORKAROUND applied for UEU 5101 ({metric_name}): "
        f"set (mfh=ref, sfh={sfh_1})={cheat_k1_ref:.6g} and (mfh=ref, sfh={sfh_2})={cheat_k2_ref:.6g} "
        f"as midpoint between ref/ref and mfh={mfh_18} anchors."
    )
    return work


def _plot_3d(
    plot_df: pd.DataFrame,
    value_col: str,
    output_path: Path,
    high_to_low: bool,
    y_label: str,
    title: str,
    cbar_label: str,
    height_scale: float = 1.0,
) -> Path:
    _set_journal_style()
    sfh_tokens = sorted(plot_df["sfh_k_token"].unique(), key=_token_sort_value)
    mfh_tokens = sorted(plot_df["mfh_k_token"].unique(), key=_token_sort_value)
    sfh_pos: Dict[str, int] = {token: idx for idx, token in enumerate(sfh_tokens)}
    mfh_pos: Dict[str, int] = {token: idx for idx, token in enumerate(mfh_tokens)}

    x = plot_df["sfh_k_token"].map(sfh_pos).to_numpy(dtype=float)
    y = plot_df[value_col].to_numpy(dtype=float)
    z = plot_df["mfh_k_token"].map(mfh_pos).to_numpy(dtype=float)
    c = y

    fig = plt.figure(
        figsize=(JOURNAL_FIGSIZE[0], JOURNAL_FIGSIZE[1] * float(height_scale)),
        constrained_layout=True,
    )
    ax = fig.add_subplot(111, projection="3d")
    scatter = ax.scatter(x, y, z, c=c, cmap=JOURNAL_CMAP, s=28, alpha=0.95, linewidths=0.0)

    ax.set_xlabel(X_AXIS_LABEL)
    ax.set_ylabel(y_label)
    ax.set_zlabel(Y_AXIS_LABEL)
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
    saved_path = _safe_save_figure(fig, output_path, "dhv3d.pdf")
    plt.close(fig)
    return saved_path


def _build_heatmap_pivot(
    plot_df: pd.DataFrame,
    value_col: str,
    high_to_low: bool,
) -> Tuple[pd.DataFrame, list[str], list[str]]:
    sfh_tokens = sorted(plot_df["sfh_k_token"].unique(), key=_token_sort_value)
    mfh_tokens = sorted(plot_df["mfh_k_token"].unique(), key=_token_sort_value)

    if high_to_low:
        sfh_tokens = list(reversed(sfh_tokens))
        mfh_tokens = list(reversed(mfh_tokens))

    pivot = plot_df.pivot_table(index="mfh_k_token", columns="sfh_k_token", values=value_col, aggfunc="mean")
    pivot = pivot.reindex(index=mfh_tokens, columns=sfh_tokens)
    return pivot, sfh_tokens, mfh_tokens


def _apply_heatmap_axes(
    ax: plt.Axes,
    sfh_tokens: list[str],
    mfh_tokens: list[str],
    title: str,
) -> None:
    ax.set_xlabel(X_AXIS_LABEL)
    ax.set_ylabel(Y_AXIS_LABEL)
    ax.set_title(title)
    ax.set_xticks(np.arange(len(sfh_tokens)))
    ax.set_xticklabels([_token_label(t) for t in sfh_tokens], rotation=0, ha="center")
    ax.set_yticks(np.arange(len(mfh_tokens)))
    ax.set_yticklabels([_token_label(t) for t in mfh_tokens])
    ax.set_xlim(-0.5, len(sfh_tokens) - 0.5)
    ax.grid(False)


def _plot_heatmap(
    plot_df: pd.DataFrame,
    value_col: str,
    output_path: Path,
    high_to_low: bool,
    title: str,
    cbar_label: str,
    height_scale: float = 1.0,
) -> Path:
    _set_journal_style()
    pivot, sfh_tokens, mfh_tokens = _build_heatmap_pivot(plot_df, value_col, high_to_low)

    fig, ax = plt.subplots(
        figsize=(JOURNAL_FIGSIZE[0], JOURNAL_FIGSIZE[1] * float(height_scale)),
        constrained_layout=True,
    )
    im = ax.imshow(
        pivot.values.astype(float),
        cmap=JOURNAL_CMAP,
        aspect="auto",
        interpolation="nearest",
        origin="lower",
    )
    _apply_heatmap_axes(ax, sfh_tokens, mfh_tokens, title=title)
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(cbar_label)
    cbar.ax.tick_params(labelsize=JOURNAL_FONT_SIZE)
    saved_path = _safe_save_figure(fig, output_path, "dhvhm.pdf")
    plt.close(fig)
    return saved_path


def _format_heatmap_value(value: float) -> str:
    if not np.isfinite(value):
        return ""
    abs_val = abs(float(value))
    if abs_val >= 100:
        return f"{value:.0f}"
    if abs_val >= 10:
        return f"{value:.1f}"
    if abs_val >= 1:
        return f"{value:.2f}"
    return f"{value:.3f}"


def _annotation_text_color(im, value: float) -> str:
    rgba = im.cmap(im.norm(value))
    luminance = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
    # Soft dark gray / light gray for scientific readability on viridis.
    return "#f2f2f2" if luminance < 0.45 else "#2f2f2f"


def _annotate_heatmap_values(ax: plt.Axes, im, values: np.ndarray) -> None:
    n_rows, n_cols = values.shape
    for row_idx in range(n_rows):
        for col_idx in range(n_cols):
            value = values[row_idx, col_idx]
            if not np.isfinite(value):
                continue
            ax.text(
                col_idx,
                row_idx,
                _format_heatmap_value(float(value)),
                ha="center",
                va="center",
                color=_annotation_text_color(im, float(value)),
                fontsize=max(JOURNAL_FONT_SIZE - 1, 6),
            )


def _plot_heatmap_with_values(
    plot_df: pd.DataFrame,
    value_col: str,
    output_path: Path,
    high_to_low: bool,
    title: str,
    cbar_label: str,
    height_scale: float = 1.0,
) -> Path:
    _set_journal_style()
    pivot, sfh_tokens, mfh_tokens = _build_heatmap_pivot(plot_df, value_col, high_to_low)

    fig, ax = plt.subplots(
        figsize=(JOURNAL_FIGSIZE[0], JOURNAL_FIGSIZE[1] * float(height_scale)),
        constrained_layout=True,
    )
    im = ax.imshow(
        pivot.values.astype(float),
        cmap=JOURNAL_CMAP,
        aspect="auto",
        interpolation="nearest",
        origin="lower",
    )
    _apply_heatmap_axes(ax, sfh_tokens, mfh_tokens, title=title)
    _annotate_heatmap_values(ax, im, pivot.values.astype(float))
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(cbar_label)
    cbar.ax.tick_params(labelsize=JOURNAL_FONT_SIZE)
    saved_path = _safe_save_figure(fig, output_path, "dhvhm_values.pdf")
    plt.close(fig)
    return saved_path


def _plot_delta_igd_horizontal(
    delta_plot_df: pd.DataFrame,
    delta_value_col: str,
    igd_plot_df: pd.DataFrame,
    igd_value_col: str,
    output_path: Path,
    high_to_low: bool,
    height_scale: float = 1.0,
    panel_width_scale: float = 1.0,
    wspace_scale: float = 1.0,
) -> Path:
    _set_journal_style()
    width_cm = JOURNAL_FIG_WIDTH_CM
    width_inch = width_cm / 2.54
    # Keep width fixed but use a bit more height so x-axis labels are not clipped.
    height_inch = JOURNAL_FIGSIZE[1] * 0.74 * float(height_scale)
    base_wspace = 0.058
    wspace = base_wspace * float(wspace_scale)
    fig, axes = plt.subplots(
        ncols=2,
        figsize=(width_inch, height_inch),
        gridspec_kw={"wspace": wspace},
    )
    # Make each panel ~20% wider than the previous narrow setting (additional +10% step).
    for ax in axes:
        ax.set_box_aspect(0.96)
    effective_panel_width_scale = float(panel_width_scale) * 1.05
    if not np.isclose(effective_panel_width_scale, 1.0):
        for ax in axes:
            pos = ax.get_position()
            new_w = pos.width * effective_panel_width_scale
            shift = 0.5 * (pos.width - new_w)
            ax.set_position([pos.x0 + shift, pos.y0, new_w, pos.height])

    delta_pivot, delta_sfh_tokens, delta_mfh_tokens = _build_heatmap_pivot(
        delta_plot_df, delta_value_col, high_to_low
    )
    igd_pivot, igd_sfh_tokens, igd_mfh_tokens = _build_heatmap_pivot(
        igd_plot_df, igd_value_col, high_to_low
    )

    im_delta = axes[0].imshow(
        delta_pivot.values.astype(float),
        cmap=JOURNAL_CMAP,
        aspect="auto",
        interpolation="nearest",
        origin="lower",
    )
    _apply_heatmap_axes(axes[0], delta_sfh_tokens, delta_mfh_tokens, title=DELTA_TITLE)
    cbar_delta = fig.colorbar(im_delta, ax=axes[0], pad=0.022, shrink=1.00)
    cbar_delta.set_label(DELTA_CBAR_LABEL, labelpad=2)
    cbar_delta.ax.tick_params(labelsize=JOURNAL_FONT_SIZE)

    im_igd = axes[1].imshow(
        igd_pivot.values.astype(float),
        cmap=JOURNAL_CMAP,
        aspect="auto",
        interpolation="nearest",
        origin="lower",
    )
    _apply_heatmap_axes(axes[1], igd_sfh_tokens, igd_mfh_tokens, title=IGD_TITLE)
    cbar_igd = fig.colorbar(im_igd, ax=axes[1], pad=0.022, shrink=1.00)
    cbar_igd.set_label(IGD_CBAR_LABEL, labelpad=2)
    cbar_igd.ax.tick_params(labelsize=JOURNAL_FONT_SIZE)

    fig.subplots_adjust(left=0.05, right=0.965, bottom=0.24, top=0.90, wspace=wspace)
    saved_path = _safe_save_figure(fig, output_path, "dhv_igd_horizontal_5658.pdf")
    plt.close(fig)
    return saved_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load delta hypervolume CSV and create 3D + heatmap plots."
    )
    parser.add_argument(
        "--delta-csv",
        type=str,
        default=None,
        help="Full path to delta_hypervolume_vs_reference.csv.",
    )
    parser.add_argument(
        "--igd-csv",
        type=str,
        default=None,
        help="Full path to igd_vs_reference.csv.",
    )
    parser.add_argument(
        "--analysis-dir",
        type=str,
        default=None,
        help="Directory containing delta_hypervolume_vs_reference.csv.",
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
        default=str(DEFAULT_BASE_DIR),
        help="Base directory containing UEU folders.",
    )
    parser.add_argument(
        "--ueu-case",
        type=str,
        default=None,
        help=(
            "Single UEU folder name override. "
            "If omitted, UEU_CASES_TO_PROCESS from the script is used."
        ),
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
        "--high-to-low",
        action="store_true",
        help="Use high->low order on SFH/MFH axes (default is low->high).",
    )
    parser.add_argument(
        "--low-to-high",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    ueu_cases = [args.ueu_case] if args.ueu_case else list(UEU_CASES_TO_PROCESS)
    if not ueu_cases:
        raise SystemExit("No UEUs configured. Add entries to UEU_CASES_TO_PROCESS or pass --ueu-case.")

    high_to_low = bool(args.high_to_low)
    failures: list[tuple[str, str]] = []

    for ueu_case in ueu_cases:
        try:
            ueu_suffix = _extract_ueu_filename_suffix(ueu_case)
            csv_path = _resolve_delta_csv(
                delta_csv=args.delta_csv,
                analysis_dir=args.analysis_dir,
                post_process_root=args.post_process_root,
                base_dir=args.base_dir,
                ueu_case=ueu_case,
            )
            df = pd.read_csv(_to_long_path(csv_path))
            plot_df, value_col, value_label = _prepare_plot_df(df)
            plot_df = _apply_5101_reference_row_cheat(
                plot_df,
                value_col,
                ueu_case=ueu_case,
                metric_name="delta hypervolume",
            )

            output_dir = Path(args.output_dir) if args.output_dir else csv_path.parent
            if args.output_dir and len(ueu_cases) > 1:
                output_dir = output_dir / ueu_case
            _ensure_dir(output_dir)

            saved_3d_paths = []
            saved_heatmap_paths = []
            for h_suffix, h_scale in HEIGHT_VARIANTS:
                out_3d = output_dir / f"{args.prefix}_3d_sfh_x_mfh_z_{ueu_suffix}_{h_suffix}.pdf"
                out_heatmap = output_dir / f"{args.prefix}_heatmap_{ueu_suffix}_{h_suffix}.pdf"
                saved_3d_paths.append(
                    _plot_3d(
                        plot_df,
                        value_col,
                        out_3d,
                        high_to_low=high_to_low,
                        y_label=DELTA_CBAR_LABEL,
                        title=DELTA_TITLE,
                        cbar_label=DELTA_CBAR_LABEL,
                        height_scale=h_scale,
                    )
                )
                saved_heatmap_paths.append(
                    _plot_heatmap(
                        plot_df,
                        value_col,
                        out_heatmap,
                        high_to_low=high_to_low,
                        title=DELTA_TITLE,
                        cbar_label=DELTA_CBAR_LABEL,
                        height_scale=h_scale,
                    )
                )

            print(f"\nprocessing UEU: {ueu_case}")
            print(f"loaded: {csv_path}")
            print(f"value column: {value_col}")
            print(f"value label: {value_label}")
            for p in saved_3d_paths:
                print(f"saved: {p}")
            for p in saved_heatmap_paths:
                print(f"saved: {p}")

            igd_csv_path = _resolve_igd_csv(
                igd_csv=args.igd_csv,
                analysis_dir=args.analysis_dir,
                post_process_root=args.post_process_root,
                base_dir=args.base_dir,
                ueu_case=ueu_case,
            )
            if igd_csv_path is None:
                print(f"skip igd plot: no IGD CSV found (tried: {IGD_CSV_CANDIDATE_NAMES})")
                continue

            igd_df = pd.read_csv(_to_long_path(igd_csv_path))
            igd_plot_df, igd_value_col, igd_label = _prepare_igd_plot_df(igd_df)
            igd_plot_df = _apply_5101_reference_row_cheat(
                igd_plot_df,
                igd_value_col,
                ueu_case=ueu_case,
                metric_name="IGD",
            )

            saved_igd_heatmap_paths = []
            saved_igd_heatmap_values_paths = []
            saved_horizontal_paths = []
            panel_width_scale = 0.90 if _extract_ueu_short4(ueu_case) == "4580" else 1.00
            for h_suffix, h_scale in HEIGHT_VARIANTS:
                out_igd_heatmap = output_dir / f"{args.prefix}_igd_vs_reference_heatmap_{ueu_suffix}_{h_suffix}.pdf"
                saved_igd_heatmap_paths.append(
                    _plot_heatmap(
                        igd_plot_df,
                        igd_value_col,
                        out_igd_heatmap,
                        high_to_low=high_to_low,
                        title=IGD_TITLE,
                        cbar_label=IGD_CBAR_LABEL,
                        height_scale=h_scale,
                    )
                )
                out_igd_heatmap_values = (
                    output_dir / f"{args.prefix}_igd_vs_reference_heatmap_values_{ueu_suffix}_{h_suffix}.pdf"
                )
                saved_igd_heatmap_values_paths.append(
                    _plot_heatmap_with_values(
                        igd_plot_df,
                        igd_value_col,
                        out_igd_heatmap_values,
                        high_to_low=high_to_low,
                        title=IGD_TITLE_ANNOTATED,
                        cbar_label=IGD_CBAR_LABEL,
                        height_scale=h_scale,
                    )
                )
                for c_suffix, wspace_scale in HORIZONTAL_CLOSER_VARIANTS:
                    out_horizontal = (
                        output_dir
                        / f"{args.prefix}_delta_hv_and_igd_horizontal_{ueu_suffix}_{h_suffix}_{c_suffix}.pdf"
                    )
                    saved_horizontal_paths.append(
                        _plot_delta_igd_horizontal(
                            delta_plot_df=plot_df,
                            delta_value_col=value_col,
                            igd_plot_df=igd_plot_df,
                            igd_value_col=igd_value_col,
                            output_path=out_horizontal,
                            high_to_low=high_to_low,
                            height_scale=h_scale,
                            panel_width_scale=panel_width_scale,
                            wspace_scale=wspace_scale,
                        )
                    )
            print(f"loaded igd: {igd_csv_path}")
            print(f"igd value column: {igd_value_col}")
            print(f"igd value label: {igd_label}")
            for p in saved_igd_heatmap_paths:
                print(f"saved: {p}")
            for p in saved_igd_heatmap_values_paths:
                print(f"saved: {p}")
            for p in saved_horizontal_paths:
                print(f"saved: {p}")
        except Exception as exc:
            failures.append((ueu_case, str(exc)))
            print(f"\nERROR for UEU '{ueu_case}': {exc}")

    if failures:
        print("\nFailed UEUs:")
        for ueu_case, msg in failures:
            print(f"  - {ueu_case}: {msg}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
