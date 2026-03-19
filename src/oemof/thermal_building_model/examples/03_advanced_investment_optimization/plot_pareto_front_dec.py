
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
import seaborn
import pickle

import copy
import numpy as np
import pickle
import os
def _to_float(x):
    if isinstance(x, (np.generic,)):
        return float(x)
    return x
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt


def plot_all_points_with_front_and_selected(
    combined_front,
    pareto_front=None,                 # optional: list of dicts or (co2, totex) tuples
    selected_co2=None,                 # array-like
    selected_totex=None,               # array-like
    selected_labels=None,              # optional labels for selected points
    label_every: int = 1,              # label every k-th selected point
    max_labels: int = 12,              # hard cap on how many labels to draw
    name=None,
    filename=None,
    figsize=(6, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    xlabel=r"Annual CO$_2$-eq in kg",
    ylabel=r"Totex in €",
    cbar_label=r"Peak load in kW",
    cmap="viridis",
    s_all=10,
    alpha_all=0.65,
    s_selected=28,
    show=True,
    dpi=600,
    grid=True,
):
    """
    Journal-ready plot:
    - All Pareto points as scatter colored by peak (colorbar).
    - Pareto-optimal curve as dashed line.
    - Selected points highlighted + optionally annotated with numbers.
    """

    # -----------------------------
    # GLOBAL FONT & STYLE SETTINGS
    # -----------------------------
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.titlesize": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
        "mathtext.fontset": "cm",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # -----------------------------
    # COLORS (journal-proof)
    # -----------------------------
    palette = sns.color_palette("colorblind")
    col_front = palette[3]   # strong contrasting tone for dashed curve
    col_sel = palette[0]     # blue for selected points
    col_sel_edge = "white"   # improves readability on dense scatter

    # -----------------------------
    # DATA: all points (colored by peak)
    # -----------------------------
    co2_all = np.array([r["co2"] for r in combined_front], dtype=float)
    totex_all = np.array([r["totex"] for r in combined_front], dtype=float)
    peak_all = np.array([r["peak"] for r in combined_front], dtype=float)

    fig, ax = plt.subplots(figsize=figsize)

    sc = ax.scatter(
        co2_all,
        totex_all,
        c=peak_all,
        cmap=cmap,
        s=s_all,
        alpha=alpha_all,
        linewidths=0.0,
        zorder=1,
    )

    # -----------------------------
    # Pareto front curve (dashed)
    # -----------------------------
    if pareto_front is None:
        # default: derive curve from combined_front by sorting by co2
        pf = sorted(combined_front, key=lambda r: (r["co2"], r["totex"]))
        pf_co2 = np.array([r["co2"] for r in pf], dtype=float)
        pf_totex = np.array([r["totex"] for r in pf], dtype=float)
    else:
        # accept list of dicts or list of tuples
        if len(pareto_front) == 0:
            pf_co2 = np.array([])
            pf_totex = np.array([])
        else:
            if isinstance(pareto_front[0], dict):
                pf_sorted = sorted(pareto_front, key=lambda r: (r["co2"], r["totex"]))
                pf_co2 = np.array([r["co2"] for r in pf_sorted], dtype=float)
                pf_totex = np.array([r["totex"] for r in pf_sorted], dtype=float)
            else:
                pf_sorted = sorted(pareto_front, key=lambda t: (t[0], t[1]))
                pf_co2 = np.array([t[0] for t in pf_sorted], dtype=float)
                pf_totex = np.array([t[1] for t in pf_sorted], dtype=float)

    if pf_co2.size > 0:
        ax.plot(
            pf_co2,
            pf_totex,
            linestyle="--",
            linewidth=1.3,
            color=col_front,
            label="Pareto-optimal front",
            zorder=2,
        )

    # -----------------------------
    # Selected points (highlight + optional labels)
    # -----------------------------
    if selected_co2 is not None and selected_totex is not None:
        sel_co2 = np.array(selected_co2, dtype=float)
        sel_totex = np.array(selected_totex, dtype=float)

        ax.scatter(
            sel_co2,
            sel_totex,
            s=s_selected,
            color=col_sel,
            edgecolors=col_sel_edge,
            linewidths=0.6,
            zorder=3,
            label=f"Selected points (n={len(sel_co2)})",
        )

        # Labels (few only)
        if selected_labels is None:
            selected_labels = [str(i + 1) for i in range(len(sel_co2))]

        # choose indices to label
        idx = list(range(0, len(sel_co2), max(1, label_every)))
        idx = idx[:max_labels]

        for i in idx:
            ax.annotate(
                selected_labels[i],
                (sel_co2[i], sel_totex[i]),
                textcoords="offset points",
                xytext=(3, 3),
                ha="left",
                va="bottom",
                fontsize=font_size,
                color=col_sel,
                bbox=dict(boxstyle="circle,pad=0.18", fc="white", ec=col_sel, lw=0.6),
                zorder=4,
            )

    # -----------------------------
    # Labels, grid, legend, colorbar
    # -----------------------------
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)

    if grid:
        ax.grid(True, alpha=0.3, linewidth=0.6)

    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(cbar_label, fontsize=font_size)
    cbar.ax.tick_params(labelsize=font_size)

    ax.legend(frameon=False, loc="best")

    fig.tight_layout()

    # -----------------------------
    # SAVE
    # -----------------------------
    if filename is None and name is not None:
        filename = f"pareto_all_with_front_selected_{name}.pdf"

    if filename is not None:
        fig.savefig(filename, format="pdf", dpi=dpi, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig, ax

def process_units_for_processed(
    processed_district_data,
    *,
    # Global divisors
    cost_divisor=1.0,          # e.g. 1000 for k€
    co2_divisor=1.0,           # e.g. 1.0 keep as-is
    peak_divisor=1.0,          # e.g. 1000 for MW
    floor_area = 1,
    # Capacity handling
    power_capacity_divisor=1.0,      # kW -> MW: 1000
    heat_storage_name="Heat storage",
    # Heat storage is given as V [m³], convert to energy [kWh]
    hs_delta_T_K=30.0,               # temperature gap
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
            district['co2'] = _to_float(district['co2']) / (co2_divisor*floor_area)
        if 'totex' in district:
            district['totex'] = _to_float(district['totex']) / (cost_divisor*floor_area)
        if 'peak' in district:
            district['peak'] = _to_float(district['peak']) / (peak_divisor*floor_area)
        if 'electricity_grid' in district:
            district['electricity_grid']["added_line_length"] = _to_float(district['electricity_grid']["added_line_length"] ) / (power_capacity_divisor*floor_area)
            district['electricity_grid']["added_trafo_capacity"] = _to_float(district['electricity_grid']["added_trafo_capacity"]) / (power_capacity_divisor*floor_area)
            district['electricity_grid']["added_line_cost"] = _to_float(district['electricity_grid']["added_line_cost"] ) / (cost_divisor*floor_area)
            district['electricity_grid']["added_trafo_cost"] = _to_float(district['electricity_grid']["added_trafo_cost"]) / (cost_divisor*floor_area)
            district['electricity_grid']["added_line_co2"] = _to_float(district['electricity_grid']["added_line_co2"] ) / (co2_divisor*floor_area)
            district['electricity_grid']["added_trafo_co2"] = _to_float(district['electricity_grid']["added_trafo_co2"]) / (co2_divisor*floor_area)
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
                    vals['cost'] = _to_float(vals['cost']) / (cost_divisor*floor_area)
                if 'co2' in vals:
                    vals['co2'] = _to_float(vals['co2']) / (co2_divisor*floor_area)

                # capacity handling
                if 'capacity' in vals:
                    cap_val = _to_float(vals['capacity'])

                    if tech_or_carrier == heat_storage_name:
                        # Save original m³
                        vals['capacity_in_m3'] = cap_val

                        # Convert to kWh
                        energy_kWh = cap_val * m3_to_kWh
                        # Scale (e.g. to MWh if power_capacity_divisor=1000)
                        energy_scaled = energy_kWh / (power_capacity_divisor*floor_area)

                        # Overwrite capacity with converted energy
                        vals['capacity'] = energy_scaled

                    else:
                        # Non-heat-storage: treat as POWER (e.g., kW) and scale
                        vals['capacity'] = cap_val / (power_capacity_divisor*floor_area)

    return out

import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

# ------------------------------------------------------------------
# Journal-style global plotting defaults (use as shared baseline)
# ------------------------------------------------------------------
def set_journal_style(font_family="TeX Gyre Termes", font_size=9):
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.titlesize": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
        "mathtext.fontset": "cm",
        "pdf.fonttype": 42,  # editable text
        "ps.fonttype": 42,
    })

# ------------------------------------------------------------------
# Pareto plot: CO2 vs TOTEX (combined front + selected points)
# Uses seaborn colorblind palette, consistent with your template.
# ------------------------------------------------------------------
def plot_pareto_co2_totex(
    co2_all,
    totex_all,
    selected_co2=None,
    selected_totex=None,
    name=None,
    filename=None,
    figsize=(6, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    xlabel=r"Annual CO$_2$-eq in kg",
    ylabel=r"Totex in EUR",
    title="",
    show=True,
    dpi=600,
):
    # -----------------------------
    # GLOBAL FONT & STYLE SETTINGS
    # -----------------------------
    set_journal_style(font_family=font_family, font_size=font_size)

    # -----------------------------
    # COLORS (journal-proof, colorblind)
    # -----------------------------
    palette = sns.color_palette("colorblind")
    col_front = palette[3]   # strong contrasting tone
    col_sel   = palette[0]   # classic blue

    # -----------------------------
    # FIGURE
    # -----------------------------
    fig, ax = plt.subplots(figsize=figsize)

    # Combined Pareto front (line)
    ax.plot(
        co2_all,
        totex_all,
        linestyle="--",
        lw=1.4,
        color=col_front,
        label="Combined Pareto front",
        zorder=2,
    )

    # Selected points (scatter)
    if selected_co2 is not None and selected_totex is not None:
        n_sel = len(selected_co2)
        ax.scatter(
            selected_co2,
            selected_totex,
            s=18,
            color=col_sel,
            edgecolors="white",
            linewidths=0.4,
            label=f"Selected points (n={n_sel})",
            zorder=3,
        )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)

    ax.grid(True, alpha=0.3, linewidth=0.6)
    ax.legend(frameon=False, loc="best")

    fig.tight_layout()

    # -----------------------------
    # SAVE
    # -----------------------------
    if filename is None and name is not None:
        filename = f"pareto_{name}.pdf"

    if filename is not None:
        fig.savefig(filename, format="pdf", dpi=dpi, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig, ax

# -----------------------------
# Example usage (same pattern as your template)
# -----------------------------
# width_cm = 15.11293
# height_cm = 6.5 * 1.8
# width_inch = width_cm / 2.54
# height_inch = height_cm / 2.54
#
# plot_pareto_co2_totex(
#     co2_all=co2_all,
#     totex_all=cost_all,
#     selected_co2=selected_co2,
#     selected_totex=selected_cost,
#     name="co2_totex",
#     figsize=(width_inch, height_inch * 1.05),
#     font_size=9,
#     title="",
#     filename=r"C:\Users\hill_mx\Desktop\Results Manuel\Abbildungen\pareto_co2_totex.pdf",
# )

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

def plot_all_pareto_points(
    combined_front,
    name=None,
    filename=None,
    figsize=(6, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    xlabel=r"Annual CO$_2$-eq in kg",
    ylabel=r"Totex in €",
    cbar_label=r"Peak load in kW",
    cmap="viridis",
    s=8,
    alpha=0.7,
    show=True,
    dpi=600,
):
    """
    Journal-ready scatter plot of all Pareto points.
    Color encodes peak load.
    """

    # -----------------------------
    # GLOBAL FONT & STYLE SETTINGS
    # -----------------------------
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.titlesize": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
        "mathtext.fontset": "cm",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # -----------------------------
    # DATA EXTRACTION
    # -----------------------------
    co2   = np.array([r["co2"] for r in combined_front])
    totex = np.array([r["totex"] for r in combined_front])
    peak  = np.array([r["peak"] for r in combined_front])

    # -----------------------------
    # FIGURE
    # -----------------------------
    fig, ax = plt.subplots(figsize=figsize)

    sc = ax.scatter(
        co2,
        totex,
        c=peak,
        cmap=cmap,
        s=s,
        alpha=alpha,
        linewidths=0.0,
    )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)

    ax.grid(True, alpha=0.3, linewidth=0.6)

    # -----------------------------
    # COLORBAR
    # -----------------------------
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(cbar_label, fontsize=font_size)
    cbar.ax.tick_params(labelsize=font_size)

    fig.tight_layout()

    # -----------------------------
    # SAVE
    # -----------------------------
    if filename is None and name is not None:
        filename = f"pareto_all_points_{name}.pdf"

    if filename is not None:
        fig.savefig(filename, format="pdf", dpi=dpi, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig, ax
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

import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt


def _nice_tick_step(n_points: int, target_ticks: int = 8) -> int:
    """
    Choose a "nice" integer step for x ticks (1,2,5 * 10^k) so that we show
    ~target_ticks ticks for n_points.
    """
    if n_points <= 1:
        return 1

    raw = max(1.0, (n_points - 1) / max(1, (target_ticks - 1)))
    k = 10 ** int(np.floor(np.log10(raw)))
    candidates = np.array([1, 2, 5, 10]) * k
    step = int(candidates[np.argmin(np.abs(candidates - raw))])
    return max(1, step)


def _build_pareto_xticks(n_points: int, target_ticks: int = 8):
    """
    Returns tick positions and labels for Pareto-solution index axis:
    - integer labels (0..n-1)
    - "nice" step (5, 10, 50, 100, ...)
    - always include last index
    """
    if n_points <= 1:
        return np.array([0]), ["0"]

    step = _nice_tick_step(n_points, target_ticks=target_ticks)
    ticks = np.arange(0, n_points, step, dtype=int)
    if ticks[-1] != n_points - 1:
        ticks = np.append(ticks, n_points - 1)

    labels = [str(int(t)) for t in ticks]
    return ticks, labels


def plot_stackplot_for_pareto_solutions_with_peak(
    district_sums,
    technologies,
    energy_types,
    value_type="cost",
    # journal-style controls
    figsize=(6.0, 3.6),
    font_size=9,
    font_family="TeX Gyre Termes",
    facecolor="white",
    dpi=600,
    filename=None,
    show=True,
    # x-axis (pareto solutions)
    x_label="Pareto-optimal solution index (sorted)",
    sort_key=None,                 # e.g. "co2" or "totex" or None (keep input order)
    target_xticks=8,               # << choose ~ how many ticks you want
    x_tick_rotation=0,
    # peak styling (thinner dashed line)
    peak_lw=0.4,                  # thinner than before
    peak_alpha=0.9,
    peak_drawstyle="steps-mid",    # reduces visual jitter
    peak_smooth_window=0,          # 0=off; e.g. 5 for rolling mean (visual only)
    # label overrides (per 100 m² etc.)
    y_label_override=None,
    peak_label_override=None,
    # legend placement: above plot, multi-column
    legend_ncol=4,                 # 12 entries -> 3x4
    legend_loc="upper center",
    legend_bbox=(0.5, 1.12),
    control_values =False,
):
    """
    Journal-ready stacked area plot over Pareto-optimal solutions + peak on secondary axis.
    - "nice" x-ticks (5, 10, 50, ...) depending on number of points
    - thinner dashed peak line
    - legend above plot (multi-column), no titles on figure (paper style)
    """

    # -----------------------------
    # GLOBAL FONT & STYLE SETTINGS
    # -----------------------------
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.titlesize": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
        "mathtext.fontset": "cm",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # -----------------------------
    # FIGURE
    # -----------------------------
    fig, ax1 = plt.subplots(figsize=figsize, facecolor=facecolor)

    # -----------------------------
    # COLORS (colorblind-safe)
    # -----------------------------
    n_tech = len(technologies)
    n_energy = len(energy_types)
    palette = sns.color_palette("colorblind", n_colors=max(n_tech + n_energy, 3))
    technology_colors = palette[:n_tech]
    energy_colors = palette[n_tech:n_tech + n_energy] if n_energy > 0 else []

    # -----------------------------
    # X axis: solutions (ordered)
    # -----------------------------
    solution_ids = list(district_sums.keys())

    if sort_key in ("co2", "cost", "totex", "peak"):
        solution_ids = sorted(
            solution_ids,
            key=lambda sid: float(district_sums[sid].get(sort_key, np.nan))
        )

    n_pts = len(solution_ids)
    x = np.arange(n_pts)

    # -----------------------------
    # DATA + STACKPLOT
    # -----------------------------
    vt = value_type.lower()

    if vt == "capacity":
        tech_only = []
        for sid in solution_ids:
            tech_data = district_sums[sid]["technologies"]
            tech_vals = [max(0.0, float(tech_data.get(tech, {}).get("capacity", 0.0))) for tech in technologies]
            tech_only.append(tech_vals)

        tech_only = np.array(tech_only).T  # (n_tech, n_pts)
        if tech_only.size == 0:
            raise ValueError("No capacity data found for technologies.")

        ax1.stackplot(
            x,
            *tech_only,
            alpha=0.75,
            colors=technology_colors,
            labels=technologies,
            linewidth=0.0
        )

        ax1.set_ylabel(y_label_override or "Installed capacity (kW or kWh)")

    elif vt in ("cost", "co2"):
        all_data_positive = []
        all_data_negative = []
        co2_only = []
        totex_only = []
        for sid in solution_ids:
            co2_only.append(district_sums[sid]["co2"])
            totex_only.append(district_sums[sid]["totex"])

            tech_data = district_sums[sid]["technologies"]
            energy_data = district_sums[sid].get("energy_types", {})

            tech_pos = [max(0.0, float(tech_data.get(tech, {}).get(vt, 0.0))) for tech in technologies]
            tech_neg = [min(0.0, float(tech_data.get(tech, {}).get(vt, 0.0))) for tech in technologies]

            energy_pos = [max(0.0, float(energy_data.get(e, {}).get(vt, 0.0))) for e in energy_types]
            energy_neg = [min(0.0, float(energy_data.get(e, {}).get(vt, 0.0))) for e in energy_types]

            all_data_positive.append(tech_pos + energy_pos)
            all_data_negative.append(tech_neg + energy_neg)
        # Plot the control values
        if control_values:
            if vt == "cost":
                ax1.plot(x, totex_only,  # Horizontal line for totex
                    color="red", linestyle="--", label=f"Control Total Totex in Totex for {sid}",
                    linewidth=2, zorder=10
                )
            elif vt == "co2":
                ax1.plot(x, co2_only,  # Horizontal line for co2
                    color="blue", linestyle="--", label=f"Control CO2 Emissions for {sid}",
                    linewidth=2, zorder=10
                )
        all_data_positive = np.array(all_data_positive).T
        all_data_negative = np.array(all_data_negative).T

        if all_data_positive.shape[1] != n_pts:
            raise ValueError("Mismatch in number of Pareto solutions and data points")

        colors = list(technology_colors) + list(energy_colors)
        labels = list(technologies) + list(energy_types)

        polys_pos = ax1.stackplot(
            x,
            *all_data_positive,
            alpha=0.70,
            colors=colors,
            labels=labels,
            linewidth=0.0
        )
        polys_neg = ax1.stackplot(
            x,
            *all_data_negative,
            alpha=0.70,
            colors=colors,
            baseline="zero",
            linewidth=0.0
        )

        # --- NEW: hatch ALL energy-type areas with the SAME hatch ---
        energy_hatch = ".."  # change if you want e.g. "//" or "xx"
        hatch_lw = 0.04 # thin hatch stroke
        n_tech = len(technologies)

        for j in range(len(energy_types)):
            idx = n_tech + j  # energy polys start after technology polys
            for poly in (polys_pos[idx], polys_neg[idx]):
                poly.set_hatch(energy_hatch)
                poly.set_edgecolor("black")  # hatch color comes from edgecolor
                poly.set_linewidth(hatch_lw)  # controls hatch stroke thickness

        if y_label_override is not None:
            ax1.set_ylabel(y_label_override)
        else:
            ax1.set_ylabel("Totex in thousand EUR" if vt == "cost" else r"Annual CO$_2$-eq in t")
    else:
        raise ValueError("value_type must be one of {'cost','co2','capacity'}")

    # -----------------------------
    # Peak on secondary axis (optionally smoothed)
    # -----------------------------
    ax2 = ax1.twinx()
    peak_values = np.array([float(district_sums[sid].get("peak", np.nan)) for sid in solution_ids], dtype=float)

    peak_plot = peak_values.copy()
    if peak_smooth_window and peak_smooth_window > 1:
        pv = peak_plot.copy()
        ok = np.isfinite(pv)
        if ok.any() and (~ok).any():
            pv[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), pv[ok])
        kernel = np.ones(int(peak_smooth_window)) / float(peak_smooth_window)
        peak_plot = np.convolve(pv, kernel, mode="same")

    ax2.plot(
        x,
        peak_plot,
        color="black",
        linestyle="--",
        linewidth=peak_lw,
        alpha=peak_alpha,
        label="Peak load in kW",
        zorder=5,
        drawstyle=peak_drawstyle if peak_drawstyle else "default",
    )

    ax2.set_ylabel(peak_label_override or "Annual peak load in kW")

    # -----------------------------
    # X ticks: NICE numbering (5, 10, 50, ...)
    # -----------------------------
    # -----------------------------
    # X ticks: NICE numbering (5, 10, 50, ...)
    # -----------------------------
    tick_pos, tick_labels = _build_pareto_xticks(n_pts, target_ticks=target_xticks)

    # remove penultimate tick label (keep the max/last tick)
    tick_pos = list(tick_pos)
    tick_labels = list(tick_labels)
    if len(tick_pos) >= 2:
        tick_pos.pop(-2)
        tick_labels.pop(-2)

    ax1.set_xticks(tick_pos)
    ax1.set_xticklabels(tick_labels, rotation=x_tick_rotation, ha="center")
    ax1.set_xlabel(x_label)

    # optional: give the last label more room and align it nicely
    ax1.set_xlim(-0.5, n_pts - 0.5 + 0.02 * n_pts)  # little right padding
    lbls = ax1.get_xticklabels()
    if lbls:
        lbls[-1].set_ha("right")

    # --- remove penultimate tick label (keep the max/last tick) ---
    tick_pos = list(tick_pos)
    tick_labels = list(tick_labels)

    if len(tick_pos) >= 2:
        tick_pos.pop(-2)
        tick_labels.pop(-2)
    # --- ensure negative contributions are visible (if present) ---
    ymin, ymax = ax1.get_ylim()
    if ymin >= 0:
        # try to infer min from the stacked negative parts
        # (fallback: keep current)
        pass

    # Better: compute bounds from plotted data:
    all_y = []
    for coll in ax1.collections:
        try:
            verts = coll.get_paths()[0].vertices
            all_y.append(verts[:, 1])
        except Exception:
            pass

    if all_y:
        y = np.concatenate(all_y)
        y = y[np.isfinite(y)]
        if y.size > 0:
            pad = 0.03 * (y.max() - y.min() + 1e-12)
            ax1.set_ylim(y.min() - pad, y.max() + pad)

    # subtle grid on primary axis only
    ax1.grid(True, axis="y", alpha=0.25, linewidth=0.6)

    # -----------------------------
    # Legend ABOVE plot (multi-column), no legend title
    # -----------------------------
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()

    unique = {}
    for h, l in list(zip(h1, l1)) + list(zip(h2, l2)):
        if l not in unique:
            unique[l] = h

    fig.legend(
        unique.values(),
        unique.keys(),
        ncol=legend_ncol,
        loc=legend_loc,
        bbox_to_anchor=legend_bbox,
        frameon=False,
        handlelength=1.6,
        columnspacing=1.2,
    )

    # Leave space for legend on top
    fig.tight_layout(rect=[0, 0, 1, 0.94])

    # -----------------------------
    # SAVE / SHOW
    # -----------------------------
    if filename:
        fig.savefig(filename, format="pdf", dpi=dpi, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig, ax1, ax2


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

def process_district_data(matches, buildings, cen_or_dec, set_reference_to_one_building=False):
    energy_types = ["Electricity", "BioGas", "NaturalGas", "Hydrogen"]
    technologies = ['pv_system', 'heat_storage', 'battery', 'gas_heater', 'chp', 'hp', 'building']

    technology_name_map = {
        'pv_system': 'PV-System',
        'heat_storage': 'Heat storage',
        'battery': 'Battery',
        'gas_heater': 'Gas heater',
        'chp': 'CHP',
        'hp': 'Heat pump',
        'building': 'Retrofit',
    }

    # NEW: energy naming map
    energy_type_name_map = {
        "Electricity": "Electricity",
        "BioGas": "Bio gas",
        "NaturalGas": "Natural gas",
        "Hydrogen": "Hydrogen",
    }

    district_data = {}
    district_key = 0

    for district in matches:
        district_key += 1
        selection = district.get("selection", {})

        district_data[district_key] = {
            "co2": district.get("co2"),
            "peak": district.get("peak"),
            "totex": district.get("totex"),
        }
        district_data[district_key]["electricity_grid"] = {}
        district_data[district_key]["electricity_grid"]["cost"] = district["Electricity_Grid"]["investment_cost"]
        district_data[district_key]["electricity_grid"]["added_trafo_capacity"] = district["Electricity_Grid"]["added_trafo_capacity"]
        district_data[district_key]["electricity_grid"]["added_line_length"] = district["Electricity_Grid"]["added_line_length"]
        district_data[district_key]["electricity_grid"]["added_trafo_cost"] = district["Electricity_Grid"]["added_trafo_cost"]
        district_data[district_key]["electricity_grid"]["added_line_cost"] = district["Electricity_Grid"]["added_line_cost"]
        district_data[district_key]["electricity_grid"]["added_trafo_co2"] = district["Electricity_Grid"]["added_trafo_co2"]
        district_data[district_key]["electricity_grid"]["added_line_co2"] = district["Electricity_Grid"]["added_line_co2"]

        # -------------------------
        # DECENTRALIZED CASE (dec)
        # -------------------------
        if cen_or_dec == "dec":
            for building_name, building_wrapper in selection.items():

                district_data[district_key][building_name] = {}

                record = building_wrapper.get("record", {})
                results = record.get("results", {})

                if set_reference_to_one_building:
                    buildings_in_cluster = results.get(building_name, {}).get("buildings_in_cluster", 1)
                else:
                    buildings_in_cluster = 1
                    buildings_in_cluster_scale_technology = results.get(building_name, {}).get("buildings_in_cluster", 1)
                # energy deltas (per building)
                for energy_type in energy_types:
                    delta_cost, delta_co2 = calculate_delta(energy_type, results)
                    if delta_cost is None or delta_co2 is None:
                        continue

                    # use mapped name
                    et_readable = energy_type_name_map.get(energy_type, energy_type)

                    district_data[district_key][building_name].setdefault(et_readable, {})
                    district_data[district_key][building_name][et_readable]["cost"] = float(delta_cost) / buildings_in_cluster
                    district_data[district_key][building_name][et_readable]["co2"] = float(delta_co2) / buildings_in_cluster

                # technologies per building
                building_results = results.get(building_name, {})
                for technology in technologies:
                    total_cost = 0.0
                    total_co2 = 0.0
                    total_capacity = 0.0

                    for key, tech_data in building_results.items():
                        if key in ("buildings_in_cluster", "buildings_in_cluster_used"):
                            continue
                        if not key.startswith(technology):
                            continue

                        total_cost += float(tech_data.get("investment_cost", 0.0)) / buildings_in_cluster
                        total_co2 += float(tech_data.get("investment_co2", 0.0)) / buildings_in_cluster
                        if technology != "building":
                            total_capacity += float(tech_data.get("capacity", 0.0)) * buildings_in_cluster_scale_technology/ buildings_in_cluster

                    readable = technology_name_map.get(technology, technology)
                    district_data[district_key][building_name][readable] = {
                        "cost": total_cost,
                        "co2": total_co2,
                        "capacity": total_capacity
                    }

        # ----------------------
        # CENTRALIZED CASE (cen)
        # ----------------------
        elif cen_or_dec == "cen":
            district_data[district_key]["heat_grid"] = {}

            # (1) energy deltas -> directly under heat_grid
            for energy_type in energy_types:
                delta_cost, delta_co2 = calculate_delta(energy_type, selection)
                if delta_cost is None or delta_co2 is None:
                    continue

                et_readable = energy_type_name_map.get(energy_type, energy_type)

                district_data[district_key]["heat_grid"][et_readable] = {
                    "cost": float(delta_cost),
                    "co2": float(delta_co2),
                }

            # (2) heat_grid technologies -> also directly under heat_grid (flat)
            hg_data = selection.get("heat_grid")
            if isinstance(hg_data, dict):
                if set_reference_to_one_building:
                    hg_cluster = hg_data.get("buildings_in_cluster", 1)
                else:
                    hg_cluster = 1
                for technology in technologies:
                    total_cost = 0.0
                    total_co2 = 0.0
                    total_capacity = 0.0

                    for key, tech_data in hg_data.items():
                        if key in ("buildings_in_cluster", "buildings_in_cluster_used"):
                            continue
                        if not key.startswith(technology):
                            continue

                        total_cost += float(tech_data.get("investment_cost", 0.0)) / hg_cluster
                        total_co2 += float(tech_data.get("investment_co2", 0.0)) / hg_cluster
                        if technology != "building":
                            total_capacity += float(tech_data.get("capacity", 0.0))  / hg_cluster

                    readable = technology_name_map.get(technology, technology)
                    district_data[district_key]["heat_grid"][readable] = {
                        "cost": total_cost,
                        "co2": total_co2,
                        "capacity": total_capacity
                    }

            # (3) buildings: technologies per building
            for building_name, building_data in selection.items():
                if building_name not in buildings:
                    continue

                district_data[district_key][building_name] = {}

                if set_reference_to_one_building:
                    buildings_in_cluster = building_data.get("buildings_in_cluster", 1)
                else:
                    buildings_in_cluster = 1
                    buildings_in_cluster_scale_technology = results.get(building_name, {}).get("buildings_in_cluster",
                                                                                               1)

                for technology in technologies:
                    total_cost = 0.0
                    total_co2 = 0.0
                    total_capacity = 0.0

                    for key, tech_data in building_data.items():
                        if key in ("buildings_in_cluster", "buildings_in_cluster_used"):
                            continue
                        if not key.startswith(technology):
                            continue

                        total_cost += float(tech_data.get("investment_cost", 0.0)) / buildings_in_cluster
                        total_co2 += float(tech_data.get("investment_co2", 0.0)) / buildings_in_cluster
                        if technology != "building":
                            total_capacity += float(tech_data.get("capacity", 0.0)) * buildings_in_cluster_scale_technology/ buildings_in_cluster

                    readable = technology_name_map.get(technology, technology)
                    district_data[district_key][building_name][readable] = {
                        "cost": total_cost,
                        "co2": total_co2,
                        "capacity": total_capacity
                    }

        else:
            raise ValueError("cen_or_dec must be 'cen' or 'dec'")

    return district_data


def calculate_sums_for_technologies_and_energy_for_a_district(district_data, energy_types, technologies,building_name_map):
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
                    if tech == "Added trafo capacity" or tech == "Added line length":
                        continue
                    district_sums[district_id]['technologies'][tech]['cost'] += building_data.get(tech, {}).get('cost', 0)
                    district_sums[district_id]['technologies'][tech]['co2'] += building_data.get(tech, {}).get('co2', 0)
                    district_sums[district_id]['technologies'][tech]['capacity'] += building_data.get(tech, {}).get('capacity', 0)
                # Summiere für Energieträger (cost und co2)
                for energy in energy_types:
                    district_sums[district_id]['energy_types'][energy]['cost'] += building_data.get(energy, {}).get('cost', 0)
                    district_sums[district_id]['energy_types'][energy]['co2'] += building_data.get(energy, {}).get('co2', 0)
        district_sums[district_id]['technologies']["Added trafo capacity"]= {}
        district_sums[district_id]['technologies']["Added trafo capacity"]['capacity'] = district["electricity_grid"]["added_trafo_capacity"]
        district_sums[district_id]['technologies']["Added trafo capacity"]['cost'] = district["electricity_grid"]["added_trafo_cost"]
        district_sums[district_id]['technologies']["Added trafo capacity"]['co2'] = district["electricity_grid"]["added_trafo_co2"]

        district_sums[district_id]['technologies']["Added line length"]= {}
        district_sums[district_id]['technologies']["Added line length"]['capacity'] = district["electricity_grid"]["added_line_length"]
        district_sums[district_id]['technologies']["Added line length"]['cost'] = district["electricity_grid"]["added_line_cost"]
        district_sums[district_id]['technologies']["Added line length"]['co2'] = district["electricity_grid"]["added_line_co2"]


        district_sums[district_id]["peak"] = district["peak"]
        district_sums[district_id]["co2"] = district["co2"]
        district_sums[district_id]["totex"] = district["totex"]
    return district_sums
def _index_to_letters(i: int) -> str:
    # 0->A, 1->B, ... 25->Z, 26->AA ...
    i += 1
    s = ""
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(ord("A") + r) + s
    return s
def normalise_front_per_input_value(combined_front, input_value):
    """
    Returns a new list of records where co2, peak, totex are normalised
    per 100 m^2 of total floor area.

    Division factor: A_100 = total_floor_area_all / 100.
    """
    if input_value is None or input_value <= 0:
        raise ValueError("total_floor_area_all must be > 0 for normalisation.")

    A_100 = input_value

    out = []
    for r in combined_front:
        rr = dict(r)  # shallow copy
        rr["co2"] = rr["co2"] / A_100
        rr["peak"] = rr["peak"] / A_100
        rr["totex"] = rr["totex"] / A_100
        out.append(rr)

    return out

import os
def _nice_tick_step(n_points: int, target_ticks: int = 8) -> int:
    """Choose a 'nice' integer step (1,2,5 * 10^k) for index ticks."""
    if n_points <= 1:
        return 1
    raw = max(1.0, (n_points - 1) / max(1, (target_ticks - 1)))
    k = 10 ** int(np.floor(np.log10(raw)))
    candidates = np.array([1, 2, 5, 10]) * k
    step = int(candidates[np.argmin(np.abs(candidates - raw))])
    return max(1, step)


def _build_pareto_tick_indices(n_points: int, target_ticks: int = 8):
    """Indices + labels for Pareto-front points to highlight (like your stackplot ticks)."""
    if n_points <= 1:
        return np.array([0], dtype=int), ["0"]
    step = _nice_tick_step(n_points, target_ticks=target_ticks)
    idx = np.arange(0, n_points, step, dtype=int)
    if idx[-1] != n_points - 1:
        idx = np.append(idx, n_points - 1)
    labels = [str(int(i)) for i in idx]
    return idx, labels


def plot_all_points_with_front_and_tick_highlights(
    combined_front,
    pareto_front,                         # list of (co2, totex) tuples (already Pareto-optimal)
    # style / output
    filename,
    figsize=(6, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    dpi=600,
    show=False,
    # axis labels
    xlabel=r"Annual CO$_2$-eq in kg",
    ylabel=r"Totex in EUR",
    cbar_label=r"Peak load in kW",
    # tick-highlight logic (matches stackplot idea)
    target_xticks=8,
    max_labels=12,                        # label at most this many highlighted tick points
    # marker sizes
    s_all=10,
    alpha_all=0.65,
    s_tick=30,
    # pareto line style
    front_lw=1.3,
    front_ls="--",
):
    """
    Plot:
      - full combined front (scatter colored by peak + colorbar)
      - Pareto front curve (dashed)
      - highlight ONLY the Pareto-front points whose indices correspond to 'nice' tick indices
        (same logic as in your Pareto-solution x-axis ticks), with circle labels showing the index.
    Returns: (tick_indices, tick_points) where tick_points are (co2, totex) tuples.
    """

    # -----------------------------
    # GLOBAL FONT & STYLE SETTINGS
    # -----------------------------
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.titlesize": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
        "mathtext.fontset": "cm",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # -----------------------------
    # COLORS (journal-proof, colorblind)
    # -----------------------------
    palette = sns.color_palette("colorblind", n_colors=8)
    col_front = palette[3]   # dashed Pareto curve
    col_tick = palette[0]    # highlighted points + labels

    # -----------------------------
    # DATA: combined cloud (colored by peak)
    # -----------------------------
    co2_all = np.array([r["co2"] for r in combined_front], dtype=float)
    totex_all = np.array([r["totex"] for r in combined_front], dtype=float)
    peak_all = np.array([r["peak"] for r in combined_front], dtype=float)

    # -----------------------------
    # DATA: pareto front (sorted for stable indexing + clean curve)
    # -----------------------------
    pf = sorted(pareto_front, key=lambda t: (t[0], t[1]))
    pf_co2 = np.array([t[0] for t in pf], dtype=float)
    pf_totex = np.array([t[1] for t in pf], dtype=float)

    tick_idx, tick_labels = _build_pareto_tick_indices(len(pf), target_ticks=target_xticks)

    # label fewer if too many (still highlight all tick points; only label subset)
    label_idx = tick_idx
    label_labels = tick_labels
    if len(label_idx) > max_labels:
        keep = np.linspace(0, len(label_idx) - 1, max_labels).round().astype(int)
        label_idx = label_idx[keep]
        label_labels = [tick_labels[i] for i in keep]
    # --- drop penultimate label to avoid overlap, keep max label ---
    label_idx = list(label_idx)  # falls numpy array
    label_labels = list(label_labels)  # gleiche Länge

    if len(label_idx) >= 2:
        label_idx.pop(-2)  # vorletztes raus
        label_labels.pop(-2)  # passendes Label auch raus
    # tick points as tuples (for later matching/selection)
    tick_points = [pf[i] for i in tick_idx]

    # -----------------------------
    # FIGURE
    # -----------------------------
    fig, ax = plt.subplots(figsize=figsize)

    # Combined front scatter (colored by peak)
    sc = ax.scatter(
        co2_all,
        totex_all,
        c=peak_all,
        cmap="viridis",
        s=s_all,
        alpha=alpha_all,
        linewidths=0.0,
        zorder=1,
        label="All points",
    )

    # Pareto curve
    ax.plot(
        pf_co2,
        pf_totex,
        linestyle=front_ls,
        linewidth=front_lw,
        color=col_front,
        zorder=3,
        label="Pareto front",
    )

    # Highlight tick-index points on Pareto curve
    ax.scatter(
        pf_co2[tick_idx],
        pf_totex[tick_idx],
        s=s_tick,
        color=col_tick,
        edgecolors="white",
        linewidths=0.6,
        zorder=4,
        label="Pareto-optimal solution index ",
    )

    # Annotate only subset (clean)
    for idx, lab in zip(label_idx, label_labels):
        ax.annotate(
            lab,
            (pf_co2[idx], pf_totex[idx]),
            textcoords="offset points",
            xytext=(3, 3),
            ha="left",
            va="bottom",
            fontsize=font_size,
            color=col_tick,
            bbox=dict(boxstyle="circle,pad=0.18", fc="white", ec=col_tick, lw=0.6),
            zorder=5,
        )

    # Labels, grid
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25, linewidth=0.6)

    # Colorbar
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(cbar_label, fontsize=font_size)
    cbar.ax.tick_params(labelsize=font_size)

    # Legend
    ax.legend(frameon=False, loc="best")

    fig.tight_layout()
    fig.savefig(filename, format="pdf", dpi=dpi, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return tick_idx, tick_points


def run_pareto_plots(
    combined_front,
    out_prefix,
    width_inch,
    height_inch,
    font_size,
    out_dir,
    x_label,
    y_label,
    cbar_label,
    show,
    # NEW controls:
    add_index_front_plot=True,
    target_xticks=8,

):
    # 2D data for pareto extraction
    co2 = [r["co2"] for r in combined_front]
    cost = [r["totex"] for r in combined_front]
    data_2d = sorted(list(zip(co2, cost)))

    # Pareto envelope in (co2, totex)
    pareto_front = get_pareto_front(data_2d)
    pareto_co2, pareto_cost = zip(*pareto_front)

    # Your selection logic (unchanged)
    selected_points_y = select_evenly_spaced_pareto_points_focus_y_axis(pareto_front, num_points=12)
    selected_points_x = select_evenly_spaced_pareto_points_focus_x_axis(pareto_front, num_points=12)
    reduced_points = reduce_pareto_points(selected_points_y + selected_points_x)
    selected_co2, selected_cost = zip(*reduced_points)

    # --- Plots ---
    # Export 3 height variants for the 3 main plots:
    # base (100%), h85 (-15%), h70 (-30%).
    height_variants = (
        ("", 1.00),
        ("_h85", 0.85),
        ("_h70", 0.70),
    )
    for suffix, h_factor in height_variants:
        current_figsize = (width_inch, height_inch * h_factor)

        plot_all_pareto_points(
            combined_front,
            name=f"{out_prefix}_all_points{suffix}",
            figsize=current_figsize,
            font_size=font_size,
            filename=rf"{out_dir}\{out_prefix}_pareto_all_points{suffix}.pdf",
            xlabel=x_label,
            ylabel=y_label,
            cbar_label=cbar_label,
            show=show,
        )

        plot_pareto_co2_totex(
            co2_all=pareto_co2,
            totex_all=pareto_cost,
            selected_co2=selected_co2,
            selected_totex=selected_cost,
            name=f"{out_prefix}_front_only{suffix}",
            figsize=current_figsize,
            font_size=font_size,
            title="",
            filename=rf"{out_dir}\{out_prefix}_pareto_front{suffix}.pdf",
            xlabel=x_label,
            ylabel=y_label,
            show=show,
        )

        plot_all_points_with_front_and_selected(
            combined_front=combined_front,
            pareto_front=pareto_front,          # list of (co2, totex) tuples
            selected_co2=selected_co2,
            selected_totex=selected_cost,
            label_every=3,
            max_labels=10,
            figsize=current_figsize,
            font_size=font_size,
            filename=rf"{out_dir}\{out_prefix}_pareto_all_with_front_selected{suffix}.pdf",
            xlabel=x_label,
            ylabel=y_label,
            cbar_label=cbar_label,
            show=show,
        )

    tick_idx, tick_points = plot_all_points_with_front_and_tick_highlights(
        combined_front=combined_front,
        pareto_front=pareto_front,  # list of (co2, totex) tuples
        figsize=(width_inch, height_inch),
        font_size=font_size,
        filename=rf"{out_dir}\{out_prefix}_pareto_all_with_front_tick_highlights.pdf",
        xlabel=x_label,
        ylabel=y_label,
        cbar_label=cbar_label,
        target_xticks=8,  # same idea as stackplot tick logic
        max_labels=12,  # label at most 12 of those highlighted points
    )

    # convert tick indices to actual (co2, totex) points if you still need them:
    pf_sorted = sorted(pareto_front, key=lambda t: (t[0], t[1]))
    tick_points = [pf_sorted[i] for i in tick_idx]
    # matching (if you need it)
    matches_selected = find_exact_match_in_combined_front(reduced_points, combined_front)
    matches_front = find_exact_match_in_combined_front(pareto_front, combined_front)

    return {
        "pareto_front": pareto_front,
        "reduced_points": reduced_points,
        "matches_selected": matches_selected,
        "matches_front": matches_front,
        "tick_indices_for_stackplot": tick_idx,  # << use this if you want identical indices elsewhere
    }



def load_rep_info(pkl_path: str, kind: str, numeric: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    kind: "SFH" oder "MFH"
    Gibt zurück: {building_id: {"name", "net_floor_area", "buildings_in_cluster", "total_floor_area"}}
    """
    with open(pkl_path, "rb") as f:
        df = pickle.load(f)

    # falls Spaltennamen mal anders sind, hier anpassen:
    required = {"building_id", "net_floor_area", "buildings_in_cluster","number_of_residents"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {pkl_path}: {missing}")

    rep_info: Dict[str, Dict[str, Any]] = {}
    seen = set()
    rep_idx = 0

    for _, row in df.iterrows():
        bid = str(row["building_id"])
        if bid in seen:
            continue
        seen.add(bid)
        import ast

        profiles = len(ast.literal_eval(row["list_lpg_households"]))
        net_area = float(row["net_floor_area"])
        n_buildings = int(row["buildings_in_cluster"])
        n_residents = int(row["number_of_residents"])
        total_area = net_area * n_buildings
        number_of_apartments = profiles * n_buildings
        number_of_residents = n_residents * n_buildings
        suffix = str(rep_idx + 1) if numeric else _index_to_letters(rep_idx)
        name = f"Rep. {kind}-{suffix}"
        rep_idx += 1

        rep_info[bid] = {
            "name": name,
            "net_floor_area": net_area,
            "buildings_in_cluster": n_buildings,
            "total_floor_area": total_area,
            "number_of_households": number_of_apartments,
            "number_of_residents": number_of_residents,
        }

    return rep_info
# ============================================================
# Helper: plot comparison of Pareto fronts (points colored by PEAK)
# ============================================================
def plot_compare_pareto_fronts_peak(
    pareto_sets,
    filename,
    figsize=(6, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    xlabel=r"Annual CO$_2$-eq in kg",
    ylabel=r"Totex in EUR",
    cbar_label=r"Peak load in kW",
    dpi=600,
    show=False,
):
    """
    pareto_sets: dict like
      {
        "DENI...": {
           "co2": np.array([...]),
           "totex": np.array([...]),
           "peak": np.array([...]),
        }, ...
      }
    """
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.titlesize": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
        "mathtext.fontset": "cm",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # Global peak range (one shared colorbar)
    all_peaks = np.concatenate([v["peak"] for v in pareto_sets.values() if len(v["peak"]) > 0])
    vmin = np.nanmin(all_peaks)
    vmax = np.nanmax(all_peaks)

    # Marker shapes to distinguish UEUs (color still = peak)
    markers = ["o", "s", "^", "D", "P", "X"]

    fig, ax = plt.subplots(figsize=figsize)

    # use same colormap across all sets
    cmap = plt.get_cmap("viridis")

    for i, (ueu_short, data) in enumerate(pareto_sets.items()):
        sc = ax.scatter(
            data["co2"],
            data["totex"],
            c=data["peak"],
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            s=16,
            alpha=0.85,
            marker=markers[i % len(markers)],
            linewidths=0.25,
            edgecolors="white",
            label=ueu_short,
            zorder=2,
        )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25, linewidth=0.6)

    # legend: only distinguishes UEUs (marker shape)
    ax.legend(frameon=False, loc="best")

    # shared colorbar for peak
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(cbar_label, fontsize=font_size)
    cbar.ax.tick_params(labelsize=font_size)

    fig.tight_layout()
    fig.savefig(filename, format="pdf", dpi=dpi, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)
def maniupulate_combined_front_elect_grid(combined_front,no_electricity_grid_active):

    # Iterate over the combined_front (assuming it's a list of solutions)
    if no_electricity_grid_active:
        for idx, solution in enumerate(combined_front):
            combined_front[idx]["Electricity_Grid"] = {}
            combined_front[idx]["Electricity_Grid"][
                "added_trafo_cost"] =0
            combined_front[idx]["Electricity_Grid"][
                "added_line_cost"] =0
            combined_front[idx]["Electricity_Grid"][
                "added_line_length"] =0
            combined_front[idx]["Electricity_Grid"][
                "added_line_co2"] =0
            combined_front[idx]["Electricity_Grid"][
                "added_trafo_co2"] =0
            combined_front[idx]["Electricity_Grid"][
                "added_trafo_capacity"] =0
            combined_front[idx]["Electricity_Grid"][
                "investment_cost"] =0
    else:

        for idx, solution in enumerate(combined_front):
            combined_front[idx]["co2"] = combined_front[idx]["co2"] - combined_front[idx]["Electricity_Grid"]["added_line_co2"]
            combined_front[idx]["Electricity_Grid"]["added_line_co2"] = combined_front[idx]["Electricity_Grid"]["added_line_co2"]/100
            combined_front[idx]["co2"] = combined_front[idx]["co2"] + combined_front[idx]["Electricity_Grid"]["added_line_co2"]
    return combined_front
def maniupulate_combined_front(combined_front,value_types,building_in_cluster):
    technologies = ["pv_system", "heat_storage", "battery", "gas_heater", "chp", "hp", "building"]
    carriers = ["Electricity", "NaturalGas", "BioGas", "Hydrogen"]

    # Iterate over the combined_front (assuming it's a list of solutions)
    for idx, solution in enumerate(combined_front):
        totex = 0  # Reset totex for each solution
        totex += combined_front[idx]["Electricity_Grid"]["added_line_cost"] + combined_front[idx]["Electricity_Grid"]["added_trafo_cost"]
        for building in building_in_cluster:
            # Step 1: Add the totex based on carrier data (grid costs and revenues)
            for carrier in carriers:
                totex += solution["selection"][building]["record"]["results"][carrier]["flow_from_grid_cost"]
                if solution["selection"][building]["record"]["results"][carrier]["flow_into_grid_revenue"] is not None:
                    totex -= solution["selection"][building]["record"]["results"][carrier]["flow_into_grid_revenue"]

            # Step 2: Add the totex for each technology
            for technology in technologies:
                # Check for multiple instances of technologies (like gas_heater_DENILD...)
                tech_keys = [key for key in solution["selection"][building]["record"]["results"][building].keys() if
                             key.startswith(f"{technology}_{building}")]
                for tech_key in tech_keys:
                    tech_data = solution["selection"][building]["record"]["results"][building][tech_key]
                    if "investment_cost" in tech_data:
                        totex += tech_data["investment_cost"]

            # Optional: If the 'building' itself has an 'investment_cost', add it as well
            building_data = solution["selection"][building]["record"]["results"][building]
            if "investment_cost" in building_data:
                totex += building_data["investment_cost"]

        # Save the calculated totex back into the combined_front for the current solution
        combined_front[idx]["totex_control"] = combined_front[idx]["totex"]
        combined_front[idx]["totex"] = totex
    return combined_front
    # Now `totex` contains the total investment costs for all technologies and carriers across all buildings
    # combined_front[idx]["totex1"] now holds the `totex` value for each solution in the list

def ueu_display(name_or_short: str) -> str:

    return UEU_NAME_MAP.get(name_or_short, name_or_short)
UEU_NAME_MAP = {
    "DENI03403000SEC4580": "Low heat density",
    "DENI03403000SEC5658": "Medium heat density",
    "DENI03403000SEC5101": "High heat density",
}
if __name__ == "__main__":# ============================================================

    import os
    import pickle
    import numpy as np
    import matplotlib.pyplot as plt
    import seaborn as sns

    # ============================================================
    # CONFIG (your base)
    # ============================================================
    ueu_list = [
        "processed_bds_in_DENI03403000SEC5658",
        "processed_bds_in_DENI03403000SEC4580",
        "processed_bds_in_DENI03403000SEC5101",
    ]
    no_electricity_grid_active = True
    base_path = r"C:\Users\hill_mx\Desktop\From Luis\Case Studies\Small New"
    out_dir   = r"C:\Users\hill_mx\Desktop\123"
    input_dir = r"C:\Users\hill_mx\Desktop\123"
    if False:
        result_name = "cen_processed_2026_01_28_combined_front_of__elect_grid_considered_"
        cen_or_dec = "cen"
    else:
        result_name = "dec_processed_2026_03_17_combined_front_of_"  # cen
        cen_or_dec = "dec"
    width_cm  = 15.11293
    height_cm = 6.5 * 1.8
    width_inch  = width_cm / 2.54
    height_inch = height_cm / 2.54
    font_size = 9

    energy_types = ["Electricity", "Bio gas", "Natural gas", "Hydrogen"]
    technologies = ["PV-System", "Heat storage", "Battery", "Gas heater", "CHP", "Heat pump", "Added trafo capacity","Added line length","Retrofit"]

    value_types = ["cost", "co2", "capacity"]
    Y_LABELS_PER_100M2 = {
        "cost": "Annual TOTEX in EUR per 100 m$^2$",
        "co2": r"Annual CO$_2$-eq in kg per 100 m$^2$",
        "capacity": "Installed capacity in kW or kWh per 100 m$^2$",
    }

    # ============================================================
    # STORAGE: collect results while looping
    # ============================================================
    ueu_results = {}  # {ueu_short: {...}} stored while looping

    # ============================================================
    # LOOP OVER UEUs
    # ============================================================
    for ueu in ueu_list:
        print(ueu)
        ueu_short = ueu.removeprefix("processed_bds_in_")
        print(f"\n=== UEU: {ueu_short} ===")
        if ueu=="processed_bds_in_DENI03403000SEC5658":
            print("EXTRA CASE FOR 5658 SINCE IT IS NOT CLUSTERED RESULTS")
            path1=r"C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model\examples\03_advanced_investment_optimization"
            import geopandas as gpd
            import pandas as pd
            gpkg_ueu = os.path.join(path1, ueu, f"{ueu}.gpkg")
            gdf_ueu = gpd.read_file(gpkg_ueu)
            sfh_cluster = gdf_ueu.loc[gdf_ueu["tabula_building_type"] == "SFH"].copy()
            mfh_cluster = gdf_ueu.loc[gdf_ueu["tabula_building_type"] == "MFH"].copy()
            all_buildings = pd.concat([sfh_cluster.copy(), mfh_cluster.copy()], ignore_index=True)
            import numpy as np
            import ast

            import numpy as np


            def get_household_count(x):
                if isinstance(x, (list, tuple, np.ndarray)):
                    return len(x)

                if isinstance(x, str):
                    s = x.strip()
                    assert s.startswith("[") and s.endswith("]"), f"Kein Listen-String: {x}"
                    inner = s[1:-1].strip()
                    if inner == "":
                        return 0
                    return inner.count(",") + 1

                raise TypeError(f"Unerwarteter Typ: {type(x)} mit Wert {x}")


            all_buildings["number_of_households"] = all_buildings["list_number_of_adults"].apply(get_household_count)
            rep_info = {
                row["building_id"]: {
                    "name": row["building_id"],
                    "net_floor_area": float(row["net_floor_area"]),
                    "buildings_in_cluster": 1,
                    "total_floor_area": float(row["net_floor_area"]),
                    "number_of_households": len(row["list_number_of_adults"]),
                    "number_of_residents": int(row["number_of_residents"]) if not pd.isna(
                        row["number_of_residents"]) else 0,
                }
                for _, row in all_buildings.iterrows()
            }
        # ---- input paths for rep info ----
        else:
            path_mfh = os.path.join(base_path, ueu, "mfh_cluster.pkl")
            path_sfh = os.path.join(base_path, ueu, "sfh_cluster.pkl")

            sfh_rep_info = load_rep_info(path_sfh, "SFH", numeric=False)
            mfh_rep_info = load_rep_info(path_mfh, "MFH", numeric=False)

            rep_info = {**sfh_rep_info, **mfh_rep_info}
        building_in_cluster = list(rep_info.keys())
        total_floor_area_all = sum(info["total_floor_area"] for info in rep_info.values())
        total_number_of_households = sum(info["number_of_households"] for info in rep_info.values())

        print("Total floor area:", total_floor_area_all)

        # ---- load combined front (pickle) ----
        combined_front_path = os.path.join(
            input_dir,
            f"{result_name}{ueu_short}.pkl"
        )

        if not os.path.exists(combined_front_path):
            print(f"WARNING: missing combined-front file: {combined_front_path}")
            continue

        with open(combined_front_path, "rb") as f:
            building_dict_loaded = pickle.load(f)

        combined_front = building_dict_loaded[2]

        combined_front = maniupulate_combined_front_elect_grid(combined_front,no_electricity_grid_active)

        #combined_front = maniupulate_combined_front(combined_front,value_types,building_in_cluster)

        combined_front_per100 = normalise_front_per_input_value(
            combined_front=combined_front,
            input_value=total_floor_area_all/100,
        )
        combined_front_per_household = normalise_front_per_input_value(
            combined_front=combined_front,
            input_value=total_number_of_households,
        )
        # ------------------------------------------------------------
        # (1) Pareto plots: absolute + per 100 m²
        # ------------------------------------------------------------
        if True:
            res_abs = run_pareto_plots(
                show=False,
                combined_front=combined_front,
                out_prefix=f"{cen_or_dec}_{ueu_display(ueu_short)}_abs",
                width_inch=width_inch,
                height_inch=height_inch,
                font_size=font_size,
                out_dir=out_dir,
                x_label=r"Annual CO$_2$-eq in kg",
                y_label=r"Annual TOTEX in EUR",
                cbar_label=r"Peak load in kW",
            )

            if True:

                res_per100 = run_pareto_plots(
                    show=False,
                    combined_front=combined_front_per100,
                    out_prefix=f"{cen_or_dec}_{ueu_display(ueu_short)}_per_100m2",
                    width_inch=width_inch,
                    height_inch=height_inch,
                    font_size=font_size,
                    out_dir=out_dir,
                    x_label=r"Annual CO$_2$-eq in kg per 100 m$^2$",
                    y_label=r"Annual TOTEX in EUR per 100 m$^2$",
                    cbar_label=r"Peak load in kW per 100 m$^2$",
                )
                res_per_household = run_pareto_plots(
                    show=False,
                    combined_front=combined_front_per_household,
                    out_prefix=f"{cen_or_dec}_{ueu_display(ueu_short)}_per_household",
                    width_inch=width_inch,
                    height_inch=height_inch,
                    font_size=font_size,
                    out_dir=out_dir,
                    x_label=r"Annual CO$_2$-eq in kg per household",
                    y_label=r"Totex EUR per household",
                    cbar_label=r"Peak load in kW per household",
                )
        # ------------------------------------------------------------

        pareto_front_abs = res_abs["pareto_front"]  # list[(co2, totex)]  (ABS)
        matches_front_abs = res_abs["matches_front"]  # list[dict] matched from combined_front (ABS)
        if True:
            pareto_front_per100 = res_per100["pareto_front"]  # list[(co2, totex)]  (PER 100 m²)
            matches_front_per100 = res_per100["matches_front"]  # list[dict] matched from combined_front_per100 (PER 100 m²)BS)

            pareto_front_per_household = res_per_household["pareto_front"]  # list[(co2, totex)]  (PER 100 m²)
            matches_front_per_household = res_per_household["matches_front"]  # list[dict] matched from combined_front_per100 (PER 100 m²)
        def _rounded_key(c, t, dec=6):
            return (round(float(c), dec), round(float(t), dec))


        def _extract_peak_aligned(pareto_front, matches_front, lookup_records, dec=6):
            """
            Returns peak array aligned to pareto_front.
            - If matches_front has same length -> assume same order and take peaks directly
            - Else -> fallback to lookup by rounded (co2, totex)
            """
            if isinstance(matches_front, list) and len(matches_front) == len(pareto_front):
                return np.array([float(m.get("peak", np.nan)) for m in matches_front], dtype=float)

            lookup = {
                _rounded_key(r["co2"], r["totex"], dec): float(r.get("peak", np.nan))
                for r in lookup_records
                if r is not None and "co2" in r and "totex" in r
            }
            return np.array([lookup.get(_rounded_key(c, t, dec), np.nan) for (c, t) in pareto_front], dtype=float)

        if True:
            # -------- ABS plot data --------
            pf_abs_co2 = np.array([pt[0] for pt in pareto_front_abs], dtype=float)
            pf_abs_totex = np.array([pt[1] for pt in pareto_front_abs], dtype=float)
            pf_abs_peak = _extract_peak_aligned(
                pareto_front=pareto_front_abs,
                matches_front=matches_front_abs,
                lookup_records=combined_front,  # IMPORTANT: ABS lookup uses ABS combined_front
            )

            # -------- PER 100 m² plot data --------
            pf_per_co2 = np.array([pt[0] for pt in pareto_front_per100], dtype=float)
            pf_per_totex = np.array([pt[1] for pt in pareto_front_per100], dtype=float)
            pf_per_peak = _extract_peak_aligned(
                pareto_front=pareto_front_per100,
                matches_front=matches_front_per100,
                lookup_records=combined_front_per100,  # IMPORTANT: per100 lookup uses per100 combined_front
            )

            # -------- PER HOUSEHOLD plot data --------
            pf_hh_co2 = np.array([pt[0] for pt in pareto_front_per_household], dtype=float)
            pf_hh_totex = np.array([pt[1] for pt in pareto_front_per_household], dtype=float)
            pf_hh_peak = _extract_peak_aligned(
                pareto_front=pareto_front_per_household,
                matches_front=matches_front_per_household,
                lookup_records=combined_front_per_household,
                # IMPORTANT: per-household lookup uses per-household combined front
            )

            # -------- store --------
            ueu_results[ueu_display(ueu_short)] = {
                "total_floor_area_all": total_floor_area_all,

                "pareto_front_abs": pareto_front_abs,
                "pareto_front_per100": pareto_front_per100,
                "pareto_front_per_household": pareto_front_per_household,

                "pareto_plotdata_abs": {
                    "co2": pf_abs_co2,
                    "totex": pf_abs_totex,
                    "peak": pf_abs_peak,
                },
                "pareto_plotdata_per100": {
                    "co2": pf_per_co2,
                    "totex": pf_per_totex,
                    "peak": pf_per_peak,
                },
                "pareto_plotdata_per_household": {
                    "co2": pf_hh_co2,
                    "totex": pf_hh_totex,
                    "peak": pf_hh_peak,
                },

                # keep anything else you might need
                "res_abs": res_abs,
                "res_per100": res_per100,
                "res_per_household": res_per_household,
            }
        # ------------------------------------------------------------
        # District sums for stackplots (per 100 m²)
        # ------------------------------------------------------------
        matches_whole_front = find_exact_match_in_combined_front(pareto_front_abs, combined_front)
        if not matches_whole_front:
            print(f"WARNING: No matches for Pareto front in combined_front for UEU {ueu_display(ueu_short)}. Skipping stackplots.")
            continue

        processed_district_data = process_district_data(matches_whole_front,building_in_cluster,cen_or_dec)
        processed_district_data = process_units_for_processed(
            processed_district_data,
            floor_area=total_floor_area_all / 100.0,
        )
        building_name_map = {bid: info["name"] for bid, info in rep_info.items()}
        if cen_or_dec == "cen":
            building_name_map["heat_grid"] = "Heat grid"

        district_sums = calculate_sums_for_technologies_and_energy_for_a_district(
            processed_district_data,
            energy_types,
            technologies,
            building_name_map
        )

        # ------------------------------------------------------------
        # (2) Stackplots (per 100 m²)
        # ------------------------------------------------------------
        if True:
            for vt in value_types:
                fig, ax1, ax2 = plot_stackplot_for_pareto_solutions_with_peak(
                    district_sums=district_sums,
                    technologies=technologies,
                    energy_types=energy_types,
                    value_type=vt,
                    figsize=(width_inch, height_inch),
                    font_size=font_size,
                    show=False,
                    filename=os.path.join(out_dir, f"{cen_or_dec}_{ueu_display(ueu_short)}_stackplot_{vt}_per_100m2.pdf"),
                    x_label="Pareto-optimal solution index (sorted)",
                    sort_key=None,
                    target_xticks=8,
                    peak_lw=0.5,
                    peak_drawstyle="steps-mid",
                    legend_ncol=4,
                )

                ax1.set_ylabel(Y_LABELS_PER_100M2[vt])
                ax2.set_ylabel("Annual peak load in kW per 100 m$^2$")

                fig.savefig(
                    os.path.join(out_dir, f"{cen_or_dec}_{ueu_display(ueu_short)}_stackplot_{vt}_per_100m2.pdf"),
                    dpi=600,
                    bbox_inches="tight",
                    format="pdf",
                )
                plt.close(fig)

            print(f"Done: {ueu_display(ueu_short)}")

    # AFTER LOOP: one comparison plot across UEUs
    # (ABS Pareto fronts, points colored by peak; marker shape distinguishes UEU)
    # ============================================================
    pareto_sets_abs = {
        ueu_display(ueu_short): ueu_results[ueu_display(ueu_short)]["pareto_plotdata_abs"]
        for ueu_short in ueu_results.keys()
    }

    plot_compare_pareto_fronts_peak(
        pareto_sets=pareto_sets_abs,
        filename=os.path.join(out_dir, "COMPARE_pareto_fronts_abs_peak_colored.pdf"),
        figsize=(width_inch, height_inch),
        font_size=font_size,
        xlabel=r"Annual CO$_2$-eq in kg",
        ylabel=r"Annual TOTEX in EUR",
        cbar_label=r"Peak load in kW",
        show=False,
    )
    import os
    import numpy as np
    import matplotlib.pyplot as plt

    import os
    import numpy as np
    import matplotlib.pyplot as plt


    def plot_compare_per100_perhh_pareto_fronts_peak(
            ueu_results,
            filename,
            figsize=(8, 4),
            font_size=9,
            font_family="TeX Gyre Termes",
            # axis labels
            xlabel_per100=r"Annual CO$_2$-eq in kg per 100 m$^2$",
            ylabel_per100=r"Annual TOTEX in EUR per 100 m$^2$",
            xlabel_perhh=r"Annual CO$_2$-eq in kg per household",
            ylabel_perhh=r"Totex EUR per household",
            # colorbar labels
            cbar_label_per100=r"Peak load in kW per 100 m$^2$",
            cbar_label_perhh=r"Peak load in kW per household",
            legend_ncol=3,
            dpi=600,
            show=False,
            debug_print=False,
    ):
        import numpy as np
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.ticker import FuncFormatter

        # -----------------------------
        # GLOBAL STYLE
        # -----------------------------
        plt.style.use("default")
        plt.rcParams.update({
            "font.family": font_family,
            "font.size": font_size,
            "axes.labelsize": font_size,
            "xtick.labelsize": font_size,
            "ytick.labelsize": font_size,
            "legend.fontsize": font_size,
            "mathtext.fontset": "cm",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        })

        # Make sure no weird white "under/over/bad" behavior
        cmap = plt.get_cmap("viridis").copy()
        cmap.set_under(cmap(0.0))
        cmap.set_over(cmap(1.0))
        cmap.set_bad(cmap(0.0))

        # -----------------------------
        # STABLE MARKERS PER UEU
        # -----------------------------
        markers = ["o", "s", "^", "D", "P", "X", "v", "<", ">"]
        ueu_keys = sorted(ueu_results.keys())
        marker_map = {k: markers[i % len(markers)] for i, k in enumerate(ueu_keys)}

        # -----------------------------
        # COLLECT DATA (only per100 + perhh)
        # -----------------------------
        panels = {"per100": {}, "perhh": {}}
        peaks = {"per100": [], "perhh": []}

        for k in ueu_keys:
            r = ueu_results[k]
            for key, name in [
                ("per100", "pareto_plotdata_per100"),
                ("perhh", "pareto_plotdata_per_household"),
            ]:
                x = np.asarray(r[name]["co2"], float)
                y = np.asarray(r[name]["totex"], float)
                p = np.asarray(r[name]["peak"], float)
                panels[key][k] = (x, y, p)
                if np.isfinite(p).any():
                    peaks[key].append(p[np.isfinite(p)])

        # robust vlims for colorbars
        vlims = {}
        for key, arrs in peaks.items():
            if arrs:
                vv = np.concatenate(arrs)
                vlims[key] = (float(np.nanmin(vv)), float(np.nanmax(vv)))
            else:
                vlims[key] = (0.0, 1.0)

        # -----------------------------
        # TRUE DATA RANGES (NO MATPLOTLIB MARGINS)
        # -----------------------------
        def _finite_minmax(arr):
            arr = np.asarray(arr, float)
            arr = arr[np.isfinite(arr)]
            if arr.size == 0:
                return (0.0, 1.0)
            return (float(arr.min()), float(arr.max()))

        panel_ranges = {}
        for panel_key in ["per100", "perhh"]:
            allx, ally = [], []
            for k in ueu_keys:
                x, y, _ = panels[panel_key][k]
                if x is not None and len(x):
                    allx.append(np.asarray(x, float))
                if y is not None and len(y):
                    ally.append(np.asarray(y, float))
            x_min, x_max = _finite_minmax(np.concatenate(allx) if allx else np.array([0.0, 1.0]))
            y_min, y_max = _finite_minmax(np.concatenate(ally) if ally else np.array([0.0, 1.0]))
            panel_ranges[panel_key] = {"x": (x_min, x_max), "y": (y_min, y_max)}

        if debug_print:
            print("---- DATA MIN/MAX (true, before snapping) ----")
            for pk in ["per100", "perhh"]:
                print(f"{pk:6s}  x_min={panel_ranges[pk]['x'][0]:.6g}, x_max={panel_ranges[pk]['x'][1]:.6g}   "
                      f"y_min={panel_ranges[pk]['y'][0]:.6g}, y_max={panel_ranges[pk]['y'][1]:.6g}")

        # -----------------------------
        # NICE TICKS (1-2-5 * 10^n), NO SCI NOTATION
        # -----------------------------
        def _nice_125_step(span, ntarget=5):
            if span <= 0 or not np.isfinite(span):
                return 1.0
            raw = span / max(ntarget - 1, 1)
            exp = np.floor(np.log10(raw))
            f = raw / (10 ** exp)
            if f <= 1:
                m = 1
            elif f <= 2:
                m = 2
            elif f <= 5:
                m = 5
            else:
                m = 10
            return m * (10 ** exp)

        def _nice_ticks_and_limits(vmin, vmax, ntarget=5):
            if not (np.isfinite(vmin) and np.isfinite(vmax)):
                vmin, vmax = 0.0, 1.0
            if vmin == vmax:
                dv = 1.0 if vmin == 0 else abs(vmin) * 0.1
                vmin, vmax = vmin - dv, vmax + dv

            span = vmax - vmin
            step = _nice_125_step(span, ntarget=ntarget)

            vmin_n = np.floor(vmin / step) * step
            vmax_n = np.ceil(vmax / step) * step
            ticks = np.arange(vmin_n, vmax_n + 0.5 * step, step)

            ticks[np.isclose(ticks, 0)] = 0.0
            if np.isclose(vmin_n, 0):
                vmin_n = 0.0
            if np.isclose(vmax_n, 0):
                vmax_n = 0.0

            return ticks, vmin_n, vmax_n

        def _int_no_sci_formatter(x, pos=None):
            if np.isclose(x, round(x)):
                return f"{int(round(x))}"
            s = f"{x:.4f}".rstrip("0").rstrip(".")
            return s

        _intfmt = FuncFormatter(_int_no_sci_formatter)

        def _apply_nice_axis_using_data(ax, x_minmax, y_minmax, ntarget=5):
            xt, xmin_n, xmax_n = _nice_ticks_and_limits(x_minmax[0], x_minmax[1], ntarget=ntarget)
            yt, ymin_n, ymax_n = _nice_ticks_and_limits(y_minmax[0], y_minmax[1], ntarget=ntarget)

            ax.set_xlim(xmin_n, xmax_n)
            ax.set_ylim(ymin_n, ymax_n)
            ax.set_xticks(xt)
            ax.set_yticks(yt)

            ax.xaxis.set_major_formatter(_intfmt)
            ax.yaxis.set_major_formatter(_intfmt)

            if debug_print:
                print(f"AXIS set -> xlim=({xmin_n:.6g},{xmax_n:.6g}) ylim=({ymin_n:.6g},{ymax_n:.6g})")

        # -----------------------------
        # FIGURE (2 panels)
        # -----------------------------
        fig, axes = plt.subplots(
            ncols=2,
            figsize=figsize,
            gridspec_kw={"wspace": 0.40}
        )

        def scatter(ax, data, vmin, vmax):
            sc = None
            for k in ueu_keys:
                x, y, p = data[k]
                if len(x):
                    sc = ax.scatter(
                        x, y,
                        c=p, cmap=cmap, vmin=vmin, vmax=vmax,
                        s=20,
                        marker=marker_map[k],
                        edgecolors="none",  # <- no black outline
                        linewidths=0.0,
                    )
            ax.grid(True, alpha=0.25)
            ax.margins(x=0.0, y=0.0)
            return sc

        sc_per100 = scatter(axes[0], panels["per100"], *vlims["per100"])
        axes[0].set_xlabel(xlabel_per100)
        axes[0].set_ylabel(ylabel_per100)

        sc_perhh = scatter(axes[1], panels["perhh"], *vlims["perhh"])
        axes[1].set_xlabel(xlabel_perhh)
        axes[1].set_ylabel(ylabel_perhh)

        if debug_print:
            print("---- AXIS LIMITS AFTER SNAPPING ----")

        _apply_nice_axis_using_data(axes[0], panel_ranges["per100"]["x"], panel_ranges["per100"]["y"], ntarget=5)
        _apply_nice_axis_using_data(axes[1], panel_ranges["perhh"]["x"], panel_ranges["perhh"]["y"], ntarget=5)

        # -----------------------------
        # LEGEND (markers, black)
        # -----------------------------
        legend_handles = [
            Line2D(
                [0], [0],
                marker=marker_map[k],
                linestyle="None",
                markerfacecolor="none",
                markeredgecolor="black",
                color="black",
                markersize=6,
                label=k,
            )
            for k in ueu_keys
        ]

        fig.legend(
            handles=legend_handles,
            frameon=False,
            loc="upper center",
            ncol=min(legend_ncol, len(legend_handles)),
        )

        fig.tight_layout(rect=[0, 0, 1, 0.90])

        # -----------------------------
        # COLORBARS (default ticks, no "nice ending")
        # -----------------------------
        for ax, sc, label in zip(
                axes,
                [sc_per100, sc_perhh],
                [cbar_label_per100, cbar_label_perhh],
        ):
            if sc is not None:
                cbar = fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.92)
                cbar.set_label(label)
                cbar.ax.tick_params(labelsize=font_size)

        fig.savefig(filename, dpi=dpi, bbox_inches="tight")
        if show:
            plt.show()
        else:
            plt.close(fig)
    def plot_compare_abs_per100_perhh_pareto_fronts_peak(
        ueu_results,
        filename,
        figsize=(12, 4),
        font_size=9,
        font_family="TeX Gyre Termes",
        # axis labels
        xlabel_abs=r"Annual CO$_2$-eq in kg",
        ylabel_abs=r"Annual TOTEX in EUR",
        xlabel_per100=r"Annual CO$_2$-eq in kg per 100 m$^2$",
        ylabel_per100=r"Annual TOTEX in EUR per 100 m$^2$",
        xlabel_perhh=r"Annual CO$_2$-eq in kg per household",
        ylabel_perhh=r"Totex EUR per household",
        # colorbar labels
        cbar_label_abs=r"Peak load in kW",
        cbar_label_per100=r"Peak load in kW per 100 m$^2$",
        cbar_label_perhh=r"Peak load in kW per household",
        legend_ncol=3,
        dpi=600,
        show=False,
        debug_print=True,   # <- Kontroll-Prints AN/AUS
    ):
        import numpy as np
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.ticker import FuncFormatter

        # -----------------------------
        # GLOBAL STYLE
        # -----------------------------
        plt.style.use("default")
        plt.rcParams.update({
            "font.family": font_family,
            "font.size": font_size,
            "axes.labelsize": font_size,
            "xtick.labelsize": font_size,
            "ytick.labelsize": font_size,
            "legend.fontsize": font_size,
            "mathtext.fontset": "cm",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        })

        cmap = plt.get_cmap("viridis")

        # -----------------------------
        # STABLE MARKERS PER UEU
        # -----------------------------
        markers = ["o", "s", "^", "D", "P", "X", "v", "<", ">"]
        ueu_keys = sorted(ueu_results.keys())
        marker_map = {k: markers[i % len(markers)] for i, k in enumerate(ueu_keys)}

        # -----------------------------
        # COLLECT DATA
        # -----------------------------
        panels = {"abs": {}, "per100": {}, "perhh": {}}
        peaks = {"abs": [], "per100": [], "perhh": []}

        for k in ueu_keys:
            r = ueu_results[k]
            for key, name in [
                ("abs", "pareto_plotdata_abs"),
                ("per100", "pareto_plotdata_per100"),
                ("perhh", "pareto_plotdata_per_household"),
            ]:
                x = np.asarray(r[name]["co2"], float)
                y = np.asarray(r[name]["totex"], float)
                p = np.asarray(r[name]["peak"], float)
                panels[key][k] = (x, y, p)
                if np.isfinite(p).any():
                    peaks[key].append(p[np.isfinite(p)])

        # robust vlims for colorbars
        vlims = {}
        for key, arrs in peaks.items():
            if arrs:
                vv = np.concatenate(arrs)
                vlims[key] = (float(np.nanmin(vv)), float(np.nanmax(vv)))
            else:
                vlims[key] = (0.0, 1.0)

        # -----------------------------
        # TRUE DATA RANGES (NO MATPLOTLIB MARGINS)
        # -----------------------------
        def _finite_minmax(arr):
            arr = np.asarray(arr, float)
            arr = arr[np.isfinite(arr)]
            if arr.size == 0:
                return (0.0, 1.0)
            return (float(arr.min()), float(arr.max()))

        panel_ranges = {}
        for panel_key in ["abs", "per100", "perhh"]:
            allx, ally = [], []
            for k in ueu_keys:
                x, y, _ = panels[panel_key][k]
                if x is not None and len(x):
                    allx.append(np.asarray(x, float))
                if y is not None and len(y):
                    ally.append(np.asarray(y, float))
            x_min, x_max = _finite_minmax(np.concatenate(allx) if allx else np.array([0.0, 1.0]))
            y_min, y_max = _finite_minmax(np.concatenate(ally) if ally else np.array([0.0, 1.0]))
            panel_ranges[panel_key] = {"x": (x_min, x_max), "y": (y_min, y_max)}

        if debug_print:
            print("---- DATA MIN/MAX (true, before snapping) ----")
            for pk in ["abs", "per100", "perhh"]:
                print(f"{pk:6s}  x_min={panel_ranges[pk]['x'][0]:.6g}, x_max={panel_ranges[pk]['x'][1]:.6g}   "
                      f"y_min={panel_ranges[pk]['y'][0]:.6g}, y_max={panel_ranges[pk]['y'][1]:.6g}")

        # -----------------------------
        # SCIENTIFIC NICE TICKS (1-2-5 * 10^n), NO SCI NOTATION
        # -----------------------------
        def _nice_125_step(span, ntarget=5):
            if span <= 0 or not np.isfinite(span):
                return 1.0
            raw = span / max(ntarget - 1, 1)
            exp = np.floor(np.log10(raw))
            f = raw / (10 ** exp)
            if f <= 1:
                m = 1
            elif f <= 2:
                m = 2
            elif f <= 5:
                m = 5
            else:
                m = 10
            return m * (10 ** exp)

        def _nice_ticks_and_limits(vmin, vmax, ntarget=5):
            if not (np.isfinite(vmin) and np.isfinite(vmax)):
                vmin, vmax = 0.0, 1.0
            if vmin == vmax:
                dv = 1.0 if vmin == 0 else abs(vmin) * 0.1
                vmin, vmax = vmin - dv, vmax + dv

            span = vmax - vmin
            step = _nice_125_step(span, ntarget=ntarget)

            vmin_n = np.floor(vmin / step) * step
            vmax_n = np.ceil(vmax / step) * step

            ticks = np.arange(vmin_n, vmax_n + 0.5 * step, step)

            # avoid "-0"
            ticks[np.isclose(ticks, 0)] = 0.0
            if np.isclose(vmin_n, 0):
                vmin_n = 0.0
            if np.isclose(vmax_n, 0):
                vmax_n = 0.0

            return ticks, vmin_n, vmax_n

        def _int_no_sci_formatter(x, pos=None):
            if np.isclose(x, round(x)):
                return f"{int(round(x))}"
            s = f"{x:.4f}".rstrip("0").rstrip(".")
            return s

        _intfmt = FuncFormatter(_int_no_sci_formatter)

        def _apply_nice_axis_using_data(ax, x_minmax, y_minmax, ntarget=5):
            xt, xmin_n, xmax_n = _nice_ticks_and_limits(x_minmax[0], x_minmax[1], ntarget=ntarget)
            yt, ymin_n, ymax_n = _nice_ticks_and_limits(y_minmax[0], y_minmax[1], ntarget=ntarget)

            ax.set_xlim(xmin_n, xmax_n)
            ax.set_ylim(ymin_n, ymax_n)
            ax.set_xticks(xt)
            ax.set_yticks(yt)

            ax.xaxis.set_major_formatter(_intfmt)
            ax.yaxis.set_major_formatter(_intfmt)

            if debug_print:
                print(f"AXIS set -> xlim=({xmin_n:.6g},{xmax_n:.6g}) ylim=({ymin_n:.6g},{ymax_n:.6g})")

        def _apply_nice_cbar(cbar, ntarget=5):
            vmin, vmax = cbar.mappable.get_clim()
            ticks, _, _ = _nice_ticks_and_limits(float(vmin), float(vmax), ntarget=ntarget)
            cbar.set_ticks(ticks)
            cbar.ax.yaxis.set_major_formatter(_intfmt)

        # -----------------------------
        # FIGURE
        # -----------------------------
        fig, axes = plt.subplots(
            ncols=3,
            figsize=figsize,
            gridspec_kw={"wspace": 0.40}
        )

        def scatter(ax, data, vmin, vmax):
            sc = None
            for k in ueu_keys:
                x, y, p = data[k]
                if len(x):
                    sc = ax.scatter(
                        x, y,
                        c=p, cmap=cmap, vmin=vmin, vmax=vmax,
                        s=20,
                        marker=marker_map[k],
                        #edgecolors="black",
                        linewidths=0.1,
                    )
            ax.grid(True, alpha=0.25)
            ax.margins(x=0.0, y=0.0)  # extra safety: no autoscale padding
            return sc

        sc1 = scatter(axes[0], panels["abs"], *vlims["abs"])
        axes[0].set_xlabel(xlabel_abs)
        axes[0].set_ylabel(ylabel_abs)

        sc2 = scatter(axes[1], panels["per100"], *vlims["per100"])
        axes[1].set_xlabel(xlabel_per100)
        axes[1].set_ylabel(ylabel_per100)

        sc3 = scatter(axes[2], panels["perhh"], *vlims["perhh"])
        axes[2].set_xlabel(xlabel_perhh)
        axes[2].set_ylabel(ylabel_perhh)

        if debug_print:
            print("---- AXIS LIMITS AFTER SNAPPING (using true data min/max) ----")

        _apply_nice_axis_using_data(axes[0], panel_ranges["abs"]["x"], panel_ranges["abs"]["y"], ntarget=5)
        _apply_nice_axis_using_data(axes[1], panel_ranges["per100"]["x"], panel_ranges["per100"]["y"], ntarget=5)
        _apply_nice_axis_using_data(axes[2], panel_ranges["perhh"]["x"], panel_ranges["perhh"]["y"], ntarget=5)

        # -----------------------------
        # LEGEND (black markers)
        # -----------------------------
        legend_handles = [
            Line2D(
                [0], [0],
                marker=marker_map[k],
                linestyle="None",
                markerfacecolor="none",
                markeredgecolor="black",
                color="black",
                markersize=6,
                label=k,
            )
            for k in ueu_keys
        ]
        legend_labels = [h.get_label() for h in legend_handles]

        fig.legend(
            handles=legend_handles,
            labels=legend_labels,
            frameon=False,
            loc="upper center",
            ncol=min(legend_ncol, len(legend_handles)),
        )

        fig.tight_layout(rect=[0, 0, 1, 0.90])

        # -----------------------------
        # COLORBARS
        # -----------------------------
        for ax, sc, label in zip(
            axes,
            [sc1, sc2, sc3],
            [cbar_label_abs, cbar_label_per100, cbar_label_perhh],
        ):
            if sc is not None:
                cbar = fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.92)
                cbar.set_label(label)
                if False:
                    _apply_nice_cbar(cbar, ntarget=5)

        fig.savefig(filename, dpi=dpi, bbox_inches="tight")
        if show:
            plt.show()
        else:
            plt.close(fig)


    plot_compare_abs_per100_perhh_pareto_fronts_peak(
         ueu_results=ueu_results,
         filename=os.path.join(out_dir, "COMPARE_abs_vs_per100_vs_perhh_pareto_fronts_peak_colored.pdf"),
         figsize=(width_inch * 2.2, height_inch),  # wider for 3 panels
         font_size=font_size,
         legend_ncol=3,
         show=False,
 )
    plot_compare_per100_perhh_pareto_fronts_peak(
        ueu_results=ueu_results,
        filename=os.path.join(out_dir, "COMPARE_per100_vs_perhh_pareto_fronts_peak_colored.pdf"),
        figsize=(width_inch * 1.6, height_inch),  # z.B. etwas breiter als 1 Panel
        font_size=font_size,
        legend_ncol=3,
        show=False,
    )
