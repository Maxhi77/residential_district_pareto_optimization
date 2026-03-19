import math

import pandas as pd
import pytest

solph = pytest.importorskip("oemof.solph")
po = pytest.importorskip("pyomo.environ")

from oemof.solph import views
from oemof.thermal_building_model.helpers.post_processing import (
    calc_excess_temperature_degree_hours,
)
from oemof.thermal_building_model.m_5RC import M5RC
from oemof.thermal_building_model.tabula.tabula_reader import (
    BuildingConfig5RC,
    BuildingParameters,
)

_TRANSFORMER_CLS = getattr(solph.components, "Transformer", solph.components.Converter)


@pytest.fixture
def building_config():
    return BuildingConfig5RC(
        total_internal_area=180.0,
        h_ve=80.0,
        h_tr_w=25.0,
        h_tr_em=90.0,
        h_tr_is=110.0,
        mass_area=90.0,
        h_tr_ms=220.0,
        c_m=2_500_000.0,
        floor_area=120.0,
        heat_transfer_coefficient_ventilation=0.5,
        total_air_change_rate=0.4,
    )


def _build_toy_model(
    building_config,
    *,
    n_steps,
    t_outside,
    internal_gains,
    solar_gains,
    t_set_heating,
    t_set_cooling,
    initial_temperature=20.0,
    grid_cost=1.0,
):
    timeindex = pd.date_range("2020-01-01", periods=n_steps, freq="h")
    es = solph.EnergySystem(timeindex=timeindex, infer_last_interval=False)

    b_heat = solph.buses.Bus(label="b_heat")
    b_cool = solph.buses.Bus(label="b_cool")
    b_elec = solph.buses.Bus(label="b_elec")
    es.add(b_heat, b_cool, b_elec)

    es.add(
        solph.components.Source(
            label="grid",
            outputs={b_elec: solph.flows.Flow(variable_costs=grid_cost)},
        )
    )
    es.add(
        _TRANSFORMER_CLS(
            label="heater",
            inputs={b_elec: solph.flows.Flow()},
            outputs={b_heat: solph.flows.Flow()},
            conversion_factors={b_heat: 1.0},
        )
    )

    building = M5RC(
        label="building",
        inputs={b_heat: solph.flows.Flow(variable_costs=0)},
        outputs={b_cool: solph.flows.Flow(variable_costs=0)},
        building_config=building_config,
        t_outside=t_outside,
        internal_gains=internal_gains,
        solar_gains=solar_gains,
        t_set_heating=t_set_heating,
        t_set_cooling=t_set_cooling,
        t_inital=initial_temperature,
    )
    es.add(building)

    model = solph.Model(es)
    return es, model, building


def _get_series_by_attr(results, node_label, attr_name):
    sequences = views.node(results, node_label)["sequences"]
    cols = [col for col in sequences.columns if col[1] == attr_name]
    assert len(cols) == 1, f"Expected exactly one '{attr_name}' column, found {len(cols)}."
    return sequences[cols[0]]


def _get_building_heat_flow(results):
    sequences = views.node(results, "building")["sequences"]
    cols = [
        col
        for col in sequences.columns
        if col[1] == "flow" and col[0][1] == "building"
    ]
    assert len(cols) == 1, "Expected one inflow into building."
    return sequences[cols[0]]


def _get_building_cool_flow(results):
    sequences = views.node(results, "building")["sequences"]
    cols = [
        col
        for col in sequences.columns
        if col[1] == "flow" and col[0][0] == "building"
    ]
    assert len(cols) == 1, "Expected one outflow from building."
    return sequences[cols[0]]


def test_model_structure_minimal_case(building_config):
    n_steps = 4
    _, model, building = _build_toy_model(
        building_config,
        n_steps=n_steps,
        t_outside=[20.0] * n_steps,
        internal_gains=[0.0] * n_steps,
        solar_gains=[0.0] * n_steps,
        t_set_heating=20.0,
        t_set_cooling=25.0,
        initial_temperature=20.0,
    )

    block = model.GenericBuildingBlock
    assert len(block.BUILDING) == 1
    assert building in list(block.BUILDING)
    assert len(block.t_air) == len(model.TIMEPOINTS)
    assert len(block.t_m_ts) == len(model.TIMEPOINTS)
    assert len(block.balance_t_air) == len(model.TIMEINDEX)
    assert len(block.balance_t_m_current_t_s) == len(model.TIMEINDEX)
    assert block.t_air[building, 0].fixed
    assert block.t_air[building, 0].value == pytest.approx(20.0, abs=1e-9)


def test_model_structure_with_time_varying_bounds(building_config):
    n_steps = 5
    t_set_heating = [19.0, 19.5, 20.0, 20.5, 21.0]
    t_set_cooling = [24.0, 24.5, 25.0, 25.5, 26.0]

    _, model, building = _build_toy_model(
        building_config,
        n_steps=n_steps,
        t_outside=[18.0] * n_steps,
        internal_gains=[0.0] * n_steps,
        solar_gains=[0.0] * n_steps,
        t_set_heating=t_set_heating,
        t_set_cooling=t_set_cooling,
        initial_temperature=20.0,
    )

    block = model.GenericBuildingBlock
    first_idx = min(model.TIMEPOINTS)
    last_idx = max(model.TIMEPOINTS)
    assert block.t_air[building, first_idx].lb == pytest.approx(t_set_heating[0], abs=1e-9)
    assert block.t_air[building, first_idx].ub == pytest.approx(t_set_cooling[0], abs=1e-9)
    assert block.t_air[building, last_idx].lb == pytest.approx(t_set_heating[-1], abs=1e-9)
    assert block.t_air[building, last_idx].ub == pytest.approx(t_set_cooling[-1], abs=1e-9)


def test_solve_toy_case_zero_demand(available_solver, building_config):
    n_steps = 4
    es, model, _ = _build_toy_model(
        building_config,
        n_steps=n_steps,
        t_outside=[20.0] * n_steps,
        internal_gains=[0.0] * n_steps,
        solar_gains=[0.0] * n_steps,
        t_set_heating=20.0,
        t_set_cooling=20.0,
        initial_temperature=20.0,
        grid_cost=1.0,
    )

    solve_result = model.solve(solver=available_solver, solve_kwargs={"tee": False})
    termination = str(solve_result.solver.termination_condition).lower()
    assert termination in {"optimal", "feasible"}

    results = solph.processing.results(model)
    es.results["main"] = results
    t_air = _get_series_by_attr(results, "building", "t_air")
    heat_flow = _get_building_heat_flow(results)
    cool_flow = _get_building_cool_flow(results)

    for value in t_air.values:
        assert value == pytest.approx(20.0, abs=1e-6)
    assert math.isclose(float(heat_flow.sum()), 0.0, abs_tol=1e-8)
    assert math.isclose(float(cool_flow.sum()), 0.0, abs_tol=1e-8)
    assert po.value(model.objective) == pytest.approx(0.0, abs=1e-8)


def test_solve_toy_case_heating_sign_and_objective(available_solver, building_config):
    n_steps = 4
    _, model, _ = _build_toy_model(
        building_config,
        n_steps=n_steps,
        t_outside=[0.0] * n_steps,
        internal_gains=[0.0] * n_steps,
        solar_gains=[0.0] * n_steps,
        t_set_heating=20.0,
        t_set_cooling=20.0,
        initial_temperature=20.0,
        grid_cost=1.0,
    )

    solve_result = model.solve(solver=available_solver, solve_kwargs={"tee": False})
    termination = str(solve_result.solver.termination_condition).lower()
    assert termination in {"optimal", "feasible"}

    results = solph.processing.results(model)
    t_air = _get_series_by_attr(results, "building", "t_air")
    heat_flow = _get_building_heat_flow(results)
    cool_flow = _get_building_cool_flow(results)

    for value in t_air.values:
        assert value == pytest.approx(20.0, abs=1e-5)
    assert float(heat_flow.sum()) > 0.0
    assert math.isclose(float(cool_flow.sum()), 0.0, abs_tol=1e-8)
    assert po.value(model.objective) == pytest.approx(float(heat_flow.sum()), abs=1e-5)


def test_input_validation_rejects_multiple_inputs(building_config):
    b1 = solph.buses.Bus(label="b1")
    b2 = solph.buses.Bus(label="b2")
    b3 = solph.buses.Bus(label="b3")

    building = M5RC(
        label="invalid_building",
        inputs={b1: solph.flows.Flow(), b2: solph.flows.Flow()},
        outputs={b3: solph.flows.Flow()},
        building_config=building_config,
        t_outside=[20.0],
        internal_gains=[0.0],
        solar_gains=[0.0],
        t_set_heating=20.0,
        t_set_cooling=25.0,
    )

    with pytest.raises(AttributeError, match="Only one input flow allowed"):
        building._check_number_of_flows()


def test_input_validation_rejects_invalid_parameter_dict_keys():
    with pytest.raises(ValueError, match="All keys in a_wall must start with a_wall_"):
        BuildingParameters(
            floor_area=100.0,
            heat_transfer_coefficient_ventilation=0.5,
            total_air_change_rate=0.4,
            room_height=2.5,
            frame_area_fraction_of_window=0.2,
            radiation_non_perpendicular_to_the_glazing=0.9,
            a_wall={"wall_bad_key": 10.0},
        )


def test_input_validation_rejects_missing_window_specific_keys():
    with pytest.raises(ValueError, match="All keys in a_window_specific must be one of"):
        BuildingParameters(
            floor_area=100.0,
            heat_transfer_coefficient_ventilation=0.5,
            total_air_change_rate=0.4,
            room_height=2.5,
            frame_area_fraction_of_window=0.2,
            radiation_non_perpendicular_to_the_glazing=0.9,
            a_window_specific={
                "a_window_east": 10.0,
                "a_window_south": 10.0,
                "a_window_west": 10.0,
            },
        )


def test_results_extraction_structure_and_boundary_timesteps(
    available_solver, building_config
):
    n_steps = 6
    es, model, _ = _build_toy_model(
        building_config,
        n_steps=n_steps,
        t_outside=[20.0] * n_steps,
        internal_gains=[0.0] * n_steps,
        solar_gains=[0.0] * n_steps,
        t_set_heating=20.0,
        t_set_cooling=20.0,
        initial_temperature=20.0,
    )

    model.solve(solver=available_solver, solve_kwargs={"tee": False})
    results = solph.processing.results(model)
    node_data = views.node(results, "building")

    assert "sequences" in node_data
    assert "scalars" in node_data
    sequences = node_data["sequences"]
    t_air = _get_series_by_attr(results, "building", "t_air")
    heat_flow = _get_building_heat_flow(results)

    assert len(sequences.index) == n_steps
    assert sequences.index[0] == es.timeindex[0]
    assert sequences.index[-1] == es.timeindex[-1]
    assert len(t_air) == n_steps
    assert math.isclose(float(heat_flow.sum()), 0.0, abs_tol=1e-8)


def test_post_processing_excess_temperature_degree_hours():
    t_air = [24.0, 26.0, 27.5, 30.0]
    result = calc_excess_temperature_degree_hours(t_air, boundary_temp=26.0)
    assert result == pytest.approx(5.5, abs=1e-12)
