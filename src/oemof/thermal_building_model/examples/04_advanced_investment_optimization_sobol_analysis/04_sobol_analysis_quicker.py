from oemof.thermal_building_model.oemof_facades.base_component import  PhysicalBaseUnit

from oemof.thermal_building_model.oemof_facades.infrastructure.grids import ElectricityGrid, GasGrid
from oemof.thermal_building_model.oemof_facades.infrastructure.carriers import ElectricityCarrier, HeatCarrier, \
    GasCarrier
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses, flatten_components_list
from oemof.thermal_building_model.oemof_facades.infrastructure.demands import ElectricityDemand, WarmWater
from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import PVSystem
from oemof.thermal_building_model.oemof_facades.technologies.storages import Battery, HotWaterTank
from oemof.thermal_building_model.oemof_facades.technologies.converter import AirHeatPump, GasHeater
from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import ThermalBuilding
from oemof import solph
from oemof.thermal_building_model.helpers.calculate_pv_electricity_yield import simulate_pv_yield
import pandas as pd

import random
from oemof.thermal_building_model.input.economics.investment_components_sobol import battery_config,hot_water_tank_config,air_heat_pump_config,gas_heater_config,pv_system_config
import copy
import os
import pickle
import multiprocessing
import argparse
import sys
from SALib.sample import saltelli

DEFAULT_OUTPUT_DIR_REMOTE = "/jump/mh"
DEFAULT_MFH_PROFILES_DIR_REMOTE = (
    "/home/mh/thermal_building_clone/src/oemof/thermal_building_model/"
    "examples/04_advanced_investment_optimization_sobol_analysis/lpg_profiles"
)
DEFAULT_SFH_PROFILES_DIR_REMOTE = (
    "/home/hill_mx/thermal_building_clone/src/oemof/thermal_building_model/"
    "examples/04_advanced_investment_optimization_sobol_analysis/lpg_profiles"
)

def main(year_of_construction,target_residents,tabula_building_code, building_type,building_size,demand_path,floor_to_roof_area_ratio,azimuth,tilt,co2_limit,peak_new,result_key):
    target_residents = target_residents
    building_type = building_type
    building_id = tabula_building_code
    floor_area = building_size
    demand_path = demand_path
    floor_to_roof_area_ratio = floor_to_roof_area_ratio
    construction_year = year_of_construction
    solver = "scip"  # 'glpk', 'gurobi',....
    number_of_time_steps = 8760


    date_time_index = solph.create_time_index(
        2012, number=number_of_time_steps-1)
    es = solph.EnergySystem(timeindex=date_time_index,
                            infer_last_interval=False)

    electricity_grid_dataclass = ElectricityGrid(max_peak_from_grid=peak_new,
                                                     max_peak_into_grid=peak_new)



    electricity_grid_bus_from_grid = electricity_grid_dataclass.get_bus_from_grid()
    electricity_grid_bus_into_grid = electricity_grid_dataclass.get_bus_into_grid()
    electricity_grid_sink = electricity_grid_dataclass.create_sink()
    electricity_grid_source = electricity_grid_dataclass.create_source()
    electricity_carrier_dataclass = ElectricityCarrier()
    electricity_carrier_bus = electricity_carrier_dataclass.get_bus()
    connect_buses(input=electricity_grid_bus_from_grid, target=electricity_carrier_bus, output=electricity_grid_bus_into_grid)
    if building_type == "SFH":
        electricity_demand_dataclass = ElectricityDemand(
            demand_path=demand_path + '/SumProfiles.Electricity.csv',
            bus=electricity_carrier_bus,
        )
    elif building_type == "MFH":
        value_list_elect_demand = []
        result_key_list = [result_key] if isinstance(result_key, str) else list(result_key)

        for result_k in result_key_list:
            csv_path = os.path.join(demand_path, result_k, "SumProfiles.Electricity.csv")
            df_elect = pd.read_csv(csv_path, delimiter=";")
            elect_df = (
                df_elect.groupby(df_elect.index // 60)["Sum [kWh]"]
                .sum()
                .to_frame(name="Hourly_Sum")["Hourly_Sum"]
            ) * 1000
            values = elect_df.tolist()

            if not value_list_elect_demand:
                value_list_elect_demand = values
            else:
                value_list_elect_demand = [
                    a + b for a, b in zip(value_list_elect_demand, values)
                ]

        electricity_demand_dataclass = ElectricityDemand(
            value_list=value_list_elect_demand,
            bus=electricity_carrier_bus,
        )
    else:
        raise ValueError(f"Unknown building_type: {building_type}")
    electricity_demand = electricity_demand_dataclass.create_demand()

    electricity  = [electricity_grid_bus_from_grid,
                    electricity_grid_bus_into_grid,
                    electricity_grid_sink,
                    electricity_grid_source,
                    electricity_carrier_bus,
                    electricity_demand]

    building_dataclass = ThermalBuilding(name=building_id,
                                         building_type=building_type,
                                         number_of_occupants=target_residents,
                                         floor_area=floor_area,
                                         country="DE",
                                         construction_year=construction_year,
                                         class_building="average",
                                         heat_level_calculation=True,
                                         number_of_time_steps=number_of_time_steps,
                                         time_index=date_time_index,
                                         refurbishment_status="no_refurbishment",
                                         )
    temp_heating_demand_building = building_dataclass.level_heating_demand

    heat_carrier_temperature_levels = [40,temp_heating_demand_building,80]
    heat_carrier_dataclass = HeatCarrier(levels = heat_carrier_temperature_levels)
    heat_carrier_dataclass.connect_buses_decreasing_levels()

    heat_carrier_bus = heat_carrier_dataclass.get_bus()
    for key, value in heat_carrier_bus.items():
        es.add(value)

    building_dataclass.bus = heat_carrier_bus[building_dataclass.level_heating_demand]


    if building_type == "SFH":
        heat_demand_dataclass = WarmWater(
            name="WarmWater",
            level=40,
            bus=heat_carrier_bus[40],
            demand_path=demand_path + '/SumProfiles.Warm Water.csv',
        )
    elif building_type == "MFH":
        value_list_ww_demand = []
        result_key_list = [result_key] if isinstance(result_key, str) else list(result_key)

        for result_k in result_key_list:
            csv_path = os.path.join(demand_path, result_k, "SumProfiles.Warm Water.csv")
            df_warm_water = pd.read_csv(csv_path, delimiter=";")
            warm_water_demand_df = (
                df_warm_water.groupby(df_warm_water.index // 60)["Sum [L]"]
                .sum()
                .to_frame(name="Hourly_Sum")["Hourly_Sum"]
            )
            values = warm_water_demand_df.tolist()

            if not value_list_ww_demand:
                value_list_ww_demand = values
            else:
                value_list_ww_demand = [a + b for a, b in zip(value_list_ww_demand, values)]

        heat_demand_dataclass = WarmWater(
            name="WarmWater",
            level=40,
            bus=heat_carrier_bus[40],
            value_list=value_list_ww_demand,
        )
    else:
        raise ValueError(f"Unknown building_type: {building_type}")


    heat_demand = heat_demand_dataclass.create_demand()
    hot_water_tank_config_building = copy.deepcopy(hot_water_tank_config)
    hot_water_tank_config_building.maximum_capacity =  4
    hot_water_tank_input_bus = solph.buses.Bus(label=f"tank_input_bus_{building_id}")
    hot_water_tank_output_bus = solph.buses.Bus(label=f"tank_output_bus_{building_id}")

    hot_water_tank_dataclass = HotWaterTank(
        name="heat_storage",
        investment=True,
        temperature_buses=heat_carrier_dataclass.get_bus(),
        max_temperature=80,
        min_temperature=40,
        investment_component=hot_water_tank_config_building,
        input_bus=hot_water_tank_input_bus,
        output_bus=hot_water_tank_output_bus,
    )
    hot_water_tank = hot_water_tank_dataclass.create_storage()
    hot_water_tank_stratisfied_temp_levels_dict = hot_water_tank_dataclass.get_stratified_storage_temperature_levels()
    hot_water_tank_stratisfied = hot_water_tank_dataclass.create_stratified_storage(
        hot_water_tank_stratisfied_temp_levels_dict, heat_carrier_bus)
    for key, value in hot_water_tank_stratisfied.items():
        es.add(value)
    es.add(hot_water_tank,hot_water_tank_input_bus,hot_water_tank_output_bus)


    es.add(hot_water_tank)

    air_heat_pump_config_building = copy.deepcopy(air_heat_pump_config)

    air_heat_pump_dataclass = AirHeatPump(heat_carrier_bus=heat_carrier_dataclass.get_bus(),
                                          investment=True,
                                          name="hp_" + str(building_id),
                                          investment_component=air_heat_pump_config_building)
    air_heat_pump_bus = air_heat_pump_dataclass.get_bus()
    air_heat_pump = air_heat_pump_dataclass.create_source()

    air_heat_pump_converters = air_heat_pump_dataclass.create_converters(heat_pump_bus=air_heat_pump_bus,
                                                                         electricity_bus=electricity_carrier_bus,
                                                                         heat_carrier_bus=heat_carrier_bus)
    es.add(air_heat_pump_bus,air_heat_pump,*air_heat_pump_converters)

    gas_grid_dataclass = GasGrid()
    gas_grid_bus_from_grid = gas_grid_dataclass.get_bus_from_grid()
    gas_grid_source = gas_grid_dataclass.create_source()

    gas_carrier_dataclass = GasCarrier()
    gas_bus = gas_carrier_dataclass.get_bus()
    connect_buses(input=gas_grid_bus_from_grid, target=gas_bus)
    gas_heater_config_building = copy.deepcopy(gas_heater_config)

    gas_heater_dataclass = GasHeater(investment=True,
                                     investment_component=gas_heater_config_building)
    gas_heater_bus = gas_heater_dataclass.get_bus()
    gas_heater= gas_heater_dataclass.create_source()
    gas_heater_converters= gas_heater_dataclass.create_converters(gas_heater_bus = gas_heater_bus,
                                                                  gas_bus = gas_bus,
                                                                  heat_carrier_bus=heat_carrier_dataclass.get_bus())
    es.add(            gas_heater_bus,
        gas_heater,
        *gas_heater_converters)

    es.add(gas_grid_bus_from_grid,
            gas_bus,
           gas_grid_source,
)
    battery_config_building = copy.deepcopy(battery_config)
    if building_type == "SFH":
        battery_config_building.maximum_capacity = 30000 / PhysicalBaseUnit.factor
    elif building_type == "MFH":
        battery_config_building.maximum_capacity = 80000 / PhysicalBaseUnit.factor

    battery_dataclass = Battery(investment=True,
                                input_bus = electricity_carrier_bus,
                                output_bus = electricity_carrier_bus,
                                investment_component=battery_config_building)
    battery = battery_dataclass.create_storage()
    es.add(battery)




    building_component = building_dataclass.create_demand()
    es.add(building_component)
    heat = []
    heat = [
        #heat_grid_sink,
            #heat_grid_source,
            #heat_grid_bus_from_grid,
           # heat_grid_bus_into_grid,
            heat_carrier_bus,
            heat_demand]
    pv_system_config_building = copy.deepcopy(pv_system_config)

    from oemof.thermal_building_model.helpers.path_helper import get_project_root

    main_path = get_project_root()
    print("main path:"+str(main_path))
    epw_path = os.path.join(
        main_path,
        "thermal_building_model",
        "input",
        "weather_files",
        "03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv",
    )
    pv_yield_per_wp = simulate_pv_yield(
        pv_nominal_power_in_watt=1,
        tilt=tilt,
        azimuth = azimuth,
        epw_path=epw_path,
        both_side_average=True
    )
    pv_dataclass = PVSystem(investment=True,
                            value_list = pv_yield_per_wp.tolist(),
                            investment_component=pv_system_config_building)

    total_roof_area = building_dataclass.get_roof_area()
    ratio_standard = floor_area/total_roof_area
    roof_area_increasement =1/(floor_to_roof_area_ratio/ratio_standard)
    pv_dataclass.update_maximum_investment_pv_capacity_based_on_area(area=building_dataclass.get_roof_area_for_pv()*roof_area_increasement)
    pv_bus = pv_dataclass.get_bus()
    pv_system = pv_dataclass.create_source()
    pv_system_curtailment_capable = pv_dataclass.create_sink()
    connect_buses(input=pv_bus, target=electricity_carrier_bus)

    es.add(pv_system,pv_system_curtailment_capable,pv_bus)

    electricity_components = flatten_components_list(electricity)
    heat_components = flatten_components_list(heat)
    # Add all components to the energy system in one go
    # Add all components to the energy system in one go
    es.add(*(heat_components))
    es.add(*(electricity_components))
    model = solph.Model(es)

    if co2_limit is None:
        model = solph.constraints.additional_total_limit(model, "co2", limit=10000000)

    else:
        model = solph.constraints.additional_total_limit(model, "co2", limit=co2_limit )
    # Show the graph
    # Show the graph

    try:
        print("__________")
        print("start for:")


        model.solve(solver=solver, solve_kwargs={"tee": True},
                                              cmdline_options={"mipgap": 0.0075})
        meta_results = solph.processing.meta_results(model)
        print(meta_results["objective"])
        #print(meta_results["solver"]["Wall time"])
        results = solph.processing.results(model)

        final_results = {}
        final_results[hot_water_tank_dataclass.name] = hot_water_tank_dataclass.post_process(results,hot_water_tank)

        final_results[battery_dataclass.name] = battery_dataclass.post_process(results,battery)

        final_results[electricity_grid_dataclass.name] = electricity_grid_dataclass.post_process(results,electricity_grid_source,electricity_grid_sink
                                                )
        final_results[gas_grid_dataclass.name] = gas_grid_dataclass.post_process(results,gas_grid_source,None
                                                )
        #final_results[heat_grid_dataclass.name] = heat_grid_dataclass.post_process(results,heat_grid_source,None)
        final_results[gas_heater_dataclass.name] = gas_heater_dataclass.post_process(results,gas_heater,gas_heater_converters,heat_carrier_bus,gas_bus)
        final_results[air_heat_pump_dataclass.name] = air_heat_pump_dataclass.post_process(results,air_heat_pump,air_heat_pump_converters,heat_carrier_bus,electricity_carrier_bus)

        final_results[pv_dataclass.name] = pv_dataclass.post_process(results,pv_system,pv_system_curtailment_capable)

        final_results[building_dataclass.name] = building_dataclass.post_process(results,building_component)

        final_results[electricity_demand_dataclass.name] = electricity_demand_dataclass.post_process(results,electricity_demand)

        final_results[heat_demand_dataclass.name] = heat_demand_dataclass.post_process(results,heat_demand)


        final_results["co2_post_process"] = (final_results[battery_dataclass.name]["investment_co2"
                                ]+final_results[hot_water_tank_dataclass.name]["investment_co2"
                                ]+final_results[gas_heater_dataclass.name]["investment_co2"
                                ]+final_results[air_heat_pump_dataclass.name]["investment_co2"
                                ]+final_results[pv_dataclass.name]["investment_co2"
                                ]+final_results[building_dataclass.name]["investment_co2"]
                                #+final_results[heat_grid_dataclass.name]["investment_co2"]
                                +final_results[electricity_grid_dataclass.name]["flow_from_grid_co2"
                                ]-final_results[electricity_grid_dataclass.name]["flow_into_grid_co2"
                                ]+final_results[gas_grid_dataclass.name]["flow_from_grid_co2"
                                ])
        co2 = model.total_limit_co2()
        final_results[electricity_grid_dataclass.name]["peak_from_grid"]
        final_results[electricity_grid_dataclass.name]["peak_into_grid"]


        print("co2_constraint: ", co2)
        print("co2_manuel: ", final_results["co2_post_process"])
        print("objective",str(meta_results["objective"]))
        final_results["co2_oemof_model"] = co2
        final_results["totex"] = meta_results["objective"]
        final_results["peak_from_grid"] = final_results[electricity_grid_dataclass.name]["peak_from_grid"]
        final_results["peak_into_grid"] = final_results[electricity_grid_dataclass.name]["peak_into_grid"]
        return final_results, co2
    except Exception as e:
        print(e)
        return None, None

print("start")
# 1. Problem definieren
problem = {
    'num_vars': 6,
    'names': ['net_floor_area','floor_to_roof_area_ratio', 'tabula_year_class', 'number_of_residents',"azimuth","tilt"],
    'bounds': [
        [0, 1],      # Wohnfläche in m²
        [0,1]   ,        #floor_to_roof_area_ratio
        [1, 11],        # tabula_year_class (1-11 Klassen)
        [0, 1],         # Bewohner
        [0, 180],       #azimuth
        [30, 60]          # tilt
    ]
}
# Sampling (kleine Anzahl für Test)
param_values = saltelli.sample(problem, int(1024), calc_second_order=False)
# laut chat gpt bei 6 params sollte man n=	1024für gute Ergebnisse, das wären 16.000 Durchläufe
# Spaltenindex merken
# sfh liegt zwischen 1.5:3 und MFH zwischen 2:4
idx_size = problem['names'].index('net_floor_area')
idx_floor_to_roof_area_ratio = problem['names'].index('floor_to_roof_area_ratio')
idx_year_class = problem['names'].index('tabula_year_class')
idx_residents = problem['names'].index('number_of_residents')
idx_azimuth = problem['names'].index('azimuth')
idx_tilt = problem['names'].index('tilt')

sfh_floor_area_min, sfh_floor_area_max = 105, 320
mfh_floor_area_min, mfh_floor_area_max = 300, 528

sfh_residents_min, sfh_residents_max = 1, 6
mfh_residents_min, mfh_residents_max = 3, 14

sfh_ratio_min, sfh_ratio_max = 0.8, 3 #floor to roof
mfh_ratio_min, mfh_ratio_max = 2, 5
# Runden der gewünschten Variablen
# Mapping
if True:
    from different_household_models import sobol_households
import random

def random_household_sizes(total: int, k: int, min_size: int = 1, max_size: int = 6) -> list[int]:
    """
    Liefert eine zufällige Liste der Länge k, deren Summe total ist,
    und jeder Eintrag liegt in [min_size, max_size].
    """
    if total < k * min_size or total > k * max_size:
        raise ValueError(f"Unmöglich: total={total} passt nicht zu k={k} mit [{min_size},{max_size}]")

    remaining = total
    sizes = []
    for i in range(k):
        remaining_slots = k - i - 1

        # was muss mindestens / maximal noch übrig bleiben?
        min_for_rest = remaining_slots * min_size
        max_for_rest = remaining_slots * max_size

        # aktuelle Wahl muss so sein, dass Rest noch möglich ist
        low = max(min_size, remaining - max_for_rest)
        high = min(max_size, remaining - min_for_rest)

        s = random.randint(low, high)
        sizes.append(s)
        remaining -= s

    random.shuffle(sizes)
    return sizes
def possible_households_by_size(sobol_households: dict, sizes: list[int]) -> list[list[tuple]]:
    """
    Für jede Haushaltsgröße in sizes: Liste möglicher Haushalte [(name,res), ...]
    """
    result = []
    for s in sizes:
        possible = [(name, res) for name, res in sobol_households.items() if res == s]
        result.append(possible)
    return result
def run_multiprocessing(gap_starter,
                        idx_size,
                        idx_year_class,
                        idx_residents,
                        idx_azimuth,
                        idx_tilt,
                        setted_gap=0,
                        n_samples=None,
                        gap_size=200,
                        gap_size_saver=200,
                        building_type="MFH",
                        host_name="unknown",
                        output_dir=DEFAULT_OUTPUT_DIR_REMOTE,
                        mfh_profiles_dir=DEFAULT_MFH_PROFILES_DIR_REMOTE,
                        sfh_profiles_dir=DEFAULT_SFH_PROFILES_DIR_REMOTE,
                        ):


    # Beispiel-Durchlauf
    results_loop_to_save = {}
    results_loop_to_save_peak_limit = {}
    results_loop_to_save_co2_limit = {}
    results_loop_to_save_simple = {}
    results_loop_to_save_peak_limit_simple = {}
    results_loop_to_save_co2_limit_simple = {}

    if n_samples is None:
        n_samples = max(0, len(param_values) - setted_gap)
    if n_samples <= 0:
        return

    host_end_exclusive = min(setted_gap + n_samples, len(param_values))
    if setted_gap >= host_end_exclusive:
        return

    counter=  0
    status=True
    counter_for_txt = 0
    os.makedirs(output_dir, exist_ok=True)
    for params in param_values:
        gap_min = gap_starter * gap_size + setted_gap
        gap_max = min((gap_starter + 1) * gap_size + setted_gap, host_end_exclusive)
        if gap_min >= gap_max:
            break

        if gap_min > counter:
            counter += 1
            continue
        if counter >= gap_max:
            break
        status=False
        # Erstelle den Dateipfad für die Textdatei
        file_path = os.path.join(
            output_dir, f"txt_{building_type}_{host_name}_{gap_min}_{gap_max}.txt"
        )

        # Öffne die Textdatei zum Anhängen oder Erstellen (falls sie nicht existiert)

            # Wenn der counter_for_txt gleich 0 ist, schreibe die Startzeile in die Datei
        if counter_for_txt == 0:
            with open(file_path, 'a') as f:
                f.write(f"Started for: counter_for_txt {counter_for_txt} missing: {gap_max - counter}\n")

        # Schreibe alle 5 Schritte (counter_for_txt % 5) in die Datei
        elif counter_for_txt % 5 == 0:
            with open(file_path, 'a') as f:
                f.write(f"Started for: counter_for_txt {counter_for_txt} missing: {gap_max - counter}\n")

        counter_for_txt +=1
        # Normalisierungsfunktion
        # Rückberechnungsfunktion
        def reverse_normalize(normalized_value, min_val, max_val):
            return normalized_value * (max_val - min_val) + min_val

        if building_type == "SFH":
            building_size = reverse_normalize(params[idx_size], sfh_floor_area_min, sfh_floor_area_max)
            normalized_residents = reverse_normalize(params[idx_residents], sfh_residents_min, sfh_residents_max)
            floor_to_roof_area_ratio = reverse_normalize(params[idx_floor_to_roof_area_ratio], sfh_ratio_min, sfh_ratio_max)
            target_residents = normalized_residents
            # Passende Haushalte filtern
            possible_households = [
                (name, res) for name, res in sobol_households.items()
                if res == int(target_residents)
            ]

            if possible_households:
                chosen_household, _ = random.choice(possible_households)
            else:
                chosen_household = "Kein passender Haushalt gefunden"
        elif building_type == "MFH":
            building_size = reverse_normalize(params[idx_size], mfh_floor_area_min, mfh_floor_area_max)
            normalized_residents = reverse_normalize(params[idx_residents], mfh_residents_min, mfh_residents_max)
            floor_to_roof_area_ratio = reverse_normalize(params[idx_floor_to_roof_area_ratio], mfh_ratio_min, mfh_ratio_max)
            # Passende Haushalte filtern
            target_residents = int(normalized_residents)
            if target_residents == 3:
                number_households = 3
            elif target_residents == 4:
                number_households = random.choice([3, 4])
            elif target_residents > 4:
                number_households = random.randint(3, 5)  # 3,4,5

            # 2) in Haushaltsgrößen aufteilen (1..6)
            sizes = random_household_sizes(target_residents, number_households, 1, 6)
            possible_households_lists = possible_households_by_size(sobol_households, sizes)
            chosen_household = possible_households_lists


        tabula_year_class = int(params[idx_year_class])  # Die Nummer, die du brauchst
        azimuth = params[idx_azimuth]
        tilt = params[idx_tilt]

        # TABULA-Building-Code generieren

        if tabula_year_class == 1:
            year_of_construction = 1850
        elif tabula_year_class == 2:
            year_of_construction = 1910
        elif tabula_year_class == 3:
            year_of_construction = 1930
        elif tabula_year_class == 4:
            year_of_construction = 1950
        elif tabula_year_class == 5:
            year_of_construction = 1960
        elif tabula_year_class == 6:
            year_of_construction = 1970
        elif tabula_year_class == 7:
            year_of_construction = 1980
        elif tabula_year_class == 8:
            year_of_construction = 1990
        elif tabula_year_class == 9:
            year_of_construction = 2000
        elif tabula_year_class == 10:
            year_of_construction = 2005
        elif tabula_year_class == 11:
            year_of_construction = 2010
        elif tabula_year_class == 12:
            year_of_construction = 2020

        refurbishment_status_tabula ="no_refurbishment"
        if building_type =="SFH":
            tabula_building_code = f"DE.N.SFH.{tabula_year_class:02d}.Gen.ReEx.001.001"
        elif building_type =="MFH":
            tabula_building_code = f"DE.N.MFH.{tabula_year_class:02d}.Gen.ReEx.001.001"
        print(f" Ziel-Bewohner: {target_residents}, Haushalt: {chosen_household}, Floor Area: {building_size}")
        print(f"TABULA-Code: {year_of_construction}\n")
        print("building size: " +str(building_size) )
        print("counter: " + str(counter))
        import re


        def format_household_key(chosen_household):
            def map_chr_to_result_key(household_name):
                if not isinstance(household_name, str):
                    return None

                match = re.match(r"CHR0?(\d+)", household_name.strip())
                if match:
                    number = int(match.group(1))  # int entfernt fuehrende Nullen
                    return f"Results_CHH_{number}"
                return None

            if isinstance(chosen_household, str):
                result_key_single = map_chr_to_result_key(chosen_household)
                return result_key_single if result_key_single else "Results_INVALID"

            extracted_household_names = []
            if isinstance(chosen_household, (list, tuple)):
                for household in chosen_household:
                    if isinstance(household, str):
                        extracted_household_names.append(household)
                        continue

                    if isinstance(household, (list, tuple)) and household:
                        first_entry = household[0]
                        if isinstance(first_entry, str):
                            extracted_household_names.append(first_entry)
                        elif isinstance(first_entry, (list, tuple)) and first_entry:
                            if isinstance(first_entry[0], str):
                                extracted_household_names.append(first_entry[0])

            result_keys = [
                result_key
                for result_key in (
                    map_chr_to_result_key(household_name)
                    for household_name in extracted_household_names
                )
                if result_key is not None
            ]

            if not result_keys:
                return "Results_INVALID"
            if len(result_keys) == 1:
                return result_keys[0]
            return result_keys
        if building_type == "SFH":
            result_key = format_household_key(chosen_household)
            demand_path = os.path.join(sfh_profiles_dir, result_key)
        elif building_type == "MFH":
            result_key = format_household_key(chosen_household)
            demand_path = mfh_profiles_dir


        final_results, co2  = main(year_of_construction,
             target_residents,
             tabula_building_code,
             building_type,
             building_size,
             demand_path,
             floor_to_roof_area_ratio,
             azimuth, tilt,None,None,result_key
                 )
        if final_results is None:
            results_loop_to_save[counter] = {
                "results": None,

                "co2": None,
                "totex": None,
                "peak": None
            }
            results_loop_to_save_simple[counter] = {
                "co2": None,
                "totex": None,
                "peak": None
            }
            results_loop_to_save_co2_limit[counter] = {
                "results": None,

                "co2": None,
                "totex": None,
                "peak": None
            }
            results_loop_to_save_co2_limit_simple[counter] = {
                "co2": None,
                "totex": None,
                "peak": None
            }
            results_loop_to_save_peak_limit[counter] = {
                "results": None,

                "co2": None,
                "totex": None,
                "peak": None
            }
            results_loop_to_save_peak_limit_simple[counter] = {
                "co2": None,
                "totex": None,
                "peak": None
            }
        else:
            totex = final_results["totex"]
            peak = (final_results["Electricity"]["peak_into_grid"],
            final_results["Electricity"]["peak_from_grid"])
            results_loop_to_save[counter] = {
                    "results": final_results,

                    "co2": co2,
                    "totex": totex,
                    "peak": peak
            }
            results_loop_to_save_simple[counter] = {
                "co2": co2,
                "totex": totex,
                "peak": peak
            }
            final_results_co2_limit, co2_co2_limit = main(year_of_construction,
                                      target_residents,
                                      tabula_building_code,
                                      building_type,
                                      building_size,
                                      demand_path,
                                      floor_to_roof_area_ratio,
                                      azimuth, tilt, co2*0.5, None,result_key
                                      )
            if final_results_co2_limit is None:
                results_loop_to_save_co2_limit[counter] = {
                    "results": None,

                    "co2": None,
                    "totex": None,
                    "peak": None
                }
                results_loop_to_save_co2_limit_simple[counter] = {
                    "co2": None,
                    "totex": None,
                    "peak": None
                }
                results_loop_to_save_peak_limit[counter] = {
                    "results": None,

                    "co2": None,
                    "totex": None,
                    "peak": None
                }
                results_loop_to_save_peak_limit_simple[counter] = {
                    "co2": None,
                    "totex": None,
                    "peak": None
                }
            else:
                totex = final_results_co2_limit["totex"]
                peak = (final_results_co2_limit["Electricity"]["peak_into_grid"],
                        final_results_co2_limit["Electricity"]["peak_from_grid"])
                results_loop_to_save_co2_limit[counter] = {
                    "results": final_results_co2_limit,

                    "co2": co2_co2_limit,
                    "totex": totex,
                    "peak": peak
                }
                results_loop_to_save_co2_limit_simple[counter] = {
                    "co2": co2_co2_limit,
                    "totex": totex,
                    "peak": peak
                }
                final_results_peak_limit, co2_peak_limit = main(year_of_construction,
                                                              target_residents,
                                                              tabula_building_code,
                                                              building_type,
                                                              building_size,
                                                              demand_path,
                                                              floor_to_roof_area_ratio,
                                                              azimuth, tilt, co2*0.5, max(peak)*0.5,result_key
                                                              )
                if final_results_peak_limit is None:
                    results_loop_to_save_peak_limit[counter] = {
                        "results": None,

                        "co2": None,
                        "totex": None,
                        "peak": None
                    }
                    results_loop_to_save_peak_limit_simple[counter] = {
                        "co2": None,
                        "totex": None,
                        "peak": None
                    }
                else:
                    totex = final_results_co2_limit["totex"]
                    peak = (final_results_co2_limit["Electricity"]["peak_into_grid"],
                            final_results_co2_limit["Electricity"]["peak_from_grid"])
                    results_loop_to_save_peak_limit[counter] = {
                        "results": final_results_peak_limit,

                        "co2": co2_peak_limit,
                        "totex": totex,
                        "peak": peak
                    }
                    results_loop_to_save_peak_limit_simple[counter] = {
                        "co2": co2_peak_limit,
                        "totex": totex,
                        "peak": peak
                    }

        if False:
            results_loop_to_save[(counter,building_size, household_type,target_residents,year_of_construction)] = {
                        "results": None,
                        "co2": None,
                        "totex": None,
                        "peak": None
                    }

        if (
            counter % gap_size_saver == 0
            or counter == (gap_max - 1)
            or counter == (len(param_values) - 1)
            or counter == (len(param_values) - 2)
        ):
            gap_value_to_save  = setted_gap + gap_starter
            file_path = os.path.join(
                output_dir, f"sobol_{building_type}_{host_name}_{setted_gap}_{counter}.pkl"
            )
            file_path_co2 = os.path.join(
                output_dir, f"sobol_co2_{building_type}_{host_name}_{setted_gap}_{counter}.pkl"
            )
            file_path_peak = os.path.join(
                output_dir, f"sobol_peak_{building_type}_{host_name}_{setted_gap}_{counter}.pkl"
            )
            file_path_simple = os.path.join(
                output_dir, f"simple_sobol_{building_type}_{host_name}_{setted_gap}_{counter}.pkl"
            )
            file_path_co2_simple = os.path.join(
                output_dir, f"simple_sobol_co2_{building_type}_{host_name}_{setted_gap}_{counter}.pkl"
            )
            file_path_peak_simple = os.path.join(
                output_dir, f"simple_sobol_peak_{building_type}_{host_name}_{setted_gap}_{counter}.pkl"
            )
            # If the file doesn't exist, create it and save the results
            print(f"New results created for {file_path}")

            # Save the updated or new results back to the pickle file
            with open(file_path, "wb") as f:
                pickle.dump(results_loop_to_save, f)
            with open(file_path_co2, "wb") as f:
                pickle.dump(results_loop_to_save_co2_limit, f)
            with open(file_path_peak, "wb") as f:
                pickle.dump(results_loop_to_save_peak_limit, f)
            with open(file_path_simple, "wb") as f:
                pickle.dump(results_loop_to_save_simple, f)
            with open(file_path_co2_simple, "wb") as f:
                pickle.dump(results_loop_to_save_co2_limit_simple, f)
            with open(file_path_peak_simple, "wb") as f:
                pickle.dump(results_loop_to_save_peak_limit_simple, f)
            # Save the updated or new results back to the pickle file
            results_loop_to_save = {}
            results_loop_to_save_peak_limit = {}
            results_loop_to_save_co2_limit = {}
            results_loop_to_save_simple = {}
            results_loop_to_save_peak_limit_simple = {}
            results_loop_to_save_co2_limit_simple = {}
        counter += 1
        if counter >= gap_max:
            break
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run sobol analysis with explicit per-host slice.")
    parser.add_argument("--host-name", type=str, default="unknown")

    parser.add_argument("--setted-gap", type=int, default=None,
                        help="Absolute start index in param_values for this host/run.")
    parser.add_argument("--n-samples", type=int, default=None,
                        help="How many samples this host should process.")

    parser.add_argument("--gap-size", type=int, default=5)
    parser.add_argument("--gap-size-saver", type=int, default=5)
    parser.add_argument("--building-type", type=str, default="MFH", choices=["SFH", "MFH"])

    parser.add_argument("--workers", type=int, default=1,
                        help="Max number of gap processes to run in parallel on this host.")
    parser.add_argument("--serial", action="store_true",
                        help="Run gaps sequentially (no multiprocessing).")
    parser.add_argument("--debug-local", action="store_true",
                        help="Use local debug defaults so the script can be started directly from IDE.")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory for pickle/txt result chunks.")
    parser.add_argument("--mfh-profiles-dir", type=str, default=None,
                        help="Base directory for MFH profiles.")
    parser.add_argument("--sfh-profiles-dir", type=str, default=None,
                        help="Base directory for SFH profiles.")
    args = parser.parse_args()
    if len(sys.argv) == 1:
        args.debug_local = True

    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_profiles_dir = os.path.join(script_dir, "lpg_profiles")

    if args.debug_local:
        if args.setted_gap is None:
            args.setted_gap = 0
        if args.n_samples is None:
            args.n_samples = 1
        if args.host_name == "unknown":
            args.host_name = "debug_local"
        args.serial = True
        args.workers = 1
        args.gap_size = 1
        args.gap_size_saver = 1
        if args.output_dir is None:
            args.output_dir = os.path.join(script_dir, "debug_output")
        if args.mfh_profiles_dir is None:
            args.mfh_profiles_dir = local_profiles_dir
        if args.sfh_profiles_dir is None:
            args.sfh_profiles_dir = local_profiles_dir
    else:
        if args.setted_gap is None or args.n_samples is None:
            parser.error("--setted-gap und --n-samples sind erforderlich (oder --debug-local verwenden).")
        if args.output_dir is None:
            args.output_dir = DEFAULT_OUTPUT_DIR_REMOTE
        if args.mfh_profiles_dir is None:
            args.mfh_profiles_dir = DEFAULT_MFH_PROFILES_DIR_REMOTE
        if args.sfh_profiles_dir is None:
            args.sfh_profiles_dir = DEFAULT_SFH_PROFILES_DIR_REMOTE

    if args.setted_gap < 0:
        raise ValueError("--setted-gap must be >= 0")
    if args.n_samples <= 0:
        raise ValueError("--n-samples must be > 0")
    if args.gap_size <= 0:
        raise ValueError("--gap-size must be > 0")
    if args.workers <= 0:
        raise ValueError("--workers must be > 0")

    setted_gap = args.setted_gap
    available_samples = max(0, len(param_values) - setted_gap)
    effective_samples = min(args.n_samples, available_samples)
    if effective_samples <= 0:
        raise ValueError("No samples available for this --setted-gap in param_values.")

    number_of_gaps = (effective_samples + args.gap_size - 1) // args.gap_size
    gap_values = range(number_of_gaps)

    print(
        f"host={args.host_name} setted_gap={setted_gap} n_samples={effective_samples} "
        f"gaps={number_of_gaps} gap_size={args.gap_size} workers={args.workers} "
        f"output_dir={args.output_dir}"
    )

    if args.serial or args.workers == 1:
        for gap_starter in gap_values:
            run_multiprocessing(
                gap_starter,
                idx_size,
                idx_year_class,
                idx_residents,
                idx_azimuth,
                idx_tilt,
                setted_gap,
                effective_samples,
                args.gap_size,
                args.gap_size_saver,
                args.building_type,
                args.host_name,
                args.output_dir,
                args.mfh_profiles_dir,
                args.sfh_profiles_dir,
            )
    else:
        gap_list = list(gap_values)
        for i in range(0, len(gap_list), args.workers):
            batch = []
            for gap_starter in gap_list[i:i + args.workers]:
                p = multiprocessing.Process(
                    target=run_multiprocessing,
                    args=(
                        gap_starter,
                        idx_size,
                        idx_year_class,
                        idx_residents,
                        idx_azimuth,
                        idx_tilt,
                        setted_gap,
                        effective_samples,
                        args.gap_size,
                        args.gap_size_saver,
                        args.building_type,
                        args.host_name,
                        args.output_dir,
                        args.mfh_profiles_dir,
                        args.sfh_profiles_dir,
                    ),
                )
                batch.append(p)
                p.start()

            for p in batch:
                p.join()

# START 19:09
