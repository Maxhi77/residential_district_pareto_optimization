from __future__ import annotations

import argparse
import csv
import gc
import pickle
from pathlib import Path


DEFAULT_ROOT = Path(
    "/home/hill_mx/thermal_building_clone/src/oemof/thermal_building_model/"
    "examples/03_advanced_investment_optimization/"
    "processed_bds_in_DENI03403000SEC5101"
)
DEFAULT_OUTPUT = Path(__file__).with_name("failed_pickle_loads.csv")


def try_load_pickle(path: Path) -> tuple[bool, str, str]:
    try:
        with path.open("rb") as fh:
            obj = pickle.load(fh)
        del obj
        gc.collect()
        return True, "", ""
    except Exception as exc:
        return False, type(exc).__name__, str(exc)


def path_matches_dir_prefix(path: Path, root: Path, prefixes: list[str]) -> bool:
    if not prefixes:
        return True
    try:
        relative_parts = path.relative_to(root).parts[:-1]
    except ValueError:
        relative_parts = path.parts[:-1]
    return any(part.startswith(tuple(prefixes)) for part in relative_parts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Try loading pickle files and write unloadable files to a CSV."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Root directory to scan, usually a processed_bds_in_* directory.",
    )
    parser.add_argument("--pattern", default="*.pkl", help="File glob to scan below root.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="CSV path for failed pickle loads.",
    )
    parser.add_argument(
        "--only-dir-prefix",
        action="append",
        default=[],
        help=(
            "Optional directory-name prefix to restrict scanning. Can be passed "
            "multiple times, e.g. --only-dir-prefix combined_cluster."
        ),
    )
    args = parser.parse_args()

    root = args.root.expanduser()
    output = args.output.expanduser()

    if not root.exists():
        raise FileNotFoundError(f"Root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Root is not a directory: {root}")

    failed_rows = []
    checked = 0
    seen_files = set()

    for path in root.rglob(args.pattern):
        if not path.is_file():
            continue
        if not path_matches_dir_prefix(path, root, args.only_dir_prefix):
            continue

        resolved_path = path.resolve()
        if resolved_path in seen_files:
            continue
        seen_files.add(resolved_path)

        checked += 1
        ok, error_type, error_message = try_load_pickle(path)
        if ok:
            print(f"ok     {path}")
            continue

        print(f"failed {path}: {error_type}: {error_message}")
        failed_rows.append(
            {
                "path": str(path),
                "file_name": path.name,
                "size_bytes": path.stat().st_size if path.exists() else "",
                "error_type": error_type,
                "error_message": error_message,
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "path",
                "file_name",
                "size_bytes",
                "error_type",
                "error_message",
            ],
        )
        writer.writeheader()
        writer.writerows(failed_rows)

    print()
    print(f"Root:          {root}")
    print(f"Checked files: {checked}")
    print(f"Failed files:  {len(failed_rows)}")
    print(f"CSV written:   {output}")


if __name__ == "__main__":
    main()
