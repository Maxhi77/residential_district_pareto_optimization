from __future__ import annotations

import argparse
import csv
import gc
import pickle
from pathlib import Path


DEFAULT_ROOT = Path(
    r"M:\04_ArchivMA\Hillen Maximilian\Veröffentlichungen\UEU"
    r"\processed_bds_in_DENI03403000SEC5658"
)


def try_load_pickle(path: Path) -> tuple[bool, str, str]:
    try:
        with path.open("rb") as fh:
            obj = pickle.load(fh)
        del obj
        gc.collect()
        return True, "", ""
    except Exception as exc:
        return False, type(exc).__name__, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Try loading pickle files and write unloadable files to a CSV."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--pattern", default="*.pkl")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    root = args.root.expanduser()
    output = args.output or (root / "failed_pickle_loads.csv")

    failed_rows = []
    checked = 0

    combined_cluster_dirs = [
        path for path in root.rglob("combined_cluster*")
        if path.is_dir()
    ]

    seen_files = set()
    for cluster_dir in combined_cluster_dirs:
        for path in cluster_dir.rglob(args.pattern):
            if not path.is_file():
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
    print(f"Combined cluster dirs: {len(combined_cluster_dirs)}")
    print(f"Checked files: {checked}")
    print(f"Failed files:  {len(failed_rows)}")
    print(f"CSV written:   {output}")


if __name__ == "__main__":
    main()
