import argparse
import pickle
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


COMBO_PATTERN = re.compile(r"^sfh_(k\d+|reference)_mfh_(k\d+|reference)$")
DEFAULT_UEU_CASE = "processed_bds_in_DENI03403000SEC5658"
POST_PROCESS_ROOT_PATTERN = "post_processed_dec_k_combinations_*"
DEFAULT_REFERENCE_MARGIN = 0.05


def _parse_date_suffix(folder_name: str) -> Tuple[int, int, int] | None:
    match = re.search(r"(\d{4})_(\d{2})_(\d{2})$", folder_name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _is_reference_token(token: str) -> bool:
    return str(token).lower() == "reference"


def _token_to_k(token: str) -> Optional[int]:
    if _is_reference_token(token):
        return None
    return int(token[1:])


def _token_sort_value(token: str) -> int:
    k_value = _token_to_k(token)
    if k_value is None:
        return 10**9
    return int(k_value)


def _token_label(token: str) -> str:
    if _is_reference_token(token):
        return "reference"
    return str(int(token[1:]))


def _discover_post_process_root(base_dir: Path, ueu_case: str) -> Path:
    cluster_root = Path(str(ueu_case)) if Path(str(ueu_case)).is_absolute() else (base_dir / ueu_case)
    if not cluster_root.exists():
        raise FileNotFoundError(f"UEU folder not found: {cluster_root}")

    candidates = [p for p in sorted(cluster_root.glob(POST_PROCESS_ROOT_PATTERN)) if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No post-process folder found below: {cluster_root}")

    dated = [p for p in candidates if _parse_date_suffix(p.name) is not None]
    if dated:
        candidates = sorted(dated, key=lambda p: _parse_date_suffix(p.name))
    return candidates[-1]


def _parse_combo_name(combo_name: str) -> Optional[Dict[str, Any]]:
    match = COMBO_PATTERN.match(combo_name)
    if not match:
        return None
    sfh_token = match.group(1)
    mfh_token = match.group(2)
    return {
        "combo": combo_name,
        "sfh_k_token": sfh_token,
        "mfh_k_token": mfh_token,
        "sfh_k": _token_to_k(sfh_token),
        "mfh_k": _token_to_k(mfh_token),
    }


def _extract_combined_front_payload(path: Path) -> List[Dict[str, Any]]:
    with open(path, "rb") as fh:
        data = pickle.load(fh)

    if isinstance(data, list):
        if data and all(isinstance(item, dict) for item in data):
            return data
        if len(data) >= 3 and isinstance(data[2], list):
            if all(isinstance(item, dict) for item in data[2]):
                return data[2]

    if isinstance(data, tuple):
        if len(data) >= 3 and isinstance(data[2], list):
            if all(isinstance(item, dict) for item in data[2]):
                return data[2]

    if isinstance(data, dict):
        maybe = data.get("combined_front")
        if isinstance(maybe, list) and all(isinstance(item, dict) for item in maybe):
            return maybe

    raise ValueError(f"Unsupported combined-front payload in {path}")


def _extract_points(front: Iterable[Dict[str, Any]]) -> np.ndarray:
    points: List[Tuple[float, float, float]] = []
    for rec in front:
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


def _dominates(a: np.ndarray, b: np.ndarray, tol: float = 1e-12) -> bool:
    return np.all(a <= b + tol) and np.any(a < b - tol)


def _pareto_prune(points: np.ndarray, tol: float = 1e-12) -> np.ndarray:
    if len(points) <= 1:
        return points
    keep = np.ones(len(points), dtype=bool)
    for i in range(len(points)):
        if not keep[i]:
            continue
        for j in range(len(points)):
            if i == j or not keep[j]:
                continue
            if _dominates(points[j], points[i], tol=tol):
                keep[i] = False
                break
    return points[keep]


def _compute_reference_point(points: np.ndarray, margin: float) -> np.ndarray:
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

    pts = _pareto_prune(pts)
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

    pts = _pareto_prune(pts)
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

        hv += width * _hypervolume_2d(active[:, 1:], ref[1:])
    return float(hv)


def _sort_combo_df(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["sfh_sort"] = work["sfh_k_token"].map(_token_sort_value)
    work["mfh_sort"] = work["mfh_k_token"].map(_token_sort_value)
    work = work.sort_values(["sfh_sort", "mfh_sort", "combo"]).drop(columns=["sfh_sort", "mfh_sort"])
    return work.reset_index(drop=True)


def _build_pairwise_delta_df(combo_df: pd.DataFrame) -> pd.DataFrame:
    hv_map = {row["combo"]: float(row["hypervolume"]) for _, row in combo_df.iterrows() if pd.notna(row["hypervolume"])}
    combo_names = list(combo_df["combo"].tolist())

    rows: List[Dict[str, Any]] = []
    for combo_from in combo_names:
        hv_from = hv_map.get(combo_from)
        if hv_from is None:
            continue
        for combo_to in combo_names:
            hv_to = hv_map.get(combo_to)
            if hv_to is None:
                continue
            delta = hv_to - hv_from
            delta_rel = np.nan if np.isclose(hv_from, 0.0) else (delta / hv_from) * 100.0
            rows.append(
                {
                    "combo_from": combo_from,
                    "combo_to": combo_to,
                    "hv_from": hv_from,
                    "hv_to": hv_to,
                    "delta_hv": delta,
                    "delta_hv_rel_pct": delta_rel,
                }
            )
    return pd.DataFrame(rows)


def _build_raise_delta_df(combo_df: pd.DataFrame, along: str) -> pd.DataFrame:
    if along not in {"mfh", "sfh"}:
        raise ValueError("along must be 'mfh' or 'sfh'")

    work = combo_df.copy()
    work = work[pd.notna(work["hypervolume"])].copy()
    if work.empty:
        return pd.DataFrame()

    if along == "mfh":
        group_col = "sfh_k_token"
        varying_col = "mfh_k_token"
    else:
        group_col = "mfh_k_token"
        varying_col = "sfh_k_token"

    rows: List[Dict[str, Any]] = []
    for group_value, group_df in work.groupby(group_col, dropna=False):
        ordered = group_df.sort_values(varying_col, key=lambda s: s.map(_token_sort_value), ascending=True)
        ordered = ordered.reset_index(drop=True)
        for from_idx in range(len(ordered) - 1):
            from_row = ordered.iloc[from_idx]
            for to_idx in range(from_idx + 1, len(ordered)):
                to_row = ordered.iloc[to_idx]
                hv_from = float(from_row["hypervolume"])
                hv_to = float(to_row["hypervolume"])
                delta = hv_to - hv_from
                delta_rel = np.nan if np.isclose(hv_from, 0.0) else (delta / hv_from) * 100.0
                rows.append(
                    {
                        "along": along,
                        group_col: group_value,
                        f"{varying_col}_from": from_row[varying_col],
                        f"{varying_col}_to": to_row[varying_col],
                        "combo_from": from_row["combo"],
                        "combo_to": to_row["combo"],
                        "hv_from": hv_from,
                        "hv_to": hv_to,
                        "delta_hv": delta,
                        "delta_hv_rel_pct": delta_rel,
                    }
                )
    return pd.DataFrame(rows)


def _build_delta_grid_from_origin(
    combo_df: pd.DataFrame,
    origin_sfh_token: str = "k01",
    origin_mfh_token: str = "k01",
) -> pd.DataFrame:
    work = combo_df.copy()
    work = work[pd.notna(work["hypervolume"])].copy()
    if work.empty:
        return pd.DataFrame()

    origin_mask = (
        work["sfh_k_token"].astype(str).str.lower() == str(origin_sfh_token).lower()
    ) & (
        work["mfh_k_token"].astype(str).str.lower() == str(origin_mfh_token).lower()
    )
    if not origin_mask.any():
        work_sorted = work.sort_values(
            ["sfh_k_token", "mfh_k_token"],
            key=lambda s: s.map(_token_sort_value),
            ascending=True,
        )
        origin_row = work_sorted.iloc[0]
        print(
            f"Requested origin (sfh={origin_sfh_token}, mfh={origin_mfh_token}) not found. "
            f"Using smallest available combo: {origin_row['combo']}"
        )
    else:
        origin_row = work[origin_mask].iloc[0]

    origin_combo = str(origin_row["combo"])
    origin_hv = float(origin_row["hypervolume"])

    work["origin_combo"] = origin_combo
    work["origin_hv"] = origin_hv
    work["delta_hv_from_origin"] = work["hypervolume"].astype(float) - origin_hv
    work["delta_hv_from_origin_rel_pct"] = np.where(
        np.isclose(origin_hv, 0.0),
        np.nan,
        (work["delta_hv_from_origin"] / origin_hv) * 100.0,
    )
    work = _sort_combo_df(work)
    return work.reset_index(drop=True)


def _plot_delta_hv_3d_grid(
    delta_grid_df: pd.DataFrame,
    output_path: Path,
    reverse_x: bool = False,
    reverse_z: bool = False,
) -> None:
    if delta_grid_df.empty:
        return

    plot_df = delta_grid_df.copy()
    plot_df = plot_df[pd.notna(plot_df["delta_hv_from_origin"])].copy()
    if plot_df.empty:
        return

    sfh_tokens = sorted(plot_df["sfh_k_token"].astype(str).unique(), key=_token_sort_value)
    mfh_tokens = sorted(plot_df["mfh_k_token"].astype(str).unique(), key=_token_sort_value)
    sfh_pos_map = {token: idx for idx, token in enumerate(sfh_tokens)}
    mfh_pos_map = {token: idx for idx, token in enumerate(mfh_tokens)}

    plot_df["x_sfh_pos"] = plot_df["sfh_k_token"].astype(str).map(sfh_pos_map).astype(float)
    plot_df["z_mfh_pos"] = plot_df["mfh_k_token"].astype(str).map(mfh_pos_map).astype(float)

    x = plot_df["x_sfh_pos"].to_numpy(dtype=float)
    y = plot_df["delta_hv_from_origin"].to_numpy(dtype=float)
    z = plot_df["z_mfh_pos"].to_numpy(dtype=float)
    c = y

    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(111, projection="3d")
    sc = ax.scatter(x, y, z, c=c, cmap="viridis", s=55, alpha=0.95)

    origin_combo = str(plot_df["origin_combo"].iloc[0]) if "origin_combo" in plot_df.columns else "unknown"
    ax.set_title(f"Delta hypervolume from origin ({origin_combo})")
    ax.set_xlabel("SFH k")
    ax.set_ylabel("Delta hypervolume")
    ax.set_zlabel("MFH k")

    ax.set_xticks(list(sfh_pos_map.values()))
    ax.set_xticklabels([_token_label(t) for t in sfh_tokens], rotation=0)
    ax.set_zticks(list(mfh_pos_map.values()))
    ax.set_zticklabels([_token_label(t) for t in mfh_tokens], rotation=0)

    if reverse_x:
        ax.set_xlim(max(sfh_pos_map.values()), min(sfh_pos_map.values()))
    else:
        ax.set_xlim(min(sfh_pos_map.values()), max(sfh_pos_map.values()))

    if reverse_z:
        ax.set_zlim(max(mfh_pos_map.values()), min(mfh_pos_map.values()))
    else:
        ax.set_zlim(min(mfh_pos_map.values()), max(mfh_pos_map.values()))

    cbar = fig.colorbar(sc, ax=ax, pad=0.15, shrink=0.75)
    cbar.set_label("Delta hypervolume")
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def run_analysis(
    post_process_root: Path,
    output_dir: Path,
    reference_margin: float,
    origin_sfh_token: str,
    origin_mfh_token: str,
    reverse_x: bool,
    reverse_z: bool,
) -> None:
    combo_dirs = [p for p in sorted(post_process_root.iterdir()) if p.is_dir() and COMBO_PATTERN.match(p.name)]
    if not combo_dirs:
        raise FileNotFoundError(f"No combo folders found in: {post_process_root}")

    rows: List[Dict[str, Any]] = []
    combo_points: Dict[str, np.ndarray] = {}
    all_points: List[np.ndarray] = []

    for combo_dir in combo_dirs:
        parsed = _parse_combo_name(combo_dir.name)
        if parsed is None:
            continue

        combined_front_path = combo_dir / "combined_front.pkl"
        if not combined_front_path.exists():
            rows.append(
                {
                    **parsed,
                    "combined_front_path": str(combined_front_path),
                    "num_points_raw": 0,
                    "num_points_pareto": 0,
                    "hypervolume": np.nan,
                    "status": "missing_combined_front",
                }
            )
            continue

        try:
            front = _extract_combined_front_payload(combined_front_path)
            points = _extract_points(front)
            pareto_points = _pareto_prune(points) if len(points) else points
        except Exception as exc:
            rows.append(
                {
                    **parsed,
                    "combined_front_path": str(combined_front_path),
                    "num_points_raw": 0,
                    "num_points_pareto": 0,
                    "hypervolume": np.nan,
                    "status": f"load_error: {exc}",
                }
            )
            continue

        combo_points[combo_dir.name] = pareto_points
        if len(pareto_points):
            all_points.append(pareto_points)

        rows.append(
            {
                **parsed,
                "combined_front_path": str(combined_front_path),
                "num_points_raw": int(len(points)),
                "num_points_pareto": int(len(pareto_points)),
                "status": "ok" if len(pareto_points) else "empty_front",
            }
        )

    combo_df = pd.DataFrame(rows)
    if combo_df.empty:
        raise RuntimeError(f"No valid combo rows found in: {post_process_root}")

    if all_points:
        ref = _compute_reference_point(np.vstack(all_points), margin=reference_margin)
        for idx, row in combo_df.iterrows():
            combo_name = row["combo"]
            points = combo_points.get(combo_name)
            if points is None or len(points) == 0:
                combo_df.loc[idx, "hypervolume"] = np.nan
                continue
            combo_df.loc[idx, "hypervolume"] = _hypervolume_3d(points, ref)
        combo_df["ref_co2"] = float(ref[0])
        combo_df["ref_peak"] = float(ref[1])
        combo_df["ref_totex"] = float(ref[2])
    else:
        combo_df["hypervolume"] = np.nan
        combo_df["ref_co2"] = np.nan
        combo_df["ref_peak"] = np.nan
        combo_df["ref_totex"] = np.nan

    combo_df = _sort_combo_df(combo_df)
    pairwise_df = _build_pairwise_delta_df(combo_df)
    mfh_raise_df = _build_raise_delta_df(combo_df, along="mfh")
    sfh_raise_df = _build_raise_delta_df(combo_df, along="sfh")
    delta_grid_df = _build_delta_grid_from_origin(
        combo_df,
        origin_sfh_token=origin_sfh_token,
        origin_mfh_token=origin_mfh_token,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    combo_csv = output_dir / "hypervolume_by_combo.csv"
    pairwise_csv = output_dir / "delta_hypervolume_pairwise.csv"
    mfh_raise_csv = output_dir / "delta_hypervolume_raise_mfh.csv"
    sfh_raise_csv = output_dir / "delta_hypervolume_raise_sfh.csv"
    delta_grid_csv = output_dir / "delta_hypervolume_from_origin_grid.csv"
    matrix_csv = output_dir / "delta_hypervolume_matrix.csv"
    plot_png = output_dir / "delta_hypervolume_3d_sfh_x_mfh_z_from_origin.png"

    combo_df.to_csv(combo_csv, index=False)
    pairwise_df.to_csv(pairwise_csv, index=False)
    mfh_raise_df.to_csv(mfh_raise_csv, index=False)
    sfh_raise_df.to_csv(sfh_raise_csv, index=False)
    delta_grid_df.to_csv(delta_grid_csv, index=False)

    if not pairwise_df.empty:
        matrix = pairwise_df.pivot(index="combo_from", columns="combo_to", values="delta_hv")
        matrix = matrix.reindex(index=combo_df["combo"].tolist(), columns=combo_df["combo"].tolist())
        matrix.to_csv(matrix_csv)
    else:
        pd.DataFrame().to_csv(matrix_csv, index=False)

    _plot_delta_hv_3d_grid(delta_grid_df, plot_png, reverse_x=reverse_x, reverse_z=reverse_z)

    print(f"Post-process root: {post_process_root}")
    print(f"Output dir: {output_dir}")
    print("Assumption: combined_front is a 3-objective front (co2, peak, totex), all minimized.")
    print(
        f"Directional delta logic: "
        f"for each fixed SFH compute from mfh_kXX -> all higher mfh_kYY; "
        f"for each fixed MFH compute from sfh_kXX -> all higher sfh_kYY."
    )
    print(f"saved: {combo_csv}")
    print(f"saved: {pairwise_csv}")
    print(f"saved: {mfh_raise_csv}")
    print(f"saved: {sfh_raise_csv}")
    print(f"saved: {delta_grid_csv}")
    print(f"saved: {matrix_csv}")
    print(f"saved: {plot_png}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate 3D hypervolume and delta-hypervolume across decentralized SFH/MFH combinations."
    )
    parser.add_argument(
        "--post-process-root",
        type=str,
        default=None,
        help="Folder containing combo subfolders named like sfh_k01_mfh_k01.",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=str(Path(__file__).resolve().parent),
        help="Base directory containing UEU folders (used when --post-process-root is not set).",
    )
    parser.add_argument(
        "--ueu-case",
        type=str,
        default=DEFAULT_UEU_CASE,
        help="UEU folder name or absolute UEU path (used when --post-process-root is not set).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output folder for CSV files. Default: <post_process_root>/hypervolume_analysis",
    )
    parser.add_argument(
        "--reference-margin",
        type=float,
        default=DEFAULT_REFERENCE_MARGIN,
        help="Reference point margin above global max per objective.",
    )
    parser.add_argument(
        "--origin-sfh-token",
        type=str,
        default="k01",
        help="Origin SFH token for grid delta, e.g. k01 or reference.",
    )
    parser.add_argument(
        "--origin-mfh-token",
        type=str,
        default="k01",
        help="Origin MFH token for grid delta, e.g. k01 or reference.",
    )
    parser.add_argument(
        "--reverse-x",
        action="store_true",
        help="Reverse SFH order on x-axis (high->low).",
    )
    parser.add_argument(
        "--reverse-z",
        action="store_true",
        help="Reverse MFH order on z-axis (high->low).",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.reference_margin < 0:
        raise ValueError("--reference-margin must be >= 0")

    if args.post_process_root:
        post_process_root = Path(args.post_process_root)
    else:
        post_process_root = _discover_post_process_root(Path(args.base_dir), args.ueu_case)

    if not post_process_root.exists():
        raise FileNotFoundError(f"post-process root not found: {post_process_root}")
    if not post_process_root.is_dir():
        raise NotADirectoryError(f"post-process root is not a directory: {post_process_root}")

    output_dir = Path(args.output_dir) if args.output_dir else (post_process_root / "hypervolume_analysis")
    run_analysis(
        post_process_root=post_process_root,
        output_dir=output_dir,
        reference_margin=float(args.reference_margin),
        origin_sfh_token=str(args.origin_sfh_token),
        origin_mfh_token=str(args.origin_mfh_token),
        reverse_x=bool(args.reverse_x),
        reverse_z=bool(args.reverse_z),
    )


if __name__ == "__main__":
    main()
