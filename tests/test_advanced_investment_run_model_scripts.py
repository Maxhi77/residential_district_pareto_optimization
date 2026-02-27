import math
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

solph = pytest.importorskip("oemof.solph")
po = pytest.importorskip("pyomo.environ")

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
            "No MILP solver available (checked: gurobi, cbc, glpk, highs)."
        )
    return solver


def _sum_node_flow(results, node_label):
    sequences = solph.views.node(results, node_label)["sequences"]
    flow_cols = [col for col in sequences.columns if col[1] == "flow"]
    if not flow_cols:
        return 0.0
    return float(sequences[flow_cols].sum().sum())


def _build_decentralized_es(n=4, peak_new=None):
    t1_agg = pd.date_range("2020-01-01", periods=n, freq="h")
    es = solph.EnergySystem(timeindex=t1_agg, infer_last_interval=False)

    # Same generation style as in 07: grid + carrier + connection.
    if peak_new is False or peak_new is None:
        electricity_grid_dataclass = ElectricityGrid()
    else:
        electricity_grid_dataclass = ElectricityGrid(
            max_peak_from_grid=peak_new, max_peak_into_grid=peak_new
        )

    electricity_grid_bus_from_grid = electricity_grid_dataclass.get_bus_from_grid()
    electricity_grid_bus_into_grid = electricity_grid_dataclass.get_bus_into_grid()
    electricity_grid_sink = electricity_grid_dataclass.create_sink()
    electricity_grid_source = electricity_grid_dataclass.create_source()
    electricity_carrier_dataclass = ElectricityCarrier(name="electricity_carrier")
    electricity_carrier_bus = electricity_carrier_dataclass.get_bus()
    connect_buses(
        input=electricity_grid_bus_from_grid,
        target=electricity_carrier_bus,
        output=electricity_grid_bus_into_grid,
    )

    electricity = [
        electricity_grid_bus_from_grid,
        electricity_grid_bus_into_grid,
        electricity_grid_sink,
        electricity_grid_source,
        electricity_carrier_bus,
    ]
    es.add(*electricity)

    natural_gas_grid_dataclass = GasGrid(name="NaturalGas")
    natural_gas_grid_bus_from_grid = natural_gas_grid_dataclass.get_bus_from_grid()
    natural_gas_grid_source = natural_gas_grid_dataclass.create_source()

    bio_gas_grid_dataclass = GasGrid(name="BioGas")
    bio_gas_grid_bus_from_grid = bio_gas_grid_dataclass.get_bus_from_grid()
    bio_gas_grid_source = bio_gas_grid_dataclass.create_source()

    gas_carrier_dataclass = GasCarrier(name="gas_carrier")
    gas_bus = gas_carrier_dataclass.get_bus()
    connect_buses(input=natural_gas_grid_bus_from_grid, target=gas_bus)
    connect_buses(input=bio_gas_grid_bus_from_grid, target=gas_bus)
    es.add(
        natural_gas_grid_bus_from_grid,
        natural_gas_grid_source,
        bio_gas_grid_source,
        bio_gas_grid_bus_from_grid,
        gas_bus,
    )

    hydrogen_grid_dataclass = HydrogenGrid(name="Hydrogen")
    hydrogen_grid_bus_from_grid = hydrogen_grid_dataclass.get_bus_from_grid()
    hydrogen_grid_source = hydrogen_grid_dataclass.create_source()
    hydrogen_carrier_dataclass = HydrogenCarrier(name="hydrogen_carrier")
    hydrogen_bus = hydrogen_carrier_dataclass.get_bus()
    connect_buses(input=hydrogen_grid_bus_from_grid, target=hydrogen_bus)
    es.add(hydrogen_grid_bus_from_grid, hydrogen_grid_source, hydrogen_bus)

    building_ids = ["b1", "b2"]
    for bid in building_ids:
        b_e = ElectricityCarrier(name=f"e_carrier_{bid}").get_bus()
        b_g = GasCarrier(name=f"g_carrier_{bid}").get_bus()
        b_h2 = HydrogenCarrier(name=f"h2_carrier_{bid}").get_bus()
        h_carrier = HeatCarrier(name=f"h_carrier_{bid}", levels=[40, 50, 80])
        h_carrier.connect_buses_decreasing_levels()
        b_h = h_carrier.get_bus()

        conv_e_into = solph.components.Converter(
            label=f"conv_e_into_grid_{bid}",
            inputs={b_e: solph.flows.Flow()},
            outputs={electricity_carrier_bus: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={electricity_carrier_bus: 1},
        )
        conv_e_from = solph.components.Converter(
            label=f"conv_e_from_grid_{bid}",
            inputs={electricity_carrier_bus: solph.flows.Flow()},
            outputs={b_e: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={b_e: 1},
        )

        conv_g_into = solph.components.Converter(
            label=f"conv_g_into_grid_{bid}",
            inputs={b_g: solph.flows.Flow()},
            outputs={gas_bus: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={gas_bus: 1},
        )
        conv_g_from = solph.components.Converter(
            label=f"conv_g_from_grid_{bid}",
            inputs={gas_bus: solph.flows.Flow()},
            outputs={b_g: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={b_g: 1},
        )

        conv_h2_into = solph.components.Converter(
            label=f"conv_hydrogen_into_grid_{bid}",
            inputs={b_h2: solph.flows.Flow()},
            outputs={hydrogen_bus: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={hydrogen_bus: 1},
        )
        conv_h2_from = solph.components.Converter(
            label=f"conv_hydrogen_from_grid_{bid}",
            inputs={hydrogen_bus: solph.flows.Flow()},
            outputs={b_h2: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={b_h2: 1},
        )

        e_demand = ElectricityDemand(
            name=f"e_demand_{bid}",
            value_list=np.array([4000.0, 3500.0, 3000.0, 3200.0]),
            bus=b_e,
        ).create_demand()

        ww_demand = WarmWater(
            name=f"ww_demand_{bid}",
            value_list=np.array([40.0, 35.0, 30.0, 25.0]),
            level=50,
            bus=b_h[50],
        ).create_demand()

        building_heat_demand = HeatDemand(
            name=f"building_{bid}",
            value_list=np.array([3.0, 3.0, 3.0, 3.0]),
            level=50,
            bus=b_h[50],
        ).create_demand()

        pv = PVSystem(
            investment=False,
            name=f"pv_system_{bid}",
            nominal_power=1.0,
            value_list=np.array([0.1, 0.2, 0.2, 0.1]),
        )
        pv_bus = pv.get_bus()
        pv_source = pv.create_source()
        pv_sink = pv.create_sink()
        connect_buses(input=pv_bus, target=b_e)

        battery = Battery(
            investment=False,
            name=f"battery_{bid}",
            input_bus=b_e,
            output_bus=b_e,
            nominal_capacity=4.0,
            balanced=False,
            initial_storage_level=0.5,
        ).create_storage()

        hot_water_tank = HotWaterTank(
            investment=False,
            name=f"heat_storage_{bid}",
            temperature_buses=b_h,
            max_temperature=80,
            min_temperature=40,
            input_bus=b_h[80],
            output_bus=b_h[80],
            volume_in_m3=0.05,
        ).create_storage()

        gas_heater_dc = GasHeater(
            investment=False, name=f"gas_heater_{bid}", nominal_power=20.0
        )
        gas_heater_bus = gas_heater_dc.get_bus()
        gas_heater_source = gas_heater_dc.create_source()
        gas_heater_converters = gas_heater_dc.create_converters(
            gas_heater_bus=gas_heater_bus, gas_bus=b_g, heat_carrier_bus=b_h
        )

        hp_dc = AirHeatPump(
            investment=False,
            name=f"hp_{bid}",
            nominal_power=0.2,
            air_temperature=np.array([5.0] * n),
        )
        hp_bus = hp_dc.get_bus()
        hp_source = hp_dc.create_source()
        hp_converters = hp_dc.create_converters(
            heat_pump_bus=hp_bus, electricity_bus=b_e, heat_carrier_bus=b_h
        )

        chp_dc = CHP(investment=False, name=f"chp_{bid}", nominal_power=0.2)
        chp_bus = chp_dc.get_bus()
        chp_source = chp_dc.create_source()
        chp_converters = chp_dc.create_converters(
            chp_bus=chp_bus, gas_bus=b_h2, electricity_bus=b_e, heat_carrier_bus=b_h
        )

        es.add(
            b_e,
            b_g,
            b_h2,
            *b_h.values(),
            conv_e_into,
            conv_e_from,
            conv_g_into,
            conv_g_from,
            conv_h2_into,
            conv_h2_from,
            e_demand,
            ww_demand,
            building_heat_demand,
            pv_bus,
            pv_source,
            pv_sink,
            battery,
            hot_water_tank,
            gas_heater_bus,
            gas_heater_source,
            *gas_heater_converters,
            hp_bus,
            hp_source,
            *hp_converters,
            chp_bus,
            chp_source,
            *chp_converters,
        )

    return es


def _build_centralized_es(n=4, peak_new=None):
    t1_agg = pd.date_range("2020-01-01", periods=n, freq="h")
    es = solph.EnergySystem(timeindex=t1_agg, infer_last_interval=False)

    if peak_new is False or peak_new is None:
        electricity_grid_dataclass = ElectricityGrid()
    else:
        electricity_grid_dataclass = ElectricityGrid(
            max_peak_from_grid=peak_new, max_peak_into_grid=peak_new
        )

    electricity_grid_bus_from_grid = electricity_grid_dataclass.get_bus_from_grid()
    electricity_grid_bus_into_grid = electricity_grid_dataclass.get_bus_into_grid()
    electricity_grid_sink = electricity_grid_dataclass.create_sink()
    electricity_grid_source = electricity_grid_dataclass.create_source()
    electricity_carrier_dataclass = ElectricityCarrier(name="electricity_carrier")
    electricity_carrier_bus = electricity_carrier_dataclass.get_bus()
    connect_buses(
        input=electricity_grid_bus_from_grid,
        target=electricity_carrier_bus,
        output=electricity_grid_bus_into_grid,
    )
    es.add(
        electricity_grid_bus_from_grid,
        electricity_grid_bus_into_grid,
        electricity_grid_sink,
        electricity_grid_source,
        electricity_carrier_bus,
    )

    natural_gas_grid_dataclass = GasGrid(name="NaturalGas")
    natural_gas_grid_bus_from_grid = natural_gas_grid_dataclass.get_bus_from_grid()
    natural_gas_grid_source = natural_gas_grid_dataclass.create_source()

    bio_gas_grid_dataclass = GasGrid(name="BioGas")
    bio_gas_grid_bus_from_grid = bio_gas_grid_dataclass.get_bus_from_grid()
    bio_gas_grid_source = bio_gas_grid_dataclass.create_source()

    gas_carrier_dataclass = GasCarrier(name="gas_carrier")
    gas_bus = gas_carrier_dataclass.get_bus()
    connect_buses(input=natural_gas_grid_bus_from_grid, target=gas_bus)
    connect_buses(input=bio_gas_grid_bus_from_grid, target=gas_bus)
    es.add(
        natural_gas_grid_bus_from_grid,
        natural_gas_grid_source,
        bio_gas_grid_bus_from_grid,
        bio_gas_grid_source,
        gas_bus,
    )

    hydrogen_grid_dataclass = HydrogenGrid(name="Hydrogen")
    hydrogen_grid_bus_from_grid = hydrogen_grid_dataclass.get_bus_from_grid()
    hydrogen_grid_source = hydrogen_grid_dataclass.create_source()
    hydrogen_carrier_dataclass = HydrogenCarrier(name="hydrogen_carrier")
    hydrogen_bus = hydrogen_carrier_dataclass.get_bus()
    connect_buses(input=hydrogen_grid_bus_from_grid, target=hydrogen_bus)
    es.add(hydrogen_grid_bus_from_grid, hydrogen_grid_source, hydrogen_bus)

    heat_grid_temperature = 50
    central_heat_carrier = HeatCarrier(
        name="h_carrier_heat_grid", levels=[40, 50, 80]
    )
    central_heat_carrier.connect_buses_decreasing_levels()
    b_h_central = central_heat_carrier.get_bus()
    es.add(*b_h_central.values())

    heat_grid_investment = HeatGridInvestment(
        name="heat_grid_investment",
        heat_transfer_station_max_kW=[(5.0, 2)],
        pipe_length_in_meter=100,
        peak_load_in_kw=10,
        flow_temperature=heat_grid_temperature,
        total_heat_demand=500,
        fictional_demand=4,
    )
    heat_grid_investment.tsam_total_amount = 4
    heat_grid_investment.value_list = np.array([1.0, 1.0, 1.0, 1.0])
    heat_grid_bus = heat_grid_investment.get_bus()
    heat_grid_source = heat_grid_investment.create_source(heat_grid_bus)
    heat_grid_sink = heat_grid_investment.create_sink(heat_grid_bus)
    es.add(heat_grid_bus, heat_grid_source, heat_grid_sink)

    gas_heater_dc = GasHeater(
        investment=False, name="gas_heater_heat_grid_1", nominal_power=30.0
    )
    gas_heater_bus = gas_heater_dc.get_bus()
    gas_heater_source = gas_heater_dc.create_source()
    gas_heater_converters = gas_heater_dc.create_converters(
        gas_heater_bus=gas_heater_bus, gas_bus=gas_bus, heat_carrier_bus=b_h_central
    )
    es.add(gas_heater_bus, gas_heater_source, *gas_heater_converters)

    hp_dc = AirHeatPump(
        investment=False,
        name="hp_heat_grid_1",
        nominal_power=0.2,
        air_temperature=np.array([5.0] * n),
    )
    hp_bus = hp_dc.get_bus()
    hp_source = hp_dc.create_source()
    hp_converters = hp_dc.create_converters(
        heat_pump_bus=hp_bus,
        electricity_bus=electricity_carrier_bus,
        heat_carrier_bus=b_h_central,
    )
    es.add(hp_bus, hp_source, *hp_converters)

    chp_dc = CHP(investment=False, name="chp_heat_grid_1", nominal_power=0.2)
    chp_bus = chp_dc.get_bus()
    chp_source = chp_dc.create_source()
    chp_converters = chp_dc.create_converters(
        chp_bus=chp_bus,
        gas_bus=hydrogen_bus,
        electricity_bus=electricity_carrier_bus,
        heat_carrier_bus=b_h_central,
    )
    es.add(chp_bus, chp_source, *chp_converters)

    battery = Battery(
        investment=False,
        name="battery_heat_grid_1",
        input_bus=electricity_carrier_bus,
        output_bus=electricity_carrier_bus,
        nominal_capacity=5.0,
        balanced=False,
        initial_storage_level=0.5,
    ).create_storage()
    es.add(battery)

    hot_water_tank = HotWaterTank(
        investment=False,
        name="heat_storage_heat_grid_1",
        temperature_buses=b_h_central,
        max_temperature=80,
        min_temperature=40,
        input_bus=b_h_central[80],
        output_bus=b_h_central[80],
        volume_in_m3=0.05,
    ).create_storage()
    es.add(hot_water_tank)

    for bid in ["b1", "b2"]:
        b_h_local = HeatCarrier(name=f"h_carrier_{bid}", levels=[50]).get_bus()
        b_e_local = ElectricityCarrier(name=f"e_carrier_{bid}").get_bus()
        es.add(*b_h_local.values(), b_e_local)

        conv_h_from_grid_50 = solph.components.Converter(
            label=f"conv_h_from_grid_50_{bid}",
            inputs={b_h_central[50]: solph.flows.Flow()},
            outputs={b_h_local[50]: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={b_h_local[50]: 1},
        )
        conv_h_from_grid_heatdemand = solph.components.Converter(
            label=f"conv_h_from_grid_heatdemand_{bid}",
            inputs={b_h_central[heat_grid_temperature]: solph.flows.Flow()},
            outputs={b_h_local[50]: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={b_h_local[50]: 1},
        )
        conv_e_into = solph.components.Converter(
            label=f"conv_e_into_grid_{bid}",
            inputs={b_e_local: solph.flows.Flow()},
            outputs={electricity_carrier_bus: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={electricity_carrier_bus: 1},
        )
        conv_e_from = solph.components.Converter(
            label=f"conv_e_from_grid_{bid}",
            inputs={electricity_carrier_bus: solph.flows.Flow()},
            outputs={b_e_local: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={b_e_local: 1},
        )

        e_demand = ElectricityDemand(
            name=f"e_demand_{bid}",
            value_list=np.array([3500.0, 3000.0, 2800.0, 3200.0]),
            bus=b_e_local,
        ).create_demand()
        ww_demand = WarmWater(
            name=f"ww_demand_{bid}",
            value_list=np.array([35.0, 30.0, 25.0, 20.0]),
            level=50,
            bus=b_h_local[50],
        ).create_demand()
        building_heat_demand = HeatDemand(
            name=f"building_{bid}",
            value_list=np.array([2.5, 2.5, 2.5, 2.5]),
            level=50,
            bus=b_h_local[50],
        ).create_demand()

        pv = PVSystem(
            investment=False,
            name=f"pv_system_{bid}",
            nominal_power=1.0,
            value_list=np.array([0.1, 0.2, 0.2, 0.1]),
        )
        pv_bus = pv.get_bus()
        pv_source = pv.create_source()
        pv_sink = pv.create_sink()
        connect_buses(input=pv_bus, target=b_e_local)

        es.add(
            conv_h_from_grid_50,
            conv_h_from_grid_heatdemand,
            conv_e_into,
            conv_e_from,
            e_demand,
            ww_demand,
            building_heat_demand,
            pv_bus,
            pv_source,
            pv_sink,
        )

    return es


def _solve_objective_and_results(es, solver):
    model = solph.Model(es)
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
    meta = solph.processing.meta_results(model)
    results = solph.processing.results(model)
    return float(meta["objective"]), results


_EXPECTED_PATH = Path(__file__).with_name("advanced_investment_expected_values.json")


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


def test_decentralized_facade_toy_system_solves(available_solver):
    es = _build_decentralized_es(n=4)
    objective, results = _solve_objective_and_results(es, available_solver)
    assert math.isfinite(objective)

    labels = {node.label for node in es.nodes}
    assert "gas_heater_b1_source" in labels
    assert "gas_heater_b2_source" in labels
    assert "hp_b1_source" in labels
    assert "chp_b1_source" in labels
    assert "battery_b1" in labels
    assert "heat_storage_b1" in labels
    assert "pv_system_b1_source" in labels

    assert _sum_node_flow(results, "conv_e_from_grid_b1") > 0
    assert _sum_node_flow(results, "conv_e_from_grid_b2") > 0

    es_repeat = _build_decentralized_es(n=4)
    objective_repeat, _ = _solve_objective_and_results(es_repeat, available_solver)
    assert objective == pytest.approx(objective_repeat, abs=1e-6)


def test_centralized_facade_toy_system_solves(available_solver):
    es = _build_centralized_es(n=4)
    objective, results = _solve_objective_and_results(es, available_solver)
    assert math.isfinite(objective)

    labels = {node.label for node in es.nodes}
    assert "gas_heater_heat_grid_1_source" in labels
    assert "hp_heat_grid_1_source" in labels
    assert "chp_heat_grid_1_source" in labels
    assert "heat_grid_investment_source" in labels
    assert "conv_h_from_grid_50_b1" in labels
    assert "conv_h_from_grid_50_b2" in labels
    assert "gas_heater_b1_source" not in labels

    conv_h_from_grid_50_b1_sum = _sum_node_flow(results, "conv_h_from_grid_50_b1")
    conv_h_from_grid_50_b2_sum = _sum_node_flow(results, "conv_h_from_grid_50_b2")
    heat_grid_sink_sum = _sum_node_flow(results, "heat_grid_investment_sink")
    heat_grid_source_sum = _sum_node_flow(results, "heat_grid_investment_source")
    assert conv_h_from_grid_50_b1_sum > 0
    assert conv_h_from_grid_50_b2_sum > 0
    assert heat_grid_sink_sum > 0
    assert heat_grid_source_sum > 0

    es_repeat = _build_centralized_es(n=4)
    objective_repeat, _ = _solve_objective_and_results(es_repeat, available_solver)
    assert objective == pytest.approx(objective_repeat, abs=1e-6)
    _assert_or_update_expected(
        "centralized_facade_toy_system",
        available_solver,
        {
            "objective": float(objective),
            "conv_h_from_grid_50_b1_sum": float(conv_h_from_grid_50_b1_sum),
            "conv_h_from_grid_50_b2_sum": float(conv_h_from_grid_50_b2_sum),
            "heat_grid_sink_sum": float(heat_grid_sink_sum),
            "heat_grid_source_sum": float(heat_grid_source_sum),
        },
    )
