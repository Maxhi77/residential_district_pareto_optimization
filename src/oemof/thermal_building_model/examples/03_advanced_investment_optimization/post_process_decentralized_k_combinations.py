import argparse
import multiprocessing
import os
import pickle
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd

from pareto_optimal_help_functions import combine_all_buildings


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_UEU_CASE = "processed_bds_in_DENI03403000SEC5101"
DEFAULT_REFURBISHMENT_STRATEGIES = [
    "no_refurbishment",
    "usual_refurbishment",
    "advanced_refurbishment",
    "GEG_standard",
]
DEFAULT_OPTIMIZATION_STRATEGIES = ["co2"]

DEFAULT_K_VALUES_TO_OPTIMIZE_SFH = ["reference"]
DEFAULT_K_VALUES_TO_OPTIMIZE_MFH = ["reference"]

#DEFAULT_K_VALUES_TO_OPTIMIZE_SFH = ["reference"]
#DEFAULT_K_VALUES_TO_OPTIMIZE_MFH = ["reference"]
TODAY_DATE = date.today().strftime("%Y_%m_%d")
DEFAULT_OUTPUT_ROOT_NAME = f"post_processed_dec_k_combinations_{TODAY_DATE}"

# Backward-compatible module constants.
UEU_CASE = DEFAULT_UEU_CASE
REFURBISHMENT_STRATEGIES = list(DEFAULT_REFURBISHMENT_STRATEGIES)
OPTIMIZATION_STRATEGIES = list(DEFAULT_OPTIMIZATION_STRATEGIES)
OUTPUT_ROOT_NAME = DEFAULT_OUTPUT_ROOT_NAME


def _is_reference_k(k_value: Any) -> bool:
    return isinstance(k_value, str) and k_value.lower() == "reference"


def _k_token(k_value: Any) -> str:
    if _is_reference_k(k_value):
        return "reference"
    return f"k{int(k_value):02d}"


def _combo_name(sfh_k: Any, mfh_k: Any) -> str:
    return f"sfh_{_k_token(sfh_k)}_mfh_{_k_token(mfh_k)}"


def _format_k_for_log(k_value: Any) -> str:
    if _is_reference_k(k_value):
        return "reference"
    return f"k{int(k_value):02d}"


def _dedupe_keep_order(items: Iterable[Any]) -> List[Any]:
    out = []
    seen = set()
    for item in items:
        marker = item.lower() if isinstance(item, str) else item
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def _parse_k_values(raw_csv: Any) -> List[Any]:
    if raw_csv is None:
        return []

    out = []
    for token in str(raw_csv).split(","):
        value = token.strip()
        if not value:
            continue
        if value.lower() == "reference":
            out.append("reference")
        else:
            out.append(int(value))
    return _dedupe_keep_order(out)


def _parse_csv_values(raw_csv: Any) -> List[str]:
    if raw_csv is None:
        return []
    values = [x.strip() for x in str(raw_csv).split(",") if x.strip()]
    return _dedupe_keep_order(values)


def _resolve_workers(raw_workers: Any, serial: bool = False) -> int:
    workers_raw = str(raw_workers).strip().lower()
    if workers_raw in {"false", "auto", "none"}:
        n_cores = os.cpu_count() or 1
        workers = max(1, n_cores // 2)
    else:
        try:
            workers = int(raw_workers)
        except ValueError as exc:
            raise ValueError("--workers must be an integer or one of: False, auto, none") from exc
        if workers <= 0:
            raise ValueError("--workers must be > 0, or use False/auto for automatic sizing")
    if serial:
        workers = 1
    return max(1, workers)


def _remove_series(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _remove_series(v)
            for k, v in obj.items()
            if not isinstance(v, pd.Series)
        }
    if isinstance(obj, list):
        return [_remove_series(v) for v in obj if not isinstance(v, pd.Series)]
    return obj


def _load_cluster_dataframe(cluster_root: Path, building_type: str, k_value: Any) -> pd.DataFrame:
    if _is_reference_k(k_value):
        gpkg_path = cluster_root / f"{cluster_root.name}.gpkg"
        if not gpkg_path.exists():
            raise FileNotFoundError(f"Missing reference gpkg: {gpkg_path}")
        gdf = gpd.read_file(gpkg_path)
        if "tabula_building_type" not in gdf.columns:
            raise ValueError(f"Missing column 'tabula_building_type' in {gpkg_path}")
        out = gdf.loc[gdf["tabula_building_type"] == building_type].copy()
        if "buildings_in_cluster" not in out.columns:
            out["buildings_in_cluster"] = 1
        return out

    token = _k_token(k_value)
    folder = cluster_root / f"{building_type.lower()}_cluster_{token}"
    cluster_file = folder / f"{building_type.lower()}_cluster.pkl"
    if not cluster_file.exists():
        raise FileNotFoundError(f"Missing cluster file: {cluster_file}")
    with open(cluster_file, "rb") as fh:
        data = pickle.load(fh)
    if isinstance(data, pd.DataFrame):
        out = data
    else:
        out = pd.DataFrame(data)
    if "buildings_in_cluster" not in out.columns:
        out["buildings_in_cluster"] = 1
    return out


def _result_folder_for_type(cluster_root: Path, building_type: str, k_value: Any) -> Path:
    if _is_reference_k(k_value):
        return cluster_root / "reference"
    return cluster_root / f"{building_type.lower()}_cluster_{_k_token(k_value)}"


def _filter_record_keys(
    data: Dict[Any, Any],
    optimization_strategies: Iterable[str],
) -> Dict[Any, Any]:
    allowed = set(optimization_strategies)

    def _keep_key(k: Any) -> bool:
        return isinstance(k, tuple) and len(k) >= 4 and k[3] in allowed

    return {k: v for k, v in data.items() if _keep_key(k)}


def _to_positive_float(value: Any, default: float = 1.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    if not np.isfinite(out) or out <= 0:
        return default
    return out


def _scale_payload(value: Any, factor: float) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value) * factor
    if isinstance(value, list):
        return [(_scale_payload(v, factor) if isinstance(v, (int, float, np.integer, np.floating)) else v) for v in value]
    if isinstance(value, tuple):
        return tuple((_scale_payload(v, factor) if isinstance(v, (int, float, np.integer, np.floating)) else v) for v in value)
    if isinstance(value, np.ndarray):
        try:
            return value * factor
        except Exception:
            return value
    if isinstance(value, pd.Series):
        try:
            return value * factor
        except Exception:
            return value
    return value


def _resolve_cluster_root(ueu_case: str, base_dir: Path) -> Path:
    ueu_path = Path(str(ueu_case))
    if ueu_path.is_absolute():
        return ueu_path
    return base_dir / str(ueu_case)


def _scale_building_records_to_occurrence(
    recs: Dict[Any, Dict[str, Any]],
    building_id: str,
    target_occurrence: float,
    print_scaling: bool = False,
    print_scaling_only_changed: bool = True,
    scaling_context: str = "",
) -> Dict[Any, Dict[str, Any]]:
    if not recs:
        if print_scaling:
            print(f"[scaling] {scaling_context} building={building_id} no_records")
        return recs

    carriers_to_scale = ("Electricity", "NaturalGas", "NautralGas", "BioGas", "Hydrogen")
    carrier_single_keys = (
        "flow_from_grid_sum",
        "flow_into_grid_sum",
        "flow_from_grid_cost",
        "flow_into_grid_revenue",
        "flow_from_grid_co2",
        "flow_into_grid_co2",
        "peak_into_grid",
        "peak_from_grid",
        "peak",
    )
    carrier_series_keys = ("flow_from_grid", "flow_into_grid", "flow_from_grid_flow_into_grid")
    technology_prefixes = ("pv_system", "heat_storage", "battery", "gas_heater", "chp", "hp", "building")
    investment_keys = ("investment_cost", "investment_co2")
    top_level_numeric = ("co2", "totex", "peak", "real_peak_from_grid", "real_peak_into_grid")
    results_numeric = ("co2_oemof_model", "co2_operation", "co2_investment", "totex", "totex_oemof_model")
    scaling_markers = set()

    for rec_key, rec in recs.items():
        if not isinstance(rec, dict):
            continue
        results = rec.get("results")
        if not isinstance(results, dict):
            continue

        building_results = results.get(building_id)
        if not isinstance(building_results, dict):
            continue

        used = _to_positive_float(building_results.get("buildings_in_cluster_used", 1), default=1.0)
        target = _to_positive_float(target_occurrence, default=1.0)
        factor = target / used if used > 0 else 1.0
        marker = (round(used, 12), round(target, 12), round(factor, 12))
        if marker not in scaling_markers:
            scaling_markers.add(marker)
            if print_scaling and (not print_scaling_only_changed or abs(factor - 1.0) > 1e-12):
                print(
                    f"[scaling] {scaling_context} building={building_id} "
                    f"used={used} target={target} factor={factor}"
                )

        if abs(factor - 1.0) <= 1e-12:
            building_results["buildings_in_cluster"] = target
            building_results["buildings_in_cluster_used"] = target
            continue

        for k in top_level_numeric:
            if k in rec and rec[k] is not None:
                rec[k] = _scale_payload(rec[k], factor)

        for k in results_numeric:
            if k in results and results[k] is not None:
                results[k] = _scale_payload(results[k], factor)

        for carrier in carriers_to_scale:
            carrier_data = results.get(carrier)
            if not isinstance(carrier_data, dict):
                continue
            for k in carrier_single_keys:
                if k in carrier_data and carrier_data[k] is not None:
                    carrier_data[k] = _scale_payload(carrier_data[k], factor)
            for k in carrier_series_keys:
                if k in carrier_data and carrier_data[k] is not None:
                    carrier_data[k] = _scale_payload(carrier_data[k], factor)

        for comp_key, comp_val in building_results.items():
            if not isinstance(comp_val, dict):
                continue
            if not any(comp_key.startswith(f"{prefix}_{building_id}") for prefix in technology_prefixes):
                continue
            for inv_key in investment_keys:
                if inv_key in comp_val and comp_val[inv_key] is not None:
                    comp_val[inv_key] = _scale_payload(comp_val[inv_key], factor)

        building_results["buildings_in_cluster"] = target
        building_results["buildings_in_cluster_used"] = target
        rec["scaled_to_buildings_in_cluster_factor"] = factor

    if print_scaling and not scaling_markers:
        print(f"[scaling] {scaling_context} building={building_id} no_scaling_marker")

    return recs


def _load_building_result_records(
    result_folder: Path,
    building_id: Any,
    refurbish: str,
    optimization_strategies: Iterable[str],
) -> Dict[Any, Any]:
    prefix = f"results_dec_{refurbish}_no_EV_{building_id}"
    files = sorted(result_folder.glob(f"{prefix}_co2_*.pkl"))
    if not files:
        fallback = result_folder / f"{prefix}.pkl"
        if fallback.exists():
            files = [fallback]

    merged: Dict[Any, Any] = {}
    for path in files:
        with open(path, "rb") as fh:
            raw = pickle.load(fh)
        if not isinstance(raw, dict):
            continue
        filtered = _filter_record_keys(raw, optimization_strategies)
        cleaned = _remove_series(filtered)
        merged.update(cleaned)
    return merged


def _build_decentralized_building_dict_for_combination(
    cluster_root: Path,
    sfh_k: Any,
    mfh_k: Any,
    refurbishment_strategies: Iterable[str],
    optimization_strategies: Iterable[str],
    print_scaling: bool = False,
    print_scaling_only_changed: bool = True,
) -> Tuple[Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]], Dict[str, int]]:
    sfh_df = _load_cluster_dataframe(cluster_root, "SFH", sfh_k)
    mfh_df = _load_cluster_dataframe(cluster_root, "MFH", mfh_k)

    if "building_id" not in sfh_df.columns and not sfh_df.empty:
        raise ValueError("SFH cluster frame has no 'building_id' column.")
    if "building_id" not in mfh_df.columns and not mfh_df.empty:
        raise ValueError("MFH cluster frame has no 'building_id' column.")

    sfh_ids = [str(x) for x in sfh_df["building_id"].tolist()] if not sfh_df.empty else []
    mfh_ids = [str(x) for x in mfh_df["building_id"].tolist()] if not mfh_df.empty else []
    sfh_occurrence = {}
    mfh_occurrence = {}
    if not sfh_df.empty:
        for _, row in sfh_df.iterrows():
            sfh_occurrence[str(row["building_id"])] = _to_positive_float(row.get("buildings_in_cluster", 1), default=1.0)
    if not mfh_df.empty:
        for _, row in mfh_df.iterrows():
            mfh_occurrence[str(row["building_id"])] = _to_positive_float(row.get("buildings_in_cluster", 1), default=1.0)

    sfh_folder = _result_folder_for_type(cluster_root, "SFH", sfh_k)
    mfh_folder = _result_folder_for_type(cluster_root, "MFH", mfh_k)

    building_dict: Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]] = {}
    stats = {
        "sfh_buildings": len(sfh_ids),
        "mfh_buildings": len(mfh_ids),
        "sfh_total_occurrence": int(round(sum(sfh_occurrence.values()))) if sfh_occurrence else 0,
        "mfh_total_occurrence": int(round(sum(mfh_occurrence.values()))) if mfh_occurrence else 0,
        "loaded_refurbishment_buckets": 0,
        "missing_refurbishment_buckets": 0,
    }

    combo_name = _combo_name(sfh_k, mfh_k)
    mixed_buildings: List[Tuple[str, str, Path, float]] = (
        [(bid, "SFH", sfh_folder, sfh_occurrence.get(bid, 1.0)) for bid in sfh_ids]
        + [(bid, "MFH", mfh_folder, mfh_occurrence.get(bid, 1.0)) for bid in mfh_ids]
    )
    for building_id, building_type, folder, target_occurrence in mixed_buildings:
        building_dict[building_id] = {}
        for refurbish in refurbishment_strategies:
            try:
                recs = _load_building_result_records(
                    result_folder=folder,
                    building_id=building_id,
                    refurbish=refurbish,
                    optimization_strategies=optimization_strategies,
                )
                recs = _scale_building_records_to_occurrence(
                    recs=recs,
                    building_id=building_id,
                    target_occurrence=target_occurrence,
                    print_scaling=print_scaling,
                    print_scaling_only_changed=print_scaling_only_changed,
                    scaling_context=(
                        f"combo={combo_name} type={building_type} "
                        f"refurb={refurbish}"
                    ),
                )
            except Exception:
                recs = {}
            building_dict[building_id][refurbish] = recs
            if recs:
                stats["loaded_refurbishment_buckets"] += 1
            else:
                stats["missing_refurbishment_buckets"] += 1

    return building_dict, stats


def _save_combination_outputs(
    output_dir: Path,
    building_dict: Dict[str, Dict[str, Dict[Any, Dict[str, Any]]]],
    per_building_front: Dict[str, List[Dict[str, Any]]],
    combined_front: List[Dict[str, Any]],
    meta: Dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "building_dict.pkl", "wb") as fh:
        pickle.dump(building_dict, fh, protocol=pickle.HIGHEST_PROTOCOL)
    with open(output_dir / "per_building_front.pkl", "wb") as fh:
        pickle.dump(per_building_front, fh, protocol=pickle.HIGHEST_PROTOCOL)
    with open(output_dir / "combined_front.pkl", "wb") as fh:
        pickle.dump(combined_front, fh, protocol=pickle.HIGHEST_PROTOCOL)
    with open(output_dir / "combined_package.pkl", "wb") as fh:
        pickle.dump([building_dict, per_building_front, combined_front], fh, protocol=pickle.HIGHEST_PROTOCOL)
    with open(output_dir / "meta.pkl", "wb") as fh:
        pickle.dump(meta, fh, protocol=pickle.HIGHEST_PROTOCOL)


def _process_single_combination(task: Tuple[str, str, Any, Any, List[str], List[str], str, bool, bool]) -> Dict[str, Any]:
    (
        cluster_root_raw,
        output_root_raw,
        sfh_k,
        mfh_k,
        refurbishment_strategies,
        optimization_strategies,
        ueu_case,
        print_scaling,
        print_scaling_only_changed,
    ) = task
    cluster_root = Path(cluster_root_raw)
    output_root = Path(output_root_raw)
    combo = _combo_name(sfh_k, mfh_k)

    try:
        building_dict, stats = _build_decentralized_building_dict_for_combination(
            cluster_root=cluster_root,
            sfh_k=sfh_k,
            mfh_k=mfh_k,
            refurbishment_strategies=refurbishment_strategies,
            optimization_strategies=optimization_strategies,
            print_scaling=print_scaling,
            print_scaling_only_changed=print_scaling_only_changed,
        )
    except Exception as exc:
        return {
            "combo": combo,
            "sfh_k": _k_token(sfh_k),
            "mfh_k": _k_token(mfh_k),
            "status": "skipped",
            "reason": str(exc),
        }

    non_empty_buildings = [
        bid for bid, data in building_dict.items()
        if any(bool(data.get(ref, {})) for ref in refurbishment_strategies)
    ]
    if not non_empty_buildings:
        return {
            "combo": combo,
            "sfh_k": _k_token(sfh_k),
            "mfh_k": _k_token(mfh_k),
            "status": "skipped",
            "reason": "no result files found",
        }

    filtered_building_dict = {bid: building_dict[bid] for bid in non_empty_buildings}
    try:
        per_building_front, combined_front = combine_all_buildings(
            filtered_building_dict,
            refurbishment_strategies=refurbishment_strategies,
            tau=1e-9,
            eps_rel_each=(0.002, 0.002, 0.002),
            modes_each=("log", "log", "log"),
            eps_rel_merge=(0.008, 0.008, 0.008),
            modes_merge=("log", "log", "log"),
            max_points_after_each_merge=2000,
        )
    except Exception as exc:
        return {
            "combo": combo,
            "sfh_k": _k_token(sfh_k),
            "mfh_k": _k_token(mfh_k),
            "status": "failed",
            "reason": str(exc),
        }

    combo_output_dir = output_root / combo
    meta = {
        "ueu_case": ueu_case,
        "sfh_k": sfh_k,
        "mfh_k": mfh_k,
        "combo": combo,
        "stats": stats,
        "total_buildings": len(filtered_building_dict),
        "combined_front_size": len(combined_front),
    }
    _save_combination_outputs(
        output_dir=combo_output_dir,
        building_dict=filtered_building_dict,
        per_building_front=per_building_front,
        combined_front=combined_front,
        meta=meta,
    )
    return {
        "combo": combo,
        "sfh_k": _k_token(sfh_k),
        "mfh_k": _k_token(mfh_k),
        "status": "ok",
        "buildings": len(filtered_building_dict),
        "combined_front_size": len(combined_front),
        "output_dir": str(combo_output_dir),
    }


def _print_row_status(row: Dict[str, Any], index: int, total: int) -> None:
    status = str(row.get("status", "unknown"))
    combo = row.get("combo")
    if status == "ok":
        print(
            f"[{index}/{total}] ok {combo}: buildings={row.get('buildings')} "
            f"combined_front={row.get('combined_front_size')} -> {row.get('output_dir')}"
        )
    else:
        print(f"[{index}/{total}] {status} {combo}: {row.get('reason')}")


def run_all_combinations(
    ueu_case: str = UEU_CASE,
    sfh_k_values: Optional[Iterable[Any]] = None,
    mfh_k_values: Optional[Iterable[Any]] = None,
    refurbishment_strategies: Optional[Iterable[str]] = None,
    optimization_strategies: Optional[Iterable[str]] = None,
    workers: int = 1,
    max_tasks: Optional[int] = None,
    task_offset: int = 0,
    base_dir: Optional[str] = None,
    output_root_name: Optional[str] = None,
    print_scaling: bool = False,
    print_scaling_only_changed: bool = True,
) -> Path:
    sfh_values = list(sfh_k_values) if sfh_k_values is not None else list(DEFAULT_K_VALUES_TO_OPTIMIZE_SFH)
    mfh_values = list(mfh_k_values) if mfh_k_values is not None else list(DEFAULT_K_VALUES_TO_OPTIMIZE_MFH)
    refurbishments = list(refurbishment_strategies) if refurbishment_strategies is not None else list(REFURBISHMENT_STRATEGIES)
    optimization_modes = (
        list(optimization_strategies)
        if optimization_strategies is not None
        else list(OPTIMIZATION_STRATEGIES)
    )

    if not sfh_values:
        raise ValueError("No SFH k values configured.")
    if not mfh_values:
        raise ValueError("No MFH k values configured.")
    if not refurbishments:
        raise ValueError("No refurbishment strategies configured.")
    if not optimization_modes:
        raise ValueError("No optimization strategies configured.")
    if workers <= 0:
        raise ValueError("workers must be > 0")
    if max_tasks is not None and max_tasks <= 0:
        raise ValueError("max_tasks must be > 0 when provided")
    if task_offset < 0:
        raise ValueError("task_offset must be >= 0")

    data_base_dir = Path(base_dir).expanduser() if base_dir else BASE_DIR
    cluster_root = _resolve_cluster_root(str(ueu_case), data_base_dir)
    if not cluster_root.exists():
        raise FileNotFoundError(
            f"UEU folder not found: {cluster_root} (ueu_case={ueu_case}, base_dir={data_base_dir})"
        )

    output_dir_name = str(output_root_name).strip() if output_root_name is not None else ""
    if not output_dir_name:
        output_dir_name = DEFAULT_OUTPUT_ROOT_NAME
    output_root = cluster_root / output_dir_name
    output_root.mkdir(parents=True, exist_ok=True)

    all_combinations = [(sfh_k, mfh_k) for sfh_k in sfh_values for mfh_k in mfh_values]
    total_combinations = len(all_combinations)
    if task_offset > 0:
        all_combinations = all_combinations[task_offset:]
    if max_tasks is not None:
        all_combinations = all_combinations[:max_tasks]
    if not all_combinations:
        raise ValueError("No combinations to run after applying task_offset/max_tasks/filter settings.")

    print(f"UEU: {ueu_case}")
    print(f"Data base dir: {data_base_dir}")
    print(f"Cluster root: {cluster_root}")
    print(f"Output root: {output_root}")
    print(f"SFH K list: {sfh_values}")
    print(f"MFH K list: {mfh_values}")
    print(f"Refurbishments: {refurbishments}")
    print(f"Optimization strategies: {optimization_modes}")
    print(f"Workers: {workers}")
    print(f"Task offset: {task_offset}")
    print(f"Total combos available: {total_combinations}")
    print(f"Task count: {len(all_combinations)}")
    print(f"Print scaling: {print_scaling}")
    print(f"Print scaling only changed: {print_scaling_only_changed}")

    summary_rows = []
    tasks = [
        (
            str(cluster_root),
            str(output_root),
            sfh_k,
            mfh_k,
            refurbishments,
            optimization_modes,
            str(ueu_case),
            bool(print_scaling),
            bool(print_scaling_only_changed),
        )
        for sfh_k, mfh_k in all_combinations
    ]

    if workers > 1 and len(tasks) > 1:
        with multiprocessing.Pool(processes=workers) as pool:
            for index, row in enumerate(pool.imap_unordered(_process_single_combination, tasks), start=1):
                summary_rows.append(row)
                _print_row_status(row, index, len(tasks))
    else:
        for index, task in enumerate(tasks, start=1):
            row = _process_single_combination(task)
            summary_rows.append(row)
            _print_row_status(row, index, len(tasks))

    summary_df = pd.DataFrame(summary_rows)
    summary_csv = output_root / "summary.csv"
    summary_df.to_csv(summary_csv, index=False)
    print(f"\nDone. Summary: {summary_csv}")
    return summary_csv


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post-process decentralized k-combination results.")
    parser.add_argument("--host-name", type=str, default="unknown")
    parser.add_argument(
        "--workers",
        type=str,
        default="auto",
        help="Parallel worker processes. Use an integer, or False/auto for automatic sizing.",
    )
    parser.add_argument("--serial", action="store_true", help="Run selected combinations sequentially.")
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum number of SFH/MFH combination tasks to execute.",
    )
    parser.add_argument(
        "--task-offset",
        type=int,
        default=0,
        help="Start index in the deterministic SFHxMFH combination list.",
    )
    parser.add_argument(
        "--ueu-case",
        type=str,
        default=DEFAULT_UEU_CASE,
        help="UEU folder name below the example directory.",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=None,
        help="Base directory containing UEU folders. Defaults to this script directory.",
    )
    parser.add_argument(
        "--sfh-k",
        type=str,
        default=",".join(str(x) for x in DEFAULT_K_VALUES_TO_OPTIMIZE_SFH),
        help="Comma-separated SFH k values, e.g. reference,1,2,4",
    )
    parser.add_argument(
        "--mfh-k",
        type=str,
        default=",".join(str(x) for x in DEFAULT_K_VALUES_TO_OPTIMIZE_MFH),
        help="Comma-separated MFH k values, e.g. reference,1,2,3",
    )
    parser.add_argument(
        "--refurbishments",
        type=str,
        default=",".join(DEFAULT_REFURBISHMENT_STRATEGIES),
        help="Comma-separated refurbishment cases.",
    )
    parser.add_argument(
        "--optimization-strategies",
        type=str,
        default=",".join(DEFAULT_OPTIMIZATION_STRATEGIES),
        help="Comma-separated optimization strategy keys, e.g. co2",
    )
    parser.add_argument(
        "--output-root-name",
        type=str,
        default=None,
        help="Output folder name below the UEU folder. Defaults to date-based folder.",
    )
    parser.add_argument(
        "--print-scaling",
        action="store_true",
        help="Print scaling factor (used -> target -> factor) per building/combo/refurbishment.",
    )
    parser.add_argument(
        "--print-scaling-all",
        action="store_true",
        help="With --print-scaling, also print unchanged factors (factor=1).",
    )
    return parser


if __name__ == "__main__":
    parser = _build_arg_parser()
    args = parser.parse_args()

    sfh_requested = _parse_k_values(args.sfh_k)
    mfh_requested = _parse_k_values(args.mfh_k)
    selected_refurbishments = _parse_csv_values(args.refurbishments)
    selected_optimization = _parse_csv_values(args.optimization_strategies)

    if not sfh_requested:
        raise ValueError("No SFH k values provided via --sfh-k.")
    if not mfh_requested:
        raise ValueError("No MFH k values provided via --mfh-k.")
    if not selected_refurbishments:
        raise ValueError("No refurbishments provided via --refurbishments.")
    if not selected_optimization:
        raise ValueError("No optimization strategies provided via --optimization-strategies.")

    workers = _resolve_workers(args.workers, serial=args.serial)

    print(
        f"host={args.host_name} workers={workers} task_offset={args.task_offset} max_tasks={args.max_tasks} "
        f"ueu_case={args.ueu_case} base_dir={args.base_dir or str(BASE_DIR)} "
        f"sfh_k={[ _format_k_for_log(x) for x in sfh_requested ]} "
        f"mfh_k={[ _format_k_for_log(x) for x in mfh_requested ]} "
        f"refurbishments={selected_refurbishments} optimization_strategies={selected_optimization} "
        f"print_scaling={args.print_scaling} print_scaling_all={args.print_scaling_all}"
    )

    run_all_combinations(
        ueu_case=args.ueu_case,
        sfh_k_values=sfh_requested,
        mfh_k_values=mfh_requested,
        refurbishment_strategies=selected_refurbishments,
        optimization_strategies=selected_optimization,
        workers=workers,
        max_tasks=args.max_tasks,
        task_offset=args.task_offset,
        base_dir=args.base_dir,
        output_root_name=args.output_root_name,
        print_scaling=args.print_scaling,
        print_scaling_only_changed=(not args.print_scaling_all),
    )
