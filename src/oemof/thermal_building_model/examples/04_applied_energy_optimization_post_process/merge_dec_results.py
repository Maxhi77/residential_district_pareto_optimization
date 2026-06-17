import argparse
import pickle
from pathlib import Path


REFURBISHMENTS = (
    "no_refurbishment",
    "usual_refurbishment",
    "advanced_refurbishment",
    "GEG_standard",
)


def parse_result_filename(path: Path):
    """
    Parse filenames like:
    results_dec_processed_bds_in_DENI03403000SEC5658_advanced_refurbishment_no_EV_DENILD1100004uKD.pkl
    """
    stem = path.stem
    prefix = "results_dec_"

    if not stem.startswith(prefix):
        return None

    rest = stem[len(prefix):]

    for refurbishment in REFURBISHMENTS:
        marker = f"_{refurbishment}_"
        if marker not in rest:
            continue

        ueu, tail = rest.split(marker, 1)
        if "_" not in tail:
            return None

        ev, building_id = tail.rsplit("_", 1)
        return ueu, refurbishment, ev, building_id

    return None


def merge_results(base_dir: Path):
    merged_by_ueu = {}

    for path in sorted(base_dir.glob("results_dec_*.pkl")):
        parsed = parse_result_filename(path)
        if parsed is None:
            continue

        ueu, _refurbishment, _ev, building_id = parsed

        with open(path, "rb") as f:
            file_data = pickle.load(f)

        if ueu not in merged_by_ueu:
            merged_by_ueu[ueu] = {}

        if building_id not in merged_by_ueu[ueu]:
            merged_by_ueu[ueu][building_id] = {}

        # Merge all scenario keys of this file into the building-level dict.
        if isinstance(file_data, dict):
            merged_by_ueu[ueu][building_id].update(file_data)
        else:
            merged_by_ueu[ueu][building_id] = file_data

    for ueu, payload in merged_by_ueu.items():
        ueu_short = ueu.replace("processed_bds_in_", "", 1)
        out_path = base_dir / f"merged_{ueu_short}.pkl"
        with open(out_path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"Saved: {out_path} (buildings: {len(payload)})")


def main():
    parser = argparse.ArgumentParser(
        description="Merge decentralized single-building result files into one file per UEU."
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory containing results_dec_*.pkl files (default: current working directory).",
    )
    args = parser.parse_args()

    merge_results(args.base_dir)


if __name__ == "__main__":
    main()


