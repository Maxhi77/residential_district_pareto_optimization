import math

import pandas as pd
import pytest

solph = pytest.importorskip("oemof.solph")
po = pytest.importorskip("pyomo.environ")

from oemof.solph import Flow
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses
from oemof.thermal_building_model.oemof_facades.infrastructure.carriers import (
    ElectricityCarrier,
    GasCarrier,
    HeatCarrier,
    HydrogenCarrier,
)
from oemof.thermal_building_model.oemof_facades.infrastructure.demands import (
    ElectricityDemand,
    HeatDemand,
    WarmWater,
)
from oemof.thermal_building_model.oemof_facades.infrastructure.grids import (
    ElectricityGrid,
    GasGrid,
    HydrogenGrid,
)
from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import (
    ThermalBuilding,
)
from oemof.thermal_building_model.oemof_facades.technologies.converter import (
    AirHeatPump,
    CHP,
    GasHeater,
)
from oemof.thermal_building_model.oemof_facades.technologies.heat_grid import (
    HeatGridInvestment,
)
from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import (
    PVSystem,
)
from oemof.thermal_building_model.oemof_facades.technologies.storages import (
    Battery,
    HotWaterTank,
)


def _find_available_solver():
    for solver_name in ("gurobi", "cbc", "glpk", "highs"):
        solver = po.SolverFactory(solver_name)
        try:
            if solver.available(exception_flag=False):
                return solver_name
        except Exception:
            continue
    return None


@pytest.fixture(scope="module")
def available_solver():
    solver = _find_available_solver()
    if solver is None:
        pytest.skip(
            "No MILP solver available (checked: gurobi, cbc, glpk, highs). "
            "Install one of them to run solver-backed tests."
        )
    return solver


def _safe_add(es, component):
    if isinstance(component, dict):
        for value in component.values():
            es.add(value)
    elif isinstance(component, (list, tuple, set)):
        for value in component:
            _safe_add(es, value)
    else:
        es.add(component)


def _build_policy_system(max_peak_from_grid=None):
    n = 4
    timeindex = pd.date_range("2022-01-01", periods=n, freq="h")
    es = solph.EnergySystem(timeindex=timeindex, infer_last_interval=False)

    electricity_grid = ElectricityGrid(
        max_peak_from_grid=max_peak_from_grid, max_peak_into_grid=max_peak_from_grid
    )
    electricity_grid.operation_grid.working_rate = 0.08
    electricity_grid.operation_grid.co2_per_flow = 0.50
    electricity_grid.operation_grid.revenue = 0.0
    gas_grid = GasGrid(name="NaturalGas")
    hydrogen_grid = HydrogenGrid(name="Hydrogen")
    hydrogen_grid.operation_grid.working_rate = 2.0
    hydrogen_grid.operation_grid.co2_per_flow = 0.01

    b_elec = ElectricityCarrier(name="PolicyElectricityCarrier").get_bus()
    b_gas = GasCarrier(name="PolicyGasCarrier").get_bus()
    b_hydrogen = HydrogenCarrier(name="PolicyHydrogenCarrier").get_bus()
    b_heat = HeatCarrier(name="PolicyHeatCarrier", levels=[50, 70]).get_bus()

    # Carriers from grids (same pattern as the examples).
    connect_buses(
        input=electricity_grid.get_bus_from_grid(),
        target=b_elec,
        output=electricity_grid.get_bus_into_grid(),
    )
    connect_buses(input=gas_grid.get_bus_from_grid(), target=b_gas)
    connect_buses(input=hydrogen_grid.get_bus_from_grid(), target=b_hydrogen)

    e_source = electricity_grid.create_source()
    e_sink = electricity_grid.create_sink()
    g_source = gas_grid.create_source()
    h2_source = hydrogen_grid.create_source()

    electricity_demand = ElectricityDemand(
        name="policy_electricity", value_list=[12.0, 2.0, 2.0, 2.0], bus=b_elec
    ).create_demand()

    # CHP provides an alternative electricity supply route for CO2 and peak tests.
    chp = CHP(investment=False, name="policy_chp", nominal_power=20.0)
    chp_bus = chp.get_bus()
    chp_source = chp.create_source()
    chp_converters = chp.create_converters(
        chp_bus=chp_bus,
        gas_bus=b_hydrogen,
        electricity_bus=b_elec,
        heat_carrier_bus=b_heat,
    )
    heat_dumps = [
        solph.components.Sink(label=f"policy_heat_dump_{lvl}", inputs={bus: Flow()})
        for lvl, bus in b_heat.items()
    ]

    _safe_add(
        es,
        [
            electricity_grid.get_bus_from_grid(),
            electricity_grid.get_bus_into_grid(),
            gas_grid.get_bus_from_grid(),
            hydrogen_grid.get_bus_from_grid(),
            b_elec,
            b_gas,
            b_hydrogen,
            b_heat,
            e_source,
            e_sink,
            g_source,
            h2_source,
            electricity_demand,
            chp_bus,
            chp_source,
            chp_converters,
            heat_dumps,
        ],
    )

    return es, {
        "electricity_grid": electricity_grid,
        "gas_grid": gas_grid,
        "hydrogen_grid": hydrogen_grid,
        "electricity_source": e_source,
        "electricity_sink": e_sink,
        "gas_source": g_source,
        "hydrogen_source": h2_source,
    }


def _solve_and_collect(es, components, solver, co2_limit=None):
    model = solph.Model(es)
    if co2_limit is not None:
        model = solph.constraints.additional_total_limit(model, "co2", limit=co2_limit)

    cmdline_options = {}
    if solver == "gurobi":
        cmdline_options = {"MIPGap": 0, "Threads": 1, "Seed": 0}
    solve_result = model.solve(
        solver=solver,
        solve_kwargs={"tee": False},
        cmdline_options=cmdline_options,
    )
    termination = str(solve_result.solver.termination_condition).lower()
    assert termination in {"optimal", "feasible"}

    results = solph.processing.results(model)
    meta = solph.processing.meta_results(model)

    p_elec = components["electricity_grid"].post_process(
        results, components["electricity_source"], components["electricity_sink"]
    )
    p_gas = components["gas_grid"].post_process(results, components["gas_source"], None)
    p_h2 = components["hydrogen_grid"].post_process(
        results, components["hydrogen_source"], None
    )
    total_co2 = (
        p_elec["flow_from_grid_co2"]
        - p_elec["flow_into_grid_co2"]
        + p_gas["flow_from_grid_co2"]
        + p_h2["flow_from_grid_co2"]
    )
    return {
        "results": results,
        "meta": meta,
        "objective": float(meta["objective"]),
        "total_co2": float(total_co2),
        "peak_from_grid": float(p_elec["peak_from_grid"]),
    }


def test_co2_constraint_regression_reduces_emissions(available_solver):
    es_base, comp_base = _build_policy_system(max_peak_from_grid=None)
    base = _solve_and_collect(es_base, comp_base, solver=available_solver)

    assert math.isfinite(base["objective"])
    assert base["total_co2"] > 0

    co2_cap = base["total_co2"] * 0.80
    es_cap, comp_cap = _build_policy_system(max_peak_from_grid=None)
    constrained = _solve_and_collect(
        es_cap, comp_cap, solver=available_solver, co2_limit=co2_cap
    )

    assert math.isfinite(constrained["objective"])
    assert constrained["total_co2"] <= co2_cap + 1e-6
    assert constrained["total_co2"] < base["total_co2"] - 1e-6


def test_peak_constraint_regression_reduces_grid_peak(available_solver):
    es_base, comp_base = _build_policy_system(max_peak_from_grid=None)
    base = _solve_and_collect(es_base, comp_base, solver=available_solver)
    assert base["peak_from_grid"] > 0

    peak_cap = base["peak_from_grid"] * 0.80
    es_peak, comp_peak = _build_policy_system(max_peak_from_grid=peak_cap)
    constrained = _solve_and_collect(es_peak, comp_peak, solver=available_solver)

    assert constrained["peak_from_grid"] <= peak_cap + 1e-6
    assert constrained["peak_from_grid"] < base["peak_from_grid"] - 1e-6


def test_co2_and_peak_50_percent_reduction(available_solver):
    es_base, comp_base = _build_policy_system(max_peak_from_grid=None)
    base = _solve_and_collect(es_base, comp_base, solver=available_solver)

    assert math.isfinite(base["objective"])
    assert base["total_co2"] > 0
    assert base["peak_from_grid"] > 0

    co2_cap_50 = base["total_co2"] * 0.50
    peak_cap_50 = base["peak_from_grid"] * 0.50

    es_reduced, comp_reduced = _build_policy_system(max_peak_from_grid=peak_cap_50)
    reduced = _solve_and_collect(
        es_reduced,
        comp_reduced,
        solver=available_solver,
        co2_limit=co2_cap_50,
    )

    assert math.isfinite(reduced["objective"])
    assert reduced["total_co2"] <= co2_cap_50 + 1e-6
    assert reduced["peak_from_grid"] <= peak_cap_50 + 1e-6
    assert reduced["total_co2"] < base["total_co2"] - 1e-6
    assert reduced["peak_from_grid"] < base["peak_from_grid"] - 1e-6


def test_technology_and_refurbishment_object_coverage_solve_path(available_solver):
    n = 4
    timeindex = pd.date_range("2022-01-01", periods=n, freq="h")
    es = solph.EnergySystem(timeindex=timeindex, infer_last_interval=False)

    electricity_grid = ElectricityGrid()
    gas_grid = GasGrid(name="NaturalGas")
    hydrogen_grid = HydrogenGrid(name="Hydrogen")
    e_carrier = ElectricityCarrier(name="CoverageElectricityCarrier")
    g_carrier = GasCarrier(name="CoverageGasCarrier")
    h2_carrier = HydrogenCarrier(name="CoverageHydrogenCarrier")
    h_carrier = HeatCarrier(name="CoverageHeatCarrier", levels=[40, 50, 70])
    h_carrier.connect_buses_decreasing_levels()

    b_e = e_carrier.get_bus()
    b_g = g_carrier.get_bus()
    b_h2 = h2_carrier.get_bus()
    b_h = h_carrier.get_bus()

    connect_buses(
        input=electricity_grid.get_bus_from_grid(),
        target=b_e,
        output=electricity_grid.get_bus_into_grid(),
    )
    connect_buses(input=gas_grid.get_bus_from_grid(), target=b_g)
    connect_buses(input=hydrogen_grid.get_bus_from_grid(), target=b_h2)

    e_source = electricity_grid.create_source()
    e_sink = electricity_grid.create_sink()
    g_source = gas_grid.create_source()
    h2_source = hydrogen_grid.create_source()

    e_demand_dc = ElectricityDemand(
        name="coverage_electricity", value_list=[2.0, 2.0, 2.0, 2.0], bus=b_e
    )
    e_demand = e_demand_dc.create_demand()
    ww_demand_dc = WarmWater(
        name="coverage_warmwater", value_list=pd.Series([10.0, 10.0, 10.0, 10.0]), level=50, bus=b_h[50]
    )
    ww_demand = ww_demand_dc.create_demand()

    pv_dc = PVSystem(
        investment=False, name="coverage_pv", nominal_power=2.0, value_list=[0.0, 0.0, 1.0, 1.0]
    )
    pv_bus = pv_dc.get_bus()
    pv_source = pv_dc.create_source()
    pv_sink = pv_dc.create_sink()
    connect_buses(input=pv_bus, target=b_e)

    battery_dc = Battery(
        investment=False,
        name="coverage_battery",
        input_bus=b_e,
        output_bus=b_e,
        nominal_capacity=4.0,
        balanced=False,
        initial_storage_level=0.5,
    )
    battery = battery_dc.create_storage()

    tank_dc = HotWaterTank(
        investment=False,
        name="coverage_hot_water_tank",
        temperature_buses=b_h,
        max_temperature=70,
        min_temperature=40,
        input_bus=b_h[70],
        output_bus=b_h[70],
        volume_in_m3=0.2,
    )
    tank = tank_dc.create_storage()

    gh_dc = GasHeater(investment=False, name="coverage_gas_heater")
    gh_bus = gh_dc.get_bus()
    gh_source = gh_dc.create_source()
    gh_converters = gh_dc.create_converters(
        gas_heater_bus=gh_bus, gas_bus=b_g, heat_carrier_bus=b_h
    )

    hp_dc = AirHeatPump(
        investment=False,
        name="coverage_air_heat_pump",
        air_temperature=[5.0] * n,
    )
    hp_bus = hp_dc.get_bus()
    hp_source = hp_dc.create_source()
    hp_converters = hp_dc.create_converters(
        heat_pump_bus=hp_bus, electricity_bus=b_e, heat_carrier_bus=b_h
    )

    chp_dc = CHP(investment=False, name="coverage_chp")
    chp_bus = chp_dc.get_bus()
    chp_source = chp_dc.create_source()
    chp_converters = chp_dc.create_converters(
        chp_bus=chp_bus, gas_bus=b_h2, electricity_bus=b_e, heat_carrier_bus=b_h
    )

    # Refurbishment object from oemof_facades/refurbishment.
    building_dc = ThermalBuilding(
        name="coverage_building",
        number_of_time_steps=n,
        number_of_occupants=2,
        number_of_household=1,
        country="DE",
        construction_year=1980,
        floor_area=120,
        class_building="average",
        building_type="SFH",
        refurbishment_status="no_refurbishment",
        heat_level_calculation=True,
        time_index=timeindex,
    )
    building_dc.bus = b_h
    building_demand = building_dc.create_demand()

    heat_grid_dc = HeatGridInvestment(
        name="coverage_heat_grid",
        heat_transfer_station_max_kW=[(5, 2)],
        pipe_length_in_meter=30,
        peak_load_in_kw=10,
        flow_temperature=50,
        total_heat_demand=200,
        fictional_demand=4,
    )
    heat_grid_dc.value_list = [1.0, 1.0, 1.0, 1.0]
    heat_grid_dc.tsam_total_amount = 4.0
    heat_grid_bus = heat_grid_dc.get_bus()
    heat_grid_source = heat_grid_dc.create_source(heat_grid_bus)
    heat_grid_sink = heat_grid_dc.create_sink(heat_grid_bus)

    _safe_add(
        es,
        [
            electricity_grid.get_bus_from_grid(),
            electricity_grid.get_bus_into_grid(),
            gas_grid.get_bus_from_grid(),
            hydrogen_grid.get_bus_from_grid(),
            b_e,
            b_g,
            b_h2,
            b_h,
            pv_bus,
            heat_grid_bus,
            e_source,
            e_sink,
            g_source,
            h2_source,
            e_demand,
            ww_demand,
            pv_source,
            pv_sink,
            battery,
            tank,
            gh_bus,
            gh_source,
            gh_converters,
            hp_bus,
            hp_source,
            hp_converters,
            chp_bus,
            chp_source,
            chp_converters,
            building_demand,
            heat_grid_source,
            heat_grid_sink,
        ],
    )

    model = solph.Model(es)
    solve_result = model.solve(solver=available_solver, solve_kwargs={"tee": False})
    termination = str(solve_result.solver.termination_condition).lower()
    assert termination in {"optimal", "feasible"}

    results = solph.processing.results(model)
    labels = {node.label for node in es.nodes}

    # Coverage: infrastructure and facade technologies are present.
    assert any("coverageelectricitycarrier" in lbl.lower() for lbl in labels)
    assert any("coverageheatcarrier_50" in lbl.lower() for lbl in labels)
    assert any("coverage_gas_heater_source" in lbl.lower() for lbl in labels)
    assert any("coverage_air_heat_pump_source" in lbl.lower() for lbl in labels)
    assert any("coverage_chp_source" in lbl.lower() for lbl in labels)
    assert any("coverage_pv_source" in lbl.lower() for lbl in labels)
    assert any("coverage_hot_water_tank" in lbl.lower() for lbl in labels)
    assert any("coverage_battery" in lbl.lower() for lbl in labels)
    assert any("coverage_building" in lbl.lower() for lbl in labels)
    assert any("coverage_heat_grid_source" in lbl.lower() for lbl in labels)

    # Coverage: result structures exist for representative technology objects.
    assert solph.views.node(results, "coverage_gas_heater_source")["sequences"].shape[0] == n
    assert solph.views.node(results, "coverage_air_heat_pump_source")["sequences"].shape[0] == n
    assert solph.views.node(results, "coverage_chp_source")["sequences"].shape[0] == n
    assert solph.views.node(results, "coverage_pv_source")["sequences"].shape[0] == n
    assert solph.views.node(results, "coverage_building_lvlTrue_demand")["sequences"].shape[0] == n
