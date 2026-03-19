import math
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

solph = pytest.importorskip("oemof.solph")

from oemof.solph import Flow
from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents
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
)
from oemof.thermal_building_model.oemof_facades.infrastructure.grids import (
    ElectricityGrid,
    GasGrid,
    HydrogenGrid,
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

def _new_es(n=4):
    tindex = pd.date_range("2020-01-01", periods=n, freq="h")
    return solph.EnergySystem(timeindex=tindex, infer_last_interval=False)


def _inv(
    *,
    maximum_capacity,
    minimum_capacity,
    cost_per_unit,
    cost_offset=5,
    co2_per_capacity=4,
    co2_offset=10,
    lifetime=20,
):
    return InvestmentComponents(
        maximum_capacity=maximum_capacity,
        minimum_capacity=minimum_capacity,
        cost_per_unit=cost_per_unit,
        cost_offset=cost_offset,
        co2_per_capacity=co2_per_capacity,
        co2_offset=co2_offset,
        lifetime=lifetime,
    )


def _add_electricity_infrastructure(es, max_peak_from_grid=None, max_peak_into_grid=None):
    if max_peak_from_grid is None and max_peak_into_grid is None:
        grid = ElectricityGrid(name="Electricity")
    else:
        grid = ElectricityGrid(
            name="Electricity",
            max_peak_from_grid=max_peak_from_grid,
            max_peak_into_grid=max_peak_into_grid,
        )
    grid.operation_grid.revenue = 0.0
    bus_from = grid.get_bus_from_grid()
    bus_into = grid.get_bus_into_grid()
    sink = grid.create_sink()
    source = grid.create_source()
    carrier = ElectricityCarrier(name="electricity_carrier")
    carrier_bus = carrier.get_bus()
    connect_buses(input=bus_from, target=carrier_bus, output=bus_into)
    es.add(bus_from, bus_into, sink, source, carrier_bus)
    return {"grid": grid, "bus": carrier_bus, "source": source, "sink": sink}


def _add_gas_infrastructure(es, grid_name="NaturalGas", carrier_name="gas_carrier"):
    grid = GasGrid(name=grid_name)
    grid.operation_grid.revenue = 0.0
    bus_from = grid.get_bus_from_grid()
    source = grid.create_source()
    carrier = GasCarrier(name=carrier_name)
    carrier_bus = carrier.get_bus()
    connect_buses(input=bus_from, target=carrier_bus)
    es.add(bus_from, source, carrier_bus)
    return {"grid": grid, "bus": carrier_bus, "source": source}


def _add_hydrogen_infrastructure(es, grid_name="Hydrogen", carrier_name="hydrogen_carrier"):
    grid = HydrogenGrid(name=grid_name)
    grid.operation_grid.revenue = 0.0
    bus_from = grid.get_bus_from_grid()
    source = grid.create_source()
    carrier = HydrogenCarrier(name=carrier_name)
    carrier_bus = carrier.get_bus()
    connect_buses(input=bus_from, target=carrier_bus)
    es.add(bus_from, source, carrier_bus)
    return {"grid": grid, "bus": carrier_bus, "source": source}


def _build_gas_heater_case():
    es = _new_es()
    _add_electricity_infrastructure(es)
    gas = _add_gas_infrastructure(es)

    heat_carrier = HeatCarrier(name="heat_carrier_gas_heater", levels=[50])
    heat_bus = heat_carrier.get_bus()
    es.add(*heat_bus.values())

    demand_dc = HeatDemand(
        name="heat_demand_gas_heater",
        value_list=[5.0, 6.0, 5.0, 4.0],
        level=50,
        bus=heat_bus[50],
    )
    demand = demand_dc.create_demand()

    tech_dc = GasHeater(
        investment=True,
        name="gas_heater_case",
        investment_component=_inv(
            maximum_capacity=30.0,
            minimum_capacity=0.1,
            cost_per_unit=300.0,
            cost_offset=200.0,
            co2_per_capacity=0.05,
            lifetime=20,
        ),
    )
    tech_bus = tech_dc.get_bus()
    tech_source = tech_dc.create_source()
    tech_converters = tech_dc.create_converters(
        gas_heater_bus=tech_bus,
        gas_bus=gas["bus"],
        heat_carrier_bus=heat_bus,
    )
    es.add(tech_bus, tech_source, *tech_converters, demand)
    return es, tech_dc, tech_source, tech_converters, heat_bus, gas["bus"]


def _build_air_heat_pump_case():
    es = _new_es()
    electricity = _add_electricity_infrastructure(es)

    heat_carrier = HeatCarrier(name="heat_carrier_hp", levels=[50])
    heat_bus = heat_carrier.get_bus()
    es.add(*heat_bus.values())

    demand = HeatDemand(
        name="heat_demand_hp",
        value_list=[4.0, 4.0, 4.0, 4.0],
        level=50,
        bus=heat_bus[50],
    ).create_demand()

    tech_dc = AirHeatPump(
        investment=True,
        name="air_heat_pump_case",
        air_temperature=[5.0, 5.0, 5.0, 5.0],
        investment_component=_inv(
            maximum_capacity=20.0,
            minimum_capacity=0.1,
            cost_per_unit=500.0,
            cost_offset=200.0,
            co2_per_capacity=0.03,
            lifetime=20,
        ),
    )
    tech_bus = tech_dc.get_bus()
    tech_source = tech_dc.create_source()
    tech_converters = tech_dc.create_converters(
        heat_pump_bus=tech_bus,
        electricity_bus=electricity["bus"],
        heat_carrier_bus=heat_bus,
    )
    es.add(tech_bus, tech_source, *tech_converters, demand)
    return es, tech_dc, tech_source, tech_converters, heat_bus, electricity["bus"]


def _build_chp_case():
    es = _new_es()
    electricity = _add_electricity_infrastructure(es)
    hydrogen = _add_hydrogen_infrastructure(es)

    heat_carrier = HeatCarrier(name="heat_carrier_chp", levels=[50])
    heat_bus = heat_carrier.get_bus()
    es.add(*heat_bus.values())

    heat_demand = HeatDemand(
        name="heat_demand_chp",
        value_list=[3.0, 3.0, 3.0, 3.0],
        level=50,
        bus=heat_bus[50],
    ).create_demand()

    # Keep electricity system connected and consumed.
    e_demand = ElectricityDemand(
        name="electricity_demand_chp",
        value_list=[1.0, 1.0, 1.0, 1.0],
        bus=electricity["bus"],
    ).create_demand()

    tech_dc = CHP(
        investment=True,
        name="chp_case",
        investment_component=_inv(
            maximum_capacity=20.0,
            minimum_capacity=0.1,
            cost_per_unit=700.0,
            cost_offset=300.0,
            co2_per_capacity=0.04,
            lifetime=20,
        ),
    )
    tech_bus = tech_dc.get_bus()
    tech_source = tech_dc.create_source()
    tech_converters = tech_dc.create_converters(
        chp_bus=tech_bus,
        gas_bus=hydrogen["bus"],
        electricity_bus=electricity["bus"],
        heat_carrier_bus=heat_bus,
    )
    es.add(tech_bus, tech_source, *tech_converters, heat_demand, e_demand)
    return es, tech_dc, tech_source, tech_converters, heat_bus, hydrogen["bus"]


def _build_pv_case():
    es = _new_es()
    electricity = _add_electricity_infrastructure(es, max_peak_from_grid=0.0, max_peak_into_grid=0.0)

    e_demand = ElectricityDemand(
        name="electricity_demand_pv",
        value_list=[1.0, 1.0, 1.0, 1.0],
        bus=electricity["bus"],
    ).create_demand()

    tech_dc = PVSystem(
        investment=True,
        name="pv_case",
        value_list=np.array([1.0, 1.0, 1.0, 1.0]),
        investment_component=_inv(
            maximum_capacity=20.0,
            minimum_capacity=0.1,
            cost_per_unit=400.0,
            cost_offset=100.0,
            co2_per_capacity=0.01,
            lifetime=20,
        ),
    )
    tech_bus = tech_dc.get_bus()
    tech_source = tech_dc.create_source()
    tech_sink = tech_dc.create_sink()
    connect_buses(input=tech_bus, target=electricity["bus"])
    es.add(tech_bus, tech_source, tech_sink, e_demand)
    return es, electricity, tech_dc, tech_source, tech_sink


def _build_battery_case():
    es = _new_es()
    electricity = _add_electricity_infrastructure(es, max_peak_from_grid=0.0, max_peak_into_grid=50.0)

    # Supply only at first timestep; battery must shift to later demand.
    source = solph.components.Source(
        label="surplus_source",
        outputs={electricity["bus"]: Flow(fix=[1.0, 0.0, 0.0, 0.0], nominal_value=12.0)},
    )
    demand = ElectricityDemand(
        name="electricity_demand_battery",
        value_list=[0.0, 2.5, 2.5, 2.5],
        bus=electricity["bus"],
    ).create_demand()

    tech_dc = Battery(
        investment=True,
        name="battery_case",
        input_bus=electricity["bus"],
        output_bus=electricity["bus"],
        nominal_capacity=1.0,
        balanced=False,
        initial_storage_level=0.0,
        investment_component=_inv(
            maximum_capacity=20.0,
            minimum_capacity=0.1,
            cost_per_unit=250.0,
            cost_offset=100.0,
            co2_per_capacity=0.02,
            lifetime=15,
        ),
    )
    tech_storage = tech_dc.create_storage()
    es.add(source, demand, tech_storage)
    return es, tech_dc, tech_storage


def _build_hot_water_tank_case():
    es = _new_es()
    _add_electricity_infrastructure(es)

    heat_carrier = HeatCarrier(name="heat_carrier_tank", levels=[80])
    heat_bus = heat_carrier.get_bus()
    es.add(*heat_bus.values())

    source = solph.components.Source(
        label="heat_surplus_source",
        outputs={heat_bus[80]: Flow(fix=[1.0, 1.0, 0.0, 0.0], nominal_value=4.0)},
    )
    demand = HeatDemand(
        name="heat_demand_tank",
        value_list=[0.0, 0.0, 3.0, 3.0],
        level=80,
        bus=heat_bus[80],
    ).create_demand()

    tech_dc = HotWaterTank(
        investment=True,
        name="hot_water_tank_case",
        temperature_buses=heat_bus,
        max_temperature=80,
        min_temperature=40,
        input_bus=heat_bus[80],
        output_bus=heat_bus[80],
        volume_in_m3=0.05,
        balanced=False,
        initial_storage_level=0.0,
        investment_component=_inv(
            # For HotWaterTank this is interpreted as volume [m^3] before internal conversion.
            maximum_capacity=0.3,
            minimum_capacity=0.01,
            cost_per_unit=900.0,
            cost_offset=100.0,
            co2_per_capacity=1.0,
            lifetime=25,
        ),
    )
    tech_storage = tech_dc.create_storage()
    es.add(source, demand, tech_storage)
    return es, tech_dc, tech_storage


def _build_heat_grid_case():
    es = _new_es()
    _add_electricity_infrastructure(es)

    tech_dc = HeatGridInvestment(
        name="heat_grid_case",
        heat_transfer_station_max_kW=[(5.0, 1), (4.0, 1)],
        pipe_length_in_meter=50.0,
        peak_load_in_kw=10.0,
        flow_temperature=50,
        total_heat_demand=500.0,
        fictional_demand=4.0,
    )
    tech_dc.value_list = np.array([1.0, 1.0, 1.0, 1.0])
    tech_dc.tsam_total_amount = 4.0
    heat_grid_bus = tech_dc.get_bus()
    source = tech_dc.create_source(heat_grid_bus)
    sink = tech_dc.create_sink(heat_grid_bus)
    es.add(heat_grid_bus, source, sink)
    return es, tech_dc, source, sink


def _assert_stable(value_a, value_b, tol=1e-6):
    assert value_a == pytest.approx(value_b, abs=tol)


_EXPECTED_PATH = Path(__file__).with_name("technology_expected_values.json")


def _load_expected():
    if not _EXPECTED_PATH.exists():
        return {}
    with _EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_expected(data):
    with _EXPECTED_PATH.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)


def _assert_or_update_expected(case_name, solver_name, metrics):
    update = os.getenv("TBM_UPDATE_EXPECTED", "0") == "1"
    data = _load_expected()
    key = f"{case_name}::{solver_name}"
    if update:
        data[key] = {k: float(v) for k, v in metrics.items()}
        _save_expected(data)
        return

    if key not in data:
        pytest.fail(
            f"Missing expected values for '{key}'. "
            f"Run once with TBM_UPDATE_EXPECTED=1 to create {str(_EXPECTED_PATH)}."
        )

    expected = data[key]
    for metric_name, value in metrics.items():
        assert float(value) == pytest.approx(float(expected[metric_name]), abs=1e-6)


def test_gas_heater_investment_and_operation_stable(available_solver, solve_solph_model):
    es, tech_dc, source, converters, heat_bus, gas_bus = _build_gas_heater_case()
    _, results, obj = solve_solph_model(es, available_solver)
    post = tech_dc.post_process(results, source, converters, heat_bus, gas_bus)
    assert math.isfinite(obj)
    assert post["capacity"] > 0
    assert post["investment_cost"] > 0
    assert post["flow_from_converter_sum"] > 0

    es2, tech_dc2, source2, converters2, heat_bus2, gas_bus2 = _build_gas_heater_case()
    _, results2, _ = solve_solph_model(es2, available_solver)
    post2 = tech_dc2.post_process(results2, source2, converters2, heat_bus2, gas_bus2)
    _assert_stable(float(post["investment_cost"]), float(post2["investment_cost"]))
    _assert_or_update_expected(
        "gas_heater",
        available_solver,
        {
            "objective": float(obj),
            "capacity": float(post["capacity"]),
            "investment_cost": float(post["investment_cost"]),
            "flow_from_converter_sum": float(post["flow_from_converter_sum"]),
        },
    )


def test_air_heat_pump_investment_and_operation_stable(available_solver, solve_solph_model):
    es, tech_dc, source, converters, heat_bus, electricity_bus = _build_air_heat_pump_case()
    _, results, obj = solve_solph_model(es, available_solver)
    post = tech_dc.post_process(results, source, converters, heat_bus, electricity_bus)
    assert math.isfinite(obj)
    assert post["capacity"] > 0
    assert post["investment_cost"] > 0
    assert post["flow_from_converter_sum"] > 0

    es2, tech_dc2, source2, converters2, heat_bus2, electricity_bus2 = _build_air_heat_pump_case()
    _, results2, _ = solve_solph_model(es2, available_solver)
    post2 = tech_dc2.post_process(results2, source2, converters2, heat_bus2, electricity_bus2)
    _assert_stable(float(post["investment_cost"]), float(post2["investment_cost"]))
    _assert_or_update_expected(
        "air_heat_pump",
        available_solver,
        {
            "objective": float(obj),
            "capacity": float(post["capacity"]),
            "investment_cost": float(post["investment_cost"]),
            "flow_from_converter_sum": float(post["flow_from_converter_sum"]),
        },
    )


def test_chp_investment_and_operation_stable(available_solver, solve_solph_model):
    es, tech_dc, source, converters, heat_bus, fuel_bus = _build_chp_case()
    _, results, obj = solve_solph_model(es, available_solver)
    post = tech_dc.post_process(results, source, converters, heat_bus, fuel_bus)
    assert math.isfinite(obj)
    assert post["capacity"] > 0
    assert post["investment_cost"] > 0
    assert post["flow_from_converter_sum"] > 0

    es2, tech_dc2, source2, converters2, heat_bus2, fuel_bus2 = _build_chp_case()
    _, results2, _ = solve_solph_model(es2, available_solver)
    post2 = tech_dc2.post_process(results2, source2, converters2, heat_bus2, fuel_bus2)
    _assert_stable(float(post["investment_cost"]), float(post2["investment_cost"]))
    _assert_or_update_expected(
        "chp",
        available_solver,
        {
            "objective": float(obj),
            "capacity": float(post["capacity"]),
            "investment_cost": float(post["investment_cost"]),
            "flow_from_converter_sum": float(post["flow_from_converter_sum"]),
        },
    )


def test_pv_investment_and_operation_stable(available_solver, solve_solph_model):
    es, electricity, tech_dc, source, sink = _build_pv_case()
    _, results, obj = solve_solph_model(es, available_solver)
    post = tech_dc.post_process(results, source, sink)
    grid_post = electricity["grid"].post_process(results, electricity["source"], electricity["sink"])
    assert math.isfinite(obj)
    assert post["capacity"] > 0
    assert post["investment_cost"] > 0
    assert post["sum"] > 0
    flow_from_grid_sum = grid_post["flow_from_grid_sum"]
    if pd.isna(flow_from_grid_sum):
        flow_from_grid_sum = 0.0
    assert float(flow_from_grid_sum) == pytest.approx(0.0, abs=1e-6)

    es2, _, tech_dc2, source2, sink2 = _build_pv_case()
    _, results2, _ = solve_solph_model(es2, available_solver)
    post2 = tech_dc2.post_process(results2, source2, sink2)
    _assert_stable(float(post["investment_cost"]), float(post2["investment_cost"]))
    _assert_or_update_expected(
        "pv",
        available_solver,
        {
            "objective": float(obj),
            "capacity": float(post["capacity"]),
            "investment_cost": float(post["investment_cost"]),
            "sum": float(post["sum"]),
            "grid_import_sum": float(flow_from_grid_sum),
        },
    )


def test_battery_investment_and_operation_stable(available_solver, solve_solph_model):
    es, tech_dc, storage = _build_battery_case()
    _, results, obj = solve_solph_model(es, available_solver)
    post = tech_dc.post_process(results, storage)
    assert math.isfinite(obj)
    assert post["capacity"] > 0
    assert post["investment_cost"] > 0
    assert float(post["flow_into"].sum()) > 0

    es2, tech_dc2, storage2 = _build_battery_case()
    _, results2, _ = solve_solph_model(es2, available_solver)
    post2 = tech_dc2.post_process(results2, storage2)
    _assert_stable(float(post["investment_cost"]), float(post2["investment_cost"]))
    _assert_or_update_expected(
        "battery",
        available_solver,
        {
            "objective": float(obj),
            "capacity": float(post["capacity"]),
            "investment_cost": float(post["investment_cost"]),
            "flow_into_sum": float(post["flow_into"].sum()),
            "flow_co2_sum": float(post["flow_co2"].sum()),
        },
    )


def test_hot_water_tank_investment_and_operation_stable(available_solver, solve_solph_model):
    es, tech_dc, storage = _build_hot_water_tank_case()
    _, results, obj = solve_solph_model(es, available_solver)
    post = tech_dc.post_process(results, storage)
    assert math.isfinite(obj)
    assert post["capacity"] > 0
    assert post["investment_cost"] > 0
    assert float(post["flow_into"].sum()) > 0

    es2, tech_dc2, storage2 = _build_hot_water_tank_case()
    _, results2, _ = solve_solph_model(es2, available_solver)
    post2 = tech_dc2.post_process(results2, storage2)
    _assert_stable(float(post["investment_cost"]), float(post2["investment_cost"]))
    _assert_or_update_expected(
        "hot_water_tank",
        available_solver,
        {
            "objective": float(obj),
            "capacity": float(post["capacity"]),
            "investment_cost": float(post["investment_cost"]),
            "flow_into_sum": float(post["flow_into"].sum()),
            "flow_co2_sum": float(post["flow_co2"].sum()),
        },
    )


def test_heat_grid_investment_and_operation_stable(available_solver, solve_solph_model, sum_node_flow):
    es, tech_dc, source, sink = _build_heat_grid_case()
    _, results, obj = solve_solph_model(es, available_solver)
    post = tech_dc.post_process()
    sink_flow = sum_node_flow(results, sink.label)
    assert math.isfinite(obj)
    assert post["investment_cost"] > 0
    assert post["investment_co2"] > 0
    assert sink_flow > 0

    es2, tech_dc2, source2, _ = _build_heat_grid_case()
    _, _, _ = solve_solph_model(es2, available_solver)
    post2 = tech_dc2.post_process()
    _assert_stable(float(post["investment_cost"]), float(post2["investment_cost"]))
    _assert_or_update_expected(
        "heat_grid",
        available_solver,
        {
            "objective": float(obj),
            "investment_cost": float(post["investment_cost"]),
            "investment_co2": float(post["investment_co2"]),
            "sink_flow_sum": float(sink_flow),
        },
    )
