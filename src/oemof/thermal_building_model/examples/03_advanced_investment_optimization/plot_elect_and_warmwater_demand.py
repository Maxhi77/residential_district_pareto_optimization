import os
import pickle
from oemof import solph
import numpy as np
from plot_pareto_front_dec import load_rep_info
from oemof.thermal_building_model.helpers import calculate_gain_by_sun
from oemof.thermal_building_model.helpers.path_helper import get_project_root
from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import ThermalBuilding
from oemof.thermal_building_model.helpers.calculate_pv_electricity_yield import simulate_pv_yield
from oemof.thermal_building_model.helpers import calculate_gain_by_sun
from oemof.thermal_building_model.helpers.path_helper import get_project_root
from oemof.thermal_building_model.input.economics.investment_components import battery_config,hot_water_tank_config,air_heat_pump_config,gas_heater_config,pv_system_config,chp_config
from oemof.thermal_building_model.oemof_facades.infrastructure.demands import ElectricityDemand, WarmWater
from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import PVSystem
import copy
import pandas as pd

def aggregate_district_from_df(data_classes_comp):
    # --- robust imports (falls in der Console was überschrieben wurde) ---
    import importlib
    np = importlib.import_module("numpy")  # holt garantiert das numpy-modul

    # --- Helfer: eine Zeile (row_name) über alle Spalten aufsummieren ---
    def sum_row(row_name: str):
        if row_name not in data_classes_comp.index:
            raise KeyError(f"Row '{row_name}' not found in DataFrame index.")

        s = data_classes_comp.loc[row_name].dropna()

        if len(s) == 0:
            return np.array([], dtype=float)

        arrays = []
        lengths = []

        for col, v in s.items():
            a = np.asarray(v, dtype=float).ravel()  # garantiert 1D float
            arrays.append(a)
            lengths.append(a.size)

        # alle müssen gleiche Länge haben
        if len(set(lengths)) != 1:
            bad = {col: np.asarray(v).size for col, v in s.items()}
            raise ValueError(
                f"Inconsistent lengths in row '{row_name}'. Lengths: {sorted(set(lengths))}. Details: {bad}"
            )

        return np.sum(np.vstack(arrays), axis=0)

    # --- Aggregation ---
    agg_heat = sum_row("heating_demand")
    agg_el   = sum_row("electricity_demand")
    agg_pv   = sum_row("pv_system_max")

    # optional: warm water, falls vorhanden
    agg_ww = sum_row("warm_water_demand") if "warm_water_demand" in data_classes_comp.index else None

    out = {
        "aggregated_heat_demand": agg_heat.tolist(),
        "aggregated_warm_water_demand" : agg_ww.tolist(),
        "aggregated_electricity_demand": agg_el.tolist(),
        "aggregated_pv_system_max": agg_pv.tolist(),
    }


    return out


# --- usage ---

def process_cluster(building_row, building_type, epw_path, directory_path, data, refurbish, number_of_time_steps,data_classes_comp,ev,time_index,number_of_buildings_in_cluster,roof_pitch_angle):

        building_id = building_row['building_id']
        tabula_year_class = building_row['tabula_year_class']
        building_floor_area = building_row['net_floor_area']
        number_of_occupants = building_row['number_of_residents']
        number_of_households = building_row['number_of_apartments']
        if number_of_buildings_in_cluster is  None:
            number_of_buildings_in_cluster = building_row['buildings_in_cluster']
        # Zuordnung Baujahr
        year_map = {
            1: 1850, 2: 1910, 3: 1930, 4: 1950,
            5: 1960, 6: 1970, 7: 1980, 8: 1990,
            9: 2000, 10: 2005, 11: 2010, 12: 2020
        }
        year_of_construction = year_map.get(tabula_year_class, 2000)  # fallback
        print(building_id)
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
        # PV-Ertrag pro Watt
        pv_yield_per_wp = simulate_pv_yield(
            pv_nominal_power_in_watt=1,
            tilt=roof_pitch_angle,
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
        pv_value = [value * number_of_buildings_in_cluster for value in pv.value_list]
        pv_value = [value * pv.investment_component.maximum_capacity for value in pv_value]

        n = int(number_of_buildings_in_cluster)

        electricity_scaled = (np.asarray(electricity_demand.value_list, dtype=float) * n).tolist()
        building_heating_demand = (np.asarray(building.value_list, dtype=float) * n).tolist()
        warmwater_scaled = (np.asarray(heat_demand.value_list, dtype=float) * n).tolist()
        data_classes_comp[building_id] = {"electricity_demand":electricity_scaled,
                                          "pv_system_max":pv_value,
                                          "heating_demand":building_heating_demand,
                                          "warm_water_demand":warmwater_scaled,
                                          "building_type":building_type}
        return data_classes_comp
ueu_list = [
    "processed_bds_in_DENI03403000SEC5658",
    "processed_bds_in_DENI03403000SEC4580",
    "processed_bds_in_DENI03403000SEC5101",
]

base_path = r"C:\Users\hill_mx\Desktop\From Luis\Case Studies\Small New"
out_dir   = r"C:\Users\hill_mx\Desktop\UEU testing results"

if True:
    result_name = "cen_processed_2026_01_17_combined_front_of_"
    cen_or_dec = "cen"
else:
    result_name = "dec_processed_2026_01_16_combined_front_of_"  # cen
    cen_or_dec = "dec"
width_cm  = 15.11293
height_cm = 6.5 * 1.8
width_inch  = width_cm / 2.54
height_inch = height_cm / 2.54
font_size = 9
ev = "no_EV"
# ============================================================
# LOOP OVER UEUs
# ============================================================
for all_buildings in [False]:
    for ueu in ueu_list:
        print(ueu)
        ueu_short = ueu.removeprefix("processed_bds_in_")
        print(f"\n=== UEU: {ueu_short} ===")

        # ---- input paths for rep info ----
        if all_buildings:
            import geopandas as gpd
            import os

            path_ueu = os.path.join(base_path, ueu + ".gpkg")

            ueu_all = gpd.read_file(path_ueu)

            total_floor_area_all = sum(ueu_all["net_floor_area"])
            total_number_of_residents = sum(ueu_all["number_of_residents"])
            import ast
            import re
            import numpy as np


            def parse_list_cell(x):
                # already a real list/tuple/np array
                if isinstance(x, (list, tuple, np.ndarray)):
                    return list(x)

                # NaN/None
                if x is None or (isinstance(x, float) and np.isnan(x)):
                    return []

                # string case
                if isinstance(x, str):
                    s = x.strip()

                    # replace np.float64(3.0) -> 3.0  (also handles np.int64(...), np.float32(...), etc.)
                    s = re.sub(r"np\.\w+\(([^()]*)\)", r"\1", s)

                    # now safe literal_eval
                    try:
                        v = ast.literal_eval(s)
                    except Exception:
                        return []  # fallback: treat as empty if malformed

                    # ensure list
                    if isinstance(v, (list, tuple, np.ndarray)):
                        return list(v)
                    else:
                        return [v]

                # any other scalar -> treat as single entry
                return [x]


            # total number of list entries across all rows
            total_len = ueu_all["list_number_of_adults"].apply(lambda x: len(parse_list_cell(x))).sum()
            total_number_of_households = total_len
        else:
            path_mfh = os.path.join(base_path, ueu, "mfh_cluster.pkl")
            path_sfh = os.path.join(base_path, ueu, "sfh_cluster.pkl")
            sfh_cluster_path = os.path.join(base_path, ueu, 'sfh_cluster.pkl')
            with open(sfh_cluster_path, 'rb') as f:
                sfh_cluster = pickle.load(f)
            mfh_cluster_path = os.path.join(base_path, ueu, 'mfh_cluster.pkl')
            with open(mfh_cluster_path, 'rb') as f:
                mfh_cluster = pickle.load(f)
            sfh_rep_info = load_rep_info(path_sfh, "SFH", numeric=False)
            mfh_rep_info = load_rep_info(path_mfh, "MFH", numeric=False)

            rep_info = {**sfh_rep_info, **mfh_rep_info}
            building_in_cluster = list(rep_info.keys())
            total_floor_area_all = sum(info["net_floor_area"] for info in rep_info.values())
            total_number_of_households = sum(info["number_of_households"] for info in rep_info.values())
            total_number_of_residents = sum(info["number_of_residents"] for info in rep_info.values())
            print("Total floor area:", total_floor_area_all)


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

        refurbish = "no_refurbishment"
        directory_path = r"C:\Users\hill_mx\Desktop\From Luis\Case Studies\Small New\\" + ueu

        main_path = get_project_root()
        data = pd.DataFrame()
        data["air_temperature"] = location.weather_data["drybulb_C"].to_list()
        number_of_time_steps = 8760
        date_time_index = solph.create_time_index(2025, number=number_of_time_steps - 1)
        data.index = date_time_index
        if all_buildings:
            for index, building_row in ueu_all.iterrows():
                data = process_cluster(
                    building_row=building_row,
                    building_type=building_row["tabula_building_type"],
                    epw_path=epw_path,
                    directory_path=directory_path,
                    data=data,
                    refurbish=refurbish,
                    number_of_time_steps=number_of_time_steps,
                    data_classes_comp = data_classes_comp,
                    ev=ev,
                    time_index=date_time_index,
                    number_of_buildings_in_cluster = 1,
                    roof_pitch_angle=building_row["roof_pitch_angle"]

                )
        else:
            for index, building_row in sfh_cluster.iterrows():
                data = process_cluster(
                    building_row=building_row,
                    building_type="SFH",
                    epw_path=epw_path,
                    directory_path=directory_path,
                    data=data,
                    refurbish=refurbish,
                    number_of_time_steps=number_of_time_steps,
                    data_classes_comp = data_classes_comp,
                    ev=ev,
                    time_index=date_time_index,
                    roof_pitch_angle = building_row["avg_roof_pitch_angle"],
                    number_of_buildings_in_cluster=None
                )
            for index, building_row in mfh_cluster.iterrows():
                data = process_cluster(
                    building_row=building_row,
                    building_type="MFH",
                    epw_path=epw_path,
                    directory_path=directory_path,
                    data=data,
                    refurbish=refurbish,
                    number_of_time_steps=number_of_time_steps,
                    data_classes_comp = data_classes_comp,
                    ev =ev,
                    time_index=date_time_index,
                    roof_pitch_angle=building_row["avg_roof_pitch_angle"],
                    number_of_buildings_in_cluster=None

                )
        print(data)
        import numpy as np

        file_path_ueu = os.path.join(main_path,ueu+'_data_all_'+str(all_buildings)+'_'+ev+'.pkl')

        data.to_pickle(file_path_ueu)
        # Ensure numpy array is available
        # Double-check that np.array is not overwritten anywhere in your code

        import builtins

        aggregated_data = aggregate_district_from_df(data)

        # Example usage:
        # Define the file path where you want to save the DataFrame
        file_path_aggregated = os.path.join(main_path,ueu+'_data_aggregated_all_'+str(all_buildings)+'_'+ev+'.pkl')

        # Save the DataFrame as a pickle file
        import pickle

        with open(file_path_aggregated, "wb") as f:
            pickle.dump(aggregated_data, f)


