import argparse
import csv
import math
import os
import pickle
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from oemof.thermal_building_model.helpers.pareto_optimal_help_functions import (  # noqa: E402
    combine_all_buildings,
    pareto_prune_points,
)


DEFAULT_BUILDING_DICT = Path(
    "M:/04_ArchivMA/Hillen Maximilian/Veröffentlichungen/UEU/"
    "processed_bds_in_DENI03403000SEC5658/"
    "post_processed_dec_k_combinations_2026_07_07/"
    "sfh_k06_mfh_k01/building_dict.pkl"
)
DEFAULT_OUTPUT_ROOT = SCRIPT_DIR / "pareto_recombination_parameter_sweep_5658"
REFURBISHMENT_STRATEGIES = [
    "no_refurbishment",
    "usual_refurbishment",
    "advanced_refurbishment",
    "GEG_standard",
]
OBJECTIVE_KEYS = ("co2", "peak", "totex")


@dataclass(frozen=True)
class SweepVariant:
    name: str
    eps_each: Tuple[float, float, float]
    eps_merge: Tuple[float, float, float]
    cap: int
    description: str


CAP_VALUES = [250, 500, 1000, 2000, 4000, 8000]


def _variant_name(family: str, cap: int) -> str:
    if family == "strict" and cap in {4000, 8000}:
        return f"paper_strict_cap{cap}"
    if family == "baseline" and cap == 2000:
        return "paper_baseline_cap2000"
    if family == "relaxed" and cap == 500:
        return "paper_relaxed_cap500"
    if family == "relaxed":
        return f"relaxed_bucket_cap{cap}"
    return f"{family}_cap{cap}"


VARIANTS = [
    SweepVariant(
        _variant_name("strict", cap),
        (0.001, 0.001, 0.001),
        (0.004, 0.004, 0.004),
        cap,
        f"Strict archive buckets with cap {cap}.",
    )
    for cap in CAP_VALUES
] + [
    SweepVariant(
        _variant_name("baseline", cap),
        (0.002, 0.002, 0.002),
        (0.008, 0.008, 0.008),
        cap,
        f"Baseline archive buckets with cap {cap}.",
    )
    for cap in CAP_VALUES
] + [
    SweepVariant(
        _variant_name("relaxed", cap),
        (0.004, 0.004, 0.004),
        (0.016, 0.016, 0.016),
        cap,
        f"Relaxed archive buckets with cap {cap}.",
    )
    for cap in CAP_VALUES
] + [
    SweepVariant(
        _variant_name("very_relaxed", cap),
        (0.008, 0.008, 0.008),
        (0.032, 0.032, 0.032),
        cap,
        f"Very relaxed archive buckets with cap {cap}.",
    )
    for cap in CAP_VALUES
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


def _mkdir(path: Path) -> None:
    Path(_to_long_path(path)).mkdir(parents=True, exist_ok=True)


def _load_pickle(path: Path) -> Any:
    with open(_to_long_path(path), "rb") as fh:
        return pickle.load(fh)


def _save_pickle(path: Path, payload: Any) -> None:
    _mkdir(path.parent)
    with open(_to_long_path(path), "wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)


def _write_text(path: Path, text: str) -> None:
    _mkdir(path.parent)
    with open(_to_long_path(path), "w", encoding="utf-8") as fh:
        fh.write(text)


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    _mkdir(path.parent)
    if not rows:
        return
    columns = list(rows[0].keys())
    with open(_to_long_path(path), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _objectives(record: Dict[str, Any]) -> Tuple[float, float, float]:
    return tuple(float(record[key]) for key in OBJECTIVE_KEYS)


def _records_to_array(records: Sequence[Dict[str, Any]]) -> np.ndarray:
    if not records:
        return np.empty((0, 3), dtype=float)
    return np.asarray([_objectives(record) for record in records], dtype=float)


def _pareto_front(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not records:
        return []
    keep = pareto_prune_points([_objectives(record) for record in records], tau=1e-9)
    return [records[idx] for idx in keep]


def _normalize_pair(reference: np.ndarray, variant: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if len(reference) == 0:
        return reference, variant
    stacked = reference if len(variant) == 0 else np.vstack([reference, variant])
    mins = np.min(stacked, axis=0)
    maxs = np.max(stacked, axis=0)
    span = np.maximum(maxs - mins, 1e-12)
    return (reference - mins) / span, (variant - mins) / span


def _nearest_distances(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    if len(source) == 0 or len(target) == 0:
        return np.asarray([], dtype=float)
    chunks = []
    for start in range(0, len(source), 500):
        chunk = source[start : start + 500]
        diff = chunk[:, None, :] - target[None, :, :]
        chunks.append(np.sqrt(np.min(np.sum(diff * diff, axis=2), axis=1)))
    return np.concatenate(chunks) if chunks else np.asarray([], dtype=float)


def _nondominated_array(points: np.ndarray) -> np.ndarray:
    if len(points) == 0:
        return points
    if points.shape[1] == 2:
        order = np.lexsort((points[:, 1], points[:, 0]))
        sorted_points = points[order]
        keep_rows = []
        best_second = math.inf
        for point in sorted_points:
            if float(point[1]) < best_second - 1e-12:
                keep_rows.append(point)
                best_second = float(point[1])
        return np.asarray(keep_rows, dtype=float)
    keep = pareto_prune_points([tuple(row) for row in points], tau=1e-12)
    return points[keep]


def _hypervolume_2d_min(points: np.ndarray, ref: np.ndarray) -> float:
    pts = points[
        np.isfinite(points).all(axis=1)
        & (points[:, 0] < ref[0])
        & (points[:, 1] < ref[1])
    ]
    if len(pts) == 0:
        return 0.0
    pts = _nondominated_array(pts)
    pts = pts[np.argsort(pts[:, 0], kind="mergesort")]
    area = 0.0
    best_second = math.inf
    for idx, point in enumerate(pts):
        first = float(point[0])
        next_first = float(pts[idx + 1, 0]) if idx + 1 < len(pts) else float(ref[0])
        best_second = min(best_second, float(point[1]))
        area += max(next_first - first, 0.0) * max(float(ref[1]) - best_second, 0.0)
    return area


def _hypervolume_3d_min(points: np.ndarray, ref: np.ndarray) -> float:
    pts = points[
        np.isfinite(points).all(axis=1)
        & (points[:, 0] < ref[0])
        & (points[:, 1] < ref[1])
        & (points[:, 2] < ref[2])
    ]
    if len(pts) == 0:
        return 0.0
    pts = _nondominated_array(pts)
    pts = pts[np.argsort(pts[:, 0], kind="mergesort")]
    hv = 0.0
    for idx, point in enumerate(pts):
        first = float(point[0])
        next_first = float(pts[idx + 1, 0]) if idx + 1 < len(pts) else float(ref[0])
        hv += max(next_first - first, 0.0) * _hypervolume_2d_min(pts[: idx + 1, 1:3], ref[1:3])
    return hv


def _reference_point(fronts: Iterable[Sequence[Dict[str, Any]]]) -> np.ndarray:
    arrays = [_records_to_array(front) for front in fronts if front]
    if not arrays:
        return np.ones(3)
    stacked = np.vstack(arrays)
    mins = np.min(stacked, axis=0)
    maxs = np.max(stacked, axis=0)
    span = np.maximum(maxs - mins, np.maximum(np.abs(maxs), 1.0) * 1e-9)
    return maxs + 0.05 * span


def _compare_fronts(
    reference_name: str,
    reference_front: Sequence[Dict[str, Any]],
    variant_name: str,
    variant_front: Sequence[Dict[str, Any]],
    hv_reference_point: np.ndarray,
    runtime_s: float,
) -> Dict[str, Any]:
    ref_arr = _records_to_array(reference_front)
    var_arr = _records_to_array(variant_front)
    ref_norm, var_norm = _normalize_pair(ref_arr, var_arr)
    ref_to_var = _nearest_distances(ref_norm, var_norm)
    var_to_ref = _nearest_distances(var_norm, ref_norm)
    hv_ref = _hypervolume_3d_min(ref_arr, hv_reference_point)
    hv_var = _hypervolume_3d_min(var_arr, hv_reference_point)
    return {
        "reference": reference_name,
        "variant": variant_name,
        "reference_front_size": len(reference_front),
        "variant_front_size": len(variant_front),
        "runtime_s": round(runtime_s, 3),
        "igd_ref_to_variant_norm": float(np.mean(ref_to_var)) if len(ref_to_var) else math.nan,
        "igd_variant_to_ref_norm": float(np.mean(var_to_ref)) if len(var_to_ref) else math.nan,
        "bidirectional_igd_norm": (
            float((np.mean(ref_to_var) + np.mean(var_to_ref)) / 2.0)
            if len(ref_to_var) and len(var_to_ref)
            else math.nan
        ),
        "max_ref_to_variant_norm": float(np.max(ref_to_var)) if len(ref_to_var) else math.nan,
        "hv": hv_var,
        "hv_reference": hv_ref,
        "hv_difference": hv_var - hv_ref,
        "hv_relative_to_reference": hv_var / hv_ref if hv_ref > 0 else math.nan,
    }


def _run_variant(
    building_dict: Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]],
    variant: SweepVariant,
    output_dir: Path,
    overwrite: bool,
) -> Tuple[List[Dict[str, Any]], float]:
    front_path = output_dir / "combined_front.pkl"
    runtime_path = output_dir / "runtime.txt"
    if Path(_to_long_path(front_path)).exists() and not overwrite:
        front = _load_pickle(front_path)
        runtime_s = math.nan
        if Path(_to_long_path(runtime_path)).exists():
            with open(_to_long_path(runtime_path), "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for line in text.splitlines():
                if line.startswith("runtime_s="):
                    runtime_s = float(line.split("=", 1)[1])
                    break
        return front, runtime_s

    started_at = datetime.now()
    t0 = time.perf_counter()
    per_building_front, combined_front = combine_all_buildings(
        building_dict,
        refurbishment_strategies=REFURBISHMENT_STRATEGIES,
        tau=1e-9,
        eps_rel_each=variant.eps_each,
        modes_each=("log", "log", "log"),
        eps_rel_merge=variant.eps_merge,
        modes_merge=("log", "log", "log"),
        max_points_after_each_merge=variant.cap,
    )
    combined_front = _pareto_front(combined_front)
    runtime_s = time.perf_counter() - t0
    finished_at = datetime.now()

    meta = {
        "variant": asdict(variant),
        "objective_order": OBJECTIVE_KEYS,
        "tau": 1e-9,
        "modes_each": ("log", "log", "log"),
        "modes_merge": ("log", "log", "log"),
        "total_buildings": len(building_dict),
        "combined_front_size": len(combined_front),
        "per_building_front_sizes": {
            building_id: len(front)
            for building_id, front in per_building_front.items()
        },
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at.isoformat(timespec="seconds"),
        "runtime_s": runtime_s,
    }
    package = [building_dict, per_building_front, combined_front]

    _save_pickle(output_dir / "building_dict.pkl", building_dict)
    _save_pickle(output_dir / "per_building_front.pkl", per_building_front)
    _save_pickle(output_dir / "combined_front.pkl", combined_front)
    _save_pickle(output_dir / "combined_package.pkl", package)
    _save_pickle(output_dir / "meta.pkl", meta)
    _write_text(
        output_dir / "runtime.txt",
        "\n".join(
            [
                f"variant={variant.name}",
                f"description={variant.description}",
                f"eps_each={variant.eps_each}",
                f"eps_merge={variant.eps_merge}",
                f"cap={variant.cap}",
                f"started_at={started_at.isoformat(timespec='seconds')}",
                f"finished_at={finished_at.isoformat(timespec='seconds')}",
                f"runtime_s={runtime_s:.6f}",
                f"combined_front_size={len(combined_front)}",
            ]
        )
        + "\n",
    )
    return combined_front, runtime_s


def _variant_dir(output_root: Path, idx: int, variant_name: str) -> Path:
    existing = sorted(output_root.glob(f"*_{variant_name}"))
    if existing:
        return existing[0]
    return output_root / f"{idx:02d}_{variant_name}"


def _compare_fronts_with_hv_cache(
    reference_name: str,
    reference_front: Sequence[Dict[str, Any]],
    variant_name: str,
    variant_front: Sequence[Dict[str, Any]],
    hv_values: Dict[str, float],
    runtime_s: float,
) -> Dict[str, Any]:
    ref_arr = _records_to_array(reference_front)
    var_arr = _records_to_array(variant_front)
    ref_norm, var_norm = _normalize_pair(ref_arr, var_arr)
    ref_to_var = _nearest_distances(ref_norm, var_norm)
    var_to_ref = _nearest_distances(var_norm, ref_norm)
    hv_ref = hv_values[reference_name]
    hv_var = hv_values[variant_name]
    return {
        "reference": reference_name,
        "variant": variant_name,
        "reference_front_size": len(reference_front),
        "variant_front_size": len(variant_front),
        "runtime_s": round(runtime_s, 3),
        "igd_ref_to_variant_norm": float(np.mean(ref_to_var)) if len(ref_to_var) else math.nan,
        "igd_variant_to_ref_norm": float(np.mean(var_to_ref)) if len(var_to_ref) else math.nan,
        "bidirectional_igd_norm": (
            float((np.mean(ref_to_var) + np.mean(var_to_ref)) / 2.0)
            if len(ref_to_var) and len(var_to_ref)
            else math.nan
        ),
        "max_ref_to_variant_norm": float(np.max(ref_to_var)) if len(ref_to_var) else math.nan,
        "hv": hv_var,
        "hv_reference": hv_ref,
        "hv_difference": hv_var - hv_ref,
        "hv_relative_to_reference": hv_var / hv_ref if hv_ref > 0 else math.nan,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run archive-parameter sweep for UEU 5658, SFH k06 + MFH k01."
    )
    parser.add_argument("--building-dict", type=Path, default=DEFAULT_BUILDING_DICT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", type=str, default=datetime.now().strftime("%Y_%m_%d_%H%M%S"))
    parser.add_argument("--reference-variant", type=str, default="paper_strict_cap8000")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    building_dict_path = args.building_dict.expanduser()
    if not building_dict_path.is_file():
        raise SystemExit(f"building_dict not found: {building_dict_path}")

    output_root = args.output_root / args.run_id / "sfh_k06_mfh_k01"
    _mkdir(output_root)
    building_dict = _load_pickle(building_dict_path)

    fronts: Dict[str, List[Dict[str, Any]]] = {}
    runtimes: Dict[str, float] = {}
    run_rows: List[Dict[str, Any]] = []
    for idx, variant in enumerate(VARIANTS, start=1):
        variant_dir = _variant_dir(output_root, idx, variant.name)
        print(f"[{idx}/{len(VARIANTS)}] {variant.name}", flush=True)
        front, runtime_s = _run_variant(
            building_dict=building_dict,
            variant=variant,
            output_dir=variant_dir,
            overwrite=args.overwrite,
        )
        fronts[variant.name] = front
        runtimes[variant.name] = runtime_s
        run_rows.append(
            {
                "variant": variant.name,
                "eps_each": variant.eps_each,
                "eps_merge": variant.eps_merge,
                "cap": variant.cap,
                "front_size": len(front),
                "runtime_s": round(runtime_s, 3),
                "output_dir": str(variant_dir),
            }
        )
        _write_csv(output_root / "run_summary.csv", run_rows)

    if args.reference_variant not in fronts:
        raise SystemExit(f"Unknown reference variant: {args.reference_variant}")

    hv_ref_point = _reference_point(fronts.values())
    reference_front = fronts[args.reference_variant]
    hv_values = {
        variant.name: _hypervolume_3d_min(
            _records_to_array(fronts[variant.name]),
            hv_ref_point,
        )
        for variant in VARIANTS
    }
    metric_rows = [
        _compare_fronts_with_hv_cache(
            reference_name=args.reference_variant,
            reference_front=reference_front,
            variant_name=variant.name,
            variant_front=fronts[variant.name],
            hv_values=hv_values,
            runtime_s=runtimes[variant.name],
        )
        for variant in VARIANTS
    ]
    _write_csv(output_root / "comparison_metrics.csv", metric_rows)
    _write_text(
        output_root / "hypervolume_reference_point.txt",
        (
            f"objective_order={OBJECTIVE_KEYS}\n"
            f"reference_variant={args.reference_variant}\n"
            f"reference_point={tuple(float(x) for x in hv_ref_point)}\n"
        ),
    )
    print(f"Wrote sweep results to: {output_root}", flush=True)


if __name__ == "__main__":
    main()
