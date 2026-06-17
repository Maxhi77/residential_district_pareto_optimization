import argparse
import multiprocessing
import os
import pickle
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
TODAY_DATE = date.today().strftime("%Y_%m_%d")
DEFAULT_OUTPUT_ROOT_NAME = f"post_processed_cen_k_combinations_{TODAY_DATE}"

DEFAULT_UEU_CASE = [
    "processed_bds_in_DENI03403000SEC5658",
    # "processed_bds_in_DENI03403000SEC5101",
    # "processed_bds_in_DENI03403000SEC4580",
]
DEFAULT_K_VALUES_TO_OPTIMIZE_SFH = ["reference", 1, 2, 4, 6, 8, 10, 14, 18]
DEFAULT_K_VALUES_TO_OPTIMIZE_MFH = ["reference", 1, 2, 3, 4, 5, 6]
DEFAULT_TEMPERATURES = [50, 60, 70, 80]

UEU_CASE = list(DEFAULT_UEU_CASE)
OUTPUT_ROOT_NAME = DEFAULT_OUTPUT_ROOT_NAME

_RESULT_FILE_RE = re.compile(r"^res_cen_t(?P<temperature>\d+)_?(?P<variant>.*)\.pkl$")


def _is_reference_k(k_value: Any) -> bool:
    return isinstance(k_value, str) and k_value.lower() == "reference"


def _k_token(k_value: Any) -> str:
    if _is_reference_k(k_value):
        return "reference"
    return f"k{int(k_value):02d}"


def _short_k_token(k_value: Any) -> str:
    if _is_reference_k(k_value):
        return "ref"
    return f"k{int(k_value):02d}"


def _combo_name(sfh_k: Any, mfh_k: Any) -> str:
    return f"sfh_{_k_token(sfh_k)}_mfh_{_k_token(mfh_k)}"


def _combined_cluster_folder_name(sfh_k: Any, mfh_k: Any) -> str:
    return f"combined_cluster_sfh_{_k_token(sfh_k)}_mfh_{_k_token(mfh_k)}"


def _legacy_centralized_folder_name(sfh_k: Any, mfh_k: Any) -> str:
    return f"cen_s{_short_k_token(sfh_k)}_m{_short_k_token(mfh_k)}"


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


def _parse_int_values(raw_csv: Any) -> List[int]:
    if raw_csv is None:
        return []
    return _dedupe_keep_order(
        [int(x.strip()) for x in str(raw_csv).split(",") if x.strip()]
    )


def _parse_csv_values(raw_csv: Any) -> List[str]:
    if raw_csv is None:
        return []
    return _dedupe_keep_order([x.strip() for x in str(raw_csv).split(",") if x.strip()])


def _parse_ueu_cases(raw_value: Any) -> List[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple, set)):
        return _dedupe_keep_order([str(x).strip() for x in raw_value if str(x).strip()])
    return _parse_csv_values(raw_value)


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


def _resolve_case_root(ueu_case: str, base_dir: Path) -> Path:
    ueu_path = Path(str(ueu_case))
    if ueu_path.is_absolute():
        return ueu_path
    return base_dir / str(ueu_case)


def _resolve_centralized_result_dir(
    case_root: Path,
    sfh_k: Any,
    mfh_k: Any,
    allow_legacy: bool = True,
) -> Path:
    candidates = [
        case_root / _combined_cluster_folder_name(sfh_k, mfh_k) / "centralized",
    ]
    if allow_legacy:
        candidates.append(case_root / _legacy_centralized_folder_name(sfh_k, mfh_k))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "No centralized result folder found. Checked: "
        + ", ".join(str(candidate) for candidate in candidates)
    )


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


def _load_centralized_result_files(
    result_dir: Path,
    temperatures: Optional[Iterable[int]] = None,
    file_pattern: str = "res_cen_t*.pkl",
) -> Dict[int, Dict[str, Dict[Any, Dict[str, Any]]]]:
    allowed_temperatures = set(temperatures) if temperatures is not None else None
    heat_grid_dict: Dict[int, Dict[str, Dict[Any, Dict[str, Any]]]] = {}

    for path in sorted(result_dir.glob(file_pattern)):
        match = _RESULT_FILE_RE.match(path.name)
        if not match:
            continue

        temperature = int(match.group("temperature"))
        if allowed_temperatures is not None and temperature not in allowed_temperatures:
            continue

        variant = match.group("variant").strip("_") or "default"
        with open(path, "rb") as fh:
            raw = pickle.load(fh)

        if not isinstance(raw, dict):
            raise ValueError(f"Expected dict in {path}, got {type(raw).__name__}")

        heat_grid_dict.setdefault(temperature, {})[variant] = _remove_series(raw)

    return heat_grid_dict


def _to_plain_value(value: Any) -> Any:
    if isinstance(value, (np.float64, np.float32, np.float16)):
        return float(value)
    if isinstance(value, (np.int64, np.int32, np.int16, np.int8)):
        return int(value)
    return value


def process_building_dict(
    building_dict_heat_grid: Dict[int, Dict[str, Dict[Any, Dict[str, Any]]]]
) -> List[Dict[str, Any]]:
    """
    Convert centralized heat-grid results to the same combined-front format used
    in x_post_process_examples.py.
    """
    result_list = []

    for temperature, temp_dict in building_dict_heat_grid.items():
        for maybe_variant, value in temp_dict.items():
            if isinstance(value, dict) and "co2" in value:
                variant = "default"
                building_items = {maybe_variant: value}
            else:
                variant = maybe_variant
                building_items = value

            if not isinstance(building_items, dict):
                continue

            for key, data in building_items.items():
                if not isinstance(data, dict):
                    continue
                if data.get("co2") is None or data.get("peak") is None:
                    continue

                results = data.get("results", {})
                results_clean = {
                    rk: (
                        {kk: _to_plain_value(v) for kk, v in rv.items()}
                        if isinstance(rv, dict)
                        else _to_plain_value(rv)
                    )
                    for rk, rv in results.items()
                }

                result_list.append(
                    {
                        "co2": float(data["co2"]),
                        "peak": float(data["peak"]),
                        "totex": float(data["totex"]),
                        "selection": {
                            "key": key,
                            "heat_grid_temperature": temperature,
                            "variant": variant,
                            **results_clean,
                        },
                    }
                )

    return result_list


def _save_combination_outputs(
    output_dir: Path,
    building_dict: Dict[int, Dict[str, Dict[Any, Dict[str, Any]]]],
    combined_front: List[Dict[str, Any]],
    meta: Dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "building_dict.pkl", "wb") as fh:
        pickle.dump(building_dict, fh, protocol=pickle.HIGHEST_PROTOCOL)
    with open(output_dir / "combined_front.pkl", "wb") as fh:
        pickle.dump(combined_front, fh, protocol=pickle.HIGHEST_PROTOCOL)
    with open(output_dir / "combined_package.pkl", "wb") as fh:
        pickle.dump([building_dict, building_dict, combined_front], fh, protocol=pickle.HIGHEST_PROTOCOL)
    with open(output_dir / "meta.pkl", "wb") as fh:
        pickle.dump(meta, fh, protocol=pickle.HIGHEST_PROTOCOL)

    for temperature, temp_dict in building_dict.items():
        temp_output_dir = output_dir / f"t{temperature}"
        temp_output_dir.mkdir(parents=True, exist_ok=True)
        temp_building_dict = {temperature: temp_dict}
        temp_combined_front = process_building_dict(temp_building_dict)
        temp_meta = {
            **meta,
            "temperature": temperature,
            "result_files": sum(len(variants) for variants in temp_building_dict.values()),
            "combined_front_size": len(temp_combined_front),
        }
        with open(temp_output_dir / "building_dict.pkl", "wb") as fh:
            pickle.dump(temp_building_dict, fh, protocol=pickle.HIGHEST_PROTOCOL)
        with open(temp_output_dir / "combined_front.pkl", "wb") as fh:
            pickle.dump(temp_combined_front, fh, protocol=pickle.HIGHEST_PROTOCOL)
        with open(temp_output_dir / "combined_package.pkl", "wb") as fh:
            pickle.dump(
                [temp_building_dict, temp_building_dict, temp_combined_front],
                fh,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        with open(temp_output_dir / "meta.pkl", "wb") as fh:
            pickle.dump(temp_meta, fh, protocol=pickle.HIGHEST_PROTOCOL)


def _process_single_combination(
    task: Tuple[str, str, Any, Any, List[int], str, bool, str]
) -> Dict[str, Any]:
    (
        case_root_raw,
        output_root_raw,
        sfh_k,
        mfh_k,
        temperatures,
        file_pattern,
        allow_legacy,
        ueu_case,
    ) = task
    case_root = Path(case_root_raw)
    output_root = Path(output_root_raw)
    combo = _combo_name(sfh_k, mfh_k)

    try:
        result_dir = _resolve_centralized_result_dir(
            case_root=case_root,
            sfh_k=sfh_k,
            mfh_k=mfh_k,
            allow_legacy=allow_legacy,
        )
        building_dict = _load_centralized_result_files(
            result_dir=result_dir,
            temperatures=temperatures,
            file_pattern=file_pattern,
        )
    except Exception as exc:
        return {
            "combo": combo,
            "sfh_k": _k_token(sfh_k),
            "mfh_k": _k_token(mfh_k),
            "status": "failed",
            "reason": str(exc),
        }

    if not building_dict:
        return {
            "combo": combo,
            "sfh_k": _k_token(sfh_k),
            "mfh_k": _k_token(mfh_k),
            "status": "failed",
            "reason": "no centralized result files found",
        }

    combined_front = process_building_dict(building_dict)
    if not combined_front:
        return {
            "combo": combo,
            "sfh_k": _k_token(sfh_k),
            "mfh_k": _k_token(mfh_k),
            "status": "failed",
            "reason": "combined_front is empty after processing",
        }

    combo_output_dir = output_root / combo
    temperature_counts = {
        f"t{temperature}": len(variants)
        for temperature, variants in sorted(building_dict.items())
    }
    meta = {
        "ueu_case": ueu_case,
        "sfh_k": sfh_k,
        "mfh_k": mfh_k,
        "combo": combo,
        "source_dir": str(result_dir),
        "temperatures": sorted(building_dict),
        "temperature_result_file_counts": temperature_counts,
        "result_files": sum(temperature_counts.values()),
        "combined_front_size": len(combined_front),
    }
    _save_combination_outputs(
        output_dir=combo_output_dir,
        building_dict=building_dict,
        combined_front=combined_front,
        meta=meta,
    )

    return {
        "combo": combo,
        "sfh_k": _k_token(sfh_k),
        "mfh_k": _k_token(mfh_k),
        "status": "ok",
        "temperatures": ",".join(f"t{x}" for x in sorted(building_dict)),
        "result_files": meta["result_files"],
        "combined_front_size": len(combined_front),
        "output_dir": str(combo_output_dir),
    }


def _print_row_status(row: Dict[str, Any], index: int, total: int) -> None:
    status = str(row.get("status", "unknown"))
    combo = row.get("combo")
    if status == "ok":
        print(
            f"[{index}/{total}] ok {combo}: temperatures={row.get('temperatures')} "
            f"files={row.get('result_files')} combined_front={row.get('combined_front_size')} "
            f"-> {row.get('output_dir')}"
        )
    else:
        print(f"[{index}/{total}] {status} {combo}: {row.get('reason')}")


def run_all_combinations(
    ueu_case: str = DEFAULT_UEU_CASE[0],
    sfh_k_values: Optional[Iterable[Any]] = None,
    mfh_k_values: Optional[Iterable[Any]] = None,
    temperatures: Optional[Iterable[int]] = None,
    workers: int = 1,
    max_tasks: Optional[int] = None,
    task_offset: int = 0,
    base_dir: Optional[str] = None,
    output_root_name: Optional[str] = None,
    file_pattern: str = "res_cen_t*.pkl",
    allow_legacy: bool = True,
) -> Path:
    sfh_values = list(sfh_k_values) if sfh_k_values is not None else list(DEFAULT_K_VALUES_TO_OPTIMIZE_SFH)
    mfh_values = list(mfh_k_values) if mfh_k_values is not None else list(DEFAULT_K_VALUES_TO_OPTIMIZE_MFH)
    selected_temperatures = (
        list(temperatures) if temperatures is not None else list(DEFAULT_TEMPERATURES)
    )

    if not sfh_values:
        raise ValueError("No SFH k values configured.")
    if not mfh_values:
        raise ValueError("No MFH k values configured.")
    if not selected_temperatures:
        raise ValueError("No temperatures configured.")
    if workers <= 0:
        raise ValueError("workers must be > 0")
    if max_tasks is not None and max_tasks <= 0:
        raise ValueError("max_tasks must be > 0 when provided")
    if task_offset < 0:
        raise ValueError("task_offset must be >= 0")

    result_base_dir = Path(base_dir).expanduser() if base_dir else BASE_DIR
    case_root = _resolve_case_root(str(ueu_case), result_base_dir)
    if not case_root.exists():
        raise FileNotFoundError(
            f"UEU folder not found: {case_root} "
            f"(ueu_case={ueu_case}, base_dir={result_base_dir})"
        )

    output_dir_name = str(output_root_name).strip() if output_root_name is not None else ""
    if not output_dir_name:
        output_dir_name = DEFAULT_OUTPUT_ROOT_NAME
    output_root = case_root / output_dir_name
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
    print(f"Base dir: {result_base_dir}")
    print(f"Case root: {case_root}")
    print(f"Output root: {output_root}")
    print(f"SFH K list: {sfh_values}")
    print(f"MFH K list: {mfh_values}")
    print(f"Temperatures: {selected_temperatures}")
    print(f"File pattern: {file_pattern}")
    print(f"Allow legacy folders: {allow_legacy}")
    print(f"Workers: {workers}")
    print(f"Task offset: {task_offset}")
    print(f"Total combos available: {total_combinations}")
    print(f"Task count: {len(all_combinations)}")

    tasks = [
        (
            str(case_root),
            str(output_root),
            sfh_k,
            mfh_k,
            selected_temperatures,
            file_pattern,
            bool(allow_legacy),
            str(ueu_case),
        )
        for sfh_k, mfh_k in all_combinations
    ]

    summary_rows = []
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

    non_ok_rows = [row for row in summary_rows if str(row.get("status", "")).lower() != "ok"]
    if non_ok_rows:
        max_preview = 10
        preview = "; ".join(
            f"{row.get('combo')} [{row.get('status')}]: {row.get('reason')}"
            for row in non_ok_rows[:max_preview]
        )
        if len(non_ok_rows) > max_preview:
            preview += f"; ... +{len(non_ok_rows) - max_preview} more"
        raise RuntimeError(
            f"{len(non_ok_rows)} of {len(summary_rows)} combinations failed. "
            f"See summary at {summary_csv}. Details: {preview}"
        )
    return summary_csv


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post-process centralized k-combination results.")
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
        default=",".join(DEFAULT_UEU_CASE),
        help="Comma-separated UEU folder names below the example directory.",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=None,
        help="Base directory containing result UEU folders. Defaults to this script directory.",
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
        "--temperatures",
        type=str,
        default=",".join(str(x) for x in DEFAULT_TEMPERATURES),
        help="Comma-separated heat-grid temperatures, e.g. 50,80",
    )
    parser.add_argument(
        "--file-pattern",
        type=str,
        default="res_cen_t*.pkl",
        help="Glob pattern for centralized result files inside each result folder.",
    )
    parser.add_argument(
        "--output-root-name",
        type=str,
        default=None,
        help="Output folder name below the UEU folder. Defaults to date-based folder.",
    )
    parser.add_argument(
        "--no-legacy-folders",
        action="store_true",
        help="Only use combined_cluster_sfh_*_mfh_*/centralized folders.",
    )
    return parser


if __name__ == "__main__":
    parser = _build_arg_parser()
    args = parser.parse_args()

    selected_ueu_cases = _parse_ueu_cases(args.ueu_case)
    sfh_requested = _parse_k_values(args.sfh_k)
    mfh_requested = _parse_k_values(args.mfh_k)
    selected_temperatures = _parse_int_values(args.temperatures)

    if not selected_ueu_cases:
        raise ValueError("No UEU cases provided via --ueu-case.")
    if not sfh_requested:
        raise ValueError("No SFH k values provided via --sfh-k.")
    if not mfh_requested:
        raise ValueError("No MFH k values provided via --mfh-k.")
    if not selected_temperatures:
        raise ValueError("No temperatures provided via --temperatures.")

    workers = _resolve_workers(args.workers, serial=args.serial)

    print(
        f"host={args.host_name} workers={workers} task_offset={args.task_offset} "
        f"max_tasks={args.max_tasks} ueu_cases={selected_ueu_cases} "
        f"base_dir={args.base_dir or str(BASE_DIR)} sfh_k={[_k_token(x) for x in sfh_requested]} "
        f"mfh_k={[_k_token(x) for x in mfh_requested]} temperatures={selected_temperatures} "
        f"file_pattern={args.file_pattern} allow_legacy={not args.no_legacy_folders}"
    )

    for index, selected_ueu in enumerate(selected_ueu_cases, start=1):
        print(f"\n=== UEU [{index}/{len(selected_ueu_cases)}]: {selected_ueu} ===")
        run_all_combinations(
            ueu_case=selected_ueu,
            sfh_k_values=sfh_requested,
            mfh_k_values=mfh_requested,
            temperatures=selected_temperatures,
            workers=workers,
            max_tasks=args.max_tasks,
            task_offset=args.task_offset,
            base_dir=args.base_dir,
            output_root_name=args.output_root_name,
            file_pattern=args.file_pattern,
            allow_legacy=(not args.no_legacy_folders),
        )
