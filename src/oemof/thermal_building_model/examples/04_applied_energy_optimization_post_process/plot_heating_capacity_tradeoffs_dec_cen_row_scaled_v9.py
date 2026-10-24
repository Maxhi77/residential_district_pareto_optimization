#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Heating-technology capacity mixes along the SAME sampled Pareto trade-offs.

Standalone reduced version of b_plot_pareto_front_dec.py.
It preserves the source script's input resolvers, grid-cost overrides, capacity
aggregation, normalisation per 100 m², Pareto filtering, matching and
seven-solution selection/harmonisation. Only the plotting task is changed.

Modes: decentralized, centralized, or both.
Centralized paths: checks each strategy explicitly; auto-discovers full UEU sets.
Use --check-centralized-inputs to diagnose missing files without running plots.
Version 9 searches explicit strategy files across the original archive and local
postprocessing roots, and reports legacy temperature-level files separately.
Each PDF is exactly 11.8 cm wide, consistent with the supplied script.

IMPORTANT: The original source labels the three technology 'capacity' outputs
in kW. It does not independently establish whether CHP is thermal or electric
rated capacity. DO NOT describe sums as kW_th until verified. Set --chp-basis
thermal only when the actual input is thermal kW. If electrical, set
--chp-basis electrical --chp-thermal-factor <validated factor>.
Similarly verify that HP capacity means output heating capacity in kW_th.

Sample use (run this file inside the same analysis source folder):
    python plot_heating_capacity_tradeoffs_dec_cen.py --mode both
or override directories:
    python plot_heating_capacity_tradeoffs_dec_cen.py --mode dec \
        --optimization-root PATH --decentralized-root PATH --output-dir PATH

CSV files provide unscaled-by-axis values and technology shares for audit.
"""
from __future__ import annotations
import argparse
import copy
import csv
import math
import os
import pickle
import re
from pathlib import Path
from posixpath import normpath
from typing import Any, Dict, Iterable, List, Tuple, Optional
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
from matplotlib.ticker import MaxNLocator

PDF_EXPORT_WIDTH_CM = 11.8
PDF_EXPORT_WIDTH_INCH = PDF_EXPORT_WIDTH_CM / 2.54
HEAT_GRID_PLANNING_FILENAMES = (
    "fictional_heat_grid_costs_DENI03403000SEC4580_reference_reference.xlsx",
    "fictional_heat_grid_costs_DENI03403000SEC5101_reference_reference.xlsx",
    "fictional_heat_grid_costs_DENI03403000SEC5658_reference_reference.xlsx",
)
XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
UEU_NAME_MAP = {
    "DENI03403000SEC4580": "Low heat density",
    "DENI03403000SEC5658": "Medium heat density",
    "DENI03403000SEC5101": "High heat density",
}
UEU_SHORT_ORDER = list(UEU_NAME_MAP)
ENERGY_TYPES = ["Electricity", "Bio gas", "Natural gas", "Hydrogen"]
TECHNOLOGIES = [
    "PV-System", "Heat storage", "Battery", "Gas heater", "CHP",
    "Heat pump", "Retrofit", "Heat grid", "Seasonal storage",
]
TRADEOFF_KEYS = ("cost-co2", "peak-co2", "cost-peak")
TRADEOFF_LABELS = {
    "cost-co2": "Ann. TOTEX – Ann. GWP",
    "peak-co2": "Peak – Ann. GWP",
    "cost-peak": "Peak – Ann. TOTEX",
}
TRADEOFF_ENDPOINTS = {
    "cost-co2": ("TOTEX opt.", "GWP opt."),
    "peak-co2": ("Peak opt.", "GWP opt."),
    "cost-peak": ("Peak opt.", "TOTEX opt."),
}
# Original's rows are sorted from GWP to TOTEX in cost-co2 and from
# TOTEX to peak in cost-peak. The original figure reverses both.
REVERSE_TRADEOFF = {"cost-co2": True, "peak-co2": False, "cost-peak": True}
# Positions 3/4/5 in the supplied script's colorblind technology palette.
TECH_COLORS = {"Gas heater": "#D55E00", "CHP": "#CC78BC", "ASHP": "#CA9161"}


def _to_float(x):
    if isinstance(x, (np.generic,)):
        return float(x)
    return x

def _savefig_fixed_pdf_width(fig, filename, *args, **kwargs):
    file_suffix = Path(filename).suffix.lower() if filename is not None else ""
    fmt = str(kwargs.get("format", "")).lower()
    if file_suffix == ".pdf" or fmt == "pdf":
        height = fig.get_size_inches()[1]
        fig.set_size_inches(PDF_EXPORT_WIDTH_INCH, height, forward=False)
        kwargs.pop("bbox_inches", None)
        kwargs["format"] = "pdf"
    fig.savefig(filename, *args, **kwargs)

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

def get_pareto_front(data):
    pareto_front = []
    last_cost = float('inf')  # Initialisieren mit sehr hohem Wert
    for item in data:
        co2_val = item[0]
        cost_val = item[1]
        if cost_val < last_cost:  # Wenn der Kostenwert besser ist, füge den Punkt zur Pareto-Front hinzu
            pareto_front.append(tuple(item))
            last_cost = cost_val  # Aktuellen Kostenwert merken
    return pareto_front

def get_pareto_front_for_axes(combined_front, x_key, y_key):
    data_2d = []
    for rec in combined_front:
        xv = rec.get(x_key)
        yv = rec.get(y_key)
        if xv is None or yv is None:
            continue
        xv = float(xv)
        yv = float(yv)
        if not (np.isfinite(xv) and np.isfinite(yv)):
            continue
        data_2d.append((xv, yv))
    if not data_2d:
        return []
    data_2d = sorted(data_2d)
    return get_pareto_front(data_2d)

def find_exact_match_in_combined_front_by_keys(
    reduced_points, combined_front, x_key, y_key, tol=1e-8
):
    unique_points = []
    for pt in reduced_points:
        x_r, y_r = pt
        if not any(
            np.isclose(x_r, u[0], atol=tol) and np.isclose(y_r, u[1], atol=tol)
            for u in unique_points
        ):
            unique_points.append((x_r, y_r))

    matches = []
    for x_r, y_r in unique_points:
        best_match = None
        best_score = None
        for point in combined_front:
            x_c = point.get(x_key)
            y_c = point.get(y_key)
            if x_c is None or y_c is None:
                continue
            x_c = float(x_c)
            y_c = float(y_c)
            if np.isclose(x_r, x_c, atol=tol) and np.isclose(y_r, y_c, atol=tol):
                score = (
                    float(point.get("co2", np.inf)),
                    float(point.get("peak", np.inf)),
                    float(point.get("totex", np.inf)),
                )
                if best_score is None or score < best_score:
                    best_score = score
                    best_match = point
        if best_match is not None:
            matches.append(best_match)

    return matches

def select_evenly_spaced_front_indices(front_points, num_points=8):
    """
    Selects `num_points` indices that are evenly distributed along a front.
    Distribution uses cumulative distance in normalised 2D space for robust spacing.
    """
    n_points = len(front_points)
    if n_points == 0:
        return []
    if n_points <= num_points:
        return list(range(n_points))

    arr = np.asarray(front_points, dtype=float)
    x = arr[:, 0]
    y = arr[:, 1]

    def _normalise(v):
        v = np.asarray(v, dtype=float)
        v_min = np.nanmin(v)
        v_max = np.nanmax(v)
        span = v_max - v_min
        if span <= 0:
            return np.zeros_like(v)
        return (v - v_min) / span

    x_n = _normalise(x)
    y_n = _normalise(y)

    seg_lengths = np.sqrt(np.diff(x_n) ** 2 + np.diff(y_n) ** 2)
    cum_dist = np.concatenate(([0.0], np.cumsum(seg_lengths)))
    total_dist = float(cum_dist[-1])

    if total_dist <= 0:
        raw_idx = np.linspace(0, n_points - 1, num_points)
        return sorted(set(int(round(v)) for v in raw_idx))

    targets = np.linspace(0.0, total_dist, num_points)
    selected = []
    for t in targets:
        i = int(np.searchsorted(cum_dist, t, side="left"))
        i = int(np.clip(i, 0, n_points - 1))
        cands = [i]
        if i > 0:
            cands.append(i - 1)
        best = min(cands, key=lambda j: abs(cum_dist[j] - t))
        selected.append(int(best))

    unique_selected = []
    for idx in selected:
        if idx not in unique_selected:
            unique_selected.append(idx)

    if 0 not in unique_selected:
        unique_selected.insert(0, 0)
    if (n_points - 1) not in unique_selected:
        unique_selected.append(n_points - 1)

    unique_selected = sorted(set(unique_selected))
    desired = min(num_points, n_points)

    if len(unique_selected) < desired:
        remaining = [i for i in range(n_points) if i not in unique_selected]
        while len(unique_selected) < desired and remaining:
            best_new = max(
                remaining,
                key=lambda j: min(abs(cum_dist[j] - cum_dist[s]) for s in unique_selected),
            )
            unique_selected.append(best_new)
            remaining.remove(best_new)
        unique_selected = sorted(unique_selected)

    if len(unique_selected) > desired:
        if desired == 1:
            unique_selected = [0]
        elif desired == 2:
            unique_selected = [0, n_points - 1]
        else:
            core = unique_selected[1:-1]
            if core:
                core_pick = np.linspace(0, len(core) - 1, desired - 2)
                core_pick = [core[int(round(i))] for i in core_pick]
            else:
                core_pick = []
            unique_selected = [0] + core_pick + [n_points - 1]
            unique_selected = sorted(set(unique_selected))

    return unique_selected[:desired]

def _select_evenly_spaced_indices_1d(n_points, num_select):
    if n_points <= 0 or num_select <= 0:
        return []
    if num_select >= n_points:
        return list(range(n_points))

    raw = np.linspace(0, n_points - 1, num_select)
    idx = [int(round(v)) for v in raw]
    uniq = []
    for i in idx:
        if i not in uniq:
            uniq.append(i)
    if len(uniq) < num_select:
        for i in range(n_points):
            if i not in uniq:
                uniq.append(i)
            if len(uniq) >= num_select:
                break
    return sorted(uniq[:num_select])

def _downsample_rows_evenly(rows, target_n):
    if target_n <= 0:
        return []
    if len(rows) <= target_n:
        return list(rows)
    idx = _select_evenly_spaced_indices_1d(len(rows), target_n)
    return [rows[i] for i in idx]

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
    technologies = [
        'pv_system',
        'heat_storage',
        'battery',
        'gas_heater',
        'chp',
        'hp',
        'building',
        'heat_grid_investment',
        'seasonal_water_tank',
    ]

    technology_name_map = {
        'pv_system': 'PV-System',
        'heat_storage': 'Heat storage',
        'battery': 'Battery',
        'gas_heater': 'Gas heater',
        'chp': 'CHP',
        'hp': 'Heat pump',
        'building': 'Retrofit',
        'heat_grid_investment': 'Heat grid',
        'main_line': 'Main line',
        'house_service_line': 'House connection',
        'house_station': 'Building substation',
        'central_transfer_station': 'Central transfer station',
        'pump_station': 'Pump station',
        'seasonal_water_tank': 'Seasonal storage',
    }

    # NEW: energy naming map
    energy_type_name_map = {
        "Electricity": "Electricity",
        "BioGas": "Bio gas",
        "NaturalGas": "Natural gas",
        "Hydrogen": "Hydrogen",
    }

    retrofit_capacity_by_strategy = {
        "no_refurbishment": 0.0,
        "usual_refurbishment": 0.33,
        "geg_standard": 0.66,
        "advanced_refurbishment": 1.0,
    }

    def _retrofit_capacity_from_strategy(strategy):
        if strategy is None:
            return 0.0
        strategy_key = str(strategy).strip().lower()
        return float(retrofit_capacity_by_strategy.get(strategy_key, 0.0))

    def _is_centralized_building_block(name, value):
        if name in {"Electricity", "BioGas", "NaturalGas", "Hydrogen", "heat_grid"}:
            return False
        if not isinstance(name, str) or not isinstance(value, dict):
            return False
        if "buildings_in_cluster" in value or "buildings_in_cluster_used" in value:
            return True
        return any(str(component_key).startswith(f"building_{name}") for component_key in value)

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
                    if technology == "building":
                        total_capacity = _retrofit_capacity_from_strategy(
                            building_wrapper.get("strategy")
                        )

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
                        if technology not in ("building", "heat_grid_investment"):
                            total_capacity += float(tech_data.get("capacity", 0.0))  / hg_cluster

                    readable = technology_name_map.get(technology, technology)
                    district_data[district_key]["heat_grid"][readable] = {
                        "cost": total_cost,
                        "co2": total_co2,
                        "capacity": total_capacity
                    }

            # (3) buildings: technologies per building
            for building_name, building_data in selection.items():
                if not _is_centralized_building_block(building_name, building_data):
                    continue

                district_data[district_key][building_name] = {}

                if set_reference_to_one_building:
                    buildings_in_cluster = building_data.get("buildings_in_cluster", 1)
                else:
                    buildings_in_cluster = 1
                    buildings_in_cluster_scale_technology = building_data.get("buildings_in_cluster", 1)

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
                    if technology == "building":
                        total_capacity = _retrofit_capacity_from_strategy(
                            building_data.get("strategy")
                        )

                    readable = technology_name_map.get(technology, technology)
                    district_data[district_key][building_name][readable] = {
                        "cost": total_cost,
                        "co2": total_co2,
                        "capacity": total_capacity
                    }

        else:
            raise ValueError("cen_or_dec must be 'cen' or 'dec'")

    return district_data

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
    thermal_storage_names=None,
    # Heat storage is given as V [m³], convert to energy [kWh]
    hs_delta_T_K=30.0,               # temperature gap
    hs_density_kg_per_m3=1000.0,     # water
    hs_c_Wh_per_kgK=1.163,           # specific heat
    # After conversion to kWh, optionally scale to MWh etc.
    # Where to store the converted energy capacity
    hs_target_key="energy_capacity_kWh",  # or keep "capacity" if you prefer
    no_scale_capacity_names=("Retrofit",),
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

    no_scale_capacity_names = set(no_scale_capacity_names or ())
    if thermal_storage_names is None:
        thermal_storage_names = {heat_storage_name, "Seasonal storage"}
    else:
        thermal_storage_names = set(thermal_storage_names)

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

                    if tech_or_carrier in no_scale_capacity_names:
                        # Keep relative capacities (e.g. retrofit depth in [0, 1]) unchanged.
                        vals['capacity'] = cap_val
                    elif tech_or_carrier in thermal_storage_names:
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
                    if tech == "Retrofit":
                        # Retrofit capacity is a relative depth [0..1] and not meaningful in stackplot capacity sums.
                        district_sums[district_id]['technologies'][tech]['capacity'] += 0.0
                    else:
                        district_sums[district_id]['technologies'][tech]['capacity'] += building_data.get(tech, {}).get('capacity', 0)
                # Summiere für Energieträger (cost und co2)
                for energy in energy_types:
                    district_sums[district_id]['energy_types'][energy]['cost'] += building_data.get(energy, {}).get('cost', 0)
                    district_sums[district_id]['energy_types'][energy]['co2'] += building_data.get(energy, {}).get('co2', 0)
        if "electricity_grid" in district:
            if "Added trafo capacity" in technologies:
                district_sums[district_id]['technologies']["Added trafo capacity"] = {}
                district_sums[district_id]['technologies']["Added trafo capacity"]['capacity'] = district["electricity_grid"]["added_trafo_capacity"]
                district_sums[district_id]['technologies']["Added trafo capacity"]['cost'] = district["electricity_grid"]["added_trafo_cost"]
                district_sums[district_id]['technologies']["Added trafo capacity"]['co2'] = district["electricity_grid"]["added_trafo_co2"]

            if "Added line length" in technologies:
                district_sums[district_id]['technologies']["Added line length"] = {}
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
        for optional_col in (
            "tabula_year_class",
            "heat_load_1",
            "heat_load_2",
            "heat_load_3",
        ):
            if optional_col in df.columns:
                rep_info[bid][optional_col] = row.get(optional_col)

    return rep_info

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

def _is_front_like_list(obj):
    if not isinstance(obj, list):
        return False
    if len(obj) == 0:
        return True
    first = obj[0]
    if not isinstance(first, dict):
        return False
    return {"co2", "totex", "peak"}.issubset(set(first.keys()))

def _extract_combined_front_from_loaded_object(loaded_obj):
    """
    Accepts different pickle layouts and returns a front list[dict].
    Supports:
      - direct front list
      - tuple/list containing a front list
      - dict with key 'combined_front' or 'centralized_front'
    """
    if _is_front_like_list(loaded_obj):
        return loaded_obj

    if isinstance(loaded_obj, (list, tuple)):
        if len(loaded_obj) > 2 and _is_front_like_list(loaded_obj[2]):
            return loaded_obj[2]
        for item in loaded_obj:
            if _is_front_like_list(item):
                return item

    if isinstance(loaded_obj, dict):
        if _is_front_like_list(loaded_obj.get("centralized_front")):
            return loaded_obj["centralized_front"]
        if _is_front_like_list(loaded_obj.get("combined_front")):
            return loaded_obj["combined_front"]
        for item in loaded_obj.values():
            if _is_front_like_list(item):
                return item

    raise ValueError(
        "Could not extract front list from pickle payload. "
        f"Top-level type: {type(loaded_obj)}"
    )

def resolve_combined_front_path(
    *,
    ueu_short,
    input_dir,
    result_name,
    combined_front_input_override=None,
):
    """
    Resolve combined/centralized front input path.

    combined_front_input_override can be:
      - file path to a pickle
      - directory containing centralized_front.pkl, combined_front.pkl, or a package pickle
      - template containing {ueu_short}
    """
    if combined_front_input_override:
        override = os.path.expandvars(os.path.expanduser(combined_front_input_override))
        try:
            override = override.format(ueu_short=ueu_short)
        except Exception:
            pass
        override_fs = _to_windows_long_path(override)

        if os.path.isdir(override_fs):
            for candidate_name in (
                "centralized_front.pkl",
                "centralized_package.pkl",
                "combined_front.pkl",
                "combined_package.pkl",
                "building_dict.pkl",
            ):
                candidate = os.path.join(override_fs, candidate_name)
                if os.path.exists(_to_windows_long_path(candidate)):
                    return _to_windows_long_path(candidate)
            raise FileNotFoundError(
                f"Override directory exists but no supported pickle found: {override}"
            )

        return _to_windows_long_path(override)

    default_candidates = [
        os.path.join(input_dir, f"{result_name}.pkl"),
        os.path.join(input_dir, f"{result_name}{ueu_short}.pkl"),
    ]
    for default_path in default_candidates:
        if os.path.exists(_to_windows_long_path(default_path)):
            return _to_windows_long_path(default_path)
    return _to_windows_long_path(default_candidates[-1])

def load_combined_front_from_path(pkl_path):
    pkl_path_fs = _to_windows_long_path(pkl_path)
    with open(pkl_path_fs, "rb") as f:
        loaded_obj = pickle.load(f)
    return _extract_combined_front_from_loaded_object(loaded_obj)

def _post_process_date_key(folder_name):
    prefix = "post_processed_dec_k_combinations_"
    if not str(folder_name).startswith(prefix):
        return None
    date_part = str(folder_name)[len(prefix):]
    try:
        year, month, day = [int(part) for part in date_part.split("_")]
    except ValueError:
        return None
    return year, month, day

def _latest_decentralized_reference_front_dir(hypervolume_results_root, ueu_short):
    ueu_root = Path(hypervolume_results_root) / f"processed_bds_in_{ueu_short}"
    if not ueu_root.exists():
        raise FileNotFoundError(f"UEU hypervolume folder not found: {ueu_root}")

    candidates = [
        path
        for path in ueu_root.iterdir()
        if path.is_dir() and _post_process_date_key(path.name) is not None
    ]
    if not candidates:
        raise FileNotFoundError(f"No post-process folders found below: {ueu_root}")

    latest_post_process = max(candidates, key=lambda path: _post_process_date_key(path.name))
    return str(latest_post_process / "sfh_reference_mfh_reference")

def _resolve_centralized_front_path(
    *,
    resolved_path,
    examples_root,
    ueu,
    combined_cluster,
    case_temperature_level,
):
    resolved_path = Path(str(resolved_path))
    resolved_path_long = _to_windows_long_path(resolved_path)
    strict_m_archive_only = str(ueu).endswith("DENI03403000SEC5658")
    if os.path.exists(resolved_path_long):
        if resolved_path.is_dir():
            candidate = resolved_path / "centralized_front.pkl"
            candidate_long = _to_windows_long_path(candidate)
            if os.path.exists(candidate_long):
                return candidate_long
            if not strict_m_archive_only:
                temp_level = str(case_temperature_level).split("_", 1)[0]
                local_roots = [
                    path
                    for path in Path(examples_root).glob("04_post_processed_cen_*")
                    if path.is_dir()
                ]
                for root in sorted(local_roots, reverse=True):
                    local_candidate = (
                        root
                        / str(ueu)
                        / str(combined_cluster)
                        / temp_level
                        / "centralized_front.pkl"
                    )
                    local_candidate_long = _to_windows_long_path(local_candidate)
                    if os.path.exists(local_candidate_long):
                        return local_candidate_long
            raise FileNotFoundError(
                "Centralized front directory exists, but centralized_front.pkl is missing. "
                f"No matching local fallback was found: {candidate}"
            )
        return resolved_path_long

    if not strict_m_archive_only:
        temp_level = str(case_temperature_level).split("_", 1)[0]
        if resolved_path.name in {"cmin", "cmax"}:
            parent_temperature_front = resolved_path.parent / "centralized_front.pkl"
            parent_temperature_front_long = _to_windows_long_path(parent_temperature_front)
            if os.path.exists(parent_temperature_front_long):
                return parent_temperature_front_long

        local_roots = [
            path
            for path in Path(examples_root).glob("04_post_processed_cen_*")
            if path.is_dir()
        ]
        for root in sorted(local_roots, reverse=True):
            local_candidate = (
                root
                / str(ueu)
                / str(combined_cluster)
                / temp_level
                / "centralized_front.pkl"
            )
            local_candidate_long = _to_windows_long_path(local_candidate)
            if os.path.exists(local_candidate_long):
                return local_candidate_long

    raise FileNotFoundError(
        "Centralized front path does not exist. "
        "No local 04_post_processed_cen fallback is allowed for SEC5658; "
        "for other UEUs no matching local fallback was found. "
        "Check that the M: archive path is mounted. "
        f"Missing path: {resolved_path}"
    )

def _to_windows_long_path(path_str):
    """
    Convert path to extended-length Windows path (\\\\?\\...) when needed.
    Helps with MAX_PATH issues on long file names.
    """
    if not isinstance(path_str, str):
        path_str = str(path_str)

    abs_path = os.path.abspath(path_str)
    if os.name != "nt":
        return abs_path

    if abs_path.startswith("\\\\?\\"):
        return abs_path

    # UNC path: \\server\share -> \\?\UNC\server\share
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path.lstrip("\\")

    # normal drive path
    if len(abs_path) >= 248:
        return "\\\\?\\" + abs_path
    return abs_path

def _resolve_ueu_gpkg_path(optimization_root, ueu):
    ueu_root = Path(optimization_root) / str(ueu)
    candidates = [
        ueu_root / f"{ueu}.gpkg",
        ueu_root / f"{Path(str(ueu)).name}.gpkg",
    ]
    for candidate in candidates:
        candidate_long = _to_windows_long_path(candidate)
        if os.path.exists(candidate_long):
            return candidate_long
    raise FileNotFoundError(
        "UEU GPKG not found. Tried:\n"
        + "\n".join(str(candidate) for candidate in candidates)
    )

def _xlsx_column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in str(cell_ref) if ch.isalpha())
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter.upper()) - ord("A") + 1
    return index - 1

def _workbook_target_to_zip_path(target: str) -> str:
    target = str(target).lstrip("/")
    if target.startswith("xl/"):
        return target
    return normpath("xl/" + target)

def _xlsx_cell_value(cell: ET.Element, shared_strings: List[str]) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//main:t", XLSX_NS))

    value = cell.find("main:v", XLSX_NS)
    raw = "" if value is None else value.text or ""
    if cell.attrib.get("t") == "s" and raw:
        return shared_strings[int(raw)]
    return raw

def _read_xlsx_sheet_without_openpyxl(path: Path, sheet_name: str) -> pd.DataFrame:
    with ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("main:si", XLSX_NS):
                shared_strings.append(
                    "".join(text.text or "" for text in item.findall(".//main:t", XLSX_NS))
                )

        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_targets = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships_root.findall("rel:Relationship", XLSX_NS)
        }

        sheet_target = None
        available_sheet_names = []
        for sheet in workbook_root.findall(".//main:sheet", XLSX_NS):
            available_sheet_names.append(sheet.attrib.get("name", ""))
            if sheet.attrib.get("name") == sheet_name:
                relationship_id = sheet.attrib[
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                ]
                sheet_target = relationship_targets[relationship_id]

        if sheet_target is None:
            raise ValueError(
                f"Input Excel has no '{sheet_name}' sheet. "
                f"Available sheets: {available_sheet_names}"
            )

        sheet_root = ET.fromstring(
            archive.read(_workbook_target_to_zip_path(sheet_target))
        )

    rows = []
    for row in sheet_root.findall(".//main:sheetData/main:row", XLSX_NS):
        values = {}
        max_column = -1
        for cell in row.findall("main:c", XLSX_NS):
            column = _xlsx_column_index(cell.attrib["r"])
            max_column = max(max_column, column)
            values[column] = _xlsx_cell_value(cell, shared_strings)
        rows.append([values.get(column, "") for column in range(max_column + 1)])

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows[1:], columns=rows[0])

def _ueu_short_from_case_name(value: str) -> str:
    match = re.search(r"SEC(\d+)", str(value))
    return f"DENI03403000SEC{match.group(1)}" if match else str(value)

def _load_heat_grid_planning_overrides(base_dir: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    overrides = {}
    for filename in HEAT_GRID_PLANNING_FILENAMES:
        path = Path(base_dir) / filename
        if not path.exists():
            print(f"WARNING: Heat-grid planning override file missing: {path}")
            continue

        summary = _read_xlsx_sheet_without_openpyxl(path, "summary")
        required = {
            "ueu_case",
            "temperature_level",
            "refurbishment_scenario",
            "total_capex_eur_annualized",
            "total_gwp_kg_co2_eq_annualized",
        }
        missing = sorted(required - set(summary.columns))
        if missing:
            raise ValueError(f"Missing heat-grid planning columns in {path}: {missing}")

        for _, row in summary.iterrows():
            ueu_short = _ueu_short_from_case_name(row["ueu_case"])
            case_key = f"{row['temperature_level']}_{row['refurbishment_scenario']}"
            key = (ueu_short, case_key)
            overrides[key] = {
                "ueu_short": ueu_short,
                "case_key": case_key,
                "temperature_level": str(row["temperature_level"]),
                "refurbishment_scenario": str(row["refurbishment_scenario"]),
                "cost": float(row["total_capex_eur_annualized"]),
                "gwp": float(row["total_gwp_kg_co2_eq_annualized"]),
                "source": str(path),
            }
    return overrides

def _heat_grid_investment_keys(heat_grid_data: Dict[str, Any]) -> List[str]:
    return [
        key
        for key, value in heat_grid_data.items()
        if isinstance(key, str)
        and key.startswith("heat_grid_investment")
        and isinstance(value, dict)
    ]

def _sum_heat_grid_investment_values(
    heat_grid_data: Dict[str, Any],
) -> Tuple[float, float]:
    old_cost = 0.0
    old_gwp = 0.0
    for key in _heat_grid_investment_keys(heat_grid_data):
        tech_data = heat_grid_data[key]
        old_cost += float(tech_data.get("investment_cost", 0.0) or 0.0)
        old_gwp += float(tech_data.get("investment_co2", 0.0) or 0.0)
    return old_cost, old_gwp

def _apply_heat_grid_planning_override_to_front(
    combined_front: List[Dict[str, Any]],
    *,
    ueu_short: str,
    case_temperature_level: Optional[str],
    overrides: Dict[Tuple[str, str], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not case_temperature_level:
        return combined_front

    override = overrides.get((ueu_short, str(case_temperature_level)))
    if override is None:
        print(
            "WARNING: No heat-grid planning override for "
            f"{ueu_short} / {case_temperature_level}; using loaded front values."
        )
        return combined_front

    updated_records = 0
    old_cost_values = []
    old_gwp_values = []
    new_cost = float(override["cost"])
    new_gwp = float(override["gwp"])

    for record in combined_front:
        selection = record.setdefault("selection", {})
        heat_grid_data = selection.setdefault("heat_grid", {})
        if not isinstance(heat_grid_data, dict):
            continue

        old_cost, old_gwp = _sum_heat_grid_investment_values(heat_grid_data)
        old_cost_values.append(old_cost)
        old_gwp_values.append(old_gwp)

        investment_keys = _heat_grid_investment_keys(heat_grid_data)
        if not investment_keys:
            investment_keys = ["heat_grid_investment_heat_grid_planning_override"]
            heat_grid_data[investment_keys[0]] = {}

        primary = heat_grid_data[investment_keys[0]]
        primary["investment_cost"] = new_cost
        primary["investment_co2"] = new_gwp
        primary.setdefault("capacity", 0.0)

        for extra_key in investment_keys[1:]:
            heat_grid_data[extra_key]["investment_cost"] = 0.0
            heat_grid_data[extra_key]["investment_co2"] = 0.0

        if "totex" in record:
            record["totex"] = float(record["totex"]) + (new_cost - old_cost)
        if "co2" in record:
            record["co2"] = float(record["co2"]) + (new_gwp - old_gwp)
        updated_records += 1

    old_cost_unique = sorted({round(value, 6) for value in old_cost_values})
    old_gwp_unique = sorted({round(value, 6) for value in old_gwp_values})
    print(
        "Heat-grid planning override applied: "
        f"{ueu_short} / {case_temperature_level}, records={updated_records}, "
        f"old_cost_unique={old_cost_unique[:5]}, new_cost={new_cost:.2f}, "
        f"old_gwp_unique={old_gwp_unique[:5]}, new_gwp={new_gwp:.2f}"
    )
    return combined_front

def _first_existing_path(candidates, fallback=None):
    for candidate in candidates:
        if candidate is None:
            continue
        candidate_path = Path(os.path.expandvars(os.path.expanduser(str(candidate))))
        if candidate_path.exists():
            return candidate_path
    return Path(fallback) if fallback is not None else None

def _default_optimization_root():
    env_value = os.environ.get("OPTIMIZATION_RESULTS_ROOT")
    examples_root = Path(__file__).resolve().parent.parent
    candidates = [
        env_value,
        Path("/jump/mh"),
        Path.home() / "thermal_building_clone" / "src" / "oemof" / "thermal_building_model" / "examples" / "03_applied_energy_optimization",
        examples_root / "03_applied_energy_optimization",
    ]
    fallback = examples_root / "03_applied_energy_optimization"
    return _first_existing_path(candidates, fallback=fallback)

def _default_centralized_post_processed_root():
    env_value = os.environ.get("CENTRALIZED_POST_PROCESSED_ROOT")
    examples_root = Path(__file__).resolve().parent.parent
    candidates = [
        env_value,
        Path("/jump/mh/centralized_post_processed"),
        Path.home() / "centralized_post_processed",
        Path(r"M:\04_ArchivMA\Hillen Maximilian\Veröffentlichungen\UEU\centralized_post_processed"),
        Path(__file__).resolve().parent / "centralized" / "centralized_post_processed",
    ]
    fallback = Path("/jump/mh/centralized_post_processed") if os.name != "nt" else candidates[3]
    return _first_existing_path(candidates, fallback=fallback)

def _default_decentralized_hypervolume_root():
    env_value = os.environ.get("DECENTRALIZED_HYPERVOLUME_ROOT")
    examples_root = Path(__file__).resolve().parent.parent
    candidates = [
        env_value,
        examples_root / "05_applied_energy_pareto_set_analysis" / "decentralized" / "hypervolume_results",
        Path.home() / "thermal_building_clone" / "src" / "oemof" / "thermal_building_model" / "examples"
        / "05_applied_energy_pareto_set_analysis" / "decentralized" / "hypervolume_results",
    ]
    fallback = examples_root / "05_applied_energy_pareto_set_analysis" / "decentralized" / "hypervolume_results"
    return _first_existing_path(candidates, fallback=fallback)

def _default_plot_output_root():
    env_value = os.environ.get("PARETO_PLOT_OUTPUT_ROOT")
    if env_value:
        return Path(env_value).expanduser()
    if os.name != "nt":
        jump_root = Path("/jump/mh")
        if jump_root.exists():
            return jump_root / "pareto_plot_outputs"
        return Path.home() / "pareto_plot_outputs"
    return Path(r"C:\Users\hill_mx\Desktop\123")



def _extract_parallel_axes_rows_from_matches(
    matches, building_in_cluster, cen_or_dec, total_floor_area_all,
    energy_types, technologies, building_name_map, rep_info=None,
):
    """Same source processing/aggregating as the original, only three axes retained."""
    if not matches:
        return []
    matches = list(matches)
    processed = process_district_data(matches, building_in_cluster, cen_or_dec)
    processed = process_units_for_processed(
        processed, floor_area=total_floor_area_all / 100.0,
        no_scale_capacity_names=("Retrofit",),
    )
    district_sums = calculate_sums_for_technologies_and_energy_for_a_district(
        processed, energy_types, technologies, building_name_map,
    )
    result = []
    for district_id, district in district_sums.items():
        tech = district.get("technologies", {})
        result.append({
            "totex": float(district.get("totex", np.nan)),
            "gwp": float(district.get("co2", np.nan)),
            "peak": float(district.get("peak", np.nan)),
            "heat_pump_capacity": float(tech.get("Heat pump", {}).get("capacity", 0.0)),
            "gas_heater_capacity": float(tech.get("Gas heater", {}).get("capacity", 0.0)),
            "chp_capacity": float(tech.get("CHP", {}).get("capacity", 0.0)),
        })
    return result


def collect_parallel_tradeoff_rows(
    combined_front, building_in_cluster, cen_or_dec, total_floor_area_all,
    energy_types, technologies, building_name_map, rep_info=None,
    num_points_per_front=7, return_debug=False,
):
    """Exact source algorithm: 2D Pareto -> rematch -> arc-length sampling."""
    front_specs = [
        ("cost-co2", "co2", "totex"),
        ("cost-peak", "totex", "peak"),
        ("peak-co2", "peak", "co2"),
    ]
    rows_by_tradeoff, debug_counts = {}, {}
    for tradeoff_name, x_key, y_key in front_specs:
        front_points = get_pareto_front_for_axes(combined_front, x_key=x_key, y_key=y_key)
        matches = find_exact_match_in_combined_front_by_keys(
            front_points, combined_front, x_key=x_key, y_key=y_key,
        ) if front_points else []
        full_rows = _extract_parallel_axes_rows_from_matches(
            matches, building_in_cluster, cen_or_dec, total_floor_area_all,
            energy_types, technologies, building_name_map, rep_info=rep_info,
        ) if matches else []
        idx_sel = select_evenly_spaced_front_indices(
            front_points=front_points, num_points=num_points_per_front,
        ) if front_points else []
        selected_rows = []
        for order, idx in enumerate(idx_sel):
            if idx >= len(full_rows):
                continue
            row = dict(full_rows[idx])
            row["point_order"] = int(order)
            selected_rows.append(row)
        rows_by_tradeoff[tradeoff_name] = selected_rows
        debug_counts[tradeoff_name] = {
            "front_points": len(front_points), "matches": len(matches),
            "full_rows": len(full_rows), "selected_idx": len(idx_sel),
            "selected_rows": len(selected_rows),
        }
    if return_debug:
        return rows_by_tradeoff, 1.0, debug_counts
    return rows_by_tradeoff, 1.0


def build_harmonized_parallel_tradeoff_rows(
    combined_front, building_in_cluster, cen_or_dec, total_floor_area_all,
    energy_types, technologies, building_name_map, n_points, rep_info=None,
    tradeoff_keys=("cost-co2", "cost-peak", "peak-co2"),
):
    """Copied selection scheme: probe 7..17, harmonize and downsample."""
    best_pack = None
    best_min_selected = -1
    found_uniform_target = False
    for probe_n in range(n_points, n_points + 11):
        probe_rows, anchor, debug = collect_parallel_tradeoff_rows(
            combined_front=combined_front,
            building_in_cluster=building_in_cluster,
            cen_or_dec=cen_or_dec,
            total_floor_area_all=total_floor_area_all,
            energy_types=energy_types,
            technologies=technologies,
            building_name_map=building_name_map,
            rep_info=rep_info,
            num_points_per_front=probe_n,
            return_debug=True,
        )
        counts = [int(debug.get(k, {}).get("selected_rows", 0)) for k in tradeoff_keys]
        min_sel = min(counts) if counts else 0
        if min_sel > best_min_selected:
            best_min_selected = min_sel
            best_pack = (probe_n, probe_rows, anchor, debug)
        if min_sel >= n_points:
            found_uniform_target = True
            best_pack = (probe_n, probe_rows, anchor, debug)
            break
    if best_pack is None:
        return None
    used_n, rows_by_tradeoff, anchor, debug_counts = best_pack
    counts = [int(debug_counts.get(k, {}).get("selected_rows", 0)) for k in tradeoff_keys]
    common_n = min(counts) if counts else 0
    return {
        "rows_by_tradeoff": {
            k: _downsample_rows_evenly(rows_by_tradeoff.get(k, []), common_n)
            for k in tradeoff_keys
        },
        "common_n": int(common_n),
        "debug_counts": debug_counts,
        "used_probe_n": int(used_n),
        "found_uniform_target": bool(found_uniform_target),
    }


def load_reference_rep_info(optimization_root: Path, ueu: str, reference_path: Path):
    """Preserves GPKG route for reference/reference and PKLs for clustered runs."""
    if "sfh_reference" in str(reference_path).lower() and "mfh_reference" in str(reference_path).lower():
        try:
            import geopandas as gpd
        except ImportError as exc:
            raise ImportError("geopandas is required for reference/reference GPKG files") from exc
        frame = gpd.read_file(_resolve_ueu_gpkg_path(optimization_root, ueu))
        frame = frame.loc[frame["tabula_building_type"].isin(["SFH", "MFH"])].copy()
        import ast
        def household_count(x):
            if isinstance(x, (list, tuple, np.ndarray)):
                return len(x)
            if isinstance(x, str):
                s = x.strip()
                assert s.startswith("[") and s.endswith("]"), f"Invalid household-list text: {x}"
                inner = s[1:-1].strip()
                return 0 if not inner else inner.count(",") + 1
            raise TypeError(f"Invalid list_number_of_adults type: {type(x)}")
        frame["number_of_households"] = frame["list_number_of_adults"].apply(household_count)
        return {
            row["building_id"]: {
                "name": row["building_id"],
                "net_floor_area": float(row["net_floor_area"]),
                "buildings_in_cluster": 1,
                "total_floor_area": float(row["net_floor_area"]),
                "number_of_households": int(row["number_of_households"]),
                "number_of_residents": int(row["number_of_residents"])
                    if not pd.isna(row["number_of_residents"]) else 0,
            }
            for _, row in frame.iterrows()
        }
    ueu_dir = optimization_root / ueu
    sfh = load_rep_info(str(ueu_dir / "sfh_cluster.pkl"), "SFH", numeric=False)
    mfh = load_rep_info(str(ueu_dir / "mfh_cluster.pkl"), "MFH", numeric=False)
    return {**sfh, **mfh}


def _resolve_decentralized_source(ueu_short, root, examples_root):
    # The medium-UEU pin is the one in the supplied source script.
    if ueu_short == "DENI03403000SEC5658":
        pin = (examples_root / "03_applied_energy_optimization"
               / f"processed_bds_in_{ueu_short}"
               / "post_processed_dec_k_combinations_2026_04_30"
               / "sfh_reference_mfh_reference")
        if pin.exists():
            return pin
        print(f"WARNING: Original medium-UEU pin not found: {pin}; using newest available front")
    return Path(_latest_decentralized_reference_front_dir(root, ueu_short))



# A centralized UEU contributes exactly three strategy-specific Pareto datasets.
# Only explicitly strategy-named paths are automatically accepted.  In
# particular, a generic t80/centralized_front.pkl is NOT silently interpreted
# as both t80/cmin and t80/cmax.
CENTRALIZED_CASES = (("t50", "cmin"), ("t80", "cmax"), ("t80", "cmin"))
CENTRALIZED_CLUSTER = "combined_cluster_sfh_reference_mfh_reference"


def _centralized_candidate_roots(args, examples_root):
    """Return exact source roots (original archive/local folders included)."""
    if args.centralized_root is not None:
        explicit = Path(os.path.expandvars(os.path.expanduser(str(args.centralized_root))))
        return [explicit]

    roots = []
    env_root = os.environ.get("CENTRALIZED_POST_PROCESSED_ROOT")
    if env_root:
        roots.append(Path(os.path.expandvars(os.path.expanduser(env_root))))
    roots.extend([
        Path(r"M:\04_ArchivMA\Hillen Maximilian\Veröffentlichungen\UEU\centralized_post_processed"),
        Path(__file__).resolve().parent / "centralized" / "centralized_post_processed",
        Path("/jump/mh/centralized_post_processed"),
        Path.home() / "centralized_post_processed",
    ])
    if examples_root.is_dir():
        roots.extend(sorted(
            (x for x in examples_root.glob("04_post_processed_cen_*") if x.is_dir()),
            reverse=True,
        ))
    result = []
    seen = set()
    for root in roots:
        key = os.path.normcase(os.path.abspath(str(root)))
        if key not in seen:
            seen.add(key)
            result.append(root)
    return result


def _candidate_strategy_files(root, ueu_short, temp, retrofit):
    """Recognise only files explicitly stored under a named retrofit strategy."""
    ueu = f"processed_bds_in_{ueu_short}"
    cluster_root = Path(root) / ueu / CENTRALIZED_CLUSTER
    return [
        cluster_root / temp / retrofit / "centralized_front.pkl",
        cluster_root / f"{temp}_{retrofit}" / "centralized_front.pkl",
    ]


def _legacy_temperature_file(root, ueu_short, temp):
    return (Path(root) / f"processed_bds_in_{ueu_short}"
            / CENTRALIZED_CLUSTER / temp / "centralized_front.pkl")


def _get_valid_file(paths):
    for path in paths:
        if os.path.isfile(_to_windows_long_path(path)):
            return _to_windows_long_path(path)
    return None


def resolve_all_centralized_fronts(args, examples_root):
    """Check all explicit strategy files and report original-script fallbacks.

    The original script also falls back to a shared temperature-level file,
    but without metadata this does not identify the 80 C retrofit strategy.
    Such files are shown in diagnostics, not silently assigned.
    """
    roots = _centralized_candidate_roots(args, examples_root)
    resolved = {}
    problems = []
    print("\nCentralized input discovery (version 9)")
    print("Each of the three heat-grid/retrofit strategies must be identified distinctly.")
    print("Root candidates (in priority order):")
    for root in roots:
        print(f"  {'FOUND' if root.is_dir() else 'MISSING'}: {root}")

    for ueu_short in UEU_SHORT_ORDER:
        print(f"\nUEU {ueu_short}:")
        per_root = []
        for root in roots:
            if not root.is_dir():
                continue
            found = {}
            legacy = {}
            for temp, retrofit in CENTRALIZED_CASES:
                key = f"{temp}_{retrofit}"
                candidate = _get_valid_file(_candidate_strategy_files(root, ueu_short, temp, retrofit))
                if candidate:
                    found[key] = candidate
                else:
                    generic = _legacy_temperature_file(root, ueu_short, temp)
                    if os.path.isfile(_to_windows_long_path(generic)):
                        legacy[key] = _to_windows_long_path(generic)
            per_root.append((root, found, legacy))

        # Prefer a complete, internally consistent campaign/root.
        full_roots = [(root, found) for root, found, _ in per_root if len(found) == len(CENTRALIZED_CASES)]
        if full_roots:
            root, found = full_roots[0]
            resolved[ueu_short] = found
            print(f"  OK: all cases found below {root}")
            for key, path in found.items():
                print(f"     {key}: {path}")
            continue

        # Explicit strategy files may exist across roots but mixing campaigns
        # changes the optimization data. Never mix them without user consent.
        best_root, best_exact, _ = max(per_root, key=lambda x: len(x[1]), default=(None, {}, {}))
        all_explicit = {}
        for root, found, _ in per_root:
            for key, path in found.items():
                all_explicit.setdefault(key, (root, path))
        needed = [f"{temp}_{retrofit}" for temp, retrofit in CENTRALIZED_CASES]
        if getattr(args, "allow_mixed_centralized_roots", False) and all(k in all_explicit for k in needed):
            resolved[ueu_short] = {k: all_explicit[k][1] for k in needed}
            print("  WARNING: combining cases from DIFFERENT roots, explicitly requested:")
            for k in needed:
                print(f"     {k}: {all_explicit[k][1]}")
            continue

        missing = [k for k in needed if k not in best_exact]
        print(f"  INCOMPLETE: best directory = {best_root}")
        for key in needed:
            path = best_exact.get(key)
            if path:
                print(f"     OK      {key}: {path}")
            else:
                print(f"     MISSING {key}")
        legacy_seen = set()
        for root, _, legacy in per_root:
            for path in legacy.values():
                if path not in legacy_seen:
                    legacy_seen.add(path)
                    print(f"     LEGACY temperature-only file: {path}")
        if legacy_seen:
            print("     These legacy files are accepted by the original script as")
            print("     fallbacks, but they do NOT uniquely identify cmin versus cmax.")
        if all(k in all_explicit for k in needed):
            print("     All strategies exist across roots; use --allow-mixed-centralized-roots")
            print("     only if you have verified that the optimization campaigns are compatible.")
        else:
            remaining = [k for k in needed if k not in all_explicit]
            print(f"     Missing explicit strategies across all roots: {', '.join(remaining)}")
        problems.append(ueu_short)

    if problems:
        raise FileNotFoundError(
            "Could not identify the three centralized strategy-specific fronts for: "
            + ", ".join(problems) + "\n"
            "See the diagnostics above. The original source may have used a "
            "t80/centralized_front.pkl fallback or skipped missing cases. "
            "Those behaviours do not prove that all three retrofit strategies "
            "are represented. If you locate the correct directory, pass "
            "--centralized-root FULL_PATH."
        )
    return resolved

def collect_ueu_rows(mode, args):
    examples_root = Path(__file__).resolve().parent.parent
    optimization_root = Path(args.optimization_root or _default_optimization_root())
    dec_root = Path(args.decentralized_root or _default_decentralized_hypervolume_root())
    centralized_paths = resolve_all_centralized_fronts(args, examples_root) if mode == "cen" else {}
    override_dir = Path(args.heat_grid_planning_dir or
                        (Path(__file__).resolve().parent / "centralized" / "heat_grid_planning"))
    overrides = _load_heat_grid_planning_overrides(override_dir) if mode == "cen" else {}
    if mode == "cen" and not overrides:
        print("WARNING: No heat-grid planning overrides found. Original central Pareto objectives may differ.")
    result = {}
    for ueu_short in UEU_SHORT_ORDER:
        ueu = f"processed_bds_in_{ueu_short}"
        if mode == "dec":
            source = _resolve_decentralized_source(ueu_short, dec_root, examples_root)
            front_path = resolve_combined_front_path(
                ueu_short=ueu_short, input_dir="", result_name="combined_front",
                combined_front_input_override=str(source),
            )
            rep = load_reference_rep_info(optimization_root, ueu, Path(front_path))
            front = maniupulate_combined_front_elect_grid(
                load_combined_front_from_path(front_path), True,
            )
        else:
            entries = []
            used_paths = set()
            path_for_rep = None
            for temp, retrofit in CENTRALIZED_CASES:
                case = f"{temp}_{retrofit}"
                front_path = centralized_paths[ueu_short][case]
                front_key = str(Path(front_path).resolve()).lower()
                if front_key in used_paths:
                    print(f"NOTE: {ueu_short} {case}: source file repeats an earlier strategy path; "
                          "preserving original source deduplication")
                    continue
                used_paths.add(front_key)
                path_for_rep = Path(front_path)
                records = maniupulate_combined_front_elect_grid(
                    load_combined_front_from_path(front_path), True,
                )
                records = _apply_heat_grid_planning_override_to_front(
                    records, ueu_short=ueu_short,
                    case_temperature_level=case, overrides=overrides,
                )
                flag = {"t50_cmin": 1.0, "t80_cmax": 0.5, "t80_cmin": 0.0}[case]
                for rec in records:
                    marked = dict(rec)
                    marked["heat_grid_retrofit_temp_case"] = flag
                    entries.append(marked)
            if not entries:
                raise ValueError(f"No centralized fronts found for {ueu}")
            front = entries
            rep = load_reference_rep_info(optimization_root, ueu, path_for_rep)
        total_floor_area = sum(float(info["total_floor_area"]) for info in rep.values())
        if not np.isfinite(total_floor_area) or total_floor_area <= 0:
            raise ValueError(f"Invalid floor area for {ueu}: {total_floor_area}")
        building_name_map = {bid: info["name"] for bid, info in rep.items()}
        if mode == "cen":
            building_name_map["heat_grid"] = "Heat grid"
        tech = [t for t in TECHNOLOGIES if mode == "cen" or t not in {"Heat grid", "Seasonal storage"}]
        pack = build_harmonized_parallel_tradeoff_rows(
            combined_front=front,
            building_in_cluster=list(rep.keys()),
            cen_or_dec=mode, total_floor_area_all=total_floor_area,
            energy_types=ENERGY_TYPES, technologies=tech,
            building_name_map=building_name_map, n_points=args.points,
            rep_info=rep,
        )
        if not pack or pack["common_n"] == 0:
            raise ValueError(f"No selected Pareto rows for {mode}/{ueu_short}")
        if pack["common_n"] != args.points:
            print(f"WARNING: {mode}/{ueu_short} only {pack['common_n']} points "
                  f"(requested {args.points})")
        print(f"{mode} {ueu_short}: floor area={total_floor_area:.1f} m²; "
              f"selected={pack['common_n']} per trade-off; probe={pack['used_probe_n']}")
        result[UEU_NAME_MAP[ueu_short]] = pack["rows_by_tradeoff"]
    return result


def make_capacity_data(rows_by_ueu, args):
    data = {}
    for label, by_tradeoff in rows_by_ueu.items():
        data[label] = {}
        for tradeoff, rows in by_tradeoff.items():
            ordered = list(reversed(rows)) if REVERSE_TRADEOFF[tradeoff] else list(rows)
            converted = []
            for order, row in enumerate(ordered, start=1):
                gas = float(row["gas_heater_capacity"])
                chp = float(row["chp_capacity"])
                hp = float(row["heat_pump_capacity"])
                values = (gas, chp, hp)
                if not all(np.isfinite(v) and v >= -1e-10 for v in values):
                    raise ValueError(f"Invalid installed capacity at {label}/{tradeoff}/{order}: {values}")
                if args.chp_basis == "electrical":
                    chp *= args.chp_thermal_factor
                gas, chp, hp = (max(0., v) for v in (gas, chp, hp))
                total = gas + chp + hp
                converted.append({
                    "index": order, "gas": gas, "chp": chp, "ashp": hp,
                    "total": total, "gas_pct": 100*gas/total if total else np.nan,
                    "chp_pct": 100*chp/total if total else np.nan,
                    "ashp_pct": 100*hp/total if total else np.nan,
                    "totex": row["totex"], "gwp": row["gwp"], "peak": row["peak"],
                })
            data[label][tradeoff] = converted
    return data


def write_audit_csv(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["UEU", "tradeoff", "point_start_to_end", "gas_kW_per100m2",
                         "chp_kW_per100m2", "ashp_kW_per100m2", "total_kW_per100m2",
                         "gas_share_pct", "chp_share_pct", "ashp_share_pct",
                         "annual_TOTEX_per100m2", "annual_GWP_per100m2", "peak_per100m2"])
        for label in UEU_NAME_MAP.values():
            for tradeoff in TRADEOFF_KEYS:
                for row in data[label][tradeoff]:
                    writer.writerow([label, tradeoff, row["index"], row["gas"], row["chp"],
                                     row["ashp"], row["total"], row["gas_pct"], row["chp_pct"],
                                     row["ashp_pct"], row["totex"], row["gwp"], row["peak"]])


def plot_heat_supply_mix(data, filename, args, height_pct=100):
    """Plot stacked installed-capacity mixes with row-wise y-axis scaling."""
    set_journal_style(font_family="TeX Gyre Termes", font_size=8)

    # Reduced baseline height (20% smaller than the previous version), then scaled.
    previous_height_cm = 6.5 * 1.34 * (1.90 * 0.85) * 3.0 * 0.30
    reduced_base_height_cm = previous_height_cm * 0.80
    height_cm = reduced_base_height_cm * (float(height_pct) / 100.0)
    height_inch = height_cm / 2.54

    fig, axes = plt.subplots(
        3,
        3,
        figsize=(PDF_EXPORT_WIDTH_INCH, height_inch),
        sharex=False,
        sharey=False,
        facecolor="white",
    )

    labels = ["Low\nheat\ndensity", "Medium\nheat\ndensity", "High\nheat\ndensity"]
    data_labels = list(UEU_NAME_MAP.values())
    row_maxima = {}
    for label in data_labels:
        row_max = max(
            row["total"]
            for tradeoff in TRADEOFF_KEYS
            for row in data[label][tradeoff]
        )
        row_maxima[label] = max(1.0, row_max * 1.10)

    # Muted scientific palette, intentionally avoiding the previous orange emphasis.
    plot_colors = {
        "Gas heater": "#4C78A8",   # muted blue
        "CHP": "#7A5195",          # muted violet
        "ASHP": "#54A24B",         # muted green
    }

    endpoint_map = {
        "TOTEX opt.": "Ann. TOTEX\noptimal",
        "GWP opt.": "Ann. GWP\noptimal",
        "Peak opt.": "Peak grid ex.\npower optimal",
    }

    top_title_map = {
        "cost-co2": "Ann. TOTEX - Ann. GWP",
        "peak-co2": "Peak grid ex. power - Ann. GWP",
        "cost-peak": "Peak grid ex. power - Ann. TOTEX",
    }

    for i, (display_label, data_label) in enumerate(zip(labels, data_labels)):
        row_ylim = row_maxima[data_label]
        for j, tradeoff in enumerate(TRADEOFF_KEYS):
            ax = axes[i, j]
            rows = data[data_label][tradeoff]
            x = np.arange(1, len(rows) + 1)
            base = np.zeros(len(rows))

            for key, name in (("gas", "Gas heater"), ("chp", "CHP"), ("ashp", "ASHP")):
                vals = np.array([r[key] for r in rows], dtype=float)
                ax.bar(
                    x,
                    vals,
                    bottom=base,
                    width=0.68,
                    color=plot_colors[name],
                    edgecolor="none",
                    alpha=0.95,
                    label=name,
                    zorder=3,
                )
                base += vals

            ax.set_xlim(0.45, max(len(rows), 1) + 0.55)
            ax.set_ylim(0, row_ylim)
            ax.grid(axis="y", alpha=0.22, linewidth=0.55, zorder=0)
            ax.tick_params(axis="both", labelsize=7, length=2.0, pad=1.4)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))

            if i == 0:
                ax.set_title(top_title_map[tradeoff], fontsize=6.0, pad=3.0)

            ax.set_xticks(x)
            if i == 2:
                ax.set_xticklabels([str(k) for k in x])
            else:
                ax.set_xticklabels([])

            if j != 0:
                ax.tick_params(axis="y", labelleft=False)

            # Only the bottom row receives descriptive x-axis endpoint labels.
            if i == 2:
                endpoints_y = -0.36
                left_label, right_label = TRADEOFF_ENDPOINTS[tradeoff]
                left_label = endpoint_map.get(left_label, left_label)
                right_label = endpoint_map.get(right_label, right_label)
                ax.text(
                    1,
                    endpoints_y,
                    left_label,
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="top",
                    fontsize=6.0,
                )
                ax.text(
                    len(rows),
                    endpoints_y,
                    right_label,
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="top",
                    fontsize=6.0,
                )

    # Final panel positions must be established before placing row labels.
    # This keeps each label centered on its actual subplot row at any height.
    fig.subplots_adjust(
        left=0.172,
        right=0.950,
        bottom=0.235,
        top=0.812,
        wspace=0.36,
        hspace=0.34,
    )

    # Shared y-axis title positioned close to the leftmost y-axis ticks.
    fig.text(
        0.120,
        0.52,
        "Installed heat supply capacity in kW per 100 m$^2$",
        rotation=90,
        ha="center",
        va="center",
        fontsize=6.0,
    )

    # Place each rotated UEU label at the measured vertical center of its
    # subplot row (not at hand-chosen coordinates).
    for row_idx, row_label in enumerate(labels):
        position = axes[row_idx, 0].get_position()
        y_pos = 0.5 * (position.y0 + position.y1)
        fig.text(
            0.060,
            y_pos,
            row_label,
            rotation=90,
            ha="center",
            va="center",
            multialignment="center",
            fontsize=7.0,
            fontweight="bold",
        )

    from matplotlib.patches import Patch
    handles = [
        Patch(facecolor=plot_colors[k], edgecolor="none", label=k)
        for k in ("Gas heater", "CHP", "ASHP")
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.56, 0.995),
        ncol=3,
        frameon=False,
        fontsize=7.0,
        columnspacing=1.15,
        handlelength=1.1,
        handletextpad=0.35,
    )

    fig.text(
        0.56,
        0.882,
        "Pareto-front progression along selected points",
        ha="center",
        va="center",
        fontsize=7.0,
    )

    _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=600)
    plt.close(fig)
    print(f"Saved {filename} ({PDF_EXPORT_WIDTH_CM} cm wide, h{int(height_pct)}).")

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=("dec", "cen", "both"), default="both")
    p.add_argument("--points", type=int, default=7)
    p.add_argument("--optimization-root", type=Path)
    p.add_argument("--decentralized-root", type=Path)
    p.add_argument("--centralized-root", type=Path,
                   help="Root containing processed_bds_in_* directories and all three strategy cases")
    p.add_argument("--allow-mixed-centralized-roots", action="store_true",
                   help="Allow explicit strategy files from different source roots; verify campaign compatibility first")
    p.add_argument("--check-centralized-inputs", action="store_true",
                   help="Check all nine centralized input files and exit without generating figures")
    p.add_argument("--heat-grid-planning-dir", type=Path)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--chp-basis", choices=("as-recorded", "thermal", "electrical"),
                   default="as-recorded", help="Verify source CHP capacity basis before claiming kW_th")
    p.add_argument("--heights", type=int, nargs="+", default=[50, 60, 70, 80, 90, 100],
                   help="Figure height variants to export, relative to the reduced baseline height.")
    p.add_argument("--chp-thermal-factor", type=float,
                   help="kW thermal / kW electrical; REQUIRED if --chp-basis electrical")
    args = p.parse_args()
    if args.chp_basis == "electrical" and (args.chp_thermal_factor is None or args.chp_thermal_factor <= 0):
        p.error("--chp-basis electrical requires a verified positive --chp-thermal-factor")
    if args.chp_basis == "as-recorded":
        print("WARNING: Source does not prove CHP 'capacity' is thermal. "
              "Stacked sums are as-recorded capacity measures, not confirmed kW_th.")
    if args.points < 2:
        p.error("--points must be >= 2")
    if args.check_centralized_inputs:
        resolve_all_centralized_fronts(args, Path(__file__).resolve().parent.parent)
        print("All nine centralized datasets were found. You can run --mode cen now.")
        return
    out = args.output_dir or _default_plot_output_root()
    Path(out).mkdir(parents=True, exist_ok=True)
    modes = ("dec", "cen") if args.mode == "both" else (args.mode,)
    for mode in modes:
        print("="*80, f"\nProcessing {mode}\n", "="*80)
        rows = collect_ueu_rows(mode, args)
        capacity = make_capacity_data(rows, args)
        csv_stem = f"{mode}_COMPARE_heating_generation_capacity_mix_per_100m2_p{args.points}"
        write_audit_csv(capacity, Path(out) / (csv_stem + ".csv"))
        print("Audit data:", Path(out) / (csv_stem + ".csv"))
        for h in args.heights:
            if h <= 0:
                raise ValueError(f"Invalid height specifier: {h}")
            stem = f"{mode}_COMPARE_heating_generation_capacity_mix_per_100m2_p{args.points}_h{int(h)}"
            plot_heat_supply_mix(capacity, Path(out) / (stem + ".pdf"), args, height_pct=h)


if __name__ == "__main__":
    main()
