import pickle
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


EXAMPLES_BASE_DIR = (
    Path(__file__).resolve().parents[1] / "03_applied_energy_optimization"
)
OUTPUT_BASE_DIR = Path(__file__).resolve().parent / "reference_kpi_comparison"
DEMANDS_PKL_NAME = "demands_and_pv_potential.pkl"


def _discover_cluster_roots(base_dir: Path) -> list[Path]:
    roots: list[Path] = []
    for candidate in sorted(base_dir.iterdir()):
        if not candidate.is_dir():
            continue
        if not candidate.name.startswith("processed_bds_in_"):
            continue
        has_reference_payload = any(
            (candidate / ref_dir / DEMANDS_PKL_NAME).exists()
            for ref_dir in ("reference", "sfh_reference", "mfh_reference")
        )
        if has_reference_payload:
            roots.append(candidate)
    return roots


def _load_pickle(path: Path) -> dict:
    with open(path, "rb") as fh:
        data = pickle.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict payload in {path}, got {type(data)}")
    return data


def _to_float_array(values) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


def _aggregate_timeseries(payload: dict) -> dict[str, np.ndarray]:
    keys = ("electricity_demand", "warm_water_demand", "building_heating_demand", "pv_potential")
    weights = payload.get("buildings_in_cluster", {})

    aggregated: dict[str, np.ndarray] = {}
    for key in keys:
        per_building = payload.get(key, {})
        total: np.ndarray | None = None
        for building_id, values in per_building.items():
            series = _to_float_array(values)
            if total is None:
                total = np.zeros_like(series, dtype=float)
            elif len(series) != len(total):
                raise ValueError(
                    f"Length mismatch in '{key}' for building '{building_id}': "
                    f"{len(series)} != {len(total)}"
                )
            weight = float(weights.get(building_id, 1.0))
            total += series * weight
        if total is None:
            raise ValueError(f"No data for key '{key}'.")
        aggregated[key] = total

    return aggregated


def _sum_aggregated_timeseries(*series_dicts: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    if not series_dicts:
        raise ValueError("No timeseries dictionaries passed.")
    out = {k: v.copy() for k, v in series_dicts[0].items()}
    for nxt in series_dicts[1:]:
        for key in out:
            if len(out[key]) != len(nxt[key]):
                raise ValueError(f"Length mismatch for '{key}' while summing aggregated timeseries.")
            out[key] += nxt[key]
    return out


def _compute_metrics(aggregated: dict[str, np.ndarray]) -> dict[str, float]:
    electricity = aggregated["electricity_demand"]
    dhw = aggregated["warm_water_demand"]
    heating = aggregated["building_heating_demand"]
    pv = aggregated["pv_potential"]

    return {
        "total_electricity": float(np.sum(electricity)),
        "total_dhw": float(np.sum(dhw)),
        "total_heating": float(np.sum(heating)),
        "total_pv": float(np.sum(pv)),
        "peak_electricity": float(np.max(electricity)),
        "peak_dhw": float(np.max(dhw)),
        "peak_heating": float(np.max(heating)),
        "peak_pv": float(np.max(pv)),
    }


def _safe_ratio(value: float, ref: float) -> float:
    if np.isclose(ref, 0.0):
        return np.nan
    return float(value / ref)


def _load_reference_payloads(cluster_root: Path) -> dict[str, dict[str, np.ndarray]]:
    payload_paths = {
        "reference": cluster_root / "reference" / DEMANDS_PKL_NAME,
        "sfh_reference": cluster_root / "sfh_reference" / DEMANDS_PKL_NAME,
        "mfh_reference": cluster_root / "mfh_reference" / DEMANDS_PKL_NAME,
    }

    aggregated_by_scenario: dict[str, dict[str, np.ndarray]] = {}
    for scenario, path in payload_paths.items():
        if not path.exists():
            continue
        payload = _load_pickle(path)
        aggregated_by_scenario[scenario] = _aggregate_timeseries(payload)

    if (
        "sfh_reference" in aggregated_by_scenario
        and "mfh_reference" in aggregated_by_scenario
    ):
        aggregated_by_scenario["sfh_plus_mfh"] = _sum_aggregated_timeseries(
            aggregated_by_scenario["sfh_reference"],
            aggregated_by_scenario["mfh_reference"],
        )

    return aggregated_by_scenario


def _build_summary_table(cluster_root: Path) -> pd.DataFrame:
    aggregated = _load_reference_payloads(cluster_root)
    if not aggregated:
        return pd.DataFrame()

    metrics_by_scenario = {
        scenario: _compute_metrics(series)
        for scenario, series in aggregated.items()
    }
    reference_metrics = metrics_by_scenario.get("reference")

    rows: list[dict] = []
    for scenario in ("reference", "sfh_reference", "mfh_reference", "sfh_plus_mfh"):
        scenario_metrics = metrics_by_scenario.get(scenario)
        if scenario_metrics is None:
            continue

        row = {"scenario": scenario}
        for metric_name, value in scenario_metrics.items():
            row[metric_name] = value
            if reference_metrics is None:
                row[f"{metric_name}_ratio_to_reference"] = np.nan
                row[f"{metric_name}_delta_pct_to_reference"] = np.nan
            else:
                ratio = _safe_ratio(value, reference_metrics[metric_name])
                row[f"{metric_name}_ratio_to_reference"] = ratio
                row[f"{metric_name}_delta_pct_to_reference"] = (ratio - 1.0) * 100.0
        rows.append(row)

    return pd.DataFrame(rows)


def _plot_ratio_comparison(summary_df: pd.DataFrame, title: str, save_path: Path) -> None:
    df = summary_df.copy()
    ratio_cols_total = [
        "total_electricity_ratio_to_reference",
        "total_dhw_ratio_to_reference",
        "total_heating_ratio_to_reference",
        "total_pv_ratio_to_reference",
    ]
    ratio_cols_peak = [
        "peak_electricity_ratio_to_reference",
        "peak_dhw_ratio_to_reference",
        "peak_heating_ratio_to_reference",
        "peak_pv_ratio_to_reference",
    ]
    pretty_total = ["Electricity", "DHW", "Heating", "PV"]
    pretty_peak = ["Electricity", "DHW", "Heating", "PV"]

    scenarios = [s for s in ("reference", "sfh_reference", "mfh_reference", "sfh_plus_mfh") if s in set(df["scenario"])]
    colors = {
        "reference": "0.55",
        "sfh_reference": "tab:blue",
        "mfh_reference": "tab:orange",
        "sfh_plus_mfh": "tab:green",
    }

    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.2), constrained_layout=True)
    bar_width = 0.18

    def _draw_panel(ax, cols, labels, panel_title):
        x = np.arange(len(cols))
        for idx, scenario in enumerate(scenarios):
            row = df.loc[df["scenario"] == scenario].iloc[0]
            vals = [float(row[c]) for c in cols]
            offset = (idx - (len(scenarios) - 1) / 2) * bar_width
            ax.bar(
                x + offset,
                vals,
                width=bar_width,
                label=scenario,
                color=colors.get(scenario, None),
                alpha=0.85,
            )

        ax.axhline(1.0, color="0.35", linestyle=":", linewidth=1.0)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel("Ratio to reference in -")
        ax.set_title(panel_title)
        ax.grid(True, axis="y", alpha=0.25)

    _draw_panel(axes[0], ratio_cols_total, pretty_total, "Annual Totals")
    _draw_panel(axes[1], ratio_cols_peak, pretty_peak, "Annual Peaks")

    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=len(scenarios), frameon=False, bbox_to_anchor=(0.5, 1.06))
    fig.suptitle(title, y=1.12, fontsize=10)
    fig.savefig(save_path, bbox_inches="tight")
    plt.close(fig)


def _plot_absolute_comparison(summary_df: pd.DataFrame, title: str, save_path: Path) -> None:
    df = summary_df.copy()
    total_cols = ["total_electricity", "total_dhw", "total_heating", "total_pv"]
    peak_cols = ["peak_electricity", "peak_dhw", "peak_heating", "peak_pv"]
    labels = ["Electricity", "DHW", "Heating", "PV"]

    scenarios = [s for s in ("reference", "sfh_reference", "mfh_reference", "sfh_plus_mfh") if s in set(df["scenario"])]
    colors = {
        "reference": "0.55",
        "sfh_reference": "tab:blue",
        "mfh_reference": "tab:orange",
        "sfh_plus_mfh": "tab:green",
    }

    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.2), constrained_layout=True)
    bar_width = 0.18

    def _draw_panel(ax, cols, panel_title):
        x = np.arange(len(cols))
        for idx, scenario in enumerate(scenarios):
            row = df.loc[df["scenario"] == scenario].iloc[0]
            vals = [float(row[c]) for c in cols]
            offset = (idx - (len(scenarios) - 1) / 2) * bar_width
            ax.bar(
                x + offset,
                vals,
                width=bar_width,
                label=scenario,
                color=colors.get(scenario, None),
                alpha=0.85,
            )
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel("Absolute KPI value")
        ax.set_title(panel_title)
        ax.grid(True, axis="y", alpha=0.25)

    _draw_panel(axes[0], total_cols, "Annual Totals")
    _draw_panel(axes[1], peak_cols, "Annual Peaks")

    handles, legend_labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", ncol=len(scenarios), frameon=False, bbox_to_anchor=(0.5, 1.06))
    fig.suptitle(title, y=1.12, fontsize=10)
    fig.savefig(save_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    cluster_roots = _discover_cluster_roots(EXAMPLES_BASE_DIR)
    if not cluster_roots:
        print(f"No eligible UEU folders found below: {EXAMPLES_BASE_DIR}")
        return

    OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

    for cluster_root in cluster_roots:
        print(f"processing: {cluster_root.name}")
        summary_df = _build_summary_table(cluster_root)
        if summary_df.empty:
            print("  - skip: no reference payloads found")
            continue

        output_dir = OUTPUT_BASE_DIR / cluster_root.name
        output_dir.mkdir(parents=True, exist_ok=True)

        summary_csv = output_dir / "reference_kpi_comparison_summary.csv"
        summary_df.to_csv(summary_csv, index=False)
        print(f"  - saved summary: {summary_csv}")

        wide_table = summary_df.set_index("scenario").T.reset_index().rename(columns={"index": "kpi"})
        wide_csv = output_dir / "reference_kpi_comparison_wide.csv"
        wide_table.to_csv(wide_csv, index=False)
        print(f"  - saved wide table: {wide_csv}")

        if "reference" in set(summary_df["scenario"]):
            figure_path = output_dir / "reference_kpi_ratio_comparison.pdf"
            _plot_ratio_comparison(
                summary_df=summary_df,
                title=f"Reference KPI comparison - {cluster_root.name}",
                save_path=figure_path,
            )
            print(f"  - saved figure: {figure_path}")
        else:
            figure_path = output_dir / "reference_kpi_absolute_comparison.pdf"
            _plot_absolute_comparison(
                summary_df=summary_df,
                title=f"Reference KPI comparison (absolute) - {cluster_root.name}",
                save_path=figure_path,
            )
            print(f"  - no 'reference' payload found, saved absolute figure: {figure_path}")


if __name__ == "__main__":
    main()
