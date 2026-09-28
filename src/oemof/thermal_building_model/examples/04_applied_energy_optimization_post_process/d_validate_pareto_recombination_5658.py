import argparse
import csv
import importlib.util
import itertools
import math
import os
import pickle
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEFAULT_DATA_ROOT = Path(
    r"M:\04_ArchivMA\Hillen Maximilian\Veröffentlichungen\UEU\processed_bds_in_DENI03403000SEC5658"
)
DEFAULT_OUTPUT_ROOT = SCRIPT_DIR / "pareto_recombination_validation_5658"
DEFAULT_REFURBISHMENT_STRATEGIES = [
    "no_refurbishment",
    "usual_refurbishment",
    "advanced_refurbishment",
    "GEG_standard",
]
DEFAULT_OPTIMIZATION_STRATEGIES = ["co2"]
OBJECTIVE_KEYS = ("co2", "peak", "totex")


from oemof.thermal_building_model.helpers.pareto_optimal_help_functions import (
    _compute_real_peak_from_selection,
    collect_options_for_building,
    combine_two_fronts,
    compute_global_scales_from_fronts,
    epsilon_reduce,
    pareto_prune_building,
    pareto_prune_points,
    select_by_crowding,
)


def _load_decentralized_postprocess_module():
    module_path = SCRIPT_DIR / "decentralized" / "a_post_process_decentralized_k_combinations.py"
    spec = importlib.util.spec_from_file_location("dec_postprocess_for_validation", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import post-process module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DEC_POST = _load_decentralized_postprocess_module()


@dataclass(frozen=True)
class VariantConfig:
    name: str
    use_building_prune: bool
    eps_each: Optional[Tuple[float, float, float]]
    eps_merge: Optional[Tuple[float, float, float]]
    max_points_after_each_merge: Optional[int]
    order_mode: str = "default"
    seed: int = 0
    exact_cartesian: bool = False


def _parse_k_token(raw: str) -> Any:
    value = str(raw).strip().lower()
    if value == "reference":
        return "reference"
    if value.startswith("k"):
        value = value[1:]
    return int(value)


def _combo_name(sfh_k: Any, mfh_k: Any) -> str:
    return f"sfh_{_k_token(sfh_k)}_mfh_{_k_token(mfh_k)}"


def _k_token(k_value: Any) -> str:
    if isinstance(k_value, str) and k_value.lower() == "reference":
        return "reference"
    return f"k{int(k_value):02d}"


def _objectives(record: Dict[str, Any]) -> Tuple[float, float, float]:
    return tuple(float(record[key]) for key in OBJECTIVE_KEYS)


def _pareto_front(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not records:
        return []
    points = [_objectives(record) for record in records]
    keep = pareto_prune_points(points, tau=1e-9)
    return [records[i] for i in keep]


def _records_to_array(records: Sequence[Dict[str, Any]]) -> np.ndarray:
    if not records:
        return np.empty((0, 3), dtype=float)
    return np.asarray([_objectives(record) for record in records], dtype=float)


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:d}:{sec:02d}"


def _count_raw_options(
    building_dict_for_one: Dict[str, Dict[Any, Dict[str, Any]]],
    refurbishment_strategies: Iterable[str],
) -> int:
    return len(collect_options_for_building(building_dict_for_one, refurbishment_strategies))


def _front_for_building(
    building_id: str,
    building_data: Dict[str, Dict[Any, Dict[str, Any]]],
    refurbishment_strategies: Iterable[str],
    use_building_prune: bool,
    eps_rel: Optional[Tuple[float, float, float]],
    modes: Tuple[str, str, str],
    scales: Tuple[float, float, float],
    max_options_per_building: Optional[int],
) -> List[Dict[str, Any]]:
    if use_building_prune:
        front = pareto_prune_building(building_data, refurbishment_strategies, tau=1e-9)
    else:
        front = collect_options_for_building(building_data, refurbishment_strategies)

    if eps_rel is not None and front:
        front = epsilon_reduce(front, eps_rel, modes=modes, scales=scales)

    if use_building_prune and front:
        front = _pareto_front(front)

    if max_options_per_building is not None and len(front) > max_options_per_building:
        front = select_by_crowding(front, max_options_per_building, keys=OBJECTIVE_KEYS)

    return [{**record, "selection": {building_id: record}} for record in front]


def _ordered_building_ids(
    ids: Sequence[str],
    mode: str,
    seed: int,
    option_counts: Dict[str, int],
) -> List[str]:
    out = list(ids)
    if mode == "default":
        return out
    if mode == "reverse":
        return list(reversed(out))
    if mode == "small_first":
        return sorted(out, key=lambda bid: (option_counts.get(bid, 10**12), bid))
    if mode == "large_first":
        return sorted(out, key=lambda bid: (-option_counts.get(bid, -1), bid))
    if mode == "random":
        rng = random.Random(seed)
        rng.shuffle(out)
        return out
    raise ValueError(f"Unknown order mode: {mode}")


def _recombine_incremental(
    building_dict: Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]],
    refurbishment_strategies: Iterable[str],
    config: VariantConfig,
    max_options_per_building: Optional[int] = None,
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    global_scales = compute_global_scales_from_fronts(
        building_dict,
        refurbishment_strategies=refurbishment_strategies,
        tau=1e-9,
    )
    option_counts = {
        bid: _count_raw_options(data, refurbishment_strategies)
        for bid, data in building_dict.items()
    }
    bids = _ordered_building_ids(
        list(building_dict.keys()),
        mode=config.order_mode,
        seed=config.seed,
        option_counts=option_counts,
    )

    per_building_fronts: Dict[str, List[Dict[str, Any]]] = {}
    for bid in bids:
        front = _front_for_building(
            building_id=bid,
            building_data=building_dict[bid],
            refurbishment_strategies=refurbishment_strategies,
            use_building_prune=config.use_building_prune,
            eps_rel=config.eps_each,
            modes=("log", "log", "log"),
            scales=global_scales,
            max_options_per_building=max_options_per_building,
        )
        if front:
            per_building_fronts[bid] = front

    ordered_non_empty = [bid for bid in bids if bid in per_building_fronts]
    if not ordered_non_empty:
        return per_building_fronts, []

    current = per_building_fronts[ordered_non_empty[0]]
    for idx in range(1, len(ordered_non_empty)):
        bid = ordered_non_empty[idx]
        current = combine_two_fronts(
            current,
            per_building_fronts[bid],
            "merged",
            bid,
            tau=1e-9,
            eps_rel=config.eps_merge,
            modes=("log", "log", "log"),
            scales=global_scales,
            max_points=config.max_points_after_each_merge,
        )

    return per_building_fronts, _pareto_front(current)


def _exact_cartesian_front(
    building_dict: Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]],
    refurbishment_strategies: Iterable[str],
    use_building_prune: bool,
    max_combinations: int,
) -> Tuple[List[Dict[str, Any]], int, List[Tuple[str, int]]]:
    option_lists: List[Tuple[str, List[Dict[str, Any]]]] = []
    for bid, data in building_dict.items():
        if use_building_prune:
            options = pareto_prune_building(data, refurbishment_strategies, tau=1e-9)
        else:
            options = collect_options_for_building(data, refurbishment_strategies)
        options = [{**record, "selection": {bid: record}} for record in options]
        if options:
            option_lists.append((bid, options))

    counts = [(bid, len(options)) for bid, options in option_lists]
    product_size = 1
    for _, count in counts:
        product_size *= count
        if product_size > max_combinations:
            raise RuntimeError(
                "Exact Cartesian reference too large: "
                f"{product_size} combinations exceed limit {max_combinations}. "
                "Use fewer subset buildings or raise --max-exact-combinations."
            )

    front: List[Dict[str, Any]] = []
    batch: List[Dict[str, Any]] = []
    produced = 0
    for combo in itertools.product(*(options for _, options in option_lists)):
        selection = {}
        co2 = 0.0
        totex = 0.0
        for bid, option in zip((bid for bid, _ in option_lists), combo):
            selection[bid] = option
            co2 += float(option["co2"])
            totex += float(option["totex"])
        real_peak_from_grid, real_peak_into_grid, peak = _compute_real_peak_from_selection(selection)
        batch.append(
            {
                "co2": co2,
                "peak": peak,
                "totex": totex,
                "real_peak_from_grid": real_peak_from_grid,
                "real_peak_into_grid": real_peak_into_grid,
            }
        )
        produced += 1
        if len(batch) >= 25000:
            front = _pareto_front(front + batch)
            batch = []

    if batch:
        front = _pareto_front(front + batch)
    return front, produced, counts


def _choose_exact_subset(
    building_dict: Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]],
    refurbishment_strategies: Iterable[str],
    requested_size: int,
    max_combinations: int,
) -> List[str]:
    counts = []
    for bid, data in building_dict.items():
        count = _count_raw_options(data, refurbishment_strategies)
        if count > 0:
            counts.append((bid, count))
    counts.sort(key=lambda item: (item[1], item[0]))

    chosen = []
    product_size = 1
    for bid, count in counts:
        if len(chosen) >= requested_size:
            break
        if product_size * count > max_combinations and chosen:
            break
        chosen.append(bid)
        product_size *= count
    return chosen


def _normalize_arrays(ref: np.ndarray, approx: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if len(ref) == 0:
        return ref, approx
    if len(approx) == 0:
        stacked = ref
    else:
        stacked = np.vstack([ref, approx])
    mins = np.min(stacked, axis=0)
    maxs = np.max(stacked, axis=0)
    span = np.maximum(maxs - mins, 1e-12)
    return (ref - mins) / span, (approx - mins) / span


def _nearest_distances(reference: np.ndarray, approximation: np.ndarray) -> np.ndarray:
    if len(reference) == 0 or len(approximation) == 0:
        return np.asarray([], dtype=float)
    diff = reference[:, None, :] - approximation[None, :, :]
    return np.sqrt(np.min(np.sum(diff * diff, axis=2), axis=1))


def _additive_epsilon(reference: np.ndarray, approximation: np.ndarray) -> float:
    if len(reference) == 0 or len(approximation) == 0:
        return math.nan
    eps_values = []
    for ref_point in reference:
        per_candidate = np.max(approximation - ref_point, axis=1)
        eps_values.append(float(np.min(per_candidate)))
    return float(np.max(eps_values))


def _dominance_coverage(reference: np.ndarray, approximation: np.ndarray, tol: float = 1e-12) -> float:
    if len(reference) == 0 or len(approximation) == 0:
        return math.nan
    covered = 0
    for ref_point in reference:
        if np.any(np.all(approximation <= ref_point + tol, axis=1)):
            covered += 1
    return covered / len(reference)


def _compare_to_reference(
    combo: str,
    reference_name: str,
    reference_records: Sequence[Dict[str, Any]],
    variant_name: str,
    variant_records: Sequence[Dict[str, Any]],
    elapsed_s: float,
    produced_combinations: Optional[int] = None,
) -> Dict[str, Any]:
    ref_arr = _records_to_array(reference_records)
    var_arr = _records_to_array(variant_records)
    ref_norm, var_norm = _normalize_arrays(ref_arr, var_arr)
    nn = _nearest_distances(ref_norm, var_norm)

    return {
        "combo": combo,
        "reference": reference_name,
        "variant": variant_name,
        "reference_front_size": len(reference_records),
        "variant_front_size": len(variant_records),
        "produced_combinations": produced_combinations,
        "elapsed_s": round(elapsed_s, 3),
        "igd_norm": float(np.mean(nn)) if len(nn) else math.nan,
        "max_nearest_distance_norm": float(np.max(nn)) if len(nn) else math.nan,
        "share_ref_points_within_1pct_norm": float(np.mean(nn <= 0.01)) if len(nn) else math.nan,
        "share_ref_points_weakly_covered": _dominance_coverage(ref_norm, var_norm),
        "additive_epsilon_norm": _additive_epsilon(ref_norm, var_norm),
    }


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    _mkdir(path.parent)
    if not rows:
        return
    columns = list(rows[0].keys())
    with open(_to_long_path(path), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _save_pickle(path: Path, payload: Any) -> None:
    _mkdir(path.parent)
    with open(_to_long_path(path), "wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)


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


def _plot_projection(path: Path, fronts: Dict[str, Sequence[Dict[str, Any]]], title: str) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"plot skipped ({exc})")
        return

    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    for name, records in fronts.items():
        arr = _records_to_array(records)
        if len(arr) == 0:
            continue
        arr = arr[np.argsort(arr[:, 0])]
        if name.startswith("exact"):
            ax.plot(arr[:, 0], arr[:, 2], linewidth=1.4, label=name)
        else:
            ax.scatter(arr[:, 0], arr[:, 2], s=12, alpha=0.7, label=name)
    ax.set_xlabel("Ann. CO2-eq.")
    ax.set_ylabel("Ann. TOTEX")
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=7)
    _mkdir(path.parent)
    fig.tight_layout()
    fig.savefig(_to_long_path(path), dpi=300)
    plt.close(fig)


def _plot_metric_bars(path: Path, rows: Sequence[Dict[str, Any]], metric: str, title: str) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"plot skipped ({exc})")
        return

    filtered = [row for row in rows if row.get("variant") != row.get("reference")]
    if not filtered:
        return
    labels = [str(row["variant"]) for row in filtered]
    values = [float(row[metric]) if row.get(metric) not in (None, "") else math.nan for row in filtered]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.bar(range(len(values)), values)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=7)
    ax.set_ylabel(metric)
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.25)
    _mkdir(path.parent)
    fig.tight_layout()
    fig.savefig(_to_long_path(path), dpi=300)
    plt.close(fig)


def _load_building_dict(
    data_root: Path,
    sfh_k: Any,
    mfh_k: Any,
    refurbishment_strategies: Sequence[str],
    optimization_strategies: Sequence[str],
    ev_token: str,
) -> Tuple[Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]], Dict[str, int]]:
    original_loader = DEC_POST._load_building_result_records
    DEC_POST._load_building_result_records = (
        lambda result_folder, building_id, refurbish, optimization_strategies:
        _load_building_result_records_flexible(
            result_folder=Path(result_folder),
            building_id=building_id,
            refurbish=refurbish,
            optimization_strategies=optimization_strategies,
            ev_token=ev_token,
        )
    )
    try:
        try:
            building_dict, stats = DEC_POST._build_decentralized_building_dict_for_combination(
                cluster_root=data_root,
                result_root=data_root,
                sfh_k=sfh_k,
                mfh_k=mfh_k,
                refurbishment_strategies=refurbishment_strategies,
                optimization_strategies=optimization_strategies,
                print_scaling=False,
                print_scaling_only_changed=True,
            )
        except FileNotFoundError:
            if _k_token(sfh_k) != "reference" or _k_token(mfh_k) != "reference":
                raise
            print(
                "Reference gpkg not found; falling back to building ids parsed from reference result filenames.",
                flush=True,
            )
            building_dict, stats = _load_reference_reference_from_filenames(
                data_root=data_root,
                refurbishment_strategies=refurbishment_strategies,
                optimization_strategies=optimization_strategies,
                ev_token=ev_token,
            )
    finally:
        DEC_POST._load_building_result_records = original_loader
    non_empty = {
        bid: data
        for bid, data in building_dict.items()
        if any(bool(data.get(refurbishment, {})) for refurbishment in refurbishment_strategies)
    }
    return non_empty, stats


def _ev_tokens(ev_token: str) -> List[str]:
    normalized = str(ev_token).strip()
    if normalized.lower() == "all":
        return ["no_EV", "yes_EV"]
    if normalized not in {"no_EV", "yes_EV"}:
        raise ValueError("--ev-token must be one of: all, no_EV, yes_EV")
    return [normalized]


def _load_building_result_records_flexible(
    result_folder: Path,
    building_id: Any,
    refurbish: str,
    optimization_strategies: Iterable[str],
    ev_token: str,
) -> Dict[Any, Any]:
    folder_key = str(result_folder)
    cached_files = DEC_POST.RESULT_FOLDER_FILE_CACHE.get(folder_key)
    if cached_files is None:
        cached_files = sorted(path for path in result_folder.glob("*.pkl") if path.is_file())
        DEC_POST.RESULT_FOLDER_FILE_CACHE[folder_key] = cached_files

    merged: Dict[Any, Any] = {}
    for ev in _ev_tokens(ev_token):
        prefix = f"results_dec_{refurbish}_{ev}_{building_id}"
        chunk_prefix = f"{prefix}_co2_"
        files = [
            path for path in cached_files
            if path.name.startswith(chunk_prefix) and path.name.endswith(".pkl")
        ]
        fallback_name = f"{prefix}.pkl"
        files.extend(path for path in cached_files if path.name == fallback_name)

        for path in files:
            with open(_to_long_path(path), "rb") as fh:
                raw = pickle.load(fh)
            if not isinstance(raw, dict):
                continue
            filtered = DEC_POST._filter_record_keys(raw, optimization_strategies)
            cleaned = DEC_POST._remove_series(filtered)
            for key, value in cleaned.items():
                out_key = key
                if ev_token.lower() == "all":
                    out_key = tuple(list(key) + [ev])
                merged[out_key] = value
    return merged


def _load_reference_reference_from_filenames(
    data_root: Path,
    refurbishment_strategies: Sequence[str],
    optimization_strategies: Sequence[str],
    ev_token: str,
) -> Tuple[Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]], Dict[str, int]]:
    reference_folder = data_root / "reference"
    if not reference_folder.is_dir():
        raise FileNotFoundError(f"Missing reference result folder: {reference_folder}")

    building_ids = set()
    for path in reference_folder.glob("results_dec_*_EV_*_co2_*.pkl"):
        name = path.name
        for refurbish in refurbishment_strategies:
            for ev in _ev_tokens(ev_token):
                prefix = f"results_dec_{refurbish}_{ev}_"
                if not name.startswith(prefix):
                    continue
                match = re.match(rf"^{re.escape(prefix)}(.+?)_co2_.+\.pkl$", name)
                if match:
                    building_ids.add(match.group(1))

    building_dict: Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]] = {}
    loaded_buckets = 0
    missing_buckets = 0
    for building_id in sorted(building_ids):
        building_dict[building_id] = {}
        for refurbish in refurbishment_strategies:
            recs = _load_building_result_records_flexible(
                result_folder=reference_folder,
                building_id=building_id,
                refurbish=refurbish,
                optimization_strategies=optimization_strategies,
                ev_token=ev_token,
            )
            building_dict[building_id][refurbish] = recs
            if recs:
                loaded_buckets += 1
            else:
                missing_buckets += 1

    stats = {
        "sfh_buildings": None,
        "mfh_buildings": None,
        "reference_buildings_from_filenames": len(building_ids),
        "sfh_total_occurrence": None,
        "mfh_total_occurrence": None,
        "loaded_refurbishment_buckets": loaded_buckets,
        "missing_refurbishment_buckets": missing_buckets,
    }
    return building_dict, stats


def _run_variant(
    building_dict: Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]],
    refurbishment_strategies: Sequence[str],
    config: VariantConfig,
    max_exact_combinations: int,
    max_options_per_building: Optional[int],
) -> Tuple[List[Dict[str, Any]], float, Optional[int]]:
    started_at = time.perf_counter()
    produced_combinations = None
    if config.exact_cartesian:
        front, produced_combinations, _ = _exact_cartesian_front(
            building_dict=building_dict,
            refurbishment_strategies=refurbishment_strategies,
            use_building_prune=config.use_building_prune,
            max_combinations=max_exact_combinations,
        )
    else:
        _, front = _recombine_incremental(
            building_dict=building_dict,
            refurbishment_strategies=refurbishment_strategies,
            config=config,
            max_options_per_building=max_options_per_building,
        )
    return front, time.perf_counter() - started_at, produced_combinations


def _subset_variants() -> List[VariantConfig]:
    return [
        VariantConfig("exact_raw_no_prune_no_bucket_no_cap", False, None, None, None, exact_cartesian=True),
        VariantConfig("exact_after_local_prune_only", True, None, None, None, exact_cartesian=True),
        VariantConfig("incremental_no_bucket_no_cap_default_order", True, None, None, None),
        VariantConfig("incremental_no_bucket_no_cap_reverse_order", True, None, None, None, order_mode="reverse"),
        VariantConfig("current_archive_default_order", True, (0.002, 0.002, 0.002), (0.008, 0.008, 0.008), 2000),
        VariantConfig("current_archive_reverse_order", True, (0.002, 0.002, 0.002), (0.008, 0.008, 0.008), 2000, order_mode="reverse"),
        VariantConfig("current_archive_random_order_seed1", True, (0.002, 0.002, 0.002), (0.008, 0.008, 0.008), 2000, order_mode="random", seed=1),
        VariantConfig("no_bucket_with_archive_cap", True, None, None, 2000),
        VariantConfig("bucket_without_archive_cap", True, (0.002, 0.002, 0.002), (0.008, 0.008, 0.008), None),
        VariantConfig("stricter_bucket_larger_archive", True, (0.001, 0.001, 0.001), (0.002, 0.002, 0.002), 5000),
        VariantConfig("no_local_prune_current_bucket_cap", False, (0.002, 0.002, 0.002), (0.008, 0.008, 0.008), 2000),
    ]


def _full_variants() -> List[VariantConfig]:
    return [
        VariantConfig("current_archive_default_order", True, (0.002, 0.002, 0.002), (0.008, 0.008, 0.008), 2000),
        VariantConfig("current_archive_reverse_order", True, (0.002, 0.002, 0.002), (0.008, 0.008, 0.008), 2000, order_mode="reverse"),
        VariantConfig("current_archive_random_order_seed1", True, (0.002, 0.002, 0.002), (0.008, 0.008, 0.008), 2000, order_mode="random", seed=1),
        VariantConfig("stricter_bucket_larger_archive", True, (0.001, 0.001, 0.001), (0.002, 0.002, 0.002), 5000),
        VariantConfig("no_bucket_with_archive_cap", True, None, None, 2000),
    ]


def _run_combo(
    data_root: Path,
    output_root: Path,
    sfh_k: Any,
    mfh_k: Any,
    refurbishment_strategies: Sequence[str],
    optimization_strategies: Sequence[str],
    subset_buildings: int,
    max_exact_combinations: int,
    run_full: bool,
    max_options_per_building: Optional[int],
    ev_token: str,
) -> List[Dict[str, Any]]:
    combo = _combo_name(sfh_k, mfh_k)
    combo_output = output_root / combo
    print(f"\n=== {combo} ===", flush=True)
    building_dict, stats = _load_building_dict(
        data_root=data_root,
        sfh_k=sfh_k,
        mfh_k=mfh_k,
        refurbishment_strategies=refurbishment_strategies,
        optimization_strategies=optimization_strategies,
        ev_token=ev_token,
    )
    if not building_dict:
        print("No non-empty buildings found.", flush=True)
        return []

    subset_ids = _choose_exact_subset(
        building_dict=building_dict,
        refurbishment_strategies=refurbishment_strategies,
        requested_size=subset_buildings,
        max_combinations=max_exact_combinations,
    )
    subset_dict = {bid: building_dict[bid] for bid in subset_ids}
    subset_counts = [
        {
            "combo": combo,
            "building_id": bid,
            "raw_options": _count_raw_options(building_dict[bid], refurbishment_strategies),
            "local_pareto_options": len(pareto_prune_building(building_dict[bid], refurbishment_strategies, tau=1e-9)),
        }
        for bid in subset_ids
    ]
    _write_csv(combo_output / "subset_building_counts.csv", subset_counts)

    print(
        f"Loaded buildings={len(building_dict)}; exact subset={len(subset_dict)}; "
        f"stats={stats}",
        flush=True,
    )

    metrics_rows: List[Dict[str, Any]] = []
    subset_fronts: Dict[str, List[Dict[str, Any]]] = {}
    subset_reference_name = "exact_raw_no_prune_no_bucket_no_cap"

    for config in _subset_variants():
        print(f"subset variant: {config.name}", flush=True)
        try:
            front, elapsed_s, produced = _run_variant(
                building_dict=subset_dict,
                refurbishment_strategies=refurbishment_strategies,
                config=config,
                max_exact_combinations=max_exact_combinations,
                max_options_per_building=max_options_per_building,
            )
        except Exception as exc:
            print(f"  skipped: {exc}", flush=True)
            metrics_rows.append(
                {
                    "combo": combo,
                    "reference": subset_reference_name,
                    "variant": config.name,
                    "reference_front_size": math.nan,
                    "variant_front_size": math.nan,
                    "produced_combinations": math.nan,
                    "elapsed_s": math.nan,
                    "igd_norm": math.nan,
                    "max_nearest_distance_norm": math.nan,
                    "share_ref_points_within_1pct_norm": math.nan,
                    "share_ref_points_weakly_covered": math.nan,
                    "additive_epsilon_norm": math.nan,
                    "status": f"skipped: {exc}",
                    "scope": "subset",
                }
            )
            continue
        subset_fronts[config.name] = front
        _save_pickle(combo_output / "subset_fronts" / f"{config.name}.pkl", front)
        print(
            f"  front={len(front)} elapsed={_format_duration(elapsed_s)} "
            f"produced={produced if produced is not None else '-'}",
            flush=True,
        )

    reference_front = subset_fronts.get(subset_reference_name, [])
    for name, front in subset_fronts.items():
        row = _compare_to_reference(
            combo=combo,
            reference_name=subset_reference_name,
            reference_records=reference_front,
            variant_name=name,
            variant_records=front,
            elapsed_s=0.0,
        )
        row["status"] = "ok"
        row["scope"] = "subset"
        metrics_rows.append(row)

    _plot_projection(
        combo_output / "subset_co2_totex_projection.png",
        subset_fronts,
        f"{combo}: subset validation",
    )
    _plot_metric_bars(
        combo_output / "subset_igd_norm.png",
        [row for row in metrics_rows if row.get("scope") == "subset"],
        "igd_norm",
        f"{combo}: distance to exact subset reference",
    )
    _plot_metric_bars(
        combo_output / "subset_additive_epsilon_norm.png",
        [row for row in metrics_rows if row.get("scope") == "subset"],
        "additive_epsilon_norm",
        f"{combo}: additive epsilon to exact subset reference",
    )

    if run_full:
        full_fronts: Dict[str, List[Dict[str, Any]]] = {}
        full_reference_name = "current_archive_default_order"
        for config in _full_variants():
            print(f"full variant: {config.name}", flush=True)
            try:
                front, elapsed_s, produced = _run_variant(
                    building_dict=building_dict,
                    refurbishment_strategies=refurbishment_strategies,
                    config=config,
                    max_exact_combinations=max_exact_combinations,
                    max_options_per_building=max_options_per_building,
                )
            except Exception as exc:
                print(f"  skipped: {exc}", flush=True)
                continue
            full_fronts[config.name] = front
            _save_pickle(combo_output / "full_fronts" / f"{config.name}.pkl", front)
            print(
                f"  front={len(front)} elapsed={_format_duration(elapsed_s)} "
                f"produced={produced if produced is not None else '-'}",
                flush=True,
            )

        full_reference = full_fronts.get(full_reference_name)
        if full_reference is None and full_fronts:
            full_reference_name = next(iter(full_fronts))
            full_reference = full_fronts[full_reference_name]
        if full_reference is not None:
            for name, front in full_fronts.items():
                row = _compare_to_reference(
                    combo=combo,
                    reference_name=full_reference_name,
                    reference_records=full_reference,
                    variant_name=name,
                    variant_records=front,
                    elapsed_s=0.0,
                )
                row["status"] = "ok"
                row["scope"] = "full"
                metrics_rows.append(row)
            _plot_projection(
                combo_output / "full_co2_totex_projection.png",
                full_fronts,
                f"{combo}: full approximation variants",
            )

    _write_csv(combo_output / "validation_metrics.csv", metrics_rows)
    return metrics_rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate decentralized Pareto recombination for UEU 5658 by comparing "
            "exact subset fronts and approximation variants."
        )
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--combos",
        type=str,
        default="6:1",
        help="Comma-separated SFH:MFH pairs, e.g. 6:1.",
    )
    parser.add_argument("--subset-buildings", type=int, default=5)
    parser.add_argument("--max-exact-combinations", type=int, default=1_000_000)
    parser.add_argument(
        "--run-full",
        action="store_true",
        help="Also run full-size approximation variants. Exact full Cartesian validation is not attempted.",
    )
    parser.add_argument(
        "--ev-token",
        type=str,
        default="no_EV",
        choices=["all", "no_EV", "yes_EV"],
        help="Which EV result token to read from filenames.",
    )
    parser.add_argument(
        "--max-options-per-building",
        type=int,
        default=None,
        help="Optional safety cap per building before approximate recombination.",
    )
    return parser.parse_args()


def _parse_combos(raw: str) -> List[Tuple[Any, Any]]:
    combos = []
    for token in str(raw).split(","):
        token = token.strip()
        if not token:
            continue
        if ":" not in token:
            raise ValueError(f"Combo token must be SFH:MFH, got: {token}")
        sfh_raw, mfh_raw = token.split(":", 1)
        combos.append((_parse_k_token(sfh_raw), _parse_k_token(mfh_raw)))
    return combos


def main() -> None:
    args = _parse_args()
    data_root = args.data_root.expanduser()
    if not data_root.is_dir():
        raise SystemExit(f"Data root not found: {data_root}")

    run_id = date.today().strftime("%Y_%m_%d")
    output_root = args.output_root / args.ev_token / run_id
    _mkdir(output_root)

    all_rows: List[Dict[str, Any]] = []
    for sfh_k, mfh_k in _parse_combos(args.combos):
        rows = _run_combo(
            data_root=data_root,
            output_root=output_root,
            sfh_k=sfh_k,
            mfh_k=mfh_k,
            refurbishment_strategies=DEFAULT_REFURBISHMENT_STRATEGIES,
            optimization_strategies=DEFAULT_OPTIMIZATION_STRATEGIES,
            subset_buildings=args.subset_buildings,
            max_exact_combinations=args.max_exact_combinations,
            run_full=args.run_full,
            max_options_per_building=args.max_options_per_building,
            ev_token=args.ev_token,
        )
        all_rows.extend(rows)

    _write_csv(output_root / "validation_metrics_all_combos.csv", all_rows)
    print(f"\nWrote results to: {output_root}", flush=True)


if __name__ == "__main__":
    main()
