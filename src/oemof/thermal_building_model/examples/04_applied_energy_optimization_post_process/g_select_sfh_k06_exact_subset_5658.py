from __future__ import annotations

import argparse
import csv
import json
import math
import os
import pickle
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from oemof.thermal_building_model.helpers.pareto_optimal_help_functions import (  # noqa: E402
    collect_options_for_building,
    pareto_prune_building,
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
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "pareto_recombination_validation_5658" / "sfh_k06_exact_subset"
DEFAULT_MAX_COMBINATIONS = 1_000_000
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


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    _mkdir(path.parent)
    if not rows:
        return
    columns = list(rows[0].keys())
    with open(_to_long_path(path), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Any) -> None:
    _mkdir(path.parent)
    with open(_to_long_path(path), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


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


def _raw_option_count(building_data: dict[str, dict[Any, dict[str, Any]]]) -> int:
    return len(collect_options_for_building(building_data, REFURBISHMENT_STRATEGIES))


def _local_pareto_option_count(building_data: dict[str, dict[Any, dict[str, Any]]]) -> int:
    if _raw_option_count(building_data) == 0:
        return 0
    return len(pareto_prune_building(building_data, REFURBISHMENT_STRATEGIES, tau=1e-9))


def _count_by_refurbishment(
    building_data: dict[str, dict[Any, dict[str, Any]]]
) -> dict[str, int]:
    return {
        refurbish: len(building_data.get(refurbish, {}))
        for refurbish in REFURBISHMENT_STRATEGIES
    }


def _choose_max_subset(
    rows: list[dict[str, Any]],
    max_combinations: int,
    count_column: str,
) -> tuple[list[dict[str, Any]], int]:
    candidates = [
        row for row in rows if int(row[count_column]) > 0
    ]
    candidates.sort(key=lambda row: (int(row[count_column]), row["building_id"]))

    selected = []
    product = 1
    for row in candidates:
        next_product = product * int(row[count_column])
        if selected and next_product > max_combinations:
            break
        if next_product > max_combinations:
            continue
        selected.append(row)
        product = next_product

    return selected, product


def _product(values: Iterable[int]) -> int:
    out = 1
    for value in values:
        out *= int(value)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Select the largest SFH-only exact-recombination subset for "
            "SEC5658 sfh_k06_mfh_k01 under a Cartesian product limit."
        )
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--building-dict", type=Path, default=DEFAULT_BUILDING_DICT)
    parser.add_argument("--sfh-folder", type=str, default="sfh_cluster_k06")
    parser.add_argument("--mfh-folder", type=str, default="mfh_cluster_k01")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-combinations", type=int, default=DEFAULT_MAX_COMBINATIONS)
    parser.add_argument(
        "--selection-count",
        choices=["raw", "local_pareto"],
        default="local_pareto",
        help=(
            "Option count used for the product limit. local_pareto matches an exact "
            "reference after local building Pareto pruning."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    building_dict = _load_pickle(args.building_dict)
    data_root = args.data_root
    sfh_ids = _building_ids_from_result_folder(data_root / args.sfh_folder)
    mfh_ids = _building_ids_from_result_folder(data_root / args.mfh_folder)

    if not sfh_ids:
        raise SystemExit(f"No SFH building ids found in {data_root / args.sfh_folder}")

    rows = []
    for building_id in sorted(building_dict):
        in_sfh_folder = building_id in sfh_ids
        in_mfh_folder = building_id in mfh_ids
        building_type = "sfh" if in_sfh_folder and not in_mfh_folder else "mfh" if in_mfh_folder else "unknown"
        raw_count = _raw_option_count(building_dict[building_id])
        local_pareto_count = _local_pareto_option_count(building_dict[building_id])
        row = {
            "building_id": building_id,
            "building_type": building_type,
            "in_sfh_cluster_k06": in_sfh_folder,
            "in_mfh_cluster_k01": in_mfh_folder,
            "raw_options": raw_count,
            "local_pareto_options": local_pareto_count,
            **{
                f"{refurbish}_entries": count
                for refurbish, count in _count_by_refurbishment(building_dict[building_id]).items()
            },
        }
        rows.append(row)

    sfh_rows = [row for row in rows if row["building_type"] == "sfh"]
    count_column = "raw_options" if args.selection_count == "raw" else "local_pareto_options"
    selected, selected_product = _choose_max_subset(
        rows=sfh_rows,
        max_combinations=args.max_combinations,
        count_column=count_column,
    )

    for row in rows:
        row["selected"] = row in selected
        row["selection_count_used"] = row[count_column]

    selected_building_dict = {
        row["building_id"]: building_dict[row["building_id"]]
        for row in selected
    }
    raw_product_selected = _product(row["raw_options"] for row in selected) if selected else 0
    local_pareto_product_selected = (
        _product(row["local_pareto_options"] for row in selected) if selected else 0
    )
    next_candidate = None
    selected_ids = {row["building_id"] for row in selected}
    for row in sorted(sfh_rows, key=lambda item: (int(item[count_column]), item["building_id"])):
        if row["building_id"] not in selected_ids and int(row[count_column]) > 0:
            next_candidate = row
            break

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "data_root": str(data_root),
        "building_dict": str(args.building_dict),
        "combination": "sfh_k06_mfh_k01",
        "building_scope": "sfh_only",
        "max_combinations": args.max_combinations,
        "selection_count": args.selection_count,
        "selection_count_column": count_column,
        "total_buildings_in_building_dict": len(building_dict),
        "sfh_buildings_found": len(sfh_rows),
        "mfh_buildings_found": sum(1 for row in rows if row["building_type"] == "mfh"),
        "selected_building_count": len(selected),
        "selected_building_ids": [row["building_id"] for row in selected],
        "selected_product_for_limit": selected_product,
        "selected_raw_product": raw_product_selected,
        "selected_local_pareto_product": local_pareto_product_selected,
        "all_sfh_raw_product": _product(row["raw_options"] for row in sfh_rows),
        "all_sfh_local_pareto_product": _product(row["local_pareto_options"] for row in sfh_rows),
        "next_unselected_candidate": (
            {
                "building_id": next_candidate["building_id"],
                "raw_options": next_candidate["raw_options"],
                "local_pareto_options": next_candidate["local_pareto_options"],
                "product_if_added": selected_product * int(next_candidate[count_column]),
            }
            if next_candidate is not None
            else None
        ),
    }

    _mkdir(args.output_dir)
    _write_csv(args.output_dir / "building_option_counts.csv", rows)
    _write_csv(args.output_dir / "selected_buildings.csv", selected)
    _write_json(args.output_dir / "selected_buildings_summary.json", summary)
    _save_pickle(args.output_dir / "selected_building_dict.pkl", selected_building_dict)

    print(f"output_dir={args.output_dir}")
    print(f"sfh_buildings_found={len(sfh_rows)}")
    print(f"selected_building_count={len(selected)}")
    print(f"selected_building_ids={summary['selected_building_ids']}")
    print(f"selected_product_for_limit={selected_product}")
    if next_candidate is not None:
        print(
            "next_candidate_if_added="
            f"{next_candidate['building_id']} -> "
            f"{selected_product * int(next_candidate[count_column])}"
        )
    print(f"all_sfh_raw_product={summary['all_sfh_raw_product']}")
    print(f"all_sfh_local_pareto_product={summary['all_sfh_local_pareto_product']}")


if __name__ == "__main__":
    main()
