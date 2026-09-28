import argparse
import os
import pickle
import re
from pathlib import Path
from typing import Dict

import matplotlib
import numpy as np
from matplotlib.lines import Line2D

matplotlib.use("Agg")
import matplotlib.pyplot as plt


UEU_CASES_TO_PROCESS = [
    "processed_bds_in_DENI03403000SEC4580",
    "processed_bds_in_DENI03403000SEC5101",
    "processed_bds_in_DENI03403000SEC5658",
]
POST_PROCESS_ROOT_PATTERN = re.compile(r"^post_processed_dec_k_combinations_(\d{4})_(\d{2})_(\d{2})$")
COMBO_PATTERN = re.compile(r"^sfh_(k\d+|reference)_mfh_(k\d+|reference)$")
COMBINED_FRONT_FILENAME = "combined_front.pkl"

DEFAULT_BASE_DIR = Path(__file__).resolve().parent / "hypervolume_results"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "pareto_front"
DEFAULT_CLUSTER_SOURCE_DIR = Path(__file__).resolve().parents[2] / "03_applied_energy_optimization"
REFERENCE_BUILDING_KPI_CSV = Path(__file__).resolve().parents[1] / "reference_ueu_building_kpis.csv"
JOURNAL_FONT_FAMILY = "TeX Gyre Termes"
JOURNAL_FONT_SIZE = 9
JOURNAL_AXIS_FONT_SIZE = 8
JOURNAL_TICK_FONT_SIZE = 8
JOURNAL_DPI = 600
JOURNAL_CMAP = "viridis"
JOURNAL_FIG_WIDTH_CM = 11.8
JOURNAL_FIG_HEIGHT_CM = 5.270992
# PDF export contract: every saved PDF page from this plot script must be 11.8 cm wide.
# Do not pass bbox_inches="tight" for PDF output; it changes the final PDF bounding box.
PANEL_WIDTH_SCALE = 0.88
PANEL_HEIGHT_SCALE = 0.90
HEIGHT_VARIANTS: list[tuple[str, float]] = [
    ("h80", 0.80),
    ("h90", 0.90),
    ("h100", 1.00),
    ("h110", 1.10),
    ("h120", 1.20),
    ("h130", 1.30),
]

PAIR_DEFS = [
    ("totex", "co2"),
    ("totex", "peak"),
    ("co2", "peak"),
]
DIM_META = {
    "co2": {
        "index": 0,
        "scale": 1.0,
        "x_label": r"Ann. GWP" + "\n" + r"in kg CO$_2$-eq." + "\n" + r"per 100 m$^2$",
        "y_label": r"Ann. GWP in kg" + "\n" + r"CO$_2$-eq. per 100 m$^2$",
    },
    "peak": {
        "index": 1,
        "scale": 1.0,
        "x_label": r"Peak grid ex. power" + "\n" + r"in kW" + "\n" + r"per 100 m$^2$",
        "y_label": r"Peak grid ex. power" + "\n" + r"in kW per 100 m$^2$",
    },
    "totex": {
        "index": 2,
        "scale": 1.0,
        "x_label": r"Ann. TOTEX" + "\n" + r"in EUR" + "\n" + r"per 100 m$^2$",
        "y_label": r"Ann. TOTEX in EUR" + "\n" + r"per 100 m$^2$",
    },
}
DIM_INDEX = {key: int(meta["index"]) for key, meta in DIM_META.items()}
SFH_CMAP_SEQUENCE = [
    "Blues",
    "Oranges",
    "Purples",
    "Reds",
    "YlGnBu",
    "PuRd",
    "YlOrBr",
    "GnBu",
]
SELECTED_COMBOS_BY_UEU_SUFFIX: dict[str, set[str]] = {
    "4580": {
        "sfh_k01_mfh_k01",
        "sfh_k01_mfh_k02",
        "sfh_k01_mfh_k03",
        "sfh_k02_mfh_k01",
        "sfh_k02_mfh_k02",
        "sfh_k02_mfh_k03",
        "sfh_reference_mfh_reference",
    },
    "5101": {
        "sfh_k01_mfh_k01",
        "sfh_k01_mfh_k02",
        "sfh_k01_mfh_k03",
        "sfh_k02_mfh_k01",
        "sfh_k02_mfh_k02",
        "sfh_k02_mfh_k03",
        "sfh_reference_mfh_k01",
        "sfh_reference_mfh_k02",
        "sfh_reference_mfh_k03",
        "sfh_reference_mfh_reference",
    },
    "5658": {
        "sfh_reference_mfh_reference",
        "sfh_k02_mfh_k01",
        "sfh_k04_mfh_k01",
        "sfh_k06_mfh_k01",
        "sfh_k02_mfh_k02",
        "sfh_k04_mfh_k02",
        "sfh_k06_mfh_k02",
    }
}


def _set_journal_style(font_family: str = JOURNAL_FONT_FAMILY, font_size: int = JOURNAL_FONT_SIZE) -> None:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.family": font_family,
            "font.size": font_size,
            "axes.titlesize": font_size,
            "axes.labelsize": JOURNAL_AXIS_FONT_SIZE,
            "xtick.labelsize": JOURNAL_TICK_FONT_SIZE,
            "ytick.labelsize": JOURNAL_TICK_FONT_SIZE,
            "legend.fontsize": font_size,
            "mathtext.fontset": "cm",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _parse_date_suffix(folder_name: str) -> tuple[int, int, int] | None:
    match = POST_PROCESS_ROOT_PATTERN.match(folder_name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _extract_ueu_filename_suffix(ueu_case: str) -> str:
    token = Path(str(ueu_case)).name
    match = re.search(r"(DENI[0-9A-Za-z]+)", token)
    if match:
        return match.group(1)
    return token.replace(" ", "_")


def _extract_ueu_sector_suffix(ueu_case: str | Path | None) -> str | None:
    if ueu_case is None:
        return None
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


def _token_to_k(token: str) -> int | None:
    if _is_reference_token(token):
        return None
    return int(str(token)[1:])


def _token_sort_value(token: str) -> int:
    if _is_reference_token(token):
        return 10**9
    return int(str(token)[1:])


def _token_label(token: str) -> str:
    if _is_reference_token(token):
        return r"\mathrm{ref.}"
    return str(int(str(token)[1:]))


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
    short_root = Path(__file__).resolve().parent / "_plot_outputs"
    fallback_short_dir = short_root / fallback_name

    def _save(path: Path) -> None:
        if path.suffix.lower() == ".pdf":
            height = fig.get_size_inches()[1]
            fig.set_size_inches(JOURNAL_FIG_WIDTH_CM / 2.54, height, forward=False)
        fig.savefig(_to_long_path(path), dpi=JOURNAL_DPI)

    def _save_with_numbered_permission_fallback(path: Path) -> Path:
        try:
            _save(path)
            return path
        except PermissionError:
            for idx in range(1, 100):
                numbered = path.with_name(f"{path.stem}_new{idx}{path.suffix}")
                if _path_exists(numbered):
                    continue
                _save(numbered)
                print(f"permission fallback used: {path} -> {numbered}")
                return numbered
            raise

    preferred_len = len(str(preferred_path.resolve()))
    if os.name == "nt" and preferred_len >= 240:
        _ensure_dir(short_root)
        fallback_short_dir = _save_with_numbered_permission_fallback(fallback_short_dir)
        print(f"path fallback used: {preferred_path} -> {fallback_short_dir}")
        return fallback_short_dir

    _ensure_dir(preferred_path.parent)
    try:
        return _save_with_numbered_permission_fallback(preferred_path)
    except (FileNotFoundError, OSError):
        fallback_same_dir = preferred_path.parent / fallback_name
        _ensure_dir(fallback_same_dir.parent)
        try:
            fallback_same_dir = _save_with_numbered_permission_fallback(fallback_same_dir)
            print(f"path fallback used: {preferred_path} -> {fallback_same_dir}")
            return fallback_same_dir
        except (FileNotFoundError, OSError):
            _ensure_dir(short_root)
            fallback_short_dir = _save_with_numbered_permission_fallback(fallback_short_dir)
            print(f"path fallback used: {preferred_path} -> {fallback_short_dir}")
            return fallback_short_dir


def _ensure_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        os.makedirs(_to_long_path(path), exist_ok=True)


def _iter_child_dirs(path: Path) -> list[Path]:
    child_dirs: list[Path] = []
    try:
        with os.scandir(_to_long_path(path)) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        child_dirs.append(path / entry.name)
                except OSError:
                    continue
    except OSError:
        for child in path.iterdir():
            if _path_exists(child) and child.is_dir():
                child_dirs.append(child)
    return sorted(child_dirs, key=lambda p: p.name)


def _discover_latest_post_process_root(base_dir: Path, ueu_case: str) -> Path:
    cluster_root = Path(str(ueu_case)) if Path(str(ueu_case)).is_absolute() else (base_dir / ueu_case)
    if not cluster_root.exists():
        raise FileNotFoundError(f"UEU folder not found: {cluster_root}")

    candidates = [p for p in _iter_child_dirs(cluster_root) if _parse_date_suffix(p.name) is not None]
    if not candidates:
        raise FileNotFoundError(f"No post-process folders found below: {cluster_root}")
    candidates = sorted(candidates, key=lambda p: _parse_date_suffix(p.name))
    return candidates[-1]


def _parse_combo_name(name: str) -> dict | None:
    match = COMBO_PATTERN.match(name)
    if not match:
        return None
    sfh_token = match.group(1)
    mfh_token = match.group(2)
    return {
        "combo": name,
        "sfh_k_token": sfh_token,
        "mfh_k_token": mfh_token,
        "sfh_k": _token_to_k(sfh_token),
        "mfh_k": _token_to_k(mfh_token),
    }


def _extract_points_from_combined_front(path: Path) -> np.ndarray:
    with open(_to_long_path(path), "rb") as fh:
        data = pickle.load(fh)

    if not isinstance(data, list):
        return np.empty((0, 3), dtype=float)

    points: list[tuple[float, float, float]] = []
    for rec in data:
        if not isinstance(rec, dict):
            continue
        co2 = rec.get("co2")
        peak = rec.get("peak")
        totex = rec.get("totex")
        if co2 is None or peak is None or totex is None:
            continue
        try:
            point = (float(co2), float(peak), float(totex))
        except Exception:
            continue
        if not np.all(np.isfinite(point)):
            continue
        points.append(point)

    if not points:
        return np.empty((0, 3), dtype=float)
    return np.asarray(points, dtype=float)


def _load_all_combo_fronts(post_process_root: Path, allowed_combos: set[str] | None = None) -> list[dict]:
    fronts: list[dict] = []
    for combo_dir in _iter_child_dirs(post_process_root):
        if allowed_combos is not None and combo_dir.name not in allowed_combos:
            continue
        parsed = _parse_combo_name(combo_dir.name)
        if parsed is None:
            continue

        front_path = combo_dir / COMBINED_FRONT_FILENAME
        if not _path_exists(front_path):
            continue

        points = _extract_points_from_combined_front(front_path)
        if len(points) == 0:
            continue

        fronts.append(
            {
                **parsed,
                "points": points,
                "front_path": str(front_path),
            }
        )

    fronts.sort(key=lambda row: (_token_sort_value(row["sfh_k_token"]), _token_sort_value(row["mfh_k_token"])))
    return fronts


def _resolve_ueu_data_dir(ueu_case: str) -> Path:
    case_path = Path(str(ueu_case))
    if case_path.is_absolute() and case_path.exists():
        return case_path
    candidate = DEFAULT_CLUSTER_SOURCE_DIR / case_path.name
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"UEU data directory not found for '{ueu_case}'. Expected: {candidate}")


def _load_total_floor_area_from_cluster_pickle(path: Path) -> float:
    with open(_to_long_path(path), "rb") as fh:
        payload = pickle.load(fh)
    if not hasattr(payload, "columns") or not hasattr(payload, "iterrows"):
        raise ValueError(f"Unexpected cluster payload type in {path}: {type(payload)}")

    required_cols = {"building_id", "net_floor_area", "buildings_in_cluster"}
    missing = required_cols - set(payload.columns)
    if missing:
        raise ValueError(f"Missing columns in {path}: {sorted(missing)}")

    total_floor_area = 0.0
    seen_buildings: set[str] = set()
    for _, row in payload.iterrows():
        building_id = str(row["building_id"])
        if building_id in seen_buildings:
            continue
        seen_buildings.add(building_id)
        total_floor_area += float(row["net_floor_area"]) * float(row["buildings_in_cluster"])
    return float(total_floor_area)


def _per_100m2_divisor_for_ueu(ueu_case: str) -> float:
    try:
        ueu_data_dir = _resolve_ueu_data_dir(ueu_case)
    except FileNotFoundError:
        return _per_100m2_divisor_from_reference_kpis(ueu_case)
    sfh_path = ueu_data_dir / "sfh_cluster.pkl"
    mfh_path = ueu_data_dir / "mfh_cluster.pkl"
    if not _path_exists(sfh_path):
        return _per_100m2_divisor_from_reference_kpis(ueu_case)
    if not _path_exists(mfh_path):
        return _per_100m2_divisor_from_reference_kpis(ueu_case)

    total_floor_area = (
        _load_total_floor_area_from_cluster_pickle(sfh_path)
        + _load_total_floor_area_from_cluster_pickle(mfh_path)
    )
    divisor = total_floor_area / 100.0
    if not np.isfinite(divisor) or divisor <= 0:
        raise ValueError(f"Invalid floor-area divisor for UEU '{ueu_case}': {divisor}")
    return float(divisor)


def _per_100m2_divisor_from_reference_kpis(ueu_case: str) -> float:
    if not _path_exists(REFERENCE_BUILDING_KPI_CSV):
        raise FileNotFoundError(
            f"Missing cluster pickles and reference KPI CSV for UEU '{ueu_case}': "
            f"{REFERENCE_BUILDING_KPI_CSV}"
        )

    import pandas as pd

    df = pd.read_csv(_to_long_path(REFERENCE_BUILDING_KPI_CSV))
    if "ueu_case" not in df.columns or "net_floor_area" not in df.columns:
        raise ValueError(
            f"Reference KPI CSV must contain 'ueu_case' and 'net_floor_area': "
            f"{REFERENCE_BUILDING_KPI_CSV}"
        )

    mask = df["ueu_case"].astype(str) == str(ueu_case)
    total_floor_area = pd.to_numeric(df.loc[mask, "net_floor_area"], errors="coerce").dropna().sum()
    divisor = float(total_floor_area) / 100.0
    if not np.isfinite(divisor) or divisor <= 0:
        raise ValueError(f"Invalid reference-KPI floor-area divisor for UEU '{ueu_case}': {divisor}")
    print(f"floor-area fallback used for {ueu_case}: {REFERENCE_BUILDING_KPI_CSV}")
    return divisor


def _normalise_fronts_per_100m2(fronts: list[dict], divisor: float) -> list[dict]:
    normalised: list[dict] = []
    for row in fronts:
        scaled_points = np.asarray(row["points"], dtype=float) / float(divisor)
        normalised.append({**row, "points": scaled_points})
    return normalised


def _pareto_front_2d(points: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    if len(points) == 0:
        return np.empty((0, 2), dtype=float)

    pts = np.asarray(points, dtype=float)
    valid_mask = np.all(np.isfinite(pts), axis=1)
    pts = pts[valid_mask]
    if len(pts) == 0:
        return np.empty((0, 2), dtype=float)

    # Minimization in both dimensions.
    order = np.lexsort((pts[:, 1], pts[:, 0]))
    pts = pts[order]

    front: list[tuple[float, float]] = []
    best_y = np.inf
    for x_val, y_val in pts:
        if y_val < (best_y - eps):
            front.append((float(x_val), float(y_val)))
            best_y = float(y_val)

    if not front:
        return np.empty((0, 2), dtype=float)
    return np.asarray(front, dtype=float)


def _build_sfh_palette_map(fronts: list[dict]) -> Dict[str, object]:
    tokens = sorted({str(row["sfh_k_token"]) for row in fronts}, key=_token_sort_value)
    mapping: Dict[str, object] = {}
    palette_idx = 0
    for token in tokens:
        if _is_reference_token(token):
            mapping[token] = plt.get_cmap("Purples")
            continue
        cmap_name = SFH_CMAP_SEQUENCE[palette_idx % len(SFH_CMAP_SEQUENCE)]
        mapping[token] = plt.get_cmap(cmap_name)
        palette_idx += 1
    return mapping


def _get_mfh_shade_value(mfh_k: int | None, mfh_min: int, mfh_span: int) -> float:
    if mfh_k is None:
        return 0.95
    rel = (float(mfh_k) - float(mfh_min)) / float(mfh_span) if mfh_span > 0 else 1.0
    rel = min(max(rel, 0.0), 1.0)
    # Slightly boost low-end separation so nearby k_MFH values are still distinguishable.
    rel = rel**0.75
    # Sequential colormaps get darker for values closer to 1.0.
    return 0.30 + 0.65 * rel


def _axis_label(dim_key: str, axis: str) -> str:
    label_key = "x_label" if axis == "x" else "y_label"
    return str(DIM_META[dim_key][label_key])


def _scaled_dim_values(values: np.ndarray, dim_key: str) -> np.ndarray:
    return np.asarray(values, dtype=float) * float(DIM_META[dim_key]["scale"])


def _legend_mfh_entries_for_ueu(ueu_case: str | Path | None) -> int:
    suffix = _extract_ueu_sector_suffix(ueu_case)
    if suffix in {"4580", "5101"}:
        return 3
    return 2


def _shrink_axes_box(ax: plt.Axes, width_scale: float, height_scale: float) -> None:
    pos = ax.get_position()
    new_w = pos.width * float(width_scale)
    new_h = pos.height * float(height_scale)
    new_x0 = pos.x0 + 0.5 * (pos.width - new_w)
    new_y0 = pos.y0 + 0.5 * (pos.height - new_h)
    ax.set_position([new_x0, new_y0, new_w, new_h])


def _plot_front_pair(
    ax: plt.Axes,
    fronts: list[dict],
    x_key: str,
    y_key: str,
    palette_map: Dict[str, object],
    mfh_min: int,
    mfh_span: int,
) -> None:
    x_idx = DIM_INDEX[x_key]
    y_idx = DIM_INDEX[y_key]

    for row in fronts:
        raw_points = np.asarray(row["points"], dtype=float)
        points_2d = np.column_stack(
            (
                _scaled_dim_values(raw_points[:, x_idx], x_key),
                _scaled_dim_values(raw_points[:, y_idx], y_key),
            )
        )
        points = _pareto_front_2d(points_2d)
        if len(points) == 0:
            continue

        sfh_token = str(row["sfh_k_token"])
        mfh_token = str(row["mfh_k_token"])
        if _is_reference_token(sfh_token) and _is_reference_token(mfh_token):
            color = "black"
        else:
            cmap = palette_map.get(sfh_token, plt.get_cmap(JOURNAL_CMAP))
            color = cmap(_get_mfh_shade_value(row["mfh_k"], mfh_min=mfh_min, mfh_span=mfh_span))
        alpha = 0.70
        line_width = 1.10

        ax.plot(
            points[:, 0],
            points[:, 1],
            color=color,
            linewidth=line_width,
            alpha=alpha,
            zorder=2,
        )
        ax.scatter(
            points[:, 0],
            points[:, 1],
            color=color,
            marker="o",
            s=7.0,
            alpha=min(1.0, alpha + 0.10),
            linewidths=0.0,
            zorder=3,
        )

    ax.set_xlabel(_axis_label(x_key, axis="x"))
    ax.set_ylabel(_axis_label(y_key, axis="y"), labelpad=5.0)
    ax.tick_params(axis="both", which="major", pad=1.5, labelsize=JOURNAL_TICK_FONT_SIZE)
    ax.grid(True, alpha=0.3, linewidth=0.6)


def _collect_legend_data(fronts: list[dict], max_groups: int = 3) -> tuple[list[tuple[str, list[str]]], bool, int]:
    mfh_tokens_by_sfh: Dict[str, set[str]] = {}
    for row in fronts:
        sfh_token = str(row["sfh_k_token"])
        mfh_token = str(row["mfh_k_token"])
        if _is_reference_token(sfh_token) and _is_reference_token(mfh_token):
            continue
        mfh_tokens_by_sfh.setdefault(sfh_token, set()).add(mfh_token)

    ordered_sfh_tokens = sorted(mfh_tokens_by_sfh.keys(), key=_token_sort_value)
    groups_to_show = ordered_sfh_tokens[:max_groups]
    group_specs = [
        (sfh_token, sorted(mfh_tokens_by_sfh[sfh_token], key=_token_sort_value))
        for sfh_token in groups_to_show
    ]
    has_ref_ref = any(
        _is_reference_token(str(row["sfh_k_token"])) and _is_reference_token(str(row["mfh_k_token"]))
        for row in fronts
    )
    hidden_groups = max(0, len(ordered_sfh_tokens) - max_groups)
    return group_specs, has_ref_ref, hidden_groups


def _render_grouped_legend(
    legend_ax: plt.Axes,
    group_specs: list[tuple[str, list[str]]],
    has_ref_ref: bool,
    hidden_groups: int,
    palette_map: Dict[str, object],
    mfh_min: int,
    mfh_span: int,
) -> None:
    legend_ax.axis("off")
    legend_font_size = max(7, JOURNAL_FONT_SIZE - 1)
    title_x, line_x0, line_x1, text_x = 0.12, 0.15, 0.39, 0.44

    rows: list[dict] = []
    for sfh_token, mfh_tokens in group_specs:
        rows.append({"kind": "heading", "sfh_token": sfh_token})
        for mfh_token in mfh_tokens:
            rows.append({"kind": "item", "sfh_token": sfh_token, "mfh_token": mfh_token})
        rows.append({"kind": "spacer"})
    if has_ref_ref:
        rows.extend([{"kind": "heading_ref"}, {"kind": "item_ref"}, {"kind": "spacer"}])
    if hidden_groups > 0:
        rows.append({"kind": "hint", "hidden_groups": hidden_groups})

    spacing_factor = 10.0
    heading_step = 0.012 * spacing_factor
    item_step = 0.010 * spacing_factor
    spacer_step = 0.014 * spacing_factor
    hint_step = 0.009 * spacing_factor
    y = 0.985

    for row in rows:
        kind = row["kind"]
        if kind == "heading":
            sfh_label = _token_label(str(row["sfh_token"]))
            legend_ax.text(title_x, y, rf"$k_{{\mathrm{{SFH}}}} = {sfh_label}$", ha="left", va="top", transform=legend_ax.transAxes, fontsize=legend_font_size)
        elif kind == "item":
            sfh_token = str(row["sfh_token"])
            mfh_token = str(row["mfh_token"])
            shade = _get_mfh_shade_value(_token_to_k(mfh_token), mfh_min=mfh_min, mfh_span=mfh_span)
            color = palette_map.get(sfh_token, plt.get_cmap(JOURNAL_CMAP))(shade)
            y_mid = y - (0.50 * item_step)
            legend_ax.add_line(Line2D([line_x0, line_x1], [y_mid, y_mid], color=color, linewidth=2.4, alpha=0.85, transform=legend_ax.transAxes, clip_on=False))
            legend_ax.text(text_x, y_mid, rf"$k_{{\mathrm{{MFH}}}} = {_token_label(mfh_token)}$", ha="left", va="center", transform=legend_ax.transAxes, fontsize=legend_font_size)
        elif kind == "heading_ref":
            legend_ax.text(title_x, y, r"$k_{\mathrm{MFH}} = \mathrm{ref.}$", ha="left", va="top", transform=legend_ax.transAxes, fontsize=legend_font_size)
        elif kind == "item_ref":
            y_mid = y - (0.50 * item_step)
            legend_ax.add_line(Line2D([line_x0, line_x1], [y_mid, y_mid], color="black", linewidth=2.4, alpha=0.85, transform=legend_ax.transAxes, clip_on=False))
            legend_ax.text(text_x, y_mid, r"$k_{\mathrm{SFH}} = \mathrm{ref.}$", ha="left", va="center", transform=legend_ax.transAxes, fontsize=legend_font_size)
        elif kind == "hint":
            legend_ax.text(title_x, y, f"+{int(row['hidden_groups'])} more SFH groups", ha="left", va="top", transform=legend_ax.transAxes, fontsize=legend_font_size)
        if kind in ("heading", "heading_ref"):
            y -= heading_step
        elif kind in ("item", "item_ref"):
            y -= item_step
        elif kind == "spacer":
            y -= spacer_step
        else:
            y -= hint_step


def _render_matrix_legend(
    legend_ax: plt.Axes,
    group_specs: list[tuple[str, list[str]]],
    has_ref_ref: bool,
    hidden_groups: int,
    palette_map: Dict[str, object],
    mfh_min: int,
    mfh_span: int,
) -> None:
    legend_ax.axis("off")
    legend_font_size = max(7, JOURNAL_FONT_SIZE - 1)
    mfh_cols = sorted({tok for _, toks in group_specs for tok in toks if not _is_reference_token(tok)}, key=_token_sort_value)[:3]
    if not mfh_cols:
        mfh_cols = ["k1", "k2"]

    x_label = 0.01
    x0 = 0.26
    col_w = 0.22
    y = 0.97
    legend_ax.text(x_label, y, r"$\mathrm{SFH}\backslash\mathrm{MFH}$", ha="left", va="top", transform=legend_ax.transAxes, fontsize=legend_font_size)
    for i, mfh_tok in enumerate(mfh_cols):
        legend_ax.text(x0 + i * col_w, y, rf"$k_{{\mathrm{{MFH}}}}={_token_label(mfh_tok)}$", ha="left", va="top", transform=legend_ax.transAxes, fontsize=legend_font_size)
    y -= 0.10

    for sfh_tok, tokens in group_specs:
        legend_ax.text(x_label, y, rf"$k_{{\mathrm{{SFH}}}}={_token_label(sfh_tok)}$", ha="left", va="center", transform=legend_ax.transAxes, fontsize=legend_font_size)
        cmap = palette_map.get(sfh_tok, plt.get_cmap(JOURNAL_CMAP))
        for i, mfh_tok in enumerate(mfh_cols):
            if mfh_tok in tokens:
                shade = _get_mfh_shade_value(_token_to_k(mfh_tok), mfh_min=mfh_min, mfh_span=mfh_span)
                color = cmap(shade)
                legend_ax.add_line(Line2D([x0 + i * col_w, x0 + i * col_w + 0.14], [y, y], color=color, linewidth=3.0, alpha=0.9, transform=legend_ax.transAxes, clip_on=False))
            else:
                legend_ax.text(x0 + i * col_w + 0.05, y, "–", ha="center", va="center", transform=legend_ax.transAxes, fontsize=legend_font_size)
        y -= 0.12

    if has_ref_ref:
        legend_ax.text(x_label, y, r"$k_{\mathrm{MFH}}=\mathrm{ref.}$", ha="left", va="center", transform=legend_ax.transAxes, fontsize=legend_font_size)
        legend_ax.add_line(Line2D([x0, x0 + 0.14], [y, y], color="black", linewidth=3.0, alpha=0.9, transform=legend_ax.transAxes, clip_on=False))
        legend_ax.text(x0 + 0.16, y, r"$k_{\mathrm{SFH}}=\mathrm{ref.}$", ha="left", va="center", transform=legend_ax.transAxes, fontsize=legend_font_size)
        y -= 0.12

    if hidden_groups > 0:
        legend_ax.text(x_label, max(0.02, y), f"+{hidden_groups} more SFH groups", ha="left", va="bottom", transform=legend_ax.transAxes, fontsize=legend_font_size)


def _render_split_legend(
    legend_ax: plt.Axes,
    group_specs: list[tuple[str, list[str]]],
    has_ref_ref: bool,
    hidden_groups: int,
    palette_map: Dict[str, object],
    mfh_min: int,
    mfh_span: int,
) -> None:
    legend_ax.axis("off")
    legend_font_size = max(7, JOURNAL_FONT_SIZE - 1)
    y = 0.97
    legend_ax.text(0.01, y, r"$\mathrm{SFH\ color\ families}$", ha="left", va="top", transform=legend_ax.transAxes, fontsize=legend_font_size)
    y -= 0.08
    for sfh_tok, _ in group_specs:
        color = palette_map.get(sfh_tok, plt.get_cmap(JOURNAL_CMAP))(_get_mfh_shade_value(mfh_min, mfh_min, mfh_span))
        legend_ax.add_line(Line2D([0.03, 0.23], [y, y], color=color, linewidth=3.0, alpha=0.9, transform=legend_ax.transAxes, clip_on=False))
        legend_ax.text(0.27, y, rf"$k_{{\mathrm{{SFH}}}}={_token_label(sfh_tok)}$", ha="left", va="center", transform=legend_ax.transAxes, fontsize=legend_font_size)
        y -= 0.09

    y -= 0.03
    legend_ax.text(0.01, y, r"$\mathrm{MFH\ shade\ levels}$", ha="left", va="top", transform=legend_ax.transAxes, fontsize=legend_font_size)
    y -= 0.08
    mfh_tokens = sorted({tok for _, toks in group_specs for tok in toks if not _is_reference_token(tok)}, key=_token_sort_value)[:3]
    sample_cmap = plt.get_cmap("Blues")
    for mfh_tok in mfh_tokens:
        shade = _get_mfh_shade_value(_token_to_k(mfh_tok), mfh_min=mfh_min, mfh_span=mfh_span)
        legend_ax.add_line(Line2D([0.03, 0.23], [y, y], color=sample_cmap(shade), linewidth=3.0, alpha=0.9, transform=legend_ax.transAxes, clip_on=False))
        legend_ax.text(0.27, y, rf"$k_{{\mathrm{{MFH}}}}={_token_label(mfh_tok)}$", ha="left", va="center", transform=legend_ax.transAxes, fontsize=legend_font_size)
        y -= 0.09

    if has_ref_ref:
        y -= 0.02
        legend_ax.add_line(Line2D([0.03, 0.23], [y, y], color="black", linewidth=3.0, alpha=0.9, transform=legend_ax.transAxes, clip_on=False))
        legend_ax.text(0.27, y, r"$k_{\mathrm{SFH}}=\mathrm{ref.},\ k_{\mathrm{MFH}}=\mathrm{ref.}$", ha="left", va="center", transform=legend_ax.transAxes, fontsize=legend_font_size)
        y -= 0.09
    if hidden_groups > 0:
        legend_ax.text(0.01, max(0.02, y), f"+{hidden_groups} more SFH groups", ha="left", va="bottom", transform=legend_ax.transAxes, fontsize=legend_font_size)


def _add_right_side_color_legends(
    legend_ax: plt.Axes,
    fronts: list[dict],
    palette_map: Dict[str, object],
    mfh_min: int,
    mfh_span: int,
) -> None:
    group_specs, has_ref_ref, hidden_groups = _collect_legend_data(fronts, max_groups=3)
    if not group_specs and not has_ref_ref:
        legend_ax.axis("off")
        legend_ax.text(0.0, 0.98, "No groups to display.", ha="left", va="top")
        return
    _render_grouped_legend(legend_ax, group_specs, has_ref_ref, hidden_groups, palette_map, mfh_min, mfh_span)


def _add_top_column_legend(
    legend_ax: plt.Axes,
    fronts: list[dict],
    palette_map: Dict[str, object],
    mfh_min: int,
    mfh_span: int,
    max_mfh_entries: int = 2,
) -> None:
    legend_ax.axis("off")
    legend_font_size = max(7, JOURNAL_FONT_SIZE - 1)
    group_specs, has_ref_ref, hidden_groups = _collect_legend_data(fronts, max_groups=4)

    columns: list[dict] = []
    for sfh_token, mfh_tokens in group_specs:
        cols = [tok for tok in mfh_tokens if not _is_reference_token(tok)]
        columns.append(
            {
                "title": rf"$k_{{\mathrm{{SFH}}}} = {_token_label(sfh_token)}$",
                "sfh_token": sfh_token,
                "mfh_tokens": cols[:max_mfh_entries],
            }
        )
    if has_ref_ref:
        columns.append(
            {
                "title": r"$k_{\mathrm{MFH}} = \mathrm{ref.}$",
                "sfh_token": None,
                "mfh_tokens": ["reference"],
            }
        )

    if not columns:
        legend_ax.text(0.0, 0.98, "No groups to display.", ha="left", va="top")
        return

    ncols = len(columns)
    y_title = 0.93
    if max_mfh_entries <= 2:
        y_rows = [0.52, 0.26]
    else:
        y_rows = [0.56, 0.36, 0.16]

    for i, col in enumerate(columns):
        col_left = i / ncols
        col_right = (i + 1) / ncols
        col_w = col_right - col_left

        title_x = col_left + 0.04 * col_w
        line_x0 = col_left + 0.06 * col_w
        line_x1 = col_left + 0.40 * col_w
        text_x = col_left + 0.46 * col_w

        legend_ax.text(
            title_x,
            y_title,
            str(col["title"]),
            ha="left",
            va="top",
            transform=legend_ax.transAxes,
            fontsize=legend_font_size,
        )

        sfh_token = col["sfh_token"]
        mfh_tokens = list(col["mfh_tokens"])
        for ridx, mfh_token in enumerate(mfh_tokens[:max_mfh_entries]):
            y = y_rows[ridx]
            if sfh_token is None:
                color = "black"
                row_label = r"$k_{\mathrm{SFH}} = \mathrm{ref.}$"
            else:
                shade = _get_mfh_shade_value(_token_to_k(str(mfh_token)), mfh_min=mfh_min, mfh_span=mfh_span)
                color = palette_map.get(str(sfh_token), plt.get_cmap(JOURNAL_CMAP))(shade)
                row_label = rf"$k_{{\mathrm{{MFH}}}} = {_token_label(str(mfh_token))}$"

            legend_ax.add_line(
                Line2D(
                    [line_x0, line_x1],
                    [y, y],
                    color=color,
                    linewidth=2.4,
                    alpha=0.85,
                    transform=legend_ax.transAxes,
                    clip_on=False,
                )
            )
            legend_ax.text(
                text_x,
                y,
                row_label,
                ha="left",
                va="center",
                transform=legend_ax.transAxes,
                fontsize=legend_font_size,
            )

    if hidden_groups > 0:
        legend_ax.text(
            0.01,
            0.02,
            f"+{hidden_groups} more SFH groups",
            ha="left",
            va="bottom",
            transform=legend_ax.transAxes,
            fontsize=legend_font_size,
        )


def _plot_all_projections(
    fronts: list[dict],
    output_path: Path,
    ueu_case: str,
    height_scale: float = 1.0,
) -> Path:
    _set_journal_style()
    palette_map = _build_sfh_palette_map(fronts)
    max_mfh_entries = _legend_mfh_entries_for_ueu(ueu_case)
    mfh_numeric_values = [int(row["mfh_k"]) for row in fronts if row["mfh_k"] is not None]
    mfh_min = min(mfh_numeric_values) if mfh_numeric_values else 1
    mfh_max = max(mfh_numeric_values) if mfh_numeric_values else mfh_min
    mfh_span = max(mfh_max - mfh_min, 1)

    fig = plt.figure(
        figsize=(JOURNAL_FIG_WIDTH_CM / 2.54, JOURNAL_FIG_HEIGHT_CM * float(height_scale) / 2.54)
    )
    legend_height_ratio = 0.56 if max_mfh_entries >= 3 else 0.34
    legend_hspace = 0.12 if max_mfh_entries >= 3 else 0.03
    outer_gs = fig.add_gridspec(
        nrows=2,
        ncols=1,
        height_ratios=[legend_height_ratio, 1.0],
        hspace=legend_hspace,
    )
    plot_gs = outer_gs[1, 0].subgridspec(nrows=1, ncols=3, wspace=0.70)
    plot_axes = [fig.add_subplot(plot_gs[0, i]) for i in range(3)]
    legend_ax = fig.add_subplot(outer_gs[0, 0])

    for ax, (x_key, y_key) in zip(plot_axes, PAIR_DEFS):
        _plot_front_pair(
            ax,
            fronts,
            x_key=x_key,
            y_key=y_key,
            palette_map=palette_map,
            mfh_min=mfh_min,
            mfh_span=mfh_span,
        )
        if y_key == "peak":
            _, ymax = ax.get_ylim()
            if ymax >= 4.0:
                ax.set_yticks([2.0, 4.0])
                ax.set_yticklabels(["2.0", "4.0"])
                ax.tick_params(axis="y", which="major", labelsize=JOURNAL_TICK_FONT_SIZE)
        if _extract_ueu_sector_suffix(ueu_case) == "5101" and x_key == "totex" and y_key == "peak":
            ax.set_xticks([2250, 2750])
            ax.set_xticklabels(["2250", "2750"])
            ax.tick_params(axis="x", which="major", labelsize=JOURNAL_TICK_FONT_SIZE)
    # Move the leftmost y-axis label slightly inward to avoid clipping.
    if plot_axes:
        plot_axes[0].yaxis.set_label_coords(-0.42, 0.5)
    _add_top_column_legend(
        legend_ax=legend_ax,
        fronts=fronts,
        palette_map=palette_map,
        mfh_min=mfh_min,
        mfh_span=mfh_span,
        max_mfh_entries=max_mfh_entries,
    )
    fig.subplots_adjust(left=0.17, right=0.985, bottom=0.34, top=0.95)
    for ax in plot_axes:
        _shrink_axes_box(ax, PANEL_WIDTH_SCALE, PANEL_HEIGHT_SCALE)

    saved_path = _safe_save_figure(fig, output_path, output_path.name)
    plt.close(fig)
    return saved_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot Pareto front projections for all SFH/MFH cluster combinations."
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
        help="Single UEU folder override. If omitted, UEU_CASES_TO_PROCESS is used.",
    )
    parser.add_argument(
        "--post-process-root",
        type=str,
        default=None,
        help="Optional explicit post_processed_dec_k_combinations_YYYY_MM_DD folder.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output folder. Default: <script_dir>/pareto_front/<ueu_case>/.",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="pareto_front_projections",
        help="Output filename prefix.",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    ueu_cases = [args.ueu_case] if args.ueu_case else list(UEU_CASES_TO_PROCESS)
    if not ueu_cases:
        raise SystemExit("No UEUs configured. Add entries to UEU_CASES_TO_PROCESS or pass --ueu-case.")

    failures: list[tuple[str, str]] = []
    for ueu_case in ueu_cases:
        try:
            if args.post_process_root:
                post_process_root = Path(args.post_process_root)
            else:
                post_process_root = _discover_latest_post_process_root(Path(args.base_dir), ueu_case)
            if not post_process_root.exists():
                raise FileNotFoundError(f"post-process root not found: {post_process_root}")

            ueu_suffix_code = _extract_ueu_sector_suffix(ueu_case) or _extract_ueu_sector_suffix(post_process_root)
            allowed_combos = SELECTED_COMBOS_BY_UEU_SUFFIX.get(str(ueu_suffix_code), None)
            if allowed_combos is not None and len(allowed_combos) == 0:
                # Empty filter should not hide everything by accident.
                allowed_combos = None
            missing_selected_combos: list[str] = []
            if allowed_combos is not None:
                available_combo_dirs = {
                    p.name
                    for p in _iter_child_dirs(post_process_root)
                    if _parse_combo_name(p.name) is not None
                }
                missing_selected_combos = sorted(allowed_combos - available_combo_dirs)
            fronts = _load_all_combo_fronts(post_process_root, allowed_combos=allowed_combos)
            if not fronts:
                raise ValueError(
                    f"No non-empty '{COMBINED_FRONT_FILENAME}' found below: {post_process_root}"
                )
            per_100m2_divisor = _per_100m2_divisor_for_ueu(str(ueu_case))
            fronts = _normalise_fronts_per_100m2(fronts, divisor=per_100m2_divisor)

            ueu_suffix = _extract_ueu_filename_suffix(ueu_case)
            output_dir = (
                Path(args.output_dir)
                if args.output_dir
                else (DEFAULT_OUTPUT_ROOT / Path(str(ueu_case)).name)
            )
            _ensure_dir(output_dir)
            saved_paths = []
            for height_suffix, height_scale in HEIGHT_VARIANTS:
                out_path = output_dir / f"{args.prefix}_{ueu_suffix}_{height_suffix}.pdf"
                saved_paths.append(
                    _plot_all_projections(
                        fronts=fronts,
                        output_path=out_path,
                        ueu_case=ueu_case,
                        height_scale=height_scale,
                    )
                )

            print(f"\nprocessing UEU: {ueu_case}")
            print(f"post-process root: {post_process_root}")
            if allowed_combos is not None:
                print(f"combo filter active: {len(allowed_combos)} selected combinations for SEC{ueu_suffix_code}")
                if missing_selected_combos:
                    print(
                        f"selected combos missing in folder (ignored): {len(missing_selected_combos)}"
                    )
            print(f"normalisation divisor (A/100): {per_100m2_divisor:.6f}")
            print(f"loaded combos with fronts: {len(fronts)}")
            for saved in saved_paths:
                print(f"saved: {saved}")
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
