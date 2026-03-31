import pickle
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd

from pareto_optimal_help_functions import combine_all_buildings


BASE_DIR = Path(__file__).resolve().parent
UEU_CASE = "processed_bds_in_DENI03403000SEC5658"
REFURBISHMENT_STRATEGIES = [
    "no_refurbishment",
    "usual_refurbishment",
    "advanced_refurbishment",
    "GEG_standard",
]
OPTIMIZATION_STRATEGIES = ["co2"]

DEFAULT_K_VALUES_TO_OPTIMIZE_SFH = ["reference", 1, 2, 4, 6, 8, 10, 14, 18]
DEFAULT_K_VALUES_TO_OPTIMIZE_MFH = ["reference", 1, 2, 3, 4, 5, 6]

TODAY_DATE = date.today().strftime("%Y_%m_%d")
OUTPUT_ROOT_NAME = f"post_processed_dec_k_combinations_{TODAY_DATE}"


def _is_reference_k(k_value: Any) -> bool:
    return isinstance(k_value, str) and k_value.lower() == "reference"


def _k_token(k_value: Any) -> str:
    if _is_reference_k(k_value):
        return "reference"
    return f"k{int(k_value):02d}"


def _combo_name(sfh_k: Any, mfh_k: Any) -> str:
    return f"sfh_{_k_token(sfh_k)}_mfh_{_k_token(mfh_k)}"


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


def _scale_building_records_to_occurrence(
    recs: Dict[Any, Dict[str, Any]],
    building_id: str,
    target_occurrence: float,
) -> Dict[Any, Dict[str, Any]]:
    if not recs:
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

    mixed_buildings: List[Tuple[str, Path, float]] = (
        [(bid, sfh_folder, sfh_occurrence.get(bid, 1.0)) for bid in sfh_ids]
        + [(bid, mfh_folder, mfh_occurrence.get(bid, 1.0)) for bid in mfh_ids]
    )
    for building_id, folder, target_occurrence in mixed_buildings:
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


def run_all_combinations() -> None:
    cluster_root = BASE_DIR / UEU_CASE
    if not cluster_root.exists():
        raise FileNotFoundError(f"UEU folder not found: {cluster_root}")

    output_root = cluster_root / OUTPUT_ROOT_NAME
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"UEU: {UEU_CASE}")
    print(f"Output root: {output_root}")
    print(f"SFH K list: {DEFAULT_K_VALUES_TO_OPTIMIZE_SFH}")
    print(f"MFH K list: {DEFAULT_K_VALUES_TO_OPTIMIZE_MFH}")

    summary_rows = []

    for sfh_k in DEFAULT_K_VALUES_TO_OPTIMIZE_SFH:
        for mfh_k in DEFAULT_K_VALUES_TO_OPTIMIZE_MFH:
            combo = _combo_name(sfh_k, mfh_k)
            print(f"\n--- Processing {combo} ---")

            try:
                building_dict, stats = _build_decentralized_building_dict_for_combination(
                    cluster_root=cluster_root,
                    sfh_k=sfh_k,
                    mfh_k=mfh_k,
                    refurbishment_strategies=REFURBISHMENT_STRATEGIES,
                    optimization_strategies=OPTIMIZATION_STRATEGIES,
                )
            except Exception as exc:
                print(f"skip {combo}: {exc}")
                summary_rows.append(
                    {
                        "combo": combo,
                        "sfh_k": _k_token(sfh_k),
                        "mfh_k": _k_token(mfh_k),
                        "status": "skipped",
                        "reason": str(exc),
                    }
                )
                continue

            non_empty_buildings = [
                bid for bid, data in building_dict.items()
                if any(bool(data.get(ref, {})) for ref in REFURBISHMENT_STRATEGIES)
            ]
            if not non_empty_buildings:
                print(f"skip {combo}: no result files found.")
                summary_rows.append(
                    {
                        "combo": combo,
                        "sfh_k": _k_token(sfh_k),
                        "mfh_k": _k_token(mfh_k),
                        "status": "skipped",
                        "reason": "no result files found",
                    }
                )
                continue

            filtered_building_dict = {bid: building_dict[bid] for bid in non_empty_buildings}
            per_building_front, combined_front = combine_all_buildings(
                filtered_building_dict,
                refurbishment_strategies=REFURBISHMENT_STRATEGIES,
                tau=1e-9,
                eps_rel_each=(0.002, 0.002, 0.002),
                modes_each=("log", "log", "log"),
                eps_rel_merge=(0.008, 0.008, 0.008),
                modes_merge=("log", "log", "log"),
                max_points_after_each_merge=1000,
            )

            combo_output_dir = output_root / combo
            meta = {
                "ueu_case": UEU_CASE,
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
            print(
                f"saved {combo}: buildings={len(filtered_building_dict)} "
                f"combined_front={len(combined_front)} -> {combo_output_dir}"
            )
            summary_rows.append(
                {
                    "combo": combo,
                    "sfh_k": _k_token(sfh_k),
                    "mfh_k": _k_token(mfh_k),
                    "status": "ok",
                    "buildings": len(filtered_building_dict),
                    "combined_front_size": len(combined_front),
                    "output_dir": str(combo_output_dir),
                }
            )

    summary_df = pd.DataFrame(summary_rows)
    summary_csv = output_root / "summary.csv"
    summary_df.to_csv(summary_csv, index=False)
    print(f"\nDone. Summary: {summary_csv}")


if __name__ == "__main__":
    run_all_combinations()
