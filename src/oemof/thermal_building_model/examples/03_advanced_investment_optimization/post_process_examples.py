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
Number = float
import pandas as pd
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
    for key, entry in cleaned_data.items():
        if not isinstance(entry, dict):
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
    return cleaned_data


import pickle
from pathlib import Path


def load_data(refurbishment_strategies, buildings_in_ueu,base_dir=None):
    if base_dir is None:
        base_dir = Path.cwd()
    else:
        base_dir = Path(base_dir)

    print("Arbeitsverzeichnis:", base_dir)
    connection_setup = ["uncon"]
    ueu = "DENI03403000SEC5658"
    building_dict = {}


    for building in buildings_in_ueu:
        building_dict[building] = {}
        for refurbishment in refurbishment_strategies:
            file_name = f"results_dec_processed_bds_in_{ueu}_{refurbishment}_no_EV_{building}.pkl"
            full_path = base_dir / file_name
            try:
                with open(full_path, "rb") as f:
                    data = pickle.load(f)

                    cleaned_data = remove_series(data)
                    scaled_up_data = scale_cleaned_data(cleaned_data)# nehme an, deine Funktion existiert
                    building_dict[building][refurbishment] = scaled_up_data
            except FileNotFoundError:
                print(f"Datei fehlt: {full_path}")
                building_dict[building][refurbishment] = None
            except Exception as e:
                print(f"Fehler bei {building}, {refurbishment}: {e}")
                building_dict[building][refurbishment] = None

    return building_dict

def load_heat_grid_data(numbers, ueu="DENI03403000SEC5658", base_dir=None):

    if base_dir is None:
        base_dir = Path.cwd()
    else:
        base_dir = Path(base_dir)

    print("Arbeitsverzeichnis:", base_dir)

    heat_grid_dict = {}

    for num in numbers:
        file_name = f"results_heat_grid_{num}_processed_bds_in_{ueu}_no_EV.pkl"
        full_path = base_dir / file_name
        try:
            with open(full_path, "rb") as f:
                data = pickle.load(f)
                heat_grid_dict[num] = data
        except FileNotFoundError:
            print(f"❌ Datei fehlt: {full_path}")
            heat_grid_dict[num] = None
        except Exception as e:
            print(f"⚠️ Fehler bei {num}: {e}")
            heat_grid_dict[num] = None

    return heat_grid_dict


def process_building_dict(building_dict_heat_grid):
    """
    Process building data from `building_dict_heat_grid` and store the results in the desired format.

    Parameters:
    building_dict_heat_grid (dict): Input dictionary containing building data.

    Returns:
    result_list (list): Processed list of building results in the required format.
    """
    result_list = []

    # Iteriere über jedes Gebäude (Temperatur 50, 60, etc.)
    for temperature in building_dict_heat_grid:
        for key in building_dict_heat_grid[temperature]:
            data = building_dict_heat_grid[temperature][key]

            # Wenn co2 oder peak None sind, überspringe das aktuelle Gebäude
            if data['co2'] is None or data['peak'] is None:
                continue

            # Erstelle die Auswahlstruktur für das Ergebnis
            selection = {
                'key': key,
                'heat_grid_temperature': temperature
            }

            # Extrahiere das Resultat (mit entferntem Series)
            results = data.get('results', {})

            # Wenn 'results' ein dict ist, gehe mit .items() durch, ansonsten behandle es als Wert
            # Hier werden die Ergebnisse in den "selection"-Schlüssel eingefügt
            results_clean = {
                key: {
                    kk: (float(v) if isinstance(v, (np.float64, np.float32)) else v)
                    for kk, v in vv.items() if isinstance(vv, dict)
                } if isinstance(vv, dict) else float(vv)
                for key, vv in results.items()
            }

            # Füge das Ergebnis zur Liste hinzu
            result_list.append({
                'co2': float(data['co2']),
                'peak': float(data['peak']),
                'totex': float(data['totex']),
                'selection': {**selection, **results_clean}  # Die "results" werden unter "selection" eingefügt
            })

    return result_list
centralized=False
buildings_in_ueu = ["DENILD1100004s6k","DENILD1100004rAk","DENILD1100004tAY","DENILD1100004qZL","DENILD1100004rSr"]
refurbishment_strategies = ["no_refurbishment", "usual_refurbishment", "advanced_refurbishment", "GEG_standard"]
heat_grid_supply_temperatures = [50,60,70,80]

if centralized:
    building_dict = load_heat_grid_data(heat_grid_supply_temperatures)
    print("finished loadding")
    with open(f"dec_processed_08_26_results_of_DENI03403000SEC5658.pkl", "wb") as f:   # "wb" = write binary
        pickle.dump(building_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
    combined_front = process_building_dict(building_dict)
    with open(f"cen_processed_08_26_combined_front_of_DENI03403000SEC5658.pkl", "wb") as f:  # "wb" = write binary
        pickle.dump([building_dict, building_dict, combined_front], f, protocol=pickle.HIGHEST_PROTOCOL)
else:
    building_dict = load_data(refurbishment_strategies,buildings_in_ueu)
    print("finished loadding")
    with open(f"cen_processed_08_26_results_of_DENI03403000SEC5658.pkl", "wb") as f:   # "wb" = write binary
        pickle.dump(building_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
    variable_to_iterate = refurbishment_strategies
    pareto_front_per_building = {}


    per_bldg, combined_front = combine_all_buildings(
        building_dict,
        refurbishment_strategies=refurbishment_strategies,
        tau=1e-9,
        # pro Gebäude feiner in Totex
        eps_rel_each=(0.003, 0.003, 0.001), # co2, peak, totex
        modes_each=('log','log','log'),
        scales_each=(1.0, 1.0, 1.0),
        # beim Mergen etwas gröber, Totex weiterhin feiner
        eps_rel_merge=(0.01, 0.01, 0.003),
        modes_merge=('log','log','log'),
        scales_merge=(1.0, 1.0, 1.0),
        max_points_after_each_merge=7000
    )
    with open(f"dec_processed_08_26_combined_front_of_DENI03403000SEC5658.pkl", "wb") as f:   # "wb" = write binary
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


