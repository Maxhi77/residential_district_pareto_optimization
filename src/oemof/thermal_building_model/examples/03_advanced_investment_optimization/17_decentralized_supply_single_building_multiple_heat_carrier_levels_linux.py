import argparse
from oemof.thermal_building_model.oemof_facades.base_component import  PhysicalBaseUnit
from oemof.solph.components import Converter
import copy
from oemof.thermal_building_model.oemof_facades.infrastructure.grids import ElectricityGrid, GasGrid, HydrogenGrid
from oemof.thermal_building_model.oemof_facades.infrastructure.carriers import ElectricityCarrier, HeatCarrier, \
    GasCarrier, HydrogenCarrier
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses, flatten_components_list
from oemof.thermal_building_model.oemof_facades.infrastructure.demands import ElectricityDemand, WarmWater
from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import PVSystem
from oemof.thermal_building_model.oemof_facades.technologies.storages import Battery, HotWaterTank
from oemof.thermal_building_model.oemof_facades.technologies.converter import AirHeatPump, GasHeater, CHP
from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import ThermalBuilding
from oemof.thermal_building_model.helpers.calculate_pv_electricity_yield import simulate_pv_yield
from oemof import solph
from oemof.solph.constraints import storage_level_constraint,equate_variables
from pyomo import environ as po

import matplotlib.pyplot as plt
import networkx as nx
from oemof.network.graph import create_nx_graph
import os
import pickle
from oemof.thermal_building_model.helpers import calculate_gain_by_sun
from oemof.thermal_building_model.helpers.path_helper import get_project_root
from oemof.thermal_building_model.input.economics.investment_components import battery_config,hot_water_tank_config,air_heat_pump_config,gas_heater_config,pv_system_config,chp_config
from oemof.thermal_building_model.input.economics.operation_grid_economics import (
    natural_gas_grid_config,
    bio_gas_grid_config,
    electricity_grid_config,
    hydrogen_grid_config,
)

from oemof.thermal_building_model.tabula.tabula_reader import Building
import pprint as pp
import geopandas as gpd
import tsam.timeseriesaggregation as tsam

import pandas as pd
import multiprocessing
from urllib.parse import urlparse

_CO2_WORKER_CONTEXT = {}
DEFAULT_SOLVER = "scip"
SOLVER = DEFAULT_SOLVER
DEFAULT_SOLVER_THREADS = 1
SOLVER_THREADS = DEFAULT_SOLVER_THREADS
DEFAULT_EV_MODE = "yes_EV"
EV_MODE = DEFAULT_EV_MODE
RESULT_STORAGE_ROOT = None
RESULT_CHECK_ROOT = None
DEFAULT_CO2_REDUCTION_FACTORS = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.01]
DEFAULT_PEAK_REDUCTION_FACTORS = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
PRICE_SCENARIO_CONFIGS = {
    "ref": {
        "electricity_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "electricity_minus20": {
        "electricity_factor": 0.8,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "electricity_plus20": {
        "electricity_factor": 1.2,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "gas_minus20": {
        "electricity_factor": 1.0,
        "natural_gas_factor": 0.8,
        "bio_gas_factor": 0.8,
        "hydrogen_factor": 1.0,
    },
    "gas_plus20": {
        "electricity_factor": 1.0,
        "natural_gas_factor": 1.2,
        "bio_gas_factor": 1.2,
        "hydrogen_factor": 1.0,
    },
    "hydrogen_minus20": {
        "electricity_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 0.8,
    },
    "hydrogen_plus20": {
        "electricity_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.2,
    },
}
DEFAULT_PRICE_SCENARIO_SWEEP = [
    "ref",
    "electricity_minus20",
    "electricity_plus20",
    "gas_minus20",
    "gas_plus20",
    "hydrogen_minus20",
    "hydrogen_plus20",
]
DEFAULT_PRICE_SCENARIOS = ["ref"]

def _set_co2_worker_context(context):
    global _CO2_WORKER_CONTEXT
    _CO2_WORKER_CONTEXT = context


def _normalize_price_scenario_name(name):
    if name is None:
        return "ref"
    value = str(name).strip().lower()
    return value if value else "ref"


def _resolve_price_scenario_config(price_scenario):
    if isinstance(price_scenario, dict):
        required_keys = {
            "electricity_factor",
            "natural_gas_factor",
            "bio_gas_factor",
            "hydrogen_factor",
        }
        missing = sorted(required_keys.difference(price_scenario.keys()))
        if missing:
            raise ValueError(f"price_scenario dict is missing keys: {missing}")
        return copy.deepcopy(price_scenario)

    scenario_name = _normalize_price_scenario_name(price_scenario)
    if scenario_name not in PRICE_SCENARIO_CONFIGS:
        raise ValueError(
            f"Unknown price scenario '{price_scenario}'. Supported: {sorted(PRICE_SCENARIO_CONFIGS.keys())}"
        )
    return copy.deepcopy(PRICE_SCENARIO_CONFIGS[scenario_name])


def _scenario_output_cluster_name(cluster_name, price_scenario_name):
    scenario_name = _normalize_price_scenario_name(price_scenario_name)
    if scenario_name == "ref":
        return cluster_name
    return f"{cluster_name}_{scenario_name}"
#  create solver
def run_model(co2_new,peak_new,refurbish,data,aggregation1,t1_agg,data_classes_comp,combined_cluster, building_id_in_cluster,cluster_occurence,heat_demand_worst_case,price_scenario=None):
    es = solph.EnergySystem(
        timeindex=t1_agg,
        timeincrement=[1] * len(t1_agg),
        periods=[t1_agg],
        tsa_parameters=[
            {
                "timesteps_per_period": aggregation1.hoursPerPeriod,
                "order": aggregation1.clusterOrder,
                "timeindex": aggregation1.timeIndex,
            },
        ],
        infer_last_interval=False,
    )

    price_scenario_config = _resolve_price_scenario_config(price_scenario)
    electricity_grid_config_grid = copy.deepcopy(electricity_grid_config)
    electricity_grid_config_grid.working_rate *= float(price_scenario_config["electricity_factor"])
    if peak_new is False or None:
        electricity_grid_dataclass = ElectricityGrid(operation_grid=electricity_grid_config_grid)
    else:
        electricity_grid_dataclass = ElectricityGrid(max_peak_from_grid=peak_new,
                                                     max_peak_into_grid=peak_new,
                                                     operation_grid=electricity_grid_config_grid)

    electricity_grid_bus_from_grid = electricity_grid_dataclass.get_bus_from_grid()
    electricity_grid_bus_into_grid = electricity_grid_dataclass.get_bus_into_grid()
    electricity_grid_sink = electricity_grid_dataclass.create_sink()
    electricity_grid_source = electricity_grid_dataclass.create_source()
    electricity_carrier_dataclass = ElectricityCarrier()
    electricity_carrier_bus = electricity_carrier_dataclass.get_bus()
    connect_buses(input=electricity_grid_bus_from_grid, target=electricity_carrier_bus, output=electricity_grid_bus_into_grid)

    electricity  = [electricity_grid_bus_from_grid,
                    electricity_grid_bus_into_grid,
                    electricity_grid_sink,
                    electricity_grid_source,
                    electricity_carrier_bus]
    es.add(*electricity)

    natural_gas_grid_config_grid = copy.deepcopy(natural_gas_grid_config)
    natural_gas_grid_config_grid.working_rate *= float(price_scenario_config["natural_gas_factor"])
    natural_gas_grid_dataclass = GasGrid(operation_grid=natural_gas_grid_config_grid,
                                 name="NaturalGas")
    natural_gas_grid_bus_from_grid = natural_gas_grid_dataclass.get_bus_from_grid()
    natural_gas_grid_source = natural_gas_grid_dataclass.create_source()

    bio_gas_grid_config_grid = copy.deepcopy(bio_gas_grid_config)
    bio_gas_grid_config_grid.working_rate *= float(price_scenario_config["bio_gas_factor"])
    bio_gas_grid_dataclass = GasGrid(operation_grid=bio_gas_grid_config_grid,
                                 name="BioGas")
    bio_gas_grid_bus_from_grid = bio_gas_grid_dataclass.get_bus_from_grid()
    bio_gas_grid_source = bio_gas_grid_dataclass.create_source()

    gas_carrier_dataclass = GasCarrier()
    gas_bus = gas_carrier_dataclass.get_bus()
    connect_buses(input=natural_gas_grid_bus_from_grid, target=gas_bus)
    connect_buses(input=bio_gas_grid_bus_from_grid, target=gas_bus)

    gas = [natural_gas_grid_bus_from_grid,natural_gas_grid_source,bio_gas_grid_source,bio_gas_grid_bus_from_grid,gas_bus]
    es.add(*gas)
    if True:
        hydrogen_grid_config_grid = copy.deepcopy(hydrogen_grid_config)
        hydrogen_grid_config_grid.working_rate *= float(price_scenario_config["hydrogen_factor"])
        hydrogen_grid_dataclass = HydrogenGrid(operation_grid=hydrogen_grid_config_grid)
        hydrogen_grid_bus_from_grid = hydrogen_grid_dataclass.get_bus_from_grid()
        hydrogen_grid_source = hydrogen_grid_dataclass.create_source()

        hydrogen_carrier_dataclass = HydrogenCarrier()
        hydrogen_bus = hydrogen_carrier_dataclass.get_bus()
        connect_buses(input=hydrogen_grid_bus_from_grid, target=hydrogen_bus)


        hydrogen = [hydrogen_grid_bus_from_grid,hydrogen_grid_source,hydrogen_bus]
        es.add(*hydrogen)
    component_per_building = {}

    dataclasses = {}
    components = {}
    index_stopper=1
    for index, row in combined_cluster.iterrows():
        if building_id_in_cluster != row["building_id"]:
            continue
        building_id =row['building_id']
        all_building_and_not_clusters = True
        if all_building_and_not_clusters:
            building_in_cluster = 1
            building_in_cluster_to_save = 1
        else:
            building_in_cluster =row['buildings_in_cluster']
            building_in_cluster_to_save = row['buildings_in_cluster']
        dataclasses[building_id] = {}
        components[building_id] = {}
        if True:
            electricity_carrier_dataclass_building = ElectricityCarrier(name="e_carrier_"+str(building_id))
            electricity_carrier_bus_building = electricity_carrier_dataclass_building.get_bus()
            grid_into_converter_building = Converter(label="conv_e_into_grid_"+str(building_id),
                                                  inputs={electricity_carrier_bus_building: solph.flows.Flow()},
                                                  outputs={electricity_carrier_bus: solph.flows.Flow()},
                                                  conversion_factors={electricity_carrier_bus_building: 1/ building_in_cluster })
            grid_from_converter_building = Converter(label="conv_e_from_grid_"+str(building_id),
                                                  inputs={electricity_carrier_bus: solph.flows.Flow()},
                                                  outputs={electricity_carrier_bus_building: solph.flows.Flow()},
                                                  conversion_factors={electricity_carrier_bus_building: 1/ building_in_cluster})

            electricity_demand_dataclass_building = data_classes_comp.loc["electricity_demand", building_id]
            electricity_demand_dataclass_building.value_list = data["e_demand_"+str(building_id)]
            electricity_demand_dataclass_building.bus=electricity_carrier_bus_building
            electricity_demand = electricity_demand_dataclass_building.create_demand()

            dataclasses[building_id]["electricity_carrier_dataclass_building"] = electricity_carrier_dataclass_building
            dataclasses[building_id]["electricity_demand_dataclass_building"] = electricity_demand_dataclass_building

            components[building_id]["electricity_carrier_bus_building"] = electricity_carrier_bus_building
            components[building_id]["grid_into_converter_building"] = grid_into_converter_building
            components[building_id]["grid_from_converter_building"] = grid_from_converter_building
            components[building_id]["electricity_demand"] = electricity_demand

        max_required_heating = max(data["ww_demand_"+str(building_id)] + data["building_"+str(building_id)]) * 3
        print("max_required_heating: "+str(max(data["ww_demand_"+str(building_id)] + data["building_"+str(building_id)])))
        building_dataclass = copy.deepcopy(data_classes_comp.loc["building", building_id])
        temp_heating_demand_building = building_dataclass.level_heating_demand
        if True:
            heat_carrier_temperature_levels = [40,50]
            if temp_heating_demand_building==60:
                heat_carrier_temperature_levels.extend([temp_heating_demand_building, 80])
            elif temp_heating_demand_building == 50:
                heat_carrier_temperature_levels.extend([80])
            else:
                heat_carrier_temperature_levels.extend([temp_heating_demand_building, 80])
        else:
            heat_carrier_temperature_levels = [40,50,60,70,80]
        heat_carrier_dataclass = HeatCarrier(name="h_carrier_"+str(building_id),
            levels = heat_carrier_temperature_levels)
        if True:
            heat_carrier_dataclass.connect_buses_decreasing_levels()
        else:
            connect_buses(input=heat_carrier_dataclass.get_bus([temp_heating_demand_building])[temp_heating_demand_building], target=heat_carrier_dataclass.get_bus([50])[50])
        heat_carrier_bus = heat_carrier_dataclass.get_bus()
        heat_demand_dataclass = data_classes_comp.loc["heat_demand", building_id]
        heat_demand_dataclass.value_list = data["ww_demand_"+str(building_id)]

        heat_demand_dataclass.level = heat_demand_dataclass.demand_temperature
        heat_demand_dataclass.bus = heat_carrier_bus[heat_demand_dataclass.demand_temperature]

        heat_demand = heat_demand_dataclass.create_demand()

        dataclasses[building_id]["heat_carrier_dataclass"] = heat_carrier_dataclass
        dataclasses[building_id]["heat_demand_dataclass"] = heat_demand_dataclass
        dataclasses[building_id]["max_required_heating"] = max(data["ww_demand_"+str(building_id)] + data["building_"+str(building_id)])
        components[building_id]["heat_demand"] = heat_demand
        components[building_id]["heat_carrier_bus"] = heat_carrier_bus

        if True:
            building_dataclass = copy.deepcopy(data_classes_comp.loc["building", building_id])
            building_dataclass.value_list = data["building_"+str(building_id)]

            demand = 0
            for cluster, count in cluster_occurence.items():
                # Hole den entsprechenden WW-Demand aus 'data' für das Cluster (erste Zahl in cluster_order entspricht dem Cluster)
                demand = demand + data["building_"+str(building_id)][cluster].sum() * count
            building_dataclass.tsam_total_amount=demand
            building_dataclass.set_number_of_buildings_in_cluster(building_in_cluster)
            building_dataclass.bus=heat_carrier_bus[building_dataclass.level_heating_demand]

            building_component = building_dataclass.create_demand()

            dataclasses[building_id]["building_dataclass"] = building_dataclass
            components[building_id]["building_component"] = building_component
        if True:
            for key, config in hot_water_tank_config.items():
                print(building_id)
                hot_water_tank_config_building = copy.deepcopy(config)
                if True:
                    if data_classes_comp[building_id]["building_type"] == "SFH":
                        if hot_water_tank_config_building.maximum_capacity >1:
                            hot_water_tank_config_building.maximum_capacity = 0.17 * heat_demand_worst_case
                    elif data_classes_comp[building_id]["building_type"] == "MFH":
                        if hot_water_tank_config_building.maximum_capacity > 1:
                            hot_water_tank_config_building.maximum_capacity = 0.2 * heat_demand_worst_case

                hot_water_tank_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)
                hot_water_tank_input_bus = solph.buses.Bus(label=f"tank_input_bus_{building_id}_{key}")
                hot_water_tank_output_bus = solph.buses.Bus(label=f"tank_output_bus_{building_id}_{key}")
                if False:
                    hot_water_tank_dataclass = HotWaterTank(
                        name=f"heat_storage_{building_id}_{key}",
                        investment=True,
                        temperature_buses = heat_carrier_dataclass.get_bus(),
                        max_temperature=80,
                        min_temperature=(40+temp_heating_demand_building)/2,
                        investment_component=hot_water_tank_config_building,
                        input_bus= heat_carrier_dataclass.get_bus()[80],
                        output_bus=heat_carrier_bus[80],
                        )

                else:
                    hot_water_tank_dataclass = HotWaterTank(
                        name=f"heat_storage_{building_id}_{key}",
                        investment=True,
                        temperature_buses = heat_carrier_dataclass.get_bus(),
                        max_temperature=80,
                        min_temperature=40,
                        investment_component=hot_water_tank_config_building,
                        input_bus= hot_water_tank_input_bus,
                        output_bus=hot_water_tank_output_bus,
                        )

                if True:
                    hot_water_tank = hot_water_tank_dataclass.create_storage()

                    dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)] = hot_water_tank_dataclass
                    components[building_id]["hot_water_tank_"+str(key)] = hot_water_tank
                    if True:
                        hot_water_tank_stratisfied_temp_levels_dict = hot_water_tank_dataclass.get_stratified_storage_temperature_levels()
                        hot_water_tank_stratisfied = hot_water_tank_dataclass.create_stratified_storage(
                            hot_water_tank_stratisfied_temp_levels_dict,heat_carrier_bus)

                        dataclasses[building_id]["hot_water_tank_stratisfied_temp_levels_"+str(key)] = hot_water_tank_stratisfied_temp_levels_dict
                        components[building_id]["hot_water_tank_stratisfied_"+str(key)] = hot_water_tank_stratisfied
                        components[building_id]["hot_water_tank_input_bus_"+str(key)] = hot_water_tank_input_bus
                        components[building_id]["hot_water_tank_output_bus_"+str(key)] = hot_water_tank_output_bus
        if True:
            for key, config in air_heat_pump_config.items():
                air_heat_pump_config_building =  copy.deepcopy(config)
                if air_heat_pump_config_building.maximum_capacity > max_required_heating:
                    air_heat_pump_config_building.maximum_capacity = max_required_heating
                air_heat_pump_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)
                air_heat_pump_dataclass = AirHeatPump(heat_carrier_bus= heat_carrier_dataclass.get_bus(),
                                                      investment=True,
                                                      name="hp_"+str(building_id)+"_"+str(key),
                                                      air_temperature=data["air_temperature"],
                                                      investment_component=air_heat_pump_config_building)
                air_heat_pump_bus = air_heat_pump_dataclass.get_bus()
                air_heat_pump= air_heat_pump_dataclass.create_source()
                new_key = int((80 + temp_heating_demand_building) / 2)

                air_heat_pump_converters= air_heat_pump_dataclass.create_converters(heat_pump_bus = air_heat_pump_bus,
                                                                                 electricity_bus = electricity_carrier_bus_building,
                                                                                 heat_carrier_bus=heat_carrier_bus)

                dataclasses[building_id]["air_heat_pump_dataclass_"+str(key)] = air_heat_pump_dataclass
                components[building_id]["air_heat_pump_converters_"+str(key)] = air_heat_pump_converters
                components[building_id]["air_heat_pump_"+str(key)] = air_heat_pump
                components[building_id]["air_heat_pump_bus_"+str(key)] = air_heat_pump_bus

        gas_carrier_dataclass_building = GasCarrier(name="g_carrier_"+str(building_id))
        gas_carrier_bus_building = gas_carrier_dataclass_building.get_bus()
        grid_gas_into_converter_building = Converter(label="conv_g_into_grid_"+str(building_id),
                                              inputs={gas_carrier_bus_building: solph.flows.Flow()},
                                              outputs={gas_bus: solph.flows.Flow()},
                                              conversion_factors={gas_carrier_bus_building: 1/building_in_cluster})
        grid_gas_from_converter_building = Converter(label="conv_g_from_grid_"+str(building_id),
                                              inputs={gas_bus: solph.flows.Flow()},
                                              outputs={gas_carrier_bus_building: solph.flows.Flow()},
                                              conversion_factors={gas_carrier_bus_building: 1/building_in_cluster})
        components[building_id]["grid_gas_into_converter_building"] = grid_gas_into_converter_building
        components[building_id]["grid_gas_from_converter_building"] = grid_gas_from_converter_building
        dataclasses[building_id]["gas_carrier_dataclass_building"] = gas_carrier_dataclass_building
        components[building_id]["gas_carrier_bus_building"] = gas_carrier_bus_building
        if True:
            hydrogen_carrier_dataclass_building = HydrogenCarrier(name="hydrogen_carrier_"+str(building_id))
            hydrogen_carrier_bus_building = hydrogen_carrier_dataclass_building.get_bus()
            grid_hydrogen_into_converter_building = Converter(label="conv_hydrogen_into_grid_"+str(building_id),
                                                  inputs={hydrogen_carrier_bus_building: solph.flows.Flow()},
                                                  outputs={hydrogen_bus: solph.flows.Flow()},
                                                  conversion_factors={hydrogen_carrier_bus_building: 1/building_in_cluster})
            grid_hydrogen_from_converter_building = Converter(label="conv_hydrogen_from_grid_"+str(building_id),
                                                  inputs={hydrogen_bus: solph.flows.Flow()},
                                                  outputs={hydrogen_carrier_bus_building: solph.flows.Flow()},
                                                  conversion_factors={hydrogen_carrier_bus_building: 1/building_in_cluster})
            components[building_id]["grid_hydrogen_into_converter_building"] = grid_hydrogen_into_converter_building
            components[building_id]["grid_hydrogen_from_converter_building"] = grid_hydrogen_from_converter_building
            dataclasses[building_id]["hydrogen_carrier_dataclass_building"] = hydrogen_carrier_dataclass_building
            components[building_id]["hydrogen_carrier_bus_building"] = hydrogen_carrier_bus_building

        for key, config in gas_heater_config.items():
            gas_heater_config_building = copy.deepcopy(config)
            if gas_heater_config_building.maximum_capacity > max_required_heating:
                gas_heater_config_building.maximum_capacity = max_required_heating
            gas_heater_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)

            gas_heater_dataclass = GasHeater(investment=True,
                                             name="gas_heater_"+str(building_id)+"_"+str(key),
                                             investment_component=gas_heater_config_building)
            gas_heater_bus = gas_heater_dataclass.get_bus()
            gas_heater= gas_heater_dataclass.create_source()
            gas_heater_converters= gas_heater_dataclass.create_converters(gas_heater_bus = gas_heater_bus,
                                                                          gas_bus = gas_carrier_bus_building,
                                                                          heat_carrier_bus=heat_carrier_dataclass.get_bus())

            dataclasses[building_id]["gas_heater_dataclass_"+str(key)] = gas_heater_dataclass
            components[building_id]["gas_heater_converters_"+str(key)] = gas_heater_converters
            components[building_id]["gas_heater_bus_"+str(key)] = gas_heater_bus
            components[building_id]["gas_heater_"+str(key)] = gas_heater
        if True:
            for key, config in chp_config.items():
                chp_config_building = copy.deepcopy(config)
                if chp_config_building.maximum_capacity > max_required_heating:
                    chp_config_building.maximum_capacity = max_required_heating
                chp_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)

                chp_dataclass = CHP(investment=True,
                                    name="chp_"+str(building_id)+"_"+str(key),
                                    investment_component=chp_config_building,
                                    )
                chp_bus = chp_dataclass.get_bus()
                chp= chp_dataclass.create_source()
                chp_converters= chp_dataclass.create_converters(chp_bus = chp_bus,
                                                                gas_bus = hydrogen_carrier_bus_building,
                                                                heat_carrier_bus=heat_carrier_dataclass.get_bus(),
                                                                electricity_bus = electricity_carrier_bus_building
                                                                )

                dataclasses[building_id]["chp_dataclass_"+str(key)] = chp_dataclass
                components[building_id]["chp_converters_"+str(key)] = chp_converters
                components[building_id]["chp_bus_"+str(key)] = chp_bus
                components[building_id]["chp_"+str(key)] = chp
        if True:
            for key, config in battery_config.items():
                battery_config_building =  copy.deepcopy(config)
                if data_classes_comp.loc["building", building_id] == "SFH":
                    battery_config_building.maximum_capacity = 30000/PhysicalBaseUnit.factor
                elif data_classes_comp.loc["building", building_id] == "MFH":
                    battery_config_building.maximum_capacity = 80000/PhysicalBaseUnit.factor
                battery_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)
                battery_dataclass = Battery(investment=True,
                                            name="battery_"+str(building_id)+"_"+str(key),
                                            input_bus = electricity_carrier_bus_building,
                                            output_bus = electricity_carrier_bus_building,
                                            investment_component=battery_config_building)
                battery = battery_dataclass.create_storage()

                dataclasses[building_id]["battery_dataclass_"+str(key)] = battery_dataclass
                components[building_id]["battery_"+str(key)] = battery
        if True:
            for key, config in pv_system_config.items():
                pv_dataclass = copy.deepcopy(data_classes_comp[building_id]["pv_system"][key])
                pv_dataclass_config_building = copy.deepcopy(config)
                pv_dataclass_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)
                pv_dataclass.investment_component=pv_dataclass_config_building

                pv_dataclass.value_list = data["pv_system_" + str(building_id)+"_"+str(key)]

                pv_dataclass.update_maximum_investment_pv_capacity_based_on_area(area = building_dataclass.get_roof_area_for_pv())
                pv_bus = pv_dataclass.get_bus()
                pv_system = pv_dataclass.create_source()
                pv_system_curtailment_capable = pv_dataclass.create_sink()
                connect_buses(input = pv_bus, target = electricity_carrier_bus_building)

                dataclasses[building_id]["pv_dataclass_"+str(key)] = pv_dataclass
                components[building_id]["pv_system_"+str(key)] = pv_system
                components[building_id]["pv_system_curtailment_capable_" + str(key)] = pv_system_curtailment_capable
                components[building_id]["pv_bus_" + str(key)] = pv_bus
    for building_id, building_data in components.items():
        # Ensure we're processing the components for the current building
        for oemof_comp, comp_value in building_data.items():
            # Check if the component is a list (which it should not be, based on the structure)
            if isinstance(comp_value, list):
                for item in comp_value:
                    es.add(item)
                    # Process each component in the list
            # Check if the component is a dictionary, meaning it has nested components
            elif isinstance(comp_value, dict):
                # If it's a dictionary, iterate over its key-value pairs
                for key, value in comp_value.items():
                    es.add(value)
            else:
                # Otherwise, just add the component directly
                es.add(comp_value)
    model = solph.Model(es)
    if True:
        for building_id, building_data in dataclasses.items():
            for key, _ in hot_water_tank_config.items():
                for temperature, stratisfied_storage in components[building_id]["hot_water_tank_stratisfied_"+str(key)].items():
                    storage_father = es.groups[components[building_id]["hot_water_tank_"+str(key)].label]
                    storage_child = stratisfied_storage
                    share_stratisfied = dataclasses[building_id]["hot_water_tank_stratisfied_temp_levels_"+str(key)][temperature]

                    def equate_variables_rule(share_stratisfied):
                        return model.GenericInvestmentStorageBlock.invest[storage_child, 0] <= model.GenericInvestmentStorageBlock.invest[storage_father, 0] * share_stratisfied

                    setattr(model, "eq_"+components[building_id]["hot_water_tank_stratisfied_"+str(key)][temperature].label, po.Constraint(rule=equate_variables_rule(share_stratisfied)))
    if False:
        if len(pv_system_config) > 1:
            for key, config in pv_system_config.items():
                maximum_pv_capacity = dataclasses[building_id][
                    "pv_dataclass_" + str(key)].investment_component.maximum_capacity
                maximum_key = max(pv_system_config)

                def equate_variables_rule(maximum_pv_capacity, maximum_key):
                    for ke in range(maximum_key):
                        key = int(ke + 1)
                        return model.InvestmentFlowBlock.invest[
                            es.groups[components[building_id]["pv_system_" + str(key)].label],
                            components[building_id]["electricity_carrier_bus_building"],
                            0] + \
                            model.InvestmentFlowBlock.invest[
                                es.groups[components[building_id]["pv_system_" + str(key)].label],
                                components[building_id]["electricity_carrier_bus_building"],
                                0] <= maximum_pv_capacity

                setattr(model, "eq" + components[building_id]["pv_system_" + str(key)].label,
                        po.Constraint(rule=equate_variables_rule(int(maximum_key), int(maximum_pv_capacity))))

    if False:
        # Create the graph from the energy system (es)
        graph = create_nx_graph(es)
        # Draw the graph
        plt.figure(figsize=(18, 14))  # Set figure size
        nx.draw(graph, with_labels=True, font_size=6)
        plt.show()
    if co2_new is None:
        model = solph.constraints.additional_total_limit(model, "co2", limit=144000000)
    else:
        print("new co2 VALUE:"+str(co2_new))
        model = solph.constraints.additional_total_limit(model, "co2", limit=co2_new)
    # Show the graph
    # Show the graph
        print("__________")
        print("start for:")
        print("boundary co2:"+str(co2_new))
        print("boundary peak:" + str(peak_new))
    try:


        model.solve(solver=SOLVER, solve_kwargs={"tee": True},
                                              cmdline_options={"mipgap": 0.005,
                                                               "threads": SOLVER_THREADS},
        )
        meta_results = solph.processing.meta_results(model)
        results = solph.processing.results(model)
        final_results = {}
        final_results[electricity_grid_dataclass.name] = electricity_grid_dataclass.post_process(results,electricity_grid_source,electricity_grid_sink)
        final_results[natural_gas_grid_dataclass.name] = natural_gas_grid_dataclass.post_process(results,natural_gas_grid_source,None)
        final_results[bio_gas_grid_dataclass.name] = bio_gas_grid_dataclass.post_process(results,bio_gas_grid_source,None)

        if True:
            final_results[hydrogen_grid_dataclass.name] = hydrogen_grid_dataclass.post_process(results, hydrogen_grid_source, None)
        if False:
            final_results[heat_grid_dataclass.name] = heat_grid_dataclass.post_process(results,heat_grid_source,None)

        for building_id, building_data in components.items():
            final_results[building_id] = {}
            if True:
                for key,_ in pv_system_config.items():
                    final_results[building_id][dataclasses[building_id]["pv_dataclass_"+str(key)].name] = dataclasses[building_id]["pv_dataclass_"+str(key)].post_process(results,components[building_id]["pv_system_"+str(key)],components[building_id]["pv_system_curtailment_capable_"+str(key)])
            if True:
                for key,_ in hot_water_tank_config.items():
                    final_results[building_id][dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].name] = dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].post_process(results,components[building_id]["hot_water_tank_"+str(key)])
            if True:
                for key,_ in battery_config.items():
                    final_results[building_id][dataclasses[building_id]["battery_dataclass_"+str(key)].name] = dataclasses[building_id]["battery_dataclass_"+str(key)].post_process(results,components[building_id]["battery_"+str(key)])
            for key,_ in gas_heater_config.items():
                final_results[building_id][dataclasses[building_id]["gas_heater_dataclass_"+str(key)].name] = dataclasses[building_id]["gas_heater_dataclass_"+str(key)].post_process(results,
                                                                                                                                                                  components[building_id]["gas_heater_"+str(key)],
                                                                                                                                                                  components[building_id]["gas_heater_converters_"+str(key)],
                                                                                                                                                                  components[building_id]["heat_carrier_bus"],
                                                                                                                                       components[building_id]["gas_carrier_bus_building"])
            if True:
                for key, _ in chp_config.items():
                    final_results[building_id][dataclasses[building_id]["chp_dataclass_" + str(key)].name] = \
                    dataclasses[building_id]["chp_dataclass_" + str(key)].post_process(results,
                                                                                              components[building_id][
                                                                                                  "chp_" + str(key)],
                                                                                              components[building_id][
                                                                                                  "chp_converters_" + str(
                                                                                                      key)],
                                                                                              components[building_id][
                                                                                                  "heat_carrier_bus"],
                                                                                              components[building_id][
                                                                                                  "hydrogen_carrier_bus_building"])
                for key,_ in air_heat_pump_config.items():
                    final_results[building_id][dataclasses[building_id]["air_heat_pump_dataclass_"+str(key)].name] = dataclasses[building_id]["air_heat_pump_dataclass_"+str(key)].post_process(results,
                                                                                                                                                                            components[building_id]["air_heat_pump_"+str(key)],
                                                                                                                                                                        components[building_id]["air_heat_pump_converters_"+str(key)],
                                                                                                                                                                        components[building_id]["heat_carrier_bus"],
                                                                                                                                                                        components[building_id]["electricity_carrier_bus_building"])
            if True:
                final_results[building_id][dataclasses[building_id]["building_dataclass"].name] = dataclasses[building_id]["building_dataclass"].post_process(results,components[building_id]["building_component"])
                final_results[building_id]["max_required_heating"] = dataclasses[building_id]["max_required_heating"]
            final_results[building_id][dataclasses[building_id]["electricity_demand_dataclass_building"].name] = dataclasses[building_id]["electricity_demand_dataclass_building"].post_process(results,components[building_id]["electricity_demand"])

            final_results[building_id][dataclasses[building_id]["heat_demand_dataclass"].name] = dataclasses[building_id]["heat_demand_dataclass"].post_process(results,components[building_id]["heat_demand"])
            if True:
                final_results[building_id]["buildings_in_cluster"] = building_in_cluster_to_save
                final_results[building_id]["buildings_in_cluster_used"] = dataclasses[building_id][
                "building_dataclass"].buildings_in_cluster
        co2_investment = 0
        for building_id in components:

            # For each component, sum up the CO2 contributions to the overall system
            if True:
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["battery_dataclass_"+str(key)].name]["investment_co2"] for key,_ in battery_config.items())
            if True:
                co2_investment += sum(
                    final_results[building_id][dataclasses[building_id]["chp_dataclass_" + str(key)].name][
                        "investment_co2"] for key, _ in chp_config.items())
                co2_investment += sum(
                    final_results[building_id][dataclasses[building_id]["air_heat_pump_dataclass_" + str(key)].name][
                        "investment_co2"] for key, _ in air_heat_pump_config.items())
            if True:
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].name]["investment_co2"] for key,_ in hot_water_tank_config.items())
            co2_investment += sum(final_results[building_id][dataclasses[building_id]["gas_heater_dataclass_"+str(key)].name]["investment_co2"] for key,_ in gas_heater_config.items())
            if True:
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["pv_dataclass_"+str(key)].name]["investment_co2"] for key,_ in pv_system_config.items())
            if True:
                co2_investment += final_results[building_id][dataclasses[building_id]["building_dataclass"].name]["investment_co2"
                                ]
        co2_operation = final_results[electricity_grid_dataclass.name]["flow_from_grid_co2"
                                ]-final_results[electricity_grid_dataclass.name]["flow_into_grid_co2"
                                ]+final_results[natural_gas_grid_dataclass.name]["flow_from_grid_co2"
                                ]+final_results[bio_gas_grid_dataclass.name]["flow_from_grid_co2"
                                ]+final_results[hydrogen_grid_dataclass.name]["flow_from_grid_co2"
                                ]

        co2_oemof_model = model.total_limit_co2()

        print("co2_constraint: ", co2_oemof_model)
        print("co2_post_process_inv: ", co2_investment)
        print("co2_post_process_oper: ", co2_operation)
        print("objective",str(meta_results["objective"]))
        print("elect_from_grid: "+str(sum(final_results[electricity_grid_dataclass.name]["flow_from_grid"])/1000))
        print("elect_into_grid: "+str(sum(final_results[electricity_grid_dataclass.name]["flow_into_grid"])/1000))
        print("elect_from_grid: "+str((final_results[electricity_grid_dataclass.name]["flow_from_grid"].sum())/1000))
        print("elect_into_grid: "+str((final_results[electricity_grid_dataclass.name]["flow_into_grid"].sum())/1000))
        final_results["co2_oemof_model"] = co2_oemof_model
        final_results["co2_operation"] = co2_operation
        final_results["co2_investment"] = co2_investment
        final_results["totex"] = meta_results["objective"]
        final_results["totex_oemof_model"] = meta_results["objective"]
        if SOLVER == "scip":
            return final_results, co2_oemof_model, None
        else:
            return final_results, co2_oemof_model, meta_results["solver"]["Wall time"]

    except Exception as e:
        print(e)
        return None, None, None


def process_cluster(building_row, building_type, epw_path, directory_path, data, refurbish, number_of_time_steps,data_classes_comp,ev,time_index):

        building_id = building_row['building_id']
        tabula_year_class = building_row['tabula_year_class']
        building_floor_area = building_row['net_floor_area']
        building_roof_area = building_row['roof_surface_area']
        number_of_occupants = building_row['number_of_residents']
        number_of_households = building_row['number_of_apartments']
        azimuth = building_row['azimuth']
        tilt = building_row['tilt']
        # Zuordnung Baujahr
        year_map = {
            1: 1850, 2: 1910, 3: 1930, 4: 1950,
            5: 1960, 6: 1970, 7: 1980, 8: 1990,
            9: 2000, 10: 2005, 11: 2010, 12: 2020
        }
        year_of_construction = year_map.get(tabula_year_class, 2000)  # fallback

        # Demands laden
        with open(os.path.join(directory_path, f"{building_id}_demand_{ev}.pkl"), "rb") as f:
            demand = pickle.load(f)

        electricity_cols = [col for col in demand.columns if col.startswith("Electricity")]
        demand_electricity = (demand[electricity_cols].sum(axis=1) * 1000).tolist()
        warm_water_cols = [col for col in demand.columns if col.startswith("Warm Water_")]
        demand_warm_water = demand[warm_water_cols].sum(axis=1).tolist()

        # Datenklassen
        electricity_demand = ElectricityDemand(name=f"e_demand_{building_id}", value_list=demand_electricity)
        heat_demand = WarmWater(name=f"ww_demand_{building_id}", value_list=demand_warm_water, level=40)
        building = ThermalBuilding(
            name=f"building_{building_id}",
            floor_area=building_floor_area,
            number_of_occupants=number_of_occupants,
            number_of_household=number_of_households,
            country="DE",
            construction_year=year_of_construction,
            class_building="average",
            building_type=building_type,
            refurbishment_status=refurbish,
            heat_level_calculation=True,
            time_index=time_index,
        )

        heat_demand_worst_case_building = ThermalBuilding(
            name=f"building_{building_id}",
            floor_area=building_floor_area,
            number_of_occupants=number_of_occupants,
            number_of_household=number_of_households,
            country="DE",
            construction_year=year_of_construction,
            class_building="average",
            building_type=building_type,
            refurbishment_status="no_refurbishment",
            heat_level_calculation=True,
            time_index=time_index,
        )
        heat_demand_worst_case = max(heat_demand_worst_case_building.value_list) + max(heat_demand.value_list)
        # PV-Ertrag pro Watt
        pv_yield_per_wp = simulate_pv_yield(
            pv_nominal_power_in_watt=1,
            tilt=tilt,
            azimuth=azimuth,
            epw_path=epw_path
        )

        dict_pv_systems = {}
        for key, config in pv_system_config.items():
            pv_system_config_building= copy.deepcopy(config)
            pv = PVSystem(
                investment=True,
                name=f"pv_system_{building_id}_{key}",
                value_list=pv_yield_per_wp.tolist(),
                investment_component=pv_system_config_building
            )

            pv.update_maximum_investment_pv_capacity_based_on_area(building.get_roof_area_for_pv(building_roof_area))
            data[pv.name] = pv.value_list
            dict_pv_systems[key] = pv


        # Spalten hinzufügen
        data[electricity_demand.name] = electricity_demand.value_list
        data[heat_demand.name] = heat_demand.value_list
        data[building.name] = building.value_list

        data_classes_comp[building_id] = {"electricity_demand":electricity_demand,
                                          "pv_system":dict_pv_systems,
                                          "building":building,
                                          "heat_demand":heat_demand,
                                          "building_type":building_type}
        return data, data_classes_comp, heat_demand_worst_case

def compute_co2_target(co2_ref, factor):
    # preserves your original handling of negative references
    if co2_ref > 0:
        return co2_ref * factor
    else:
        return co2_ref * (1 + 1 - factor)

def compute_peak_target(peak_ref, factor):
    return peak_ref * factor

def _co2_factor_to_suffix(factor):
    # Examples: 1 -> "1", 0.9 -> "09", 0.08 -> "008", 0.05 -> "005"
    value = float(factor)
    if value.is_integer():
        return str(int(value))

    s = f"{value:.6f}".rstrip("0").rstrip(".")
    if s.startswith("-0."):
        return "m0" + s[3:]
    if s.startswith("0."):
        return "0" + s[2:]
    return s.replace(".", "")

def _atomic_pickle_dump(path, payload):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(payload, fh)

def _load_pickle_if_exists(path):
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as fh:
        data = pickle.load(fh)
    return data if isinstance(data, dict) else {}

def _build_result_entries(final_results, co2, peak_reduction_factor, refurbish, time, price_scenario_name):
    if final_results is None:
        full_entry = {
            "results": None,
            "co2": None,
            "peak_reduction_factor": None,
            "refurbish": None,
            "price_scenario": price_scenario_name,
            "totex": None,
            "peak": None,
            "time": None,
        }
        simple_entry = {
            "co2": None,
            "peak_reduction_factor": None,
            "refurbish": None,
            "price_scenario": price_scenario_name,
            "totex": None,
            "peak": None,
            "time": None,
        }
        return full_entry, simple_entry

    peak = max(final_results["Electricity"]["peak_from_grid"], final_results["Electricity"]["peak_into_grid"])
    totex = final_results["totex"]
    full_entry = {
        "results": final_results,
        "co2": co2,
        "peak_reduction_factor": peak_reduction_factor,
        "refurbish": refurbish,
        "price_scenario": price_scenario_name,
        "totex": totex,
        "peak": peak,
        "electricity_grid": final_results["Electricity"],
        "peak_from_grid": final_results["Electricity"]["peak_from_grid"],
        "peak_into_grid": final_results["Electricity"]["peak_into_grid"],
        "time": time,
    }
    simple_entry = {
        "co2": co2,
        "peak_reduction_factor": peak_reduction_factor,
        "refurbish": refurbish,
        "price_scenario": price_scenario_name,
        "totex": totex,
        "peak": peak,
        "electricity_grid": final_results["Electricity"],
        "peak_from_grid": final_results["Electricity"]["peak_from_grid"],
        "peak_into_grid": final_results["Electricity"]["peak_into_grid"],
        "time": time,
    }
    return full_entry, simple_entry

def run_co2_factor_worker(args):
    group_key, co2_reduction_factor = args

    context = _CO2_WORKER_CONTEXT[group_key]
    data = context["data"]
    aggregation1 = context["aggregation1"]
    t1_agg = context["t1_agg"]
    data_classes_comp = context["data_classes_comp"]
    combined_cluster = context["combined_cluster"]
    building_id_in_cluster = context["building_id_in_cluster"]
    cluster_occurence = context["cluster_occurence"]
    heat_demand_worst_case = context["heat_demand_worst_case"]
    refurbish = context["refurbish"]
    peak_reduction_factors = context["peak_reduction_factors"]
    co2_reference = context["co2_reference"]
    file_path_base = context["file_path_base"]
    simple_file_path_base = context["simple_file_path_base"]
    price_scenario_name = context["price_scenario_name"]
    price_scenario = context["price_scenario"]
    worker_file_path, worker_simple_file_path = _get_worker_result_paths(
        file_path_base,
        simple_file_path_base,
        co2_reduction_factor,
    )

    if os.path.exists(worker_file_path) and os.path.exists(worker_simple_file_path):
        return group_key, worker_file_path, worker_simple_file_path

    ref = "co2"
    co2_new = compute_co2_target(co2_reference, co2_reduction_factor)
    first_co2_run_in_peak_loop = True
    peak_reference = None

    worker_results = {}
    worker_simple_results = {}

    for peak_reduction_factor in peak_reduction_factors:
        if first_co2_run_in_peak_loop:
            peak_new = False
        else:
            peak_new = compute_peak_target(peak_reference, peak_reduction_factor)

        final_results, co2, time = run_model(
            co2_new,
            peak_new,
            refurbish,
            data,
            aggregation1,
            t1_agg,
            data_classes_comp,
            combined_cluster,
            building_id_in_cluster,
            cluster_occurence,
            heat_demand_worst_case,
            price_scenario=price_scenario,
        )

        key = (co2_reduction_factor, peak_reduction_factor, refurbish, ref)
        full_entry, simple_entry = _build_result_entries(
            final_results,
            co2,
            peak_reduction_factor,
            refurbish,
            time,
            price_scenario_name,
        )
        worker_results[key] = full_entry
        worker_simple_results[key] = simple_entry

        if final_results is None:
            if first_co2_run_in_peak_loop:
                first_co2_run_in_peak_loop = False
                peak_reference = False
            break

        if first_co2_run_in_peak_loop:
            first_co2_run_in_peak_loop = False
            peak_reference = full_entry["peak"]

    _atomic_pickle_dump(worker_file_path, worker_results)
    _atomic_pickle_dump(worker_simple_file_path, worker_simple_results)

    return group_key, worker_file_path, worker_simple_file_path

def _safe_load_cluster_pickle(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    with open(path, "rb") as f:
        data = pickle.load(f)
    if isinstance(data, pd.DataFrame):
        return data
    return pd.DataFrame(data)


def _is_reference_k(k_value):
    return isinstance(k_value, str) and k_value.lower() == "reference"


def _normalize_k_for_key(k_value):
    if _is_reference_k(k_value):
        return "reference"
    return int(k_value)


def _format_k_for_log(k_value):
    if _is_reference_k(k_value):
        return "reference"
    return f"k{int(k_value):02d}"


def _dedupe_keep_order(items):
    out = []
    seen = set()
    for item in items:
        marker = item.lower() if isinstance(item, str) else item
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def _parse_k_values(raw_csv):
    if raw_csv is None:
        return []

    out = []
    for token in str(raw_csv).split(","):
        value = token.strip()
        if not value:
            continue
        if value.lower() == "reference":
            out.append("reference")
        else:
            out.append(int(value))
    return _dedupe_keep_order(out)


def _parse_ueu_cases(raw_csv):
    if raw_csv is None:
        return []

    out = []
    for token in str(raw_csv).split(","):
        value = token.strip()
        if not value:
            continue
        if ":" in value:
            value = value.split(":", 1)[0].strip()
        if value:
            out.append(value)
    return _dedupe_keep_order(out)


def _parse_refurbishments(raw_csv):
    if raw_csv is None:
        return []
    values = [x.strip() for x in str(raw_csv).split(",") if x.strip()]
    return _dedupe_keep_order(values)


def _parse_price_scenarios(raw_csv):
    if raw_csv is None:
        return list(DEFAULT_PRICE_SCENARIOS)

    values = []
    for token in str(raw_csv).split(","):
        scenario_name = _normalize_price_scenario_name(token)
        if not scenario_name:
            continue
        if scenario_name == "all":
            values.extend(DEFAULT_PRICE_SCENARIO_SWEEP)
            continue
        if scenario_name not in PRICE_SCENARIO_CONFIGS:
            raise ValueError(
                f"Unknown price scenario '{scenario_name}'. Supported: {sorted(PRICE_SCENARIO_CONFIGS.keys())} or 'all'"
            )
        values.append(scenario_name)

    values = _dedupe_keep_order(values)
    if not values:
        return list(DEFAULT_PRICE_SCENARIOS)
    return values


def _script_base_path():
    return os.path.dirname(os.path.abspath(__file__))


def _normalize_result_root(raw_value, base_path):
    if raw_value is None:
        return None

    value = str(raw_value).strip()
    if not value or value.lower() in {"none", "default"}:
        return None

    # Keep local Windows paths (e.g. C:\data) untouched.
    if len(value) >= 2 and value[1] == ":":
        normalized = value
    else:
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme != "file":
            if not parsed.path:
                raise ValueError(f"Invalid storage/check URL without path: {value}")
            normalized = parsed.path
        elif parsed.scheme == "file":
            normalized = parsed.path
        else:
            normalized = value

    if not os.path.isabs(normalized):
        normalized = os.path.abspath(os.path.join(base_path, normalized))

    return os.path.normpath(normalized)


def _get_result_storage_root():
    return RESULT_STORAGE_ROOT if RESULT_STORAGE_ROOT else _script_base_path()


def _get_result_check_root():
    if RESULT_CHECK_ROOT:
        return RESULT_CHECK_ROOT
    return _get_result_storage_root()


def _get_result_output_dir(root_path, cluster_name, k_value, building_type):
    cluster_root = os.path.join(root_path, cluster_name)
    if _is_reference_k(k_value):
        return os.path.join(cluster_root, "reference")

    k_token = f"k{int(k_value):02d}"
    if building_type == "SFH":
        return os.path.join(cluster_root, f"sfh_cluster_{k_token}")
    if building_type == "MFH":
        return os.path.join(cluster_root, f"mfh_cluster_{k_token}")
    raise ValueError(f"Unsupported building_type '{building_type}'")


def _get_result_file_bases(root_path, cluster_name, k_value, building_type, refurbish, ev, building_id_in_cluster):
    output_dir = _get_result_output_dir(root_path, cluster_name, k_value, building_type)
    base_filename = "results_dec_" + str(refurbish) + "_" + str(ev) + "_" + str(building_id_in_cluster)
    simple_base_filename = (
        "simple_results_dec_" + str(refurbish) + "_" + str(ev) + "_" + str(building_id_in_cluster)
    )
    return os.path.join(output_dir, base_filename), os.path.join(output_dir, simple_base_filename)


def _get_worker_result_paths(file_path_base, simple_file_path_base, co2_reduction_factor):
    suffix = _co2_factor_to_suffix(co2_reduction_factor)
    return (
        file_path_base + "_co2_" + suffix + ".pkl",
        simple_file_path_base + "_co2_" + suffix + ".pkl",
    )


def _missing_co2_factors(file_path_base, simple_file_path_base, co2_reduction_factors):
    missing = []
    for co2_reduction_factor in co2_reduction_factors:
        worker_file_path, worker_simple_file_path = _get_worker_result_paths(
            file_path_base,
            simple_file_path_base,
            co2_reduction_factor,
        )
        if not (os.path.exists(worker_file_path) and os.path.exists(worker_simple_file_path)):
            missing.append(co2_reduction_factor)
    return missing


def _discover_available_k_values(base_path, cluster_name, building_type=None):
    cluster_root = os.path.join(base_path, cluster_name)
    if not os.path.isdir(cluster_root):
        return []

    if building_type == "SFH":
        prefixes = ("sfh_cluster_k",)
    elif building_type == "MFH":
        prefixes = ("mfh_cluster_k",)
    else:
        prefixes = ("sfh_cluster_k", "mfh_cluster_k")

    k_values = set()
    for name in os.listdir(cluster_root):
        folder_path = os.path.join(cluster_root, name)
        if not os.path.isdir(folder_path):
            continue
        for prefix in prefixes:
            if name.startswith(prefix):
                suffix = name[len(prefix):]
                if suffix.isdigit():
                    k_values.add(int(suffix))
    return sorted(k_values)


def _load_clusters_for_k(base_path, cluster_name, k_value):
    cluster_root = os.path.join(base_path, cluster_name)
    if _is_reference_k(k_value):
        gpkg_ueu = os.path.join(cluster_root, f"{cluster_name}.gpkg")
        if not os.path.exists(gpkg_ueu):
            raise FileNotFoundError(f"Reference gpkg not found: {gpkg_ueu}")
        gdf_ueu = gpd.read_file(gpkg_ueu)
        sfh_cluster = gdf_ueu.loc[gdf_ueu["tabula_building_type"] == "SFH"].copy()
        mfh_cluster = gdf_ueu.loc[gdf_ueu["tabula_building_type"] == "MFH"].copy()
        reference_dir = os.path.join(cluster_root, "reference")
        return sfh_cluster, mfh_cluster, reference_dir, reference_dir

    k_token = f"k{int(k_value):02d}"
    sfh_dir = os.path.join(cluster_root, f"sfh_cluster_{k_token}")
    mfh_dir = os.path.join(cluster_root, f"mfh_cluster_{k_token}")
    sfh_cluster = _safe_load_cluster_pickle(os.path.join(sfh_dir, "sfh_cluster.pkl"))
    mfh_cluster = _safe_load_cluster_pickle(os.path.join(mfh_dir, "mfh_cluster.pkl"))
    return sfh_cluster, mfh_cluster, sfh_dir, mfh_dir


def _collect_building_ids_for_k(base_path, cluster_name, k_value, building_type=None):
    sfh_cluster, mfh_cluster, _, _ = _load_clusters_for_k(base_path, cluster_name, k_value)
    building_in_cluster = []
    if building_type in (None, "SFH") and not sfh_cluster.empty and "building_id" in sfh_cluster.columns:
        building_in_cluster.extend(sfh_cluster["building_id"].tolist())
    if building_type in (None, "MFH") and not mfh_cluster.empty and "building_id" in mfh_cluster.columns:
        building_in_cluster.extend(mfh_cluster["building_id"].tolist())
    return list(dict.fromkeys(building_in_cluster))


def _prepare_group_context(
    refurbish,
    building_id_in_cluster,
    ueu,
    k_value,
    building_type=None,
    price_scenario_name="ref",
    output_cluster_name=None,
):
    base_path = _script_base_path()
    directory_path = os.path.join(base_path, ueu)
    result_storage_root = _get_result_storage_root()
    scenario_name = _normalize_price_scenario_name(price_scenario_name)
    scenario_config = _resolve_price_scenario_config(scenario_name)
    if output_cluster_name is None:
        output_cluster_name = _scenario_output_cluster_name(ueu, scenario_name)

    number_of_time_steps = 8760
    sfh_cluster, mfh_cluster, _, _ = _load_clusters_for_k(base_path, ueu, k_value)
    if sfh_cluster.empty and mfh_cluster.empty:
        raise ValueError(f"No cluster files found for cluster='{ueu}', k={k_value}.")

    combined_frames = [df for df in (sfh_cluster, mfh_cluster) if not df.empty]
    combined_cluster = pd.concat(combined_frames, ignore_index=True)

    ev = EV_MODE
    is_sfh = not sfh_cluster.empty and bool((sfh_cluster["building_id"] == building_id_in_cluster).any())
    is_mfh = not mfh_cluster.empty and bool((mfh_cluster["building_id"] == building_id_in_cluster).any())
    if not is_sfh and not is_mfh:
        raise ValueError(
            f"building_id '{building_id_in_cluster}' not found in k={k_value} for cluster '{ueu}'."
        )

    if building_type == "SFH" and not is_sfh:
        raise ValueError(
            f"building_id '{building_id_in_cluster}' is not SFH in k={k_value} for cluster '{ueu}'."
        )
    if building_type == "MFH" and not is_mfh:
        raise ValueError(
            f"building_id '{building_id_in_cluster}' is not MFH in k={k_value} for cluster '{ueu}'."
        )
    output_building_type = building_type if building_type in {"SFH", "MFH"} else ("SFH" if is_sfh else "MFH")

    file_path_base, simple_file_path_base = _get_result_file_bases(
        result_storage_root,
        output_cluster_name,
        k_value,
        output_building_type,
        refurbish,
        ev,
        building_id_in_cluster,
    )
    output_dir = os.path.dirname(file_path_base)
    os.makedirs(output_dir, exist_ok=True)

    main_path = get_project_root()
    data = pd.DataFrame()
    data_classes_comp = pd.DataFrame()
    epw_path = os.path.join(
        main_path,
        "thermal_building_model",
        "input",
        "weather_files",
        "03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv",
    )
    location = calculate_gain_by_sun.Location(
        epwfile_path=os.path.join(
            main_path,
            "thermal_building_model",
            "input",
            "weather_files",
            "03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv",
        ),
    )

    data["air_temperature"] = location.weather_data["drybulb_C"].to_list()
    date_time_index = solph.create_time_index(2025, number=number_of_time_steps - 1)
    data.index = date_time_index
    heat_demand_worst_case = None

    for _, building_row in sfh_cluster.iterrows():

        if building_id_in_cluster == building_row["building_id"]:
            data, data_classes_comp, heat_demand_worst_case = process_cluster(
                building_row=building_row,
                building_type="SFH",
                epw_path=epw_path,
                directory_path=directory_path,
                data=data,
                refurbish=refurbish,
                number_of_time_steps=number_of_time_steps,
                data_classes_comp=data_classes_comp,
                ev=ev,
                time_index=date_time_index,
            )


    for _, building_row in mfh_cluster.iterrows():
        if building_id_in_cluster == building_row["building_id"]:
            data, data_classes_comp, heat_demand_worst_case = process_cluster(
                building_row=building_row,
                building_type="MFH",
                epw_path=epw_path,
                directory_path=directory_path,
                data=data,
                refurbish=refurbish,
                number_of_time_steps=number_of_time_steps,
                data_classes_comp=data_classes_comp,
                ev=ev,
                time_index=date_time_index,
            )

    if heat_demand_worst_case is None:
        raise ValueError(f"No matching building_id '{building_id_in_cluster}' in cluster '{ueu}'.")

    typical_periods = 30
    hours_per_period = 24
    aggregation1 = tsam.TimeSeriesAggregation(
        timeSeries=data.iloc[:8760],
        noTypicalPeriods=typical_periods,
        hoursPerPeriod=hours_per_period,
        clusterMethod="k_means",
    )
    aggregation1.createTypicalPeriods()
    cluster_occurence = aggregation1.clusterPeriodNoOccur
    data = aggregation1.typicalPeriods
    t1_agg = pd.date_range("2025-01-01", periods=typical_periods * hours_per_period, freq="h")

    final_results_ref, co2_ref, time = run_model(
        None,
        None,
        refurbish,
        data,
        aggregation1,
        t1_agg,
        data_classes_comp,
        combined_cluster,
        building_id_in_cluster,
        cluster_occurence,
        heat_demand_worst_case,
        price_scenario=scenario_config,
    )
    if final_results_ref is None:
        raise RuntimeError(
            f"Reference scenario failed for cluster={ueu}, building={building_id_in_cluster}, "
            f"refurbish={refurbish}, price_scenario={scenario_name}."
        )

    hp_power = 0
    gas_heater_power = 0
    if False:
        for i in range(1, 2):
            hp_power += final_results_ref[building_id_in_cluster]["hp_" + building_id_in_cluster + "_" + str(i)]["capacity"]
            gas_heater_power += final_results_ref[building_id_in_cluster]["gas_heater_" + building_id_in_cluster + "_" + str(i)]["capacity"]
        if hp_power >= gas_heater_power:
            step = 0.05
            co2_reduction_factors = [round(1 - i * step, 3) for i in range(int((1.0 - (-0.1)) / step) + 1)]
        else:
            co2_reduction_factors = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.01]
            co2_reduction_factors = list(dict.fromkeys(co2_reduction_factors))
    #peak_reduction_factors = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]

    co2_reduction_factors = list(DEFAULT_CO2_REDUCTION_FACTORS)
    peak_reduction_factors = list(DEFAULT_PEAK_REDUCTION_FACTORS)

    worker_context = {
        "data": data,
        "aggregation1": aggregation1,
        "t1_agg": t1_agg,
        "data_classes_comp": data_classes_comp,
        "combined_cluster": combined_cluster,
        "building_id_in_cluster": building_id_in_cluster,
        "cluster_occurence": cluster_occurence,
        "heat_demand_worst_case": heat_demand_worst_case,
        "refurbish": refurbish,
        "peak_reduction_factors": peak_reduction_factors,
        "co2_reference": co2_ref,
        "file_path_base": file_path_base,
        "simple_file_path_base": simple_file_path_base,
        "price_scenario_name": scenario_name,
        "price_scenario": scenario_config,
    }

    return {
        "co2_reduction_factors": co2_reduction_factors,
        "worker_context": worker_context,
    }

def run_main(refurbish, building_id_in_cluster, ueu, k_value, building_type=None, price_scenario_name="ref"):
    output_cluster_name = _scenario_output_cluster_name(ueu, price_scenario_name)
    prepared = _prepare_group_context(
        refurbish,
        building_id_in_cluster,
        ueu,
        k_value,
        building_type=building_type,
        price_scenario_name=price_scenario_name,
        output_cluster_name=output_cluster_name,
    )

    group_key = (
        ueu,
        _normalize_k_for_key(k_value),
        building_id_in_cluster,
        refurbish,
        _normalize_price_scenario_name(price_scenario_name),
    )
    _set_co2_worker_context({group_key: prepared["worker_context"]})
    worker_outputs = [run_co2_factor_worker((group_key, factor)) for factor in prepared["co2_reduction_factors"]]
    _CO2_WORKER_CONTEXT.clear()
    return worker_outputs

def run_cluster_refurbish_co2_parallel(
    cluster_name,
    processes,
    selected_k_values=None,
    selected_k_values_sfh=None,
    selected_k_values_mfh=None,
    price_scenarios_to_run=None,
):
    base_path = _script_base_path()
    result_check_root = _get_result_check_root()
    if price_scenarios_to_run is None:
        price_scenarios_to_run = list(DEFAULT_PRICE_SCENARIOS)
    else:
        price_scenarios_to_run = _dedupe_keep_order(
            [_normalize_price_scenario_name(s) for s in price_scenarios_to_run]
        )
    if not price_scenarios_to_run:
        print(f"No price scenarios selected for cluster {cluster_name}")
        return

    # Backward compatibility: one list for both SFH/MFH
    if selected_k_values is not None:
        if selected_k_values_sfh is None:
            selected_k_values_sfh = selected_k_values
        if selected_k_values_mfh is None:
            selected_k_values_mfh = selected_k_values

    available_k_values_sfh = _discover_available_k_values(base_path, cluster_name, building_type="SFH")
    available_k_values_mfh = _discover_available_k_values(base_path, cluster_name, building_type="MFH")
    reference_available = os.path.exists(os.path.join(base_path, cluster_name, f"{cluster_name}.gpkg"))
    if not available_k_values_sfh and not available_k_values_mfh and not reference_available:
        print(f"No SFH/MFH k-folders and no reference gpkg found for cluster {cluster_name}")
        return

    def _resolve_k_values(selected_k_values_local, available_k_values_local, label):
        if selected_k_values_local is None:
            return available_k_values_local

        resolved = []
        missing_numeric = []
        request_reference = False
        for raw in selected_k_values_local:
            if _is_reference_k(raw):
                request_reference = True
                continue
            try:
                k_int = int(raw)
            except Exception:
                print(f"Skipped invalid {label} k value for {cluster_name}: {raw}")
                continue
            if k_int in available_k_values_local:
                resolved.append(k_int)
            else:
                missing_numeric.append(k_int)

        if missing_numeric:
            print(f"Skipped missing {label} k values for {cluster_name}: {sorted(set(missing_numeric))}")

        if request_reference:
            if reference_available:
                resolved.append("reference")
            else:
                print(f"Skipped {label} reference for {cluster_name}: {cluster_name}.gpkg not found")

        out = []
        seen = set()
        for item in resolved:
            marker = item if isinstance(item, str) else int(item)
            if marker in seen:
                continue
            seen.add(marker)
            out.append(item)
        return out

    k_values_to_run_sfh = _resolve_k_values(selected_k_values_sfh, available_k_values_sfh, "SFH")
    k_values_to_run_mfh = _resolve_k_values(selected_k_values_mfh, available_k_values_mfh, "MFH")

    if not k_values_to_run_sfh and not k_values_to_run_mfh:
        print(f"No runnable SFH/MFH k values for cluster {cluster_name}")
        return

    task_list = []
    group_contexts = {}

    for building_type, k_values_to_run in (("SFH", k_values_to_run_sfh), ("MFH", k_values_to_run_mfh)):
        for k_value in k_values_to_run:
            building_in_cluster = _collect_building_ids_for_k(
                base_path,
                cluster_name,
                k_value,
                building_type=building_type,
            )
            for price_scenario_name in price_scenarios_to_run:
                output_cluster_name = _scenario_output_cluster_name(cluster_name, price_scenario_name)
                for refurbish in refurbishment:
                    for building_id_in_cluster in building_in_cluster:
                        check_file_path_base, check_simple_file_path_base = _get_result_file_bases(
                            result_check_root,
                            output_cluster_name,
                            k_value,
                            building_type,
                            refurbish,
                            EV_MODE,
                            building_id_in_cluster,
                        )
                        missing_factors = _missing_co2_factors(
                            check_file_path_base,
                            check_simple_file_path_base,
                            DEFAULT_CO2_REDUCTION_FACTORS,
                        )
                        if not missing_factors:
                            print(
                                f"skip existing: {cluster_name} | scenario={price_scenario_name} | {building_type} | "
                                f"k={_format_k_for_log(k_value)} | {building_id_in_cluster} | {refurbish}"
                            )
                            continue

                        try:
                            prepared = _prepare_group_context(
                                refurbish,
                                building_id_in_cluster,
                                cluster_name,
                                k_value,
                                building_type=building_type,
                                price_scenario_name=price_scenario_name,
                                output_cluster_name=output_cluster_name,
                            )
                        except Exception as exc:
                            print(
                                f"skip failed prepare: {cluster_name} | scenario={price_scenario_name} | {building_type} | "
                                f"k={_format_k_for_log(k_value)} | {building_id_in_cluster} | {refurbish} | {exc}"
                            )
                            continue

                        group_key = (
                            cluster_name,
                            building_type,
                            _normalize_k_for_key(k_value),
                            building_id_in_cluster,
                            refurbish,
                            _normalize_price_scenario_name(price_scenario_name),
                        )
                        group_contexts[group_key] = prepared["worker_context"]
                        missing_set = set(missing_factors)
                        pending_factors = [
                            factor for factor in prepared["co2_reduction_factors"] if factor in missing_set
                        ]
                        if not pending_factors:
                            print(
                                f"skip existing after-prepare: {cluster_name} | scenario={price_scenario_name} | {building_type} | "
                                f"k={_format_k_for_log(k_value)} | {building_id_in_cluster} | {refurbish}"
                            )
                            continue

                        for co2_reduction_factor in pending_factors:
                            task_list.append((group_key, co2_reduction_factor))
    if not task_list:
        print(f"No runnable tasks for cluster {cluster_name}")
        return

    if processes is None:
        processes = max(1, multiprocessing.cpu_count() // 2)

    if "fork" in multiprocessing.get_all_start_methods():
        mp_ctx = multiprocessing.get_context("fork")
        with mp_ctx.Pool(processes=processes, initializer=_set_co2_worker_context, initargs=(group_contexts,)) as pool:
            for group_key, worker_file_path, worker_simple_file_path in pool.imap_unordered(run_co2_factor_worker, task_list):
                print(f"saved {group_key} -> {worker_file_path}")
    else:
        print("No 'fork' start method available. Falling back to serial co2/refurbish task execution.")
        _set_co2_worker_context(group_contexts)
        for task in task_list:
            group_key, worker_file_path, worker_simple_file_path = run_co2_factor_worker(task)
            print(f"saved {group_key} -> {worker_file_path}")
        _CO2_WORKER_CONTEXT.clear()


DEFAULT_REFURBISHMENT = [
    "no_refurbishment",
    "usual_refurbishment",
    "advanced_refurbishment",
    "GEG_standard",
]
DEFAULT_CLUSTER_LIST = [
    "processed_bds_in_DENI03403000SEC5658",
]
DEFAULT_K_VALUES_TO_OPTIMIZE_SFH = ["reference", 1, 2, 4, 6, 8, 10, 14, 18]
DEFAULT_K_VALUES_TO_OPTIMIZE_MFH = ["reference", 1, 2, 3, 4, 5, 6]

# Legacy batches (alter Ablauf):
# (batch_name, sfh_k_values, mfh_k_values)
LEGACY_K_VALUE_BATCHES = [
    #("reference_only", ["reference"], ["reference"]),
    #("1", [1, 2, 4, 6, 8], [1, 2, 3, 4]),
    #("2", [10, 14, 18], [5 ,6]),
    #("3", [18], [6]),
]

refurbishment = list(DEFAULT_REFURBISHMENT)
price_scenarios = list(DEFAULT_PRICE_SCENARIOS)


def _run_legacy_batches(cluster_list, workers):
    print(
        f"run_mode=legacy_batches workers={workers} clusters={cluster_list} "
        f"ev={EV_MODE} price_scenarios={price_scenarios} "
        f"result_check_root={_get_result_check_root()} result_storage_root={_get_result_storage_root()}"
    )
    if not LEGACY_K_VALUE_BATCHES:
        print("No LEGACY_K_VALUE_BATCHES configured. Nothing to run in legacy_batches mode.")
        return
    for cluster_name in cluster_list:
        for idx, (batch_name, sfh_batch, mfh_batch) in enumerate(LEGACY_K_VALUE_BATCHES, start=1):
            print(
                f"cluster={cluster_name} | batch={idx}/{len(LEGACY_K_VALUE_BATCHES)} ({batch_name}) "
                f"| sfh={sfh_batch} | mfh={mfh_batch}"
            )
            run_cluster_refurbish_co2_parallel(
                cluster_name,
                processes=workers,
                selected_k_values_sfh=sfh_batch,
                selected_k_values_mfh=mfh_batch,
                price_scenarios_to_run=price_scenarios,
            )


def _run_cli_mode(args, workers):
    cluster_list = _parse_ueu_cases(args.ueu_cases)
    sfh_requested = _parse_k_values(args.sfh_k)
    mfh_requested = _parse_k_values(args.mfh_k)
    selected_refurbishments = _parse_refurbishments(args.refurbishments)
    selected_price_scenarios = _parse_price_scenarios(args.price_scenarios)

    if not cluster_list:
        raise ValueError("No UEU cases provided via --ueu-cases.")
    if not sfh_requested and not mfh_requested:
        raise ValueError("Both --sfh-k and --mfh-k are empty.")
    if not selected_refurbishments:
        raise ValueError("No refurbishments provided via --refurbishments.")
    if not selected_price_scenarios:
        raise ValueError("No price scenarios provided via --price-scenarios.")

    global refurbishment, price_scenarios
    refurbishment = selected_refurbishments
    price_scenarios = selected_price_scenarios

    print(
        f"host={args.host_name} run_mode=cli clusters={cluster_list} workers={workers} "
        f"solver_threads={SOLVER_THREADS} sfh_k={sfh_requested} mfh_k={mfh_requested} "
        f"refurbishments={refurbishment} price_scenarios={price_scenarios} ev={EV_MODE} "
        f"result_check_root={_get_result_check_root()} "
        f"result_storage_root={_get_result_storage_root()}"
    )

    for cluster_name in cluster_list:
        print(f"cluster={cluster_name} start")
        run_cluster_refurbish_co2_parallel(
            cluster_name,
            processes=workers,
            selected_k_values_sfh=sfh_requested,
            selected_k_values_mfh=mfh_requested,
            price_scenarios_to_run=price_scenarios,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run decentralized optimization with host-specific settings.")
    parser.add_argument("--host-name", type=str, default="unknown")
    parser.add_argument("--run-mode", type=str, default="cli", choices=["cli", "legacy_batches"])
    parser.add_argument(
        "--workers",
        type=str,
        default="auto",
        help="Parallel worker processes. Use an integer, or False/auto for automatic sizing.",
    )
    parser.add_argument("--serial", action="store_true", help="Run selected jobs sequentially.")
    parser.add_argument("--solver", type=str, default=DEFAULT_SOLVER, help="Solver backend, e.g. scip, gurobi, cbc.")
    parser.add_argument("--solver-threads", type=int, default=DEFAULT_SOLVER_THREADS, help="Solver threads per job.")
    parser.add_argument(
        "--result-check-root",
        type=str,
        default=None,
        help="Root path used to check whether result files already exist. Supports ftp://... URL by using its path part.",
    )
    parser.add_argument(
        "--result-storage-root",
        type=str,
        default=None,
        help="Root path where new result files are written. Supports ftp://... URL by using its path part.",
    )
    parser.add_argument(
        "--sfh-k",
        type=str,
        default=",".join(str(x) for x in DEFAULT_K_VALUES_TO_OPTIMIZE_SFH),
        help="Comma-separated SFH k values, e.g. reference,1,2,4",
    )
    parser.add_argument(
        "--mfh-k",
        type=str,
        default=",".join(str(x) for x in DEFAULT_K_VALUES_TO_OPTIMIZE_MFH),
        help="Comma-separated MFH k values, e.g. reference,1,2,3",
    )
    parser.add_argument(
        "--ueu-cases",
        type=str,
        default=",".join(DEFAULT_CLUSTER_LIST),
        help="Comma-separated UEU names. Optional ':value' suffix is accepted and ignored.",
    )
    parser.add_argument(
        "--refurbishments",
        type=str,
        default=",".join(DEFAULT_REFURBISHMENT),
        help="Comma-separated refurbishment cases.",
    )
    parser.add_argument(
        "--price-scenarios",
        type=str,
        default=",".join(DEFAULT_PRICE_SCENARIOS),
        help=(
            "Comma-separated price scenarios. Supported: "
            "ref,electricity_minus20,electricity_plus20,gas_minus20,gas_plus20,"
            "hydrogen_minus20,hydrogen_plus20 or 'all'."
        ),
    )
    parser.add_argument(
        "--ev",
        type=str,
        default=DEFAULT_EV_MODE,
        choices=["no_EV", "yes_EV"],
        help="Demand file suffix for EV scenario.",
    )
    args = parser.parse_args()

    script_base = _script_base_path()
    RESULT_STORAGE_ROOT = _normalize_result_root(args.result_storage_root, script_base)
    RESULT_CHECK_ROOT = _normalize_result_root(args.result_check_root, script_base)
    if RESULT_STORAGE_ROOT:
        os.makedirs(RESULT_STORAGE_ROOT, exist_ok=True)

    if not str(args.solver).strip():
        raise ValueError("--solver must not be empty")
    SOLVER = str(args.solver).strip()

    if args.solver_threads <= 0:
        raise ValueError("--solver-threads must be > 0")

    SOLVER_THREADS = args.solver_threads
    EV_MODE = args.ev
    price_scenarios = _parse_price_scenarios(args.price_scenarios)
    workers_raw = str(args.workers).strip().lower()
    if workers_raw in {"false", "auto", "none"}:
        n_cores = os.cpu_count() or 1
        workers = max(1, n_cores // 2)
    else:
        try:
            workers = int(args.workers)
        except ValueError as exc:
            raise ValueError("--workers must be an integer or one of: False, auto, none") from exc
        if workers <= 0:
            raise ValueError("--workers must be > 0, or use False/auto for automatic sizing")
    if args.serial:
        workers = 1
    workers = max(1, workers)

    if args.run_mode == "legacy_batches":
        _run_legacy_batches(_parse_ueu_cases(args.ueu_cases), workers)
    else:
        _run_cli_mode(args, workers)
