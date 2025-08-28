import pickle
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
from pathlib import Path
import pickle
from typing import Dict, Any, Iterable, List, Tuple, Optional
import math

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
def load_data(refurbishment_strategies,buildings_in_ueu):
    connection_setup = ["uncon"]
    ueu = "DENI03403000SEC5658"
    building_dict = {}
    base_dir = Path(
        r"C:\Users\hill_mx\Desktop\Paper UEC UEU\Ergebnisse\2025_08_26")
    building_dict = {}
    for building in buildings_in_ueu:
        building_dict[building] = {}
        for refurbishment in refurbishment_strategies:
            file_path = f"results_dec_processed_bds_in_{ueu}_{refurbishment}_no_EV_{building}.pkl"
            full_path = base_dir / file_path
            try:
                with open(
                        r"C:\Users\hill_mx\Desktop\Paper UEC UEU\Ergebnisse\2025_08_26/"+file_path,
                        "rb") as f:
                    data = pickle.load(f)
                    cleaned_data = remove_series(data)
                    building_dict[building][refurbishment] = cleaned_data
            except:
                print(building)
                print(refurbishment)
                building_dict[building][refurbishment] = None
    return building_dict

buildings_in_ueu = ["DENILD1100004s6k","DENILD1100004rAk","DENILD1100004tAY","DENILD1100004qZL","DENILD1100004rSr"]
refurbishment_strategies = ["no_refurbishment", "usual_refurbishment", "advanced_refurbishment", "GEG_standard"]

building_dict = load_data(refurbishment_strategies,buildings_in_ueu)
print("finished loadding")
with open(f"processed_08_26_results_of_DENI03403000SEC5658.pkl", "wb") as f:   # "wb" = write binary
    pickle.dump(building_dict, f, protocol=pickle.HIGHEST_PROTOCOL)

pareto_front_per_building = {}


# 1) Pareto je Gebäude & 2) kombinierte Front (mit moderatem ε beim Mergen + Cap)
per_bldg, combined_front = combine_all_buildings(
    building_dict,
    refurbishment_strategies=refurbishment_strategies,
    tau=1e-12,                      # Stricter dominance threshold
    eps_rel_each=(0.001, 0.001, 0.001),  # More precise pruning for each building
    eps_rel_merge=(0.005, 0.005, 0.005), # Stricter merging
    max_points_after_each_merge=8000    # Allow more points after each merge
)
with open(f"processed_08_26_combined_front_of_DENI03403000SEC5658.pkl", "wb") as f:   # "wb" = write binary
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


