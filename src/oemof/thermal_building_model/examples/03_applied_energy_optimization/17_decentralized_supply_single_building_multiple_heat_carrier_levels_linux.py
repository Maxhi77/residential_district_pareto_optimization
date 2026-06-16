"""Run the decentralized building-level optimization workflow.

This executable prepares clustered SFH/MFH building representatives, applies
refurbishment, EV, and price-scenario settings, and runs building-level
investment optimizations with CO2 and electricity-peak reduction sweeps. Input
data are read from processed UEU cluster folders and weather/economic
configuration files. Outputs are full and reduced pickle result files per
cluster, building representative, refurbishment case, price scenario, and CO2
step. This is the main decentralized workflow entry point used to reproduce the
building-level analyses in the manuscript.
"""

import argparse
from oemof.thermal_building_model.oemof_facades.base_component import  PhysicalBaseUnit
from oemof.solph.components import Converter
import copy
from oemof.thermal_building_model.oemof_facades.infrastructure.grids import ElectricityGrid, GasGrid, HydrogenGrid
from oemof.thermal_building_model.oemof_facades.infrastructure.carriers import ElectricityCarrier, HeatCarrier, \
    GasCarrier, HydrogenCarrier
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses, flatten_components_list
from oemof import solph
from oemof.solph.constraints import storage_level_constraint,equate_variables
from pyomo import environ as po

import matplotlib.pyplot as plt
import networkx as nx
from oemof.network.graph import create_nx_graph
import os
import pickle
from oemof.thermal_building_model.helpers import calculate_gain_by_sun
from oemof.thermal_building_model.helpers.co2_parallel import (
    run_cluster_refurbish_co2_parallel as _run_cluster_refurbish_co2_parallel,
    run_co2_factor_for_context as _run_co2_factor_for_context,
)
from oemof.thermal_building_model.helpers.optimization_io import (
    k_to_folder_token as _k_to_folder_token,
    normalize_k_for_key as _normalize_k_for_key,
    normalize_result_root,
    parse_unique_k_values as _parse_k_values,
    parse_unique_refurbishments as _parse_refurbishments,
    parse_unique_simple_ueu_cases as _parse_ueu_cases,
    script_base_path,
)
from oemof.thermal_building_model.helpers.cluster_io import (
    load_clusters_for_k as _load_clusters_for_k,
    load_clusters_for_k_pair as _load_clusters_for_k_pair,
)
from oemof.thermal_building_model.helpers.component_builders import (
    add_air_heat_pumps,
    add_batteries,
    add_chp_units,
    add_gas_heaters,
    add_hot_water_tanks,
    add_pv_systems,
)
from oemof.thermal_building_model.helpers.process_cluster import (
    process_cluster_decentralized as process_cluster,
)
from oemof.thermal_building_model.helpers.price_scenarios import (
    DEFAULT_PRICE_SCENARIOS,
    normalize_price_scenario_name as _normalize_price_scenario_name,
    parse_price_scenarios as _parse_price_scenarios,
    resolve_price_scenario_config as _resolve_price_scenario_config,
    scenario_output_cluster_name as _scenario_output_cluster_name,
)
from oemof.thermal_building_model.helpers.result_helpers import (
    get_result_file_bases as _get_result_file_bases,
)
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
import tsam.timeseriesaggregation as tsam

import pandas as pd
from urllib.parse import urlparse

_CO2_WORKER_CONTEXT = {}
DEFAULT_SOLVER = "scip"
SOLVER = DEFAULT_SOLVER
DEFAULT_SOLVER_THREADS = 1
SOLVER_THREADS = DEFAULT_SOLVER_THREADS
DEFAULT_EV_MODE = "no_EV"
EV_MODE = DEFAULT_EV_MODE
RESULT_STORAGE_ROOT = None
RESULT_CHECK_ROOT = None
DEFAULT_CO2_REDUCTION_FACTORS = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.01]
DEFAULT_PEAK_REDUCTION_FACTORS = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]

def _set_co2_worker_context(context):
    global _CO2_WORKER_CONTEXT
    _CO2_WORKER_CONTEXT = context


# Build and solve one decentralized building-level investment model.
def run_model(
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
    price_scenario=None,
    combined_optimization=False,
):
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
    electricity_grid_config_grid.revenue *= float(price_scenario_config["electricity_feed_in_factor"])
    if peak_new is False or None:
        electricity_grid_dataclass = ElectricityGrid(operation_grid=electricity_grid_config_grid)
    else:
        electricity_grid_dataclass = ElectricityGrid(max_peak_from_grid=peak_new,
                                                     max_peak_into_grid=peak_new,
                                                     operation_grid=electricity_grid_config_grid)

    # Electricity grid and district-level electricity carrier.
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

    # Natural gas and biogas grids.
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
    # Hydrogen grid.
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
    buildings_in_cluster_to_save = {}
    for index, row in combined_cluster.iterrows():
        if (not combined_optimization) and building_id_in_cluster != row["building_id"]:
            continue
        building_id =row['building_id']
        all_building_and_not_clusters = not combined_optimization
        if all_building_and_not_clusters:
            building_in_cluster = 1
            building_in_cluster_to_save = 1
        else:
            building_in_cluster = row.get("buildings_in_cluster", 1)
            building_in_cluster_to_save = row.get("buildings_in_cluster", 1)
        buildings_in_cluster_to_save[building_id] = building_in_cluster_to_save
        if isinstance(heat_demand_worst_case, dict):
            heat_demand_worst_case_building = heat_demand_worst_case.get(building_id)
        else:
            heat_demand_worst_case_building = heat_demand_worst_case
        dataclasses[building_id] = {}
        components[building_id] = {}
        # Building electricity carrier, grid converters, and electricity demand.
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
        if heat_demand_worst_case_building is None:
            heat_demand_worst_case_building = max_required_heating
        print("max_required_heating: "+str(max(data["ww_demand_"+str(building_id)] + data["building_"+str(building_id)])))
        building_dataclass = copy.deepcopy(data_classes_comp.loc["building", building_id])
        temp_heating_demand_building = building_dataclass.level_heating_demand
        # Building heat carrier and warm-water demand.
        heat_carrier_temperature_levels = [40,50]
        if temp_heating_demand_building==60:
            heat_carrier_temperature_levels.extend([temp_heating_demand_building, 80])
        elif temp_heating_demand_building == 50:
            heat_carrier_temperature_levels.extend([80])
        else:
            heat_carrier_temperature_levels.extend([temp_heating_demand_building, 80])
        heat_carrier_dataclass = HeatCarrier(name="h_carrier_"+str(building_id),
            levels = heat_carrier_temperature_levels)
        heat_carrier_dataclass.connect_buses_decreasing_levels()
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

        # Space-heating demand from the thermal building model.
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
        # Hot-water thermal storage.
        def configure_hot_water_tank_capacity(hot_water_tank_config_building, key):
            if data_classes_comp[building_id]["building_type"] == "SFH":
                if hot_water_tank_config_building.maximum_capacity >1:
                    hot_water_tank_config_building.maximum_capacity = 0.17 * heat_demand_worst_case_building
            elif data_classes_comp[building_id]["building_type"] == "MFH":
                if hot_water_tank_config_building.maximum_capacity > 1:
                    hot_water_tank_config_building.maximum_capacity = 0.2 * heat_demand_worst_case_building

        add_hot_water_tanks(
            system_id=building_id,
            config_map=hot_water_tank_config,
            dataclasses=dataclasses,
            components=components,
            temperature_buses=heat_carrier_dataclass.get_bus(),
            heat_carrier_bus=heat_carrier_bus,
            reference_unit_quantity=building_in_cluster,
            configure_config=configure_hot_water_tank_capacity,
        )
        # Air-source heat pumps.
        add_air_heat_pumps(
            system_id=building_id,
            config_map=air_heat_pump_config,
            dataclasses=dataclasses,
            components=components,
            heat_carrier_bus_for_component=heat_carrier_dataclass.get_bus(),
            heat_carrier_bus_for_converters=heat_carrier_bus,
            electricity_bus=electricity_carrier_bus_building,
            air_temperature=data["air_temperature"],
            max_required_heating=max_required_heating,
            reference_unit_quantity=building_in_cluster,
        )

        # Building gas and hydrogen carriers.
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

        # Gas heaters.
        add_gas_heaters(
            system_id=building_id,
            config_map=gas_heater_config,
            dataclasses=dataclasses,
            components=components,
            gas_bus=gas_carrier_bus_building,
            heat_carrier_bus=heat_carrier_dataclass.get_bus(),
            max_required_heating=max_required_heating,
            reference_unit_quantity=building_in_cluster,
        )
        # CHP units.
        add_chp_units(
            system_id=building_id,
            config_map=chp_config,
            dataclasses=dataclasses,
            components=components,
            gas_bus=hydrogen_carrier_bus_building,
            heat_carrier_bus=heat_carrier_dataclass.get_bus(),
            electricity_bus=electricity_carrier_bus_building,
            max_required_heating=max_required_heating,
            reference_unit_quantity=building_in_cluster,
        )
        # Battery storage.
        def configure_battery_capacity(battery_config_building, key):
            if data_classes_comp.loc["building", building_id] == "SFH":
                battery_config_building.maximum_capacity = 30000/PhysicalBaseUnit.factor
            elif data_classes_comp.loc["building", building_id] == "MFH":
                battery_config_building.maximum_capacity = 80000/PhysicalBaseUnit.factor

        add_batteries(
            system_id=building_id,
            config_map=battery_config,
            dataclasses=dataclasses,
            components=components,
            input_bus=electricity_carrier_bus_building,
            output_bus=electricity_carrier_bus_building,
            reference_unit_quantity=building_in_cluster,
            configure_config=configure_battery_capacity,
        )
        # Rooftop PV systems.
        add_pv_systems(
            system_id=building_id,
            config_map=pv_system_config,
            dataclasses=dataclasses,
            components=components,
            data_classes_comp=data_classes_comp,
            data=data,
            building_dataclass=building_dataclass,
            electricity_bus=electricity_carrier_bus_building,
            reference_unit_quantity=building_in_cluster,
        )
    # Add all collected oemof components to the energy system.
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
    # Link stratified storage investment capacities to their parent storage.
    for building_id, building_data in dataclasses.items():
        for key, _ in hot_water_tank_config.items():
            for temperature, stratisfied_storage in components[building_id]["hot_water_tank_stratisfied_"+str(key)].items():
                storage_father = es.groups[components[building_id]["hot_water_tank_"+str(key)].label]
                storage_child = stratisfied_storage
                share_stratisfied = dataclasses[building_id]["hot_water_tank_stratisfied_temp_levels_"+str(key)][temperature]

                def equate_variables_rule(share_stratisfied):
                    return model.GenericInvestmentStorageBlock.invest[storage_child, 0] <= model.GenericInvestmentStorageBlock.invest[storage_father, 0] * share_stratisfied

                setattr(model, "eq_"+components[building_id]["hot_water_tank_stratisfied_"+str(key)][temperature].label, po.Constraint(rule=equate_variables_rule(share_stratisfied)))

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


        solve_result = model.solve(solver=SOLVER, solve_kwargs={"tee": True},
                                              cmdline_options={"mipgap": 0.005,
                                                               "threads": SOLVER_THREADS},
        )
        meta_results = solph.processing.meta_results(model)
        results = solph.processing.results(model)
        final_results = {}
        # Grid-level postprocessing.
        final_results[electricity_grid_dataclass.name] = electricity_grid_dataclass.post_process(results,electricity_grid_source,electricity_grid_sink)
        final_results[natural_gas_grid_dataclass.name] = natural_gas_grid_dataclass.post_process(results,natural_gas_grid_source,None)
        final_results[bio_gas_grid_dataclass.name] = bio_gas_grid_dataclass.post_process(results,bio_gas_grid_source,None)

        final_results[hydrogen_grid_dataclass.name] = hydrogen_grid_dataclass.post_process(results, hydrogen_grid_source, None)
        if False:
            final_results[heat_grid_dataclass.name] = heat_grid_dataclass.post_process(results,heat_grid_source,None)

        # Building-level component postprocessing.
        for building_id, building_data in components.items():
            final_results[building_id] = {}
            for key,_ in pv_system_config.items():
                final_results[building_id][dataclasses[building_id]["pv_dataclass_"+str(key)].name] = dataclasses[building_id]["pv_dataclass_"+str(key)].post_process(results,components[building_id]["pv_system_"+str(key)],components[building_id]["pv_system_curtailment_capable_"+str(key)])
            for key,_ in hot_water_tank_config.items():
                final_results[building_id][dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].name] = dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].post_process(results,components[building_id]["hot_water_tank_"+str(key)])
            for key,_ in battery_config.items():
                final_results[building_id][dataclasses[building_id]["battery_dataclass_"+str(key)].name] = dataclasses[building_id]["battery_dataclass_"+str(key)].post_process(results,components[building_id]["battery_"+str(key)])
            for key,_ in gas_heater_config.items():
                final_results[building_id][dataclasses[building_id]["gas_heater_dataclass_"+str(key)].name] = dataclasses[building_id]["gas_heater_dataclass_"+str(key)].post_process(results,
                                                                                                                                                                  components[building_id]["gas_heater_"+str(key)],
                                                                                                                                                                  components[building_id]["gas_heater_converters_"+str(key)],
                                                                                                                                                                  components[building_id]["heat_carrier_bus"],
                                                                                                                                       components[building_id]["gas_carrier_bus_building"])
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
            final_results[building_id][dataclasses[building_id]["building_dataclass"].name] = dataclasses[building_id]["building_dataclass"].post_process(results,components[building_id]["building_component"])
            final_results[building_id]["max_required_heating"] = dataclasses[building_id]["max_required_heating"]
            final_results[building_id][dataclasses[building_id]["electricity_demand_dataclass_building"].name] = dataclasses[building_id]["electricity_demand_dataclass_building"].post_process(results,components[building_id]["electricity_demand"])

            final_results[building_id][dataclasses[building_id]["heat_demand_dataclass"].name] = dataclasses[building_id]["heat_demand_dataclass"].post_process(results,components[building_id]["heat_demand"])
            final_results[building_id]["buildings_in_cluster"] = buildings_in_cluster_to_save.get(building_id, 1)
            final_results[building_id]["buildings_in_cluster_used"] = dataclasses[building_id][
            "building_dataclass"].buildings_in_cluster
        # Aggregate investment and operational CO2 contributions.
        co2_investment = 0
        for building_id in components:

            # For each component, sum up the CO2 contributions to the overall system
            co2_investment += sum(final_results[building_id][dataclasses[building_id]["battery_dataclass_"+str(key)].name]["investment_co2"] for key,_ in battery_config.items())
            co2_investment += sum(
                final_results[building_id][dataclasses[building_id]["chp_dataclass_" + str(key)].name][
                    "investment_co2"] for key, _ in chp_config.items())
            co2_investment += sum(
                final_results[building_id][dataclasses[building_id]["air_heat_pump_dataclass_" + str(key)].name][
                    "investment_co2"] for key, _ in air_heat_pump_config.items())
            co2_investment += sum(final_results[building_id][dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].name]["investment_co2"] for key,_ in hot_water_tank_config.items())
            co2_investment += sum(final_results[building_id][dataclasses[building_id]["gas_heater_dataclass_"+str(key)].name]["investment_co2"] for key,_ in gas_heater_config.items())
            co2_investment += sum(final_results[building_id][dataclasses[building_id]["pv_dataclass_"+str(key)].name]["investment_co2"] for key,_ in pv_system_config.items())
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
            solver_time_s = float(getattr(solve_result.solver, "time", float("nan")))
            return final_results, co2_oemof_model, solver_time_s
        else:
            return final_results, co2_oemof_model, meta_results["solver"]["Wall time"]

    except Exception as e:
        print(e)
        return None, None, None


def run_co2_factor_worker(args):
    group_key, co2_reduction_factor = args
    return _run_co2_factor_for_context(
        group_key,
        co2_reduction_factor,
        _CO2_WORKER_CONTEXT[group_key],
        run_model=run_model,
    )

def _script_base_path():
    return script_base_path(__file__)


def _normalize_result_root(raw_value, base_path):
    return normalize_result_root(raw_value, base_path, label="storage/check")


def _get_result_storage_root():
    return RESULT_STORAGE_ROOT if RESULT_STORAGE_ROOT else _script_base_path()


def _get_result_check_root():
    if RESULT_CHECK_ROOT:
        return RESULT_CHECK_ROOT
    return _get_result_storage_root()


def _prepare_group_context(
    refurbish,
    building_id_in_cluster,
    ueu,
    k_value,
    building_type=None,
    price_scenario_name="ref",
    output_cluster_name=None,
    combined_optimization=False,
    sfh_k_value=None,
    mfh_k_value=None,
):
    base_path = _script_base_path()
    directory_path = os.path.join(base_path, ueu)
    result_storage_root = _get_result_storage_root()
    # Resolve price-scenario settings and output naming for this run group.
    scenario_name = _normalize_price_scenario_name(price_scenario_name)
    scenario_config = _resolve_price_scenario_config(scenario_name)
    if output_cluster_name is None:
        output_cluster_name = _scenario_output_cluster_name(ueu, scenario_name)

    number_of_time_steps = 8760
    # Load selected SFH/MFH cluster representatives for the requested k-values.
    if combined_optimization:
        if isinstance(k_value, (tuple, list)) and len(k_value) == 2:
            sfh_k_value = k_value[0] if sfh_k_value is None else sfh_k_value
            mfh_k_value = k_value[1] if mfh_k_value is None else mfh_k_value
        if sfh_k_value is None or mfh_k_value is None:
            raise ValueError("combined_optimization requires both sfh_k_value and mfh_k_value.")
        sfh_cluster, mfh_cluster, _, _ = _load_clusters_for_k_pair(
            base_path,
            ueu,
            sfh_k_value,
            mfh_k_value,
        )
        k_value_for_output = (sfh_k_value, mfh_k_value)
    else:
        sfh_cluster, mfh_cluster, _, _ = _load_clusters_for_k(base_path, ueu, k_value)
        k_value_for_output = k_value
    if sfh_cluster.empty and mfh_cluster.empty:
        raise ValueError(f"No cluster files found for cluster='{ueu}', k={k_value}.")

    combined_frames = [df for df in (sfh_cluster, mfh_cluster) if not df.empty]
    combined_cluster = pd.concat(combined_frames, ignore_index=True)

    ev = EV_MODE
    if combined_optimization:
        if building_id_in_cluster is None:
            building_id_in_cluster = (
                f"combined_sfh_{_k_to_folder_token(sfh_k_value)}"
                f"_mfh_{_k_to_folder_token(mfh_k_value)}"
            )
        output_building_type = "COMBINED"
    else:
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
        k_value_for_output,
        output_building_type,
        refurbish,
        ev,
        building_id_in_cluster,
    )
    output_dir = os.path.dirname(file_path_base)
    os.makedirs(output_dir, exist_ok=True)

    # Prepare weather, demand, and component input tables for optimization.
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
    heat_demand_worst_case = {} if combined_optimization else None

    # Convert building input rows into model-ready demand and component objects.
    if combined_optimization:
        for _, building_row in sfh_cluster.iterrows():
            data, data_classes_comp, heat_demand_worst_case_building = process_cluster(
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
                price_scenario_name=scenario_name,
            )
            heat_demand_worst_case[building_row["building_id"]] = heat_demand_worst_case_building

        for _, building_row in mfh_cluster.iterrows():
            data, data_classes_comp, heat_demand_worst_case_building = process_cluster(
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
                price_scenario_name=scenario_name,
            )
            heat_demand_worst_case[building_row["building_id"]] = heat_demand_worst_case_building

        if not heat_demand_worst_case:
            raise ValueError(
                f"No buildings available for combined optimization in cluster '{ueu}' "
                f"(sfh_k={sfh_k_value}, mfh_k={mfh_k_value})."
            )
    else:
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
                    price_scenario_name=scenario_name,
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
                    price_scenario_name=scenario_name,
                )

        if heat_demand_worst_case is None:
            raise ValueError(f"No matching building_id '{building_id_in_cluster}' in cluster '{ueu}'.")

    typical_periods = 30
    hours_per_period = 24
    # Aggregate the annual time series to representative periods for the MILP.
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

    # Run the unconstrained reference case used to scale CO2 and peak targets.
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
        combined_optimization=combined_optimization,
    )
    if final_results_ref is None:
        raise RuntimeError(
            f"Reference scenario failed for cluster={ueu}, building={building_id_in_cluster}, "
            f"refurbish={refurbish}, price_scenario={scenario_name}."
        )

    co2_reduction_factors = list(DEFAULT_CO2_REDUCTION_FACTORS)
    peak_reduction_factors = list(DEFAULT_PEAK_REDUCTION_FACTORS)

    # Store all immutable inputs needed by CO2-factor worker processes.
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
        "combined_optimization": combined_optimization,
    }

    return {
        "co2_reduction_factors": co2_reduction_factors,
        "worker_context": worker_context,
    }

def run_main(
    refurbish,
    building_id_in_cluster,
    ueu,
    k_value,
    building_type=None,
    price_scenario_name="ref",
    combined_optimization=False,
    sfh_k_value=None,
    mfh_k_value=None,
):
    output_cluster_name = _scenario_output_cluster_name(ueu, price_scenario_name)
    prepared = _prepare_group_context(
        refurbish,
        building_id_in_cluster,
        ueu,
        k_value,
        building_type=building_type,
        price_scenario_name=price_scenario_name,
        output_cluster_name=output_cluster_name,
        combined_optimization=combined_optimization,
        sfh_k_value=sfh_k_value,
        mfh_k_value=mfh_k_value,
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
    combined_optimization=False,
):
    return _run_cluster_refurbish_co2_parallel(
        cluster_name=cluster_name,
        processes=processes,
        base_path=_script_base_path(),
        result_check_root=_get_result_check_root(),
        selected_k_values=selected_k_values,
        selected_k_values_sfh=selected_k_values_sfh,
        selected_k_values_mfh=selected_k_values_mfh,
        price_scenarios_to_run=price_scenarios_to_run,
        combined_optimization=combined_optimization,
        default_price_scenarios=DEFAULT_PRICE_SCENARIOS,
        default_co2_reduction_factors=DEFAULT_CO2_REDUCTION_FACTORS,
        refurbishment=refurbishment,
        ev_mode=EV_MODE,
        prepare_group_context=_prepare_group_context,
        set_worker_context=_set_co2_worker_context,
        clear_worker_context=_CO2_WORKER_CONTEXT.clear,
        worker=run_co2_factor_worker,
    )


DEFAULT_REFURBISHMENT = [
    "no_refurbishment",
    "usual_refurbishment",
    "advanced_refurbishment",
    "GEG_standard",
]
DEFAULT_CLUSTER_LIST = [
    "processed_bds_in_DENI03403000SEC5658",
]
DEFAULT_K_VALUES_TO_OPTIMIZE_SFH = [6]
DEFAULT_K_VALUES_TO_OPTIMIZE_MFH = [1]

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
        f"combined_optimization={args.combined_optimization} "
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
            combined_optimization=args.combined_optimization,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run decentralized building-level optimization cases for selected clusters and scenarios."
    )
    parser.add_argument("--host-name", type=str, default="unknown", help="Optional host label used in log output.")
    parser.add_argument(
        "--run-mode",
        type=str,
        default="cli",
        choices=["cli", "legacy_batches"],
        help="Use 'cli' for selected arguments or 'legacy_batches' for predefined k-value batches.",
    )
    parser.add_argument(
        "--workers",
        type=str,
        default="auto",
        help="Number of parallel CO2-factor worker processes; use an integer, False, or auto.",
    )
    parser.add_argument("--serial", action="store_true", help="Run selected cluster/refurbishment cases sequentially.")
    parser.add_argument("--solver", type=str, default=DEFAULT_SOLVER, help="MILP solver backend, e.g. scip, gurobi, cbc.")
    parser.add_argument("--solver-threads", type=int, default=DEFAULT_SOLVER_THREADS, help="Solver threads per optimization job.")
    parser.add_argument(
        "--result-check-root",
        type=str,
        default=None,
        help="Root used to check for existing result files before running a case; ftp:// URLs use their path part.",
    )
    parser.add_argument(
        "--result-storage-root",
        type=str,
        default=None,
        help="Root directory where new decentralized result pickle files are written; ftp:// URLs use their path part.",
    )
    parser.add_argument(
        "--sfh-k",
        type=str,
        default=",".join(str(x) for x in DEFAULT_K_VALUES_TO_OPTIMIZE_SFH),
        help="Comma-separated SFH cluster k-values to run, e.g. reference,1,2,4.",
    )
    parser.add_argument(
        "--mfh-k",
        type=str,
        default=",".join(str(x) for x in DEFAULT_K_VALUES_TO_OPTIMIZE_MFH),
        help="Comma-separated MFH cluster k-values to run, e.g. reference,1,2,3.",
    )
    parser.add_argument(
        "--combined-optimization",
        action="store_true",
        help=(
            "Optimize SFH+MFH representatives jointly in one combined_cluster per (sfh_k, mfh_k) pair. "
            "If enabled, all selected buildings of the two k-clusters are added to one model run."
        ),
    )
    parser.add_argument(
        "--ueu-cases",
        type=str,
        default=",".join(DEFAULT_CLUSTER_LIST),
        help="Comma-separated UEU cluster folder names to process; an optional ':value' suffix is ignored.",
    )
    parser.add_argument(
        "--refurbishments",
        type=str,
        default=",".join(DEFAULT_REFURBISHMENT),
        help="Comma-separated refurbishment strategies to evaluate for each selected building representative.",
    )
    parser.add_argument(
        "--price-scenarios",
        type=str,
        default=",".join(DEFAULT_PRICE_SCENARIOS),
        help=(
            "Comma-separated price scenarios. Supported: "
            "yes_ev,yes_ev2,"
            "yes_ev_total,yes_ev_half,"
            "ref,electricity_minus20,electricity_plus20,electricity_minus40,electricity_plus40,"
            "electricity_feed_in_minus20,electricity_feed_in_plus20,electricity_feed_in_minus40,electricity_feed_in_plus40,"
            "gas_minus20,gas_plus20,gas_minus40,gas_plus40,"
            "hydrogen_minus20,hydrogen_plus20,hydrogen_minus40,hydrogen_plus40 or 'all'."
        ),
    )
    parser.add_argument(
        "--ev",
        type=str,
        default=DEFAULT_EV_MODE,
        choices=["no_EV", "yes_EV", "yes_EV2", "yes_EV_total", "yes_EV_half"],
        help=(
            "EV scenario mode: no_EV, yes_EV, yes_EV2, yes_EV_total, yes_EV_half. "
            "yes_EV_total assigns 1 EV to every household, yes_EV_half assigns EV to ~50% households evenly."
        ),
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
