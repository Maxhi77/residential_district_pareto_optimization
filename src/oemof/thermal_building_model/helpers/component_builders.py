from __future__ import annotations

import copy
from typing import Callable

from oemof import solph
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses
from oemof.thermal_building_model.oemof_facades.technologies.converter import (
    AirHeatPump,
    CHP,
    GasHeater,
)
from oemof.thermal_building_model.oemof_facades.technologies.storages import Battery, HotWaterTank


def _prepare_investment_config(config, max_required_heating=None, reference_unit_quantity=None):
    component_config = copy.deepcopy(config)
    if max_required_heating is not None and component_config.maximum_capacity > max_required_heating:
        component_config.maximum_capacity = max_required_heating
    if reference_unit_quantity is not None:
        component_config.set_reference_unit_quantity(reference_unit_quantity=reference_unit_quantity)
    return component_config


def add_air_heat_pumps(
    *,
    system_id,
    config_map,
    dataclasses,
    components,
    heat_carrier_bus_for_component,
    heat_carrier_bus_for_converters,
    electricity_bus,
    air_temperature,
    max_required_heating,
    reference_unit_quantity=None,
):
    for key, config in config_map.items():
        air_heat_pump_config_building = _prepare_investment_config(
            config,
            max_required_heating=max_required_heating,
            reference_unit_quantity=reference_unit_quantity,
        )
        air_heat_pump_dataclass = AirHeatPump(
            heat_carrier_bus=heat_carrier_bus_for_component,
            investment=True,
            name="hp_" + str(system_id) + "_" + str(key),
            air_temperature=air_temperature,
            investment_component=air_heat_pump_config_building,
        )
        air_heat_pump_bus = air_heat_pump_dataclass.get_bus()
        air_heat_pump = air_heat_pump_dataclass.create_source()
        air_heat_pump_converters = air_heat_pump_dataclass.create_converters(
            heat_pump_bus=air_heat_pump_bus,
            electricity_bus=electricity_bus,
            heat_carrier_bus=heat_carrier_bus_for_converters,
        )

        dataclasses[system_id]["air_heat_pump_dataclass_" + str(key)] = air_heat_pump_dataclass
        components[system_id]["air_heat_pump_converters_" + str(key)] = air_heat_pump_converters
        components[system_id]["air_heat_pump_" + str(key)] = air_heat_pump
        components[system_id]["air_heat_pump_bus_" + str(key)] = air_heat_pump_bus


def add_gas_heaters(
    *,
    system_id,
    config_map,
    dataclasses,
    components,
    gas_bus,
    heat_carrier_bus,
    max_required_heating,
    reference_unit_quantity=None,
):
    for key, config in config_map.items():
        gas_heater_config_building = _prepare_investment_config(
            config,
            max_required_heating=max_required_heating,
            reference_unit_quantity=reference_unit_quantity,
        )
        gas_heater_dataclass = GasHeater(
            investment=True,
            name="gas_heater_" + str(system_id) + "_" + str(key),
            investment_component=gas_heater_config_building,
        )
        gas_heater_bus = gas_heater_dataclass.get_bus()
        gas_heater = gas_heater_dataclass.create_source()
        gas_heater_converters = gas_heater_dataclass.create_converters(
            gas_heater_bus=gas_heater_bus,
            gas_bus=gas_bus,
            heat_carrier_bus=heat_carrier_bus,
        )

        dataclasses[system_id]["gas_heater_dataclass_" + str(key)] = gas_heater_dataclass
        components[system_id]["gas_heater_converters_" + str(key)] = gas_heater_converters
        components[system_id]["gas_heater_bus_" + str(key)] = gas_heater_bus
        components[system_id]["gas_heater_" + str(key)] = gas_heater


def add_chp_units(
    *,
    system_id,
    config_map,
    dataclasses,
    components,
    gas_bus,
    heat_carrier_bus,
    electricity_bus,
    max_required_heating,
    reference_unit_quantity=None,
):
    for key, config in config_map.items():
        chp_config_building = _prepare_investment_config(
            config,
            max_required_heating=max_required_heating,
            reference_unit_quantity=reference_unit_quantity,
        )
        chp_dataclass = CHP(
            investment=True,
            name="chp_" + str(system_id) + "_" + str(key),
            investment_component=chp_config_building,
        )
        chp_bus = chp_dataclass.get_bus()
        chp = chp_dataclass.create_source()
        chp_converters = chp_dataclass.create_converters(
            chp_bus=chp_bus,
            gas_bus=gas_bus,
            heat_carrier_bus=heat_carrier_bus,
            electricity_bus=electricity_bus,
        )

        dataclasses[system_id]["chp_dataclass_" + str(key)] = chp_dataclass
        components[system_id]["chp_converters_" + str(key)] = chp_converters
        components[system_id]["chp_bus_" + str(key)] = chp_bus
        components[system_id]["chp_" + str(key)] = chp


def add_batteries(
    *,
    system_id,
    config_map,
    dataclasses,
    components,
    input_bus,
    output_bus,
    reference_unit_quantity=None,
    configure_config: Callable | None = None,
):
    for key, config in config_map.items():
        battery_config_building = copy.deepcopy(config)
        if configure_config is not None:
            configure_config(battery_config_building, key)
        if reference_unit_quantity is not None:
            battery_config_building.set_reference_unit_quantity(reference_unit_quantity=reference_unit_quantity)
        battery_dataclass = Battery(
            investment=True,
            name="battery_" + str(system_id) + "_" + str(key),
            input_bus=input_bus,
            output_bus=output_bus,
            investment_component=battery_config_building,
        )
        battery = battery_dataclass.create_storage()

        dataclasses[system_id]["battery_dataclass_" + str(key)] = battery_dataclass
        components[system_id]["battery_" + str(key)] = battery


def add_hot_water_tanks(
    *,
    system_id,
    config_map,
    dataclasses,
    components,
    temperature_buses,
    heat_carrier_bus,
    reference_unit_quantity=None,
    configure_config: Callable | None = None,
    max_temperature=80,
    min_temperature=40,
    invest_relation_input_capacity=None,
    invest_relation_output_capacity=None,
):
    for key, config in config_map.items():
        hot_water_tank_config_building = copy.deepcopy(config)
        if configure_config is not None:
            configure_config(hot_water_tank_config_building, key)
        if reference_unit_quantity is not None:
            hot_water_tank_config_building.set_reference_unit_quantity(
                reference_unit_quantity=reference_unit_quantity
            )

        hot_water_tank_input_bus = solph.buses.Bus(label=f"tank_input_bus_{system_id}_{key}")
        hot_water_tank_output_bus = solph.buses.Bus(label=f"tank_output_bus_{system_id}_{key}")
        storage_kwargs = {}
        if invest_relation_input_capacity is not None:
            storage_kwargs["invest_relation_input_capacity"] = invest_relation_input_capacity
        if invest_relation_output_capacity is not None:
            storage_kwargs["invest_relation_output_capacity"] = invest_relation_output_capacity

        hot_water_tank_dataclass = HotWaterTank(
            name=f"heat_storage_{system_id}_{key}",
            investment=True,
            temperature_buses=temperature_buses,
            max_temperature=max_temperature,
            min_temperature=min_temperature,
            investment_component=hot_water_tank_config_building,
            input_bus=hot_water_tank_input_bus,
            output_bus=hot_water_tank_output_bus,
            **storage_kwargs,
        )
        hot_water_tank = hot_water_tank_dataclass.create_storage()
        hot_water_tank_stratified_temp_levels = (
            hot_water_tank_dataclass.get_stratified_storage_temperature_levels()
        )
        hot_water_tank_stratified = hot_water_tank_dataclass.create_stratified_storage(
            hot_water_tank_stratified_temp_levels,
            heat_carrier_bus,
        )

        dataclasses[system_id]["hot_water_tank_dataclass_" + str(key)] = hot_water_tank_dataclass
        dataclasses[system_id]["hot_water_tank_stratisfied_temp_levels_" + str(key)] = (
            hot_water_tank_stratified_temp_levels
        )
        components[system_id]["hot_water_tank_" + str(key)] = hot_water_tank
        components[system_id]["hot_water_tank_stratisfied_" + str(key)] = hot_water_tank_stratified
        components[system_id]["hot_water_tank_input_bus_" + str(key)] = hot_water_tank_input_bus
        components[system_id]["hot_water_tank_output_bus_" + str(key)] = hot_water_tank_output_bus


def add_pv_systems(
    *,
    system_id,
    config_map,
    dataclasses,
    components,
    data_classes_comp,
    data,
    building_dataclass,
    electricity_bus,
    reference_unit_quantity=None,
):
    for key, config in config_map.items():
        pv_dataclass = copy.deepcopy(data_classes_comp[system_id]["pv_system"][key])
        pv_dataclass_config_building = copy.deepcopy(config)
        if reference_unit_quantity is not None:
            pv_dataclass_config_building.set_reference_unit_quantity(reference_unit_quantity=reference_unit_quantity)
        pv_dataclass.investment_component = pv_dataclass_config_building
        pv_dataclass.value_list = data["pv_system_" + str(system_id) + "_" + str(key)]
        pv_dataclass.update_maximum_investment_pv_capacity_based_on_area(
            area=building_dataclass.get_roof_area_for_pv()
        )
        pv_bus = pv_dataclass.get_bus()
        pv_system = pv_dataclass.create_source()
        pv_system_curtailment_capable = pv_dataclass.create_sink()
        connect_buses(input=pv_bus, target=electricity_bus)

        dataclasses[system_id]["pv_dataclass_" + str(key)] = pv_dataclass
        components[system_id]["pv_system_" + str(key)] = pv_system
        components[system_id]["pv_system_curtailment_capable_" + str(key)] = pv_system_curtailment_capable
        components[system_id]["pv_bus_" + str(key)] = pv_bus
