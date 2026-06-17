"""Reusable scenario assembly blocks for advanced investment toy examples.

This module intentionally contains explicit orchestration helpers so users can
compose scenarios step-by-step:
- add grids/carriers
- add local building carriers and demands
- add technologies
- add centralized heat-grid structures
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

import numpy as np
from oemof import solph

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


def add_electricity_grid_block(
    es: solph.EnergySystem,
    peak_limit_kw: Optional[float] = None,
    carrier_name: str = "electricity_carrier",
) -> Dict[str, Any]:
    if peak_limit_kw is None:
        grid = ElectricityGrid()
    else:
        grid = ElectricityGrid(
            max_peak_from_grid=peak_limit_kw,
            max_peak_into_grid=peak_limit_kw,
        )
    bus_from = grid.get_bus_from_grid()
    bus_into = grid.get_bus_into_grid()
    source = grid.create_source()
    sink = grid.create_sink()
    carrier = ElectricityCarrier(name=carrier_name)
    carrier_bus = carrier.get_bus()
    connect_buses(input=bus_from, target=carrier_bus, output=bus_into)
    es.add(bus_from, bus_into, source, sink, carrier_bus)
    return {
        "grid": grid,
        "bus_from_grid": bus_from,
        "bus_into_grid": bus_into,
        "source": source,
        "sink": sink,
        "carrier_bus": carrier_bus,
    }


def add_gas_grids_block(
    es: solph.EnergySystem,
    natural_gas_name: str = "NaturalGas",
    bio_gas_name: str = "BioGas",
    carrier_name: str = "gas_carrier",
) -> Dict[str, Any]:
    natural_gas_grid = GasGrid(name=natural_gas_name)
    ng_bus_from = natural_gas_grid.get_bus_from_grid()
    ng_source = natural_gas_grid.create_source()

    bio_gas_grid = GasGrid(name=bio_gas_name)
    bg_bus_from = bio_gas_grid.get_bus_from_grid()
    bg_source = bio_gas_grid.create_source()

    carrier = GasCarrier(name=carrier_name)
    carrier_bus = carrier.get_bus()
    connect_buses(input=ng_bus_from, target=carrier_bus)
    connect_buses(input=bg_bus_from, target=carrier_bus)
    es.add(ng_bus_from, ng_source, bg_bus_from, bg_source, carrier_bus)
    return {
        "natural_gas_grid": natural_gas_grid,
        "natural_gas_source": ng_source,
        "bio_gas_grid": bio_gas_grid,
        "bio_gas_source": bg_source,
        "carrier_bus": carrier_bus,
    }


def add_hydrogen_grid_block(
    es: solph.EnergySystem,
    grid_name: str = "Hydrogen",
    carrier_name: str = "hydrogen_carrier",
) -> Dict[str, Any]:
    grid = HydrogenGrid(name=grid_name)
    bus_from = grid.get_bus_from_grid()
    source = grid.create_source()
    carrier = HydrogenCarrier(name=carrier_name)
    carrier_bus = carrier.get_bus()
    connect_buses(input=bus_from, target=carrier_bus)
    es.add(bus_from, source, carrier_bus)
    return {
        "grid": grid,
        "bus_from_grid": bus_from,
        "source": source,
        "carrier_bus": carrier_bus,
    }


def add_main_grids_and_carriers_block(
    es: solph.EnergySystem,
    peak_limit_kw: Optional[float] = None,
    include_hydrogen: bool = True,
) -> Dict[str, Any]:
    electricity = add_electricity_grid_block(es, peak_limit_kw=peak_limit_kw)
    gas = add_gas_grids_block(es)
    context = {
        "electricity_grid": electricity["grid"],
        "electricity_source": electricity["source"],
        "electricity_sink": electricity["sink"],
        "electricity_bus": electricity["carrier_bus"],
        "natural_gas_grid": gas["natural_gas_grid"],
        "natural_gas_source": gas["natural_gas_source"],
        "bio_gas_grid": gas["bio_gas_grid"],
        "bio_gas_source": gas["bio_gas_source"],
        "gas_bus": gas["carrier_bus"],
    }
    if include_hydrogen:
        hydrogen = add_hydrogen_grid_block(es)
        context.update(
            {
                "hydrogen_grid": hydrogen["grid"],
                "hydrogen_source": hydrogen["source"],
                "hydrogen_bus": hydrogen["carrier_bus"],
            }
        )
    return context


def add_local_building_carriers_block(
    es: solph.EnergySystem,
    building_id: str,
    shared_electricity_bus: solph.buses.Bus,
    shared_gas_bus: solph.buses.Bus,
    shared_hydrogen_bus: Optional[solph.buses.Bus],
    heat_levels: Iterable[int],
) -> Dict[str, Any]:
    local_e_bus = ElectricityCarrier(name=f"e_carrier_{building_id}").get_bus()
    local_g_bus = GasCarrier(name=f"g_carrier_{building_id}").get_bus()
    heat_carrier = HeatCarrier(name=f"h_carrier_{building_id}", levels=list(heat_levels))
    heat_carrier.connect_buses_decreasing_levels()
    local_heat_buses = heat_carrier.get_bus()

    conv_e_into = solph.components.Converter(
        label=f"conv_e_into_grid_{building_id}",
        inputs={local_e_bus: solph.flows.Flow()},
        outputs={shared_electricity_bus: solph.flows.Flow(variable_costs=1e-6)},
        conversion_factors={shared_electricity_bus: 1.0},
    )
    conv_e_from = solph.components.Converter(
        label=f"conv_e_from_grid_{building_id}",
        inputs={shared_electricity_bus: solph.flows.Flow()},
        outputs={local_e_bus: solph.flows.Flow(variable_costs=1e-6)},
        conversion_factors={local_e_bus: 1.0},
    )
    conv_g_into = solph.components.Converter(
        label=f"conv_g_into_grid_{building_id}",
        inputs={local_g_bus: solph.flows.Flow()},
        outputs={shared_gas_bus: solph.flows.Flow(variable_costs=1e-6)},
        conversion_factors={shared_gas_bus: 1.0},
    )
    conv_g_from = solph.components.Converter(
        label=f"conv_g_from_grid_{building_id}",
        inputs={shared_gas_bus: solph.flows.Flow()},
        outputs={local_g_bus: solph.flows.Flow(variable_costs=1e-6)},
        conversion_factors={local_g_bus: 1.0},
    )

    components = [
        local_e_bus,
        local_g_bus,
        *local_heat_buses.values(),
        conv_e_into,
        conv_e_from,
        conv_g_into,
        conv_g_from,
    ]

    local_h2_bus = None
    conv_h2_into = None
    conv_h2_from = None
    if shared_hydrogen_bus is not None:
        local_h2_bus = HydrogenCarrier(name=f"h2_carrier_{building_id}").get_bus()
        conv_h2_into = solph.components.Converter(
            label=f"conv_hydrogen_into_grid_{building_id}",
            inputs={local_h2_bus: solph.flows.Flow()},
            outputs={shared_hydrogen_bus: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={shared_hydrogen_bus: 1.0},
        )
        conv_h2_from = solph.components.Converter(
            label=f"conv_hydrogen_from_grid_{building_id}",
            inputs={shared_hydrogen_bus: solph.flows.Flow()},
            outputs={local_h2_bus: solph.flows.Flow(variable_costs=1e-6)},
            conversion_factors={local_h2_bus: 1.0},
        )
        components.extend([local_h2_bus, conv_h2_into, conv_h2_from])

    es.add(*components)
    return {
        "electricity_bus": local_e_bus,
        "gas_bus": local_g_bus,
        "hydrogen_bus": local_h2_bus,
        "heat_buses": local_heat_buses,
    }


def add_local_demands_block(
    es: solph.EnergySystem,
    building_id: str,
    local_electricity_bus: solph.buses.Bus,
    local_heat_buses: Dict[int, solph.buses.Bus],
    electricity_profile: np.ndarray,
    warm_water_profile: np.ndarray,
    warm_water_level: int,
    space_heating_profile: np.ndarray,
    space_heating_level: int,
) -> Dict[str, Any]:
    e_demand = ElectricityDemand(
        name=f"e_demand_{building_id}",
        value_list=electricity_profile,
        bus=local_electricity_bus,
    ).create_demand()
    ww_demand = WarmWater(
        name=f"ww_demand_{building_id}",
        value_list=warm_water_profile,
        level=warm_water_level,
        bus=local_heat_buses[warm_water_level],
    ).create_demand()
    space_demand = HeatDemand(
        name=f"building_{building_id}",
        value_list=space_heating_profile,
        level=space_heating_level,
        bus=local_heat_buses[space_heating_level],
    ).create_demand()
    es.add(e_demand, ww_demand, space_demand)
    return {
        "electricity_demand": e_demand,
        "warm_water_demand": ww_demand,
        "space_heating_demand": space_demand,
    }


def _ensure_investment_component(
    investment: bool,
    investment_component: Any,
    technology_name: str,
) -> None:
    if investment and investment_component is None:
        raise ValueError(
            f"investment_component is required for {technology_name} when investment=True."
        )


def add_pv_system(
    es: solph.EnergySystem,
    name: str,
    output_bus: solph.buses.Bus,
    value_list: np.ndarray,
    investment: bool = False,
    nominal_power: float = 1.0,
    investment_component: Any = None,
    allow_curtailment: bool = True,
) -> Dict[str, Any]:
    _ensure_investment_component(investment, investment_component, "PVSystem")
    kwargs: Dict[str, Any] = {"name": name, "value_list": value_list, "investment": investment}
    if investment:
        kwargs["investment_component"] = investment_component
        kwargs["nominal_power"] = False
    else:
        kwargs["nominal_power"] = nominal_power
    pv_dc = PVSystem(**kwargs)
    pv_bus = pv_dc.get_bus()
    pv_source = pv_dc.create_source()
    pv_sink = None
    if allow_curtailment:
        pv_sink = pv_dc.create_sink()
    connect_buses(input=pv_bus, target=output_bus)
    if pv_sink is None:
        es.add(pv_bus, pv_source)
    else:
        es.add(pv_bus, pv_source, pv_sink)
    return {"dc": pv_dc, "source": pv_source, "sink": pv_sink}


def add_battery(
    es: solph.EnergySystem,
    name: str,
    electricity_bus: solph.buses.Bus,
    investment: bool = False,
    nominal_capacity: float = 4.0,
    investment_component: Any = None,
) -> Dict[str, Any]:
    _ensure_investment_component(investment, investment_component, "Battery")
    kwargs: Dict[str, Any] = {
        "name": name,
        "investment": investment,
        "input_bus": electricity_bus,
        "output_bus": electricity_bus,
        "balanced": False,
        "initial_storage_level": 0.5,
    }
    if investment:
        kwargs["investment_component"] = investment_component
        kwargs["nominal_capacity"] = False
    else:
        kwargs["nominal_capacity"] = nominal_capacity
    battery_dc = Battery(**kwargs)
    battery = battery_dc.create_storage()
    es.add(battery)
    return {"dc": battery_dc, "storage": battery}


def add_hot_water_tank(
    es: solph.EnergySystem,
    name: str,
    heat_buses: Dict[int, solph.buses.Bus],
    heat_levels: Iterable[int],
    investment: bool = False,
    volume_in_m3: float = 0.05,
    investment_component: Any = None,
) -> Dict[str, Any]:
    _ensure_investment_component(investment, investment_component, "HotWaterTank")
    levels = list(heat_levels)
    kwargs: Dict[str, Any] = {
        "name": name,
        "investment": investment,
        "temperature_buses": heat_buses,
        "max_temperature": max(levels),
        "min_temperature": min(levels),
        "input_bus": heat_buses[max(levels)],
        "output_bus": heat_buses[max(levels)],
    }
    if investment:
        kwargs["investment_component"] = investment_component
        kwargs["volume_in_m3"] = False
    else:
        kwargs["volume_in_m3"] = volume_in_m3
    tank_dc = HotWaterTank(**kwargs)
    tank = tank_dc.create_storage()
    es.add(tank)
    return {"dc": tank_dc, "storage": tank}


def add_gas_heater(
    es: solph.EnergySystem,
    name: str,
    gas_bus: solph.buses.Bus,
    heat_carrier_bus: Dict[int, solph.buses.Bus],
    investment: bool = False,
    nominal_power: float = 20.0,
    investment_component: Any = None,
) -> Dict[str, Any]:
    _ensure_investment_component(investment, investment_component, "GasHeater")
    kwargs: Dict[str, Any] = {"name": name, "investment": investment}
    if investment:
        kwargs["investment_component"] = investment_component
        kwargs["nominal_power"] = False
    else:
        kwargs["nominal_power"] = nominal_power
    dc = GasHeater(**kwargs)
    tech_bus = dc.get_bus()
    source = dc.create_source()
    converters = dc.create_converters(
        gas_heater_bus=tech_bus,
        gas_bus=gas_bus,
        heat_carrier_bus=heat_carrier_bus,
    )
    es.add(tech_bus, source, *converters)
    return {"dc": dc, "source": source, "converters": converters}


def add_heat_pump(
    es: solph.EnergySystem,
    name: str,
    electricity_bus: solph.buses.Bus,
    heat_carrier_bus: Dict[int, solph.buses.Bus],
    air_temperature: np.ndarray,
    investment: bool = False,
    nominal_power: float = 0.2,
    investment_component: Any = None,
) -> Dict[str, Any]:
    _ensure_investment_component(investment, investment_component, "AirHeatPump")
    kwargs: Dict[str, Any] = {
        "name": name,
        "investment": investment,
        "air_temperature": air_temperature,
    }
    if investment:
        kwargs["investment_component"] = investment_component
        kwargs["nominal_power"] = False
    else:
        kwargs["nominal_power"] = nominal_power
    dc = AirHeatPump(**kwargs)
    tech_bus = dc.get_bus()
    source = dc.create_source()
    converters = dc.create_converters(
        heat_pump_bus=tech_bus,
        electricity_bus=electricity_bus,
        heat_carrier_bus=heat_carrier_bus,
    )
    es.add(tech_bus, source, *converters)
    return {"dc": dc, "source": source, "converters": converters}


def add_chp(
    es: solph.EnergySystem,
    name: str,
    gas_bus: solph.buses.Bus,
    electricity_bus: solph.buses.Bus,
    heat_carrier_bus: Dict[int, solph.buses.Bus],
    investment: bool = False,
    nominal_power: float = 0.2,
    investment_component: Any = None,
) -> Dict[str, Any]:
    _ensure_investment_component(investment, investment_component, "CHP")
    kwargs: Dict[str, Any] = {"name": name, "investment": investment}
    if investment:
        kwargs["investment_component"] = investment_component
        kwargs["nominal_power"] = False
    else:
        kwargs["nominal_power"] = nominal_power
    dc = CHP(**kwargs)
    tech_bus = dc.get_bus()
    source = dc.create_source()
    converters = dc.create_converters(
        chp_bus=tech_bus,
        gas_bus=gas_bus,
        electricity_bus=electricity_bus,
        heat_carrier_bus=heat_carrier_bus,
    )
    es.add(tech_bus, source, *converters)
    return {"dc": dc, "source": source, "converters": converters}


def add_local_pv_block(
    es: solph.EnergySystem,
    building_id: str,
    local_electricity_bus: solph.buses.Bus,
    pv_profile: np.ndarray,
    nominal_power: float = 1.0,
    allow_curtailment: bool = True,
) -> Dict[str, Any]:
    return add_pv_system(
        es=es,
        name=f"pv_system_{building_id}",
        output_bus=local_electricity_bus,
        value_list=pv_profile,
        investment=False,
        nominal_power=nominal_power,
        allow_curtailment=allow_curtailment,
    )


def add_local_storage_blocks(
    es: solph.EnergySystem,
    building_id: str,
    local_electricity_bus: solph.buses.Bus,
    local_heat_buses: Dict[int, solph.buses.Bus],
    heat_levels: Iterable[int],
    enable_battery: bool = True,
    enable_hot_water_tank: bool = True,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if enable_battery:
        out["battery"] = add_battery(
            es=es,
            name=f"battery_{building_id}",
            electricity_bus=local_electricity_bus,
            investment=False,
            nominal_capacity=4.0,
        )
    if enable_hot_water_tank:
        out["hot_water_tank"] = add_hot_water_tank(
            es=es,
            name=f"heat_storage_{building_id}",
            heat_buses=local_heat_buses,
            heat_levels=heat_levels,
            investment=False,
            volume_in_m3=0.05,
        )
    return out


def add_local_conversion_technologies_block(
    es: solph.EnergySystem,
    building_id: str,
    local_heat_buses: Dict[int, solph.buses.Bus],
    local_electricity_bus: solph.buses.Bus,
    local_gas_bus: solph.buses.Bus,
    local_hydrogen_bus: Optional[solph.buses.Bus],
    air_temperature_profile: np.ndarray,
    enable_gas_heater: bool = True,
    enable_air_heat_pump: bool = True,
    enable_chp: bool = True,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if enable_gas_heater:
        out["gas_heater"] = add_gas_heater(
            es=es,
            name=f"gas_heater_{building_id}",
            gas_bus=local_gas_bus,
            heat_carrier_bus=local_heat_buses,
            investment=False,
            nominal_power=20.0,
        )
    if enable_air_heat_pump:
        out["air_heat_pump"] = add_heat_pump(
            es=es,
            name=f"hp_{building_id}",
            electricity_bus=local_electricity_bus,
            heat_carrier_bus=local_heat_buses,
            air_temperature=air_temperature_profile,
            investment=False,
            nominal_power=0.2,
        )
    if enable_chp and local_hydrogen_bus is not None:
        out["chp"] = add_chp(
            es=es,
            name=f"chp_{building_id}",
            gas_bus=local_hydrogen_bus,
            electricity_bus=local_electricity_bus,
            heat_carrier_bus=local_heat_buses,
            investment=False,
            nominal_power=0.2,
        )
    return out


def add_central_heat_carrier_block(
    es: solph.EnergySystem,
    name: str = "h_carrier_heat_grid",
    levels: Iterable[int] = (40, 50, 80),
) -> Dict[str, Any]:
    heat_carrier = HeatCarrier(name=name, levels=list(levels))
    heat_carrier.connect_buses_decreasing_levels()
    heat_buses = heat_carrier.get_bus()
    es.add(*heat_buses.values())
    return {"dc": heat_carrier, "buses": heat_buses}


def add_heat_grid_investment_block(
    es: solph.EnergySystem,
    name: str,
    heat_transfer_station_max_kw: list[tuple[float, int]],
    pipe_length_m: float,
    peak_load_kw: float,
    flow_temperature: int,
    total_heat_demand: float,
    fictional_profile: np.ndarray,
) -> Dict[str, Any]:
    heat_grid = HeatGridInvestment(
        name=name,
        heat_transfer_station_max_kW=heat_transfer_station_max_kw,
        pipe_length_in_meter=pipe_length_m,
        peak_load_in_kw=peak_load_kw,
        flow_temperature=flow_temperature,
        total_heat_demand=total_heat_demand,
        fictional_demand=float(np.sum(fictional_profile)),
    )
    heat_grid.tsam_total_amount = float(np.sum(fictional_profile))
    heat_grid.value_list = fictional_profile
    bus = heat_grid.get_bus()
    source = heat_grid.create_source(bus)
    sink = heat_grid.create_sink(bus)
    es.add(bus, source, sink)
    return {"dc": heat_grid, "bus": bus, "source": source, "sink": sink}


def add_central_supply_technologies_block(
    es: solph.EnergySystem,
    central_heat_buses: Dict[int, solph.buses.Bus],
    shared_electricity_bus: solph.buses.Bus,
    shared_gas_bus: solph.buses.Bus,
    shared_hydrogen_bus: solph.buses.Bus,
    air_temperature_profile: np.ndarray,
    enable_gas_heater: bool = True,
    enable_air_heat_pump: bool = True,
    enable_chp: bool = True,
    enable_battery: bool = True,
    enable_hot_water_tank: bool = True,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if enable_gas_heater:
        out["gas_heater"] = add_gas_heater(
            es=es,
            name="gas_heater_heat_grid_1",
            gas_bus=shared_gas_bus,
            heat_carrier_bus=central_heat_buses,
            investment=False,
            nominal_power=30.0,
        )
    if enable_air_heat_pump:
        out["air_heat_pump"] = add_heat_pump(
            es=es,
            name="hp_heat_grid_1",
            electricity_bus=shared_electricity_bus,
            heat_carrier_bus=central_heat_buses,
            air_temperature=air_temperature_profile,
            investment=False,
            nominal_power=0.2,
        )
    if enable_chp:
        out["chp"] = add_chp(
            es=es,
            name="chp_heat_grid_1",
            gas_bus=shared_hydrogen_bus,
            electricity_bus=shared_electricity_bus,
            heat_carrier_bus=central_heat_buses,
            investment=False,
            nominal_power=0.2,
        )
    if enable_battery:
        out["battery"] = add_battery(
            es=es,
            name="battery_heat_grid_1",
            electricity_bus=shared_electricity_bus,
            investment=False,
            nominal_capacity=5.0,
        )
    if enable_hot_water_tank:
        out["hot_water_tank"] = add_hot_water_tank(
            es=es,
            name="heat_storage_heat_grid_1",
            heat_buses=central_heat_buses,
            heat_levels=sorted(central_heat_buses.keys()),
            investment=False,
            volume_in_m3=0.05,
        )
    return out


def add_central_building_connection_and_load_block(
    es: solph.EnergySystem,
    building_id: str,
    central_heat_buses: Dict[int, solph.buses.Bus],
    shared_electricity_bus: solph.buses.Bus,
    heat_grid_temperature: int,
    local_heat_level: int,
    electricity_profile: np.ndarray,
    warm_water_profile: np.ndarray,
    space_heating_profile: np.ndarray,
    enable_local_pv: bool = True,
    pv_profile: Optional[np.ndarray] = None,
    pv_allow_curtailment: bool = True,
    pv_investment: bool = False,
    pv_investment_component: Any = None,
) -> Dict[str, Any]:
    local_heat = HeatCarrier(name=f"h_carrier_{building_id}", levels=[local_heat_level])
    local_heat_buses = local_heat.get_bus()
    local_e_bus = ElectricityCarrier(name=f"e_carrier_{building_id}").get_bus()
    es.add(*local_heat_buses.values(), local_e_bus)

    conv_h_from_grid_50 = solph.components.Converter(
        label=f"conv_h_from_grid_50_{building_id}",
        inputs={central_heat_buses[local_heat_level]: solph.flows.Flow()},
        outputs={local_heat_buses[local_heat_level]: solph.flows.Flow(variable_costs=1e-6)},
        conversion_factors={local_heat_buses[local_heat_level]: 1.0},
    )
    conv_h_from_grid_heatdemand = solph.components.Converter(
        label=f"conv_h_from_grid_heatdemand_{building_id}",
        inputs={central_heat_buses[heat_grid_temperature]: solph.flows.Flow()},
        outputs={local_heat_buses[local_heat_level]: solph.flows.Flow(variable_costs=1e-6)},
        conversion_factors={local_heat_buses[local_heat_level]: 1.0},
    )
    conv_e_into = solph.components.Converter(
        label=f"conv_e_into_grid_{building_id}",
        inputs={local_e_bus: solph.flows.Flow()},
        outputs={shared_electricity_bus: solph.flows.Flow(variable_costs=1e-6)},
        conversion_factors={shared_electricity_bus: 1.0},
    )
    conv_e_from = solph.components.Converter(
        label=f"conv_e_from_grid_{building_id}",
        inputs={shared_electricity_bus: solph.flows.Flow()},
        outputs={local_e_bus: solph.flows.Flow(variable_costs=1e-6)},
        conversion_factors={local_e_bus: 1.0},
    )

    e_demand = ElectricityDemand(
        name=f"e_demand_{building_id}",
        value_list=electricity_profile,
        bus=local_e_bus,
    ).create_demand()
    ww_demand = WarmWater(
        name=f"ww_demand_{building_id}",
        value_list=warm_water_profile,
        level=local_heat_level,
        bus=local_heat_buses[local_heat_level],
    ).create_demand()
    space_demand = HeatDemand(
        name=f"building_{building_id}",
        value_list=space_heating_profile,
        level=local_heat_level,
        bus=local_heat_buses[local_heat_level],
    ).create_demand()

    es.add(
        conv_h_from_grid_50,
        conv_h_from_grid_heatdemand,
        conv_e_into,
        conv_e_from,
        e_demand,
        ww_demand,
        space_demand,
    )

    local_pv = None
    if enable_local_pv and pv_profile is not None:
        local_pv = add_pv_system(
            es=es,
            name=f"pv_system_{building_id}",
            output_bus=local_e_bus,
            value_list=pv_profile,
            investment=pv_investment,
            nominal_power=1.0,
            investment_component=pv_investment_component,
            allow_curtailment=pv_allow_curtailment,
        )

    return {
        "local_heat_buses": local_heat_buses,
        "local_electricity_bus": local_e_bus,
        "conv_h_from_grid_50_label": f"conv_h_from_grid_50_{building_id}",
        "local_pv": local_pv,
    }


# ---------------------------------------------------------------------------
# Consistent technology block aliases (preferred naming for new code)
# ---------------------------------------------------------------------------
def add_pv_system_block(*args, **kwargs) -> Dict[str, Any]:
    return add_pv_system(*args, **kwargs)


def add_battery_block(*args, **kwargs) -> Dict[str, Any]:
    return add_battery(*args, **kwargs)


def add_hot_water_tank_block(*args, **kwargs) -> Dict[str, Any]:
    return add_hot_water_tank(*args, **kwargs)


def add_gas_heater_block(*args, **kwargs) -> Dict[str, Any]:
    return add_gas_heater(*args, **kwargs)


def add_heat_pump_block(*args, **kwargs) -> Dict[str, Any]:
    return add_heat_pump(*args, **kwargs)


def add_chp_block(*args, **kwargs) -> Dict[str, Any]:
    return add_chp(*args, **kwargs)


# ---------------------------------------------------------------------------
# Example extension block
# ---------------------------------------------------------------------------
def add_heat_dump_block(
    es: solph.EnergySystem,
    input_bus: solph.buses.Bus,
    label: str,
) -> Dict[str, Any]:
    """Small example block: add a sink that can always absorb heat."""
    sink = solph.components.Sink(
        label=label,
        inputs={input_bus: solph.flows.Flow()},
    )
    es.add(sink)
    return {"sink": sink}


__all__ = [
    "add_electricity_grid_block",
    "add_gas_grids_block",
    "add_hydrogen_grid_block",
    "add_main_grids_and_carriers_block",
    "add_local_building_carriers_block",
    "add_local_demands_block",
    "add_pv_system_block",
    "add_battery_block",
    "add_hot_water_tank_block",
    "add_gas_heater_block",
    "add_heat_pump_block",
    "add_chp_block",
    "add_local_pv_block",
    "add_local_storage_blocks",
    "add_local_conversion_technologies_block",
    "add_central_heat_carrier_block",
    "add_heat_grid_investment_block",
    "add_central_supply_technologies_block",
    "add_central_building_connection_and_load_block",
    "add_heat_dump_block",
    # Backward-compatible names
    "add_pv_system",
    "add_battery",
    "add_hot_water_tank",
    "add_gas_heater",
    "add_heat_pump",
    "add_chp",
]
