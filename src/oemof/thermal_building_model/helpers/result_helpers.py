from __future__ import annotations

import os
from typing import Any

from oemof.thermal_building_model.helpers.optimization_io import (
    co2_factor_to_suffix,
    is_reference_k,
    k_to_folder_token,
)


def compute_co2_target(co2_ref: float, factor: float) -> float:
    if co2_ref > 0:
        return co2_ref * factor
    return co2_ref * (1 + 1 - factor)


def compute_peak_target(peak_ref: float, factor: float) -> float:
    return peak_ref * factor


def build_result_entries(
    final_results: dict[str, Any] | None,
    co2: float | None,
    peak_reduction_factor: float | None,
    refurbish: str | None,
    time: float | None,
    price_scenario_name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    include_price_scenario = price_scenario_name is not None

    if final_results is None:
        full_entry = {
            "results": None,
            "co2": None,
            "peak_reduction_factor": None,
            "refurbish": None,
            "totex": None,
            "peak": None,
            "time": None,
        }
        simple_entry = {
            "co2": None,
            "peak_reduction_factor": None,
            "refurbish": None,
            "totex": None,
            "peak": None,
            "time": None,
        }
        if include_price_scenario:
            full_entry["price_scenario"] = price_scenario_name
            simple_entry["price_scenario"] = price_scenario_name
        else:
            full_entry.update(
                {
                    "electricity_grid": None,
                    "peak_from_grid": None,
                    "peak_into_grid": None,
                }
            )
            simple_entry.update(
                {
                    "electricity_grid": None,
                    "peak_from_grid": None,
                    "peak_into_grid": None,
                }
            )
        return full_entry, simple_entry

    peak_from_grid = final_results["Electricity"]["peak_from_grid"]
    peak_into_grid = final_results["Electricity"]["peak_into_grid"]
    peak = max(peak_from_grid, peak_into_grid)
    totex = final_results["totex"]
    common = {
        "co2": co2,
        "peak_reduction_factor": peak_reduction_factor,
        "refurbish": refurbish,
        "totex": totex,
        "peak": peak,
        "electricity_grid": final_results["Electricity"],
        "peak_from_grid": peak_from_grid,
        "peak_into_grid": peak_into_grid,
        "time": time,
    }
    if include_price_scenario:
        common["price_scenario"] = price_scenario_name

    full_entry = {"results": final_results, **common}
    simple_entry = dict(common)
    return full_entry, simple_entry


def get_worker_result_paths(
    file_path_base: str,
    simple_file_path_base: str,
    co2_reduction_factor: float,
) -> tuple[str, str]:
    suffix = co2_factor_to_suffix(co2_reduction_factor)
    return (
        file_path_base + "_co2_" + suffix + ".pkl",
        simple_file_path_base + "_co2_" + suffix + ".pkl",
    )


def get_result_output_dir(root_path, cluster_name, k_value, building_type):
    cluster_root = os.path.join(root_path, cluster_name)
    if building_type == "COMBINED":
        if not isinstance(k_value, (tuple, list)) or len(k_value) != 2:
            raise ValueError(f"COMBINED output requires k pair (sfh_k, mfh_k), got '{k_value}'")
        sfh_k, mfh_k = k_value
        sfh_token = k_to_folder_token(sfh_k)
        mfh_token = k_to_folder_token(mfh_k)
        return os.path.join(cluster_root, f"combined_cluster_sfh_{sfh_token}_mfh_{mfh_token}")

    if is_reference_k(k_value):
        return os.path.join(cluster_root, "reference")

    k_token = k_to_folder_token(k_value)
    if building_type == "SFH":
        return os.path.join(cluster_root, f"sfh_cluster_{k_token}")
    if building_type == "MFH":
        return os.path.join(cluster_root, f"mfh_cluster_{k_token}")
    raise ValueError(f"Unsupported building_type '{building_type}'")


def get_result_file_bases(root_path, cluster_name, k_value, building_type, refurbish, ev, building_id_in_cluster):
    output_dir = get_result_output_dir(root_path, cluster_name, k_value, building_type)
    base_filename = "results_dec_" + str(refurbish) + "_" + str(ev) + "_" + str(building_id_in_cluster)
    simple_base_filename = (
        "simple_results_dec_" + str(refurbish) + "_" + str(ev) + "_" + str(building_id_in_cluster)
    )
    return os.path.join(output_dir, base_filename), os.path.join(output_dir, simple_base_filename)


def missing_co2_factors(
    file_path_base: str,
    simple_file_path_base: str,
    co2_reduction_factors,
) -> list[float]:
    missing = []
    for co2_reduction_factor in co2_reduction_factors:
        _, worker_simple_file_path = get_worker_result_paths(
            file_path_base,
            simple_file_path_base,
            co2_reduction_factor,
        )
        if not os.path.exists(worker_simple_file_path):
            missing.append(co2_reduction_factor)
    return missing
