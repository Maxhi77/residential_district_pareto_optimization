from __future__ import annotations

import multiprocessing
import os
from typing import Callable

from oemof.thermal_building_model.helpers.cluster_io import (
    collect_building_ids_for_k,
    discover_available_k_values,
)
from oemof.thermal_building_model.helpers.optimization_io import (
    atomic_pickle_dump,
    co2_factor_to_suffix,
    dedupe_keep_order,
    format_k_for_log,
    is_reference_k,
    k_to_folder_token,
    normalize_k_for_key,
)
from oemof.thermal_building_model.helpers.price_scenarios import (
    normalize_price_scenario_name,
    scenario_output_cluster_name,
)
from oemof.thermal_building_model.helpers.result_helpers import (
    build_result_entries,
    compute_co2_target,
    compute_peak_target,
    get_result_file_bases,
    get_worker_result_paths,
    missing_co2_factors,
)


def run_co2_factor_for_context(group_key, co2_reduction_factor, context, *, run_model: Callable):
    data = context["data"]
    aggregation1 = context["aggregation1"]
    t1_agg = context["t1_agg"]
    data_classes_comp = context["data_classes_comp"]
    combined_cluster = context["combined_cluster"]
    building_id_in_cluster = context["building_id_in_cluster"]
    cluster_occurence = context["cluster_occurence"]
    heat_demand_worst_case = context["heat_demand_worst_case"]
    refurbish = context["refurbish"]
    peak_reduction_factors = context["peak_reduction_factors"]
    co2_reference = context["co2_reference"]
    file_path_base = context["file_path_base"]
    simple_file_path_base = context["simple_file_path_base"]
    price_scenario_name = context["price_scenario_name"]
    price_scenario = context["price_scenario"]
    combined_optimization = context.get("combined_optimization", False)
    worker_file_path, worker_simple_file_path = get_worker_result_paths(
        file_path_base,
        simple_file_path_base,
        co2_reduction_factor,
    )

    if os.path.exists(worker_simple_file_path):
        return group_key, worker_file_path, worker_simple_file_path

    ref = "co2"
    co2_new = compute_co2_target(co2_reference, co2_reduction_factor)
    first_co2_run_in_peak_loop = True
    peak_reference = None

    worker_results = {}
    worker_simple_results = {}

    for peak_reduction_factor in peak_reduction_factors:
        if first_co2_run_in_peak_loop:
            peak_new = False
        else:
            peak_new = compute_peak_target(peak_reference, peak_reduction_factor)

        final_results, co2, time = run_model(
            co2_new,
            peak_new,
            refurbish,
            data,
            aggregation1,
            t1_agg,
            data_classes_comp,
            combined_cluster,
            building_id_in_cluster,
            cluster_occurence,
            heat_demand_worst_case,
            price_scenario=price_scenario,
            combined_optimization=combined_optimization,
        )

        key = (co2_reduction_factor, peak_reduction_factor, refurbish, ref)
        full_entry, simple_entry = build_result_entries(
            final_results,
            co2,
            peak_reduction_factor,
            refurbish,
            time,
            price_scenario_name,
        )
        worker_results[key] = full_entry
        worker_simple_results[key] = simple_entry

        if final_results is None:
            if first_co2_run_in_peak_loop:
                first_co2_run_in_peak_loop = False
                peak_reference = False
            break

        if first_co2_run_in_peak_loop:
            first_co2_run_in_peak_loop = False
            peak_reference = full_entry["peak"]

    atomic_pickle_dump(worker_file_path, worker_results)
    atomic_pickle_dump(worker_simple_file_path, worker_simple_results)

    return group_key, worker_file_path, worker_simple_file_path


def normalize_price_scenarios_to_run(price_scenarios_to_run, default_price_scenarios):
    if price_scenarios_to_run is None:
        return list(default_price_scenarios)
    return dedupe_keep_order(
        [normalize_price_scenario_name(s) for s in price_scenarios_to_run]
    )


def resolve_k_values_for_cluster(
    selected_k_values,
    available_k_values,
    label,
    cluster_name,
    reference_available,
):
    if selected_k_values is None:
        return available_k_values

    resolved = []
    missing_numeric = []
    request_reference = False
    for raw in selected_k_values:
        if is_reference_k(raw):
            request_reference = True
            continue
        try:
            k_int = int(raw)
        except Exception:
            print(f"Skipped invalid {label} k value for {cluster_name}: {raw}")
            continue
        if k_int in available_k_values:
            resolved.append(k_int)
        else:
            missing_numeric.append(k_int)

    if missing_numeric:
        print(f"Skipped missing {label} k values for {cluster_name}: {sorted(set(missing_numeric))}")

    if request_reference:
        if reference_available:
            resolved.append("reference")
        else:
            print(f"Skipped {label} reference for {cluster_name}: {cluster_name}.gpkg not found")

    out = []
    seen = set()
    for item in resolved:
        marker = item if isinstance(item, str) else int(item)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def _append_pending_co2_tasks(
    *,
    task_list,
    group_contexts,
    group_key,
    prepared,
    missing_factors,
    skip_message,
):
    missing_set = set(missing_factors)
    pending_factors = [
        factor for factor in prepared["co2_reduction_factors"] if factor in missing_set
    ]
    if not pending_factors:
        print(skip_message)
        return

    group_contexts[group_key] = prepared["worker_context"]
    for co2_reduction_factor in pending_factors:
        task_list.append((group_key, co2_reduction_factor))


def _build_combined_co2_tasks(
    *,
    base_path,
    result_check_root,
    cluster_name,
    k_values_to_run_sfh,
    k_values_to_run_mfh,
    price_scenarios_to_run,
    task_list,
    group_contexts,
    refurbishment,
    ev_mode,
    default_co2_reduction_factors,
    prepare_group_context,
):
    for sfh_k_value in k_values_to_run_sfh:
        for mfh_k_value in k_values_to_run_mfh:
            sfh_buildings = collect_building_ids_for_k(
                base_path,
                cluster_name,
                sfh_k_value,
                building_type="SFH",
            )
            mfh_buildings = collect_building_ids_for_k(
                base_path,
                cluster_name,
                mfh_k_value,
                building_type="MFH",
            )
            if not sfh_buildings and not mfh_buildings:
                print(
                    f"skip empty combined selection: {cluster_name} | "
                    f"sfh_k={format_k_for_log(sfh_k_value)} | mfh_k={format_k_for_log(mfh_k_value)}"
                )
                continue

            k_pair = (sfh_k_value, mfh_k_value)
            combined_building_id = (
                f"combined_sfh_{k_to_folder_token(sfh_k_value)}"
                f"_mfh_{k_to_folder_token(mfh_k_value)}"
            )
            for price_scenario_name in price_scenarios_to_run:
                output_cluster_name = scenario_output_cluster_name(cluster_name, price_scenario_name)
                for refurbish in refurbishment:
                    check_file_path_base, check_simple_file_path_base = get_result_file_bases(
                        result_check_root,
                        output_cluster_name,
                        k_pair,
                        "COMBINED",
                        refurbish,
                        ev_mode,
                        combined_building_id,
                    )
                    missing_factors = missing_co2_factors(
                        check_file_path_base,
                        check_simple_file_path_base,
                        default_co2_reduction_factors,
                    )
                    if not missing_factors:
                        print(
                            f"skip existing: {cluster_name} | scenario={price_scenario_name} | COMBINED | "
                            f"k={format_k_for_log(k_pair)} | {combined_building_id} | {refurbish}"
                        )
                        continue

                    try:
                        prepared = prepare_group_context(
                            refurbish,
                            combined_building_id,
                            cluster_name,
                            k_pair,
                            building_type="COMBINED",
                            price_scenario_name=price_scenario_name,
                            output_cluster_name=output_cluster_name,
                            combined_optimization=True,
                            sfh_k_value=sfh_k_value,
                            mfh_k_value=mfh_k_value,
                        )
                    except Exception as exc:
                        print(
                            f"skip failed prepare: {cluster_name} | scenario={price_scenario_name} | COMBINED | "
                            f"k={format_k_for_log(k_pair)} | {combined_building_id} | {refurbish} | {exc}"
                        )
                        continue

                    group_key = (
                        cluster_name,
                        "COMBINED",
                        normalize_k_for_key(k_pair),
                        combined_building_id,
                        refurbish,
                        normalize_price_scenario_name(price_scenario_name),
                    )
                    _append_pending_co2_tasks(
                        task_list=task_list,
                        group_contexts=group_contexts,
                        group_key=group_key,
                        prepared=prepared,
                        missing_factors=missing_factors,
                        skip_message=(
                            f"skip existing after-prepare: {cluster_name} | scenario={price_scenario_name} "
                            f"| COMBINED | k={format_k_for_log(k_pair)} | {combined_building_id} | {refurbish}"
                        ),
                    )


def _build_single_building_co2_tasks(
    *,
    base_path,
    result_check_root,
    cluster_name,
    k_values_to_run_sfh,
    k_values_to_run_mfh,
    price_scenarios_to_run,
    task_list,
    group_contexts,
    refurbishment,
    ev_mode,
    default_co2_reduction_factors,
    prepare_group_context,
):
    for building_type, k_values_to_run in (("SFH", k_values_to_run_sfh), ("MFH", k_values_to_run_mfh)):
        for k_value in k_values_to_run:
            building_in_cluster = collect_building_ids_for_k(
                base_path,
                cluster_name,
                k_value,
                building_type=building_type,
            )
            for price_scenario_name in price_scenarios_to_run:
                output_cluster_name = scenario_output_cluster_name(cluster_name, price_scenario_name)
                for refurbish in refurbishment:
                    for building_id_in_cluster in building_in_cluster:
                        check_file_path_base, check_simple_file_path_base = get_result_file_bases(
                            result_check_root,
                            output_cluster_name,
                            k_value,
                            building_type,
                            refurbish,
                            ev_mode,
                            building_id_in_cluster,
                        )
                        missing_factors = missing_co2_factors(
                            check_file_path_base,
                            check_simple_file_path_base,
                            default_co2_reduction_factors,
                        )
                        if not missing_factors:
                            print(
                                f"skip existing: {cluster_name} | scenario={price_scenario_name} | {building_type} | "
                                f"k={format_k_for_log(k_value)} | {building_id_in_cluster} | {refurbish}"
                            )
                            continue

                        try:
                            prepared = prepare_group_context(
                                refurbish,
                                building_id_in_cluster,
                                cluster_name,
                                k_value,
                                building_type=building_type,
                                price_scenario_name=price_scenario_name,
                                output_cluster_name=output_cluster_name,
                            )
                        except Exception as exc:
                            print(
                                f"skip failed prepare: {cluster_name} | scenario={price_scenario_name} | "
                                f"{building_type} | k={format_k_for_log(k_value)} | "
                                f"{building_id_in_cluster} | {refurbish} | {exc}"
                            )
                            continue

                        group_key = (
                            cluster_name,
                            building_type,
                            normalize_k_for_key(k_value),
                            building_id_in_cluster,
                            refurbish,
                            normalize_price_scenario_name(price_scenario_name),
                        )
                        _append_pending_co2_tasks(
                            task_list=task_list,
                            group_contexts=group_contexts,
                            group_key=group_key,
                            prepared=prepared,
                            missing_factors=missing_factors,
                            skip_message=(
                                f"skip existing after-prepare: {cluster_name} | scenario={price_scenario_name} "
                                f"| {building_type} | k={format_k_for_log(k_value)} | "
                                f"{building_id_in_cluster} | {refurbish}"
                            ),
                        )


def run_co2_tasks(task_list, group_contexts, processes, *, set_worker_context, worker, clear_worker_context):
    if processes is None:
        processes = max(1, multiprocessing.cpu_count() // 2)

    if "fork" in multiprocessing.get_all_start_methods():
        mp_ctx = multiprocessing.get_context("fork")
        with mp_ctx.Pool(processes=processes, initializer=set_worker_context, initargs=(group_contexts,)) as pool:
            for group_key, worker_file_path, _ in pool.imap_unordered(worker, task_list):
                print(f"saved {group_key} -> {worker_file_path}")
    else:
        print("No 'fork' start method available. Falling back to serial co2/refurbish task execution.")
        set_worker_context(group_contexts)
        for task in task_list:
            group_key, worker_file_path, _ = worker(task)
            print(f"saved {group_key} -> {worker_file_path}")
        clear_worker_context()


def run_cluster_refurbish_co2_parallel(
    *,
    cluster_name,
    processes,
    base_path,
    result_check_root,
    selected_k_values=None,
    selected_k_values_sfh=None,
    selected_k_values_mfh=None,
    price_scenarios_to_run=None,
    combined_optimization=False,
    default_price_scenarios=None,
    default_co2_reduction_factors=None,
    refurbishment=None,
    ev_mode="no_EV",
    prepare_group_context=None,
    set_worker_context=None,
    clear_worker_context=None,
    worker=None,
):
    if default_price_scenarios is None:
        default_price_scenarios = []
    if default_co2_reduction_factors is None:
        default_co2_reduction_factors = []
    if refurbishment is None:
        refurbishment = []
    if prepare_group_context is None:
        raise ValueError("prepare_group_context is required.")
    if set_worker_context is None or clear_worker_context is None or worker is None:
        raise ValueError("set_worker_context, clear_worker_context, and worker are required.")

    price_scenarios_to_run = normalize_price_scenarios_to_run(
        price_scenarios_to_run,
        default_price_scenarios,
    )
    if not price_scenarios_to_run:
        print(f"No price scenarios selected for cluster {cluster_name}")
        return

    if selected_k_values is not None:
        if selected_k_values_sfh is None:
            selected_k_values_sfh = selected_k_values
        if selected_k_values_mfh is None:
            selected_k_values_mfh = selected_k_values

    available_k_values_sfh = discover_available_k_values(base_path, cluster_name, building_type="SFH")
    available_k_values_mfh = discover_available_k_values(base_path, cluster_name, building_type="MFH")
    reference_available = os.path.exists(os.path.join(base_path, cluster_name, f"{cluster_name}.gpkg"))
    if not available_k_values_sfh and not available_k_values_mfh and not reference_available:
        print(f"No SFH/MFH k-folders and no reference gpkg found for cluster {cluster_name}")
        return

    k_values_to_run_sfh = resolve_k_values_for_cluster(
        selected_k_values_sfh,
        available_k_values_sfh,
        "SFH",
        cluster_name,
        reference_available,
    )
    k_values_to_run_mfh = resolve_k_values_for_cluster(
        selected_k_values_mfh,
        available_k_values_mfh,
        "MFH",
        cluster_name,
        reference_available,
    )
    if not k_values_to_run_sfh and not k_values_to_run_mfh:
        print(f"No runnable SFH/MFH k values for cluster {cluster_name}")
        return

    task_list = []
    group_contexts = {}
    if combined_optimization:
        if not k_values_to_run_sfh or not k_values_to_run_mfh:
            print(
                f"Combined optimization needs both SFH and MFH k values for cluster {cluster_name}. "
                f"sfh={k_values_to_run_sfh}, mfh={k_values_to_run_mfh}"
            )
            return
        _build_combined_co2_tasks(
            base_path=base_path,
            result_check_root=result_check_root,
            cluster_name=cluster_name,
            k_values_to_run_sfh=k_values_to_run_sfh,
            k_values_to_run_mfh=k_values_to_run_mfh,
            price_scenarios_to_run=price_scenarios_to_run,
            task_list=task_list,
            group_contexts=group_contexts,
            refurbishment=refurbishment,
            ev_mode=ev_mode,
            default_co2_reduction_factors=default_co2_reduction_factors,
            prepare_group_context=prepare_group_context,
        )
    else:
        _build_single_building_co2_tasks(
            base_path=base_path,
            result_check_root=result_check_root,
            cluster_name=cluster_name,
            k_values_to_run_sfh=k_values_to_run_sfh,
            k_values_to_run_mfh=k_values_to_run_mfh,
            price_scenarios_to_run=price_scenarios_to_run,
            task_list=task_list,
            group_contexts=group_contexts,
            refurbishment=refurbishment,
            ev_mode=ev_mode,
            default_co2_reduction_factors=default_co2_reduction_factors,
            prepare_group_context=prepare_group_context,
        )

    if not task_list:
        print(f"No runnable tasks for cluster {cluster_name}")
        return

    run_co2_tasks(
        task_list,
        group_contexts,
        processes,
        set_worker_context=set_worker_context,
        clear_worker_context=clear_worker_context,
        worker=worker,
    )


def run_co2_peak_sweep_to_files(
    *,
    run_case,
    co2_reference,
    peak_reference,
    co2_reduction_factors,
    peak_reduction_factors,
    result_prefix,
    scenario_name,
    reference_label="co2",
):
    for co2_reduction_factor in co2_reduction_factors:
        first_co2_run_in_peak_loop = True
        results_for_co2_step_full = {}
        results_for_co2_step_simple = {}
        co2_new = compute_co2_target(co2_reference, co2_reduction_factor)
        print("START PEAK LOOP")

        for peak_reduction_factor in peak_reduction_factors:
            print("co2_reduction_factor: " + str(co2_reduction_factor))
            print("peak_reduction_factor: " + str(peak_reduction_factor))
            if first_co2_run_in_peak_loop:
                peak_new = False
            else:
                peak_new = compute_peak_target(peak_reference, peak_reduction_factor)

            final_results, co2, time = run_case(co2_new, peak_new)
            key = (co2_reduction_factor, peak_reduction_factor, reference_label)
            full_entry, simple_entry = build_result_entries(
                final_results=final_results,
                co2=co2,
                peak_reduction_factor=peak_reduction_factor,
                refurbish=scenario_name,
                time=time,
            )
            results_for_co2_step_full[key] = full_entry
            results_for_co2_step_simple[key] = simple_entry

            if final_results is None:
                if first_co2_run_in_peak_loop:
                    first_co2_run_in_peak_loop = False
                    peak_reference = False
                break

            if first_co2_run_in_peak_loop:
                first_co2_run_in_peak_loop = False
                peak_reference = full_entry["peak"]

        co2_suffix = co2_factor_to_suffix(co2_reduction_factor)
        full_file_path = result_prefix + "_co2_" + co2_suffix + ".pkl"
        simple_file_path = result_prefix + "_simple_co2_" + co2_suffix + ".pkl"
        atomic_pickle_dump(full_file_path, results_for_co2_step_full)
        atomic_pickle_dump(simple_file_path, results_for_co2_step_simple)
        print(f"saved co2 step {co2_reduction_factor} -> {full_file_path}")
