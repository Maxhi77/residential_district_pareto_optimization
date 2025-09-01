
import pickle
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
from pathlib import Path
import pickle
from typing import Dict, Any, Iterable, List, Tuple, Optional
import math
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.cm as cm

import pickle

import copy
import numpy as np

def _to_float(x):
    if isinstance(x, (np.generic,)):
        return float(x)
    return x

def process_units_for_processed(
    processed_district_data,
    *,
    # Global divisors
    cost_divisor=1.0,          # e.g. 1000 for k€
    co2_divisor=1.0,           # e.g. 1.0 keep as-is
    peak_divisor=1.0,          # e.g. 1000 for MW
    # Capacity handling
    power_capacity_divisor=1.0,      # kW -> MW: 1000
    heat_storage_name="Heat storage",
    # Heat storage is given as V [m³], convert to energy [kWh]
    hs_delta_T_K=40.0,               # temperature gap
    hs_density_kg_per_m3=1000.0,     # water
    hs_c_Wh_per_kgK=1.163,           # specific heat
    # After conversion to kWh, optionally scale to MWh etc.
    # Where to store the converted energy capacity
    hs_target_key="energy_capacity_kWh"  # or keep "capacity" if you prefer
):
    """
    Scales costs, CO2, and capacities for processed_district_data.

    - Non-heat-storage 'capacity' is treated as POWER and scaled by power_capacity_divisor (e.g., kW->MW).
    - Heat storage 'capacity' is given in m³; it is converted to ENERGY (kWh) using ΔT and water properties,
      then scaled by heat_storage_energy_divisor (e.g., kWh->MWh).
    - Stores the converted HS energy under hs_target_key, leaving original 'capacity' (m³) intact for traceability.
      Set hs_target_key='capacity' if you want to overwrite it.

    Top-level keys handled: 'co2', 'peak', 'totex'.
    """
    out = copy.deepcopy(processed_district_data)

    # Precompute m³ -> kWh factor for given ΔT
    m3_to_kWh = (hs_density_kg_per_m3 * hs_c_Wh_per_kgK * hs_delta_T_K) / 1000.0
    # Example: 1000 * 1.163 * 40 / 1000 = 46.52 kWh per m³

    for _, district in out.items():
        # Top-level scalars
        if 'co2' in district:
            district['co2'] = _to_float(district['co2']) / co2_divisor
        if 'totex' in district:
            district['totex'] = _to_float(district['totex']) / cost_divisor
        if 'peak' in district:
            district['peak'] = _to_float(district['peak']) / peak_divisor

        # Nested groups (e.g., 'DENILD1100004s6k', ...)
        for key, sub in list(district.items()):
            if key in ('co2', 'peak', 'totex'):
                continue
            if not isinstance(sub, dict):
                continue

            for tech_or_carrier, vals in sub.items():
                if not isinstance(vals, dict):
                    continue

                # cost / co2
                if 'cost' in vals:
                    vals['cost'] = _to_float(vals['cost']) / cost_divisor
                if 'co2' in vals:
                    vals['co2'] = _to_float(vals['co2']) / co2_divisor

                # capacity handling
                if 'capacity' in vals:
                    cap_val = _to_float(vals['capacity'])

                    if tech_or_carrier == heat_storage_name:
                        # Save original m³
                        vals['capacity_in_m3'] = cap_val

                        # Convert to kWh
                        energy_kWh = cap_val * m3_to_kWh
                        # Scale (e.g. to MWh if power_capacity_divisor=1000)
                        energy_scaled = energy_kWh / power_capacity_divisor

                        # Overwrite capacity with converted energy
                        vals['capacity'] = energy_scaled

                    else:
                        # Non-heat-storage: treat as POWER (e.g., kW) and scale
                        vals['capacity'] = cap_val / power_capacity_divisor

    return out
def reduce_pareto_points(combined_points):
    # Step 2: Combine both lists


    # Step 3: Sort the list based on cost (second element of the tuple)
    combined_points.sort(key=lambda x: x[1])  # Sorting by the cost value (second element)

    # Step 4: Remove every second point, keeping the first and last
    reduced_points = [combined_points[0]]  # Keep the first point
    for i in range(1, len(combined_points) - 1, 2):  # Start from the second point, step by 2
        reduced_points.append(combined_points[i])

    reduced_points.append(combined_points[-1])  # Keep the last point

    return reduced_points
# Function to select evenly spaced points along the Pareto front
def select_evenly_spaced_pareto_points_focus_y_axis(pareto_front, num_points=10):
    # Unpack the Pareto front into two lists (co2 and cost)
    co2, cost = zip(*pareto_front)

    # Convert to numpy arrays for easier manipulation
    co2 = np.array(co2)
    cost = np.array(cost)

    # Logarithmic scaling for cost (y-axis)
    cost = np.log(cost + 1)  # Logarithm of cost (adding 1 to avoid log(0) issues)

    # Calculate the Euclidean distance between consecutive points
    distances = np.sqrt(np.diff(co2) ** 2 + np.diff(cost) ** 2)

    # Compute cumulative distances along the front
    cumulative_distances = np.concatenate(([0], np.cumsum(distances)))

    # Total length of the Pareto front
    total_distance = cumulative_distances[-1]

    # Generate evenly spaced target distances along the front
    target_distances = np.linspace(0, total_distance, num_points)

    selected_points = []
    for target in target_distances:
        # Find the index of the closest point to the target distance
        idx = np.argmin(np.abs(cumulative_distances - target))
        selected_points.append((co2[idx], cost[idx]))

    # Return the selected points, converting cost back to original scale
    selected_points = [(c[0], np.exp(c[1]) - 1) for c in selected_points]  # Reverse log transformation
    return selected_points

def select_evenly_spaced_pareto_points_focus_x_axis(pareto_front, num_points=10):
    # Unpack the Pareto front into two lists (co2 and cost)
    co2, cost = zip(*pareto_front)

    # Convert to numpy arrays for easier manipulation
    co2 = np.array(co2)
    cost = np.array(cost)

    # Calculate the Euclidean distance between consecutive points
    distances = np.sqrt(np.diff(co2) ** 2 + np.diff(cost) ** 2)

    # Compute cumulative distances along the front
    cumulative_distances = np.concatenate(([0], np.cumsum(distances)))

    # Total length of the Pareto front
    total_distance = cumulative_distances[-1]

    # Generate evenly spaced target distances along the front
    target_distances = np.linspace(0, total_distance, num_points)

    selected_points = []
    for target in target_distances:
        # Find the index of the closest point to the target distance
        idx = np.argmin(np.abs(cumulative_distances - target))
        selected_points.append((co2[idx], cost[idx]))

    return selected_points


def find_exact_match_in_combined_front(reduced_points, combined_front, tol=1e-8):
    # Step 1: Deduplicate reduced_points using np.isclose
    unique_points = []
    for pt in reduced_points:
        co2_r, totex_r = pt
        # Check if it's already in unique_points (allowing for small numerical differences)
        if not any(np.isclose(co2_r, u[0], atol=tol) and np.isclose(totex_r, u[1], atol=tol) for u in unique_points):
            unique_points.append(pt)

    matched_points = []

    # Step 2: Find the best match in combined_front for each unique reduced point
    for co2_r, totex_r in unique_points:
        best_match = None
        for point in combined_front:
            co2_c = point['co2']
            totex_c = point['totex']
            peak_c = point['peak']

            if np.isclose(co2_r, co2_c, atol=tol) and np.isclose(totex_r, totex_c, atol=tol):
                if best_match is None or peak_c < best_match['peak']:
                    best_match = point

        if best_match:
            matched_points.append(best_match)

    return matched_points

def plot_all_pareto_points(combined_front):
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
def plot_all_pareto_points_with_front(combined_front,pareto_co2,pareto_cost):
    # 3D Plot with all points
    co2   = [r['co2'] for r in combined_front]
    cost  = [r['totex'] for r in combined_front]
    peak  = [r['peak'] for r in combined_front]
    plt.figure(figsize=(7,5))
    sc = plt.scatter(co2, cost, c=peak, cmap="viridis", s=5, alpha=0.7)
    plt.colorbar(sc, label="Peak (kW)")
    plt.xlabel("CO₂-eq in kg")
    plt.ylabel("Totex in €")
    plt.grid(True, alpha=0.3)

    # Plot the Pareto front as a red line
    plt.plot(pareto_co2, pareto_cost, color='#D32F2F', linestyle='--', label='Pareto Front', lw=1,alpha=0.5)

    # Add legend
    plt.legend()
    plt.show()

def get_pareto_front(data):
    pareto_front = []
    last_cost = float('inf')  # Initialisieren mit sehr hohem Wert
    for co2_val, cost_val in data:
        if cost_val < last_cost:  # Wenn der Kostenwert besser ist, füge den Punkt zur Pareto-Front hinzu
            pareto_front.append((co2_val, cost_val))
            last_cost = cost_val  # Aktuellen Kostenwert merken
    return pareto_front
def plot_stacked_bar_for_district(district_data, value_type="cost"):
    """
    Plots stacked bars for a district.
    value_type can be 'cost' or 'co2' depending on which value you want to visualize.
    """
    # Mapping für die Gebäudebezeichner
    building_name_map = {
        "DENILD1100004qZL": "Rep. SFH-A",
        "DENILD1100004rAk": "Rep. SFH-B",
        "DENILD1100004tAY": "Rep. SFH-C",
        "DENILD1100004s6k": "Rep. MFH-A",
        "DENILD1100004rSr": "Rep. MFH-B",
    }
    # Variable zur Speicherung der maximalen Werte
    min_value_list=[]
    max_value_list=[]
    for district_id, district in district_data.items():
        building_names = list(district.keys())
        building_names.remove('co2')
        building_names.remove('peak')
        building_names.remove('totex')
        num_buildings = len(building_names)

        # Vorbereiten der Daten für die gestapelten Balken
        technologies_costs = np.zeros((num_buildings, len(technologies)))
        energy_costs = np.zeros((num_buildings, len(energy_types)))

        # Sammle die Daten für Technologien und Energieträger
        for i, building_name in enumerate(building_names):
            building_data = district[building_name]
            # Technologien (PV-System, Heat storage, etc.)
            for j, tech in enumerate(technologies):
                technologies_costs[i, j] = building_data.get(tech, {}).get(value_type, 0)
            # Energieträger (Electricity, Gas, Hydrogen)
            for k, energy in enumerate(energy_types):
                energy_costs[i, k] = building_data.get(energy, {}).get(value_type, 0)

        tech_sums = technologies_costs.sum(axis=1)
        energy_sums = energy_costs.sum(axis=1)
        total_sums = tech_sums + energy_sums
        # Bestimme den maximalen Wert
        max_value_list.append(total_sums.max())
        min_value_list.append(np.min(energy_costs))
    max_value = max(max_value_list)
    min_value = min(min_value_list)
    for district_id, district in district_data.items():
        # Erstelle ein neues Plot für jeden Distrikt
        fig, ax = plt.subplots(figsize=(10, 7))

        # Iteriere durch die Gebäude im Distrikt
        building_names = list(district.keys())
        building_names.remove('co2')
        building_names.remove('peak')
        building_names.remove('totex')
        num_buildings = len(building_names)

        # Vorbereiten der Daten für die gestapelten Balken
        technologies_costs = np.zeros((num_buildings, len(technologies)))
        energy_costs = np.zeros((num_buildings, len(energy_types)))

        # Sammle die Daten für Technologien und Energieträger
        for i, building_name in enumerate(building_names):
            building_data = district[building_name]
            # Technologien (PV-System, Heat storage, etc.)
            for j, tech in enumerate(technologies):
                technologies_costs[i, j] = building_data.get(tech, {}).get(value_type, 0)
            # Energieträger (Electricity, Gas, Hydrogen)
            for k, energy in enumerate(energy_types):
                energy_costs[i, k] = building_data.get(energy, {}).get(value_type, 0)

        # Setze die Position der Balken
        bar_positions = np.arange(num_buildings)
        bar_width = 0.35

        # Stacken der Balken für jedes Gebäude
        bottom_tech = np.zeros(num_buildings)
        bottom_energy = np.zeros(num_buildings)

        # Zeichne die Technologien gestapelt mit den neuen Namen
        for j, tech in enumerate(technologies):
            tech_label = technology_name_map.get(tech, tech)  # Nutze den neuen Namen
            ax.bar(bar_positions, technologies_costs[:, j], width=bar_width,
                   bottom=bottom_tech, label=tech_label, color=technology_colors[j])
            bottom_tech += technologies_costs[:, j]

        # Zeichne die Energieträger gestapelt
        for k, energy in enumerate(energy_types):
            energy_values = energy_costs[:, k]

            # Negative und positive Werte trennen
            negative_values = np.where(energy_values < 0, energy_values, 0)
            positive_values = np.where(energy_values > 0, energy_values, 0)

            # Zeichne negative Werte
            ax.bar(bar_positions + bar_width, negative_values, width=bar_width,
                   bottom=bottom_energy, label=f"{energy}", color=technology_colors[k + len(technologies)])

            # Update bottom für die positiven Werte (auf die negativen Werte gestapelt)
            bottom_energy += negative_values

            # Zeichne positive Werte (nur wenn notwendig)
            for i in range(num_buildings):
                if positive_values[i] != 0:
                    ax.bar(bar_positions[i] + bar_width, positive_values[i], width=bar_width,
                           bottom=0, color=technology_colors[k + len(technologies)])

            # Update bottom nach der Zeichnung der positiven Werte
            bottom_energy += positive_values

        # Einstellungen der Achsen und Legende
        ax.set_xticks(bar_positions + bar_width / 2)
        ax.set_xticklabels([building_name_map.get(name, name) for name in building_names])  # Neue Namen für X-Achse

        ax.set_ylabel(f'{value_type.capitalize()} in thousands EUR' if value_type == "cost" else 'CO2-eq in t')

        ax.set_title(f'District {district_id}')
        ax.legend(title="Technologies & Energy Carriers", bbox_to_anchor=(1.05, 1), loc='upper left')
        # Setze das Y-Limit, damit alle Plots den gleichen Bereich haben
        ax.set_ylim(min_value*1.1, max_value *1.1)

        # Anzeige der X-Achse und Y-Achse mit Anpassung für lesbare Labels
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()


import matplotlib.pyplot as plt
import numpy as np

def plot_stackplot_for_district_with_peak(district_sums, value_type="cost"):
    """
    Plots a stack plot across districts.
    - value_type in {"cost","co2","capacity"}
    - For "capacity", only technologies are plotted (energy carriers skipped).
    - capacity_unit controls the y-axis label for capacity (default "kW").
    """
    fig, ax1 = plt.subplots(figsize=(10, 7), facecolor="#F0F0F0")

    # Color setup
    all_colors = plt.cm.tab20(np.linspace(0, 1, len(technologies) + len(energy_types)))
    technology_colors = all_colors[:len(technologies)]
    energy_colors = all_colors[len(technologies):]

    # Collect data
    n_districts = len(district_sums)
    x = range(n_districts)

    if value_type.lower() == "capacity":
        # Only technologies, typically non-negative
        tech_only = []
        for district_id, district_data in district_sums.items():
            tech_data = district_data['technologies']
            tech_vals = [max(0.0, tech_data[tech].get('capacity', 0.0)) for tech in technologies]
            tech_only.append(tech_vals)

        tech_only = np.array(tech_only).T  # (n_tech, n_districts)

        # Guard in case nothing to plot
        if tech_only.size == 0:
            raise ValueError("No capacity data found for technologies.")

        ax1.stackplot(x, *tech_only, alpha=0.7, colors=technology_colors, labels=technologies)
        ax1.set_ylabel(f'Capacity in kW and kWh')
        ax1.set_title('Stack Plot for Technology Capacity')

    else:
        # Original behavior for cost/co2: technologies + energy_types (with pos/neg splits)
        all_data_positive = []
        all_data_negative = []

        for district_id, district_data in district_sums.items():
            tech_data = district_data['technologies']
            energy_data = district_data['energy_types']

            tech_pos = [max(0, tech_data[tech][value_type]) for tech in technologies]
            tech_neg = [min(0, tech_data[tech][value_type]) for tech in technologies]
            energy_pos = [max(0, energy_data[e][value_type]) for e in energy_types]
            energy_neg = [min(0, energy_data[e][value_type]) for e in energy_types]

            all_data_positive.append(tech_pos + energy_pos)
            all_data_negative.append(tech_neg + energy_neg)

        all_data_positive = np.array(all_data_positive).T
        all_data_negative = np.array(all_data_negative).T

        assert all_data_positive.shape[1] == n_districts, "Mismatch in number of districts and data points"

        ax1.stackplot(x, *all_data_positive, alpha=0.6,
                      colors=np.concatenate([technology_colors, energy_colors]),
                      labels=technologies + energy_types)
        ax1.stackplot(x, *all_data_negative, alpha=0.6,
                      colors=np.concatenate([technology_colors, energy_colors]),
                      baseline='zero')

        if value_type == "cost":
            ax1.set_ylabel('Cost in thousand EUR')
            ax1.set_title('Stack Plot for Technologies & Energy Carriers (Cost)')
        else:
            ax1.set_ylabel('CO₂-eq in t')
            ax1.set_title('Stack Plot for Technologies & Energy Carriers (CO₂)')

    # Peak on secondary axis (always shown)
    ax2 = ax1.twinx()
    peak_values = [district_data['peak'] for district_data in district_sums.values()]
    ax2.plot(x, peak_values, color='black', label='Peak in kW', linestyle='--', linewidth=1)
    ax2.set_ylabel('Annual peak in kW', color='black')

    # Combined legend without duplicates
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    unique_handles, unique_labels = [], []
    for h, l in zip(h1 + h2, l1 + l2):
        if l not in unique_labels:
            unique_handles.append(h)
            unique_labels.append(l)

    ax1.legend(unique_handles, unique_labels,
               title=("Technologies (Capacity) & Peak" if value_type=="capacity"
                      else "Technologies, Energy Carriers & Peak"),
               bbox_to_anchor=(1.05, 1), loc='upper left', ncol=1)

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()
def calculate_delta(energy_type, results):
    """
    Funktion zum Berechnen der Delta-Werte für einen bestimmten Energietyp (Strom, Gas, Wasserstoff).

    :param energy_type: Der Energietyp ('Electricity', 'Gas', 'Hydrogen')
    :param results: Das Dictionary mit den Ergebnissen für den Energietyp
    :return: Die berechneten Delta-Werte für Kosten und CO2
    """
    energy_data = results.get(energy_type, {})

    # Wenn Daten vorhanden sind, gehe wie folgt vor
    if energy_data:
        # Sichere Methode, um Werte zu holen, die `None` als 0 behandeln
        if energy_data:
            # Sichere Methode, um Werte zu holen, die `None` als 0 behandeln
            flow_from_grid_cost = energy_data.get("flow_from_grid_cost", 0) if energy_data.get(
                "flow_from_grid_cost") is not None else 0
            flow_into_grid_revenue = energy_data.get("flow_into_grid_revenue", 0) if energy_data.get(
                "flow_into_grid_revenue") is not None else 0
            flow_from_grid_co2 = energy_data.get("flow_from_grid_co2", 0) if energy_data.get(
                "flow_from_grid_co2") is not None else 0
            flow_into_grid_co2 = energy_data.get("flow_into_grid_co2", 0) if energy_data.get(
                "flow_into_grid_co2") is not None else 0

            # Berechne die Delta-Werte
            delta_cost = flow_from_grid_cost - flow_into_grid_revenue
            delta_co2 = flow_from_grid_co2 - flow_into_grid_co2

        # Berechne die Delta-Werte nur, wenn keine der Werte None ist

        return delta_cost, delta_co2

    # Falls keine Daten vorhanden sind (None), setze die Delta-Werte auf 0
    return 0, 0


def process_district_data(matches,set_reference_to_one_building=False):
    energy_types = ["Electricity", "Gas", "Hydrogen"]
    technologies = ['pv_system', 'heat_storage', 'battery', 'gas_heater', 'chp', 'hp', 'building']

    # Dictionary to map the technology names to readable names
    technology_name_map = {
        'pv_system': 'PV-System',
        'heat_storage': 'Heat storage',
        'battery': 'Battery',
        'gas_heater': 'Gas heater',
        'chp': 'CHP',
        'hp': 'Heat pump',
        'building': 'Retrofit',
    }

    # Liste der zu verarbeitenden Energietypen
    district_data = {}

    # Zähler für die Distrikt-Nummer
    district_key = 0

    for district in matches:
        # Verwende den Zähler als Schlüssel
        district_key += 1
        district_data[district_key] = {}
        district_data[district_key]["co2"] = district["co2"]
        district_data[district_key]["peak"] = district["peak"]
        district_data[district_key]["totex"] = district["totex"]

        # Schleife durch die Gebäude im Distrikt
        for building_name, building_data in district['selection'].items():
            # Überspringe 'refurbish' oder andere irrelevante Keys
            district_data[district_key][building_name] = {}

            # Greife auf den 'record'-Schlüssel für detaillierte Ergebnisse zu
            record = building_data.get("record", {})
            results = record.get("results", {})

            # Verarbeite jeden Energietyp
            for energy_type in energy_types:
                delta_cost, delta_co2 = calculate_delta(energy_type, results)
                district_data[district_key][building_name][energy_type] = {}
                if delta_cost is not None and delta_co2 is not None:
                    if set_reference_to_one_building:

                        buildings_in_cluster = results[building_name][
                            "buildings_in_cluster"]
                    else:
                        buildings_in_cluster = 1
                    # Gebe die berechneten Delta-Werte für jeden Energietyp aus
                    print(f"Building: {building_name}")
                    print(f"  Delta {energy_type} From Grid Cost: {delta_cost}")
                    print(f"  Delta {energy_type} From Grid CO2: {delta_co2}")

                    district_data[district_key][building_name][energy_type]["cost"] = delta_cost / buildings_in_cluster
                    district_data[district_key][building_name][energy_type]["co2"] = delta_co2 / buildings_in_cluster

            # Verarbeite jede Technologie (z.B. pv_system, heat_storage, gas_heater)
            for technology in technologies:
                total_cost = 0
                total_co2 = 0
                total_capacity = 0
                # Suche nach allen Technologien, die mit dem Prefix übereinstimmen und mit einer Zahl enden
                for key in results[building_name]:
                    if key.startswith(technology):
                        if key == "buildings_in_cluster":
                            continue
                        if technology == "building":
                            technology_data = results[building_name][key]
                            total_cost += technology_data.get('investment_cost', 0) / buildings_in_cluster
                            total_co2 += technology_data.get('investment_co2', 0) / buildings_in_cluster
                        else:
                            # Sucht nach Technologien mit dem angegebenen Prefix
                            technology_data = results[building_name][key]
                            total_cost += technology_data.get('investment_cost', 0) / buildings_in_cluster
                            total_co2 += technology_data.get('investment_co2', 0) / buildings_in_cluster
                            total_capacity += technology_data.get('capacity', 0) / buildings_in_cluster

                # Speichere die Daten mit dem lesbaren Namen aus der 'technology_name_map'
                readable_technology_name = technology_name_map.get(technology,
                                                                   technology)  # Falls der Name nicht in der Map vorhanden ist, verwende den Originalnamen
                district_data[district_key][building_name][readable_technology_name] = {
                    "cost": total_cost,
                    "co2": total_co2,
                    "capacity": total_capacity
                }
    return district_data

def calculate_sums_for_technologies_and_energy_for_a_district(district_data, energy_types, technologies):
    """
    Berechnet die Summen der Werte für jede Technologie und jeden Energieträger für jedes Gebäude in jedem Distrikt.
    Speichert sowohl "cost" als auch "co2".
    Struktur: [tech][cost/co2]
    """
    # Dictionary zur Speicherung der Summen pro Distrikt für jede Technologie und Energiequelle
    district_sums = {}

    # Iteriere über jedes Distrikt
    for district_id, district in district_data.items():
        # Initialisiere ein Dictionary für das Distrikt mit beiden Werten
        district_sums[district_id] = {
            'technologies': {tech: {'cost': 0, 'co2': 0, 'capacity':0} for tech in technologies},
            'energy_types': {energy: {'cost': 0, 'co2': 0} for energy in energy_types}
        }

        # Iteriere über jedes Gebäude im Distrikt
        for building_name, building_data in district.items():
            if building_name in building_name_map:
                # Summiere für Technologien (cost und co2)
                for tech in technologies:
                    district_sums[district_id]['technologies'][tech]['cost'] += building_data.get(tech, {}).get('cost', 0)
                    district_sums[district_id]['technologies'][tech]['co2'] += building_data.get(tech, {}).get('co2', 0)
                    district_sums[district_id]['technologies'][tech]['capacity'] += building_data.get(tech, {}).get('capacity', 0)
                # Summiere für Energieträger (cost und co2)
                for energy in energy_types:
                    district_sums[district_id]['energy_types'][energy]['cost'] += building_data.get(energy, {}).get('cost', 0)
                    district_sums[district_id]['energy_types'][energy]['co2'] += building_data.get(energy, {}).get('co2', 0)
        district_sums[district_id]["peak"] = district["peak"]
    return district_sums


# Die Datei mit pickle öffnen und laden
with open(r"C:\Users\hill_mx\Desktop\Paper UEC UEU\Ergebnisse\2025_08_26\dec_processed_08_26_results_of_DENI03403000SEC5658.pkl", "rb") as f:
    building_dict_loaded = pickle.load(f)
print(building_dict_loaded)
combined_front = building_dict_loaded[2]

co2 = [r['co2'] for r in combined_front]
cost = [r['totex'] for r in combined_front]
peak = [r['peak'] for r in combined_front]
# Daten kombinieren
data = list(zip(co2, cost))
data = sorted(data)
# Get the Pareto front points
pareto_front = get_pareto_front(data)
if True:
    # Extract Pareto front CO2 and cost for plotting
    pareto_co2, pareto_cost = zip(*pareto_front)

    plot_all_pareto_points(combined_front)

    selected_points_y = select_evenly_spaced_pareto_points_focus_y_axis(pareto_front,num_points=8)
    selected_points_x =select_evenly_spaced_pareto_points_focus_x_axis(pareto_front,num_points=8)

    reduced_points = reduce_pareto_points(selected_points_y+selected_points_x)  # Keep the last point

    # Extract CO2 and cost values for plotting
    selected_co2, selected_cost = zip(*reduced_points)

    # Plot the full combined Pareto front and the selected points
    co2_all, cost_all = zip(*pareto_front)
    plt.figure(figsize=(7,5))
    plt.plot(co2_all, cost_all, color='#D32F2F', linestyle='--', label='Combined Pareto Front', lw=2)
    plt.scatter(selected_co2, selected_cost, color='blue', label=f'{len(reduced_points)} Selected Points', zorder=5)
    plt.xlabel("CO₂-eq in kg")
    plt.ylabel("Totex in €")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.show()

    matches = find_exact_match_in_combined_front(reduced_points, combined_front)

matches_whole_front = find_exact_match_in_combined_front(pareto_front, combined_front)


# Aufruf der Funktion mit den Distriktdaten

# Mapping für die Gebäudebezeichner
building_name_map = {
    "DENILD1100004qZL": "Rep. SFH-A",
    "DENILD1100004rAk": "Rep. SFH-B",
    "DENILD1100004tAY": "Rep. SFH-C",
    "DENILD1100004s6k": "Rep. MFH-A",
    "DENILD1100004rSr": "Rep. MFH-B",
}

# Farben für Technologien aus der 'tab20' Farbpalette (gut geeignet für wissenschaftliche Plots)
technology_colors = cm.tab20(np.linspace(0, 1, 10))

# Energietypen und Technologien
energy_types = ["Electricity", "Gas", "Hydrogen"]
technologies = ['PV-System', 'Heat storage', 'Battery', 'Gas heater', 'CHP', 'Heat pump', 'Retrofit']

# Beispielaufruf der Funktion zum Plotten für alle Distrikte mit "cost"
if False:
    processed_district_data = process_district_data(matches,1)
    plot_stacked_bar_for_district(processed_district_data, value_type="cost")

    # Beispielaufruf der Funktion zum Plotten für alle Distrikte mit "co2"
    plot_stacked_bar_for_district(processed_district_data, value_type="co2")
processed_district_data = process_district_data(matches_whole_front)
processed_district_data = process_units_for_processed(
    processed_district_data,
    cost_divisor=1000,            # € -> k€
)
district_sums = calculate_sums_for_technologies_and_energy_for_a_district(processed_district_data, energy_types, technologies)
district_sums[1]

# Assuming `district_sums` is properly formatted and contains peak values
plot_stackplot_for_district_with_peak(district_sums, value_type="cost")# Assuming `district_sums` is properly formatted and contains peak values
plot_stackplot_for_district_with_peak(district_sums, value_type="co2")
plot_stackplot_for_district_with_peak(district_sums, value_type="capacity")