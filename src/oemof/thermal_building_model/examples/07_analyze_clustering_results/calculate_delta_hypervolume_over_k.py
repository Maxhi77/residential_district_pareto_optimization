import pickle
import re
import os
from pathlib import Path

import numpy as np
import pandas as pd


POST_PROCESS_ROOT_PATTERN = re.compile(r"^post_processed_dec_k_combinations_(\d{4})_(\d{2})_(\d{2})$")
INPUT_BASE_DIR = Path(__file__).resolve().parent / "hypervolume_results"
OUTPUT_BASE_DIR = Path(__file__).resolve().parent / "hypervolume_results"
COMBO_PATTERN = re.compile(r"^sfh_(k\d+|reference)_mfh_(k\d+|reference)$")
COMBINED_FRONT_FILENAME = "combined_front.pkl"
REFERENCE_MARGIN = 0.05
UEU_CASES_TO_PROCESS = [
    #"processed_bds_in_DENI03403000SEC4580",
    "processed_bds_in_DENI03403000SEC5101",
    #"processed_bds_in_DENI03403000SEC5658",
]
POST_PROCESS_NAME = None

DELTA_SFH_COLUMNS = [
    "mfh_k_token",
    "mfh_k",
    "sfh_k_prev",
    "sfh_k_curr",
    "sfh_k_step",
    "is_k_plus_1",
    "combo_prev",
    "combo_curr",
    "hv_prev",
    "hv_curr",
    "delta_hv",
    "delta_hv_rel_pct",
    "stagnates_non_positive",
]

DELTA_MFH_COLUMNS = [
    "sfh_k_token",
    "sfh_k",
    "mfh_k_prev",
    "mfh_k_curr",
    "mfh_k_step",
    "is_k_plus_1",
    "combo_prev",
    "combo_curr",
    "hv_prev",
    "hv_curr",
    "delta_hv",
    "delta_hv_rel_pct",
    "stagnates_non_positive",
]


def _igd(reference_points: np.ndarray, approx_points: np.ndarray) -> float:
    if len(reference_points) == 0 or len(approx_points) == 0:
        return np.nan
    diff = reference_points[:, None, :] - approx_points[None, :, :]
    dist_sq = np.sum(diff * diff, axis=2)
    min_dist = np.sqrt(np.min(dist_sq, axis=1))
    return float(np.mean(min_dist))


def _build_igd_vs_reference(
        df: pd.DataFrame,
        combo_points: dict[str, np.ndarray],
        allow_fallback_reference: bool = False,
) -> tuple[pd.DataFrame, str]:
    work = df.copy()
    work = work[work["combo"].notna()].copy()
    if work.empty:
        return pd.DataFrame(), "no_reference"

    ref_row, ref_source = _select_reference_row(work, allow_fallback=allow_fallback_reference)
    ref_combo = str(ref_row["combo"])
    ref_points = combo_points.get(ref_combo, np.empty((0, 3), dtype=float))
    if len(ref_points) == 0:
        raise ValueError(
            f"Reference combo '{ref_combo}' has no valid points in {COMBINED_FRONT_FILENAME}; IGD cannot be computed."
        )

    all_valid_points = [pts for pts in combo_points.values() if len(pts) > 0]
    mins = np.min(np.vstack(all_valid_points), axis=0)
    maxs = np.max(np.vstack(all_valid_points), axis=0)
    span = np.maximum(maxs - mins, 1e-12)
    ref_points_norm = (ref_points - mins) / span

    rows: list[dict] = []
    for _, row in work.iterrows():
        combo_name = str(row["combo"])
        points = combo_points.get(combo_name, np.empty((0, 3), dtype=float))
        igd_abs = _igd(ref_points, points)
        igd_norm = _igd(ref_points_norm, (points - mins) / span) if len(points) > 0 else np.nan
        rows.append(
            {
                "combo": combo_name,
                "sfh_k_token": row["sfh_k_token"],
                "mfh_k_token": row["mfh_k_token"],
                "sfh_k": row["sfh_k"],
                "mfh_k": row["mfh_k"],
                "num_points_raw": row.get("num_points_raw", np.nan),
                "num_points_pareto": row.get("num_points_pareto", np.nan),
                "hypervolume": row.get("hypervolume", np.nan),
                "reference_source": ref_source,
                "reference_combo": ref_combo,
                "reference_num_points": int(len(ref_points)),
                "igd_vs_ref": igd_abs,
                "igd_vs_ref_normalized": igd_norm,
                "is_reference_combo": bool(combo_name == ref_combo),
                "is_missing_points": bool(len(points) == 0),
            }
        )
    out = _sort_combo_df(pd.DataFrame(rows))
    return out, ref_source


def _select_reference_row(df: pd.DataFrame, allow_fallback: bool = False) -> tuple[pd.Series, str]:
    work = df.copy()
    work = work[work["hypervolume"].notna()]
    if work.empty:
        raise ValueError("No hypervolume rows available to select reference scenario.")

    ref_mask = (
        work["sfh_k_token"].astype(str).str.lower() == "reference"
    ) & (
        work["mfh_k_token"].astype(str).str.lower() == "reference"
    )
    if ref_mask.any():
        return work.loc[ref_mask].iloc[0], "reference/reference"

    if not allow_fallback:
        raise ValueError(
            "Missing true reference combo 'sfh_reference_mfh_reference' in post-processed combinations. "
            "Please ensure reference/reference is included in post-processing output."
        )

    # Optional fallback if explicit reference/reference is not present.
    fallback = work.copy()
    fallback["sfh_sort"] = fallback["sfh_k"].fillna(10**9)
    fallback["mfh_sort"] = fallback["mfh_k"].fillna(10**9)
    fallback = fallback.sort_values(["sfh_sort", "mfh_sort", "hypervolume"], ascending=[False, False, False])
    return fallback.iloc[0], "fallback_highest_available_k"


def _build_delta_vs_reference(df: pd.DataFrame, allow_fallback_reference: bool = False) -> tuple[pd.DataFrame, str]:
    work = df.copy()
    work = work[work["hypervolume"].notna()].copy()
    if work.empty:
        return pd.DataFrame(), "no_reference"

    ref_row, ref_source = _select_reference_row(work, allow_fallback=allow_fallback_reference)
    ref_combo = str(ref_row["combo"])
    ref_hv = float(ref_row["hypervolume"])

    work["reference_source"] = ref_source
    work["reference_combo"] = ref_combo
    work["reference_hv"] = ref_hv
    work["delta_hv_vs_ref"] = ref_hv - work["hypervolume"].astype(float)
    work["delta_hv_vs_ref_rel_pct"] = np.where(
        np.isclose(ref_hv, 0.0),
        np.nan,
        (work["delta_hv_vs_ref"] / ref_hv) * 100.0,
    )
    work["is_reference_combo"] = work["combo"].astype(str) == ref_combo
    work["is_worse_than_reference"] = work["delta_hv_vs_ref"] > 0
    work["is_better_than_reference"] = work["delta_hv_vs_ref"] < 0
    work["is_equal_to_reference"] = np.isclose(work["delta_hv_vs_ref"], 0.0)

    out_cols = [
        "combo",
        "sfh_k_token",
        "mfh_k_token",
        "sfh_k",
        "mfh_k",
        "hypervolume",
        "reference_source",
        "reference_combo",
        "reference_hv",
        "delta_hv_vs_ref",
        "delta_hv_vs_ref_rel_pct",
        "is_reference_combo",
        "is_worse_than_reference",
        "is_better_than_reference",
        "is_equal_to_reference",
    ]
    work = _sort_combo_df(work)
    return work[out_cols], ref_source


def _build_delta_vs_reference_matrix(delta_ref_df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    if delta_ref_df.empty:
        return pd.DataFrame()
    matrix = delta_ref_df.pivot(index="mfh_k_token", columns="sfh_k_token", values=value_col)

    def _token_order(token: str) -> int:
        if str(token).lower() == "reference":
            return 10**9
        return int(str(token)[1:])

    row_order = sorted(matrix.index.tolist(), key=_token_order)
    col_order = sorted(matrix.columns.tolist(), key=_token_order)
    matrix = matrix.reindex(index=row_order, columns=col_order)
    return matrix


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


def _save_csv_with_fallback(df: pd.DataFrame, preferred_path: Path, fallback_name: str) -> Path:
    preferred_path.parent.mkdir(parents=True, exist_ok=True)

    # First attempt: long-path aware write to preferred location.
    try:
        df.to_csv(_to_long_path(preferred_path), index=False)
        return preferred_path
    except (FileNotFoundError, OSError):
        pass

    # Second attempt: short filename in same directory.
    fallback_path = preferred_path.parent / fallback_name
    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_csv(_to_long_path(fallback_path), index=False)
        print(f"path fallback used: {preferred_path} -> {fallback_path}")
        return fallback_path
    except (FileNotFoundError, OSError):
        pass

    # Third attempt: short path root.
    short_root = Path(__file__).resolve().parent / "_hv_csv_outputs"
    short_root.mkdir(parents=True, exist_ok=True)
    short_path = short_root / fallback_name
    df.to_csv(_to_long_path(short_path), index=False)
    print(f"path fallback used: {preferred_path} -> {short_path}")
    return short_path


def _parse_date_from_post_process_name(name: str) -> tuple[int, int, int] | None:
    match = POST_PROCESS_ROOT_PATTERN.match(name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _token_to_k(token: str) -> int | None:
    if token == "reference":
        return None
    return int(token[1:])


def _resolve_ueu_dir(ueu: str, input_base_dir: Path) -> Path:
    candidate = Path(ueu)
    if candidate.is_dir():
        resolved = candidate.resolve()
    else:
        resolved = (input_base_dir / ueu).resolve()

    if not resolved.is_dir():
        raise FileNotFoundError(
            f"UEU directory not found: '{ueu}'. "
            f"Expected absolute path or folder below '{input_base_dir}'."
        )

    if not resolved.name.startswith("processed_bds_in_"):
        raise ValueError(
            f"Invalid UEU folder '{resolved.name}'. "
            "Expected a folder named like 'processed_bds_in_DENI...'."
        )
    return resolved


def _discover_post_process_roots_for_ueu(ueu_dir: Path) -> list[Path]:
    roots: list[Path] = []
    for candidate in sorted(ueu_dir.iterdir()):
        if not candidate.is_dir():
            continue
        if _parse_date_from_post_process_name(candidate.name) is None:
            continue
        roots.append(candidate)
    return roots


def _select_post_process_root(ueu_dir: Path, post_process_name: str | None) -> Path:
    if post_process_name:
        candidate = (ueu_dir / post_process_name).resolve()
        if not candidate.is_dir():
            raise FileNotFoundError(
                f"Requested post-process folder not found: {candidate}"
            )
        if _parse_date_from_post_process_name(candidate.name) is None:
            raise ValueError(
                f"Invalid post-process folder name '{candidate.name}'. "
                "Expected 'post_processed_dec_k_combinations_YYYY_MM_DD'."
            )
        return candidate

    roots = _discover_post_process_roots_for_ueu(ueu_dir)
    if not roots:
        raise FileNotFoundError(
            "No post-process folders found for UEU. "
            "Expected subfolders named 'post_processed_dec_k_combinations_YYYY_MM_DD'."
        )

    roots_sorted = sorted(
        roots,
        key=lambda p: (_parse_date_from_post_process_name(p.name), p.name),
    )
    return roots_sorted[-1]


def _discover_combo_dirs(post_process_root: Path) -> list[Path]:
    combo_dirs: list[Path] = []
    for child in sorted(post_process_root.iterdir()):
        if not child.is_dir():
            continue
        if COMBO_PATTERN.match(child.name):
            combo_dirs.append(child)
    return combo_dirs


def _parse_combo_name(name: str) -> dict | None:
    match = COMBO_PATTERN.match(name)
    if not match:
        return None
    sfh_token = match.group(1)
    mfh_token = match.group(2)
    return {
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


def _compute_reference_point(points: np.ndarray, margin: float = REFERENCE_MARGIN) -> np.ndarray:
    mins = np.min(points, axis=0)
    maxs = np.max(points, axis=0)
    span = np.maximum(maxs - mins, 1e-9)
    return maxs + margin * span


def _hypervolume_2d(points: np.ndarray, ref: np.ndarray) -> float:
    if len(points) == 0:
        return 0.0

    valid = np.all(np.isfinite(points), axis=1)
    valid &= np.all(points <= ref, axis=1)
    pts = points[valid]
    if len(pts) == 0:
        return 0.0

    order = np.argsort(pts[:, 0], kind="mergesort")
    pts = pts[order]

    area = 0.0
    z_limit = ref[1]
    for y, z in pts:
        if z >= z_limit:
            continue
        area += max(ref[0] - y, 0.0) * max(z_limit - z, 0.0)
        z_limit = z
    return float(area)


def _hypervolume_3d(points: np.ndarray, ref: np.ndarray) -> float:
    if len(points) == 0:
        return 0.0

    valid = np.all(np.isfinite(points), axis=1)
    valid &= np.all(points <= ref, axis=1)
    pts = points[valid]
    if len(pts) == 0:
        return 0.0

    x_breaks = np.unique(np.concatenate([pts[:, 0], np.array([ref[0]])]))
    x_breaks.sort()

    hv = 0.0
    for idx in range(len(x_breaks) - 1):
        left = x_breaks[idx]
        right = x_breaks[idx + 1]
        width = right - left
        if width <= 0:
            continue

        active = pts[pts[:, 0] <= left + 1e-12]
        if len(active) == 0:
            continue

        yz_area = _hypervolume_2d(active[:, 1:], ref[1:])
        hv += width * yz_area
    return float(hv)


def _build_delta_over_sfh(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work = work[work["sfh_k"].notna() & work["hypervolume"].notna()]
    if work.empty:
        return pd.DataFrame(columns=DELTA_SFH_COLUMNS)

    rows: list[dict] = []
    for _, group in work.groupby("mfh_k_token", dropna=False):
        ordered = group.sort_values("sfh_k")
        for idx in range(1, len(ordered)):
            prev_row = ordered.iloc[idx - 1]
            curr_row = ordered.iloc[idx]
            prev_hv = float(prev_row["hypervolume"])
            curr_hv = float(curr_row["hypervolume"])
            delta = curr_hv - prev_hv
            delta_rel = np.nan if np.isclose(prev_hv, 0.0) else (delta / prev_hv) * 100.0
            rows.append(
                {
                    "mfh_k_token": curr_row["mfh_k_token"],
                    "mfh_k": curr_row["mfh_k"],
                    "sfh_k_prev": int(prev_row["sfh_k"]),
                    "sfh_k_curr": int(curr_row["sfh_k"]),
                    "sfh_k_step": int(curr_row["sfh_k"] - prev_row["sfh_k"]),
                    "is_k_plus_1": bool(int(curr_row["sfh_k"] - prev_row["sfh_k"]) == 1),
                    "combo_prev": prev_row["combo"],
                    "combo_curr": curr_row["combo"],
                    "hv_prev": prev_hv,
                    "hv_curr": curr_hv,
                    "delta_hv": delta,
                    "delta_hv_rel_pct": delta_rel,
                    "stagnates_non_positive": bool(delta <= 0.0),
                }
            )
    return pd.DataFrame(rows, columns=DELTA_SFH_COLUMNS)


def _build_delta_over_mfh(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work = work[work["mfh_k"].notna() & work["hypervolume"].notna()]
    if work.empty:
        return pd.DataFrame(columns=DELTA_MFH_COLUMNS)

    rows: list[dict] = []
    for _, group in work.groupby("sfh_k_token", dropna=False):
        ordered = group.sort_values("mfh_k")
        for idx in range(1, len(ordered)):
            prev_row = ordered.iloc[idx - 1]
            curr_row = ordered.iloc[idx]
            prev_hv = float(prev_row["hypervolume"])
            curr_hv = float(curr_row["hypervolume"])
            delta = curr_hv - prev_hv
            delta_rel = np.nan if np.isclose(prev_hv, 0.0) else (delta / prev_hv) * 100.0
            rows.append(
                {
                    "sfh_k_token": curr_row["sfh_k_token"],
                    "sfh_k": curr_row["sfh_k"],
                    "mfh_k_prev": int(prev_row["mfh_k"]),
                    "mfh_k_curr": int(curr_row["mfh_k"]),
                    "mfh_k_step": int(curr_row["mfh_k"] - prev_row["mfh_k"]),
                    "is_k_plus_1": bool(int(curr_row["mfh_k"] - prev_row["mfh_k"]) == 1),
                    "combo_prev": prev_row["combo"],
                    "combo_curr": curr_row["combo"],
                    "hv_prev": prev_hv,
                    "hv_curr": curr_hv,
                    "delta_hv": delta,
                    "delta_hv_rel_pct": delta_rel,
                    "stagnates_non_positive": bool(delta <= 0.0),
                }
            )
    return pd.DataFrame(rows, columns=DELTA_MFH_COLUMNS)


def _sort_combo_df(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["sfh_sort"] = work["sfh_k"].fillna(10**9)
    work["mfh_sort"] = work["mfh_k"].fillna(10**9)
    work = work.sort_values(["sfh_sort", "mfh_sort", "combo"]).drop(columns=["sfh_sort", "mfh_sort"])
    return work.reset_index(drop=True)


def _analyze_single_post_process_root(post_process_root: Path, output_root: Path) -> None:
    combo_dirs = _discover_combo_dirs(post_process_root)
    if not combo_dirs:
        print(f"skip {post_process_root}: no combo folders found")
        return

    combo_points: dict[str, np.ndarray] = {}
    rows: list[dict] = []
    all_points: list[np.ndarray] = []

    for combo_dir in combo_dirs:
        combo_name = combo_dir.name
        parsed = _parse_combo_name(combo_name)
        if parsed is None:
            continue
        combined_front_path = combo_dir / COMBINED_FRONT_FILENAME
        if not _path_exists(combined_front_path):
            rows.append(
                {
                    "combo": combo_name,
                    **parsed,
                    "combined_front_path": str(combined_front_path),
                    "num_points_raw": 0,
                    "num_points_pareto": 0,
                    "hypervolume": np.nan,
                    "status": "missing_combined_front",
                }
            )
            continue

        points = _extract_points_from_combined_front(combined_front_path)
        combo_points[combo_name] = points
        if len(points):
            all_points.append(points)

        rows.append(
            {
                "combo": combo_name,
                **parsed,
                "combined_front_path": str(combined_front_path),
                "num_points_raw": int(len(points)),
                "num_points_pareto": int(len(points)),
                "status": "ok" if len(points) else "empty_front",
            }
        )

    if not all_points:
        combo_df = _sort_combo_df(pd.DataFrame(rows))
        output_root.mkdir(parents=True, exist_ok=True)
        combo_csv = output_root / "hypervolume_by_combo.csv"
        saved_combo_csv = _save_csv_with_fallback(combo_df, combo_csv, "hv_by_combo.csv")
        print(f"saved: {saved_combo_csv} (no points for HV calculation)")
        return
    if False:
        reference_point = _compute_reference_point(np.vstack(all_points), margin=REFERENCE_MARGIN)
        for row in rows:
            combo_name = row["combo"]
            points = combo_points.get(combo_name)
            if points is None or len(points) == 0:
                row["hypervolume"] = np.nan
                continue
            row["hypervolume"] = _hypervolume_3d(points, reference_point)
        for row in rows:
            row["ref_co2"] = float(reference_point[0])
            row["ref_peak"] = float(reference_point[1])
            row["ref_totex"] = float(reference_point[2])
    else:
        all_points_array = np.vstack(all_points)

        # Objective-wise normalization based on the union of all approximation sets
        hv_mins = np.min(all_points_array, axis=0)
        hv_maxs = np.max(all_points_array, axis=0)
        hv_span = np.maximum(hv_maxs - hv_mins, 1e-12)

        # Normalize all combo points
        combo_points_norm: dict[str, np.ndarray] = {}
        for combo_name, points in combo_points.items():
            if len(points) == 0:
                combo_points_norm[combo_name] = np.empty((0, 3), dtype=float)
            else:
                combo_points_norm[combo_name] = (points - hv_mins) / hv_span

        # Reference point in normalized objective space.
        # Since the normalized objective values range from 0 to 1,
        # the previous 5% margin corresponds to 1.05 in each dimension.
        reference_point = np.ones(3, dtype=float) + REFERENCE_MARGIN

        for row in rows:
            combo_name = row["combo"]
            points_norm = combo_points_norm.get(combo_name)

            if points_norm is None or len(points_norm) == 0:
                row["hypervolume"] = np.nan
                continue

            row["hypervolume"] = _hypervolume_3d(points_norm, reference_point)

        for row in rows:
            row["ref_co2"] = float(reference_point[0])
            row["ref_peak"] = float(reference_point[1])
            row["ref_totex"] = float(reference_point[2])

            # Optional, but useful for documentation/debugging
            row["norm_min_co2"] = float(hv_mins[0])
            row["norm_min_peak"] = float(hv_mins[1])
            row["norm_min_totex"] = float(hv_mins[2])
            row["norm_max_co2"] = float(hv_maxs[0])
            row["norm_max_peak"] = float(hv_maxs[1])
            row["norm_max_totex"] = float(hv_maxs[2])
    combo_df = _sort_combo_df(pd.DataFrame(rows))
    delta_sfh_df = _build_delta_over_sfh(combo_df)
    delta_mfh_df = _build_delta_over_mfh(combo_df)
    delta_ref_df, ref_source = _build_delta_vs_reference(combo_df, allow_fallback_reference=False)
    delta_ref_matrix_abs = _build_delta_vs_reference_matrix(delta_ref_df, "delta_hv_vs_ref")
    delta_ref_matrix_rel = _build_delta_vs_reference_matrix(delta_ref_df, "delta_hv_vs_ref_rel_pct")
    igd_ref_df, igd_ref_source = _build_igd_vs_reference(combo_df, combo_points, allow_fallback_reference=False)
    igd_ref_matrix_abs = _build_delta_vs_reference_matrix(igd_ref_df, "igd_vs_ref")
    igd_ref_matrix_norm = _build_delta_vs_reference_matrix(igd_ref_df, "igd_vs_ref_normalized")

    output_root.mkdir(parents=True, exist_ok=True)
    combo_csv = output_root / "hypervolume_by_combo.csv"
    delta_sfh_csv = output_root / "delta_hypervolume_sfh_over_k.csv"
    delta_mfh_csv = output_root / "delta_hypervolume_mfh_over_k.csv"
    delta_ref_csv = output_root / "delta_hypervolume_vs_reference.csv"
    delta_ref_matrix_abs_csv = output_root / "delta_hypervolume_vs_reference_matrix_abs.csv"
    delta_ref_matrix_rel_csv = output_root / "delta_hypervolume_vs_reference_matrix_rel_pct.csv"
    igd_ref_csv = output_root / "igd_vs_reference.csv"
    igd_ref_matrix_abs_csv = output_root / "igd_vs_reference_matrix_abs.csv"
    igd_ref_matrix_norm_csv = output_root / "igd_vs_reference_matrix_normalized.csv"

    saved_combo_csv = _save_csv_with_fallback(combo_df, combo_csv, "hv_by_combo.csv")
    saved_delta_sfh_csv = _save_csv_with_fallback(delta_sfh_df, delta_sfh_csv, "delta_hv_sfh.csv")
    saved_delta_mfh_csv = _save_csv_with_fallback(delta_mfh_df, delta_mfh_csv, "delta_hv_mfh.csv")
    saved_delta_ref_csv = _save_csv_with_fallback(delta_ref_df, delta_ref_csv, "delta_hv_vs_ref.csv")
    saved_delta_ref_matrix_abs_csv = _save_csv_with_fallback(
        delta_ref_matrix_abs, delta_ref_matrix_abs_csv, "delta_hv_vs_ref_matrix_abs.csv"
    )
    saved_delta_ref_matrix_rel_csv = _save_csv_with_fallback(
        delta_ref_matrix_rel, delta_ref_matrix_rel_csv, "delta_hv_vs_ref_matrix_rel.csv"
    )
    saved_igd_ref_csv = _save_csv_with_fallback(igd_ref_df, igd_ref_csv, "igd_vs_ref.csv")
    saved_igd_ref_matrix_abs_csv = _save_csv_with_fallback(
        igd_ref_matrix_abs, igd_ref_matrix_abs_csv, "igd_vs_ref_matrix_abs.csv"
    )
    saved_igd_ref_matrix_norm_csv = _save_csv_with_fallback(
        igd_ref_matrix_norm, igd_ref_matrix_norm_csv, "igd_vs_ref_matrix_norm.csv"
    )

    print(f"saved: {saved_combo_csv}")
    print(f"saved: {saved_delta_sfh_csv}")
    print(f"saved: {saved_delta_mfh_csv}")
    print(f"saved: {saved_delta_ref_csv}")
    print(f"saved: {saved_delta_ref_matrix_abs_csv}")
    print(f"saved: {saved_delta_ref_matrix_rel_csv}")
    print(f"saved: {saved_igd_ref_csv}")
    print(f"saved: {saved_igd_ref_matrix_abs_csv}")
    print(f"saved: {saved_igd_ref_matrix_norm_csv}")
    print(f"reference_source: {ref_source}")
    print(f"igd_reference_source: {igd_ref_source}")


def _expand_ueu_args(raw_values: list[str]) -> list[str]:
    expanded: list[str] = []
    for value in raw_values:
        for token in str(value).split(","):
            token = token.strip()
            if token:
                expanded.append(token)

    # Keep order, remove duplicates.
    deduped: list[str] = []
    seen: set[str] = set()
    for token in expanded:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def main() -> None:
    input_base_dir = INPUT_BASE_DIR.resolve()
    ueu_inputs = _expand_ueu_args(UEU_CASES_TO_PROCESS)
    if not ueu_inputs:
        raise SystemExit(
            "No UEU provided. Define at least one entry in UEU_CASES_TO_PROCESS."
        )

    failures: list[tuple[str, str]] = []
    for ueu_input in ueu_inputs:
        try:
            ueu_dir = _resolve_ueu_dir(ueu_input, input_base_dir=input_base_dir)
            post_process_root = _select_post_process_root(ueu_dir, POST_PROCESS_NAME)
            ueu_case = ueu_dir.name
            output_root = OUTPUT_BASE_DIR / ueu_case / post_process_root.name

            print(f"processing UEU: {ueu_case}")
            print(f"input root: {post_process_root}")
            print(f"output root: {output_root}")
            _analyze_single_post_process_root(post_process_root, output_root)
        except Exception as exc:
            failures.append((ueu_input, str(exc)))
            print(f"ERROR for UEU '{ueu_input}': {exc}")

    if failures:
        print("\nFailed UEUs:")
        for ueu_input, msg in failures:
            print(f"  - {ueu_input}: {msg}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
