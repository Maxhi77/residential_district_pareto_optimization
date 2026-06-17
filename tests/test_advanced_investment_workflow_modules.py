import importlib.util
import math
from pathlib import Path

import pytest

from oemof.thermal_building_model.oemof_facades.scenario_blocks.constraint_reduction_workflow import (
    run_stepwise_co2_peak_reduction,
)
from oemof.thermal_building_model.oemof_facades.scenario_blocks.workflow_preprocessing import (
    build_centralized_scenarios,
    deduplicate_scenarios_by_choice,
)


def _load_example_module(filename: str):
    repo_root = Path(__file__).resolve().parents[1]
    module_path = (
        repo_root
        / "src"
        / "oemof"
        / "thermal_building_model"
        / "examples"
        / "03_applied_energy_optimization"
        / filename
    )
    spec = importlib.util.spec_from_file_location(f"tbm_test_{filename}", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deduplicate_scenarios_by_choice():
    scenarios = [
        {"name": "s1", "choice": {"a": "no_refurbishment"}},
        {"name": "s2", "choice": {"a": "no_refurbishment"}},
        {"name": "s3", "choice": {"a": "advanced_refurbishment"}},
    ]
    deduped = deduplicate_scenarios_by_choice(scenarios)
    assert len(deduped) == 2
    assert deduped[0]["name"] == "s1"
    assert deduped[1]["name"] == "s3"


def test_build_centralized_scenarios_pipeline():
    called = {"remove": False}

    def _fake_build_scenarios(**_kwargs):
        return (
            [
                {"name": "s1", "choice": {"b1": "no_refurbishment"}},
                {"name": "s2", "choice": {"b1": "no_refurbishment"}},
                {"name": "s3", "choice": {"b1": "usual_refurbishment"}},
            ],
            {"b1": {}},
            {"b1": []},
        )

    def _fake_remove_duplicate_scenarios(scenarios):
        called["remove"] = True
        return list(scenarios)

    scenarios, buildings_all, available = build_centralized_scenarios(
        matching_buildings_sfh={"b1": {}},
        matching_buildings_mfh={},
        build_scenarios_fn=_fake_build_scenarios,
        remove_duplicate_scenarios_fn=_fake_remove_duplicate_scenarios,
    )
    assert called["remove"] is True
    assert len(scenarios) == 2
    assert isinstance(buildings_all, dict)
    assert isinstance(available, dict)


def test_stepwise_co2_peak_helper_persists(tmp_path):
    def _run_case(co2_limit, peak_limit):
        co2_value = 100.0 if co2_limit is None else float(min(100.0, co2_limit))
        peak = 10.0 if peak_limit is None else float(min(10.0, peak_limit))
        result = {
            "totex": 1000.0 - 0.1 * (100.0 - co2_value) - 0.2 * (10.0 - peak),
            "Electricity": {
                "peak_from_grid": peak,
                "peak_into_grid": peak / 2.0,
            },
        }
        return result, co2_value, 0.01, "optimal"

    out_path = tmp_path / "stepwise.pkl"
    summary = run_stepwise_co2_peak_reduction(
        _run_case,
        co2_reduction_factors=(1.0, 0.5),
        peak_reduction_factors=(1.0, 0.5),
        output_path=out_path,
    )
    assert out_path.exists()
    assert summary["saved_path"] == str(out_path)
    assert summary["co2_reference"] == pytest.approx(100.0)
    assert summary["peak_reference"] == pytest.approx(10.0)
    assert len(summary["results_by_key"]) >= 2


@pytest.mark.usefixtures("available_solver")
def test_decentralized_blocks_stepwise_and_single_run_equivalent_baseline(
    available_solver, tmp_path
):
    module = _load_example_module(
        "07_decentralized_supply_single_building_multiple_heat_carrier_levels_blocks.py"
    )
    cfg = module.ScenarioConfig(
        n_steps=4,
        solver=available_solver,
        output_results_path=str(tmp_path / "dec_stepwise.pkl"),
    )
    single_results, single_co2, _, single_status = module.run_model(cfg)
    assert single_status in {"optimal", "feasible"}
    assert math.isfinite(float(single_results["totex"]))
    assert math.isfinite(float(single_co2))

    summary = module.run_stepwise_workflow(
        cfg=cfg,
        co2_reduction_factors=(1.0,),
        peak_reduction_factors=(1.0,),
    )
    baseline = summary["results_by_key"][summary["baseline_key"]]
    assert baseline["termination"] in {"optimal", "feasible", None}
    assert baseline["totex"] == pytest.approx(float(single_results["totex"]), abs=1e-6)
    assert baseline["co2"] == pytest.approx(float(single_co2), abs=1e-6)
    assert Path(summary["saved_path"]).exists()


@pytest.mark.usefixtures("available_solver")
def test_centralized_blocks_stepwise_and_single_run_equivalent_baseline(
    available_solver, tmp_path
):
    module = _load_example_module(
        "08_centralized_supply_multiple_buildings_multiple_heat_carrier_levels_blocks.py"
    )
    cfg = module.ScenarioConfig(
        n_steps=4,
        solver=available_solver,
        output_results_path=str(tmp_path / "cen_stepwise.pkl"),
    )
    single_results, single_co2, _, single_status = module.run_model(cfg)
    assert single_status in {"optimal", "feasible"}
    assert math.isfinite(float(single_results["totex"]))
    assert math.isfinite(float(single_co2))

    summary = module.run_stepwise_workflow(
        cfg=cfg,
        co2_reduction_factors=(1.0,),
        peak_reduction_factors=(1.0,),
    )
    baseline = summary["results_by_key"][summary["baseline_key"]]
    assert baseline["termination"] in {"optimal", "feasible", None}
    assert baseline["totex"] == pytest.approx(float(single_results["totex"]), abs=1e-6)
    assert baseline["co2"] == pytest.approx(float(single_co2), abs=1e-6)
    assert Path(summary["saved_path"]).exists()

