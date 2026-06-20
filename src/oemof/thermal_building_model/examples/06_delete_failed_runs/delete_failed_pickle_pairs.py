from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable


DEFAULT_CSV = Path(__file__).with_name("failed_pickle_loads.csv")
DEFAULT_PLAN = Path(__file__).with_name("delete_plan.csv")


def detect_root_name(path_text: str) -> str | None:
    parts = path_text.replace("\\", "/").split("/")
    for part in parts:
        if part.startswith("processed_bds_in_"):
            return part
    return None


def map_csv_path(path_text: str, target_root: Path | None, root_name: str | None) -> Path:
    if target_root is None:
        return Path(path_text)

    normalized = path_text.replace("\\", "/")
    effective_root_name = root_name or detect_root_name(path_text)
    if not effective_root_name:
        raise ValueError(f"Could not detect processed_bds_in_* root in path: {path_text}")

    marker = f"/{effective_root_name}/"
    if marker in normalized:
        suffix = normalized.split(marker, 1)[1]
    elif normalized.endswith(f"/{effective_root_name}"):
        suffix = ""
    else:
        raise ValueError(f"Root '{effective_root_name}' not found in path: {path_text}")

    suffix_parts = [part for part in suffix.split("/") if part]
    return target_root.joinpath(*suffix_parts)


def counterpart_paths(path: Path) -> list[Path]:
    name = path.name
    counterparts = []

    if "_simple_co2_" in name:
        counterparts.append(path.with_name(name.replace("_simple_co2_", "_co2_", 1)))
    elif "_co2_" in name:
        counterparts.append(path.with_name(name.replace("_co2_", "_simple_co2_", 1)))

    if name.startswith("simple_results_dec_"):
        counterparts.append(path.with_name(name.replace("simple_results_dec_", "results_dec_", 1)))
    elif name.startswith("results_dec_"):
        counterparts.append(path.with_name("simple_" + name))

    return counterparts


def read_failed_paths(csv_path: Path) -> Iterable[str]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "path" not in reader.fieldnames:
            raise ValueError(f"CSV must contain a 'path' column: {csv_path}")
        for row in reader:
            path_text = (row.get("path") or "").strip()
            if path_text:
                yield path_text


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Delete failed pickle files from failed_pickle_loads.csv plus their "
            "full/simple counterpart files. Dry-run by default."
        )
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="failed_pickle_loads.csv path")
    parser.add_argument(
        "--target-root",
        type=Path,
        default=None,
        help=(
            "Root to map CSV paths to, e.g. /jump/mh/processed_bds_in_DENI03403000SEC5658. "
            "If omitted, paths from the CSV are used as-is."
        ),
    )
    parser.add_argument(
        "--root-name",
        default=None,
        help="Optional processed_bds_in_* folder name for path mapping.",
    )
    parser.add_argument("--plan-output", type=Path, default=DEFAULT_PLAN)
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete files. Without this flag the script only writes a deletion plan.",
    )
    args = parser.parse_args()

    target_root = args.target_root.expanduser() if args.target_root else None
    candidates: dict[Path, dict[str, str]] = {}

    for csv_path_text in read_failed_paths(args.csv):
        failed_path = map_csv_path(csv_path_text, target_root, args.root_name)
        candidates.setdefault(
            failed_path,
            {
                "candidate_type": "failed",
                "source_failed_path": csv_path_text,
            },
        )

        for counterpart in counterpart_paths(failed_path):
            candidates.setdefault(
                counterpart,
                {
                    "candidate_type": "counterpart",
                    "source_failed_path": csv_path_text,
                },
            )

    plan_rows = []
    deleted_count = 0

    for candidate_path, meta in sorted(candidates.items(), key=lambda item: str(item[0])):
        exists = candidate_path.exists()
        action = "would_delete" if exists else "missing"

        if args.delete and exists:
            candidate_path.unlink()
            deleted_count += 1
            action = "deleted"

        plan_rows.append(
            {
                "candidate_path": str(candidate_path),
                "candidate_type": meta["candidate_type"],
                "exists": exists,
                "action": action,
                "source_failed_path": meta["source_failed_path"],
            }
        )

    args.plan_output.parent.mkdir(parents=True, exist_ok=True)
    with args.plan_output.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "candidate_path",
                "candidate_type",
                "exists",
                "action",
                "source_failed_path",
            ],
        )
        writer.writeheader()
        writer.writerows(plan_rows)

    existing_count = sum(1 for row in plan_rows if row["exists"])
    print(f"CSV:          {args.csv}")
    print(f"Target root:  {target_root if target_root else '(CSV paths as-is)'}")
    print(f"Candidates:   {len(plan_rows)}")
    print(f"Existing:     {existing_count}")
    print(f"Deleted:      {deleted_count}")
    print(f"Plan written: {args.plan_output}")
    if not args.delete:
        print("Dry-run only. Add --delete to remove existing candidate files.")


if __name__ == "__main__":
    main()
