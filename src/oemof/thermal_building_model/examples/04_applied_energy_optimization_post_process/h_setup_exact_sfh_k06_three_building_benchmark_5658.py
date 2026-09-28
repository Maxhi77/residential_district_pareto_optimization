from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import os
import pickle
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from oemof.thermal_building_model.helpers.pareto_optimal_help_functions import (  # noqa: E402
    _compute_real_peak_from_selection,
    collect_options_for_building,
    pareto_prune_building,
    pareto_prune_points,
)


ARCHIVE_UEU_ROOT = (
    Path("M:/04_ArchivMA/Hillen Maximilian")
    / ("Ver" + chr(0x00F6) + "ffentlichungen")
    / "UEU"
)
DEFAULT_DATA_ROOT = ARCHIVE_UEU_ROOT / "processed_bds_in_DENI03403000SEC5658"
DEFAULT_BUILDING_DICT = (
    DEFAULT_DATA_ROOT
    / "post_processed_dec_k_combinations_2026_07_07"
    / "sfh_k06_mfh_k01"
    / "building_dict.pkl"
)
DEFAULT_OUTPUT_DIR = (
    SCRIPT_DIR
    / "pareto_recombination_validation_5658"
    / "sfh_k06_exact_3_buildings_15m"
)
DEFAULT_MAX_EXACT_COMBINATIONS = 15_000_000
DEFAULT_REQUESTED_BUILDINGS = 3
OBJECTIVE_KEYS = ("co2", "peak", "totex")
REFURBISHMENT_STRATEGIES = [
    "no_refurbishment",
    "usual_refurbishment",
    "advanced_refurbishment",
    "GEG_standard",
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


def _write_json(path: Path, payload: Any) -> None:
    _mkdir(path.parent)
    with open(_to_long_path(path), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    _mkdir(path.parent)
    if not rows:
        return
    columns = list(rows[0].keys())
    with open(_to_long_path(path), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _building_ids_from_result_folder(result_folder: Path) -> set[str]:
    pattern = re.compile(
        r"^(?:simple_)?results_dec_.+?_(?:no_EV|yes_EV)_(?P<building_id>DEN[^_]+)_co2_.+\.pkl$"
    )
    ids = set()
    for path in result_folder.glob("*.pkl"):
        match = pattern.match(path.name)
        if match:
            ids.add(match.group("building_id"))
    return ids


def _product(values: Iterable[int]) -> int:
    out = 1
    for value in values:
        out *= int(value)
    return out


def _raw_option_count(building_data: dict[str, dict[Any, dict[str, Any]]]) -> int:
    return len(collect_options_for_building(building_data, REFURBISHMENT_STRATEGIES))


def _local_pareto_options(building_data: dict[str, dict[Any, dict[str, Any]]]) -> list[dict[str, Any]]:
    if _raw_option_count(building_data) == 0:
        return []
    return pareto_prune_building(building_data, REFURBISHMENT_STRATEGIES, tau=1e-9)


def _count_by_refurbishment(
    building_data: dict[str, dict[Any, dict[str, Any]]],
) -> dict[str, int]:
    return {
        refurbish: len(building_data.get(refurbish, {}))
        for refurbish in REFURBISHMENT_STRATEGIES
    }


def _build_sfh_rows(
    building_dict: dict[str, dict[str, dict[Any, dict[str, Any]]]],
    data_root: Path,
    sfh_folder: str,
    mfh_folder: str,
) -> list[dict[str, Any]]:
    sfh_ids = _building_ids_from_result_folder(data_root / sfh_folder)
    mfh_ids = _building_ids_from_result_folder(data_root / mfh_folder)
    rows = []
    for building_id in sorted(building_dict):
        in_sfh_folder = building_id in sfh_ids
        in_mfh_folder = building_id in mfh_ids
        if not in_sfh_folder or in_mfh_folder:
            continue
        building_data = building_dict[building_id]
        raw_count = _raw_option_count(building_data)
        local_count = len(_local_pareto_options(building_data))
        rows.append(
            {
                "building_id": building_id,
                "building_type": "sfh",
                "raw_options": raw_count,
                "local_pareto_options": local_count,
                **{
                    f"{refurbish}_entries": count
                    for refurbish, count in _count_by_refurbishment(building_data).items()
                },
            }
        )
    return rows


def _choose_exact_subset(
    rows: Sequence[dict[str, Any]],
    requested_buildings: int,
    max_combinations: int,
) -> tuple[list[dict[str, Any]], int]:
    candidates = [row for row in rows if int(row["local_pareto_options"]) > 0]
    candidates.sort(key=lambda row: (int(row["local_pareto_options"]), row["building_id"]))

    selected = []
    product = 1
    for row in candidates:
        if len(selected) >= requested_buildings:
            break
        next_product = product * int(row["local_pareto_options"])
        if next_product > max_combinations:
            break
        selected.append(dict(row))
        product = next_product

    if len(selected) != requested_buildings:
        raise RuntimeError(
            f"Could only select {len(selected)} buildings below {max_combinations:,} "
            f"local-pareto combinations; requested {requested_buildings}."
        )
    return selected, product


def _pareto_front(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records:
        return []
    points = [tuple(float(record[key]) for key in OBJECTIVE_KEYS) for record in records]
    keep = pareto_prune_points(points, tau=1e-9)
    return [records[i] for i in keep]


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:d}:{sec:02d}"


def _exact_cartesian_front(
    building_dict: dict[str, dict[str, dict[Any, dict[str, Any]]]],
    use_building_prune: bool,
    max_combinations: int,
    batch_size: int,
    progress_every: int,
) -> tuple[list[dict[str, Any]], int, list[tuple[str, int]], float]:
    option_lists = []
    for building_id, building_data in building_dict.items():
        if use_building_prune:
            options = pareto_prune_building(building_data, REFURBISHMENT_STRATEGIES, tau=1e-9)
        else:
            options = collect_options_for_building(building_data, REFURBISHMENT_STRATEGIES)
        options = [{**record, "selection": {building_id: record}} for record in options]
        if options:
            option_lists.append((building_id, options))

    counts = [(building_id, len(options)) for building_id, options in option_lists]
    product_size = _product(count for _, count in counts)
    if product_size > max_combinations:
        raise RuntimeError(
            f"Exact Cartesian reference too large: {product_size:,} combinations "
            f"exceed limit {max_combinations:,}."
        )

    front: list[dict[str, Any]] = []
    batch: list[dict[str, Any]] = []
    produced = 0
    start = time.perf_counter()
    building_ids = [building_id for building_id, _ in option_lists]

    for combo in itertools.product(*(options for _, options in option_lists)):
        selection = {}
        co2 = 0.0
        totex = 0.0
        for building_id, option in zip(building_ids, combo):
            selection[building_id] = option
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

        if len(batch) >= batch_size:
            front = _pareto_front(front + batch)
            batch = []

        if progress_every > 0 and produced % progress_every == 0:
            elapsed = time.perf_counter() - start
            rate = produced / max(elapsed, 1e-12)
            remaining = (product_size - produced) / max(rate, 1e-12)
            print(
                f"exact_progress={produced:,}/{product_size:,} "
                f"elapsed={_format_duration(elapsed)} eta={_format_duration(remaining)} "
                f"current_front_size={len(front)}",
                flush=True,
            )

    if batch:
        front = _pareto_front(front + batch)

    elapsed = time.perf_counter() - start
    return front, produced, counts, elapsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare, and optionally run, the exact 3-SFH SEC5658 benchmark for "
            "sfh_k06_mfh_k01 with local building Pareto pruning."
        )
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--building-dict", type=Path, default=DEFAULT_BUILDING_DICT)
    parser.add_argument("--sfh-folder", type=str, default="sfh_cluster_k06")
    parser.add_argument("--mfh-folder", type=str, default="mfh_cluster_k01")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--requested-buildings", type=int, default=DEFAULT_REQUESTED_BUILDINGS)
    parser.add_argument("--max-exact-combinations", type=int, default=DEFAULT_MAX_EXACT_COMBINATIONS)
    parser.add_argument("--use-building-prune", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--batch-size", type=int, default=25_000)
    parser.add_argument("--progress-every", type=int, default=250_000)
    parser.add_argument(
        "--run-exact",
        action="store_true",
        help="Actually run the exact Cartesian recombination. Omit this flag for setup only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    building_dict = _load_pickle(args.building_dict)
    sfh_rows = _build_sfh_rows(
        building_dict=building_dict,
        data_root=args.data_root,
        sfh_folder=args.sfh_folder,
        mfh_folder=args.mfh_folder,
    )
    selected, selected_product = _choose_exact_subset(
        rows=sfh_rows,
        requested_buildings=args.requested_buildings,
        max_combinations=args.max_exact_combinations,
    )
    selected_ids = [row["building_id"] for row in selected]
    selected_building_dict = {
        building_id: building_dict[building_id]
        for building_id in selected_ids
    }

    selected_raw_product = _product(row["raw_options"] for row in selected)
    all_sfh_local_product = _product(row["local_pareto_options"] for row in sfh_rows)
    all_sfh_raw_product = _product(row["raw_options"] for row in sfh_rows)
    selected_id_set = set(selected_ids)
    for row in sfh_rows:
        row["selected"] = row["building_id"] in selected_id_set

    run_command = (
        "C:\\ProgramData\\mambaforge_24.3.0.0\\envs\\thermal_building_model2\\python.exe "
        f"{Path(__file__).resolve()} --run-exact"
    )
    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "data_root": str(args.data_root),
        "building_dict": str(args.building_dict),
        "combination": "sfh_k06_mfh_k01",
        "building_scope": "sfh_only",
        "requested_buildings": args.requested_buildings,
        "selected_building_count": len(selected),
        "selected_building_ids": selected_ids,
        "use_building_prune": args.use_building_prune,
        "max_exact_combinations": args.max_exact_combinations,
        "selected_local_pareto_product": selected_product,
        "selected_raw_product": selected_raw_product,
        "all_sfh_local_pareto_product": all_sfh_local_product,
        "all_sfh_raw_product": all_sfh_raw_product,
        "batch_size": args.batch_size,
        "progress_every": args.progress_every,
        "setup_only": not args.run_exact,
        "manual_run_command": run_command,
    }

    _mkdir(args.output_dir)
    _write_csv(args.output_dir / "building_option_counts.csv", sfh_rows)
    _write_csv(args.output_dir / "selected_buildings.csv", selected)
    _write_json(args.output_dir / "exact_benchmark_setup.json", summary)
    _save_pickle(args.output_dir / "selected_building_dict.pkl", selected_building_dict)

    print(f"output_dir={args.output_dir}")
    print(f"selected_building_count={len(selected)}")
    print(f"selected_building_ids={selected_ids}")
    print(f"use_building_prune={args.use_building_prune}")
    print(f"max_exact_combinations={args.max_exact_combinations}")
    print(f"selected_local_pareto_product={selected_product}")
    print(f"selected_raw_product={selected_raw_product}")

    if not args.run_exact:
        print("setup_only=True")
        print(f"manual_run_command={run_command}")
        return

    front, produced, option_counts, elapsed = _exact_cartesian_front(
        building_dict=selected_building_dict,
        use_building_prune=args.use_building_prune,
        max_combinations=args.max_exact_combinations,
        batch_size=args.batch_size,
        progress_every=args.progress_every,
    )
    exact_summary = {
        **summary,
        "setup_only": False,
        "started_at": summary["created_at"],
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "produced_combinations": produced,
        "option_counts": [
            {"building_id": building_id, "option_count": count}
            for building_id, count in option_counts
        ],
        "exact_front_size": len(front),
        "elapsed_s": round(elapsed, 3),
        "elapsed_hms": _format_duration(elapsed),
        "combinations_per_second": produced / max(elapsed, 1e-12),
    }
    _save_pickle(args.output_dir / "exact_front_after_local_building_prune.pkl", front)
    _write_csv(args.output_dir / "exact_front_after_local_building_prune.csv", front)
    _write_json(args.output_dir / "exact_benchmark_result_summary.json", exact_summary)
    print(f"produced_combinations={produced}")
    print(f"exact_front_size={len(front)}")
    print(f"elapsed_s={elapsed:.3f}")
    print(f"elapsed_hms={_format_duration(elapsed)}")
    print(f"combinations_per_second={produced / max(elapsed, 1e-12):.1f}")


if __name__ == "__main__":
    main()
