import pickle
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
from pathlib import Path
import pickle
from typing import Dict, Any, Iterable, List, Tuple, Optional
import math
import pickle
from pathlib import Path
from datetime import date
import pandas as pd
import os
from pareto_optimal_help_functions import combine_all_buildings
def remove_series(obj):
    if isinstance(obj, dict):
        # durch Dict laufen und rekursiv behandeln
        return {k: remove_series(v) for k, v in obj.items() if not isinstance(v, pd.Series)}
    elif isinstance(obj, list):
        # falls Listen enthalten sind
        return [remove_series(v) for v in obj if not isinstance(v, pd.Series)]
    else:
        return obj
def scale_cleaned_data(cleaned_data):
    """
    Iterates over cleaned_data and scales co2, totex, and peak
    if buildings_in_cluster != buildings_in_cluster_used.

    Args:
        cleaned_data (dict): nested results dictionary

    Returns:
        dict: cleaned_data with scaled values
    """
    keys_to_delete = []

    for key, entry in cleaned_data.items():
        # Skip non-dicts
        if not isinstance(entry, dict):
            continue

        # Mark entries with None results for deletion
        if entry.get("results") is None:
            keys_to_delete.append(key)
            continue

        # Also mark if co2, totex, and peak are None
        if entry.get("co2") is None and entry.get("totex") is None and entry.get("peak") is None:
            keys_to_delete.append(key)
            continue

        results = entry.get("results", {})
        # iterate over all "buildings" inside results
        for building, b_data in results.items():
            if not isinstance(b_data, dict):
                continue
            if "buildings_in_cluster" in b_data and "buildings_in_cluster_used" in b_data:
                n_cluster = b_data["buildings_in_cluster"]
                n_used = b_data["buildings_in_cluster_used"]

                if n_cluster != n_used and n_used > 0:
                    scale_value = n_cluster / n_used

                    # scale co2, totex, peak at the *outer level*
                    if "co2" in entry:
                        entry["co2"] = entry["co2"] * scale_value
                    if "totex" in entry:
                        entry["totex"] = entry["totex"] * scale_value
                    if "peak" in entry:
                        entry["peak"] = entry["peak"] * scale_value

                    # optional: auch die oemof Unterwerte mitskalieren?
                    if "co2_oemof_model" in results:
                        results["co2_oemof_model"] = results["co2_oemof_model"] * scale_value
                    if "totex_oemof_model" in results:
                        results["totex_oemof_model"] = results["totex_oemof_model"] * scale_value
                    if "totex" in results:
                        results["totex"] = results["totex"] * scale_value
    # Remove all None-entries
    for k in keys_to_delete:
        cleaned_data.pop(k, None)
    return cleaned_data


import pickle
from pathlib import Path


def load_data(result_path,refurbishment_strategies, building_in_cluster,ueu,base_dir=None,scale_up_to_building_in_cluster=False,optimization_strategies =["co2","peak"]):
    base_dir = Path(result_path)

    print("Arbeitsverzeichnis:", base_dir)
    connection_setup = ["uncon"]
    building_dict = {}


    for building in building_in_cluster:
        building_dict[building] = {}
        for refurbishment in refurbishment_strategies:
            file_name = f"results_dec_processed_bds_in_{ueu}_{refurbishment}_no_EV_{building}.pkl"
            full_path = base_dir / file_name
            try:
                with open(full_path, "rb") as f:
                    data = pickle.load(f)

                    def key_has_allowed_strategy(k, optimization_strategies):
                        return isinstance(k, tuple) and len(k) >= 4 and k[3] in optimization_strategies

                    data = {
                        k: v
                        for k, v in data.items()
                        if key_has_allowed_strategy(k, optimization_strategies)
                    }
                    cleaned_data = remove_series(data)
                    if scale_up_to_building_in_cluster:
                        scaled_up_data = scale_cleaned_data(cleaned_data)# nehme an, deine Funktion existiert
                        building_dict[building][refurbishment] = scaled_up_data
                    else:
                        building_dict[building][refurbishment] = cleaned_data
            except FileNotFoundError:
                print(f"Datei fehlt: {full_path}")
                building_dict[building][refurbishment] = None
            except Exception as e:
                print(f"Fehler bei {building}, {refurbishment}: {e}")
                building_dict[building][refurbishment] = None

    return building_dict
def load_heat_grid_data(numbers, ueu="DENI03403000SEC5658", base_dir=None):
    import pickle
    from pathlib import Path

    # base_dir must be a Path
    base_dir = Path(base_dir) if base_dir is not None else Path.cwd()

    # normalize ueu (avoid "processed_bds_in_processed_bds_in_...")
    ueu = str(ueu)
    if ueu.startswith("processed_bds_in_"):
        ueu = ueu.replace("processed_bds_in_", "", 1)

    print("Arbeitsverzeichnis:", base_dir)
    print("UEU (normalized):", ueu)

    heat_grid_dict = {}

    for num in numbers:
        # this matches your real filenames, e.g.
        # results_heat_grid_60_processed_bds_in_DENI..._no_EV_capex_max_per_building.pkl
        base_prefix = f"results_heat_grid_{num}_processed_bds_in_{ueu}_no_EV"

        matching_files = sorted(base_dir.glob(f"{base_prefix}*.pkl"))

        if not matching_files:
            print(f"❌ Keine Dateien gefunden für num={num} (prefix: {base_prefix})")
            heat_grid_dict[num] = {}
            continue

        heat_grid_dict[num] = {}

        for path in matching_files:
            suffix = path.stem.replace(base_prefix, "")
            if suffix.startswith("_"):
                suffix = suffix[1:]
            suffix = suffix if suffix else "default"

            try:
                with open(path, "rb") as f:
                    heat_grid_dict[num][suffix] = pickle.load(f)
            except Exception as e:
                print(f"⚠️ Fehler bei {path.name}: {e}")
                heat_grid_dict[num][suffix] = None

    return heat_grid_dict

def process_building_dict(building_dict_heat_grid):
    """
    Process building data from `building_dict_heat_grid` and store the results in the desired format.

    Supports both structures:
      temperature -> key -> data
      temperature -> suffix -> key -> data
    """
    import numpy as np

    result_list = []

    for temperature, temp_dict in building_dict_heat_grid.items():

        for maybe_suffix, value in temp_dict.items():

            # FALL 1: alte Struktur (key -> data)
            if isinstance(value, dict) and "co2" in value:
                suffix = "default"
                building_items = {maybe_suffix: value}

            # FALL 2: neue Struktur (suffix -> key -> data)
            else:
                suffix = maybe_suffix
                building_items = value

            for key, data in building_items.items():

                if data.get("co2") is None or data.get("peak") is None:
                    continue

                selection = {
                    "key": key,
                    "heat_grid_temperature": temperature,
                    "variant": suffix,
                }

                results = data.get("results", {})

                results_clean = {
                    rk: {
                        kk: (float(v) if isinstance(v, (np.float64, np.float32)) else v)
                        for kk, v in rv.items()
                    } if isinstance(rv, dict) else (
                        float(rv) if isinstance(rv, (np.float64, np.float32)) else rv
                    )
                    for rk, rv in results.items()
                }

                result_list.append({
                    "co2": float(data["co2"]),
                    "peak": float(data["peak"]),
                    "totex": float(data["totex"]),
                    "selection": {**selection, **results_clean},
                })

    return result_list

centralized=True
ueus = ["processed_bds_in_DENI03403000SEC5658","processed_bds_in_DENI03403000SEC5101","processed_bds_in_DENI03403000SEC4580"]
refurbishment_strategies = ["no_refurbishment", "usual_refurbishment", "advanced_refurbishment", "GEG_standard"]
optimization_strategies = ["co2"] #["co2","peak"]
today_date = date.today().strftime("%Y_%m_%d")
heat_grid_supply_temperatures = [50,60,70,80]
for ueu in ueus :
    building_in_cluster = []
    base_path = os.path.dirname(os.path.abspath(__file__))

    directory_path = os.path.join(base_path, ueu)

    result_path = os.path.join(
    base_path,
    #"02_results_2026_01_14 annuity storage false"
)

    number_of_time_steps = 8760
    path_mfh = os.path.join(base_path, ueu, 'mfh_cluster.pkl')
    with open(path_mfh, "rb") as f:
        data = pickle.load(f)
    for _, row in data.iterrows():
        building_in_cluster.append(row["building_id"])

    path_sfh = os.path.join(base_path, ueu, 'sfh_cluster.pkl')
    with open(path_sfh, "rb") as f:
        data = pickle.load(f)
    for _, row in data.iterrows():
        building_in_cluster.append(row["building_id"])

    if centralized:

        building_dict = load_heat_grid_data(heat_grid_supply_temperatures,ueu,result_path)
        print("finished loadding")
        with open(f"cec_processed_"+str(today_date)+"_results_of_"+str(ueu.removeprefix("processed_bds_in_"))+".pkl", "wb") as f:   # "wb" = write binary
            pickle.dump(building_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
        combined_front = process_building_dict(building_dict)
        with open(f"cen_processed_"+str(today_date)+"_combined_front_of_"+str(ueu.removeprefix("processed_bds_in_"))+".pkl", "wb") as f:  # "wb" = write binary
            pickle.dump([building_dict, building_dict, combined_front], f, protocol=pickle.HIGHEST_PROTOCOL)
    else:
        building_dict = load_data(result_path,refurbishment_strategies,building_in_cluster,ueu.removeprefix("processed_bds_in_"),None,False,optimization_strategies)

        refurbishment_strategies = ["no_refurbishment", "usual_refurbishment", "advanced_refurbishment", "GEG_standard"]
        technologies = ["pv_system", "heat_storage", "battery", "gas_heater", "chp", "hp", "building"]
        carriers = ["Electricity", "NaturalGas", "BioGas", "Hydrogen"]
        for building in building_in_cluster:
            for refurbishment_strategy in refurbishment_strategies:
                for result_key in building_dict[building][refurbishment_strategy]:
                    totex = 0
                    result = building_dict[building][refurbishment_strategy][result_key]
                    if result["results"] is None:
                        continue
                    if result is None:
                        continue
                    for carrier in carriers:
                        totex += result["results"][carrier]["flow_from_grid_cost"]
                        if result["results"][carrier]["flow_into_grid_revenue"] is not None:
                            totex -= result["results"][carrier]["flow_into_grid_revenue"]
                    # Step 2: Add the totex for each technology
                    for technology in technologies:
                        # Check for multiple instances of technologies (like gas_heater_DENILD...)
                        tech_keys = [key for key in result["results"][building].keys() if
                                     key.startswith(f"{technology}_{building}")]
                        for tech_key in tech_keys:
                            tech_data = result["results"][building][tech_key]
                            if "investment_cost" in tech_data:
                                totex += tech_data["investment_cost"]
                    # Optional: If the 'building' itself has an 'investment_cost', add it as well
                    building_data = result["results"][building]
                    if "investment_cost" in building_data:
                        totex += building_data["investment_cost"]
                    building_dict[building][refurbishment_strategy][result_key]["totex_old"] = building_dict[building][refurbishment_strategy][result_key]["totex"]
                    building_dict[building][refurbishment_strategy][result_key]["totex"] = totex

        print("finished loadding")
        with open(f"dec_processed_"+str(today_date)+"_results_of_"+str(ueu.removeprefix("processed_bds_in_"))+".pkl", "wb") as f:   # "wb" = write binary
            pickle.dump(building_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
        variable_to_iterate = refurbishment_strategies
        pareto_front_per_building = {}

        per_bldg, combined_front = combine_all_buildings(
            building_dict,
            refurbishment_strategies=refurbishment_strategies,
            tau=1e-9, #12000
            eps_rel_each=(0.002, 0.002, 0.002),
            modes_each=('log', 'log', 'log'),
            eps_rel_merge=(0.008, 0.008, 0.008),
            modes_merge=('log', 'log', 'log'),
            max_points_after_each_merge=9000 #12000
        )
        print("per building avg front size:", sum(len(v) for v in per_bldg.values()) / max(len(per_bldg), 1))
        print("combined_front size:", len(combined_front))
        with open(f"dec_processed_"+str(today_date)+"_combined_front_of_"+str(ueu.removeprefix("processed_bds_in_"))+".pkl", "wb") as f:   # "wb" = write binary
            pickle.dump([building_dict,per_bldg,combined_front], f, protocol=pickle.HIGHEST_PROTOCOL)




def plot_combined_front(combined_front):
    co2   = [r['co2'] for r in combined_front]
    cost  = [r['totex'] for r in combined_front]
    peak  = [r['peak'] for r in combined_front]
    # 3D Plot
    plt.figure(figsize=(7,5))
    sc = plt.scatter(co2, cost, c=peak, cmap="viridis", s=5, alpha=0.7)
    plt.colorbar(sc, label="Peak (kW)")
    plt.xlabel("CO₂-eq in kg")
    plt.ylabel("Totex in €")
    plt.grid(True, alpha=0.3)
    plt.show()

plot_combined_front(combined_front)




def plot_only_1_strategy_with_reference_as_pareto():
    buildings = [
        "results_DENILD1100004rW0_no_refurbishment_.pkl",
    "results_DENILD1100004sZd_no_refurbishment_.pkl",
    "results_DENILD1100004u2T_no_refurbishment_.pkl",
    "results_DENILD1100004uSx_no_refurbishment_.pkl",
    #"results_DENILD1100004vsl_no_refurbishment_.pkl",
                 ]
    building_dict = {}
    # Loop over each building in the list
    for building in buildings:
        # Open the pickle file and load the content into the dictionary
        with open(building, "rb") as f:
            building_dict[building] = pickle.load(f)
            for key in building_dict[building]:
                if building_dict[building][key]["peak"] is not None:
                    building_dict[building][key]["peak"] = max(
                        building_dict[building][key]["results"]["Electricity"]["peak_into_grid"],
                        building_dict[building][key]["results"]["Electricity"]["peak_from_grid"])

    from collections import defaultdict

    # Fields to average
    fields = ['co2', 'totex', 'peak']

    # Nested dict to collect values: { key -> { field -> [values] } }
    grouped_values = defaultdict(lambda: defaultdict(list))

    # Loop over buildings and collect values
    for building, inner_dict in building_dict.items():
        for key, metrics in inner_dict.items():
            for field in fields:
                value = metrics.get(field)
                if value is not None:
                    grouped_values[key][field].append(value)

    # Compute averages for each key and field
    averages = {}

    for key, field_dict in grouped_values.items():
        averages[key] = {
            field: sum(vals) / len(vals)
            for field, vals in field_dict.items()
            if vals  # make sure list is not empty
        }

    # Optional: print results nicely
    for key, metrics in averages.items():
        print(f"\nKey: {key}")
        for field, avg in metrics.items():
            print(f"  {field}: {avg:.2f}")

    with open("results_representativeSFH_no_refurbishment_.pkl", "rb") as f:
        reference_building = pickle.load(f)
        for key in reference_building:
            if reference_building[key]["peak"] is not None:
                reference_building[key]["peak"] = max(
                    reference_building[key]["results"]["Electricity"]["peak_into_grid"],
                    reference_building[key]["results"]["Electricity"]["peak_from_grid"])

    # Extract average values
    avg_co2, avg_totex, avg_peak = [], [], []
    for key, val in averages.items():
        if all(k in val for k in ['co2', 'totex', 'peak']):
            avg_co2.append(val['co2'])
            avg_totex.append(val['totex'])
            avg_peak.append(val['peak'])

    # Extract reference building values
    ref_co2, ref_totex, ref_peak = [], [], []
    for key, val in reference_building.items():
        if all(k in val for k in ['co2', 'totex', 'peak']):
            ref_co2.append(val['co2'])
            ref_totex.append(val['totex'])
            ref_peak.append(val['peak'])


    # Plot
    plt.figure(figsize=(10, 6))

    # Average points
    sc1 = plt.scatter(avg_co2, avg_totex, c=avg_peak, cmap='Blues', s=150, edgecolor='darkred', label='Average values')

    # Reference points
    sc2 = plt.scatter(ref_co2, ref_totex, c=ref_peak, cmap='Blues', s=150, marker='^', edgecolor='darkred', label='Reference values')

    # Colorbar
    cbar = plt.colorbar(sc1)
    cbar.set_label('Peak Demand')

    # Labels & style
    plt.xlabel('Annual CO₂ Emissions in kg')
    plt.ylabel('Annual Total Expenditure (Totex)')
    plt.title('Average vs Reference Building Metrics for No Refurbishment')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


