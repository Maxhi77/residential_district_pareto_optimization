
from oemof.thermal_building_model.oemof_facades.infrastructure.grids import ElectricityGrid, HeatGrid, GasGrid
from oemof.thermal_building_model.oemof_facades.infrastructure.carriers import ElectricityCarrier, HeatCarrier, \
    GasCarrier
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses, flatten_components_list
from oemof.thermal_building_model.oemof_facades.infrastructure.demands import ElectricityDemand, WarmWater
from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import PVSystem
from oemof.thermal_building_model.oemof_facades.technologies.storages import Battery, HotWaterTank
from oemof.thermal_building_model.oemof_facades.technologies.converter import AirHeatPump, GasHeater
from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import ThermalBuilding
from oemof import solph
import random
from oemof.thermal_building_model.input.economics.investment_components_sobol import battery_config,hot_water_tank_config,air_heat_pump_config,gas_heater_config,pv_system_config
import copy
import os
import pickle
import multiprocessing
from SALib.sample import saltelli

def main(target_residents,building_id, floor_area,demand_path,heating_system,refurbishment_status_tabula):
    solver = "gurobi"  # 'glpk', 'gurobi',....
    number_of_time_steps = 8760


    date_time_index = solph.create_time_index(
        2012, number=number_of_time_steps-1)
    es = solph.EnergySystem(timeindex=date_time_index,
                            infer_last_interval=False)

    electricity_grid_dataclass = ElectricityGrid()


    electricity_grid_bus_from_grid = electricity_grid_dataclass.get_bus_from_grid()
    electricity_grid_bus_into_grid = electricity_grid_dataclass.get_bus_into_grid()
    electricity_grid_sink = electricity_grid_dataclass.create_sink()
    electricity_grid_source = electricity_grid_dataclass.create_source()
    electricity_carrier_dataclass = ElectricityCarrier()
    electricity_carrier_bus = electricity_carrier_dataclass.get_bus()
    connect_buses(input=electricity_grid_bus_from_grid, target=electricity_carrier_bus, output=electricity_grid_bus_into_grid)
    electricity_demand_dataclass = ElectricityDemand(demand_path = demand_path+'/SumProfiles.Electricity.csv',
                                                    bus=electricity_carrier_bus)
    electricity_demand = electricity_demand_dataclass.create_demand()

    electricity  = [electricity_grid_bus_from_grid,
                    electricity_grid_bus_into_grid,
                    electricity_grid_sink,
                    electricity_grid_source,
                    electricity_carrier_bus,
                    electricity_demand]


    heat_grid_temperature_levels = [40]
    if False:
        heat_grid_dataclass = HeatGrid(investment=True)

        heat_grid_source = heat_grid_dataclass.create_source()
        heat_grid_bus_from_grid = heat_grid_dataclass.get_bus_from_grid()
        connect_buses(
            input=heat_grid_bus_from_grid,
            target=heat_carrier_bus)
    heat_carrier_temperature_levels = [40,50,60,70,80,90]
    heat_carrier_dataclass = HeatCarrier(levels = heat_carrier_temperature_levels)

    heat_carrier_bus = heat_carrier_dataclass.get_bus()


    heat_demand_dataclass = WarmWater(name="WarmWater",
                                       level = 40,
                                       bus=heat_carrier_bus[40],
                                        demand_path=demand_path+'/SumProfiles.Warm Water.csv')
    heat_demand = heat_demand_dataclass.create_demand()
    hot_water_tank_config_building = copy.deepcopy(hot_water_tank_config)


    hot_water_tank_dataclass = HotWaterTank(
        name="heat_storage",
        investment=True,
        temperature_buses=heat_carrier_bus,
        max_temperature=80,
        min_temperature=min(heat_carrier_bus),
        investment_component=hot_water_tank_config_building,
        input_bus=heat_carrier_bus[70],
        output_bus=heat_carrier_bus[70],
    )
    hot_water_tank = hot_water_tank_dataclass.create_storage()

    es.add(hot_water_tank)

    if heating_system==0:
        air_heat_pump_dataclass = AirHeatPump(heat_carrier_bus= heat_carrier_dataclass.get_bus(),
                                              investment=True,
                                              investment_component=air_heat_pump_config)
        air_heat_pump_bus = air_heat_pump_dataclass.get_bus()
        air_heat_pump= air_heat_pump_dataclass.create_source()
        air_heat_pump_converters= air_heat_pump_dataclass.create_converters(heat_pump_bus = air_heat_pump_bus,
                                                                         electricity_bus = electricity_carrier_bus,
                                                                         heat_carrier_bus=heat_carrier_dataclass.get_bus())
        es.add(air_heat_pump_bus,air_heat_pump,*air_heat_pump_converters)

    gas_grid_dataclass = GasGrid()
    gas_grid_bus_from_grid = gas_grid_dataclass.get_bus_from_grid()
    gas_grid_source = gas_grid_dataclass.create_source()

    gas_carrier_dataclass = GasCarrier()
    gas_bus = gas_carrier_dataclass.get_bus()
    connect_buses(input=gas_grid_bus_from_grid, target=gas_bus)
    if heating_system==1:
        gas_heater_dataclass = GasHeater(investment=True,
                                         investment_component=gas_heater_config)
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

    battery_dataclass = Battery(investment=True,
                                input_bus = electricity_carrier_bus,
                                output_bus = electricity_carrier_bus,
                                investment_component=battery_config)
    battery = battery_dataclass.create_storage()
    es.add(battery)



    building_dataclass = ThermalBuilding(name=building_id,
                                         building_type="SFH",
                                         number_of_occupants=target_residents,
                                         floor_area = floor_area,
                                          country="DE",
                                          construction_year=1980,
                                          class_building="average",
                                          heat_level_calculation = True,
                                          number_of_time_steps=number_of_time_steps,
                                         time_index=date_time_index,
                                         refurbishment_status=refurbishment_status_tabula,
                                          )
    building_dataclass.bus = heat_carrier_bus[building_dataclass.level_heating_demand]
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

    pv_dataclass = PVSystem(investment=True,
                            investment_component=pv_system_config)
    pv_dataclass.update_maximum_investment_pv_capacity_based_on_area(area=building_dataclass.get_roof_area_for_pv())
    pv_system = pv_dataclass.create_source(output_bus = electricity_carrier_bus,

                             )
    es.add(pv_system)

    electricity_components = flatten_components_list(electricity)
    heat_components = flatten_components_list(heat)
    # Add all components to the energy system in one go
    # Add all components to the energy system in one go
    es.add(*(heat_components))
    es.add(*(electricity_components))
    model = solph.Model(es)


    model = solph.constraints.additional_total_limit(model, "co2", limit=10000000)
    # Show the graph
    # Show the graph

    try:
        print("__________")
        print("start for:")


        model.solve(solver=solver, solve_kwargs={"tee": True})
        meta_results = solph.processing.meta_results(model)
        results = solph.processing.results(model)
        final_results = {}
        final_results[hot_water_tank_dataclass.name] = hot_water_tank_dataclass.post_process(results,hot_water_tank)

        final_results[battery_dataclass.name] = battery_dataclass.post_process(results,battery)

        final_results[electricity_grid_dataclass.name] = electricity_grid_dataclass.post_process(results,electricity_grid_source,electricity_grid_sink
                                                )
        final_results[gas_grid_dataclass.name] = gas_grid_dataclass.post_process(results,gas_grid_source,None
                                                )
        #final_results[heat_grid_dataclass.name] = heat_grid_dataclass.post_process(results,heat_grid_source,None)
        if heating_system==1:
            final_results[gas_heater_dataclass.name] = gas_heater_dataclass.post_process(results,gas_heater,gas_heater_converters,heat_carrier_bus,gas_bus)
        if heating_system==0:
            final_results[air_heat_pump_dataclass.name] = air_heat_pump_dataclass.post_process(results,air_heat_pump,air_heat_pump_converters,heat_carrier_bus,electricity_carrier_bus)

        final_results[pv_dataclass.name] = pv_dataclass.post_process(results,pv_system)

        final_results[building_dataclass.name] = building_dataclass.post_process(results,building_component)

        final_results[electricity_demand_dataclass.name] = electricity_demand_dataclass.post_process(results,electricity_demand)

        final_results[heat_demand_dataclass.name] = heat_demand_dataclass.post_process(results,heat_demand)


        final_results["co2_post_process"] = (final_results[battery_dataclass.name]["investment_co2"
                                ]+final_results[hot_water_tank_dataclass.name]["investment_co2"
                                ]+(final_results[gas_heater_dataclass.name]["investment_co2"
                                ]if heating_system == 1 else 0)+(final_results[air_heat_pump_dataclass.name]["investment_co2"
                                ]if heating_system == 0 else 0)+final_results[pv_dataclass.name]["investment_co2"
                                ]+final_results[building_dataclass.name]["investment_co2"]
                                #+final_results[heat_grid_dataclass.name]["investment_co2"]
                                +final_results[electricity_grid_dataclass.name]["flow_from_grid_co2"
                                ]-final_results[electricity_grid_dataclass.name]["flow_into_grid_co2"
                                ]+final_results[gas_grid_dataclass.name]["flow_from_grid_co2"
                                ])
        co2 = model.total_limit_co2()

        print("co2_constraint: ", co2)
        print("co2_manuel: ", final_results["co2_post_process"])
        print("objective",str(meta_results["objective"]))
        final_results["co2_oemof_model"] = co2
        final_results["totex"] = meta_results["objective"]

        return final_results, co2
    except Exception as e:
        print(e)
        return None, None


# 1. Problem definieren
problem = {
    'num_vars': 6,
    'names': ['net_floor_area', 'tabula_year_class', 'number_of_residents',
              'household_type',"refurbishment_status","heating_system"],
    'bounds': [
        [80, 360],      # Wohnfläche in m²
        [1, 11],        # tabula_year_class (1-11 Klassen)
        [0, 1],         # Bewohner
        [0, 2],         # household type
        [0, 2],         # Sanierungsstand 0 = nicht, 1 = normal, 2 = advanced
        [0, 1]          # Heizung: 0 = HP, 1 = Burning
    ]
}
# Sampling (kleine Anzahl für Test)
param_values = saltelli.sample(problem, int(128*2**5), calc_second_order=True)
# laut chat gpt bei 6 params sollte man n=	2048+ für gute Ergebnisse, das wären 16.000 Durchläufe
# Spaltenindex merken
idx_size = problem['names'].index('net_floor_area')
idx_year_class = problem['names'].index('tabula_year_class')
idx_residents = problem['names'].index('number_of_residents')
idx_household_type = problem['names'].index('household_type')
idx_refurbishment_status = problem['names'].index('refurbishment_status')
idx_heating_system = problem['names'].index('heating_system')
# Runden der gewünschten Variablen
# Mapping
from different_household_models import households_adult_only,households_with_seniors,households_with_families, get_resident_range
household_dicts = {
    0: households_with_seniors,
    1: households_with_families,
    2: households_adult_only
}

resident_ranges = get_resident_range(household_dicts)
gap_starter = 0

def run_multiprocessing(gap_starter,
                        idx_size,
                        idx_year_class,
                        idx_residents,
                        idx_household_type,
                        idx_refurbishment_status,
                        idx_heating_system,
                        household_dicts,
                        resident_ranges):
    # Beispiel-Durchlauf
    results_loop_to_save = {}
    counter = 0
    # Beispiel-Durchlauf
    for params in param_values:
        if (gap_starter+1) * 9000<counter:
            counter += 1
            continue
        if counter < gap_starter*9000:
            counter += 1
            continue
        heating_system=int(params[idx_heating_system])
        refurbishment_status = int(params[idx_refurbishment_status])
        building_size = params[idx_size]
        household_type = int(params[idx_household_type])
        normalized_residents = params[idx_residents]
        min_r, max_r = resident_ranges[household_type]
        target_residents = round(min_r + normalized_residents * (max_r - min_r))

        tabula_year_class = int(params[idx_year_class])  # Die Nummer, die du brauchst


        # Passende Haushalte filtern
        possible_households = [
            (name, res) for name, res in household_dicts[household_type].items()
            if res == target_residents
        ]

        if possible_households:
            chosen_household, _ = random.choice(possible_households)
        else:
            chosen_household = "Kein passender Haushalt gefunden"
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

        if refurbishment_status == 0:
            refurbishment_status_tabula ="no_refurbishment"
        elif refurbishment_status == 1:
            refurbishment_status_tabula="usual_refurbishment"
        elif refurbishment_status == 2:
            refurbishment_status_tabula="advanced_refurbishment"
        tabula_building_code = f"DE.N.SFH.{tabula_year_class:02d}.Gen.ReEx.001.001"

        print(f"Typ: {household_type}, Ziel-Bewohner: {target_residents}, Haushalt: {chosen_household}")
        print(f"TABULA-Code: {year_of_construction}\n")
        print("building size: " +str(building_size) )
        print("counter: " + str(counter))
        import re


        def format_household_key(chosen_household):
            match = re.match(r"CHR0?(\d+)", chosen_household)
            if match:
                number = int(match.group(1))  # int entfernt führende Nullen
                return f"Results_CHH_{number}"  # ohne führende Null
            else:
                return "Results_INVALID"
        result_key = format_household_key(chosen_household)
        #demand_path = fr'C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model\examples\04_advanced_investment_optimization_sobol_analysis\lpg_profiles\{result_key}'
        demand_path = f'/home/hill_mx/thermal_building_clone/src/oemof/thermal_building_model/examples/04_advanced_investment_optimization_sobol_analysis/lpg_profiles/{result_key}'

        final_results, co2  = main(target_residents,tabula_building_code, building_size,demand_path,heating_system,refurbishment_status_tabula)
        totex = final_results["totex"]
        peak = (final_results["Electricity"]["peak_into_grid"],
        final_results["Electricity"]["peak_from_grid"])
        results_loop_to_save[(counter,building_size, household_type,target_residents,year_of_construction)] = {
                "results": final_results,

                "co2": co2,
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
        if counter % 1000== 0 or counter %( len(param_values)-1)== 0:
            file_path="results_sobol_"+str(gap_starter)+"_"+str(counter)+".pkl"
            # If the file doesn't exist, create it and save the results
            existing_results = results_loop_to_save
            print(f"New results created for {file_path}")

            # Save the updated or new results back to the pickle file
            with open(file_path, "wb") as f:
                pickle.dump(existing_results, f)
            # Save the updated or new results back to the pickle file
            results_loop_to_save = {}
        counter += 1
if __name__ == "__main__":
    gap_values = range(10)  # Gap von 0 bis 9
    processes = []
    for gap_starter in gap_values:
        p = multiprocessing.Process(target=run_multiprocessing, args=(gap_starter,
                        idx_size,
                        idx_year_class,
                        idx_residents,
                        idx_household_type,
                        idx_refurbishment_status,
                        idx_heating_system,
                        household_dicts,
                        resident_ranges))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

