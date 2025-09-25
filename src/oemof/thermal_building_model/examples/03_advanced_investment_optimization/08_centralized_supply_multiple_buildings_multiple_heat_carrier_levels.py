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
from oemof.thermal_building_model.oemof_facades.technologies.heat_grid import HeatGridInvestment
from oemof.thermal_building_model.input.economics.operation_grid_economics import natural_gas_grid_config, bio_gas_grid_config

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
from oemof.thermal_building_model.input.economics.investment_components_heat_grid import battery_config,hot_water_tank_config,air_heat_pump_config,gas_heater_config,pv_system_config,chp_config

from oemof.thermal_building_model.tabula.tabula_reader import Building
import pprint as pp
import geopandas as gpd
import tsam.timeseriesaggregation as tsam

import pandas as pd
#  create solver
def run_model(co2_new,peak_new,data,aggregation1,t1_agg,data_classes_comp,combined_cluster,heat_grid_temperature,cluster_occurence):
    solver = "gurobi"
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
    dataclasses = {}
    components = {}
    building_id="heat_grid"

    dataclasses[building_id]={}
    components[building_id]={}



    if peak_new is False or None:
        electricity_grid_dataclass = ElectricityGrid()
    else:
        electricity_grid_dataclass = ElectricityGrid(max_peak_from_grid=peak_new)

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
    natural_gas_grid_dataclass = GasGrid(operation_grid=natural_gas_grid_config_grid,
                                 name="NaturalGas")
    natural_gas_grid_bus_from_grid = natural_gas_grid_dataclass.get_bus_from_grid()
    natural_gas_grid_source = natural_gas_grid_dataclass.create_source()

    bio_gas_grid_config_grid = copy.deepcopy(bio_gas_grid_config)
    bio_gas_grid_dataclass = GasGrid(operation_grid=bio_gas_grid_config_grid,
                                 name="BioGas")
    bio_gas_grid_bus_from_grid = bio_gas_grid_dataclass.get_bus_from_grid()
    bio_gas_grid_source = bio_gas_grid_dataclass.create_source()

    gas_carrier_dataclass = GasCarrier()
    gas_bus = gas_carrier_dataclass.get_bus()
    connect_buses(input=natural_gas_grid_bus_from_grid, target=gas_bus)
    connect_buses(input=bio_gas_grid_bus_from_grid, target=gas_bus)

    gas = [natural_gas_grid_bus_from_grid,bio_gas_grid_bus_from_grid,bio_gas_grid_source,natural_gas_grid_source,gas_bus]
    es.add(*gas)

    hydrogen_grid_dataclass = HydrogenGrid()
    hydrogen_grid_bus_from_grid = hydrogen_grid_dataclass.get_bus_from_grid()
    hydrogen_grid_source = hydrogen_grid_dataclass.create_source()

    hydrogen_carrier_dataclass = HydrogenCarrier()
    hydrogen_bus = hydrogen_carrier_dataclass.get_bus()
    connect_buses(input=hydrogen_grid_bus_from_grid, target=hydrogen_bus)


    hydrogen = [hydrogen_grid_bus_from_grid,hydrogen_grid_source,hydrogen_bus]
    es.add(*hydrogen)
    component_per_building = {}

    if True:
        heat_carrier_temperature_levels = [40,50]
        if heat_grid_temperature == 60:
            heat_carrier_temperature_levels.extend([heat_grid_temperature, 80])
        elif heat_grid_temperature == 50:
            heat_carrier_temperature_levels.extend([80])
        else:
            heat_carrier_temperature_levels.extend([heat_grid_temperature, 80])
    heat_carrier_dataclass = HeatCarrier(name="h_carrier_" + str(building_id),
                                         levels=heat_carrier_temperature_levels)
    heat_carrier_dataclass.connect_buses_decreasing_levels()
    heat_carrier_bus = heat_carrier_dataclass.get_bus()

    dataclasses[building_id]["heat_carrier_dataclass"] = heat_carrier_dataclass

    components[building_id]["heat_carrier_bus"] = heat_carrier_bus

    for key, config in hot_water_tank_config.items():
        hot_water_tank_config_building = copy.deepcopy(config)

        hot_water_tank_input_bus = solph.buses.Bus(label=f"tank_input_bus_{building_id}_{key}")
        hot_water_tank_output_bus = solph.buses.Bus(label=f"tank_output_bus_{building_id}_{key}")
        if False:
            hot_water_tank_dataclass = HotWaterTank(
                name=f"heat_storage_{building_id}_{key}",
                investment=True,
                temperature_buses=heat_carrier_dataclass.get_bus(),
                max_temperature=80,
                min_temperature=(40 + heat_grid_temperature) / 2,
                investment_component=hot_water_tank_config_building,
                input_bus=heat_carrier_dataclass.get_bus()[80],
                output_bus=heat_carrier_bus[80],
            )
        else:
            hot_water_tank_dataclass = HotWaterTank(
                name=f"heat_storage_{building_id}_{key}",
                investment=True,
                temperature_buses=heat_carrier_dataclass.get_bus(),
                max_temperature=80,
                min_temperature=40,
                investment_component=hot_water_tank_config_building,
                input_bus=hot_water_tank_input_bus,
                output_bus=hot_water_tank_output_bus,
            )
        hot_water_tank = hot_water_tank_dataclass.create_storage()

        dataclasses[building_id]["hot_water_tank_dataclass_" + str(key)] = hot_water_tank_dataclass
        components[building_id]["hot_water_tank_" + str(key)] = hot_water_tank

        if True:
            hot_water_tank_stratisfied_temp_levels_dict = hot_water_tank_dataclass.get_stratified_storage_temperature_levels()
            hot_water_tank_stratisfied = hot_water_tank_dataclass.create_stratified_storage(
                hot_water_tank_stratisfied_temp_levels_dict, heat_carrier_bus)

            dataclasses[building_id][
                "hot_water_tank_stratisfied_temp_levels_" + str(key)] = hot_water_tank_stratisfied_temp_levels_dict
            components[building_id]["hot_water_tank_stratisfied_" + str(key)] = hot_water_tank_stratisfied
            components[building_id]["hot_water_tank_input_bus_" + str(key)] = hot_water_tank_input_bus
            components[building_id]["hot_water_tank_output_bus_" + str(key)] = hot_water_tank_output_bus

    for key, config in air_heat_pump_config.items():
        air_heat_pump_config_building =  copy.deepcopy(config)

        air_heat_pump_dataclass = AirHeatPump(heat_carrier_bus= heat_carrier_dataclass.get_bus(),
                                              investment=True,
                                              name="hp_"+str(building_id)+"_"+str(key),
                                              air_temperature=data["air_temperature"],
                                              investment_component=air_heat_pump_config_building)


        air_heat_pump_bus = air_heat_pump_dataclass.get_bus()
        air_heat_pump= air_heat_pump_dataclass.create_source()
        new_key = int((80 + heat_grid_temperature) / 2)
        air_heat_pump_converters= air_heat_pump_dataclass.create_converters(heat_pump_bus = air_heat_pump_bus,
                                                                         electricity_bus = electricity_carrier_bus,
                                                                         heat_carrier_bus= heat_carrier_bus)



        dataclasses[building_id]["air_heat_pump_dataclass_"+str(key)] = air_heat_pump_dataclass
        components[building_id]["air_heat_pump_converters_"+str(key)] = air_heat_pump_converters
        components[building_id]["air_heat_pump_"+str(key)] = air_heat_pump
        components[building_id]["air_heat_pump_bus_"+str(key)] = air_heat_pump_bus

    if True:
        for key, config in gas_heater_config.items():
            gas_heater_config_building = copy.deepcopy(config)


            gas_heater_dataclass = GasHeater(investment=True,
                                             name="gas_heater_"+str(building_id)+"_"+str(key),
                                             investment_component=gas_heater_config_building)
            gas_heater_bus = gas_heater_dataclass.get_bus()
            gas_heater= gas_heater_dataclass.create_source()
            gas_heater_converters= gas_heater_dataclass.create_converters(gas_heater_bus = gas_heater_bus,
                                                                          gas_bus = gas_bus,
                                                                          heat_carrier_bus=heat_carrier_bus)

            dataclasses[building_id]["gas_heater_dataclass_"+str(key)] = gas_heater_dataclass
            components[building_id]["gas_heater_converters_"+str(key)] = gas_heater_converters
            components[building_id]["gas_heater_bus_"+str(key)] = gas_heater_bus
            components[building_id]["gas_heater_"+str(key)] = gas_heater
    if True:
        for key, config in chp_config.items():
            chp_config_building = copy.deepcopy(config)

            chp_dataclass = CHP(investment=True,
                                name="chp_"+str(building_id)+"_"+str(key),
                                investment_component=chp_config_building,
                                )
            chp_bus = chp_dataclass.get_bus()
            chp= chp_dataclass.create_source()
            chp_converters= chp_dataclass.create_converters(chp_bus = chp_bus,
                                                            gas_bus = hydrogen_bus,
                                                            heat_carrier_bus=heat_carrier_bus
                                                            ,
                                                            electricity_bus = electricity_carrier_bus
                                                            )

            dataclasses[building_id]["chp_dataclass_"+str(key)] = chp_dataclass
            components[building_id]["chp_converters_"+str(key)] = chp_converters
            components[building_id]["chp_bus_"+str(key)] = chp_bus
            components[building_id]["chp_"+str(key)] = chp

    for key, config in battery_config.items():
        battery_config_building =  copy.deepcopy(config)
        battery_dataclass = Battery(investment=True,
                                    name="battery_"+str(building_id)+"_"+str(key),
                                    input_bus = electricity_carrier_bus,
                                    output_bus = electricity_carrier_bus,
                                    investment_component=battery_config_building)
        battery = battery_dataclass.create_storage()

        dataclasses[building_id]["battery_dataclass_"+str(key)] = battery_dataclass
        components[building_id]["battery_"+str(key)] = battery

    total_heat_demand_year=None
    heat_transfer_station_max_kW = []
    for index, row in combined_cluster.iterrows():

        building_id = row['building_id']
        buildings_in_cluster = row['buildings_in_cluster']
        total_heat_demand_year_per_building = (data["ww_demand_" + str(building_id)]+ data["building_" + str(building_id)]) * buildings_in_cluster
        heat_transfer_station_max_kW.append((max(total_heat_demand_year_per_building),buildings_in_cluster))

        if total_heat_demand_year is None:
            total_heat_demand_year =  total_heat_demand_year_per_building
        else:
            total_heat_demand_year = total_heat_demand_year + total_heat_demand_year_per_building
    demand = 0

    fictional_heat_grid_demand= data["ww_demand_" + str(building_id)]
    fictional_heat_grid_demand[:]= 1
    total_heat_demand_year_sum=0
    for cluster, count in cluster_occurence.items():
        # Hole den entsprechenden WW-Demand aus 'data' für das Cluster (erste Zahl in cluster_order entspricht dem Cluster)
        demand = demand + fictional_heat_grid_demand[cluster].sum() * count
        total_heat_demand_year_sum  += total_heat_demand_year[cluster].sum() * count
    heat_grid_investment = HeatGridInvestment(name="heat_grid_investment",
                                    heat_transfer_station_max_kW =heat_transfer_station_max_kW,
                                    pipe_length_in_meter = 937.00,
                                    peak_load_in_kw = max(total_heat_demand_year),
                                    flow_temperature = heat_grid_temperature,
                                    total_heat_demand = total_heat_demand_year_sum,
                                    fictional_demand = demand)
    heat_grid_investment.tsam_total_amount = demand
    heat_grid_investment.value_list = fictional_heat_grid_demand
    heat_grid_investment_bus = heat_grid_investment.get_bus()
    heat_grid_investment_sink=  heat_grid_investment.create_sink(heat_grid_investment_bus)
    heat_grid_investment_source = heat_grid_investment.create_source(heat_grid_investment_bus)

    heat_grid_loss=heat_grid_investment.calculate_heat_grid_loss_for_flow_temperature(heat_grid_temperature)
    dataclasses["heat_grid"]["heat_grid_investment"] =heat_grid_investment

    components["heat_grid"]["heat_grid_investment_bus"] = heat_grid_investment_bus
    components["heat_grid"]["heat_grid_investment_sink"] = heat_grid_investment_sink
    components["heat_grid"]["heat_grid_investment_source"] = heat_grid_investment_source
    for index, row in combined_cluster.iterrows():


        building_id = row['building_id']
        print(building_id)
        dataclasses[building_id]={}
        components[building_id]={}
        buildings_in_cluster =row['buildings_in_cluster']
        building_dataclass = copy.deepcopy(data_classes_comp.loc["building", building_id])

        temp_heating_demand_building = building_dataclass.level_heating_demand
        heat_carrier_temperature_levels_building = [50, heat_grid_temperature]
        heat_carrier_dataclass_building = HeatCarrier(name="h_carrier_" + str(building_id),
                                             levels=heat_carrier_temperature_levels_building)
        heat_carrier_bus_building = heat_carrier_dataclass_building.get_bus()
        heat_50_from_converter_building = Converter(label="conv_h_from_grid_50_"+str(building_id),
                                              inputs={heat_carrier_bus[50]: solph.flows.Flow()},
                                              outputs={heat_carrier_bus_building[50]: solph.flows.Flow()},
                                              conversion_factors={heat_carrier_bus_building[50]: 1/(buildings_in_cluster)*heat_grid_loss})
        heat_heating_demand_from_converter_building = Converter(label="conv_h_from_grid_heatdemand_"+str(building_id),
                                              inputs={heat_carrier_bus[heat_grid_temperature]: solph.flows.Flow()},
                                              outputs={heat_carrier_bus_building[heat_grid_temperature]: solph.flows.Flow()},
                                              conversion_factors={heat_carrier_bus_building[heat_grid_temperature]: 1/(buildings_in_cluster)*heat_grid_loss})

        heat_demand_dataclass = data_classes_comp.loc["heat_demand", building_id]
        heat_demand_dataclass.value_list = data["ww_demand_"+str(building_id)]
        heat_demand_dataclass.level = heat_demand_dataclass.demand_temperature
        heat_demand_dataclass.bus = heat_carrier_bus_building[heat_demand_dataclass.demand_temperature]

        heat_demand = heat_demand_dataclass.create_demand()

        dataclasses[building_id]["heat_carrier_dataclass"] = heat_carrier_dataclass_building
        dataclasses[building_id]["heat_demand_dataclass"] = heat_demand_dataclass

        components[building_id]["heat_demand"] = heat_demand
        components[building_id]["heat_carrier_bus"] = heat_carrier_bus_building
        components[building_id]["heat_50_from_converter_building"] = heat_50_from_converter_building
        components[building_id]["heat_heating_demand_from_converter_building"] = heat_heating_demand_from_converter_building

        building_dataclass.value_list = data["building_"+str(building_id)]
        demand = 0
        for cluster, count in cluster_occurence.items():
            # Hole den entsprechenden WW-Demand aus 'data' für das Cluster (erste Zahl in cluster_order entspricht dem Cluster)
            demand = demand + data["building_" + str(building_id)][cluster].sum() * count

        building_dataclass.tsam_total_amount = demand
        building_dataclass.set_number_of_buildings_in_cluster(buildings_in_cluster)
        building_dataclass.bus=heat_carrier_bus_building[building_dataclass.level_heating_demand]

        building_component = building_dataclass.create_demand()

        dataclasses[building_id]["building_dataclass"] = building_dataclass
        components[building_id]["building_component"] = building_component
        max(data["ww_demand_" + str(building_id)] + data["building_" + str(building_id)])

        electricity_carrier_dataclass_building = ElectricityCarrier(name="e_carrier_"+str(building_id))
        electricity_carrier_bus_building = electricity_carrier_dataclass_building.get_bus()
        grid_into_converter_building = Converter(label="conv_e_into_grid_"+str(building_id),
                                              inputs={electricity_carrier_bus_building: solph.flows.Flow()},
                                              outputs={electricity_carrier_bus: solph.flows.Flow()},
                                              conversion_factors={electricity_carrier_bus_building: 1/buildings_in_cluster })
        grid_from_converter_building = Converter(label="conv_e_from_grid_"+str(building_id),
                                              inputs={electricity_carrier_bus: solph.flows.Flow()},
                                              outputs={electricity_carrier_bus_building: solph.flows.Flow()},
                                              conversion_factors={electricity_carrier_bus_building: 1/ buildings_in_cluster})

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

        for key, config in pv_system_config.items():
            pv_dataclass = copy.deepcopy(data_classes_comp[building_id]["pv_system"][key])
            pv_dataclass_config_building = copy.deepcopy(config)
            pv_dataclass_config_building.set_reference_unit_quantity(reference_unit_quantity=buildings_in_cluster)

            pv_dataclass.investment_component=pv_dataclass_config_building

            pv_dataclass.value_list = data["pv_system_" + str(building_id)+"_"+str(key)]

            pv_dataclass.update_maximum_investment_pv_capacity_based_on_area(area = building_dataclass.get_roof_area_for_pv())
            pv_system = pv_dataclass.create_source(output_bus = electricity_carrier_bus_building)

            dataclasses[building_id]["pv_dataclass_"+str(key)] = pv_dataclass
            components[building_id]["pv_system_"+str(key)] = pv_system

    for building_id, building_data in components.items():
        # Ensure we're processing the components for the current building
        for oemof_comp, comp_value in building_data.items():
            # Check if the component is a list (which it should not be, based on the structure)
            if isinstance(comp_value, list):
                for item in comp_value:
                    es.add(item)
                    print(item)
                    # Process each component in the list
            # Check if the component is a dictionary, meaning it has nested components
            elif isinstance(comp_value, dict):
                # If it's a dictionary, iterate over its key-value pairs
                for key, value in comp_value.items():
                    print(value)
                    es.add(value)
            else:
                # Otherwise, just add the component directly
                es.add(comp_value)
                print(comp_value)
    model = solph.Model(es)

    if True:
        for building_id, building_data in dataclasses.items():
            if building_id=="heat_grid":
                for key, config in hot_water_tank_config.items():
                    for temperature, stratisfied_storage in components[building_id]["hot_water_tank_stratisfied_"+str(key)].items():
                        storage_father = es.groups[components[building_id]["hot_water_tank_"+str(key)].label]
                        storage_child = stratisfied_storage
                        share_stratisfied = dataclasses[building_id]["hot_water_tank_stratisfied_temp_levels_"+str(key)][temperature]

                        def equate_variables_rule(share_stratisfied):
                            return model.GenericInvestmentStorageBlock.invest[storage_child, 0]  <= model.GenericInvestmentStorageBlock.invest[storage_father, 0]* share_stratisfied

                        setattr(model, "eq"+components[building_id]["hot_water_tank_stratisfied_"+str(key)][temperature].label, po.Constraint(rule=equate_variables_rule(share_stratisfied)))
    if len(pv_system_config) > 1:
        print("PV SYSTEM ÜBERARTBEITEN SODASS DER CONSTRAINT FÜR JEDES GEBÄUDE GEMACHT WIRD IN BUILDING ID")
        for key, config in pv_system_config.items():
            maximum_pv_capacity = dataclasses[building_id]["pv_dataclass_" + str(key)].investment_component.maximum_capacity
            maximum_key = max(pv_system_config)
            def equate_variables_rule(maximum_pv_capacity, maximum_key):
                for ke in range(maximum_key):
                    key = int(ke +1)
                    return model.InvestmentFlowBlock.invest[es.groups[components[building_id]["pv_system_"+str(key)].label],
                    components[building_id]["electricity_carrier_bus_building"],
                    0] + \
                    model.InvestmentFlowBlock.invest[es.groups[components[building_id]["pv_system_"+str(key)].label],
                    components[building_id]["electricity_carrier_bus_building"],
                    0] <= maximum_pv_capacity

            setattr(model, "eq"+components[building_id]["pv_system_"+str(key)].label, po.Constraint(rule=equate_variables_rule(int(maximum_pv_capacity),int(maximum_key))))

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


        model.solve(solver=solver, solve_kwargs={"tee": True},
                                              cmdline_options={"mipgap": 0.005}
        )
        meta_results = solph.processing.meta_results(model)
        results = solph.processing.results(model)
        final_results = {}
        final_results[electricity_grid_dataclass.name] = electricity_grid_dataclass.post_process(results,electricity_grid_source,electricity_grid_sink
                                                )
        final_results[natural_gas_grid_dataclass.name] = natural_gas_grid_dataclass.post_process(results,natural_gas_grid_source,None)
        final_results[bio_gas_grid_dataclass.name] = bio_gas_grid_dataclass.post_process(results, bio_gas_grid_source, None)
        final_results[hydrogen_grid_dataclass.name] = hydrogen_grid_dataclass.post_process(results, hydrogen_grid_source, None)
        if False:
            final_results[heat_grid_dataclass.name] = heat_grid_dataclass.post_process(results,heat_grid_source,None)

        for building_id, building_data in components.items():
            final_results[building_id] = {}
            if building_id=="heat_grid":
                final_results["heat_grid"]["heat_grid_investment"]=dataclasses["heat_grid"]["heat_grid_investment"].post_process()
                final_results["heat_grid"]["heat_grid_investment"]["max_required_demand"]=dataclasses["heat_grid"]["heat_grid_investment"].peak_load_in_kw
                for key,_ in hot_water_tank_config.items():

                    final_results[building_id][dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].name] = dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].post_process(results,components[building_id]["hot_water_tank_"+str(key)])
                for key,_ in battery_config.items():
                    final_results[building_id][dataclasses[building_id]["battery_dataclass_"+str(key)].name] = dataclasses[building_id]["battery_dataclass_"+str(key)].post_process(results,components[building_id]["battery_"+str(key)])
                for key,_ in gas_heater_config.items():
                    final_results[building_id][dataclasses[building_id]["gas_heater_dataclass_"+str(key)].name] = dataclasses[building_id]["gas_heater_dataclass_"+str(key)].post_process(results,
                                                                                                                                                                      components[building_id]["gas_heater_"+str(key)],
                                                                                                                                                                      components[building_id]["gas_heater_converters_"+str(key)],
                                                                                                                                                                      components[building_id]["heat_carrier_bus"],
                                                                                                                                                                      gas_bus)
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
                                                                                              hydrogen_bus)
                for key,_ in air_heat_pump_config.items():
                    final_results[building_id][dataclasses[building_id]["air_heat_pump_dataclass_"+str(key)].name] = dataclasses[building_id]["air_heat_pump_dataclass_"+str(key)].post_process(results,
                                                                                                                                                                            components[building_id]["air_heat_pump_"+str(key)],
                                                                                                                                                                            components[building_id]["air_heat_pump_converters_"+str(key)],
                                                                                                                                                                            components[building_id]["heat_carrier_bus"],
                                                                                                                                                                            electricity_carrier_bus)
            else:
                final_results[building_id][dataclasses[building_id]["building_dataclass"].name] = dataclasses[building_id]["building_dataclass"].post_process(results,components[building_id]["building_component"])
                final_results[building_id]["refurbishment_status"] = dataclasses[building_id]["building_dataclass"].refurbishment_status

                final_results[building_id][dataclasses[building_id]["electricity_demand_dataclass_building"].name] = dataclasses[building_id]["electricity_demand_dataclass_building"].post_process(results,components[building_id]["electricity_demand"])

                final_results[building_id][dataclasses[building_id]["heat_demand_dataclass"].name] = dataclasses[building_id]["heat_demand_dataclass"].post_process(results,components[building_id]["heat_demand"])
                final_results[building_id]["buildings_in_cluster"] = dataclasses[building_id]["building_dataclass"].buildings_in_cluster
                for key,_ in pv_system_config.items():
                    final_results[building_id][dataclasses[building_id]["pv_dataclass_"+str(key)].name] = dataclasses[building_id]["pv_dataclass_"+str(key)].post_process(results,components[building_id]["pv_system_"+str(key)])

        co2_investment = 0
        for building_id in components:
            if building_id == "heat_grid":
                # For each component, sum up the CO2 contributions to the overall system
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["battery_dataclass_"+str(key)].name]["investment_co2"] for key,_ in battery_config.items())
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].name]["investment_co2"] for key,_ in hot_water_tank_config.items())
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["gas_heater_dataclass_"+str(key)].name]["investment_co2"] for key,_ in gas_heater_config.items())
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["chp_dataclass_"+str(key)].name]["investment_co2"] for key,_ in chp_config.items())
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["air_heat_pump_dataclass_"+str(key)].name]["investment_co2"] for key,_ in air_heat_pump_config.items())
                co2_investment += final_results["heat_grid"]["heat_grid_investment"]["investment_co2"]

            else:
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
        return final_results, co2_oemof_model, meta_results["solver"]["Wall time"]
    except Exception as e:
        print(e)
        return None, None, None


def process_cluster(building_row, building_type, epw_path, directory_path, data, number_of_time_steps,data_classes_comp,ev,time_index,heat_grid_temperature):

        building_id = building_row['building_id']
        tabula_year_class = building_row['tabula_year_class']
        building_floor_area = building_row['net_floor_area']
        number_of_occupants = building_row['number_of_residents']
        number_of_households = building_row['number_of_apartments']
        number_of_buildings_in_cluster = building_row['buildings_in_cluster']

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

        electricity_cols = [col for col in demand.columns if col.startswith("Electricity_")]
        demand_electricity = (demand[electricity_cols].sum(axis=1) * 1000).tolist()
        warm_water_cols = [col for col in demand.columns if col.startswith("Warm Water_")]
        demand_warm_water = demand[warm_water_cols].sum(axis=1)

        # Datenklassen
        electricity_demand = ElectricityDemand(name=f"e_demand_{building_id}", value_list=demand_electricity)
        heat_demand = WarmWater(name=f"ww_demand_{building_id}", value_list=demand_warm_water, level=40)
        buildung_dict={}
        if heat_grid_temperature==40:
            building = ThermalBuilding(
                    name=f"building_{building_id}",
                    floor_area=building_floor_area,
                    number_of_occupants=number_of_occupants,
                    number_of_household=number_of_households,
                    country="DE",
                    construction_year=year_of_construction,
                    class_building="average",
                    building_type=building_type,
                    refurbishment_status="advanced_refurbishment",
                    heat_level_calculation=True,
                    time_index=time_index,
                )
            if building.level_heating_demand >40:
                building.capex_annuity = building.capex_annuity * 1.05
                building.co2_cost = building.co2_cost * 1.05
                building.level_heating_demand = 40
        else:
            for refurbishment in ["no_refurbishment","usual_refurbishment","advanced_refurbishment","GEG_standard"]:
                buildung_dict[refurbishment] = ThermalBuilding(
                    name=f"building_{building_id}",
                    floor_area=building_floor_area,
                    number_of_occupants=number_of_occupants,
                    number_of_household=number_of_households,
                    country="DE",
                    construction_year=year_of_construction,
                    class_building="average",
                    building_type=building_type,
                    refurbishment_status=refurbishment,
                    heat_level_calculation=True,
                    time_index=time_index,
                )
            matching_buildings = {key: value for key, value in buildung_dict.items() if
                                  value.level_heating_demand <= heat_grid_temperature}
            print(building_id)
            print(heat_grid_temperature)
            assert matching_buildings, "Fehler: Es wurden keine Gebäudej gefunden, die den gewünschten Heizbedarf entsprechen."

            min_capex_building = min(matching_buildings, key=lambda x: matching_buildings[x].capex_annuity)
            building = matching_buildings[min_capex_building]

        # PV-Ertrag pro Watt
        pv_yield_per_wp = simulate_pv_yield(
            pv_nominal_power_in_watt=1,
            tilt=building_row['avg_roof_pitch_angle'],
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
            pv.update_maximum_investment_pv_capacity_based_on_area(building.get_roof_area_for_pv())
            data[pv.name] = pv.value_list
            dict_pv_systems[key] = pv


        # Spalten hinzufügen
        data[electricity_demand.name] = electricity_demand.value_list
        data[heat_demand.name] = heat_demand.value_list
        data[building.name] = building.value_list

        data_classes_comp[building_id] = {"electricity_demand":electricity_demand,
                                          "pv_system":dict_pv_systems,
                                          "building":building,
                                          "heat_demand":heat_demand}
        return data, data_classes_comp



def run_main(heat_grid_temperature):
    base_path = os.path.dirname(os.path.abspath(__file__))
    ueu = "processed_bds_in_DENI03403000SEC5658"
    directory_path =os.path.join(base_path, ueu)
    number_of_time_steps = 8760
    sfh_cluster_path = os.path.join(base_path, ueu, 'sfh_cluster.pkl')
    with open(sfh_cluster_path, 'rb') as f:
        sfh_cluster = pickle.load(f)
    mfh_cluster_path = os.path.join(base_path, ueu, 'mfh_cluster.pkl')
    with open(mfh_cluster_path, 'rb') as f:
        mfh_cluster = pickle.load(f)
    combined_cluster = pd.concat([sfh_cluster,mfh_cluster])
    results_loop_to_save = {}
    ev = "no_EV"
    if True:

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
        if True:
            for index, building_row in sfh_cluster.iterrows():

                data,data_classes_comp = process_cluster(
                    building_row=building_row,
                    building_type="SFH",
                    epw_path=epw_path,
                    directory_path=directory_path,
                    data=data,
                    number_of_time_steps=number_of_time_steps,
                    data_classes_comp = data_classes_comp,
                    ev=ev,
                    time_index=date_time_index,
                    heat_grid_temperature=heat_grid_temperature
                )
        if True:
            for index, building_row in mfh_cluster.iterrows():

                data,data_classes_comp = process_cluster(
                    building_row=building_row,
                    building_type="MFH",
                    epw_path=epw_path,
                    directory_path=directory_path,
                    data=data,
                    number_of_time_steps=number_of_time_steps,
                    data_classes_comp = data_classes_comp,
                    ev =ev,
                    time_index=date_time_index,
                    heat_grid_temperature=heat_grid_temperature
                )


        typical_periods = 30
        hours_per_period = 24

        aggregation1 = tsam.TimeSeriesAggregation(
            timeSeries=data.iloc[:8760],
            noTypicalPeriods=typical_periods,
            hoursPerPeriod=hours_per_period,
            clusterMethod="k_means",

        )
        aggregation1.createTypicalPeriods()
        cluster_occurence=aggregation1.clusterPeriodNoOccur
        data = aggregation1.typicalPeriods
        t1_agg = pd.date_range(
            "2025-01-01", periods=typical_periods * hours_per_period, freq="H"
        )
        if False:
            for index, row in combined_cluster.iterrows():
                try:
                    building_id = row['building_id']
                    buildings_in_cluster = row['buildings_in_cluster']

                    # Identify the corresponding 'ww_demand' column for each building_id
                    ww_demand_column = f"ww_demand_{building_id}"
                    e_demand_column = f"e_demand_{building_id}"
                    building_demand_column = f"building_{building_id}"
                    # Multiply the ww_demand column by the number of buildings in the cluster
                    data[ww_demand_column] = data[ww_demand_column] * buildings_in_cluster
                    data[e_demand_column] = data[e_demand_column] * buildings_in_cluster
                    data[building_demand_column] = data[building_demand_column] * buildings_in_cluster
                except:
                    print(index)
            all_ww_demand_columns = [col for col in data.columns if 'ww_demand' in col]
            all_e_demand_columns = [col for col in data.columns if 'e_demand' in col]
            all_building_demand_columns = [col for col in data.columns if 'building' in col]

            data['ww_demand_total'] = data[all_ww_demand_columns].sum(axis=1)
            data['e_demand_total'] = data[all_e_demand_columns].sum(axis=1)
            data['building_total'] = data[all_building_demand_columns].sum(axis=1)

        final_results_ref, co2_ref, time = run_model(None, None,data,aggregation1,t1_agg,data_classes_comp,combined_cluster,heat_grid_temperature,cluster_occurence)
        co2_reduction_factor_ref = 1
        peak_reduction_factor_ref = 1
        results_loop_to_save[(co2_reduction_factor_ref, peak_reduction_factor_ref)] = {
            "results": final_results_ref,
            "co2": co2_ref,
            "peak_reduction_factor" : peak_reduction_factor_ref,
            "totex": final_results_ref["totex"],
            "peak": final_results_ref["Electricity"]["peak_from_grid"],
            "time":time

        }
        co2_reference_save = co2_ref
        peak_reference_save = final_results_ref["Electricity"]["peak_from_grid"]

        import numpy as np
        co2_reduction_factors =  np.arange(1, 0.325, -0.08).tolist() # [0.95,0.9,0.85,0.8,0.75,0.7,0.65,0.6,0.5] [0.9,0.8,0.7,0.6,0.5,0.4,0.3,0.2,0.1]
         #[1,0.9,0.8,0.7,0.6,0.5,0.4][1,0.95,0.9,0.85,0.8,0.75,0.7,0.65,0.6,0.55,0.5,0.45,0.4,0.35,0.3,0.25,0.2,0.15,0.1,0.05,0.01,-0.01,-0.05,-0.1,-0.2]
        for ref in ["co2","peak"]:
            if ref=="co2":
                peak_reference = peak_reference_save
                co2_reference = co2_reference_save
                for co2_reduction_factor in co2_reduction_factors:
                    first_co2_run_in_peak_loop = True
                    peak_reduction_factors = [1,0.9,0.8,0.7,0.6,0.5,0.4,0.3,0.2,0.1]
                    #peak_reduction_factors = [1,0.95,0.9,0.85,0.8,0.75,0.7,0.65,0.6,0.55,0.5,0.45,0.4,0.35,0.3,0.25,0.2,0.15,0.1,0.05]

                    if co2_reference > 0:
                        co2_new = co2_reference * co2_reduction_factor
                    else:
                        co2_new = co2_reference * (1+1-co2_reduction_factor)
                    print("START PEAK LOOP")
                    for peak_reduction_factor in peak_reduction_factors:
                        print("co2_reduction_factor: "+str(co2_reduction_factor))
                        print("peak_reduction_factor: " + str(peak_reduction_factor))
                        if first_co2_run_in_peak_loop:
                            peak_new =False
                        else:

                            peak_new = peak_reference * peak_reduction_factor

                        final_results, co2,time  = run_model(co2_new,peak_new,data,aggregation1,t1_agg,data_classes_comp,combined_cluster,heat_grid_temperature,cluster_occurence)
                        if final_results is None:
                            results_loop_to_save[(co2_reduction_factor, peak_reduction_factor,ref)] = {
                                "results": None,
                                "co2": None,
                                "peak_reduction_factor": None,
                                "refurbish": None,
                                "totex": None,
                                "peak": None,
                                "time":None
                            }
                            if first_co2_run_in_peak_loop:
                                first_co2_run_in_peak_loop = False
                                peak =False
                                peak_reference = peak
                            break
                        else:
                            peak_calculation_worked = True
                            totex = final_results["totex"]
                            peak = final_results["Electricity"]["peak_from_grid"]
                            if first_co2_run_in_peak_loop:
                                first_co2_run_in_peak_loop = False
                                peak_reference = peak

                            results_loop_to_save[(co2_reduction_factor, peak_reduction_factor)] = {
                                "results": final_results,
                                "co2": co2,
                                "peak_reduction_factor": peak_reduction_factor,
                                "totex": totex,
                                "peak": peak,
                                "time": time
                            }
                    print("FINISHED PEAK LOOP START SAVING")
                    file_path = "4results_heat_grid_"+str(heat_grid_temperature)+"_"+str(ueu)+"_" + str(ev) +".pkl"
                    if os.path.exists(file_path):
                        # If the file exists, open it and load the data
                        with open(file_path, "rb") as f:
                            existing_results = pickle.load(f)
                        print(f"Loaded existing results for {file_path}")

                        # Now you can add more data to existing_results
                        existing_results.update(results_loop_to_save)  # Example of adding new data

                    else:
                        # If the file doesn't exist, create it and save the results
                        existing_results = results_loop_to_save
                        print(f"New results created for {file_path}")

                    # Save the updated or new results back to the pickle file
                    with open(file_path, "wb") as f:
                        pickle.dump(existing_results, f)
            elif ref=="peak":
                peak_reference = peak_reference_save
                co2_reference = co2_reference_save
                co2_reduction_factors_saver=co2_reduction_factors
                peak_reduction_factors = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
                for peak_reduction_factor in peak_reduction_factors:
                    first_peak_run_in_co2_loop = True
                    co2_reduction_factors = co2_reduction_factors_saver

                    peak_new = peak_reference * peak_reduction_factor

                    print("START PEAK LOOP")
                    for co2_reduction_factor in co2_reduction_factors:
                        print("co2_reduction_factor: "+str(co2_reduction_factor))
                        print("peak_reduction_factor: " + str(peak_reduction_factor))
                        if first_peak_run_in_co2_loop:
                            co2_new =None
                        else:
                            if co2_reference > 0:
                                co2_new = co2_reference * co2_reduction_factor
                            else:
                                co2_new = co2_reference * (1 + 1 - co2_reduction_factor)
                        final_results, co2,time  = run_model(co2_new,peak_new,data,aggregation1,t1_agg,data_classes_comp,combined_cluster,heat_grid_temperature,cluster_occurence)
                        if final_results is None:
                            results_loop_to_save[(co2_reduction_factor, peak_reduction_factor,ref)] = {
                                "results": None,
                                "co2": None,
                                "peak_reduction_factor": None,
                                "refurbish": None,
                                "totex": None,
                                "peak": None,
                                "time":None
                            }
                            if first_peak_run_in_co2_loop:
                                first_peak_run_in_co2_loop = False
                                co2_new =False
                                co2_reference = co2_new
                            break
                        else:
                            totex = final_results["totex"]
                            peak = final_results["Electricity"]["peak_from_grid"]
                            if first_peak_run_in_co2_loop:
                                first_peak_run_in_co2_loop = False
                                peak_reference = peak

                            results_loop_to_save[(co2_reduction_factor, peak_reduction_factor,ref)] = {
                                "results": final_results,
                                "co2": co2,
                                "peak_reduction_factor": peak_reduction_factor,
                                "totex": totex,
                                "peak": peak,
                                "time": time
                            }
                    print("FINISHED PEAK LOOP START SAVING")
                    file_path = "4results_heat_grid_" + str(heat_grid_temperature) + "_" + str(ueu) + "_" + str(
                        ev) + ".pkl"
                    if os.path.exists(file_path):
                        # If the file exists, open it and load the data
                        with open(file_path, "rb") as f:
                            existing_results = pickle.load(f)
                        print(f"Loaded existing results for {file_path}")

                        # Now you can add more data to existing_results
                        existing_results.update(results_loop_to_save)  # Example of adding new data

                    else:
                        # If the file doesn't exist, create it and save the results
                        existing_results = results_loop_to_save
                        print(f"New results created for {file_path}")

                    # Save the updated or new results back to the pickle file
                    with open(file_path, "wb") as f:
                        pickle.dump(existing_results, f)
    file_path = "4results_heat_grid_"+str(heat_grid_temperature)+"_"+str(ueu)+"_" + str(ev) +".pkl"
    if os.path.exists(file_path):
        # If the file exists, open it and load the data
        with open(file_path, "rb") as f:
            existing_results = pickle.load(f)
        print(f"Loaded existing results for {file_path}")

        # Now you can add more data to existing_results
        existing_results.update(results_loop_to_save)  # Example of adding new data

    else:
        # If the file doesn't exist, create it and save the results
        existing_results = results_loop_to_save
        print(f"New results created for {file_path}")

    # Save the updated or new results back to the pickle file
    with open(file_path, "wb") as f:
        pickle.dump(existing_results, f)
heat_grid_supply_temperatures =[40,50,60,70]  # Beispiel #"GEG_standard"
def wrapper(args):
    rheat_grid_supply_temp = args
    try:
        print(f"start: {rheat_grid_supply_temp}")
        run_main(heat_grid_supply_temperatures)
    except Exception as e:
        print(f"crashed: {rheat_grid_supply_temp} | {e}")
if __name__ == "__main__":
    import multiprocessing
    import itertools
    tasks = list(itertools.product(heat_grid_supply_temperatures))
    # erzeugt alle Kombinationen [(refurbish1, building1), (refurbish1, building2), ...]

    with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
        pool.map(wrapper, tasks)