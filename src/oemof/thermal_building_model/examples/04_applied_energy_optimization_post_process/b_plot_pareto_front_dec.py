
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
from matplotlib import colors as mcolors

import copy
import csv
import numpy as np
import pickle
import os
import pandas as pd
from matplotlib.ticker import FuncFormatter, MaxNLocator
from posixpath import normpath
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import re
def _to_float(x):
    if isinstance(x, (np.generic,)):
        return float(x)
    return x
import numpy as np
import matplotlib.pyplot as plt

try:
    import seaborn as sns
except ModuleNotFoundError:
    class _SeabornFallback:
        _COLORBLIND = [
            "#0173B2",
            "#DE8F05",
            "#029E73",
            "#D55E00",
            "#CC78BC",
            "#CA9161",
            "#FBAFE4",
            "#949494",
            "#ECE133",
            "#56B4E9",
        ]

        @classmethod
        def color_palette(cls, palette=None, n_colors=None):
            colors = cls._COLORBLIND if palette == "colorblind" else list(plt.rcParams["axes.prop_cycle"].by_key()["color"])
            if n_colors is None:
                return colors
            return [colors[i % len(colors)] for i in range(n_colors)]

    sns = _SeabornFallback()


PDF_EXPORT_WIDTH_CM = 11.8
PDF_EXPORT_WIDTH_INCH = PDF_EXPORT_WIDTH_CM / 2.54
# PDF export contract: every saved PDF page from this plot script must be 11.8 cm wide.
# Do not pass bbox_inches="tight" for PDF output; it changes the final PDF bounding box.


def _savefig_fixed_pdf_width(fig, filename, *args, **kwargs):
    file_suffix = Path(filename).suffix.lower() if filename is not None else ""
    fmt = str(kwargs.get("format", "")).lower()
    if file_suffix == ".pdf" or fmt == "pdf":
        height = fig.get_size_inches()[1]
        fig.set_size_inches(PDF_EXPORT_WIDTH_INCH, height, forward=False)
        kwargs.pop("bbox_inches", None)
        kwargs["format"] = "pdf"
    fig.savefig(filename, *args, **kwargs)


def _linebreak_after_in_label(label: str) -> str:
    if not isinstance(label, str):
        return label
    if " in\n" in label:
        return label
    return label.replace(" in ", " in\n", 1)


def _format_plain_tick(value, _pos):
    if np.isclose(value, 0.0):
        return "0"
    return f"{value:g}"


def _set_capacity_symlog_axis(ax, max_value, linthresh=10.0):
    ax.set_yscale("symlog", linthresh=linthresh, linscale=1.0, base=10)
    ax.set_ylim(bottom=0.0)

    if not np.isfinite(max_value) or max_value <= 0:
        ax.yaxis.set_major_formatter(FuncFormatter(_format_plain_tick))
        return

    top = max(float(max_value) * 1.05, linthresh)
    next_decade = linthresh
    while next_decade < max_value:
        next_decade *= 10.0
    if next_decade <= top * 1.15:
        top = next_decade

    ticks = [0.0, linthresh]
    tick = linthresh * 10.0
    while tick <= top * 1.001:
        ticks.append(tick)
        tick *= 10.0

    ax.set_ylim(0.0, top)
    ax.set_yticks(ticks)
    ax.yaxis.set_major_formatter(FuncFormatter(_format_plain_tick))


def _apply_integer_colorbar_ticks(cbar, nbins: int = 6):
    cbar.locator = MaxNLocator(nbins=nbins, integer=True)
    cbar.update_ticks()


HEAT_GRID_PLANNING_FILENAMES = (
    "fictional_heat_grid_costs_DENI03403000SEC4580_reference_reference.xlsx",
    "fictional_heat_grid_costs_DENI03403000SEC5101_reference_reference.xlsx",
    "fictional_heat_grid_costs_DENI03403000SEC5658_reference_reference.xlsx",
)

XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


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


def _print_heat_grid_planning_overrides(overrides: Dict[Tuple[str, str], Dict[str, Any]]) -> None:
    print("\n" + "=" * 96)
    print("HEAT GRID PLANNING OVERRIDES FROM fictional_heat_grid_costs_*_reference_reference.xlsx")
    print("These values replace heat_grid_investment cost/GWP and adjust record totex/co2 before plotting.")
    print("-" * 96)
    print(f"{'UEU':<18} {'case':<10} {'cost EUR/a':>16} {'GWP kg CO2-eq/a':>20}  source")
    print("-" * 96)
    for key in sorted(overrides):
        row = overrides[key]
        print(
            f"{row['ueu_short']:<18} {row['case_key']:<10} "
            f"{row['cost']:>16,.2f} {row['gwp']:>20,.2f}  "
            f"{Path(row['source']).name}"
        )
    print("=" * 96 + "\n")


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
    xlabel=r"Ann. CO$_2$-eq. in kg",
    ylabel=r"Totex in €",
    cbar_label=r"Peak grid ex. power in kW",
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
    ax.set_ylabel(_linebreak_after_in_label(ylabel))

    if grid:
        ax.grid(True, alpha=0.3, linewidth=0.6)

    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(_linebreak_after_in_label(cbar_label), fontsize=font_size)
    _apply_integer_colorbar_ticks(cbar)
    cbar.ax.tick_params(labelsize=font_size)

    ax.legend(frameon=False, loc="best")

    fig.tight_layout()

    # -----------------------------
    # SAVE
    # -----------------------------
    if filename is None and name is not None:
        filename = f"pareto_all_with_front_selected_{name}.pdf"

    if filename is not None:
        _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)

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

import numpy as np
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
    xlabel=r"Ann. CO$_2$-eq. in kg",
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
    ax.set_ylabel(_linebreak_after_in_label(ylabel))
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
        _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)

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
    # Use the first two coordinates; an optional third coordinate keeps peak for exact rematching.
    co2 = [pt[0] for pt in pareto_front]
    cost = [pt[1] for pt in pareto_front]

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
        selected_points.append(tuple(pareto_front[idx]))

    return selected_points

def select_evenly_spaced_pareto_points_focus_x_axis(pareto_front, num_points=10):
    # Use the first two coordinates; an optional third coordinate keeps peak for exact rematching.
    co2 = [pt[0] for pt in pareto_front]
    cost = [pt[1] for pt in pareto_front]

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
        selected_points.append(tuple(pareto_front[idx]))

    return selected_points


def find_exact_match_in_combined_front(reduced_points, combined_front, tol=1e-8):
    matched_points = []
    used_record_ids = set()

    for pt in reduced_points:
        if isinstance(pt, dict):
            co2_r = pt.get("co2")
            totex_r = pt.get("totex")
            peak_r = pt.get("peak")
        else:
            co2_r = pt[0]
            totex_r = pt[1]
            peak_r = pt[2] if len(pt) > 2 else None

        candidates = []
        for point in combined_front:
            if id(point) in used_record_ids:
                continue

            co2_c = point['co2']
            totex_c = point['totex']

            if np.isclose(co2_r, co2_c, atol=tol) and np.isclose(totex_r, totex_c, atol=tol):
                candidates.append(point)

        if peak_r is not None:
            candidates_with_peak = [
                point
                for point in candidates
                if np.isclose(peak_r, point.get("peak", np.nan), atol=tol)
            ]
            if candidates_with_peak:
                candidates = candidates_with_peak

        if candidates:
            match = candidates[0]
            matched_points.append(match)
            used_record_ids.add(id(match))

    return matched_points

def plot_all_pareto_points(
    combined_front,
    name=None,
    filename=None,
    figsize=(6, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    xlabel=r"Ann. CO$_2$-eq. in kg",
    ylabel=r"Totex in €",
    cbar_label=r"Peak grid ex. power in kW",
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
    ax.set_ylabel(_linebreak_after_in_label(ylabel))

    ax.grid(True, alpha=0.3, linewidth=0.6)

    # -----------------------------
    # COLORBAR
    # -----------------------------
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(_linebreak_after_in_label(cbar_label), fontsize=font_size)
    _apply_integer_colorbar_ticks(cbar)
    cbar.ax.tick_params(labelsize=font_size)

    fig.tight_layout()

    # -----------------------------
    # SAVE
    # -----------------------------
    if filename is None and name is not None:
        filename = f"pareto_all_points_{name}.pdf"

    if filename is not None:
        _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)

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
    plt.xlabel("CO₂-eq. in kg")
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


def _extract_parallel_axes_rows_from_matches(
    matches,
    building_in_cluster,
    cen_or_dec,
    total_floor_area_all,
    energy_types,
    technologies,
    building_name_map,
    rep_info=None,
):
    """
    Build per-solution axis values (all per 100 m² except retrofit_depth).
    """
    if not matches:
        return []

    matches = list(matches)
    processed = process_district_data(matches, building_in_cluster, cen_or_dec)
    processed = process_units_for_processed(
        processed,
        floor_area=total_floor_area_all / 100.0,
        no_scale_capacity_names=("Retrofit",),
    )

    retrofit_depth_by_district = {}
    for district_id, district in processed.items():
        per_building_depths = []
        for key, sub in district.items():
            if key in ("co2", "peak", "totex", "electricity_grid", "heat_grid"):
                continue
            if not isinstance(sub, dict):
                continue
            retrofit_cap = sub.get("Retrofit", {}).get("capacity", np.nan)
            try:
                retrofit_cap = float(retrofit_cap)
            except Exception:
                retrofit_cap = np.nan
            if np.isfinite(retrofit_cap):
                per_building_depths.append(np.clip(retrofit_cap, 0.0, 1.0))
        if per_building_depths:
            retrofit_depth_by_district[district_id] = float(np.mean(per_building_depths))
        else:
            retrofit_depth_by_district[district_id] = 0.0

    district_sums = calculate_sums_for_technologies_and_energy_for_a_district(
        processed,
        energy_types,
        technologies,
        building_name_map,
    )

    rows = []
    for district_id, district in district_sums.items():
        tech = district.get("technologies", {})
        source_record = matches[district_id - 1] if district_id - 1 < len(matches) else {}
        rows.append(
            {
                "totex": float(district.get("totex", np.nan)),
                "heat_grid_totex": float(tech.get("Heat grid", {}).get("cost", 0.0)),
                "heat_grid_retrofit_temp_case": float(
                    source_record.get("heat_grid_retrofit_temp_case", np.nan)
                ),
                "avg_flow_temperature": float(
                    _average_flow_temperature_for_record(source_record, rep_info)
                ),
                "gwp": float(district.get("co2", np.nan)),
                "peak": float(district.get("peak", np.nan)),
                "heat_pump_capacity": float(tech.get("Heat pump", {}).get("capacity", 0.0)),
                "gas_heater_capacity": float(tech.get("Gas heater", {}).get("capacity", 0.0)),
                "chp_capacity": float(tech.get("CHP", {}).get("capacity", 0.0)),
                "battery_capacity": float(tech.get("Battery", {}).get("capacity", 0.0)),
                "thermal_storage_capacity": float(tech.get("Heat storage", {}).get("capacity", 0.0)),
                "seasonal_storage_capacity": float(tech.get("Seasonal storage", {}).get("capacity", 0.0)),
                "retrofit_cost": float(tech.get("Retrofit", {}).get("cost", 0.0)),
                "retrofit_capacity_raw": float(tech.get("Retrofit", {}).get("capacity", 0.0)),
                "retrofit_depth_from_capacity": float(retrofit_depth_by_district.get(district_id, 0.0)),
                "pv_capacity": float(tech.get("PV-System", {}).get("capacity", 0.0)),
            }
        )
    return rows


def collect_parallel_tradeoff_rows(
    combined_front,
    building_in_cluster,
    cen_or_dec,
    total_floor_area_all,
    energy_types,
    technologies,
    building_name_map,
    rep_info=None,
    num_points_per_front=7,
    return_debug=False,
):
    """
    Returns selected rows for the three trade-offs:
      - cost-co2:  (co2, totex)
      - cost-peak: (totex, peak)
      - peak-co2:  (peak, co2)
    Retrofit depth is derived from building retrofit capacities (strategy-based),
    where 1.0 corresponds to full retrofit depth for the whole district
    (all buildings at depth 1).
    """
    front_specs = [
        ("cost-co2", "co2", "totex"),
        ("cost-peak", "totex", "peak"),
        ("peak-co2", "peak", "co2"),
    ]

    rows_by_tradeoff = {}
    debug_counts = {}
    retrofit_depth_reference = 1.0

    for tradeoff_name, x_key, y_key in front_specs:
        front_points = get_pareto_front_for_axes(combined_front, x_key=x_key, y_key=y_key)
        if not front_points:
            rows_by_tradeoff[tradeoff_name] = []
            debug_counts[tradeoff_name] = {
                "front_points": 0,
                "matches": 0,
                "full_rows": 0,
                "selected_idx": 0,
                "selected_rows": 0,
            }
            continue

        matches = find_exact_match_in_combined_front_by_keys(
            reduced_points=front_points,
            combined_front=combined_front,
            x_key=x_key,
            y_key=y_key,
        )
        if not matches:
            rows_by_tradeoff[tradeoff_name] = []
            debug_counts[tradeoff_name] = {
                "front_points": len(front_points),
                "matches": 0,
                "full_rows": 0,
                "selected_idx": 0,
                "selected_rows": 0,
            }
            continue

        full_rows = _extract_parallel_axes_rows_from_matches(
            matches=matches,
            building_in_cluster=building_in_cluster,
            cen_or_dec=cen_or_dec,
            total_floor_area_all=total_floor_area_all,
            energy_types=energy_types,
            technologies=technologies,
            building_name_map=building_name_map,
            rep_info=rep_info,
        )

        idx_sel = select_evenly_spaced_front_indices(
            front_points=front_points,
            num_points=num_points_per_front,
        )

        selected_rows = []
        for order, idx in enumerate(idx_sel):
            if idx >= len(full_rows):
                continue
            row = dict(full_rows[idx])
            row["point_order"] = int(order)
            selected_rows.append(row)

        rows_by_tradeoff[tradeoff_name] = selected_rows
        debug_counts[tradeoff_name] = {
            "front_points": len(front_points),
            "matches": len(matches),
            "full_rows": len(full_rows),
            "selected_idx": len(idx_sel),
            "selected_rows": len(selected_rows),
        }

    for tradeoff_name, rows in rows_by_tradeoff.items():
        for row in rows:
            row["retrofit_depth"] = float(
                np.clip(row.get("retrofit_depth_from_capacity", 0.0), 0.0, 1.0)
            )

    if return_debug:
        return rows_by_tradeoff, float(retrofit_depth_reference), debug_counts
    return rows_by_tradeoff, float(retrofit_depth_reference)


def build_harmonized_parallel_tradeoff_rows(
    combined_front,
    building_in_cluster,
    cen_or_dec,
    total_floor_area_all,
    energy_types,
    technologies,
    building_name_map,
    n_points,
    rep_info=None,
    tradeoff_keys=("cost-co2", "cost-peak", "peak-co2"),
):
    best_pack = None
    best_min_selected = -1
    probe_upper = n_points + 10
    found_uniform_target = False

    for probe_n in range(n_points, probe_upper + 1):
        probe_rows, probe_anchor, probe_debug = collect_parallel_tradeoff_rows(
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
        selected_counts = [
            int(probe_debug.get(k, {}).get("selected_rows", 0))
            for k in tradeoff_keys
        ]
        min_sel = min(selected_counts) if selected_counts else 0
        if min_sel > best_min_selected:
            best_min_selected = min_sel
            best_pack = (probe_n, probe_rows, probe_anchor, probe_debug)
        if min_sel >= n_points:
            found_uniform_target = True
            best_pack = (probe_n, probe_rows, probe_anchor, probe_debug)
            break

    if best_pack is None:
        return None

    used_probe_n, rows_by_tradeoff, retrofit_anchor, debug_counts = best_pack
    selected_counts = [
        int(debug_counts.get(k, {}).get("selected_rows", 0))
        for k in tradeoff_keys
    ]
    common_n = min(selected_counts) if selected_counts else 0
    if common_n <= 0:
        return {
            "rows_by_tradeoff": {k: [] for k in tradeoff_keys},
            "common_n": 0,
            "retrofit_anchor": float(retrofit_anchor),
            "debug_counts": debug_counts,
            "used_probe_n": int(used_probe_n),
            "found_uniform_target": bool(found_uniform_target),
        }

    rows_by_tradeoff = {
        k: _downsample_rows_evenly(rows_by_tradeoff.get(k, []), common_n)
        for k in tradeoff_keys
    }
    return {
        "rows_by_tradeoff": rows_by_tradeoff,
        "common_n": int(common_n),
        "retrofit_anchor": float(retrofit_anchor),
        "debug_counts": debug_counts,
        "used_probe_n": int(used_probe_n),
        "found_uniform_target": bool(found_uniform_target),
    }


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


def _blend_with_white(color, blend_factor):
    """
    blend_factor in [0,1]:
      0.0 -> original color
      1.0 -> white
    """
    rgb = np.array(mcolors.to_rgb(color), dtype=float)
    blend_factor = float(np.clip(blend_factor, 0.0, 1.0))
    out = rgb + (1.0 - rgb) * blend_factor
    return tuple(np.clip(out, 0.0, 1.0))


STACKPLOT_EXTRA_TECH_COLORS = {
    "Heat grid": "#005A32",
    "Seasonal storage": "#B2182B",
}


STACKPLOT_ENERGY_ORDER = ["Electricity", "Bio gas", "Natural gas", "Hydrogen"]


TECHNOLOGY_DISPLAY_LABELS = {
    "Heat pump": "ASHP",
    "house_service_line": "House connection",
    "house_station": "Building substation",
    "central_transfer_station": "Central transfer station",
    "pump_station": "Pump station",
    "main_line": "Main line",
    "House service": "House connection",
    "House station": "Building substation",
    "Central transfer": "Central transfer station",
    "Seasonal storage": "Seasonal Heat Storage",
}


def _technology_display_label(technology):
    return TECHNOLOGY_DISPLAY_LABELS.get(technology, technology)


def _ordered_stackplot_energy_types(energy_types):
    energy_set = set(energy_types)
    ordered = [energy for energy in STACKPLOT_ENERGY_ORDER if energy in energy_set]
    ordered.extend(energy for energy in energy_types if energy not in ordered)
    return ordered


def _stackplot_colors(technologies, energy_types):
    energy_types = _ordered_stackplot_energy_types(energy_types)
    extra_technologies = set(STACKPLOT_EXTRA_TECH_COLORS)
    base_technologies = [tech for tech in technologies if tech not in extra_technologies]
    base_palette = sns.color_palette(
        "colorblind",
        n_colors=max(len(base_technologies) + len(energy_types), 3),
    )

    tech_color_map = {
        tech: base_palette[idx]
        for idx, tech in enumerate(base_technologies)
    }
    for tech, color in STACKPLOT_EXTRA_TECH_COLORS.items():
        tech_color_map[tech] = color

    energy_offset = len(base_technologies)
    energy_color_map = {
        energy: base_palette[energy_offset + idx]
        for idx, energy in enumerate(energy_types)
    }

    technology_colors = [tech_color_map[tech] for tech in technologies]
    energy_colors = [energy_color_map[energy] for energy in energy_types]
    return technology_colors, energy_colors


def _format_axis_value(v):
    v = float(v)
    av = abs(v)
    if av >= 1000:
        return f"{v:.0f}"
    if av >= 100:
        return f"{v:.1f}"
    if av >= 10:
        return f"{v:.2f}"
    return f"{v:.3f}"


def _old_flow_temperature_from_tabula_year_class(tabula_year_class):
    try:
        tabula_gen = int(float(tabula_year_class))
    except (TypeError, ValueError):
        return np.nan

    old_temp = 70.0
    for min_gen, temp in ((5, 70.0), (9, 60.0), (10, 50.0), (11, 40.0)):
        if tabula_gen >= min_gen:
            old_temp = temp
    return old_temp


def _ceil_to_flow_temperature_level(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return np.nan
    if not np.isfinite(value):
        return np.nan
    for temp in (40.0, 50.0, 60.0, 70.0, 80.0):
        if temp >= value:
            return temp
    return value


def _flow_temperature_for_building_strategy(building_info, strategy):
    if not isinstance(building_info, dict):
        return np.nan

    strategy_key = str(strategy or "").strip().lower()
    if strategy_key == "geg_standard":
        strategy_key = "usual_refurbishment"

    old_temp = _old_flow_temperature_from_tabula_year_class(
        building_info.get("tabula_year_class")
    )
    if not np.isfinite(old_temp):
        return np.nan
    if strategy_key in ("", "no_refurbishment"):
        return old_temp

    heat_load_col = {
        "usual_refurbishment": "heat_load_2",
        "advanced_refurbishment": "heat_load_3",
    }.get(strategy_key)
    if heat_load_col is None:
        return np.nan

    try:
        old_load = float(building_info.get("heat_load_1", np.nan))
        new_load = float(building_info.get(heat_load_col, np.nan))
    except (TypeError, ValueError):
        return np.nan
    if not (np.isfinite(old_load) and np.isfinite(new_load)) or old_load <= 0:
        return np.nan

    inlet_new = 20.0 + new_load / (old_load / (old_temp - 20.0))
    return _ceil_to_flow_temperature_level(int(inlet_new))


def _average_flow_temperature_for_record(record, rep_info):
    if not isinstance(record, dict) or not isinstance(rep_info, dict):
        return np.nan
    selection = record.get("selection", {})
    if not isinstance(selection, dict):
        return np.nan

    weighted_sum = 0.0
    weight_sum = 0.0
    for building_id, selected in selection.items():
        info = rep_info.get(building_id)
        if info is None or not isinstance(selected, dict):
            continue
        strategy = (
            selected.get("strategy")
            or selected.get("refurbishment_status")
            or selected.get("refurbish")
        )
        temp = _flow_temperature_for_building_strategy(info, strategy)
        if not np.isfinite(temp):
            continue
        try:
            weight = float(info.get("buildings_in_cluster", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        if not np.isfinite(weight) or weight <= 0:
            weight = 1.0
        weighted_sum += float(temp) * weight
        weight_sum += weight

    if weight_sum <= 0:
        return np.nan
    return weighted_sum / weight_sum


def _parallel_coordinate_axis_specs(
    include_seasonal_storage=False,
    include_heat_grid_totex=False,
    include_heat_grid_retrofit_temp_case=False,
    include_flow_temperature=False,
):
    axis_specs = [
        ("totex", "Ann.\nTOTEX\nin EUR\nper\n100m$^2$"),
        ("gwp", "Ann.\nGWP\nin kg\nCO$_2$-eq.\nper\n100m$^2$"),
        ("peak", "Peak\ngrid ex.\npower\nin kW\nper\n100m$^2$"),
        ("heat_pump_capacity", "ASHP\nin kW\nper\n100m$^2$"),
        ("gas_heater_capacity", "Gas\nheater\nin kW\nper\n100m$^2$"),
        ("chp_capacity", "CHP\nin kW\nper\n100m$^2$"),
        ("battery_capacity", "Battery\nin kWh\nper\n100m$^2$"),
        ("thermal_storage_capacity", "Heat\nstorage\nin kWh\nper\n100m$^2$"),
        ("pv_capacity", "PV-\nSystem\nin kW\nper\n100m$^2$"),
        ("retrofit_depth", "Retrofit\ndepth\nin -"),
    ]
    if include_seasonal_storage:
        axis_specs.append(
            ("seasonal_storage_capacity", "Sea-\nsonal\nstorage\nin kWh\nper\n100m$^2$")
        )
    if include_heat_grid_totex:
        axis_specs.append(
            ("heat_grid_totex", "Heat grid\nTOTEX\nin EUR\nper\n100m$^2$")
        )
    if include_heat_grid_retrofit_temp_case:
        axis_specs.append(
            (
                "heat_grid_retrofit_temp_case",
                "Heat\ngrid\nsupply\nstra-\ntegy\nin -",
            )
        )
    if include_flow_temperature:
        axis_specs.append(
            ("avg_flow_temperature", "Avg.\nflow\ntem-\nperature\nin \N{DEGREE SIGN}C")
        )
    return axis_specs


def _heat_grid_retrofit_temp_case_value(strategy_label):
    label = str(strategy_label).lower()
    if label.startswith("50") and "min" in label:
        return 1.0
    if label.startswith("80") and "min" in label:
        return 0.0
    if label.startswith("80") and ("max" in label or "advanced" in label):
        return 0.5
    return np.nan


def _parallel_coordinate_delta_axis_specs():
    return [
        ("delta_totex", r"$\Delta$ Ann." + "\n" + "TOTEX\nEUR /\n100m$^2$"),
        ("delta_gwp", r"$\Delta$ Ann." + "\n" + "GWP\nkg CO$_2$-\neq. /\n100m$^2$"),
        ("delta_peak", r"$\Delta$ Peak" + "\n" + "grid ex.\nkW /\n100m$^2$"),
        ("delta_heat_pump_capacity", r"$\Delta$ ASHP" + "\n" + "kW /\n100m$^2$"),
        ("delta_gas_heater_capacity", r"$\Delta$ Gas" + "\n" + "heater\nkW /\n100m$^2$"),
        ("delta_chp_capacity", r"$\Delta$ CHP" + "\n" + "kW /\n100m$^2$"),
        ("delta_pv_capacity", r"$\Delta$ PV-" + "\n" + "System\nkW /\n100m$^2$"),
        ("delta_battery_capacity", r"$\Delta$ Battery" + "\n" + "kWh /\n100m$^2$"),
        ("delta_thermal_storage_capacity", r"$\Delta$ Heat" + "\n" + "storage\nkWh /\n100m$^2$"),
        ("delta_retrofit_depth", r"$\Delta$ Retro-" + "\n" + "fit\ndepth\nin -"),
    ]


def build_parallel_coordinate_delta_rows_by_ueu(
    *,
    centralized_rows_by_ueu,
    decentralized_rows_by_ueu,
    ueu_order,
):
    source_keys = {
        "delta_totex": "totex",
        "delta_gwp": "gwp",
        "delta_peak": "peak",
        "delta_heat_pump_capacity": "heat_pump_capacity",
        "delta_gas_heater_capacity": "gas_heater_capacity",
        "delta_chp_capacity": "chp_capacity",
        "delta_pv_capacity": "pv_capacity",
        "delta_battery_capacity": "battery_capacity",
        "delta_thermal_storage_capacity": "thermal_storage_capacity",
        "delta_retrofit_depth": "retrofit_depth",
    }
    delta_rows_by_ueu = {}
    for ueu_label in ueu_order:
        cen_by_tradeoff = centralized_rows_by_ueu.get(ueu_label, {})
        dec_by_tradeoff = decentralized_rows_by_ueu.get(ueu_label, {})
        if not cen_by_tradeoff or not dec_by_tradeoff:
            continue

        delta_by_tradeoff = {}
        for tradeoff_name in ("cost-co2", "cost-peak", "peak-co2"):
            cen_rows = list(cen_by_tradeoff.get(tradeoff_name, []))
            dec_rows = list(dec_by_tradeoff.get(tradeoff_name, []))
            n_rows = min(len(cen_rows), len(dec_rows))
            rows = []
            for point_idx in range(n_rows):
                cen_row = cen_rows[point_idx]
                dec_row = dec_rows[point_idx]
                delta_row = {
                    "point_order": int(point_idx),
                }
                for delta_key, source_key in source_keys.items():
                    cen_value = float(cen_row.get(source_key, 0.0))
                    dec_value = float(dec_row.get(source_key, 0.0))
                    delta_row[delta_key] = cen_value - dec_value
                rows.append(delta_row)
            delta_by_tradeoff[tradeoff_name] = rows

        if any(delta_by_tradeoff.values()):
            delta_rows_by_ueu[ueu_label] = delta_by_tradeoff

    return delta_rows_by_ueu


def plot_parallel_coordinates_delta_tradeoff_fronts_stacked_ueus(
    rows_by_ueu,
    filename,
    *,
    ueu_order=None,
    scaling_mode="global_max",
    figsize=(6, 8),
    font_size=9,
    axis_font_size=None,
    legend_font_size=None,
    legend_title_font_size=9,
    font_family="TeX Gyre Termes",
    plot_mode="thin_bars",
    dpi=600,
    subplot_left=0.12,
    subplot_right=0.995,
    subplot_bottom=0.22,
    y_label_x=None,
    show=False,
):
    """
    Stacked parallel-coordinates plot of deltas:
    delta x = x_centralized - x_decentralized.

    scaling_mode:
      - "global_max": each delta axis uses one symmetric bound across all UEUs
      - "per_ueu": each UEU panel uses its own symmetric bound per delta axis
    In both modes, 0 is always centered and the scaled axis runs from -1 to 1.
    """
    set_journal_style(font_family=font_family, font_size=font_size)
    axis_font_size = font_size if axis_font_size is None else axis_font_size
    legend_font_size = font_size if legend_font_size is None else legend_font_size
    valid_scaling_modes = {"global_max", "per_ueu"}
    if scaling_mode not in valid_scaling_modes:
        raise ValueError(
            f"scaling_mode must be one of {valid_scaling_modes}, got '{scaling_mode}'"
        )

    axis_specs = _parallel_coordinate_delta_axis_specs()
    tradeoff_styles = {
        "cost-co2": {
            "base_color": "#1b6ca8",
            "start_label": "Ann. TOTEX optimal",
            "end_label": "Ann. GWP optimal",
            "blend_start": 0.05,
            "blend_end": 0.78,
            "reverse_rows": True,
        },
        "peak-co2": {
            "base_color": "#7b3294",
            "start_label": "Peak grid ex. power optimal",
            "end_label": "Ann. GWP optimal",
            "blend_start": 0.05,
            "blend_end": 0.78,
            "reverse_rows": False,
        },
        "cost-peak": {
            "base_color": "#cc4c02",
            "start_label": "Peak grid ex. power optimal",
            "end_label": "Ann. TOTEX optimal",
            "blend_start": 0.05,
            "blend_end": 0.78,
            "reverse_rows": True,
        },
    }
    ueu_label_display_map = {
        "Low heat density": "Low heat density",
        "Medium heat density": "Medium heat density",
        "High heat density": "High heat density",
    }

    if ueu_order is None:
        ordered_ueus = [k for k in rows_by_ueu.keys() if rows_by_ueu.get(k)]
    else:
        ordered_ueus = [k for k in ueu_order if rows_by_ueu.get(k)]
    if not ordered_ueus:
        return None, None

    def _compute_symmetric_bounds(ueu_labels):
        bounds = {}
        for key, _label in axis_specs:
            vals = []
            for ueu_label in ueu_labels:
                for rows in rows_by_ueu[ueu_label].values():
                    vals.extend(float(row.get(key, np.nan)) for row in rows)
            vals = np.asarray(vals, dtype=float)
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                bound = 1.0
            else:
                bound = float(max(abs(np.min(vals)), abs(np.max(vals))))
                if np.isclose(bound, 0.0):
                    bound = 1.0
            bounds[key] = bound
        return bounds

    if scaling_mode == "global_max":
        global_bounds = _compute_symmetric_bounds(ordered_ueus)
        bounds_by_ueu = {ueu_label: global_bounds for ueu_label in ordered_ueus}
    else:
        bounds_by_ueu = {
            ueu_label: _compute_symmetric_bounds([ueu_label])
            for ueu_label in ordered_ueus
        }

    x = np.arange(len(axis_specs))
    fig, axes = plt.subplots(
        nrows=len(ordered_ueus),
        ncols=1,
        figsize=figsize,
        sharex=True,
        gridspec_kw={"hspace": 0.12},
    )
    if len(ordered_ueus) == 1:
        axes = [axes]

    valid_modes_plot = {"thin_bars", "lines_points", "points_only"}
    if plot_mode not in valid_modes_plot:
        raise ValueError(f"plot_mode must be one of {valid_modes_plot}, got '{plot_mode}'")

    for panel_idx, (ax, ueu_label) in enumerate(zip(axes, ordered_ueus)):
        rows_by_tradeoff_local = rows_by_ueu[ueu_label]

        for x_pos in x:
            ax.axvline(x=x_pos, color="#D0D0D0", lw=0.8, zorder=0)
        ax.axhline(y=0.0, color="#6F6F6F", lw=0.75, zorder=1)

        rendered_entries = {"cost-co2": [], "cost-peak": [], "peak-co2": []}
        for tradeoff_name in ("cost-co2", "peak-co2", "cost-peak"):
            rows = rows_by_tradeoff_local.get(tradeoff_name, [])
            if not rows:
                continue
            style = tradeoff_styles[tradeoff_name]
            rows_iter = list(rows)
            if style.get("reverse_rows", False):
                rows_iter = list(reversed(rows_iter))
            n_rows = len(rows_iter)
            blend = np.linspace(
                float(style["blend_start"]),
                float(style["blend_end"]),
                max(n_rows, 1),
            )

            for i, row in enumerate(rows_iter):
                y = []
                raw = []
                for key, _label in axis_specs:
                    raw_val = float(row.get(key, np.nan))
                    raw.append(raw_val)
                    bound = bounds_by_ueu[ueu_label][key]
                    y.append(float(np.clip(raw_val / bound, -1.0, 1.0)))
                line_color = _blend_with_white(style["base_color"], blend[i])
                rendered_entries[tradeoff_name].append(
                    {
                        "y": np.asarray(y, dtype=float),
                        "raw": np.asarray(raw, dtype=float),
                        "color": line_color,
                    }
                )
                if plot_mode == "lines_points":
                    ax.plot(x, y, color=line_color, lw=1.2, alpha=0.95, zorder=2)
                    ax.scatter(x, y, color=line_color, s=8, zorder=3, linewidths=0.0)
                elif plot_mode == "points_only":
                    ax.scatter(x, y, color=line_color, s=14, zorder=3, linewidths=0.0)

        cluster_width = 0.72
        if plot_mode == "thin_bars":
            all_entries = []
            for tradeoff_name in ("cost-co2", "peak-co2", "cost-peak"):
                all_entries.extend(rendered_entries.get(tradeoff_name, []))
            n_total = len(all_entries)
            if n_total > 0:
                if n_total == 1:
                    offsets = np.array([0.0], dtype=float)
                    bar_w = 0.055
                else:
                    bar_w = max(0.008, (cluster_width / n_total) * 0.85)
                    offsets = np.linspace(
                        -cluster_width / 2.0 + bar_w / 2.0,
                        cluster_width / 2.0 - bar_w / 2.0,
                        n_total,
                    )
                for axis_idx, x_pos in enumerate(x):
                    for k, entry in enumerate(all_entries):
                        y_val = float(entry["y"][axis_idx])
                        raw_val = float(entry["raw"][axis_idx])
                        if (not np.isfinite(raw_val)) or np.isclose(raw_val, 0.0, atol=1e-12):
                            continue
                        ax.bar(
                            x_pos + float(offsets[k]),
                            y_val,
                            width=bar_w,
                            color=entry["color"],
                            edgecolor="none",
                            linewidth=0.0,
                            align="center",
                            alpha=0.95,
                            zorder=2.5,
                        )

        side_pad = 0.5 * cluster_width + 0.06 if plot_mode == "thin_bars" else 0.30
        ax.set_xlim(-side_pad, (len(axis_specs) - 1) + side_pad)
        ax.set_ylim(-1.12, 1.12)
        ax.set_yticks([-1.0, -0.5, 0.0, 0.5, 1.0])
        ax.set_yticklabels(["-1.00", "-0.50", "0.00", "0.50", "1.00"])
        ax.grid(axis="y", alpha=0.22, linewidth=0.6)
        ax.tick_params(axis="y", labelsize=axis_font_size)
        middle_panel_idx = len(ordered_ueus) // 2
        if panel_idx == middle_panel_idx:
            ax.set_ylabel(r"Scaled $\Delta$ in -", fontsize=axis_font_size)
            if y_label_x is not None:
                ax.yaxis.set_label_coords(y_label_x, 0.5)
        else:
            ax.set_ylabel("")
        panel_label = ueu_label_display_map.get(ueu_label, ueu_label)
        ax.text(
            0.5,
            0.985,
            panel_label,
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=font_size,
            fontweight="bold",
        )

        show_axis_max_values = (scaling_mode != "global_max") or (panel_idx == 0)
        show_axis_min_values = panel_idx == len(ordered_ueus) - 1

        if show_axis_max_values:
            for x_pos, (key, _label) in zip(x, axis_specs):
                ax.text(
                    x_pos,
                    1.03,
                    _format_axis_value(bounds_by_ueu[ueu_label][key]),
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="bottom",
                    fontsize=axis_font_size,
                    color="#4A4A4A",
                    clip_on=False,
                )
        if show_axis_min_values:
            for x_pos, (key, _label) in zip(x, axis_specs):
                ax.text(
                    x_pos,
                    -0.11,
                    "-" + _format_axis_value(bounds_by_ueu[ueu_label][key]),
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="top",
                    fontsize=axis_font_size,
                    color="#4A4A4A",
                    clip_on=False,
                )

        if panel_idx < len(ordered_ueus) - 1:
            ax.set_xticks(x)
            ax.set_xticklabels([])
            ax.tick_params(axis="x", length=0)
        else:
            ax.set_xticks(x)
            ax.set_xticklabels([lbl for _, lbl in axis_specs], rotation=0, ha="center")
            ax.tick_params(axis="x", labelsize=axis_font_size, pad=14)

    fig.subplots_adjust(
        top=0.73,
        bottom=subplot_bottom,
        left=subplot_left,
        right=subplot_right,
        hspace=0.14,
    )

    ax_pos = axes[0].get_position()
    legend_order = [
        k
        for k in ("cost-co2", "peak-co2", "cost-peak")
        if any(rows_by_ueu[u].get(k) for u in ordered_ueus)
    ]
    legend_row_h = 0.022
    legend_row_gap = 0.034
    legend_y_base = ax_pos.y1 + 0.030

    if legend_order:
        n_leg = len(legend_order)
        y0_top = legend_y_base + (n_leg - 1) * legend_row_gap
        fig.text(
            ax_pos.x0 + 0.5 * ax_pos.width,
            y0_top + legend_row_h,
            r"Pareto-front progression of $\Delta x$",
            ha="center",
            va="bottom",
            fontsize=max(legend_title_font_size - 1, 6),
        )

    for i, name in enumerate(legend_order):
        meta = tradeoff_styles[name]
        y0 = legend_y_base + (len(legend_order) - 1 - i) * legend_row_gap

        bar_w = 0.3200 * ax_pos.width
        bar_x = ax_pos.x0 + 0.5 * ax_pos.width - 0.5 * bar_w
        bar_ax = fig.add_axes([bar_x, y0, bar_w, legend_row_h])

        base_color = meta["base_color"]
        start_col = _blend_with_white(base_color, float(meta["blend_start"]))
        end_col = _blend_with_white(base_color, float(meta["blend_end"]))
        cmap = mcolors.LinearSegmentedColormap.from_list(
            f"{name}_delta_legend_cmap",
            [start_col, end_col],
        )
        grad = np.linspace(0.0, 1.0, 256)[None, :]
        bar_ax.imshow(grad, aspect="auto", cmap=cmap, interpolation="nearest")
        bar_ax.set_yticks([])
        bar_ax.set_xticks([])
        bar_ax.tick_params(axis="x", length=0, pad=0)
        for spine in bar_ax.spines.values():
            spine.set_visible(False)

        fig.text(
            bar_x - 0.010,
            y0 + legend_row_h * 0.52,
            meta["start_label"],
            ha="right",
            va="center",
            fontsize=legend_font_size,
        )
        fig.text(
            bar_x + bar_w + 0.010,
            y0 + legend_row_h * 0.52,
            meta["end_label"],
            ha="left",
            va="center",
            fontsize=legend_font_size,
        )

    _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig, axes


def plot_parallel_coordinates_tradeoff_fronts(
    rows_by_tradeoff,
    filename,
    figsize=(6, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    requested_points_per_front=None,
    plot_mode="lines_points",
    dpi=600,
    include_seasonal_storage=False,
    include_flow_temperature=False,
    show=False,
):
    """
    Parallel coordinates for 3 trade-off fronts with:
      - one base color per front
      - one color-intensity gradient across selected points per front
    """
    set_journal_style(font_family=font_family, font_size=font_size)
    valid_modes = {"lines_points", "points_only", "thin_bars"}
    if plot_mode not in valid_modes:
        raise ValueError(f"plot_mode must be one of {valid_modes}, got '{plot_mode}'")

    axis_specs = _parallel_coordinate_axis_specs(
        include_seasonal_storage=include_seasonal_storage,
        include_flow_temperature=include_flow_temperature,
    )

    all_rows = []
    for rows in rows_by_tradeoff.values():
        all_rows.extend(rows)
    if not all_rows:
        return None, None

    ranges = {}
    for key, _ in axis_specs:
        if key == "retrofit_depth":
            ranges[key] = (0.0, 1.0)
            continue

        vals = np.array([float(r.get(key, np.nan)) for r in all_rows], dtype=float)
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            ranges[key] = (0.0, 1.0)
            continue

        vmin = float(np.min(vals))
        vmax = float(np.max(vals))
        if np.isclose(vmin, vmax):
            eps = 1.0 if np.isclose(vmin, 0.0) else abs(vmin) * 0.1
            vmin -= eps
            vmax += eps
        ranges[key] = (vmin, vmax)

    def _normalise_value(key, val):
        vmin, vmax = ranges[key]
        if np.isclose(vmax, vmin):
            return 0.5
        return float(np.clip((float(val) - vmin) / (vmax - vmin), 0.0, 1.0))

    tradeoff_styles = {
        # Requested progression styling:
        # 1) TOTEX (dark) -> GWP (light)
        # 2) Peak (dark)  -> GWP (light)
        # 3) Peak (dark)  -> TOTEX (dark)
        # blend range uses "white mix" (0 = fully base color, 1 = white)
        "cost-co2": {
            "base_color": "#1b6ca8",
            "start_label": "Ann. TOTEX optimal",
            "end_label": "Ann. GWP optimal",
            "blend_start": 0.05,  # dark (TOTEX side)
            "blend_end": 0.78,    # light (GWP side)
            "reverse_rows": True,
        },
        "peak-co2": {
            "base_color": "#7b3294",
            "start_label": "Peak grid ex. power optimal",
            "end_label": "Ann. GWP optimal",
            "blend_start": 0.05,  # dark (Peak side)
            "blend_end": 0.78,    # light (GWP side)
            "reverse_rows": False,
        },
        "cost-peak": {
            "base_color": "#cc4c02",
            "start_label": "Peak grid ex. power optimal",
            "end_label": "Ann. TOTEX optimal",
            "blend_start": 0.05,  # dark (Peak side)
            "blend_end": 0.78,    # light (TOTEX side)
            "reverse_rows": True,
        },
    }

    x = np.arange(len(axis_specs))
    fig, ax = plt.subplots(figsize=figsize)

    for x_pos in x:
        ax.axvline(x=x_pos, color="#D0D0D0", lw=0.8, zorder=0)

    rendered_entries = {
        "cost-co2": [],
        "cost-peak": [],
        "peak-co2": [],
    }

    for tradeoff_name, rows in rows_by_tradeoff.items():
        if not rows:
            continue
        style = tradeoff_styles.get(
            tradeoff_name,
            {
                "base_color": "#1b6ca8",
                "blend_start": 0.05,
                "blend_end": 0.75,
                "reverse_rows": False,
            },
        )
        base_color = style["base_color"]
        rows_iter = list(rows)
        if style.get("reverse_rows", False):
            rows_iter = list(reversed(rows_iter))
        n = len(rows_iter)
        blend = np.linspace(float(style["blend_start"]), float(style["blend_end"]), max(n, 1))
        for i, row in enumerate(rows_iter):
            y = [_normalise_value(k, row.get(k, np.nan)) for k, _ in axis_specs]
            raw = [float(row.get(k, np.nan)) for k, _ in axis_specs]
            line_color = _blend_with_white(base_color, blend[i])
            rendered_entries.setdefault(tradeoff_name, []).append(
                {
                    "y": np.asarray(y, dtype=float),
                    "raw": np.asarray(raw, dtype=float),
                    "color": line_color,
                }
            )

            if plot_mode == "lines_points":
                ax.plot(x, y, color=line_color, lw=1.2, alpha=0.95, zorder=2)
                ax.scatter(x, y, color=line_color, s=8, zorder=3, linewidths=0.0)
            elif plot_mode == "points_only":
                ax.scatter(x, y, color=line_color, s=14, zorder=3, linewidths=0.0)

    cluster_width = 0.72
    if plot_mode == "thin_bars":
        all_entries = []
        for tradeoff_name in ("cost-co2", "peak-co2", "cost-peak"):
            all_entries.extend(rendered_entries.get(tradeoff_name, []))
        n_total = len(all_entries)
        if n_total > 0:
            if n_total == 1:
                offsets = np.array([0.0], dtype=float)
                bar_w = 0.055
            else:
                bar_w = max(0.008, (cluster_width / n_total) * 0.85)
                offsets = np.linspace(
                    -cluster_width / 2.0 + bar_w / 2.0,
                    cluster_width / 2.0 - bar_w / 2.0,
                    n_total,
                )

            for axis_idx, x_pos in enumerate(x):
                for k, entry in enumerate(all_entries):
                    y_val = float(entry["y"][axis_idx])
                    raw_val = float(entry["raw"][axis_idx])
                    if (not np.isfinite(raw_val)) or np.isclose(raw_val, 0.0, atol=1e-12):
                        # Keep empty slot for this bar (no fill), so alignment stays readable.
                        continue
                    ax.bar(
                        x_pos + float(offsets[k]),
                        y_val,
                        width=bar_w,
                        color=entry["color"],
                        edgecolor="none",
                        linewidth=0.0,
                        align="center",
                        alpha=0.95,
                        zorder=2.5,
                    )

    if plot_mode == "thin_bars":
        # Keep full bar clusters visible at both outer axes.
        side_pad = 0.5 * cluster_width + 0.06
    else:
        side_pad = 0.30
    ax.set_xlim(-side_pad, (len(axis_specs) - 1) + side_pad)
    ax.set_ylim(-0.12, 1.12)
    ax.set_xticks(x)
    ax.set_xticklabels([lbl for _, lbl in axis_specs], rotation=0, ha="center")
    ax.tick_params(axis="x", labelsize=font_size, pad=14)
    ax.set_yticks(np.linspace(0, 1, 5))
    ax.set_yticklabels([f"{t:.2f}" for t in np.linspace(0, 1, 5)])
    ax.tick_params(axis="y", labelsize=font_size)
    ax.set_ylabel("Scaled within each axis in -", fontsize=font_size)
    ax.grid(axis="y", alpha=0.22, linewidth=0.6)

    for x_pos, (key, _) in zip(x, axis_specs):
        vmin, vmax = ranges[key]
        ax.text(
            x_pos,
            -0.11,
            _format_axis_value(vmin),
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=font_size,
            color="#4A4A4A",
            clip_on=False,
        )
        ax.text(
            x_pos,
            1.03,
            _format_axis_value(vmax),
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=font_size,
            color="#4A4A4A",
            clip_on=False,
        )

    fig.subplots_adjust(top=0.50, bottom=0.28, left=0.07, right=0.995)

    ax_pos = ax.get_position()
    # Desired legend order (top -> bottom):
    # 1) TOTEX <-> GWP, 2) Peak <-> GWP, 3) Peak <-> TOTEX
    legend_order = [k for k in ("cost-co2", "peak-co2", "cost-peak") if rows_by_tradeoff.get(k)]
    legend_row_h = 0.0264
    legend_row_gap = 0.052
    legend_y_base = ax_pos.y1 + 0.060

    if legend_order:
        n_leg = len(legend_order)
        y0_top = legend_y_base + (n_leg - 1) * legend_row_gap
        fig.text(
            ax_pos.x0 + 0.5 * ax_pos.width,
            y0_top + legend_row_h,
            "Pareto-front progression along selected points",
            ha="center",
            va="bottom",
            fontsize=font_size,
        )

    for i, name in enumerate(legend_order):
        meta = tradeoff_styles[name]
        y0 = legend_y_base + (len(legend_order) - 1 - i) * legend_row_gap

        bar_w = 0.4125 * ax_pos.width
        bar_x = ax_pos.x0 + 0.5 * ax_pos.width - 0.5 * bar_w
        bar_ax = fig.add_axes([bar_x, y0, bar_w, legend_row_h])

        base_color = meta["base_color"]
        start_col = _blend_with_white(base_color, float(meta["blend_start"]))
        end_col = _blend_with_white(base_color, float(meta["blend_end"]))
        cmap = mcolors.LinearSegmentedColormap.from_list(
            f"{name}_legend_cmap",
            [start_col, end_col],
        )
        grad = np.linspace(0.0, 1.0, 256)[None, :]
        bar_ax.imshow(grad, aspect="auto", cmap=cmap, interpolation="nearest")
        bar_ax.set_yticks([])
        bar_ax.set_xticks([])
        bar_ax.tick_params(axis="x", length=0, pad=0)
        for spine in bar_ax.spines.values():
            spine.set_visible(False)

        fig.text(
            bar_x - 0.010,
            y0 + legend_row_h * 0.52,
            meta["start_label"],
            ha="right",
            va="center",
            fontsize=font_size,
        )
        fig.text(
            bar_x + bar_w + 0.010,
            y0 + legend_row_h * 0.52,
            meta["end_label"],
            ha="left",
            va="center",
            fontsize=font_size,
        )

    _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig, ax


def plot_parallel_coordinates_tradeoff_fronts_stacked_ueus(
    rows_by_ueu,
    filename,
    *,
    ueu_order=None,
    scaling_mode="per_ueu",
    figsize=(6, 8),
    font_size=9,
    axis_font_size=None,
    legend_font_size=None,
    legend_title_font_size=9,
    font_family="TeX Gyre Termes",
    plot_mode="thin_bars",
    dpi=600,
    include_seasonal_storage=False,
    include_heat_grid_totex=False,
    include_heat_grid_retrofit_temp_case=False,
    include_flow_temperature=False,
    x_label_rotation=0,
    subplot_left=0.12,
    subplot_right=0.995,
    subplot_bottom=0.22,
    y_label_x=None,
    show=False,
):
    """
    Stacked (top/middle/bottom) parallel-coordinates plot across UEUs.

    scaling_mode:
      - "per_ueu": each UEU is normalized with its own axis ranges
      - "global_max": all UEUs share one common max per axis (min fixed to 0 for non-retrofit)
    """
    set_journal_style(font_family=font_family, font_size=font_size)
    axis_font_size = font_size if axis_font_size is None else axis_font_size
    legend_font_size = font_size if legend_font_size is None else legend_font_size
    valid_modes = {"per_ueu", "global_max"}
    if scaling_mode not in valid_modes:
        raise ValueError(f"scaling_mode must be one of {valid_modes}, got '{scaling_mode}'")

    axis_specs = _parallel_coordinate_axis_specs(
        include_seasonal_storage=include_seasonal_storage,
        include_heat_grid_totex=include_heat_grid_totex,
        include_heat_grid_retrofit_temp_case=include_heat_grid_retrofit_temp_case,
        include_flow_temperature=include_flow_temperature,
    )
    tradeoff_styles = {
        "cost-co2": {
            "base_color": "#1b6ca8",
            "start_label": "Ann. TOTEX optimal",
            "end_label": "Ann. GWP optimal",
            "blend_start": 0.05,
            "blend_end": 0.78,
            "reverse_rows": True,
        },
        "peak-co2": {
            "base_color": "#7b3294",
            "start_label": "Peak grid ex. power optimal",
            "end_label": "Ann. GWP optimal",
            "blend_start": 0.05,
            "blend_end": 0.78,
            "reverse_rows": False,
        },
        "cost-peak": {
            "base_color": "#cc4c02",
            "start_label": "Peak grid ex. power optimal",
            "end_label": "Ann. TOTEX optimal",
            "blend_start": 0.05,
            "blend_end": 0.78,
            "reverse_rows": True,
        },
    }
    ueu_label_display_map = {
        "Low heat density": "Low heat density",
        "Medium heat density": "Medium heat density",
        "High heat density": "High heat density",
    }

    def _flatten_rows(rows_by_tradeoff_local):
        merged = []
        for _name, _rows in rows_by_tradeoff_local.items():
            merged.extend(_rows)
        return merged

    def _compute_ranges_from_rows(all_rows, *, global_max_mode=False):
        ranges_local = {}
        for key, _ in axis_specs:
            if key == "retrofit_depth":
                ranges_local[key] = (0.0, 1.0)
                continue
            vals = np.array([float(r.get(key, np.nan)) for r in all_rows], dtype=float)
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                ranges_local[key] = (0.0, 1.0)
                continue

            if global_max_mode:
                vmin = 40.0 if key == "avg_flow_temperature" else 0.0
                vmax = float(np.max(vals))
            else:
                vmin = float(np.min(vals))
                vmax = float(np.max(vals))
            if np.isclose(vmin, vmax):
                eps = 1.0 if np.isclose(vmax, 0.0) else abs(vmax) * 0.1
                vmax += eps
                if not global_max_mode:
                    vmin -= eps
            ranges_local[key] = (vmin, vmax)
        return ranges_local

    if ueu_order is None:
        ordered_ueus = [k for k in rows_by_ueu.keys() if rows_by_ueu.get(k)]
    else:
        ordered_ueus = [k for k in ueu_order if rows_by_ueu.get(k)]
    if not ordered_ueus:
        return None, None

    if scaling_mode == "global_max":
        rows_all_ueus = []
        for ueu_key in ordered_ueus:
            rows_all_ueus.extend(_flatten_rows(rows_by_ueu[ueu_key]))
        global_ranges = _compute_ranges_from_rows(rows_all_ueus, global_max_mode=True)
        ranges_by_ueu = {ueu_key: global_ranges for ueu_key in ordered_ueus}
    else:
        ranges_by_ueu = {}
        for ueu_key in ordered_ueus:
            ranges_by_ueu[ueu_key] = _compute_ranges_from_rows(
                _flatten_rows(rows_by_ueu[ueu_key]),
                global_max_mode=False,
            )

    x = np.arange(len(axis_specs))
    fig, axes = plt.subplots(
        nrows=len(ordered_ueus),
        ncols=1,
        figsize=figsize,
        sharex=True,
        gridspec_kw={"hspace": 0.12},
    )
    if len(ordered_ueus) == 1:
        axes = [axes]

    def _normalise_value(value, vmin, vmax):
        if np.isclose(vmin, vmax):
            return 0.5
        return float(np.clip((float(value) - vmin) / (vmax - vmin), 0.0, 1.0))

    valid_modes_plot = {"lines_points", "points_only", "thin_bars"}
    if plot_mode not in valid_modes_plot:
        raise ValueError(f"plot_mode must be one of {valid_modes_plot}, got '{plot_mode}'")

    for panel_idx, (ax, ueu_label) in enumerate(zip(axes, ordered_ueus)):
        rows_by_tradeoff_local = rows_by_ueu[ueu_label]
        ranges = ranges_by_ueu[ueu_label]

        for x_pos in x:
            ax.axvline(x=x_pos, color="#D0D0D0", lw=0.8, zorder=0)

        rendered_entries = {"cost-co2": [], "cost-peak": [], "peak-co2": []}
        for tradeoff_name in ("cost-co2", "peak-co2", "cost-peak"):
            rows = rows_by_tradeoff_local.get(tradeoff_name, [])
            if not rows:
                continue
            style = tradeoff_styles[tradeoff_name]
            rows_iter = list(rows)
            if style.get("reverse_rows", False):
                rows_iter = list(reversed(rows_iter))
            n_rows = len(rows_iter)
            blend = np.linspace(
                float(style["blend_start"]),
                float(style["blend_end"]),
                max(n_rows, 1),
            )

            for i, row in enumerate(rows_iter):
                y = []
                raw = []
                for key, _ in axis_specs:
                    raw_val = float(row.get(key, np.nan))
                    raw.append(raw_val)
                    y.append(_normalise_value(raw_val, *ranges[key]))
                line_color = _blend_with_white(style["base_color"], blend[i])
                rendered_entries[tradeoff_name].append(
                    {
                        "y": np.asarray(y, dtype=float),
                        "raw": np.asarray(raw, dtype=float),
                        "color": line_color,
                    }
                )
                if plot_mode == "lines_points":
                    ax.plot(x, y, color=line_color, lw=1.2, alpha=0.95, zorder=2)
                    ax.scatter(x, y, color=line_color, s=8, zorder=3, linewidths=0.0)
                elif plot_mode == "points_only":
                    ax.scatter(x, y, color=line_color, s=14, zorder=3, linewidths=0.0)

        cluster_width = 0.72
        if plot_mode == "thin_bars":
            all_entries = []
            for tradeoff_name in ("cost-co2", "peak-co2", "cost-peak"):
                all_entries.extend(rendered_entries.get(tradeoff_name, []))
            n_total = len(all_entries)
            if n_total > 0:
                if n_total == 1:
                    offsets = np.array([0.0], dtype=float)
                    bar_w = 0.055
                else:
                    bar_w = max(0.008, (cluster_width / n_total) * 0.85)
                    offsets = np.linspace(
                        -cluster_width / 2.0 + bar_w / 2.0,
                        cluster_width / 2.0 - bar_w / 2.0,
                        n_total,
                    )
                for axis_idx, x_pos in enumerate(x):
                    for k, entry in enumerate(all_entries):
                        y_val = float(entry["y"][axis_idx])
                        raw_val = float(entry["raw"][axis_idx])
                        if (not np.isfinite(raw_val)) or np.isclose(raw_val, 0.0, atol=1e-12):
                            continue
                        ax.bar(
                            x_pos + float(offsets[k]),
                            y_val,
                            width=bar_w,
                            color=entry["color"],
                            edgecolor="none",
                            linewidth=0.0,
                            align="center",
                            alpha=0.95,
                            zorder=2.5,
                        )

        side_pad = 0.5 * cluster_width + 0.06 if plot_mode == "thin_bars" else 0.30
        ax.set_xlim(-side_pad, (len(axis_specs) - 1) + side_pad)
        ax.set_ylim(-0.12, 1.12)
        ax.set_yticks(np.linspace(0, 1, 5))
        ax.set_yticklabels([f"{t:.2f}" for t in np.linspace(0, 1, 5)])
        ax.grid(axis="y", alpha=0.22, linewidth=0.6)
        ax.tick_params(axis="y", labelsize=axis_font_size)
        middle_panel_idx = len(ordered_ueus) // 2
        if panel_idx == middle_panel_idx:
            ax.set_ylabel("Scaled within each axis in -", fontsize=axis_font_size)
            if y_label_x is not None:
                ax.yaxis.set_label_coords(y_label_x, 0.5)
        else:
            ax.set_ylabel("")
        panel_label = ueu_label_display_map.get(ueu_label, ueu_label)
        ax.text(
            0.5,
            0.985,
            panel_label,
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=font_size,
            fontweight="bold",
        )

        # Axis-wise value bounds:
        # - per_ueu: show min+max on every panel
        # - global_max: show max only on top panel and min only on bottom panel
        show_axis_max_values = (scaling_mode != "global_max") or (panel_idx == 0)
        show_axis_min_values = (scaling_mode != "global_max") or (panel_idx == len(ordered_ueus) - 1)

        if show_axis_min_values:
            for x_pos, (key, _) in zip(x, axis_specs):
                vmin, _ = ranges[key]
                ax.text(
                    x_pos,
                    -0.11,
                    _format_axis_value(vmin),
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="top",
                    fontsize=axis_font_size,
                    color="#4A4A4A",
                    clip_on=False,
                )
        if show_axis_max_values:
            for x_pos, (key, _) in zip(x, axis_specs):
                _, vmax = ranges[key]
                ax.text(
                    x_pos,
                    1.03,
                    _format_axis_value(vmax),
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="bottom",
                    fontsize=axis_font_size,
                    color="#4A4A4A",
                    clip_on=False,
                )

        if panel_idx < len(ordered_ueus) - 1:
            ax.set_xticks(x)
            ax.set_xticklabels([])
            ax.tick_params(axis="x", length=0)
        else:
            ax.set_xticks(x)
            label_ha = "right" if x_label_rotation else "center"
            if x_label_rotation:
                ax.set_xticklabels(
                    [lbl for _, lbl in axis_specs],
                    rotation=x_label_rotation,
                    ha=label_ha,
                    rotation_mode="anchor",
                )
            else:
                ax.set_xticklabels([lbl for _, lbl in axis_specs], rotation=0, ha=label_ha)
            ax.tick_params(axis="x", labelsize=axis_font_size, pad=14)

    # Keep the fixed 11.8 cm page width. The UEU panels stay compact enough for
    # the top legend and bottom x labels, but slightly taller than the tight draft.
    fig.subplots_adjust(
        top=0.73,
        bottom=subplot_bottom,
        left=subplot_left,
        right=subplot_right,
        hspace=0.14,
    )

    # Same gradient legend style as single-UEU parallel-coordinates figure.
    ax_pos = axes[0].get_position()
    legend_order = [k for k in ("cost-co2", "peak-co2", "cost-peak") if any(rows_by_ueu[u].get(k) for u in ordered_ueus)]
    legend_row_h = 0.022
    legend_row_gap = 0.034
    legend_y_base = ax_pos.y1 + 0.030

    if legend_order:
        n_leg = len(legend_order)
        y0_top = legend_y_base + (n_leg - 1) * legend_row_gap
        fig.text(
            ax_pos.x0 + 0.5 * ax_pos.width,
            y0_top + legend_row_h,
            "Pareto-front progression along selected points",
            ha="center",
            va="bottom",
            fontsize=legend_title_font_size,
        )

    for i, name in enumerate(legend_order):
        meta = tradeoff_styles[name]
        y0 = legend_y_base + (len(legend_order) - 1 - i) * legend_row_gap

        bar_w = 0.3200 * ax_pos.width
        bar_x = ax_pos.x0 + 0.5 * ax_pos.width - 0.5 * bar_w
        bar_ax = fig.add_axes([bar_x, y0, bar_w, legend_row_h])

        base_color = meta["base_color"]
        start_col = _blend_with_white(base_color, float(meta["blend_start"]))
        end_col = _blend_with_white(base_color, float(meta["blend_end"]))
        cmap = mcolors.LinearSegmentedColormap.from_list(
            f"{name}_legend_cmap",
            [start_col, end_col],
        )
        grad = np.linspace(0.0, 1.0, 256)[None, :]
        bar_ax.imshow(grad, aspect="auto", cmap=cmap, interpolation="nearest")
        bar_ax.set_yticks([])
        bar_ax.set_xticks([])
        bar_ax.tick_params(axis="x", length=0, pad=0)
        for spine in bar_ax.spines.values():
            spine.set_visible(False)

        fig.text(
            bar_x - 0.010,
            y0 + legend_row_h * 0.52,
            meta["start_label"],
            ha="right",
            va="center",
            fontsize=legend_font_size,
        )
        fig.text(
            bar_x + bar_w + 0.010,
            y0 + legend_row_h * 0.52,
            meta["end_label"],
            ha="left",
            va="center",
            fontsize=legend_font_size,
        )

    _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig, axes


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

        ax.set_ylabel(_linebreak_after_in_label(f'{value_type.capitalize()} in thousands EUR' if value_type == "cost" else 'CO2-eq. in t'))

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
import matplotlib.pyplot as plt
import numpy as np
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
    energy_types = _ordered_stackplot_energy_types(energy_types)

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
    technology_colors, energy_colors = _stackplot_colors(technologies, energy_types)

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
            labels=[_technology_display_label(tech) for tech in technologies],
            linewidth=0.0
        )

        ax1.set_ylabel(_linebreak_after_in_label(y_label_override or "Installed capacity (kW or kWh)"))

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
        labels = [_technology_display_label(tech) for tech in technologies] + list(energy_types)

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
            ax1.set_ylabel(_linebreak_after_in_label(y_label_override))
        else:
            ax1.set_ylabel(_linebreak_after_in_label("Totex in thousand EUR" if vt == "cost" else r"Ann. CO$_2$-eq. in t"))
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
        label="Peak grid ex. power in kW",
        zorder=5,
        drawstyle=peak_drawstyle if peak_drawstyle else "default",
    )

    ax2.set_ylabel(_linebreak_after_in_label(peak_label_override or "Peak grid ex. power in kW"))

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
        _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig, ax1, ax2


def plot_combined_stackplots_for_pareto_solutions_with_peak(
    district_sums,
    technologies,
    energy_types,
    value_types=("cost", "co2", "capacity"),
    figsize=(6.0, 9.0),
    font_size=9,
    font_family="TeX Gyre Termes",
    facecolor="white",
    dpi=600,
    filename=None,
    show=True,
    x_label="Pareto-optimal solution index (sorted)",
    sort_key=None,
    target_xticks=8,
    x_tick_rotation=0,
    peak_lw=0.4,
    peak_alpha=0.9,
    peak_drawstyle="steps-mid",
    peak_smooth_window=0,
    y_labels=None,
    peak_label_override="Peak grid ex. power in kW",
    legend_ncol=4,
    legend_loc="upper center",
    legend_bbox=(0.5, 1.03),
    compact_width_layout=True,
    capacity_y_scale="linear",
    capacity_symlog_linthresh=10.0,
):
    energy_types = _ordered_stackplot_energy_types(energy_types)
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

    solution_ids = list(district_sums.keys())
    if sort_key in ("co2", "cost", "totex", "peak"):
        solution_ids = sorted(
            solution_ids,
            key=lambda sid: float(district_sums[sid].get(sort_key, np.nan))
        )

    n_pts = len(solution_ids)
    x = np.arange(n_pts)
    tick_pos, tick_labels = _build_pareto_xticks(n_pts, target_ticks=target_xticks)
    tick_pos = list(tick_pos)
    tick_labels = list(tick_labels)
    if len(tick_pos) >= 2:
        tick_pos.pop(-2)
        tick_labels.pop(-2)

    n_tech = len(technologies)
    n_energy = len(energy_types)
    technology_colors, energy_colors = _stackplot_colors(technologies, energy_types)
    colors = list(technology_colors) + list(energy_colors)
    labels = [_technology_display_label(tech) for tech in technologies] + list(energy_types)

    fig, axes = plt.subplots(
        nrows=len(value_types),
        ncols=1,
        figsize=figsize,
        facecolor=facecolor,
        sharex=True,
    )
    if len(value_types) == 1:
        axes = [axes]

    peak_axes = []
    for i, (ax1, vt_raw) in enumerate(zip(axes, value_types)):
        vt = str(vt_raw).lower()

        if vt == "capacity":
            tech_only = []
            for sid in solution_ids:
                tech_data = district_sums[sid]["technologies"]
                tech_vals = [max(0.0, float(tech_data.get(tech, {}).get("capacity", 0.0))) for tech in technologies]
                tech_only.append(tech_vals)
            tech_only = np.array(tech_only).T
            if tech_only.size == 0:
                raise ValueError("No capacity data found for technologies.")
            ax1.stackplot(
                x,
                *tech_only,
                alpha=0.75,
                colors=technology_colors,
                labels=[_technology_display_label(tech) for tech in technologies],
                linewidth=0.0,
            )
            if str(capacity_y_scale).lower() in ("symlog", "log"):
                stacked_capacity = np.sum(tech_only, axis=0)
                max_capacity = float(np.nanmax(stacked_capacity)) if stacked_capacity.size else np.nan
                _set_capacity_symlog_axis(
                    ax1,
                    max_capacity,
                    linthresh=float(capacity_symlog_linthresh),
                )
        elif vt in ("cost", "co2"):
            all_data_positive = []
            all_data_negative = []
            for sid in solution_ids:
                tech_data = district_sums[sid]["technologies"]
                energy_data = district_sums[sid].get("energy_types", {})

                tech_pos = [max(0.0, float(tech_data.get(tech, {}).get(vt, 0.0))) for tech in technologies]
                tech_neg = [min(0.0, float(tech_data.get(tech, {}).get(vt, 0.0))) for tech in technologies]
                energy_pos = [max(0.0, float(energy_data.get(e, {}).get(vt, 0.0))) for e in energy_types]
                energy_neg = [min(0.0, float(energy_data.get(e, {}).get(vt, 0.0))) for e in energy_types]

                all_data_positive.append(tech_pos + energy_pos)
                all_data_negative.append(tech_neg + energy_neg)

            all_data_positive = np.array(all_data_positive).T
            all_data_negative = np.array(all_data_negative).T
            if all_data_positive.shape[1] != n_pts:
                raise ValueError("Mismatch in number of Pareto solutions and data points")

            polys_pos = ax1.stackplot(
                x, *all_data_positive,
                alpha=0.70, colors=colors, labels=labels, linewidth=0.0
            )
            polys_neg = ax1.stackplot(
                x, *all_data_negative,
                alpha=0.70, colors=colors, baseline="zero", linewidth=0.0
            )
            energy_hatch = ".."
            hatch_lw = 0.04
            for j in range(len(energy_types)):
                idx = n_tech + j
                for poly in (polys_pos[idx], polys_neg[idx]):
                    poly.set_hatch(energy_hatch)
                    poly.set_edgecolor("black")
                    poly.set_linewidth(hatch_lw)
        else:
            raise ValueError("value_types must only contain {'cost','co2','capacity'}")

        if y_labels is not None and vt in y_labels:
            ax1.set_ylabel(_linebreak_after_in_label(y_labels[vt]))
        elif vt == "cost":
            ax1.set_ylabel(_linebreak_after_in_label("Totex in thousand EUR"))
        elif vt == "co2":
            ax1.set_ylabel(_linebreak_after_in_label(r"Ann. CO$_2$-eq. in t"))
        else:
            ax1.set_ylabel(_linebreak_after_in_label("Installed capacity in kW or kWh"))

        ax2 = ax1.twinx()
        peak_axes.append(ax2)
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
            label="Peak grid ex. power in kW",
            zorder=5,
            drawstyle=peak_drawstyle if peak_drawstyle else "default",
        )
        ax2.set_ylabel(_linebreak_after_in_label(peak_label_override or "Peak grid ex. power in kW"))
        ax1.yaxis.labelpad = 2
        ax2.yaxis.labelpad = 2
        ax1.tick_params(axis="y", pad=1.5)
        ax2.tick_params(axis="y", pad=1.5)

        ax1.grid(True, axis="y", alpha=0.25, linewidth=0.6)
        ax1.set_xlim(-0.5, n_pts - 0.5 + 0.02 * n_pts)
        if i < len(value_types) - 1:
            ax1.tick_params(axis="x", which="both", labelbottom=False)

    axes[-1].set_xticks(tick_pos)
    axes[-1].set_xticklabels(tick_labels, rotation=x_tick_rotation, ha="center")
    axes[-1].set_xlabel(x_label)
    lbls = axes[-1].get_xticklabels()
    if lbls:
        lbls[-1].set_ha("right")

    h1, l1 = axes[0].get_legend_handles_labels()
    h2, l2 = peak_axes[0].get_legend_handles_labels()
    unique = {}
    for h, l in list(zip(h1, l1)) + list(zip(h2, l2)):
        if l not in unique:
            unique[l] = h

    if compact_width_layout:
        legend_ncol = min(4, legend_ncol)
        legend_bbox = (0.5, 0.965)

    fig.legend(
        unique.values(),
        unique.keys(),
        ncol=legend_ncol,
        loc=legend_loc,
        bbox_to_anchor=legend_bbox,
        frameon=False,
        handlelength=1.15,
        columnspacing=0.70,
        handletextpad=0.35,
        labelspacing=0.25,
    )

    fig.tight_layout(rect=[0, 0, 1, 0.86], h_pad=0.50)
    if compact_width_layout:
        # Keep the PDF width fixed at 11.8 cm. Use most of the safe horizontal
        # space while leaving room for both y-axes and the compact top legend.
        fig.subplots_adjust(left=0.15, right=0.88, top=0.84, hspace=0.22)

    if filename:
        _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)
    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig, axes, peak_axes


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


TOTEX_RECONCILIATION_TECHNOLOGIES = [
    "PV-System",
    "Heat storage",
    "Battery",
    "Gas heater",
    "CHP",
    "Heat pump",
    "Heat grid",
    "Seasonal storage",
    "Retrofit",
]

TOTEX_RECONCILIATION_ENERGY_TYPES = [
    "Electricity",
    "Bio gas",
    "Natural gas",
    "Hydrogen",
]


def _as_float_or_zero(value):
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _csv_cost_column(prefix, name):
    cleaned = (
        str(name)
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )
    return f"{prefix}_{cleaned}_cost"


def build_totex_reconciliation_rows(district_sums):
    rows = []
    for district_id, district in district_sums.items():
        technology_costs = {
            tech: _as_float_or_zero(
                district.get("technologies", {}).get(tech, {}).get("cost", 0.0)
            )
            for tech in TOTEX_RECONCILIATION_TECHNOLOGIES
        }
        energy_costs = {
            energy: _as_float_or_zero(
                district.get("energy_types", {}).get(energy, {}).get("cost", 0.0)
            )
            for energy in TOTEX_RECONCILIATION_ENERGY_TYPES
        }

        technology_cost_sum = sum(technology_costs.values())
        energy_cost_sum = sum(energy_costs.values())
        component_cost_sum = technology_cost_sum + energy_cost_sum
        totex = _as_float_or_zero(district.get("totex", 0.0))
        difference = totex - component_cost_sum
        relative_difference = difference / totex if not np.isclose(totex, 0.0) else np.nan

        row = {
            "district_id": district_id,
            "totex": totex,
            "technology_cost_sum": technology_cost_sum,
            "energy_cost_sum": energy_cost_sum,
            "component_cost_sum": component_cost_sum,
            "totex_minus_component_cost_sum": difference,
            "relative_difference_to_totex": relative_difference,
        }
        for tech, cost in technology_costs.items():
            row[_csv_cost_column("technology", tech)] = cost
        for energy, cost in energy_costs.items():
            row[_csv_cost_column("energy", energy)] = cost
        rows.append(row)

    return rows


def write_totex_reconciliation_csv(filename, rows):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    fieldnames = [
        "district_id",
        "totex",
        "technology_cost_sum",
        "energy_cost_sum",
        "component_cost_sum",
        "totex_minus_component_cost_sum",
        "relative_difference_to_totex",
    ]
    fieldnames += [
        _csv_cost_column("technology", tech)
        for tech in TOTEX_RECONCILIATION_TECHNOLOGIES
    ]
    fieldnames += [
        _csv_cost_column("energy", energy)
        for energy in TOTEX_RECONCILIATION_ENERGY_TYPES
    ]

    with open(filename, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_totex_reconciliation_summary(rows, label):
    if not rows:
        print(f"TOTEX reconciliation {label}: no rows")
        return
    abs_diffs = [
        abs(_as_float_or_zero(row["totex_minus_component_cost_sum"]))
        for row in rows
    ]
    rel_diffs = [
        abs(_as_float_or_zero(row["relative_difference_to_totex"]))
        for row in rows
        if not np.isnan(_as_float_or_zero(row["relative_difference_to_totex"]))
    ]
    max_abs_diff = max(abs_diffs) if abs_diffs else 0.0
    max_rel_diff = max(rel_diffs) if rel_diffs else 0.0
    print(
        f"TOTEX reconciliation {label}: "
        f"max abs diff={max_abs_diff:.6g}, max rel diff={max_rel_diff:.6%}"
    )


def plot_totex_reconciliation_difference(
    rows,
    filename,
    figsize=(6, 3),
    font_size=9,
    show=False,
):
    if not rows:
        return

    x = np.arange(len(rows))
    differences = np.array(
        [
            _as_float_or_zero(row["totex_minus_component_cost_sum"])
            for row in rows
        ],
        dtype=float,
    )

    fig, ax = plt.subplots(figsize=figsize)
    ax.bar(
        x,
        differences,
        width=0.85,
        color="#4C78A8",
        edgecolor="black",
        linewidth=0.2,
    )
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_xlabel("Pareto-optimal solution index (sorted)", fontsize=font_size)
    ax.set_ylabel(
        _linebreak_after_in_label(r"TOTEX - component cost sum in $\mathrm{EUR}/a$ per 100 m$^2$"),
        fontsize=font_size,
    )
    ax.tick_params(axis="both", labelsize=font_size)
    ax.grid(axis="y", linestyle="--", linewidth=0.4, alpha=0.5)

    if len(rows) > 1:
        tick_idx, tick_labels = _build_pareto_tick_indices(
            len(rows),
            target_ticks=8,
            include_last=True,
        )
        ax.set_xticks(tick_idx)
        ax.set_xticklabels(tick_labels)

    fig.tight_layout()
    if filename:
        _savefig_fixed_pdf_width(fig, filename, dpi=600, format="pdf")
    if show:
        plt.show()
    else:
        plt.close(fig)
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


def _build_pareto_tick_indices(n_points: int, target_ticks: int = 8, include_last: bool = True):
    """Indices + labels for Pareto-front points to highlight (like your stackplot ticks)."""
    if n_points <= 1:
        return np.array([0], dtype=int), ["0"]
    step = _nice_tick_step(n_points, target_ticks=target_ticks)
    idx = np.arange(0, n_points, step, dtype=int)
    if include_last and idx[-1] != n_points - 1:
        idx = np.append(idx, n_points - 1)
    if not include_last:
        idx = idx[idx < (n_points - 1)]
        if idx.size == 0:
            idx = np.array([0], dtype=int)
    labels = [str(int(i)) for i in idx]
    return idx, labels


def _format_strategy_summary_float(value, digits=6):
    if value is None:
        return ""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(value):
        return ""
    return f"{value:.{digits}g}"


def _co2_factor_from_strategy_record(record):
    key = record.get("key")
    if isinstance(key, tuple) and key:
        try:
            return float(key[0])
        except (TypeError, ValueError):
            pass
    metadata = record.get("metadata", {})
    token = metadata.get("file_factor_token")
    if token is None:
        return None
    token = str(token)
    if token.startswith("m0"):
        token = "-0." + token[2:]
    elif token.startswith("0") and token != "0":
        token = "0." + token[1:]
    try:
        return float(token)
    except ValueError:
        return None


def _strategy_summary_row(idx, record):
    metadata = record.get("metadata", {}) if isinstance(record, dict) else {}
    co2_factor = _co2_factor_from_strategy_record(record)
    peak_factor = record.get("peak_reduction_factor")
    objective = metadata.get("file_objective")
    if objective is None:
        key = record.get("key")
        if isinstance(key, tuple) and len(key) >= 3:
            objective = key[2]
    peak_factor_value = None
    try:
        peak_factor_value = float(peak_factor)
    except (TypeError, ValueError):
        pass
    if peak_factor_value is not None and np.isclose(peak_factor_value, 1.0):
        peak_application = "first run in CO2 step: peak_new=False; this run defines the peak reference"
    elif peak_factor_value is None:
        peak_application = ""
    else:
        peak_application = "peak limit = peak_reference_for_same_CO2_step * peak_reduction_factor"

    temperature_level = metadata.get("temperature_level")
    constraint_type = metadata.get("constraint_type")
    strategy_token = ""
    if temperature_level is not None and constraint_type is not None:
        strategy_token = f"t{temperature_level}_{constraint_type}"
    return {
        "pareto_optimal_solution_index": idx,
        "strategy_label": record.get("__strategy_label"),
        "strategy_token": strategy_token,
        "temperature_level": temperature_level,
        "constraint_type": constraint_type,
        "co2_reduction_factor": co2_factor,
        "peak_reduction_factor": peak_factor,
        "co2_application": (
            "CO2 cap = co2_reference * co2_reduction_factor for positive co2_reference; "
            "fallback for non-positive reference: co2_reference * (2 - co2_reduction_factor)"
        ),
        "peak_application": peak_application,
        "file_objective": objective,
        "co2": record.get("co2"),
        "totex": record.get("totex"),
        "peak": record.get("peak"),
        "source_file": metadata.get("source_file"),
        "key": repr(record.get("key")),
    }


def _print_strategy_summary_row(row):
    print(
        "  idx={idx:>2} | strategy={strategy} | token={token} | "
        "co2_factor={co2_factor} | peak_factor={peak_factor} | "
        "co2={co2} | totex={totex} | peak={peak} | peak_application={peak_app}".format(
            idx=row["pareto_optimal_solution_index"],
            strategy=row["strategy_label"],
            token=row["strategy_token"],
            co2_factor=_format_strategy_summary_float(row["co2_reduction_factor"]),
            peak_factor=_format_strategy_summary_float(row["peak_reduction_factor"]),
            co2=_format_strategy_summary_float(row["co2"]),
            totex=_format_strategy_summary_float(row["totex"]),
            peak=_format_strategy_summary_float(row["peak"]),
            peak_app=row["peak_application"],
        )
    )


def print_global_best_strategy_solutions(strategy_records, top_n=5):
    """
    Print globally best strategy solutions before Pareto pruning.

    `strategy_records` must already contain the `__strategy_label` field and use
    the same units as the target plot, e.g. per 100 m2 for the strategy plot.
    """
    objective_sort_keys = {
        "co2": ("co2", "totex", "peak"),
        "totex": ("totex", "co2", "peak"),
        "peak": ("peak", "co2", "totex"),
    }

    def _finite_objective(record, key):
        try:
            value = float(record.get(key))
        except (TypeError, ValueError):
            return False
        return np.isfinite(value)

    finite_records = [
        record
        for record in strategy_records
        if all(_finite_objective(record, key) for key in ("co2", "totex", "peak"))
    ]
    print(
        f"Global best strategy solutions before Pareto pruning "
        f"(top {top_n} per objective, n={len(finite_records)} feasible records):"
    )
    for objective, sort_keys in objective_sort_keys.items():
        print(f"global best by {objective}:")
        sorted_records = sorted(
            finite_records,
            key=lambda record: tuple(float(record[key]) for key in sort_keys),
        )
        for idx, record in enumerate(sorted_records[:top_n]):
            _print_strategy_summary_row(_strategy_summary_row(idx, record))


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
    xlabel=r"Ann. CO$_2$-eq. in kg",
    ylabel=r"Totex in EUR",
    cbar_label=r"Peak grid ex. power in kW",
    # tick-highlight logic (matches stackplot idea)
    target_xticks=8,
    exclude_last_tick_index=False,
    max_labels=12,                        # label at most this many highlighted tick points
    # marker sizes
    s_all=10,
    alpha_all=0.65,
    s_tick=30,
    # pareto line style
    front_lw=1.3,
    front_ls="--",
    axes_width_scale=1.0,
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

    tick_idx, tick_labels = _build_pareto_tick_indices(
        len(pf),
        target_ticks=target_xticks,
        include_last=not exclude_last_tick_index,
    )

    # Label rule: always first and last, plus every second highlighted tick point.
    tick_idx_list = [int(i) for i in tick_idx]
    tick_labels_list = list(tick_labels)
    keep_pos = list(range(0, len(tick_idx_list), 2))
    if tick_idx_list:
        if 0 not in keep_pos:
            keep_pos.insert(0, 0)
        last_pos = len(tick_idx_list) - 1
        if last_pos not in keep_pos:
            keep_pos.append(last_pos)
    keep_pos = sorted(set(keep_pos))
    label_idx = [tick_idx_list[i] for i in keep_pos]
    label_labels = [tick_labels_list[i] for i in keep_pos]
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
    ax.set_ylabel(_linebreak_after_in_label(ylabel))
    ax.grid(True, alpha=0.25, linewidth=0.6)

    # Colorbar
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(_linebreak_after_in_label(cbar_label), fontsize=font_size)
    _apply_integer_colorbar_ticks(cbar)
    cbar.ax.tick_params(labelsize=font_size)

    # Legend
    ax.legend(frameon=False, loc="best")

    fig.tight_layout()
    if axes_width_scale < 1.0:
        pos = ax.get_position()
        new_width = pos.width * axes_width_scale
        x_shift = (pos.width - new_width) / 2.0
        ax.set_position([pos.x0 + x_shift, pos.y0, new_width, pos.height])
    _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return tick_idx, tick_points


def plot_strategy_points_with_front_and_tick_highlights(
    *,
    strategy_fronts,
    filename,
    figsize=(6, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    dpi=600,
    show=False,
    xlabel=r"Ann. CO$_2$-eq. in kg",
    ylabel=r"Totex in EUR",
    cbar_label=r"Peak grid ex. power in kW",
    target_xticks=8,
    exclude_last_tick_index=False,
    s_all=13,
    alpha_all=0.72,
    s_tick=30,
    front_lw=1.3,
    front_ls="--",
    axes_width_scale=1.0,
    summary_filename=None,
    print_solution_summary=False,
    annotate_solution_indices=None,
):
    """
    Plot several centralized strategy fronts as one point cloud, derive one
    resulting Pareto front from their union, and annotate Pareto-solution indices.
    """
    from matplotlib.lines import Line2D

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

    ordered_items = [
        (label, records)
        for label, records in strategy_fronts.items()
        if records
    ]
    if not ordered_items:
        raise ValueError("No strategy fronts available for centralized strategy plot.")

    combined_records = [
        {**record, "__strategy_label": label}
        for label, records in ordered_items
        for record in records
    ]
    data_2d = sorted(
        (
            (float(r["co2"]), float(r["totex"]), float(r.get("peak", np.nan)))
            for r in combined_records
        ),
        key=lambda point: (point[0], point[1]),
    )
    pareto_front = get_pareto_front(data_2d)
    if not pareto_front:
        raise ValueError("No Pareto front could be derived from centralized strategy fronts.")

    pf = sorted(pareto_front, key=lambda t: (t[0], t[1]))
    pf_co2 = np.array([t[0] for t in pf], dtype=float)
    pf_totex = np.array([t[1] for t in pf], dtype=float)
    tick_idx, tick_labels = _build_pareto_tick_indices(
        len(pf),
        target_ticks=target_xticks,
        include_last=not exclude_last_tick_index,
    )
    tick_points = [pf[i] for i in tick_idx]

    if annotate_solution_indices is None:
        tick_idx_list = [int(i) for i in tick_idx]
        tick_labels_list = list(tick_labels)
        keep_pos = list(range(0, len(tick_idx_list), 2))
        if tick_idx_list:
            keep_pos = sorted(set([0, len(tick_idx_list) - 1] + keep_pos))
        label_idx = [tick_idx_list[i] for i in keep_pos]
        label_labels = [tick_labels_list[i] for i in keep_pos]
    else:
        label_idx = [
            int(idx)
            for idx in annotate_solution_indices
            if 0 <= int(idx) < len(pf)
        ]
        label_labels = [str(idx) for idx in label_idx]

    def _match_strategy_record_for_point(co2_value, totex_value, peak_value=None, tol=1e-8):
        for record in combined_records:
            if (
                np.isclose(float(record["co2"]), float(co2_value), atol=tol)
                and np.isclose(float(record["totex"]), float(totex_value), atol=tol)
            ):
                if peak_value is None or np.isclose(
                    float(record.get("peak", np.nan)),
                    float(peak_value),
                    atol=tol,
                ):
                    return record
        return {
            "co2": co2_value,
            "totex": totex_value,
            "peak": np.nan,
            "__strategy_label": None,
        }

    pareto_records = [
        _match_strategy_record_for_point(
            point[0],
            point[1],
            point[2] if len(point) > 2 and np.isfinite(point[2]) else None,
        )
        for point in pf
    ]

    summary_rows = [
        _strategy_summary_row(idx, record)
        for idx, record in enumerate(pareto_records)
    ]
    if print_solution_summary:
        print(
            f"Resulting centralized strategy Pareto front has {len(summary_rows)} "
            f"solutions with zero-based indices 0..{max(len(summary_rows) - 1, 0)}."
        )
        print("Pareto-optimal solution index summary:")
        for row in summary_rows:
            _print_strategy_summary_row(row)
        print_global_best_strategy_solutions(combined_records, top_n=5)

    if summary_filename is not None:
        summary_dir = os.path.dirname(summary_filename)
        if summary_dir:
            os.makedirs(summary_dir, exist_ok=True)
        with open(summary_filename, "w", newline="", encoding="utf-8") as fh:
            fieldnames = list(summary_rows[0].keys()) if summary_rows else [
                "pareto_optimal_solution_index",
            ]
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summary_rows)

    peak_all = np.array([float(r["peak"]) for r in combined_records], dtype=float)
    finite_peak = peak_all[np.isfinite(peak_all)]
    vmin = float(np.min(finite_peak)) if finite_peak.size else 0.0
    vmax = float(np.max(finite_peak)) if finite_peak.size else 1.0
    if np.isclose(vmin, vmax):
        vmax = vmin + 1.0

    palette = sns.color_palette("colorblind", n_colors=8)
    col_front = palette[3]
    col_tick = palette[0]
    marker_by_position = ["^", "s", "p"]

    fig, axes = plt.subplots(
        nrows=2,
        ncols=1,
        figsize=figsize,
        sharex=True,
        sharey=True,
        gridspec_kw={"hspace": 0.08},
    )
    ax_top, ax_bottom = axes
    cmap = plt.get_cmap("viridis")

    def _scatter_strategy_points(ax):
        sc_local = None
        for idx, (label, records) in enumerate(ordered_items):
            marker = marker_by_position[idx % len(marker_by_position)]
            co2 = np.array([float(r["co2"]) for r in records], dtype=float)
            totex = np.array([float(r["totex"]) for r in records], dtype=float)
            peak = np.array([float(r["peak"]) for r in records], dtype=float)
            sc_local = ax.scatter(
                co2,
                totex,
                c=peak,
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                marker=marker,
                s=s_all,
                alpha=alpha_all,
                linewidths=0.20,
                edgecolors="black",
                zorder=1,
            )
        return sc_local

    sc = _scatter_strategy_points(ax_top)

    ax_bottom.plot(
        pf_co2,
        pf_totex,
        linestyle=front_ls,
        linewidth=front_lw,
        color=col_front,
        zorder=2,
        label="Resulting Pareto front",
    )

    for marker_idx, (strategy_label, _) in enumerate(ordered_items):
        marker = marker_by_position[marker_idx % len(marker_by_position)]
        strategy_pareto_records = [
            record
            for record in pareto_records
            if record.get("__strategy_label") == strategy_label
        ]
        if not strategy_pareto_records:
            continue
        ax_bottom.scatter(
            np.array([float(r["co2"]) for r in strategy_pareto_records], dtype=float),
            np.array([float(r["totex"]) for r in strategy_pareto_records], dtype=float),
            c=np.array([float(r.get("peak", np.nan)) for r in strategy_pareto_records], dtype=float),
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            marker=marker,
            s=s_all,
            alpha=alpha_all,
            linewidths=0.20,
            edgecolors="black",
            zorder=4,
        )

    ax_bottom.scatter(
        pf_co2[tick_idx],
        pf_totex[tick_idx],
        s=s_tick,
        facecolors="none",
        edgecolors=col_tick,
        linewidths=0.8,
        zorder=4,
        label="Pareto-optimal solution index",
    )
    for idx, lab in zip(label_idx, label_labels):
        ax_bottom.annotate(
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

    for ax in axes:
        ax.set_ylabel(_linebreak_after_in_label(ylabel))
        ax.grid(True, alpha=0.25, linewidth=0.6)
    ax_top.set_xlabel("")
    ax_top.tick_params(axis="x", labelbottom=False)
    ax_bottom.set_xlabel(xlabel)

    strategy_handles = [
        Line2D(
            [0],
            [0],
            marker=marker_by_position[idx % len(marker_by_position)],
            linestyle="None",
            markerfacecolor="white",
            markeredgecolor="black",
            color="black",
            markersize=5,
            label=label,
        )
        for idx, (label, _) in enumerate(ordered_items)
    ]
    front_handle = Line2D([0], [0], linestyle=front_ls, linewidth=front_lw, color=col_front, label="Resulting Pareto front")
    solution_handle = Line2D(
        [0],
        [0],
        marker="o",
        linestyle="None",
        markerfacecolor="white",
        markeredgecolor="black",
        color="black",
        markersize=5,
        label="Resulting Pareto-front solutions",
    )
    tick_handle = Line2D(
        [0],
        [0],
        marker="o",
        linestyle="None",
        markerfacecolor="none",
        markeredgecolor=col_tick,
        color=col_tick,
        markersize=5,
        label="Pareto-optimal solution index",
    )
    ax_top.legend(
        handles=strategy_handles,
        frameon=False,
        loc="best",
    )
    ax_bottom.legend(
        handles=[front_handle, tick_handle],
        labels=["Resulting Pareto front", "Pareto-optimal solution index"],
        frameon=False,
        loc="best",
    )

    fig.subplots_adjust(left=0.18, right=0.84, bottom=0.16, top=0.96, hspace=0.08)
    if axes_width_scale < 1.0:
        for ax in axes:
            pos = ax.get_position()
            new_width = pos.width * axes_width_scale
            x_shift = (pos.width - new_width) / 2.0
            ax.set_position([pos.x0 + x_shift, pos.y0, new_width, pos.height])

    fig_width, fig_height = fig.get_size_inches()
    top_pos = ax_top.get_position()
    bottom_pos = ax_bottom.get_position()
    cbar_pad = 0.018
    cbar_width = (bottom_pos.height * fig_height / 20.0) / fig_width
    cbar_x0 = max(top_pos.x1, bottom_pos.x1) + cbar_pad
    cbar_y0 = bottom_pos.y0
    cbar_height = top_pos.y1 - bottom_pos.y0
    cax = fig.add_axes([cbar_x0, cbar_y0, cbar_width, cbar_height])
    cbar = fig.colorbar(sc, cax=cax)
    cbar.set_label(_linebreak_after_in_label(cbar_label), fontsize=font_size)
    _apply_integer_colorbar_ticks(cbar)
    cbar.ax.tick_params(labelsize=font_size)
    try:
        _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)
    except PermissionError:
        fallback_path = Path(filename)
        fallback_filename = fallback_path.with_name(
            f"{fallback_path.stem}_updated{fallback_path.suffix}"
        )
        _savefig_fixed_pdf_width(fig, fallback_filename, format="pdf", dpi=dpi)
        print(
            "WARNING: Could not overwrite locked PDF. "
            f"Wrote updated plot to: {fallback_filename}"
        )

    if show:
        plt.show()
    else:
        plt.close(fig)

    return tick_idx, tick_points


def plot_compare_dec_cen_pareto_tick_highlights_per100(
    *,
    decentralized_front,
    centralized_fronts_by_label,
    filename,
    figsize=(8, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    xlabel=r"Ann. GWP in kg CO$_2$-eq. per 100 m$^2$",
    ylabel=r"Ann. TOTEX in EUR per 100 m$^2$",
    cbar_label=r"Peak grid ex. power in kW per 100 m$^2$",
    target_xticks=8,
    exclude_last_tick_index=True,
    layout="side_by_side",
    dpi=600,
    show=False,
):
    """
    Decentralized vs centralized Pareto-front comparison.

    Use layout="side_by_side" for separate panels or layout="single_panel" to
    overlay all fronts in one axis. Scatter color is shared via one peak colorbar.
    """
    if layout not in {"side_by_side", "single_panel"}:
        raise ValueError("layout must be 'side_by_side' or 'single_panel'.")

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

    scenarios = [("Decentralized", decentralized_front)]
    scenarios.extend((label, front) for label, front in centralized_fronts_by_label.items())
    peak_values = np.concatenate([
        np.asarray([r["peak"] for r in front], dtype=float)
        for _, front in scenarios
        if front
    ])
    vmin = float(np.nanmin(peak_values))
    vmax = float(np.nanmax(peak_values))

    all_co2 = np.concatenate([
        np.asarray([r["co2"] for r in front], dtype=float)
        for _, front in scenarios
        if front
    ])
    all_totex = np.concatenate([
        np.asarray([r["totex"] for r in front], dtype=float)
        for _, front in scenarios
        if front
    ])

    def _padded_limits(values, pad_fraction=0.025):
        vmin_local = float(np.nanmin(values))
        vmax_local = float(np.nanmax(values))
        span = vmax_local - vmin_local
        if span <= 0:
            span = max(abs(vmin_local), 1.0)
        pad = span * pad_fraction
        return vmin_local - pad, vmax_local + pad

    xlim = _padded_limits(all_co2)
    ylim = _padded_limits(all_totex)

    if layout == "side_by_side":
        fig, axes = plt.subplots(
            ncols=2,
            figsize=figsize,
            gridspec_kw={"wspace": 0.36},
        )
        axes = list(axes)
    else:
        fig, ax = plt.subplots(figsize=figsize)
        axes = [ax]

    palette = sns.color_palette("colorblind", n_colors=8)
    dec_line_color = "#0072B2"
    cen_styles = {
        "t50": {
            "line_color": "#8C2D04",
            "marker": "s",
            "linestyle": ":",
            "display": "Centralized 50 degC flow temp.",
        },
        "t80": {
            "line_color": "#EF6548",
            "marker": "^",
            "linestyle": "--",
            "display": "Centralized 80 degC flow temp.",
        },
    }
    tick_color = palette[0]
    marker_handles = []
    line_handles = []
    mappable = None

    def _custom_tick_indices(n_points, mode):
        if n_points <= 0:
            return np.array([], dtype=int), []
        if mode == "centralized_t50":
            requested = [0, 20]
        elif mode == "centralized_t80":
            requested = [0, 20, n_points - 1]
        elif mode == "decentralized_low":
            return _build_pareto_tick_indices(
                n_points,
                target_ticks=target_xticks,
                include_last=True,
            )
        else:
            return _build_pareto_tick_indices(
                n_points,
                target_ticks=target_xticks,
                include_last=not exclude_last_tick_index,
            )
        idx = np.asarray(
            [i for i in dict.fromkeys(requested) if 0 <= i < n_points],
            dtype=int,
        )
        labels = [str(int(i)) for i in idx]
        return idx, labels

    def _add_marker_handle(label, marker):
        marker_handles.append(
            plt.Line2D(
                [0], [0],
                marker=marker,
                linestyle="None",
                markerfacecolor="none",
                markeredgecolor="black",
                color="black",
                markersize=5,
                label=label,
            )
        )

    def _add_line_handle(label, line_color, linestyle):
        line_handles.append(
            plt.Line2D(
                [0], [0],
                color=line_color,
                linestyle=linestyle,
                linewidth=1.0,
                label=label,
            )
        )

    def _plot_panel(
        ax,
        front,
        *,
        line_label,
        line_color,
        marker,
        linestyle,
        tick_mode,
        scatter_label=None,
    ):
        nonlocal mappable
        co2_all = np.asarray([r["co2"] for r in front], dtype=float)
        totex_all = np.asarray([r["totex"] for r in front], dtype=float)
        peak_all = np.asarray([r["peak"] for r in front], dtype=float)

        mappable = ax.scatter(
            co2_all,
            totex_all,
            c=peak_all,
            cmap="viridis",
            vmin=vmin,
            vmax=vmax,
            s=10,
            alpha=0.65,
            marker=marker,
            linewidths=0.0,
            zorder=1,
        )

        pareto_front = get_pareto_front(sorted(zip(co2_all, totex_all)))
        pf = sorted(pareto_front, key=lambda t: (t[0], t[1]))
        pf_co2 = np.asarray([t[0] for t in pf], dtype=float)
        pf_totex = np.asarray([t[1] for t in pf], dtype=float)
        tick_idx, tick_labels = _custom_tick_indices(len(pf), tick_mode)

        ax.plot(
            pf_co2,
            pf_totex,
            color=line_color,
            linestyle=linestyle,
            linewidth=1.0,
            zorder=4,
        )
        ax.scatter(
            pf_co2[tick_idx],
            pf_totex[tick_idx],
            s=24,
            color=tick_color,
            marker="o",
            edgecolors="white",
            linewidths=0.6,
            zorder=5,
        )

        tick_idx_list = [int(i) for i in tick_idx]
        keep_pos = list(range(0, len(tick_idx_list), 2))
        if tick_idx_list:
            keep_pos = sorted(set([0, len(tick_idx_list) - 1] + keep_pos))
        for pos in keep_pos:
            idx = tick_idx_list[pos]
            ax.annotate(
                str(tick_labels[pos]),
                (pf_co2[idx], pf_totex[idx]),
                textcoords="offset points",
                xytext=(3, 3),
                ha="left",
                va="bottom",
                fontsize=font_size,
                color=tick_color,
                bbox=dict(boxstyle="circle,pad=0.18", fc="white", ec=tick_color, lw=0.6),
                zorder=6,
            )

        if scatter_label:
            _add_marker_handle(scatter_label, marker)
        _add_line_handle(line_label, line_color, linestyle)

    dec_scatter_label = "Decentralized heat supply" if layout == "single_panel" else None
    _plot_panel(
        axes[0],
        decentralized_front,
        line_label="Decentralized Pareto-front",
        line_color=dec_line_color,
        marker="o",
        linestyle="-",
        tick_mode="decentralized_low",
        scatter_label=dec_scatter_label,
    )
    if layout == "side_by_side":
        axes[0].set_title("Decentralized heat supply", pad=6)

    for temp_label, front in centralized_fronts_by_label.items():
        style = cen_styles.get(
            temp_label,
            {
                "line_color": "#4D4D4D",
                "marker": "D",
                "linestyle": "-.",
                "display": f"Centralized {temp_label}",
            },
        )
        target_ax = axes[1] if layout == "side_by_side" else axes[0]
        _plot_panel(
            target_ax,
            front,
            line_label=f"{style['display']} Pareto-front",
            scatter_label=style["display"],
            line_color=style["line_color"],
            marker=style["marker"],
            linestyle=style["linestyle"],
            tick_mode=(
                "centralized_t50"
                if temp_label == "t50"
                else "centralized_t80"
                if temp_label == "t80"
                else "default"
            ),
        )
    if layout == "side_by_side":
        axes[1].set_title("Centralized heat supply", pad=6)
    else:
        axes[0].set_title("Low heat density heat supply comparison", pad=6)

    for ax in axes:
        ax.set_xlabel(xlabel)
        ax.set_ylabel(_linebreak_after_in_label(ylabel))
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        ax.grid(True, alpha=0.25, linewidth=0.6)

    index_handle = plt.Line2D(
        [0], [0],
        marker="o",
        linestyle="None",
        markerfacecolor=tick_color,
        markeredgecolor="white",
        color=tick_color,
        markersize=5,
        label="Pareto-optimal solution index",
    )
    legend_handles = marker_handles + line_handles + [index_handle]

    fig.legend(
        handles=legend_handles,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.990),
        ncol=4,
        columnspacing=1.0,
        handlelength=1.6,
        handletextpad=0.45,
    )

    cbar = fig.colorbar(mappable, ax=axes, pad=0.025, shrink=0.82)
    cbar.set_label(_linebreak_after_in_label(cbar_label), fontsize=font_size)
    _apply_integer_colorbar_ticks(cbar)
    cbar.ax.tick_params(labelsize=font_size)

    if layout == "side_by_side":
        fig.subplots_adjust(left=0.085, right=0.875, bottom=0.18, top=0.72, wspace=0.36)
    else:
        fig.subplots_adjust(left=0.12, right=0.865, bottom=0.18, top=0.72)
    _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)

    if show:
        plt.show()
    else:
        plt.close(fig)


def _wrap_per_100m2_linebreak(label: str) -> str:
    return _linebreak_after_in_label(label)


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
    tick_highlights_exclude_last_index=False,
    write_outputs=True,

):
    y_label_wrapped = _wrap_per_100m2_linebreak(y_label)
    cbar_label_wrapped = _wrap_per_100m2_linebreak(cbar_label)

    # 2D data for pareto extraction
    co2 = [r["co2"] for r in combined_front]
    cost = [r["totex"] for r in combined_front]
    peak = [r["peak"] for r in combined_front]
    data_2d = sorted(zip(co2, cost, peak), key=lambda t: (t[0], t[1]))

    # Pareto envelope in (co2, totex)
    pareto_front = get_pareto_front(data_2d)
    pareto_co2 = [pt[0] for pt in pareto_front]
    pareto_cost = [pt[1] for pt in pareto_front]

    # Your selection logic (unchanged)
    selected_points_y = select_evenly_spaced_pareto_points_focus_y_axis(pareto_front, num_points=12)
    selected_points_x = select_evenly_spaced_pareto_points_focus_x_axis(pareto_front, num_points=12)
    reduced_points = reduce_pareto_points(selected_points_y + selected_points_x)
    selected_co2 = [pt[0] for pt in reduced_points]
    selected_cost = [pt[1] for pt in reduced_points]

    # --- Plots ---
    # Export 3 height variants for the 3 main plots:
    # base (100%), h85 (-15%), h70 (-30%).
    height_variants = (
        ("", 1.00),
        ("_h85", 0.85),
        ("_h70", 0.70),
    )
    if write_outputs:
        for suffix, h_factor in height_variants:
            current_figsize = (width_inch, height_inch * h_factor)

            plot_all_pareto_points(
                combined_front,
                name=f"{out_prefix}_all_points{suffix}",
                figsize=current_figsize,
                font_size=font_size,
                filename=rf"{out_dir}\{out_prefix}_pareto_all_points{suffix}.pdf",
                xlabel=x_label,
                ylabel=y_label_wrapped,
                cbar_label=cbar_label_wrapped,
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
                ylabel=y_label_wrapped,
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
                ylabel=y_label_wrapped,
                cbar_label=cbar_label_wrapped,
                show=show,
            )

    tick_idx = None
    tick_points = None
    tick_highlight_height_variants = (
        ("_h80", 0.80),
        ("_h70", 0.70),
        ("_h60", 0.60),
        ("_h50", 0.50),
        ("_h40", 0.40),
    )
    tick_highlight_width_variants = (
        ("", 1.00),
        ("_w90", 0.90),
        ("_w80", 0.80),
        ("_w70", 0.70),
        ("_w60", 0.60),
    )
    pf_sorted = sorted(pareto_front, key=lambda t: (t[0], t[1]))
    if write_outputs:
        for suffix, h_factor in tick_highlight_height_variants:
            for width_suffix, width_factor in tick_highlight_width_variants:
                tick_idx, tick_points = plot_all_points_with_front_and_tick_highlights(
                    combined_front=combined_front,
                    pareto_front=pareto_front,  # list of (co2, totex) tuples
                    figsize=(width_inch, height_inch * h_factor),
                    font_size=font_size,
                    filename=rf"{out_dir}\{out_prefix}_pareto_all_with_front_tick_highlights{suffix}{width_suffix}.pdf",
                    xlabel=x_label,
                    ylabel=y_label_wrapped,
                    cbar_label=cbar_label_wrapped,
                    target_xticks=target_xticks,  # same idea as stackplot tick logic
                    exclude_last_tick_index=tick_highlights_exclude_last_index,
                    max_labels=12,
                    axes_width_scale=width_factor,
                )
    else:
        tick_idx, _ = _build_pareto_tick_indices(
            len(pf_sorted),
            target_ticks=target_xticks,
            include_last=not tick_highlights_exclude_last_index,
        )

    # convert tick indices to actual (co2, totex) points if you still need them:
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
        for optional_col in (
            "tabula_year_class",
            "heat_load_1",
            "heat_load_2",
            "heat_load_3",
        ):
            if optional_col in df.columns:
                rep_info[bid][optional_col] = row.get(optional_col)

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
    xlabel=r"Ann. CO$_2$-eq. in kg",
    ylabel=r"Totex in EUR",
    cbar_label=r"Peak grid ex. power in kW",
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
    heat_density_order = [
        "Low heat density",
        "Medium heat density",
        "High heat density",
    ]
    ordered_pareto_keys = [k for k in heat_density_order if k in pareto_sets]
    ordered_pareto_keys.extend(k for k in pareto_sets.keys() if k not in ordered_pareto_keys)

    fig, ax = plt.subplots(figsize=figsize)

    # use same colormap across all sets
    cmap = plt.get_cmap("viridis")

    for i, ueu_short in enumerate(ordered_pareto_keys):
        data = pareto_sets[ueu_short]
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
    ax.set_ylabel(str(ylabel).replace("Ann. TOTEX in ", "Ann. TOTEX in\n", 1))
    ax.grid(True, alpha=0.25, linewidth=0.6)

    # legend: only distinguishes UEUs (marker shape)
    ax.legend(frameon=False, loc="best")

    # shared colorbar for peak
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(_linebreak_after_in_label(cbar_label), fontsize=font_size)
    _apply_integer_colorbar_ticks(cbar)
    cbar.ax.tick_params(labelsize=font_size)

    fig.tight_layout()
    _savefig_fixed_pdf_width(fig, filename, format="pdf", dpi=dpi)
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
UEU_SHORT_ORDER = [
    "DENI03403000SEC4580",
    "DENI03403000SEC5658",
    "DENI03403000SEC5101",
]
RADAR_UEU_TITLES = {
    "Low heat density": "Low Heat Density UEU",
    "Medium heat density": "Medium Heat Density UEU",
    "High heat density": "High Heat Density UEU",
}


def _first_existing_path(candidates, fallback=None):
    for candidate in candidates:
        if candidate is None:
            continue
        candidate_path = Path(os.path.expandvars(os.path.expanduser(str(candidate))))
        if candidate_path.exists():
            return candidate_path
    return Path(fallback) if fallback is not None else None


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


def _finite_metric_record(record):
    try:
        values = {
            "totex": float(record["totex"]),
            "co2": float(record["co2"]),
            "peak": float(record["peak"]),
        }
    except (KeyError, TypeError, ValueError):
        return None
    if not all(np.isfinite(value) for value in values.values()):
        return None
    return values


def _metric_records_from_front(front, *, floor_area=None, households=None):
    divisor = (float(floor_area) / 100.0) if floor_area and floor_area > 0 else 1.0
    household_divisor = float(households) if households and households > 0 else None
    records = []
    for record in front:
        values = _finite_metric_record(record)
        if values is None:
            continue
        per_100m2_values = {key: value / divisor for key, value in values.items()}
        if household_divisor is not None:
            per_100m2_values["_per_household"] = {
                key: value / household_divisor for key, value in values.items()
            }
        per_100m2_values["_raw_abs"] = dict(values)
        records.append(per_100m2_values)
    return records


def _load_total_floor_area_for_ueu(optimization_root, ueu):
    try:
        import geopandas as gpd
        gpkg_path = _resolve_ueu_gpkg_path(optimization_root, ueu)
        gdf = gpd.read_file(gpkg_path)
    except Exception as exc:
        print(f"WARNING: Could not load floor area for {ueu}: {exc}. Using absolute radar values.")
        return None
    if "net_floor_area" not in gdf.columns:
        print(f"WARNING: net_floor_area missing in GPKG for {ueu}. Using absolute radar values.")
        return None
    floor_area = float(pd.to_numeric(gdf["net_floor_area"], errors="coerce").sum())
    return floor_area if np.isfinite(floor_area) and floor_area > 0 else None


def _household_count_from_list_like(value):
    if isinstance(value, (list, tuple, np.ndarray)):
        return len(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            inner = stripped[1:-1].strip()
            return 0 if inner == "" else inner.count(",") + 1
    try:
        parsed = pd.to_numeric(value, errors="coerce")
    except Exception:
        parsed = np.nan
    return float(parsed) if np.isfinite(parsed) else np.nan


def _load_total_households_for_ueu(optimization_root, ueu):
    try:
        import geopandas as gpd
        gpkg_path = _resolve_ueu_gpkg_path(optimization_root, ueu)
        gdf = gpd.read_file(gpkg_path)
    except Exception as exc:
        print(f"WARNING: Could not load household count for {ueu}: {exc}.")
        return None
    if "list_number_of_adults" in gdf.columns:
        household_counts = gdf["list_number_of_adults"].apply(_household_count_from_list_like)
    elif "number_of_apartments" in gdf.columns:
        household_counts = pd.to_numeric(gdf["number_of_apartments"], errors="coerce")
    else:
        print(
            f"WARNING: household columns missing in GPKG for {ueu}. "
            "Per-household radar values will be unavailable."
        )
        return None
    households = float(pd.to_numeric(household_counts, errors="coerce").sum())
    return households if np.isfinite(households) and households > 0 else None


def _pick_min_metric(records, metric):
    if not records:
        return None
    return min(records, key=lambda rec: rec[metric])


def _normalise_record(record, ranges):
    normalised = {}
    for metric in ranges:
        value = record[metric]
        lo, hi = ranges[metric]
        if not np.isfinite(lo) or not np.isfinite(hi) or np.isclose(lo, hi):
            normalised[metric] = 1.0
        else:
            normalised[metric] = (hi - value) / (hi - lo)
            normalised[metric] = float(np.clip(normalised[metric], 0.0, 1.0))
    return normalised


def _pick_balanced_record(records, ranges):
    if not records:
        return None
    scored = []
    for record in records:
        normalised = _normalise_record(record, ranges)
        scored.append((float(np.mean(list(normalised.values()))), record))
    return max(scored, key=lambda item: item[0])[1]


def _radar_close(values):
    values = list(values)
    return values + values[:1]


def _load_radar_fronts_for_ueu(
    *,
    ueu_short,
    optimization_root,
    decentralized_hypervolume_root,
    centralized_post_processed_root,
    centralized_combined_cluster,
    centralized_groups,
    no_electricity_grid_active,
    heat_grid_planning_overrides=None,
):
    ueu = f"processed_bds_in_{ueu_short}"
    floor_area = _load_total_floor_area_for_ueu(optimization_root, ueu)
    households = _load_total_households_for_ueu(optimization_root, ueu)

    dec_records = []
    try:
        dec_dir = _latest_decentralized_reference_front_dir(
            decentralized_hypervolume_root,
            ueu_short,
        )
        dec_front = load_combined_front_from_path(Path(dec_dir) / "combined_front.pkl")
        dec_front = maniupulate_combined_front_elect_grid(dec_front, no_electricity_grid_active)
        dec_records = _metric_records_from_front(
            dec_front,
            floor_area=floor_area,
            households=households,
        )
    except Exception as exc:
        print(f"WARNING: Could not load decentralized radar front for {ueu}: {exc}")

    cen_records = []
    for temperature_level, constraint_type in centralized_groups:
        cen_front_path = (
            Path(centralized_post_processed_root)
            / ueu
            / centralized_combined_cluster
            / temperature_level
            / constraint_type
            / "centralized_front.pkl"
        )
        if not os.path.exists(_to_windows_long_path(cen_front_path)):
            print(f"WARNING: Missing centralized radar front: {cen_front_path}")
            continue
        try:
            cen_front = load_combined_front_from_path(cen_front_path)
            cen_front = maniupulate_combined_front_elect_grid(cen_front, no_electricity_grid_active)
            cen_front = _apply_heat_grid_planning_override_to_front(
                cen_front,
                ueu_short=ueu_short,
                case_temperature_level=f"{temperature_level}_{constraint_type}",
                overrides=heat_grid_planning_overrides or {},
            )
            cen_records.extend(
                _metric_records_from_front(
                    cen_front,
                    floor_area=floor_area,
                    households=households,
                )
            )
        except Exception as exc:
            print(f"WARNING: Could not load centralized radar front {cen_front_path}: {exc}")

    return {
        "ueu_label": ueu_display(ueu_short),
        "ueu": ueu,
        "floor_area": floor_area,
        "households": households,
        "decentralized": dec_records,
        "centralized": cen_records,
    }


def _build_radar_rows(raw_by_ueu, *, scaling_mode):
    metrics = ("totex", "co2", "peak")
    metric_labels = {
        "totex": "Ann. TOTEX",
        "co2": "Ann. GWP",
        "peak": "Peak grid ex. power",
    }
    if scaling_mode == "global":
        all_records = [
            record
            for item in raw_by_ueu.values()
            for group in ("decentralized", "centralized")
            for record in item[group]
        ]
        global_ranges = {
            metric: (
                min(record[metric] for record in all_records),
                max(record[metric] for record in all_records),
            )
            for metric in metrics
        } if all_records else {metric: (0.0, 1.0) for metric in metrics}
    else:
        global_ranges = None

    rows_by_ueu = {}
    range_rows = []
    for ueu_label, item in raw_by_ueu.items():
        records_for_ranges = item["decentralized"] + item["centralized"]
        if not records_for_ranges:
            continue
        ranges = global_ranges if global_ranges is not None else {
            metric: (
                min(record[metric] for record in records_for_ranges),
                max(record[metric] for record in records_for_ranges),
            )
            for metric in metrics
        }
        for metric in metrics:
            range_rows.append({
                "scaling_mode": scaling_mode,
                "ueu_label": ueu_label,
                "metric": metric,
                "metric_label": metric_labels[metric],
                "raw_min": ranges[metric][0],
                "raw_max": ranges[metric][1],
                "unit": "per 100 m2" if item.get("floor_area") else "absolute",
            })

        entries = []
        for supply_key, supply_label in (
            ("decentralized", "Dec."),
            ("centralized", "Cen."),
        ):
            records = item[supply_key]
            if not records:
                continue
            selected = [
                (f"{supply_label} - min. ann. TOTEX", _pick_min_metric(records, "totex")),
                (f"{supply_label} - min. ann. GWP", _pick_min_metric(records, "co2")),
                (f"{supply_label} - min. peak grid ex. power", _pick_min_metric(records, "peak")),
            ]
            for label, record in selected:
                if record is None:
                    continue
                normalised = _normalise_record(record, ranges)
                entries.append({
                    "label": label,
                    "supply": supply_key,
                    "raw": record,
                    "normalised": normalised,
                })
        rows_by_ueu[ueu_label] = entries
    return rows_by_ueu, range_rows


def plot_dec_cen_ueu_radar_comparison(
    rows_by_ueu,
    *,
    filename,
    scaling_mode,
    figsize,
    font_size=9,
    font_family="TeX Gyre Termes",
    show=False,
):
    from matplotlib.lines import Line2D

    metrics = ("totex", "co2", "peak")
    axis_labels = ["Ann. TOTEX", "Ann. GWP", "Peak grid ex.\npower"]
    angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
    angles_closed = _radar_close(angles)
    objective_color_map = {
        "totex": "#0072B2",
        "co2": "#D55E00",
        "peak": "#009E73",
    }
    supply_style_map = {
        "decentralized": "-",
        "centralized": "--",
    }

    def _style_key(label):
        if "TOTEX" in label:
            return "totex"
        if "GWP" in label:
            return "co2"
        if "peak" in label.lower():
            return "peak"
        return "totex"

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

    ordered_ueus = [
        "Low heat density",
        "Medium heat density",
        "High heat density",
    ]
    fig, axes = plt.subplots(
        1,
        3,
        subplot_kw={"projection": "polar"},
        figsize=figsize,
    )
    for ax, ueu_label in zip(axes, ordered_ueus):
        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        ax.set_xticks(angles)
        ax.set_xticklabels(axis_labels)
        ax.set_ylim(0.0, 1.0)
        ax.set_yticks([0.0, 0.25, 0.50, 0.75, 1.0])
        ax.set_yticklabels(["0", "0.25", "0.50", "0.75", "1.00"], fontsize=max(font_size - 1, 6))
        ax.grid(True, alpha=0.28, linewidth=0.55)
        ax.spines["polar"].set_alpha(0.55)
        ax.set_title(RADAR_UEU_TITLES.get(ueu_label, ueu_label), pad=12)
        entries = rows_by_ueu.get(ueu_label, [])
        if not entries:
            ax.text(0.5, 0.5, "Missing data", transform=ax.transAxes, ha="center", va="center")
            continue
        for entry in entries:
            values = [entry["normalised"][metric] for metric in metrics]
            supply = entry["supply"]
            style_key = _style_key(entry["label"])
            ax.plot(
                angles_closed,
                _radar_close(values),
                color=objective_color_map[style_key],
                linestyle=supply_style_map[supply],
                linewidth=1.15,
                alpha=0.88,
            )

    heat_supply_handles = [
        Line2D(
            [0],
            [0],
            color="black",
            lw=1.5,
            linestyle=supply_style_map["decentralized"],
            label="Decentralized",
        ),
        Line2D(
            [0],
            [0],
            color="black",
            lw=1.5,
            linestyle=supply_style_map["centralized"],
            label="Centralized",
        ),
    ]
    objective_handles = [
        Line2D([0], [0], color=objective_color_map["totex"], lw=1.5, label="Min. ann. TOTEX"),
        Line2D([0], [0], color=objective_color_map["co2"], lw=1.5, label="Min. ann. GWP"),
        Line2D([0], [0], color=objective_color_map["peak"], lw=1.5, label="Min. peak grid ex. power"),
    ]
    fig.legend(
        handles=heat_supply_handles,
        loc="upper center",
        bbox_to_anchor=(0.25, 0.965),
        ncol=1,
        frameon=False,
        title="Heat supply configuration",
        title_fontsize=font_size,
        handlelength=2.0,
        handletextpad=0.5,
    )
    fig.legend(
        handles=objective_handles,
        loc="upper center",
        bbox_to_anchor=(0.68, 0.965),
        ncol=1,
        frameon=False,
        title="Objective-specific solution",
        title_fontsize=font_size,
        handlelength=2.0,
        handletextpad=0.5,
    )
    fig.text(
        0.5,
        0.745,
        "Performance score after per-100 m² normalization and global min-max scaling (0 = worst, 1 = best)",
        ha="center",
        va="center",
        fontsize=max(font_size - 1, 6),
    )
    fig.subplots_adjust(left=0.04, right=0.98, bottom=0.08, top=0.72, wspace=0.36)
    _savefig_fixed_pdf_width(fig, filename, dpi=600, format="pdf")
    if show:
        plt.show()
    plt.close(fig)


RADAR_SOLUTION_ORDER = [
    ("decentralized", "totex", "Dec. - min. ann. TOTEX"),
    ("decentralized", "co2", "Dec. - min. ann. GWP"),
    ("decentralized", "peak", "Dec. - min. peak grid ex. power"),
    ("centralized", "totex", "Cen. - min. ann. TOTEX"),
    ("centralized", "co2", "Cen. - min. ann. GWP"),
    ("centralized", "peak", "Cen. - min. peak grid ex. power"),
]


def _radar_entry_objective(entry):
    label = str(entry.get("label", "")).lower()
    if "totex" in label:
        return "totex"
    if "gwp" in label:
        return "co2"
    if "peak" in label:
        return "peak"
    return ""


def _radar_entry_lookup(entries):
    lookup = {}
    for entry in entries:
        lookup[(entry.get("supply"), _radar_entry_objective(entry))] = entry
    return lookup


RADAR_ORDERED_UEUS = ["Low heat density", "Medium heat density", "High heat density"]
RADAR_METRICS = ("totex", "co2", "peak")
RADAR_METRIC_LABELS = {
    "totex": "Ann. TOTEX",
    "co2": "Ann. GWP",
    "peak": "Peak grid ex. power",
}
RADAR_OBJECTIVE_LABELS = {
    "totex": "min. ann. TOTEX",
    "co2": "min. ann. GWP",
    "peak": "min. peak grid ex. power",
}
RADAR_SUPPLY_LABELS = {
    "decentralized": "Dec.",
    "centralized": "Cen.",
}
RADAR_OBJECTIVE_COLORS = {
    "totex": "#0072B2",
    "co2": "#D55E00",
    "peak": "#009E73",
}
HEIGHT_CASE = "h90"


def build_dec_cen_heat_supply_performance_dataframe(
    rows_by_ueu,
    range_rows,
    *,
    scaling_mode,
    height_case,
):
    lookup_by_ueu = {
        ueu_label: _radar_entry_lookup(rows_by_ueu.get(ueu_label, []))
        for ueu_label in RADAR_ORDERED_UEUS
    }
    records = []
    for ueu_label in RADAR_ORDERED_UEUS:
        for supply_key, objective_key, solution_label in RADAR_SOLUTION_ORDER:
            entry = lookup_by_ueu.get(ueu_label, {}).get((supply_key, objective_key))
            if entry is None:
                raise ValueError(
                    "Missing heat-supply comparison solution: "
                    f"UEU={ueu_label}, supply={supply_key}, objective={objective_key}"
                )
            raw_abs = entry["raw"].get("_raw_abs", {})
            per_household = entry["raw"].get("_per_household", {})
            for metric in RADAR_METRICS:
                records.append(
                    {
                        "height_case": height_case,
                        "scaling_mode": scaling_mode,
                        "ueu_type": ueu_label,
                        "ueu_title": RADAR_UEU_TITLES.get(ueu_label, ueu_label),
                        "supply_configuration": supply_key,
                        "supply_label": RADAR_SUPPLY_LABELS[supply_key],
                        "selected_objective": objective_key,
                        "selected_objective_label": RADAR_OBJECTIVE_LABELS[objective_key],
                        "solution_label": solution_label,
                        "kpi": metric,
                        "kpi_label": RADAR_METRIC_LABELS[metric],
                        "raw_value": float(raw_abs.get(metric, np.nan)),
                        "value_per_100m2": float(entry["raw"][metric]),
                        "value_per_household": float(per_household.get(metric, np.nan)),
                        "performance_score": float(entry["normalised"][metric]),
                    }
                )

    df = pd.DataFrame.from_records(records)
    validate_dec_cen_heat_supply_performance_dataframe(
        df,
        range_rows,
        scaling_mode=scaling_mode,
        height_case=height_case,
    )
    return df


def validate_dec_cen_heat_supply_performance_dataframe(
    df,
    range_rows,
    *,
    scaling_mode,
    height_case,
):
    expected_ueus = set(RADAR_ORDERED_UEUS)
    expected_supplies = set(RADAR_SUPPLY_LABELS)
    expected_objectives = {objective for _supply, objective, _label in RADAR_SOLUTION_ORDER}
    expected_metrics = set(RADAR_METRICS)

    present_ueus = set(df["ueu_type"].unique())
    if present_ueus != expected_ueus:
        raise ValueError(f"Unexpected UEU set for {height_case}: {sorted(present_ueus)}")
    present_supplies = set(df["supply_configuration"].unique())
    if present_supplies != expected_supplies:
        raise ValueError(f"Unexpected supply set for {height_case}: {sorted(present_supplies)}")
    present_objectives = set(df["selected_objective"].unique())
    if present_objectives != expected_objectives:
        raise ValueError(f"Unexpected objective set for {height_case}: {sorted(present_objectives)}")
    present_metrics = set(df["kpi"].unique())
    if present_metrics != expected_metrics:
        raise ValueError(f"Unexpected KPI set for {height_case}: {sorted(present_metrics)}")

    expected_rows = (
        len(expected_ueus)
        * len(expected_supplies)
        * len(expected_objectives)
        * len(expected_metrics)
    )
    if len(df) != expected_rows:
        raise ValueError(f"Expected {expected_rows} performance rows, got {len(df)}.")
    if df["performance_score"].isna().any():
        raise ValueError("Performance dataframe contains NaN scores.")
    if not df["performance_score"].between(0.0, 1.0).all():
        bad = df.loc[~df["performance_score"].between(0.0, 1.0)]
        raise ValueError(f"Performance scores outside [0, 1]:\n{bad}")

    ranges_df = pd.DataFrame(range_rows)
    ranges_df = ranges_df.loc[ranges_df["scaling_mode"] == scaling_mode].copy()
    for metric in RADAR_METRICS:
        metric_ranges = ranges_df.loc[ranges_df["metric"] == metric, ["raw_min", "raw_max"]]
        if metric_ranges.empty:
            raise ValueError(f"Missing global range for metric {metric}.")
        rounded = {
            (round(float(row.raw_min), 10), round(float(row.raw_max), 10))
            for row in metric_ranges.itertuples()
        }
        if len(rounded) != 1:
            raise ValueError(f"Global min-max range is not identical for {metric}: {rounded}")

        lo, hi = next(iter(rounded))
        values = df.loc[df["kpi"] == metric, "value_per_100m2"]
        if values.min() < lo - 1e-7 or values.max() > hi + 1e-7:
            raise ValueError(
                f"Metric {metric} values fall outside recorded global range: "
                f"values=({values.min()}, {values.max()}), range=({lo}, {hi})"
            )


def _xlsx_column_name(index):
    name = ""
    index = int(index)
    while index >= 0:
        index, remainder = divmod(index, 26)
        name = chr(ord("A") + remainder) + name
        index -= 1
    return name


def _xlsx_cell_xml(row_idx, col_idx, value):
    import html

    cell_ref = f"{_xlsx_column_name(col_idx)}{row_idx + 1}"
    if value is None:
        return f'<c r="{cell_ref}"/>'
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return f'<c r="{cell_ref}"><v>{int(value)}</v></c>'
    if isinstance(value, (np.floating, float)):
        value = float(value)
        if np.isfinite(value):
            return f'<c r="{cell_ref}"><v>{value:.15g}</v></c>'
        return f'<c r="{cell_ref}"/>'
    escaped = html.escape(str(value), quote=True)
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'


def _write_simple_xlsx_workbook(path, sheets):
    import html

    path = Path(path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
"""
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
                for i, _sheet in enumerate(sheets, start=1)
            )
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        workbook_sheets = []
        workbook_rels = []
        for i, sheet in enumerate(sheets, start=1):
            sheet_name = html.escape(str(sheet["name"])[:31], quote=True)
            workbook_sheets.append(
                f'<sheet name="{sheet_name}" sheetId="{i}" r:id="rId{i}"/>'
            )
            workbook_rels.append(
                f'<Relationship Id="rId{i}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{i}.xml"/>'
            )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>"""
            + "".join(workbook_sheets)
            + "</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">"""
            + "".join(workbook_rels)
            + "</Relationships>",
        )

        for i, sheet in enumerate(sheets, start=1):
            rows_xml = []
            for row_idx, row in enumerate(sheet["rows"]):
                cells = "".join(
                    _xlsx_cell_xml(row_idx, col_idx, value)
                    for col_idx, value in enumerate(row)
                )
                rows_xml.append(f'<row r="{row_idx + 1}">{cells}</row>')
            archive.writestr(
                f"xl/worksheets/sheet{i}.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>"""
                + "".join(rows_xml)
                + "</sheetData></worksheet>",
            )


def _heat_supply_tradeoff_reference(value, *, label):
    value = float(value)
    if not np.isfinite(value) or np.isclose(value, 0.0):
        raise ValueError(
            "Cannot calculate heat-supply trade-off percentage because "
            f"the reference value for {label} is zero or non-finite: {value}"
        )
    return value


def build_dec_cen_objective_extreme_tradeoff_tables(performance_df):
    value_lookup = {
        (row.ueu_type, row.supply_configuration, row.selected_objective, row.kpi): float(
            row.value_per_100m2
        )
        for row in performance_df.itertuples()
    }

    objective_labels = {
        "totex": "Annual TOTEX optimum",
        "co2": "Annual GWP optimum",
        "peak": "Peak-grid-exchange optimum",
    }
    heat_supply_labels = {
        "decentralized": "Decentralized",
        "centralized": "Centralized",
    }

    absolute_rows = []
    summary_rows = []
    for ueu_label in RADAR_ORDERED_UEUS:
        for supply_key in ("decentralized", "centralized"):
            rows_by_objective = {}
            for objective_key in ("totex", "co2", "peak"):
                try:
                    metrics = {
                        metric: value_lookup[(ueu_label, supply_key, objective_key, metric)]
                        for metric in RADAR_METRICS
                    }
                except KeyError as exc:
                    raise ValueError(
                        "Missing exact heat-supply small-multiples selected value for "
                        f"UEU={ueu_label}, supply={supply_key}, objective={objective_key}: {exc}"
                    ) from exc
                rows_by_objective[objective_key] = metrics
                absolute_rows.append(
                    {
                        "UEU": ueu_label,
                        "Heat supply": heat_supply_labels[supply_key],
                        "Minimized objective": objective_labels[objective_key],
                        "Annual TOTEX [EUR per 100 m2]": metrics["totex"],
                        "Annual GWP [kg CO2-eq. per 100 m2]": metrics["co2"],
                        "Peak grid exchange [kW per 100 m2]": metrics["peak"],
                    }
                )

            ref = rows_by_objective["totex"]
            gwp_ref = _heat_supply_tradeoff_reference(
                ref["co2"],
                label=f"{ueu_label} / {heat_supply_labels[supply_key]} / GWP at TOTEX optimum",
            )
            peak_ref = _heat_supply_tradeoff_reference(
                ref["peak"],
                label=f"{ueu_label} / {heat_supply_labels[supply_key]} / peak at TOTEX optimum",
            )
            totex_ref = _heat_supply_tradeoff_reference(
                ref["totex"],
                label=f"{ueu_label} / {heat_supply_labels[supply_key]} / TOTEX optimum",
            )
            summary_rows.append(
                {
                    "UEU": ueu_label,
                    "Heat supply": heat_supply_labels[supply_key],
                    "GWP reduction vs TOTEX optimum [%]": (
                        100.0 * (gwp_ref - rows_by_objective["co2"]["co2"]) / gwp_ref
                    ),
                    "Additional TOTEX for GWP optimum [%]": (
                        100.0 * (rows_by_objective["co2"]["totex"] - totex_ref) / totex_ref
                    ),
                    "Peak reduction vs TOTEX optimum [%]": (
                        100.0 * (peak_ref - rows_by_objective["peak"]["peak"]) / peak_ref
                    ),
                    "Additional TOTEX for peak optimum [%]": (
                        100.0 * (rows_by_objective["peak"]["totex"] - totex_ref) / totex_ref
                    ),
                }
            )

    summary_df = pd.DataFrame(summary_rows)
    absolute_df = pd.DataFrame(absolute_rows)
    if len(summary_df) != 6:
        raise ValueError(f"Expected 6 trade-off summary rows, got {len(summary_df)}.")
    if len(absolute_df) != 18:
        raise ValueError(f"Expected 18 absolute-value rows, got {len(absolute_df)}.")
    return summary_df, absolute_df


def write_dec_cen_objective_extreme_tradeoff_workbook(performance_df, filename):
    summary_df, absolute_df = build_dec_cen_objective_extreme_tradeoff_tables(performance_df)
    _write_simple_xlsx_workbook(
        filename,
        [
            {
                "name": "Tradeoff_summary",
                "rows": [list(summary_df.columns)] + summary_df.values.tolist(),
            },
            {
                "name": "Absolute_values",
                "rows": [list(absolute_df.columns)] + absolute_df.values.tolist(),
            },
        ],
    )
    return summary_df, absolute_df


def export_dec_cen_objective_extreme_tradeoff_workbook(
    *,
    optimization_root,
    decentralized_hypervolume_root,
    centralized_post_processed_root,
    out_dir,
    centralized_combined_cluster,
    no_electricity_grid_active,
    heat_grid_planning_overrides=None,
    filename=None,
):
    centralized_groups = (
        ("t50", "cmin"),
        ("t80", "cmin"),
        ("t80", "cmax"),
    )
    raw_by_ueu = {}
    for ueu_short in UEU_SHORT_ORDER:
        item = _load_radar_fronts_for_ueu(
            ueu_short=ueu_short,
            optimization_root=optimization_root,
            decentralized_hypervolume_root=decentralized_hypervolume_root,
            centralized_post_processed_root=centralized_post_processed_root,
            centralized_combined_cluster=centralized_combined_cluster,
            centralized_groups=centralized_groups,
            no_electricity_grid_active=no_electricity_grid_active,
            heat_grid_planning_overrides=heat_grid_planning_overrides,
        )
        raw_by_ueu[item["ueu_label"]] = item

    rows_by_ueu, range_rows = _build_radar_rows(raw_by_ueu, scaling_mode="global")
    performance_df = build_dec_cen_heat_supply_performance_dataframe(
        rows_by_ueu,
        range_rows,
        scaling_mode="global",
        height_case="h80",
    )
    validate_dec_cen_heat_supply_performance_dataframe(
        performance_df,
        range_rows,
        scaling_mode="global",
        height_case="h80",
    )
    if filename is None:
        filename = Path(out_dir) / "6_compare_dec_cen_objective_extreme_tradeoffs.xlsx"
    summary_df, absolute_df = write_dec_cen_objective_extreme_tradeoff_workbook(
        performance_df,
        filename,
    )
    return Path(filename), summary_df, absolute_df


HEAT_SUPPLY_PROJECTION_PAIRS = (
    ("totex", "co2"),
    ("totex", "peak"),
    ("co2", "peak"),
)
HEAT_SUPPLY_PROJECTION_AXIS_LABELS = {
    "totex": r"Annual TOTEX" + "\n" + r"in EUR per 100 m$^2$",
    "co2": r"Annual GWP" + "\n" + r"in kg CO$_2$-eq. per 100 m$^2$",
    "peak": r"Peak grid exchange power" + "\n" + r"in kW per 100 m$^2$",
}
HEAT_SUPPLY_PROJECTION_COLORS = {
    "Low heat density": "#0072B2",
    "Medium heat density": "#009E73",
    "High heat density": "#D55E00",
}
HEAT_SUPPLY_PROJECTION_LINESTYLES = {
    "decentralized": "-",
    "centralized": "--",
}
HEAT_SUPPLY_PROJECTION_SUPPLY_LABELS = {
    "decentralized": "Decentralized",
    "centralized": "Centralized",
}
HEAT_SUPPLY_PROJECTION_MARKERS = {
    "decentralized": "s",
    "centralized": "o",
}
HEAT_SUPPLY_PROJECTION_VARIANTS = {
    "balanced": {
        "filename_suffix": "",
        "line_width": 1.65,
        "alpha": 0.94,
        "markers": {"decentralized": None, "centralized": "o"},
        "marker_size": 3.1,
        "markevery": 3,
        "break_projected_verticals": False,
        "centralized_points_only": False,
    },
    "both_markers": {
        "filename_suffix": "_both_markers",
        "line_width": 1.75,
        "alpha": 0.94,
        "markers": HEAT_SUPPLY_PROJECTION_MARKERS,
        "marker_size": 3.0,
        "markevery": 3,
        "break_projected_verticals": False,
        "centralized_points_only": False,
    },
    "break_verticals": {
        "filename_suffix": "_break_verticals",
        "line_width": 1.70,
        "alpha": 0.94,
        "markers": HEAT_SUPPLY_PROJECTION_MARKERS,
        "marker_size": 3.0,
        "markevery": 3,
        "break_projected_verticals": True,
        "centralized_points_only": False,
    },
    "centralized_points": {
        "filename_suffix": "_centralized_points",
        "line_width": 1.55,
        "centralized_line_width": 0.75,
        "alpha": 0.92,
        "centralized_alpha": 0.45,
        "markers": {"decentralized": "s", "centralized": "o"},
        "marker_size": 3.4,
        "markevery": 1,
        "break_projected_verticals": True,
        "centralized_points_only": True,
    },
}


def _pareto_front_2d_values(points, eps=1e-12):
    points = np.asarray(points, dtype=float)
    if points.size == 0:
        return np.empty((0, 2), dtype=float)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError(f"Expected 2D point array with shape (n, 2), got {points.shape}.")
    points = points[np.all(np.isfinite(points), axis=1)]
    if len(points) == 0:
        return np.empty((0, 2), dtype=float)

    order = np.lexsort((points[:, 1], points[:, 0]))
    points = points[order]
    front = []
    best_y = np.inf
    for x_val, y_val in points:
        if y_val < best_y - eps:
            front.append((float(x_val), float(y_val)))
            best_y = float(y_val)
    return np.asarray(front, dtype=float) if front else np.empty((0, 2), dtype=float)


def _pareto_front_2d_from_metric_records(records, x_metric, y_metric):
    points = []
    for record in records:
        try:
            point = (float(record[x_metric]), float(record[y_metric]))
        except (KeyError, TypeError, ValueError):
            continue
        if np.all(np.isfinite(point)):
            points.append(point)
    return _pareto_front_2d_values(points)


def _break_near_vertical_projection_segments(front, relative_dx_threshold=0.015):
    front = np.asarray(front, dtype=float)
    if len(front) < 2:
        return front

    x_range = float(np.nanmax(front[:, 0]) - np.nanmin(front[:, 0]))
    y_range = float(np.nanmax(front[:, 1]) - np.nanmin(front[:, 1]))
    if x_range <= 0 or y_range <= 0:
        return front

    max_dx = x_range * float(relative_dx_threshold)
    min_dy = y_range * 0.08
    broken = [front[0]]
    for prev_point, next_point in zip(front[:-1], front[1:]):
        dx = abs(float(next_point[0] - prev_point[0]))
        dy = abs(float(next_point[1] - prev_point[1]))
        if dx <= max_dx and dy >= min_dy:
            broken.append((np.nan, np.nan))
        broken.append(next_point)
    return np.asarray(broken, dtype=float)


def plot_dec_cen_heat_supply_projection_front_lines(
    raw_by_ueu,
    *,
    filename,
    figsize,
    font_size=9,
    font_family="TeX Gyre Termes",
    variant="balanced",
    show=False,
):
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter

    if variant not in HEAT_SUPPLY_PROJECTION_VARIANTS:
        raise ValueError(
            f"Unknown heat-supply projection variant '{variant}'. "
            f"Use one of: {', '.join(HEAT_SUPPLY_PROJECTION_VARIANTS)}"
        )
    variant_style = HEAT_SUPPLY_PROJECTION_VARIANTS[variant]

    set_journal_style(font_family=font_family, font_size=font_size)
    plt.rcParams.update({
        "axes.labelsize": max(font_size - 1, 7),
        "xtick.labelsize": max(font_size - 1, 7),
        "ytick.labelsize": max(font_size - 1, 7),
        "legend.fontsize": max(font_size - 1, 7),
    })

    front_lookup = {}
    panel_values = {pair: [] for pair in HEAT_SUPPLY_PROJECTION_PAIRS}
    for ueu_label in RADAR_ORDERED_UEUS:
        item = raw_by_ueu.get(ueu_label)
        if item is None:
            continue
        for supply_key in ("decentralized", "centralized"):
            records = item.get(supply_key, [])
            for pair in HEAT_SUPPLY_PROJECTION_PAIRS:
                front = _pareto_front_2d_from_metric_records(records, *pair)
                front_lookup[(ueu_label, supply_key, pair)] = front
                if len(front):
                    panel_values[pair].append(front)

    def _finite_minmax(arrays, axis_index):
        values = [
            float(value)
            for array in arrays
            for value in np.asarray(array, dtype=float)[:, axis_index]
            if np.isfinite(value)
        ]
        if not values:
            return 0.0, 1.0
        return min(values), max(values)

    def _pad_limits(vmin, vmax):
        if np.isclose(vmin, vmax):
            pad = 1.0 if np.isclose(vmin, 0.0) else abs(vmin) * 0.08
        else:
            pad = (vmax - vmin) * 0.06
        return vmin - pad, vmax + pad

    def _fmt_tick(value, pos=None):
        value = float(value)
        if abs(value) >= 100:
            return f"{value:.0f}"
        if abs(value) >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"

    fig, axes = plt.subplots(
        ncols=3,
        figsize=figsize,
        gridspec_kw={"wspace": 0.62},
    )
    tick_formatter = FuncFormatter(_fmt_tick)
    for ax, pair in zip(axes, HEAT_SUPPLY_PROJECTION_PAIRS):
        x_metric, y_metric = pair
        for ueu_label in RADAR_ORDERED_UEUS:
            for supply_key in ("decentralized", "centralized"):
                front = front_lookup.get((ueu_label, supply_key, pair), np.empty((0, 2)))
                if len(front) == 0:
                    continue
                color = HEAT_SUPPLY_PROJECTION_COLORS.get(ueu_label, "#4D4D4D")
                plot_front = (
                    _break_near_vertical_projection_segments(front)
                    if variant_style["break_projected_verticals"]
                    else front
                )
                marker = variant_style["markers"].get(supply_key)
                linewidth = float(
                    variant_style.get(f"{supply_key}_line_width", variant_style["line_width"])
                )
                alpha = float(
                    variant_style.get(f"{supply_key}_alpha", variant_style["alpha"])
                )
                ax.plot(
                    plot_front[:, 0],
                    plot_front[:, 1],
                    color=color,
                    linestyle=HEAT_SUPPLY_PROJECTION_LINESTYLES[supply_key],
                    linewidth=linewidth,
                    alpha=alpha,
                    marker=marker,
                    markersize=float(variant_style["marker_size"]) if marker else 0,
                    markevery=int(variant_style["markevery"]) if marker else None,
                    markerfacecolor="white" if marker else None,
                    markeredgewidth=0.65 if marker else None,
                    zorder=2,
                )
                if (
                    supply_key == "centralized"
                    and variant_style["centralized_points_only"]
                ):
                    ax.scatter(
                        front[:, 0],
                        front[:, 1],
                        s=float(variant_style["marker_size"]) ** 2.0 * 2.2,
                        marker=HEAT_SUPPLY_PROJECTION_MARKERS["centralized"],
                        facecolors="white",
                        edgecolors=color,
                        linewidths=0.75,
                        alpha=0.96,
                        zorder=3,
                    )
        x_min, x_max = _finite_minmax(panel_values[pair], 0)
        y_min, y_max = _finite_minmax(panel_values[pair], 1)
        ax.set_xlim(*_pad_limits(x_min, x_max))
        ax.set_ylim(*_pad_limits(y_min, y_max))
        ax.xaxis.set_major_formatter(tick_formatter)
        ax.yaxis.set_major_formatter(tick_formatter)
        ax.set_xlabel(HEAT_SUPPLY_PROJECTION_AXIS_LABELS[x_metric])
        ax.set_ylabel(HEAT_SUPPLY_PROJECTION_AXIS_LABELS[y_metric])
        ax.grid(True, alpha=0.28, linewidth=0.6)
        ax.tick_params(axis="both", which="major", pad=1.5)

    ueu_handles = [
        Line2D(
            [0],
            [0],
            color=HEAT_SUPPLY_PROJECTION_COLORS[ueu_label],
            linewidth=1.7,
            label=ueu_label,
        )
        for ueu_label in RADAR_ORDERED_UEUS
    ]
    supply_handles = [
        Line2D(
            [0],
            [0],
            color="black",
            linestyle=HEAT_SUPPLY_PROJECTION_LINESTYLES[supply_key],
            linewidth=float(
                variant_style.get(f"{supply_key}_line_width", variant_style["line_width"])
            ),
            marker=variant_style["markers"].get(supply_key),
            markersize=float(variant_style["marker_size"]),
            markerfacecolor="white",
            markeredgewidth=0.65,
            label=supply_label,
        )
        for supply_key, supply_label in HEAT_SUPPLY_PROJECTION_SUPPLY_LABELS.items()
    ]
    fig.legend(
        handles=ueu_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.985),
        ncol=3,
        frameon=False,
        handlelength=1.45,
        columnspacing=0.95,
        handletextpad=0.45,
    )
    fig.legend(
        handles=supply_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.900),
        ncol=2,
        frameon=False,
        handlelength=1.90,
        columnspacing=1.25,
        handletextpad=0.50,
    )
    fig.subplots_adjust(left=0.125, right=0.990, bottom=0.235, top=0.755, wspace=0.62)
    try:
        _savefig_fixed_pdf_width(fig, filename, dpi=600, format="pdf")
    except PermissionError:
        fallback_path = Path(filename)
        fallback_filename = fallback_path.with_name(
            f"{fallback_path.stem}_updated{fallback_path.suffix}"
        )
        _savefig_fixed_pdf_width(fig, fallback_filename, dpi=600, format="pdf")
        print(
            "WARNING: Could not overwrite locked heat-supply projection PDF. "
            f"Wrote updated plot to: {fallback_filename}"
        )
    if show:
        plt.show()
    else:
        plt.close(fig)


def export_dec_cen_heat_supply_projection_front_line_plots(
    *,
    optimization_root,
    decentralized_hypervolume_root,
    centralized_post_processed_root,
    out_dir,
    centralized_combined_cluster,
    no_electricity_grid_active,
    width_inch,
    height_inch,
    font_size,
    heat_grid_planning_overrides=None,
    height_variants=(
        ("h100", 1.00),
        ("h90", 0.90),
        ("h80", 0.80),
        ("h70", 0.70),
        ("h60", 0.60),
    ),
    plot_variants=(
        "balanced",
        "both_markers",
        "break_verticals",
        "centralized_points",
    ),
):
    centralized_groups = (
        ("t50", "cmin"),
        ("t80", "cmin"),
        ("t80", "cmax"),
    )
    raw_by_ueu = {}
    for ueu_short in UEU_SHORT_ORDER:
        item = _load_radar_fronts_for_ueu(
            ueu_short=ueu_short,
            optimization_root=optimization_root,
            decentralized_hypervolume_root=decentralized_hypervolume_root,
            centralized_post_processed_root=centralized_post_processed_root,
            centralized_combined_cluster=centralized_combined_cluster,
            centralized_groups=centralized_groups,
            no_electricity_grid_active=no_electricity_grid_active,
            heat_grid_planning_overrides=heat_grid_planning_overrides,
        )
        raw_by_ueu[item["ueu_label"]] = item

    output_paths = []
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for height_suffix, height_scale in height_variants:
        for plot_variant in plot_variants:
            variant_suffix = HEAT_SUPPLY_PROJECTION_VARIANTS[plot_variant]["filename_suffix"]
            output_path = (
                Path(out_dir)
                / (
                    "6_COMPARE_dec_cen_heat_supply_pareto_front_projection_lines_global_"
                    f"{height_suffix}{variant_suffix}.pdf"
                )
            )
            plot_dec_cen_heat_supply_projection_front_lines(
                raw_by_ueu,
                filename=output_path,
                figsize=(width_inch, height_inch * 1.08 * float(height_scale)),
                font_size=font_size,
                variant=plot_variant,
                show=False,
            )
            print(
                "Heat-supply Pareto projection line plot written "
                f"({plot_variant}): {output_path}"
            )
            output_paths.append(output_path)
    return output_paths


def print_dec_cen_heat_supply_performance_validation(df, range_rows, *, height_case):
    print(f"\n=== Heat-supply performance validation ({height_case}) ===")
    ranges_df = pd.DataFrame(range_rows)
    ranges_df = ranges_df.drop_duplicates(["scaling_mode", "metric", "raw_min", "raw_max"])
    print("Global min-max ranges used for performance score:")
    for row in ranges_df.itertuples():
        print(
            f"  {row.scaling_mode} | {row.metric}: "
            f"min={float(row.raw_min):.6g}, max={float(row.raw_max):.6g}, unit={row.unit}"
        )
    columns = [
        "ueu_type",
        "supply_label",
        "selected_objective_label",
        "kpi_label",
        "raw_value",
        "value_per_100m2",
        "performance_score",
    ]
    with pd.option_context(
        "display.max_rows",
        None,
        "display.max_columns",
        None,
        "display.width",
        220,
    ):
        print(df[columns].to_string(index=False, float_format=lambda value: f"{value:.6g}"))


def _radar_matrix_for_entries(entries):
    metrics = ("totex", "co2", "peak")
    lookup = _radar_entry_lookup(entries)
    matrix = np.full((len(RADAR_SOLUTION_ORDER), len(metrics)), np.nan, dtype=float)
    for row_idx, (supply, objective, _label) in enumerate(RADAR_SOLUTION_ORDER):
        entry = lookup.get((supply, objective))
        if entry is None:
            continue
        for col_idx, metric in enumerate(metrics):
            matrix[row_idx, col_idx] = float(entry["normalised"][metric])
    return matrix


def plot_dec_cen_ueu_heatmap_comparison(
    rows_by_ueu,
    *,
    filename,
    scaling_mode,
    figsize,
    font_size=9,
    font_family="TeX Gyre Termes",
    show=False,
):
    ordered_ueus = ["Low heat density", "Medium heat density", "High heat density"]
    metric_labels = ["Ann. TOTEX", "Ann. GWP", "Peak grid\nex. power"]
    row_labels = [label.replace(" - ", "\n") for _, _, label in RADAR_SOLUTION_ORDER]
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.titlesize": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": max(font_size - 1, 6),
        "ytick.labelsize": max(font_size - 1, 6),
        "mathtext.fontset": "cm",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    fig, axes = plt.subplots(1, 3, figsize=figsize, sharey=True)
    image = None
    for ax_idx, (ax, ueu_label) in enumerate(zip(axes, ordered_ueus)):
        matrix = _radar_matrix_for_entries(rows_by_ueu.get(ueu_label, []))
        image = ax.imshow(matrix, cmap="viridis", vmin=0.0, vmax=1.0, aspect="auto")
        ax.set_title(RADAR_UEU_TITLES.get(ueu_label, ueu_label), pad=6)
        ax.set_xticks(np.arange(len(metric_labels)))
        ax.set_xticklabels(metric_labels)
        ax.set_yticks(np.arange(len(row_labels)))
        if ax_idx == 0:
            ax.set_yticklabels(row_labels)
        else:
            ax.tick_params(axis="y", labelleft=False)
        ax.set_xticks(np.arange(-0.5, len(metric_labels), 1), minor=True)
        ax.set_yticks(np.arange(-0.5, len(row_labels), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=0.7)
        ax.tick_params(which="minor", bottom=False, left=False)
        for row_idx in range(matrix.shape[0]):
            for col_idx in range(matrix.shape[1]):
                value = matrix[row_idx, col_idx]
                if np.isfinite(value):
                    ax.text(
                        col_idx,
                        row_idx,
                        f"{value:.2f}",
                        ha="center",
                        va="center",
                        color="white" if value < 0.45 else "black",
                        fontsize=max(font_size - 2, 6),
                    )
    cbar = fig.colorbar(image, ax=axes, fraction=0.030, pad=0.018)
    cbar.set_label("Performance score (0 = worst, 1 = best)")
    cbar.set_ticks([0.0, 0.25, 0.50, 0.75, 1.0])
    fig.text(
        0.5,
        0.965,
        (
            "Performance matrix after per-100 m2 normalization and "
            f"{'global' if scaling_mode == 'global' else 'UEU-specific'} min-max scaling"
        ),
        ha="center",
        va="center",
        fontsize=font_size,
    )
    fig.subplots_adjust(left=0.17, right=0.91, bottom=0.17, top=0.82, wspace=0.12)
    _savefig_fixed_pdf_width(fig, filename, dpi=600, format="pdf")
    if show:
        plt.show()
    plt.close(fig)


def plot_dec_cen_ueu_dot_comparison(
    rows_by_ueu,
    *,
    filename,
    scaling_mode,
    figsize,
    font_size=9,
    font_family="TeX Gyre Termes",
    show=False,
):
    from matplotlib.lines import Line2D

    ordered_ueus = ["Low heat density", "Medium heat density", "High heat density"]
    objectives = [
        ("totex", "Min. ann. TOTEX solution"),
        ("co2", "Min. ann. GWP solution"),
        ("peak", "Min. peak grid ex. power solution"),
    ]
    metrics = [
        ("totex", "Ann. TOTEX"),
        ("co2", "Ann. GWP"),
        ("peak", "Peak grid"),
    ]
    colors = {"decentralized": "#0072B2", "centralized": "#D55E00"}
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.titlesize": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": max(font_size - 1, 6),
        "ytick.labelsize": max(font_size - 1, 6),
        "legend.fontsize": font_size,
        "mathtext.fontset": "cm",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    fig, axes = plt.subplots(1, 3, figsize=figsize, sharex=True, sharey=True)
    y_positions = []
    y_labels = []
    y = 0.0
    for _objective, objective_label in objectives:
        y_positions.append(y)
        y_labels.append(objective_label)
        y += 1.0
        for _metric, metric_label in metrics:
            y_positions.append(y)
            y_labels.append(f"  {metric_label}")
            y += 1.0
        y += 0.55

    for ax_idx, (ax, ueu_label) in enumerate(zip(axes, ordered_ueus)):
        lookup = _radar_entry_lookup(rows_by_ueu.get(ueu_label, []))
        ax.set_title(RADAR_UEU_TITLES.get(ueu_label, ueu_label), pad=6)
        ax.set_xlim(-0.02, 1.02)
        ax.set_xticks([0.0, 0.25, 0.50, 0.75, 1.0])
        ax.set_xticklabels(["0", "0.25", "0.50", "0.75", "1.00"])
        ax.grid(True, axis="x", alpha=0.28, linewidth=0.6)
        ax.set_ylim(max(y_positions) + 0.5, -0.5)
        cursor = 0.0
        for objective, _objective_label in objectives:
            ax.axhline(cursor - 0.5, color="0.82", linewidth=0.55)
            cursor += 1.0
            for metric, _metric_label in metrics:
                dec = lookup.get(("decentralized", objective))
                cen = lookup.get(("centralized", objective))
                dec_value = dec["normalised"][metric] if dec is not None else np.nan
                cen_value = cen["normalised"][metric] if cen is not None else np.nan
                if np.isfinite(dec_value) and np.isfinite(cen_value):
                    ax.plot([dec_value, cen_value], [cursor, cursor], color="0.70", linewidth=0.65, zorder=1)
                if np.isfinite(dec_value):
                    ax.scatter(dec_value, cursor, color=colors["decentralized"], s=20, zorder=3)
                if np.isfinite(cen_value):
                    ax.scatter(cen_value, cursor, color=colors["centralized"], s=20, zorder=3)
                cursor += 1.0
            cursor += 0.55
        if ax_idx == 0:
            ax.set_yticks(y_positions)
            ax.set_yticklabels(y_labels)
        else:
            ax.tick_params(axis="y", labelleft=False)
        ax.set_xlabel("Performance score")
    handles = [
        Line2D([0], [0], marker="o", linestyle="None", color=colors["decentralized"], label="Decentralized"),
        Line2D([0], [0], marker="o", linestyle="None", color=colors["centralized"], label="Centralized"),
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.965),
        ncol=2,
        frameon=False,
        title=(
            "Performance score after per-100 m2 normalization and "
            f"{'global' if scaling_mode == 'global' else 'UEU-specific'} min-max scaling"
        ),
        title_fontsize=font_size,
    )
    fig.subplots_adjust(left=0.28, right=0.98, bottom=0.10, top=0.80, wspace=0.10)
    _savefig_fixed_pdf_width(fig, filename, dpi=600, format="pdf")
    if show:
        plt.show()
    plt.close(fig)


def _score_lookup(df):
    lookup = {}
    for row in df.itertuples():
        lookup[(row.ueu_type, row.supply_configuration, row.selected_objective, row.kpi)] = (
            float(row.performance_score)
        )
    return lookup


def plot_dec_cen_heat_supply_heatmap(
    df,
    *,
    filename,
    figsize,
    font_size=9,
    font_family="TeX Gyre Termes",
    show=False,
):
    set_journal_style(font_family=font_family, font_size=font_size)
    row_labels = [
        label.replace(" - ", " -\n").replace("min. peak grid ex. power", "min. peak grid\nex. power")
        for _supply, _objective, label in RADAR_SOLUTION_ORDER
    ]
    metric_labels = ["Ann. TOTEX", "Ann. GWP", "Peak grid\nex. power"]
    score_lookup = _score_lookup(df)

    fig, axes = plt.subplots(1, 3, figsize=figsize, sharey=True)
    image = None
    for ax_idx, (ax, ueu_label) in enumerate(zip(axes, RADAR_ORDERED_UEUS)):
        matrix = np.full((len(RADAR_SOLUTION_ORDER), len(RADAR_METRICS)), np.nan)
        for row_idx, (supply, objective, _label) in enumerate(RADAR_SOLUTION_ORDER):
            for col_idx, metric in enumerate(RADAR_METRICS):
                matrix[row_idx, col_idx] = score_lookup[(ueu_label, supply, objective, metric)]

        image = ax.imshow(matrix, cmap="viridis", vmin=0.0, vmax=1.0, aspect="auto")
        ax.set_title(RADAR_UEU_TITLES.get(ueu_label, ueu_label), pad=6)
        ax.set_xticks(np.arange(len(metric_labels)))
        ax.set_xticklabels(metric_labels)
        ax.set_yticks(np.arange(len(row_labels)))
        if ax_idx == 0:
            ax.set_yticklabels(row_labels)
        else:
            ax.tick_params(axis="y", labelleft=False)
        ax.set_xticks(np.arange(-0.5, len(metric_labels), 1), minor=True)
        ax.set_yticks(np.arange(-0.5, len(row_labels), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=0.65)
        ax.tick_params(which="minor", bottom=False, left=False)
        ax.axhline(2.5, color="black", linewidth=0.55)
        for row_idx in range(matrix.shape[0]):
            for col_idx in range(matrix.shape[1]):
                value = matrix[row_idx, col_idx]
                ax.text(
                    col_idx,
                    row_idx,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    color="white" if value < 0.42 else "black",
                    fontsize=max(font_size - 2, 6),
                )

    cbar = fig.colorbar(image, ax=axes, fraction=0.030, pad=0.018)
    cbar.set_label("Normalized performance score (-)")
    cbar.set_ticks([0.0, 0.25, 0.50, 0.75, 1.0])
    cbar.ax.text(
        0.5,
        -0.10,
        "0 = worst, 1 = best",
        transform=cbar.ax.transAxes,
        ha="center",
        va="top",
        fontsize=max(font_size - 1, 6),
    )
    fig.subplots_adjust(left=0.205, right=0.905, bottom=0.22, top=0.86, wspace=0.10)
    _savefig_fixed_pdf_width(fig, filename, dpi=600, format="pdf")
    if show:
        plt.show()
    plt.close(fig)


def plot_dec_cen_heat_supply_dumbbell(
    df,
    *,
    filename,
    figsize,
    font_size=9,
    font_family="TeX Gyre Termes",
    show=False,
):
    from matplotlib.lines import Line2D

    set_journal_style(font_family=font_family, font_size=font_size)
    score_lookup = _score_lookup(df)
    objective_order = ("totex", "co2", "peak")
    y_rows = []
    y = 0
    for objective in objective_order:
        for metric in RADAR_METRICS:
            y_rows.append((y, objective, metric))
            y += 1
        y += 0.55
    y_positions = [item[0] for item in y_rows]
    y_labels = [
        f"{RADAR_OBJECTIVE_LABELS[objective]}\n{RADAR_METRIC_LABELS[metric]}"
        for _y, objective, metric in y_rows
    ]

    fig, axes = plt.subplots(1, 3, figsize=figsize, sharex=True, sharey=True)
    dec_color = "#0072B2"
    cen_color = "#D55E00"
    for ax_idx, (ax, ueu_label) in enumerate(zip(axes, RADAR_ORDERED_UEUS)):
        ax.set_title(RADAR_UEU_TITLES.get(ueu_label, ueu_label), pad=6)
        ax.set_xlim(-0.03, 1.03)
        ax.set_xticks([0.0, 0.25, 0.50, 0.75, 1.0])
        ax.set_xticklabels(["0", "0.25", "0.50", "0.75", "1.00"])
        ax.set_ylim(max(y_positions) + 0.65, -0.65)
        ax.grid(True, axis="x", alpha=0.28, linewidth=0.6)
        for separator in (2.5, 6.05):
            ax.axhline(separator, color="0.72", linewidth=0.55)
        for ypos, objective, metric in y_rows:
            dec_value = score_lookup[(ueu_label, "decentralized", objective, metric)]
            cen_value = score_lookup[(ueu_label, "centralized", objective, metric)]
            ax.plot(
                [dec_value, cen_value],
                [ypos, ypos],
                color="0.70",
                linewidth=0.65,
                zorder=1,
            )
            ax.scatter(
                dec_value,
                ypos,
                marker="o",
                s=20,
                color=dec_color,
                edgecolors="black",
                linewidths=0.25,
                zorder=3,
            )
            ax.scatter(
                cen_value,
                ypos,
                marker="s",
                s=22,
                facecolors="white",
                edgecolors=cen_color,
                linewidths=0.85,
                zorder=3,
            )
        if ax_idx == 0:
            ax.set_yticks(y_positions)
            ax.set_yticklabels(y_labels)
        else:
            ax.tick_params(axis="y", labelleft=False)
        ax.set_xlabel("Normalized performance score (-)")

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor=dec_color,
            markeredgecolor="black",
            markeredgewidth=0.25,
            color=dec_color,
            markersize=4.5,
            label="Decentralized",
        ),
        Line2D(
            [0],
            [0],
            marker="s",
            linestyle="None",
            markerfacecolor="white",
            markeredgecolor=cen_color,
            markeredgewidth=0.85,
            color=cen_color,
            markersize=4.5,
            label="Centralized",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.985),
        ncol=2,
        frameon=False,
        handlelength=1.0,
        columnspacing=1.4,
    )
    fig.text(
        0.5,
        0.055,
        "0 = worst, 1 = best",
        ha="center",
        va="center",
        fontsize=max(font_size - 1, 6),
    )
    fig.subplots_adjust(left=0.30, right=0.985, bottom=0.17, top=0.83, wspace=0.11)
    _savefig_fixed_pdf_width(fig, filename, dpi=600, format="pdf")
    if show:
        plt.show()
    plt.close(fig)


def plot_dec_cen_heat_supply_smallmultiples(
    df,
    *,
    filename,
    figsize,
    font_size=9,
    font_family="TeX Gyre Termes",
    show=False,
):
    from matplotlib.lines import Line2D

    legend_font_size = font_size
    content_font_size = 8
    set_journal_style(font_family=font_family, font_size=content_font_size)
    value_lookup = {
        (row.ueu_type, row.supply_configuration, row.selected_objective, row.kpi): float(row.value_per_100m2)
        for row in df.itertuples()
    }
    objective_order = ("totex", "co2", "peak")
    objective_offsets = {"totex": -0.20, "co2": 0.0, "peak": 0.20}
    x_base = np.arange(len(RADAR_ORDERED_UEUS), dtype=float)
    x_labels = ["Low", "Med.\nheat density", "High"]
    y_labels = {
        "totex": r"Ann. TOTEX in EUR per 100 m$^2$",
        "co2": r"Ann. GWP in kg CO$_2$-eq. per 100 m$^2$",
        "peak": r"Peak grid ex. power in kW per 100 m$^2$",
    }

    def _fmt_y_tick(value):
        value = float(value)
        if abs(value) >= 100:
            return f"{value:,.0f}"
        if abs(value) >= 10:
            return f"{value:,.1f}"
        return f"{value:,.2f}"

    fig, axes = plt.subplots(1, 3, figsize=figsize, sharey=False)
    for ax_idx, (ax, metric) in enumerate(zip(axes, RADAR_METRICS)):
        metric_values = [
            value
            for key, value in value_lookup.items()
            if key[3] == metric and np.isfinite(value)
        ]
        if metric_values:
            y_min = min(metric_values)
            y_max = max(metric_values)
        else:
            y_min, y_max = 0.0, 1.0
        if np.isclose(y_min, y_max):
            pad = 1.0 if np.isclose(y_min, 0.0) else abs(y_min) * 0.05
        else:
            pad = (y_max - y_min) * 0.06
        y_low = y_min - pad
        y_high = y_max + pad
        y_ticks = [y_min, (y_min + y_max) / 2.0, y_max]

        for ueu_idx, ueu_label in enumerate(RADAR_ORDERED_UEUS):
            for objective in objective_order:
                x = x_base[ueu_idx] + objective_offsets[objective]
                dec_value = value_lookup[(ueu_label, "decentralized", objective, metric)]
                cen_value = value_lookup[(ueu_label, "centralized", objective, metric)]
                color = RADAR_OBJECTIVE_COLORS[objective]
                ax.plot([x, x], [dec_value, cen_value], color=color, linewidth=0.75, alpha=0.75)
                ax.scatter(
                    x,
                    dec_value,
                    marker="o",
                    s=19,
                    facecolors=color,
                    edgecolors=color,
                    linewidths=0.25,
                    zorder=3,
                )
                ax.scatter(
                    x,
                    cen_value,
                    marker="s",
                    s=21,
                    facecolors="white",
                    edgecolors=color,
                    linewidths=0.85,
                    zorder=3,
                )
        ax.set_xlim(-0.48, len(RADAR_ORDERED_UEUS) - 0.52)
        ax.set_ylim(y_low, y_high)
        ax.set_xticks(x_base)
        ax.set_xticks(x_base[:-1] + 0.5, minor=True)
        ax.set_xticklabels(x_labels, fontsize=content_font_size)
        ax.set_yticks(y_ticks)
        ax.set_yticklabels([_fmt_y_tick(value) for value in y_ticks], fontsize=content_font_size)
        ax.grid(True, axis="y", alpha=0.28, linewidth=0.6)
        ax.grid(True, axis="x", which="minor", alpha=0.34, linewidth=0.65)
        ax.tick_params(axis="both", labelsize=content_font_size)
        ax.tick_params(axis="x", which="minor", length=0)
        ax.set_ylabel(y_labels[metric], fontsize=content_font_size)

    objective_handles = [
        Line2D([0], [0], color=RADAR_OBJECTIVE_COLORS["totex"], lw=1.4, label="Ann. TOTEX optimal"),
        Line2D([0], [0], color=RADAR_OBJECTIVE_COLORS["peak"], lw=1.4, label="Peak grid ex. power optimal"),
        Line2D([0], [0], color=RADAR_OBJECTIVE_COLORS["co2"], lw=1.4, label="Ann. GWP optimal"),
    ]
    supply_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor="black",
            markeredgecolor="black",
            markeredgewidth=0.25,
            color="0.35",
            markersize=4.5,
            label="Decentralized",
        ),
        Line2D(
            [0],
            [0],
            marker="s",
            linestyle="None",
            markerfacecolor="white",
            markeredgecolor="0.35",
            markeredgewidth=0.85,
            color="0.35",
            markersize=4.5,
            label="Centralized",
        ),
    ]
    fig.legend(
        handles=objective_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.985),
        ncol=3,
        frameon=False,
        handlelength=1.35,
        columnspacing=0.85,
        handletextpad=0.45,
        fontsize=legend_font_size,
    )
    fig.legend(
        handles=supply_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.905),
        ncol=2,
        frameon=False,
        handlelength=1.0,
        columnspacing=1.20,
        handletextpad=0.45,
        fontsize=legend_font_size,
    )
    fig.subplots_adjust(left=0.135, right=0.985, bottom=0.20, top=0.78, wspace=0.48)
    for ax in axes:
        pos = ax.get_position()
        new_width = pos.width * 0.85
        x_shift = (pos.width - new_width) / 2.0
        ax.set_position([pos.x0 + x_shift, pos.y0, new_width, pos.height])
    try:
        _savefig_fixed_pdf_width(fig, filename, dpi=600, format="pdf")
    except PermissionError:
        fallback_path = Path(filename)
        fallback_filename = fallback_path.with_name(
            f"{fallback_path.stem}_updated{fallback_path.suffix}"
        )
        _savefig_fixed_pdf_width(fig, fallback_filename, dpi=600, format="pdf")
        print(
            "WARNING: Could not overwrite locked smallmultiples PDF. "
            f"Wrote updated plot to: {fallback_filename}"
        )
    if show:
        plt.show()
    plt.close(fig)


def plot_dec_cen_heat_supply_smallmultiples_per100_per_household(
    df,
    *,
    filename,
    figsize,
    font_size=9,
    font_family="TeX Gyre Termes",
    show=False,
):
    from matplotlib.lines import Line2D

    if "value_per_household" not in df.columns or df["value_per_household"].isna().any():
        raise ValueError(
            "Per-household heat-supply small multiples require value_per_household "
            "for every performance row."
        )

    legend_font_size = font_size
    content_font_size = 7.6
    set_journal_style(font_family=font_family, font_size=content_font_size)
    objective_order = ("totex", "co2", "peak")
    objective_offsets = {"totex": -0.20, "co2": 0.0, "peak": 0.20}
    x_base = np.arange(len(RADAR_ORDERED_UEUS), dtype=float)
    x_labels = ["Low", "Med.\nheat density", "High"]
    column_titles = {
        "totex": "Ann. TOTEX\nin EUR",
        "co2": r"Ann. GWP in" + "\n" + r"kg CO$_2$-eq.",
        "peak": "Peak grid ex.\npower in kW",
    }
    row_specs = (
        ("value_per_100m2", r"per 100 m$^2$"),
        ("value_per_household", "per household"),
    )
    value_lookups = {
        value_col: {
            (row.ueu_type, row.supply_configuration, row.selected_objective, row.kpi): float(
                getattr(row, value_col)
            )
            for row in df.itertuples()
        }
        for value_col, _label in row_specs
    }

    def _fmt_y_tick(value):
        value = float(value)
        if abs(value) >= 100:
            return f"{value:,.0f}"
        if abs(value) >= 10:
            return f"{value:,.1f}"
        return f"{value:,.2f}"

    fig, axes = plt.subplots(2, 3, figsize=figsize, sharex=True, sharey=False)
    for row_idx, (value_col, row_label) in enumerate(row_specs):
        value_lookup = value_lookups[value_col]
        for col_idx, metric in enumerate(RADAR_METRICS):
            ax = axes[row_idx, col_idx]
            metric_values = [
                value
                for key, value in value_lookup.items()
                if key[3] == metric and np.isfinite(value)
            ]
            if metric_values:
                y_min = min(metric_values)
                y_max = max(metric_values)
            else:
                y_min, y_max = 0.0, 1.0
            if np.isclose(y_min, y_max):
                pad = 1.0 if np.isclose(y_min, 0.0) else abs(y_min) * 0.05
            else:
                pad = (y_max - y_min) * 0.06
            y_low = y_min - pad
            y_high = y_max + pad
            y_ticks = [y_min, (y_min + y_max) / 2.0, y_max]

            for ueu_idx, ueu_label in enumerate(RADAR_ORDERED_UEUS):
                for objective in objective_order:
                    x = x_base[ueu_idx] + objective_offsets[objective]
                    dec_value = value_lookup[(ueu_label, "decentralized", objective, metric)]
                    cen_value = value_lookup[(ueu_label, "centralized", objective, metric)]
                    color = RADAR_OBJECTIVE_COLORS[objective]
                    ax.plot([x, x], [dec_value, cen_value], color=color, linewidth=0.72, alpha=0.75)
                    ax.scatter(
                        x,
                        dec_value,
                        marker="o",
                        s=16,
                        facecolors=color,
                        edgecolors=color,
                        linewidths=0.22,
                        zorder=3,
                    )
                    ax.scatter(
                        x,
                        cen_value,
                        marker="s",
                        s=18,
                        facecolors="white",
                        edgecolors=color,
                        linewidths=0.82,
                        zorder=3,
                    )
            ax.set_xlim(-0.48, len(RADAR_ORDERED_UEUS) - 0.52)
            ax.set_ylim(y_low, y_high)
            ax.set_xticks(x_base)
            ax.set_xticks(x_base[:-1] + 0.5, minor=True)
            ax.set_yticks(y_ticks)
            ax.set_yticklabels([_fmt_y_tick(value) for value in y_ticks], fontsize=content_font_size)
            ax.grid(True, axis="y", alpha=0.28, linewidth=0.58)
            ax.grid(True, axis="x", which="minor", alpha=0.34, linewidth=0.62)
            ax.tick_params(axis="both", labelsize=content_font_size)
            ax.tick_params(axis="x", which="minor", length=0)
            if row_idx == 0:
                ax.set_title(column_titles[metric], fontsize=content_font_size + 0.4, pad=5)
                ax.set_xticklabels([])
            else:
                ax.set_xticklabels(x_labels, fontsize=content_font_size)
            if col_idx == 0:
                ax.set_ylabel(row_label, fontsize=content_font_size)

    objective_handles = [
        Line2D([0], [0], color=RADAR_OBJECTIVE_COLORS["totex"], lw=1.4, label="Ann. TOTEX optimal"),
        Line2D([0], [0], color=RADAR_OBJECTIVE_COLORS["peak"], lw=1.4, label="Peak grid ex. power optimal"),
        Line2D([0], [0], color=RADAR_OBJECTIVE_COLORS["co2"], lw=1.4, label="Ann. GWP optimal"),
    ]
    supply_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor="black",
            markeredgecolor="black",
            markeredgewidth=0.25,
            color="0.35",
            markersize=4.2,
            label="Decentralized",
        ),
        Line2D(
            [0],
            [0],
            marker="s",
            linestyle="None",
            markerfacecolor="white",
            markeredgecolor="0.35",
            markeredgewidth=0.85,
            color="0.35",
            markersize=4.2,
            label="Centralized",
        ),
    ]
    fig.legend(
        handles=objective_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.992),
        ncol=3,
        frameon=False,
        handlelength=1.30,
        columnspacing=0.72,
        handletextpad=0.42,
        fontsize=legend_font_size,
    )
    fig.legend(
        handles=supply_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.935),
        ncol=2,
        frameon=False,
        handlelength=0.95,
        columnspacing=1.05,
        handletextpad=0.42,
        fontsize=legend_font_size,
    )
    fig.subplots_adjust(left=0.135, right=0.985, bottom=0.135, top=0.82, wspace=0.45, hspace=0.42)
    try:
        _savefig_fixed_pdf_width(fig, filename, dpi=600, format="pdf")
    except PermissionError:
        fallback_path = Path(filename)
        fallback_filename = fallback_path.with_name(
            f"{fallback_path.stem}_updated{fallback_path.suffix}"
        )
        _savefig_fixed_pdf_width(fig, fallback_filename, dpi=600, format="pdf")
        print(
            "WARNING: Could not overwrite locked smallmultiples per-household PDF. "
            f"Wrote updated plot to: {fallback_filename}"
        )
    if show:
        plt.show()
    plt.close(fig)


def write_radar_summary_csv(path, rows_by_ueu, range_rows, scaling_mode):
    rows = []
    for ueu_label, entries in rows_by_ueu.items():
        for entry in entries:
            row = {
                "scaling_mode": scaling_mode,
                "ueu_label": ueu_label,
                "line_label": entry["label"],
                "supply": entry["supply"],
            }
            for metric in ("totex", "co2", "peak"):
                row[f"{metric}_raw"] = entry["raw"][metric]
                row[f"{metric}_normalized"] = entry["normalised"][metric]
            rows.append(row)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        if rows:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    range_path = Path(path).with_name(Path(path).stem + "_ranges.csv")
    with open(range_path, "w", newline="", encoding="utf-8") as fh:
        if range_rows:
            writer = csv.DictWriter(fh, fieldnames=list(range_rows[0].keys()))
            writer.writeheader()
            writer.writerows(range_rows)


def run_dec_cen_ueu_radar_plots(
    *,
    optimization_root,
    decentralized_hypervolume_root,
    centralized_post_processed_root,
    out_dir,
    centralized_combined_cluster,
    no_electricity_grid_active,
    width_inch,
    height_inch,
    font_size,
    heat_grid_planning_overrides=None,
):
    centralized_groups = (
        ("t50", "cmin"),
        ("t80", "cmin"),
        ("t80", "cmax"),
    )
    raw_by_ueu = {}
    for ueu_short in UEU_SHORT_ORDER:
        item = _load_radar_fronts_for_ueu(
            ueu_short=ueu_short,
            optimization_root=optimization_root,
            decentralized_hypervolume_root=decentralized_hypervolume_root,
            centralized_post_processed_root=centralized_post_processed_root,
            centralized_combined_cluster=centralized_combined_cluster,
            centralized_groups=centralized_groups,
            no_electricity_grid_active=no_electricity_grid_active,
            heat_grid_planning_overrides=heat_grid_planning_overrides,
        )
        raw_by_ueu[item["ueu_label"]] = item

    height_variants = (
        ("_h100", 1.00),
        ("_h90", 0.90),
        ("_h80", 0.80),
        ("_h70", 0.70),
    )
    os.makedirs(out_dir, exist_ok=True)
    for scaling_mode in ("global",):
        rows_by_ueu, range_rows = _build_radar_rows(raw_by_ueu, scaling_mode=scaling_mode)
        missing = [
            label for label in ("Low heat density", "Medium heat density", "High heat density")
            if label not in rows_by_ueu or not rows_by_ueu[label]
        ]
        if missing:
            print(
                "WARNING: Radar comparison has missing UEU data for "
                f"{scaling_mode}: {', '.join(missing)}"
            )
        csv_path = os.path.join(
            out_dir,
            f"COMPARE_dec_cen_heat_supply_radar_{scaling_mode}.csv",
        )
        write_radar_summary_csv(csv_path, rows_by_ueu, range_rows, scaling_mode)
        height_scale_by_case = {
            "h100": 1.00,
            "h90": 0.90,
            "h80": 0.80,
            "h70": 0.70,
            "h60": 0.60,
        }
        if HEIGHT_CASE not in height_scale_by_case:
            raise ValueError(f"Unsupported HEIGHT_CASE for heat-supply alternatives: {HEIGHT_CASE}")
        performance_df = build_dec_cen_heat_supply_performance_dataframe(
            rows_by_ueu,
            range_rows,
            scaling_mode=scaling_mode,
            height_case=HEIGHT_CASE,
        )
        print_dec_cen_heat_supply_performance_validation(
            performance_df,
            range_rows,
            height_case=HEIGHT_CASE,
        )
        alternative_height_scale = height_scale_by_case[HEIGHT_CASE]
        alternative_figures = [
            (
                plot_dec_cen_heat_supply_heatmap,
                f"COMPARE_dec_cen_heat_supply_heatmap_{scaling_mode}_{HEIGHT_CASE}.pdf",
                1.33,
            ),
            (
                plot_dec_cen_heat_supply_dumbbell,
                f"COMPARE_dec_cen_heat_supply_dumbbell_{scaling_mode}_{HEIGHT_CASE}.pdf",
                1.50,
            ),
        ]
        for plot_func, output_name, height_factor in alternative_figures:
            output_path = os.path.join(out_dir, output_name)
            plot_func(
                performance_df,
                filename=output_path,
                figsize=(width_inch, height_inch * height_factor * alternative_height_scale),
                font_size=9,
                show=False,
            )
            print(f"Heat-supply alternative plot written: {output_path}")
        smallmultiple_height_cases = ("h100", "h90", "h80", "h70", "h60")
        for small_h_case in smallmultiple_height_cases:
            small_output_path = os.path.join(
                out_dir,
                f"COMPARE_dec_cen_heat_supply_smallmultiples_{scaling_mode}_{small_h_case}.pdf",
            )
            plot_dec_cen_heat_supply_smallmultiples(
                performance_df,
                filename=small_output_path,
                figsize=(
                    width_inch,
                    height_inch * 1.05 * height_scale_by_case[small_h_case],
                ),
                font_size=9,
                show=False,
            )
            print(f"Heat-supply smallmultiples plot written: {small_output_path}")
            small_perhh_output_path = os.path.join(
                out_dir,
                f"COMPARE_dec_cen_heat_supply_smallmultiples_per100_per_household_{scaling_mode}_{small_h_case}.pdf",
            )
            plot_dec_cen_heat_supply_smallmultiples_per100_per_household(
                performance_df,
                filename=small_perhh_output_path,
                figsize=(
                    width_inch,
                    height_inch * 1.78 * height_scale_by_case[small_h_case],
                ),
                font_size=8,
                show=False,
            )
            print(
                "Heat-supply smallmultiples per-100m2/per-household plot written: "
                f"{small_perhh_output_path}"
            )
            for plot_variant in (
                "balanced",
                "both_markers",
                "break_verticals",
                "centralized_points",
            ):
                variant_suffix = HEAT_SUPPLY_PROJECTION_VARIANTS[plot_variant]["filename_suffix"]
                projection_output_path = os.path.join(
                    out_dir,
                    f"6_COMPARE_dec_cen_heat_supply_pareto_front_projection_lines_"
                    f"{scaling_mode}_{small_h_case}{variant_suffix}.pdf",
                )
                plot_dec_cen_heat_supply_projection_front_lines(
                    raw_by_ueu,
                    filename=projection_output_path,
                    figsize=(
                        width_inch,
                        height_inch * 1.08 * height_scale_by_case[small_h_case],
                    ),
                    font_size=9,
                    variant=plot_variant,
                    show=False,
                )
                print(
                    "Heat-supply Pareto projection line plot written "
                    f"({plot_variant}): {projection_output_path}"
                )
        for suffix, height_scale in height_variants:
            filename = os.path.join(
                out_dir,
                f"COMPARE_dec_cen_heat_supply_radar_{scaling_mode}{suffix}.pdf",
            )
            plot_dec_cen_ueu_radar_comparison(
                rows_by_ueu,
                filename=filename,
                scaling_mode=scaling_mode,
                figsize=(width_inch, height_inch * 1.18 * height_scale),
                font_size=font_size,
                show=False,
            )
            print(f"Radar comparison plot written: {filename}")


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


if __name__ == "__main__":# ============================================================

    import os
    import pickle
    import numpy as np
    import matplotlib.pyplot as plt

    # ============================================================
    # CONFIG (your base)
    # ============================================================
    ueu_list = [
        "processed_bds_in_DENI03403000SEC4580",
        "processed_bds_in_DENI03403000SEC5658",
        "processed_bds_in_DENI03403000SEC5101",
    ]
    no_electricity_grid_active = True
    centralized_same_plots_by_temperature = False
    old_decentralized = True
    if old_decentralized:
        if False:
            base_path = r"C:\Users\hill_mx\Desktop\From Luis\Case Studies\Small New"
            out_dir   = r"C:\Users\hill_mx\Desktop\123"
            combined_front_input_override_by_ueu_short = {
                "DENI03403000SEC4580": (
                    r"C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model\examples"
                    r"\03_applied_energy_optimization\processed_bds_in_DENI03403000SEC4580"
                    r"\post_processed_dec_k_combinations_2026_04_29\sfh_reference_mfh_reference"
                ),
                "DENI03403000SEC5101": (
                    r"C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model\examples"
                    r"\03_applied_energy_optimization\processed_bds_in_DENI03403000SEC5101"
                    r"\post_processed_dec_k_combinations_2026_04_29\sfh_reference_mfh_reference"
                ),
                "DENI03403000SEC5658": (
                    r"C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model\examples"
                    r"\03_applied_energy_optimization\processed_bds_in_DENI03403000SEC5658"
                    r"\post_processed_dec_k_combinations_2026_04_30\sfh_reference_mfh_reference"
                ),
            }
        else:
            base_path = r"C:\Users\hill_mx\Desktop\From Luis\Case Studies\Small New"
            out_dir   = r"C:\Users\hill_mx\Desktop\123"
            decentralized_hypervolume_results_root = (
                Path(__file__).resolve().parent.parent
                / "05_applied_energy_pareto_set_analysis"
                / "decentralized"
                / "hypervolume_results"
            )
            combined_front_input_override_by_ueu_short = {
                ueu_short: _latest_decentralized_reference_front_dir(
                    decentralized_hypervolume_results_root,
                    ueu_short,
                )
                for ueu_short in (
                    "DENI03403000SEC5658",
                    "DENI03403000SEC4580",
                    "DENI03403000SEC5101",
                )
            }
            combined_front_input_override_by_ueu_short["DENI03403000SEC5658"] = str(
                Path(__file__).resolve().parent.parent
                / "03_applied_energy_optimization"
                / "processed_bds_in_DENI03403000SEC5658"
                / "post_processed_dec_k_combinations_2026_04_30"
                / "sfh_reference_mfh_reference"
            )
    else:
        centralized_same_plots_by_temperature = True
        centralized_temperature_constraint_groups = (
            ("t50", "cmin"),
            ("t80", "cmax"),
            ("t80", "cmin"),
        )
        centralized_strategy_labels = {
            "t50_cmin": "50 \N{DEGREE SIGN}C min. required",
            "t80_cmax": "80 \N{DEGREE SIGN}C max. retrofit",
            "t80_cmin": "80 \N{DEGREE SIGN}C min. required",
        }
        centralized_combined_cluster = "combined_cluster_sfh_reference_mfh_reference"
        centralized_post_processed_root = str(_default_centralized_post_processed_root())
        base_path = str(_default_optimization_root())
        ueu_list = [
            "processed_bds_in_DENI03403000SEC4580",
            "processed_bds_in_DENI03403000SEC5658",
            "processed_bds_in_DENI03403000SEC5101",
        ]

        out_dir = str(_default_plot_output_root())
        main_out_dir = out_dir

        combined_front_input_override_by_ueu_short = {
            "DENI03403000SEC5658": str(
                Path(centralized_post_processed_root)
                / "processed_bds_in_DENI03403000SEC5658"
                / centralized_combined_cluster
            ),
            "DENI03403000SEC4580": str(
                Path(centralized_post_processed_root)
                / "processed_bds_in_DENI03403000SEC4580"
                / centralized_combined_cluster
            ),
            "DENI03403000SEC5101": str(
                Path(centralized_post_processed_root)
                / "processed_bds_in_DENI03403000SEC5101"
                / centralized_combined_cluster
            ),
        }
        if centralized_same_plots_by_temperature:
            ueu_list = [
                {
                    "ueu": ueu,
                    "temperature_level": f"{temperature_level}_{constraint_type}",
                    "combined_front_input_override": str(
                        Path(centralized_post_processed_root)
                        / ueu
                        / centralized_combined_cluster
                        / temperature_level
                        / constraint_type
                    ),
                    "out_dir": os.path.join(out_dir, temperature_level, constraint_type),
                }
                for ueu in ueu_list
                for temperature_level, constraint_type in centralized_temperature_constraint_groups
            ]
    # Optional override for combined_front input:
    # - file path to pickle
    # - directory containing combined_front.pkl
    # - template path with {ueu_short}
    # Example:
    # combined_front_input_override = (
    #     r"C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model"
    #     r"\examples\05_applied_energy_pareto_set_analysis\hypervolume_results"
    #     r"\processed_bds_in_{ueu_short}\post_processed_dec_k_combinations_2026_04_09"
    #     r"\sfh_reference_mfh_reference"
    # )
    combined_front_input_override = None
    if not old_decentralized:
        result_name = "centralized_front"
        cen_or_dec = "cen"
    else:
        result_name = "combined_front"
        cen_or_dec = "dec"
    heat_grid_planning_overrides = {}
    if cen_or_dec == "cen":
        heat_grid_planning_dir = (
            Path(__file__).resolve().parent
            / "centralized"
            / "heat_grid_planning"
        )
        heat_grid_planning_overrides = _load_heat_grid_planning_overrides(
            heat_grid_planning_dir
        )
        _print_heat_grid_planning_overrides(heat_grid_planning_overrides)
    # Width contract: every exported PDF figure must use this 11.8 cm width.
    # Do not widen individual plot families with width_inch multipliers.
    width_cm  = 11.8
    height_cm = 6.5 * 1.34
    width_inch  = width_cm / 2.54
    height_inch = height_cm / 2.54
    font_size = 9
    # True: collect required data, but write only cross-UEU compare plots.
    # False: write all per-UEU Pareto, stackplot, reconciliation, and compare plots.
    run_only_compare_plots = True
    run_parallel_coordinate_compare_plots = True
    plot_only_low_heat_density = False
    centralized_reference_post_processed_root = (
        Path(__file__).resolve().parent
        / "centralized"
        / "centralized_post_processed"
    )
    run_only_medium_heat_density = False
    if run_only_medium_heat_density:
        if ueu_list and isinstance(ueu_list[0], dict):
            ueu_list = [
                item for item in ueu_list
                if item["ueu"] == "processed_bds_in_DENI03403000SEC5658"
            ]
        else:
            ueu_list = ["processed_bds_in_DENI03403000SEC5658"]
    elif plot_only_low_heat_density:
        if ueu_list and isinstance(ueu_list[0], dict):
            ueu_list = [
                item for item in ueu_list
                if item["ueu"] == "processed_bds_in_DENI03403000SEC4580"
            ]
        else:
            ueu_list = ["processed_bds_in_DENI03403000SEC4580"]

    energy_types = ["Electricity", "Bio gas", "Natural gas", "Hydrogen"]
    technologies = [
        "PV-System",
        "Heat storage",
        "Battery",
        "Gas heater",
        "CHP",
        "Heat pump",
        "Added trafo capacity",
        "Added line length",
        "Retrofit",
        "Heat grid",
        "Seasonal storage",
    ]
    if no_electricity_grid_active:
        technologies = [
            tech for tech in technologies
            if tech not in {"Added trafo capacity", "Added line length"}
        ]
    if cen_or_dec == "dec":
        technologies = [
            tech for tech in technologies
            if tech not in {"Heat grid", "Seasonal storage"}
        ]

    value_types = ["cost", "co2", "capacity"]
    Y_LABELS_PER_100M2 = {
        "cost": "Ann. TOTEX in EUR per 100 m$^2$",
        "co2": r"Ann. GWP in kg CO$_2$-eq. per 100 m$^2$",
        "capacity": "Installed capacity in kW or kWh per 100 m$^2$",
    }
    Y_LABELS_PER_100M2_WRAPPED = {
        k: _linebreak_after_in_label(v)
        for k, v in Y_LABELS_PER_100M2.items()
    }
    Y_LABELS_PER_100M2_CAPACITY_LOG_WRAPPED = dict(Y_LABELS_PER_100M2_WRAPPED)
    Y_LABELS_PER_100M2_CAPACITY_LOG_WRAPPED["capacity"] = _linebreak_after_in_label(
        "Installed capacity (sym. log. scale) in kW or kWh per 100 m$^2$"
    )
    PEAK_LABEL_PER_100M2_WRAPPED = _linebreak_after_in_label(
        "Peak grid ex. power in kW per 100 m$^2$"
    )
    stackplot_height_variants = [
        ("", 1.00),
        ("_h80", 0.80),
        ("_h60", 0.60),
    ]
    combined_stackplot_height_variants = [
        ("_h80", 0.80),
        ("_h70", 0.70),
        ("_h60", 0.60),
        ("_h50", 0.50),
        ("_h40", 0.40),
    ]
    stacked_parallel_height_variants = [
        ("_h100", 1.00),
        ("_h90", 0.90),
        ("_h80", 0.80),
        ("_h70", 0.70),
        ("_h60", 0.60),
    ]
    stacked_parallel_font_size_variants = [
        ("_fs_8", 8),
        ("_fs_9", 9),
    ]
    single_parallel_height_factor = 1.90 * 0.85
    stacked_parallel_reference_scale = 0.30

    # ============================================================
    # STORAGE: collect results while looping
    # ============================================================
    ueu_results = {}  # {ueu_short: {...}} stored while looping
    parallel_rows_compare_by_points = {}
    centralized_strategy_fronts_per100 = {}
    centralized_strategy_fronts_abs = {}
    centralized_reference_context = {}
    centralized_strategy_fronts_per100_by_ueu = {}
    centralized_strategy_fronts_abs_by_ueu = {}
    centralized_reference_context_by_ueu = {}
    centralized_loaded_front_paths_by_ueu = {}

    if not old_decentralized:
        run_dec_cen_ueu_radar_plots(
            optimization_root=Path(base_path),
            decentralized_hypervolume_root=_default_decentralized_hypervolume_root(),
            centralized_post_processed_root=Path(centralized_post_processed_root),
            out_dir=out_dir,
            centralized_combined_cluster=centralized_combined_cluster,
            no_electricity_grid_active=no_electricity_grid_active,
            width_inch=width_inch,
            height_inch=height_inch,
            font_size=font_size,
            heat_grid_planning_overrides=heat_grid_planning_overrides,
        )

    # ============================================================
    # LOOP OVER UEUs
    # ============================================================
    for ueu_item in ueu_list:
        if isinstance(ueu_item, dict):
            ueu = ueu_item["ueu"]
            case_out_dir = ueu_item.get("out_dir", out_dir)
            case_input_override = ueu_item.get("combined_front_input_override")
            case_temperature_level = ueu_item.get("temperature_level")
        else:
            ueu = ueu_item
            case_out_dir = out_dir
            case_input_override = None
            case_temperature_level = None

        out_dir = case_out_dir
        os.makedirs(out_dir, exist_ok=True)
        print(ueu)
        ueu_short = ueu.removeprefix("processed_bds_in_")
        if case_temperature_level:
            print(f"\n=== UEU: {ueu_short} | temperature: {case_temperature_level} ===")
        else:
            print(f"\n=== UEU: {ueu_short} ===")

        combined_front_path_resolved = resolve_combined_front_path(
            ueu_short=ueu_short,
            input_dir=input_dir if "input_dir" in locals() else "",
            result_name=result_name if "result_name" in locals() else "",
            combined_front_input_override=(
                case_input_override
                if case_input_override is not None
                else combined_front_input_override_by_ueu_short.get(
                    ueu_short, combined_front_input_override
                )
            ),
        )
        if cen_or_dec == "cen" and case_temperature_level:
            combined_front_path_resolved = _resolve_centralized_front_path(
                resolved_path=combined_front_path_resolved,
                examples_root=Path(__file__).resolve().parent.parent,
                ueu=ueu,
                combined_cluster=centralized_combined_cluster,
                case_temperature_level=case_temperature_level,
            )

        if not os.path.exists(combined_front_path_resolved):
            print(f"WARNING: missing combined-front file: {combined_front_path_resolved}")
            continue

        combined_front_path_lower = str(combined_front_path_resolved).lower()
        is_reference_reference_case = (
            "sfh_reference" in combined_front_path_lower
            and "mfh_reference" in combined_front_path_lower
        )

        if is_reference_reference_case:
            print(
                "EXTRA CASE: reference/reference detected in combined-front path "
                f"for UEU {ueu_short}: {combined_front_path_resolved}"
            )
            path1 = (
                Path(__file__).resolve().parent.parent
                / "03_applied_energy_optimization"
            )
            import geopandas as gpd
            import pandas as pd
            gpkg_ueu = _resolve_ueu_gpkg_path(path1, ueu)
            print(f"UEU GPKG: {gpkg_ueu}")
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
                    "number_of_households": int(row["number_of_households"]),
                    "number_of_residents": int(row["number_of_residents"]) if not pd.isna(
                        row["number_of_residents"]) else 0,
                    "tabula_year_class": row.get("tabula_year_class"),
                    "heat_load_1": row.get("heat_load_1"),
                    "heat_load_2": row.get("heat_load_2"),
                    "heat_load_3": row.get("heat_load_3"),
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

        try:
            combined_front = load_combined_front_from_path(combined_front_path_resolved)
        except Exception as exc:
            print(
                f"WARNING: failed to load combined-front from '{combined_front_path_resolved}' "
                f"for UEU {ueu_short}: {exc}"
            )
            continue

        combined_front = maniupulate_combined_front_elect_grid(combined_front,no_electricity_grid_active)
        if cen_or_dec == "cen" and case_temperature_level:
            combined_front = _apply_heat_grid_planning_override_to_front(
                combined_front,
                ueu_short=ueu_short,
                case_temperature_level=case_temperature_level,
                overrides=heat_grid_planning_overrides,
            )

        #combined_front = maniupulate_combined_front(combined_front,value_types,building_in_cluster)

        combined_front_per100 = normalise_front_per_input_value(
            combined_front=combined_front,
            input_value=total_floor_area_all/100,
        )
        combined_front_per_household = normalise_front_per_input_value(
            combined_front=combined_front,
            input_value=total_number_of_households,
        )
        if cen_or_dec == "cen" and case_temperature_level:
            strategy_label = centralized_strategy_labels.get(
                case_temperature_level,
                case_temperature_level,
            )
            ueu_label = ueu_display(ueu_short)
            front_path_key = str(Path(combined_front_path_resolved).resolve()).lower()
            loaded_paths_for_ueu = centralized_loaded_front_paths_by_ueu.setdefault(
                ueu_label,
                set(),
            )
            if front_path_key not in loaded_paths_for_ueu:
                loaded_paths_for_ueu.add(front_path_key)
                centralized_strategy_fronts_abs_by_ueu.setdefault(ueu_label, {})[
                    strategy_label
                ] = combined_front
                centralized_strategy_fronts_per100_by_ueu.setdefault(ueu_label, {})[
                    strategy_label
                ] = combined_front_per100
            centralized_reference_context_by_ueu[ueu_label] = {
                "building_in_cluster": list(building_in_cluster),
                "rep_info": dict(rep_info),
                "total_floor_area_all": total_floor_area_all,
            }
            if ueu_short == "DENI03403000SEC5658":
                centralized_strategy_fronts_per100[strategy_label] = combined_front_per100
                centralized_strategy_fronts_abs[strategy_label] = combined_front
                centralized_reference_context = {
                    "building_in_cluster": list(building_in_cluster),
                    "rep_info": dict(rep_info),
                    "total_floor_area_all": total_floor_area_all,
                }
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
                x_label=r"Ann. GWP in kg CO$_2$-eq.",
                y_label=r"Ann. TOTEX in EUR",
                cbar_label=r"Peak grid ex. power in kW",
                tick_highlights_exclude_last_index=True,
                write_outputs=not run_only_compare_plots,
            )


            res_per100 = run_pareto_plots(
                show=False,
                combined_front=combined_front_per100,
                out_prefix=f"{cen_or_dec}_{ueu_display(ueu_short)}_per_100m2",
                width_inch=width_inch,
                height_inch=height_inch,
                font_size=font_size,
                out_dir=out_dir,
                x_label=r"Ann. GWP in kg CO$_2$-eq. per 100 m$^2$",
                y_label=r"Ann. TOTEX in EUR per 100 m$^2$",
                cbar_label=r"Peak grid ex. power in kW per 100 m$^2$",
                tick_highlights_exclude_last_index=True,
                write_outputs=not run_only_compare_plots,
            )
            res_per_household = run_pareto_plots(
                show=False,
                combined_front=combined_front_per_household,
                out_prefix=f"{cen_or_dec}_{ueu_display(ueu_short)}_per_household",
                width_inch=width_inch,
                height_inch=height_inch,
                font_size=font_size,
                out_dir=out_dir,
                x_label=r"Ann. GWP in kg CO$_2$-eq. per household",
                y_label=r"Totex EUR per household",
                cbar_label=r"Peak grid ex. power in kW per household",
                tick_highlights_exclude_last_index=True,
                write_outputs=not run_only_compare_plots,
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
            return np.array(
                [lookup.get(_rounded_key(pt[0], pt[1], dec), np.nan) for pt in pareto_front],
                dtype=float,
            )

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

            if ueu_short == "DENI03403000SEC4580" and not run_only_compare_plots:
                centralized_fronts_per100 = {}
                for temperature_level in ("t50", "t80"):
                    centralized_front_path = (
                        centralized_reference_post_processed_root
                        / f"processed_bds_in_{ueu_short}"
                        / "combined_cluster_sfh_k01_mfh_k01"
                        / temperature_level
                        / "centralized_front.pkl"
                    )
                    if not os.path.exists(_to_windows_long_path(centralized_front_path)):
                        print(
                            "WARNING: Missing centralized comparison front: "
                            f"{centralized_front_path}"
                        )
                        continue
                    centralized_front = load_combined_front_from_path(centralized_front_path)
                    centralized_fronts_per100[temperature_level] = normalise_front_per_input_value(
                        combined_front=centralized_front,
                        input_value=total_floor_area_all / 100.0,
                    )

                if centralized_fronts_per100:
                    dec_cen_height_variants = [
                        ("_h100", 1.00),
                        ("_h90", 0.90),
                        ("_h80", 0.80),
                        ("_h70", 0.70),
                        ("_h60", 0.60),
                    ]
                    dec_cen_side_by_side_width = width_inch
                    dec_cen_single_panel_width = width_inch
                    for height_suffix, height_scale in dec_cen_height_variants:
                        compare_dec_cen_filename = os.path.join(
                            out_dir,
                            f"compare_{ueu_display(ueu_short)}_per_100m2"
                            f"_pareto_all_with_front_tick_highlights_wide{height_suffix}.pdf",
                        )
                        plot_compare_dec_cen_pareto_tick_highlights_per100(
                            decentralized_front=combined_front_per100,
                            centralized_fronts_by_label=centralized_fronts_per100,
                            filename=compare_dec_cen_filename,
                            figsize=(dec_cen_side_by_side_width, height_inch * height_scale),
                            font_size=font_size,
                            layout="side_by_side",
                            show=False,
                        )
                        print(
                            "Decentralized/centralized comparison plot written: "
                            f"{compare_dec_cen_filename}"
                        )

                        compare_dec_cen_single_filename = os.path.join(
                            out_dir,
                            f"compare_{ueu_display(ueu_short)}_per_100m2"
                            f"_pareto_all_with_front_tick_highlights_single_panel_wide{height_suffix}.pdf",
                        )
                        plot_compare_dec_cen_pareto_tick_highlights_per100(
                            decentralized_front=combined_front_per100,
                            centralized_fronts_by_label=centralized_fronts_per100,
                            filename=compare_dec_cen_single_filename,
                            figsize=(dec_cen_single_panel_width, height_inch * height_scale),
                            font_size=font_size,
                            layout="single_panel",
                            show=False,
                        )
                        print(
                            "Decentralized/centralized single-panel comparison plot written: "
                            f"{compare_dec_cen_single_filename}"
                        )
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
            for district in processed_district_data.values():
                for building_name, building_data in district.items():
                    if building_name in {"co2", "peak", "totex", "electricity_grid", "heat_grid"}:
                        continue
                    if isinstance(building_data, dict):
                        building_name_map.setdefault(building_name, building_name)

        district_sums = calculate_sums_for_technologies_and_energy_for_a_district(
            processed_district_data,
            energy_types,
            technologies,
            building_name_map
        )

        if not run_only_compare_plots:
            totex_reconciliation_rows = build_totex_reconciliation_rows(district_sums)
            totex_reconciliation_filename = os.path.join(
                out_dir,
                f"{cen_or_dec}_{ueu_display(ueu_short)}_totex_reconciliation_per_100m2.csv",
            )
            write_totex_reconciliation_csv(
                totex_reconciliation_filename,
                totex_reconciliation_rows,
            )
            plot_totex_reconciliation_difference(
                totex_reconciliation_rows,
                filename=os.path.join(
                    out_dir,
                    f"{cen_or_dec}_{ueu_display(ueu_short)}_totex_reconciliation_difference_per_100m2.pdf",
                ),
                figsize=(width_inch, height_inch),
                font_size=font_size,
                show=False,
            )
            print_totex_reconciliation_summary(
                totex_reconciliation_rows,
                f"{ueu_display(ueu_short)} per 100 m2",
            )

        # ------------------------------------------------------------
        # (2) Stackplots (per 100 m²)
        # ------------------------------------------------------------
        if True:
            for vt in value_types:
                if run_only_compare_plots:
                    continue
                for height_suffix, height_scale in stackplot_height_variants:
                    filename = os.path.join(
                        out_dir,
                        f"{cen_or_dec}_{ueu_display(ueu_short)}_stackplot_{vt}_per_100m2{height_suffix}.pdf",
                    )
                    fig, ax1, ax2 = plot_stackplot_for_pareto_solutions_with_peak(
                        district_sums=district_sums,
                        technologies=technologies,
                        energy_types=energy_types,
                        value_type=vt,
                        figsize=(width_inch, height_inch * height_scale),
                        font_size=font_size,
                        show=False,
                        filename=filename,
                        x_label="Pareto-optimal solution index (sorted)",
                        sort_key=None,
                        target_xticks=8,
                        peak_lw=0.5,
                        peak_drawstyle="steps-mid",
                        legend_ncol=4,
                    )

                    ax1.set_ylabel(_linebreak_after_in_label(Y_LABELS_PER_100M2[vt]))
                    ax2.set_ylabel(_linebreak_after_in_label("Peak grid ex. power in kW per 100 m$^2$"))

                    _savefig_fixed_pdf_width(fig,
                        filename,
                        dpi=600,
                        format="pdf",
                    )
                    plt.close(fig)

            for height_suffix, height_scale in combined_stackplot_height_variants:
                if run_only_compare_plots:
                    continue
                combined_filename = os.path.join(
                    out_dir,
                    f"{cen_or_dec}_{ueu_display(ueu_short)}_stackplot_cost_co2_capacity_per_100m2{height_suffix}.pdf",
                )
                plot_combined_stackplots_for_pareto_solutions_with_peak(
                    district_sums=district_sums,
                    technologies=technologies,
                    energy_types=energy_types,
                    value_types=("cost", "co2", "capacity"),
                    figsize=(width_inch, height_inch * 3.0 * height_scale),
                    font_size=font_size,
                    show=False,
                    filename=combined_filename,
                    x_label="Pareto-optimal solution index (sorted)",
                    sort_key=None,
                    target_xticks=8,
                    peak_lw=0.5,
                    peak_drawstyle="steps-mid",
                    y_labels=Y_LABELS_PER_100M2_WRAPPED,
                    peak_label_override=PEAK_LABEL_PER_100M2_WRAPPED,
                    legend_ncol=4,
                )

            # Additional combined stackplots for alternative 2D projections:
            # (TOTEX, PEAK) and (CO2, PEAK)
            front_projection_variants = (
                ("totex_peak", "totex", "peak"),
                ("co2_peak", "co2", "peak"),
            )
            building_name_map = {bid: info["name"] for bid, info in rep_info.items()}
            if cen_or_dec == "cen":
                building_name_map["heat_grid"] = "Heat grid"

            for front_suffix, x_key, y_key in front_projection_variants:
                if run_only_compare_plots:
                    continue
                pareto_projection = get_pareto_front_for_axes(combined_front, x_key=x_key, y_key=y_key)
                if not pareto_projection:
                    print(
                        f"WARNING: Empty Pareto front for projection '{front_suffix}' in UEU "
                        f"{ueu_display(ueu_short)}. Skipping combined stackplot."
                    )
                    continue

                matches_projection = find_exact_match_in_combined_front_by_keys(
                    reduced_points=pareto_projection,
                    combined_front=combined_front,
                    x_key=x_key,
                    y_key=y_key,
                )
                if not matches_projection:
                    print(
                        f"WARNING: No matches for projection '{front_suffix}' in UEU "
                        f"{ueu_display(ueu_short)}. Skipping combined stackplot."
                    )
                    continue

                processed_projection = process_district_data(matches_projection, building_in_cluster, cen_or_dec)
                processed_projection = process_units_for_processed(
                    processed_projection,
                    floor_area=total_floor_area_all / 100.0,
                )
                district_sums_projection = calculate_sums_for_technologies_and_energy_for_a_district(
                    processed_projection,
                    energy_types,
                    technologies,
                    building_name_map,
                )

                for height_suffix, height_scale in combined_stackplot_height_variants:
                    combined_filename_projection = os.path.join(
                        out_dir,
                        f"{cen_or_dec}_{ueu_display(ueu_short)}_stackplot_cost_co2_capacity_per_100m2"
                        f"_{front_suffix}{height_suffix}.pdf",
                    )
                    plot_combined_stackplots_for_pareto_solutions_with_peak(
                        district_sums=district_sums_projection,
                        technologies=technologies,
                        energy_types=energy_types,
                        value_types=("cost", "co2", "capacity"),
                        figsize=(width_inch, height_inch * 3.0 * height_scale),
                        font_size=font_size,
                        show=False,
                        filename=combined_filename_projection,
                        x_label="Pareto-optimal solution index (sorted)",
                        sort_key=None,
                        target_xticks=8,
                        peak_lw=0.5,
                        peak_drawstyle="steps-mid",
                        y_labels=Y_LABELS_PER_100M2_WRAPPED,
                        peak_label_override=PEAK_LABEL_PER_100M2_WRAPPED,
                        legend_ncol=4,
                    )

            if run_parallel_coordinate_compare_plots:
                parallel_points_to_process = (5, 6, 7) if run_only_compare_plots else (4, 5, 6, 7)
            else:
                parallel_points_to_process = ()
            for n_points in parallel_points_to_process:
                tradeoff_keys = ("cost-co2", "cost-peak", "peak-co2")
                best_pack = None
                best_min_selected = -1
                probe_upper = n_points + 10
                found_uniform_target = False

                for probe_n in range(n_points, probe_upper + 1):
                    probe_rows, probe_anchor, probe_debug = collect_parallel_tradeoff_rows(
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
                    selected_counts = [
                        int(probe_debug.get(k, {}).get("selected_rows", 0))
                        for k in tradeoff_keys
                    ]
                    min_sel = min(selected_counts) if selected_counts else 0
                    if min_sel > best_min_selected:
                        best_min_selected = min_sel
                        best_pack = (probe_n, probe_rows, probe_anchor, probe_debug)
                    if min_sel >= n_points:
                        found_uniform_target = True
                        best_pack = (probe_n, probe_rows, probe_anchor, probe_debug)
                        break

                if best_pack is None:
                    print(
                        f"WARNING: Could not build tradeoff rows for {ueu_display(ueu_short)} "
                        f"at requested points={n_points}."
                    )
                    continue

                used_probe_n, rows_by_tradeoff, retrofit_anchor, debug_counts = best_pack

                has_parallel_rows = any(rows_by_tradeoff.get(k) for k in rows_by_tradeoff.keys())
                if has_parallel_rows:
                    for tradeoff_name in ("cost-co2", "cost-peak", "peak-co2"):
                        dbg = debug_counts.get(tradeoff_name, {})
                        print(
                            f"Parallel debug ({ueu_display(ueu_short)}, p={n_points}, {tradeoff_name}): "
                            f"front={dbg.get('front_points', 0)}, "
                            f"matches={dbg.get('matches', 0)}, "
                            f"selected={dbg.get('selected_rows', 0)}"
                        )

                    selected_counts = [
                        int(debug_counts.get(k, {}).get("selected_rows", 0))
                        for k in tradeoff_keys
                    ]
                    common_n = min(selected_counts) if selected_counts else 0
                    if common_n <= 0:
                        print(
                            f"WARNING: No common selected points for {ueu_display(ueu_short)} "
                            f"at requested points={n_points}."
                        )
                        continue

                    if (not found_uniform_target) or (common_n != n_points):
                        print(
                            f"INFO: Harmonized selected points to common_n={common_n} "
                            f"(requested={n_points}, probe_used={used_probe_n})."
                        )

                    rows_by_tradeoff = {
                        k: _downsample_rows_evenly(rows_by_tradeoff.get(k, []), common_n)
                        for k in tradeoff_keys
                    }
                    if n_points in (5, 6, 7):
                        rows_for_points = parallel_rows_compare_by_points.setdefault(n_points, {})
                        rows_for_points[ueu_display(ueu_short)] = {
                            k: [dict(row) for row in rows_by_tradeoff.get(k, [])]
                            for k in tradeoff_keys
                        }

                    for height_suffix, height_scale in combined_stackplot_height_variants:
                        if run_only_compare_plots:
                            continue
                        parallel_filename = os.path.join(
                            out_dir,
                            f"{cen_or_dec}_{ueu_display(ueu_short)}_parallel_coordinates_tradeoffs_per_100m2"
                            f"_p{n_points}{height_suffix}.pdf",
                        )
                        plot_parallel_coordinates_tradeoff_fronts(
                            rows_by_tradeoff=rows_by_tradeoff,
                            filename=parallel_filename,
                            figsize=(width_inch, height_inch * 1.90 * 0.85 * height_scale),
                            font_size=font_size,
                            requested_points_per_front=common_n,
                            plot_mode="thin_bars",
                            include_seasonal_storage=(cen_or_dec == "cen"),
                            show=False,
                        )
                    if run_only_compare_plots:
                        print(
                            f"Parallel-coordinates tradeoff data collected for {ueu_display(ueu_short)} "
                            f"(points={common_n}, requested={n_points}, retrofit depth reference={retrofit_anchor:.4g})."
                        )
                    else:
                        print(
                            f"Parallel-coordinates tradeoff plot written for {ueu_display(ueu_short)} "
                            f"(points={common_n}, requested={n_points}, retrofit depth reference={retrofit_anchor:.4g})."
                        )
                else:
                    print(
                        f"WARNING: No tradeoff rows for parallel-coordinates plot in "
                        f"{ueu_display(ueu_short)} for points={n_points}."
                    )

            print(f"Done: {ueu_display(ueu_short)}")

    compare_ueu_order = ["Low heat density", "Medium heat density", "High heat density"]
    if cen_or_dec == "cen" and centralized_strategy_fronts_per100_by_ueu:
        strategy_plot_height_variants = (
            ("_h80", 0.80),
            ("_h70", 0.70),
            ("_h60", 0.60),
            ("_h50", 0.50),
            ("_h40", 0.40),
        )
        strategy_plot_width_variants = (
            ("", 1.00),
            ("_w90", 0.90),
            ("_w80", 0.80),
            ("_w70", 0.70),
            ("_w60", 0.60),
        )
        expected_strategy_labels = [
            "50 \N{DEGREE SIGN}C min. required",
            "80 \N{DEGREE SIGN}C max. retrofit",
            "80 \N{DEGREE SIGN}C min. required",
        ]
        for strategy_ueu_label in compare_ueu_order:
            strategy_fronts_per100_for_ueu = centralized_strategy_fronts_per100_by_ueu.get(
                strategy_ueu_label,
                {},
            )
            if not strategy_fronts_per100_for_ueu:
                print(f"WARNING: No centralized strategy fronts collected for {strategy_ueu_label}.")
                continue

            ordered_strategy_fronts = {
                label: strategy_fronts_per100_for_ueu[label]
                for label in expected_strategy_labels
                if label in strategy_fronts_per100_for_ueu
            }
            missing_strategy_labels = [
                label for label in expected_strategy_labels
                if label not in strategy_fronts_per100_for_ueu
            ]
            if missing_strategy_labels:
                print(
                    f"WARNING: centralized strategy overlay missing fronts for {strategy_ueu_label}: "
                    + ", ".join(missing_strategy_labels)
                )
            if not ordered_strategy_fronts:
                continue

            strategy_out_dir = main_out_dir
            os.makedirs(strategy_out_dir, exist_ok=True)
            strategy_panel_height_factor = 1.30
            strategy_prefix = f"cen_{strategy_ueu_label}"
            for suffix, h_factor in strategy_plot_height_variants:
                for width_suffix, width_factor in strategy_plot_width_variants:
                    strategy_filename = os.path.join(
                        strategy_out_dir,
                        f"{strategy_prefix}_per_100m2"
                        f"_pareto_all_with_front_tick_highlights_strategies{suffix}{width_suffix}.pdf",
                    )
                    write_strategy_summary = suffix == "_h70" and width_suffix == ""
                    plot_strategy_points_with_front_and_tick_highlights(
                        strategy_fronts=ordered_strategy_fronts,
                        filename=strategy_filename,
                        figsize=(width_inch, height_inch * strategy_panel_height_factor * h_factor),
                        font_size=font_size,
                        xlabel=r"Ann. GWP in kg CO$_2$-eq. per 100 m$^2$",
                        ylabel=r"Ann. TOTEX in EUR per 100 m$^2$",
                        cbar_label=r"Peak grid ex. power in kW per 100 m$^2$",
                        target_xticks=8,
                        exclude_last_tick_index=True,
                        axes_width_scale=width_factor,
                        annotate_solution_indices=(
                            [0, 8, 18]
                            if strategy_ueu_label in {"Low heat density", "High heat density"}
                            else None
                        ),
                        summary_filename=(
                            os.path.splitext(strategy_filename)[0] + "_solution_summary.csv"
                            if write_strategy_summary
                            else None
                        ),
                        print_solution_summary=write_strategy_summary,
                        show=False,
                    )

            strategy_fronts_abs_for_ueu = centralized_strategy_fronts_abs_by_ueu.get(
                strategy_ueu_label,
                {},
            )
            ordered_strategy_fronts_abs = {
                label: strategy_fronts_abs_for_ueu[label]
                for label in expected_strategy_labels
                if label in strategy_fronts_abs_for_ueu
            }
            all_strategy_records_abs = [
                record
                for records in ordered_strategy_fronts_abs.values()
                for record in records
            ]
            strategy_reference_context = centralized_reference_context_by_ueu.get(strategy_ueu_label)
            if all_strategy_records_abs and strategy_reference_context:
                combined_strategy_front_abs = get_pareto_front(
                    sorted(
                        (
                            (
                                float(record["co2"]),
                                float(record["totex"]),
                                float(record.get("peak", np.nan)),
                            )
                            for record in all_strategy_records_abs
                        ),
                        key=lambda point: (point[0], point[1]),
                    )
                )
                matches_strategy_front_abs = find_exact_match_in_combined_front(
                    combined_strategy_front_abs,
                    all_strategy_records_abs,
                )
                if not matches_strategy_front_abs:
                    print(
                        "WARNING: No matches for resulting centralized strategy Pareto front "
                        f"for {strategy_ueu_label}. Skipping strategy stackplots."
                    )
                else:
                    strategy_building_in_cluster = strategy_reference_context["building_in_cluster"]
                    strategy_total_floor_area_all = strategy_reference_context["total_floor_area_all"]
                    strategy_rep_info = strategy_reference_context["rep_info"]
                    processed_strategy_data = process_district_data(
                        matches_strategy_front_abs,
                        strategy_building_in_cluster,
                        cen_or_dec,
                    )
                    processed_strategy_data = process_units_for_processed(
                        processed_strategy_data,
                        floor_area=strategy_total_floor_area_all / 100.0,
                    )
                    strategy_building_name_map = {
                        bid: info["name"]
                        for bid, info in strategy_rep_info.items()
                    }
                    strategy_building_name_map["heat_grid"] = "Heat grid"
                    for district in processed_strategy_data.values():
                        for building_name, building_data in district.items():
                            if building_name in {"co2", "peak", "totex", "electricity_grid", "heat_grid"}:
                                continue
                            if isinstance(building_data, dict):
                                strategy_building_name_map.setdefault(building_name, building_name)

                    district_sums_strategy = calculate_sums_for_technologies_and_energy_for_a_district(
                        processed_strategy_data,
                        energy_types,
                        technologies,
                        strategy_building_name_map,
                    )

                    strategy_reconciliation_rows = build_totex_reconciliation_rows(district_sums_strategy)
                    strategy_reconciliation_filename = os.path.join(
                        strategy_out_dir,
                        f"{strategy_prefix}_resulting_strategy_pareto"
                        "_totex_reconciliation_per_100m2.csv",
                    )
                    write_totex_reconciliation_csv(
                        strategy_reconciliation_filename,
                        strategy_reconciliation_rows,
                    )
                    plot_totex_reconciliation_difference(
                        strategy_reconciliation_rows,
                        filename=os.path.join(
                            strategy_out_dir,
                            f"{strategy_prefix}_resulting_strategy_pareto"
                            "_totex_reconciliation_difference_per_100m2.pdf",
                        ),
                        figsize=(width_inch, height_inch),
                        font_size=font_size,
                        show=False,
                    )

                    for vt in value_types:
                        for height_suffix, height_scale in stackplot_height_variants:
                            strategy_stackplot_filename = os.path.join(
                                strategy_out_dir,
                                f"{strategy_prefix}_resulting_strategy_pareto"
                                f"_stackplot_{vt}_per_100m2{height_suffix}.pdf",
                            )
                            fig, ax1, ax2 = plot_stackplot_for_pareto_solutions_with_peak(
                                district_sums=district_sums_strategy,
                                technologies=technologies,
                                energy_types=energy_types,
                                value_type=vt,
                                figsize=(width_inch, height_inch * height_scale),
                                font_size=font_size,
                                show=False,
                                filename=strategy_stackplot_filename,
                                x_label="Pareto-optimal solution index (sorted)",
                                sort_key=None,
                                target_xticks=8,
                                peak_lw=0.5,
                                peak_drawstyle="steps-mid",
                                legend_ncol=4,
                            )
                            ax1.set_ylabel(_linebreak_after_in_label(Y_LABELS_PER_100M2[vt]))
                            ax2.set_ylabel(PEAK_LABEL_PER_100M2_WRAPPED)
                            _savefig_fixed_pdf_width(
                                fig,
                                strategy_stackplot_filename,
                                dpi=600,
                                format="pdf",
                            )
                            plt.close(fig)

                    for height_suffix, height_scale in combined_stackplot_height_variants:
                        for axis_suffix, capacity_y_scale, y_labels in (
                            ("", "linear", Y_LABELS_PER_100M2_WRAPPED),
                            ("_log", "symlog", Y_LABELS_PER_100M2_CAPACITY_LOG_WRAPPED),
                        ):
                            strategy_combined_stackplot_filename = os.path.join(
                                strategy_out_dir,
                                f"{strategy_prefix}_resulting_strategy_pareto"
                                f"_stackplot_cost_co2_capacity_per_100m2{height_suffix}{axis_suffix}.pdf",
                            )
                            plot_combined_stackplots_for_pareto_solutions_with_peak(
                                district_sums=district_sums_strategy,
                                technologies=technologies,
                                energy_types=energy_types,
                                value_types=("cost", "co2", "capacity"),
                                figsize=(width_inch, height_inch * 3.0 * height_scale),
                                font_size=font_size,
                                show=False,
                                filename=strategy_combined_stackplot_filename,
                                x_label="Pareto-optimal solution index (sorted)",
                                sort_key=None,
                                target_xticks=8,
                                peak_lw=0.5,
                                peak_drawstyle="steps-mid",
                                y_labels=y_labels,
                                peak_label_override=PEAK_LABEL_PER_100M2_WRAPPED,
                                legend_ncol=4,
                                capacity_y_scale=capacity_y_scale,
                                capacity_symlog_linthresh=10.0,
                            )
            elif all_strategy_records_abs:
                print(
                    "WARNING: Centralized strategy records exist, but reference context is missing "
                    f"for {strategy_ueu_label}. Skipping strategy stackplots."
                )

    if cen_or_dec == "cen" and centralized_strategy_fronts_abs_by_ueu:
        for n_points in ((5, 6, 7) if run_parallel_coordinate_compare_plots else ()):
            rows_by_ueu_for_points = {}
            decentralized_rows_by_ueu_for_points = {}
            for ueu_label in compare_ueu_order:
                strategy_fronts_abs = centralized_strategy_fronts_abs_by_ueu.get(ueu_label, {})
                if not strategy_fronts_abs:
                    continue
                context = centralized_reference_context_by_ueu.get(ueu_label)
                if not context:
                    continue

                records_t50_t80 = []
                for strategy_label, records in strategy_fronts_abs.items():
                    if not (
                        strategy_label.startswith("50 ")
                        or strategy_label.startswith("80 ")
                    ):
                        continue
                    case_value = _heat_grid_retrofit_temp_case_value(strategy_label)
                    for record in records:
                        marked_record = dict(record)
                        marked_record["heat_grid_retrofit_temp_case"] = case_value
                        marked_record["heat_grid_retrofit_temp_case_label"] = strategy_label
                        records_t50_t80.append(marked_record)
                if not records_t50_t80:
                    continue

                building_name_map_cen_compare = {
                    bid: info["name"]
                    for bid, info in context["rep_info"].items()
                }
                building_name_map_cen_compare["heat_grid"] = "Heat grid"
                harmonized = build_harmonized_parallel_tradeoff_rows(
                    combined_front=records_t50_t80,
                    building_in_cluster=context["building_in_cluster"],
                    cen_or_dec=cen_or_dec,
                    total_floor_area_all=context["total_floor_area_all"],
                    energy_types=energy_types,
                    technologies=technologies,
                    building_name_map=building_name_map_cen_compare,
                    n_points=n_points,
                    rep_info=context["rep_info"],
                )
                if not harmonized or harmonized["common_n"] <= 0:
                    print(
                        "WARNING: Could not build centralized UEU parallel-coordinate "
                        f"rows for {ueu_label} at p={n_points}."
                    )
                    continue

                rows_by_ueu_for_points[ueu_label] = {
                    k: [dict(row) for row in harmonized["rows_by_tradeoff"].get(k, [])]
                    for k in ("cost-co2", "cost-peak", "peak-co2")
                }
                ueu_short_for_dec = next(
                    (
                        short
                        for short, display_label in UEU_NAME_MAP.items()
                        if display_label == ueu_label
                    ),
                    None,
                )
                if ueu_short_for_dec is None:
                    print(
                        "WARNING: Could not resolve decentralized UEU short name "
                        f"for delta plot: {ueu_label}."
                    )
                else:
                    try:
                        dec_front_dir = _latest_decentralized_reference_front_dir(
                            _default_decentralized_hypervolume_root(),
                            ueu_short_for_dec,
                        )
                        dec_front = load_combined_front_from_path(
                            Path(dec_front_dir) / "combined_front.pkl"
                        )
                        dec_front = maniupulate_combined_front_elect_grid(
                            dec_front,
                            no_electricity_grid_active,
                        )
                        dec_technologies_for_delta = [
                            tech
                            for tech in technologies
                            if tech not in {"Heat grid", "Seasonal storage"}
                        ]
                        building_name_map_dec_compare = {
                            bid: info["name"]
                            for bid, info in context["rep_info"].items()
                        }
                        harmonized_dec = build_harmonized_parallel_tradeoff_rows(
                            combined_front=dec_front,
                            building_in_cluster=context["building_in_cluster"],
                            cen_or_dec="dec",
                            total_floor_area_all=context["total_floor_area_all"],
                            energy_types=energy_types,
                            technologies=dec_technologies_for_delta,
                            building_name_map=building_name_map_dec_compare,
                            n_points=n_points,
                            rep_info=context["rep_info"],
                        )
                        if harmonized_dec and harmonized_dec["common_n"] > 0:
                            decentralized_rows_by_ueu_for_points[ueu_label] = {
                                k: [
                                    dict(row)
                                    for row in harmonized_dec["rows_by_tradeoff"].get(k, [])
                                ]
                                for k in ("cost-co2", "cost-peak", "peak-co2")
                            }
                        else:
                            print(
                                "WARNING: Could not build decentralized UEU "
                                f"parallel-coordinate rows for delta plot "
                                f"({ueu_label}, p={n_points})."
                            )
                    except Exception as exc:
                        print(
                            "WARNING: Could not load decentralized reference front "
                            f"for delta plot ({ueu_label}, p={n_points}): {exc}"
                        )
                print(
                    f"Centralized UEU parallel debug ({ueu_label}, p={n_points}): "
                    f"common_n={harmonized['common_n']}, "
                    f"probe_used={harmonized['used_probe_n']}"
                )

            missing_parallel_compare = [
                name for name in compare_ueu_order
                if name not in rows_by_ueu_for_points
            ]
            if missing_parallel_compare:
                print(
                    "WARNING: Skipping centralized stacked UEU parallel-coordinates "
                    f"comparison plot for p={n_points} (missing data for: "
                    f"{', '.join(missing_parallel_compare)})."
                )
                continue

            delta_rows_by_ueu_for_points = build_parallel_coordinate_delta_rows_by_ueu(
                centralized_rows_by_ueu=rows_by_ueu_for_points,
                decentralized_rows_by_ueu=decentralized_rows_by_ueu_for_points,
                ueu_order=compare_ueu_order,
            )
            missing_delta_compare = [
                name for name in compare_ueu_order
                if name not in delta_rows_by_ueu_for_points
            ]
            if missing_delta_compare:
                print(
                    "WARNING: Skipping centralized-minus-decentralized delta "
                    f"parallel-coordinate plot for p={n_points} (missing data for: "
                    f"{', '.join(missing_delta_compare)})."
                )

            for height_suffix, height_scale in stacked_parallel_height_variants:
                stacked_fig_height = (
                    height_inch
                    * single_parallel_height_factor
                    * 3.0
                    * stacked_parallel_reference_scale
                    * height_scale
                )
                for font_suffix, stacked_axis_font_size in stacked_parallel_font_size_variants:
                    full_axis_font_size = (
                        7.8 if font_suffix == "_fs_8" else stacked_axis_font_size
                    )
                    stacked_per_ueu_path = os.path.join(
                        main_out_dir,
                        f"cen_COMPARE_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                        f"{height_suffix}{font_suffix}_stacked_per_ueu.pdf",
                    )
                    plot_parallel_coordinates_tradeoff_fronts_stacked_ueus(
                        rows_by_ueu=rows_by_ueu_for_points,
                        ueu_order=compare_ueu_order,
                        scaling_mode="per_ueu",
                        filename=stacked_per_ueu_path,
                        figsize=(width_inch, stacked_fig_height),
                        font_size=font_size,
                        axis_font_size=stacked_axis_font_size,
                        legend_font_size=stacked_axis_font_size,
                        legend_title_font_size=font_size,
                        plot_mode="thin_bars",
                        include_seasonal_storage=True,
                        show=False,
                    )
                    print(
                        "Centralized stacked UEU parallel plot written: "
                        f"{stacked_per_ueu_path} "
                        f"(height={stacked_fig_height:.3f} in, fs={stacked_axis_font_size})"
                    )

                    stacked_per_ueu_full_path = os.path.join(
                        main_out_dir,
                        f"cen_COMPARE_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                        f"{height_suffix}{font_suffix}_stacked_per_ueu_full.pdf",
                    )
                    plot_parallel_coordinates_tradeoff_fronts_stacked_ueus(
                        rows_by_ueu=rows_by_ueu_for_points,
                        ueu_order=compare_ueu_order,
                        scaling_mode="per_ueu",
                        filename=stacked_per_ueu_full_path,
                        figsize=(width_inch, stacked_fig_height),
                        font_size=font_size,
                        axis_font_size=full_axis_font_size,
                        legend_font_size=full_axis_font_size,
                        legend_title_font_size=font_size,
                        plot_mode="thin_bars",
                        include_seasonal_storage=True,
                        include_heat_grid_totex=True,
                        subplot_left=0.095,
                        subplot_right=0.995,
                        y_label_x=-0.075,
                        show=False,
                    )
                    print(
                        "Centralized stacked UEU parallel plot with heat-grid TOTEX written: "
                        f"{stacked_per_ueu_full_path} "
                        f"(height={stacked_fig_height:.3f} in, fs={stacked_axis_font_size})"
                    )

                    stacked_per_ueu_full_2_path = os.path.join(
                        main_out_dir,
                        f"cen_COMPARE_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                        f"{height_suffix}{font_suffix}_stacked_per_ueu_full_2.pdf",
                    )
                    plot_parallel_coordinates_tradeoff_fronts_stacked_ueus(
                        rows_by_ueu=rows_by_ueu_for_points,
                        ueu_order=compare_ueu_order,
                        scaling_mode="per_ueu",
                        filename=stacked_per_ueu_full_2_path,
                        figsize=(width_inch, stacked_fig_height),
                        font_size=font_size,
                        axis_font_size=full_axis_font_size,
                        legend_font_size=full_axis_font_size,
                        legend_title_font_size=font_size,
                        plot_mode="thin_bars",
                        include_seasonal_storage=True,
                        include_heat_grid_retrofit_temp_case=True,
                        subplot_left=0.095,
                        subplot_right=0.995,
                        y_label_x=-0.075,
                        show=False,
                    )
                    print(
                        "Centralized stacked UEU parallel plot with heat-grid case written: "
                        f"{stacked_per_ueu_full_2_path} "
                        f"(height={stacked_fig_height:.3f} in, fs={full_axis_font_size})"
                    )

                    stacked_global_path = os.path.join(
                        main_out_dir,
                        f"cen_COMPARE_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                        f"{height_suffix}{font_suffix}_stacked_global_max.pdf",
                    )
                    plot_parallel_coordinates_tradeoff_fronts_stacked_ueus(
                        rows_by_ueu=rows_by_ueu_for_points,
                        ueu_order=compare_ueu_order,
                        scaling_mode="global_max",
                        filename=stacked_global_path,
                        figsize=(width_inch, stacked_fig_height),
                        font_size=font_size,
                        axis_font_size=stacked_axis_font_size,
                        legend_font_size=stacked_axis_font_size,
                        legend_title_font_size=font_size,
                        plot_mode="thin_bars",
                        include_seasonal_storage=True,
                        show=False,
                    )
                    print(
                        "Centralized stacked UEU parallel plot written: "
                        f"{stacked_global_path} "
                        f"(height={stacked_fig_height:.3f} in, fs={stacked_axis_font_size})"
                    )

                    stacked_global_full_path = os.path.join(
                        main_out_dir,
                        f"cen_COMPARE_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                        f"{height_suffix}{font_suffix}_stacked_global_max_full.pdf",
                    )
                    plot_parallel_coordinates_tradeoff_fronts_stacked_ueus(
                        rows_by_ueu=rows_by_ueu_for_points,
                        ueu_order=compare_ueu_order,
                        scaling_mode="global_max",
                        filename=stacked_global_full_path,
                        figsize=(width_inch, stacked_fig_height),
                        font_size=font_size,
                        axis_font_size=full_axis_font_size,
                        legend_font_size=full_axis_font_size,
                        legend_title_font_size=font_size,
                        plot_mode="thin_bars",
                        include_seasonal_storage=True,
                        include_heat_grid_totex=True,
                        subplot_left=0.095,
                        subplot_right=0.995,
                        y_label_x=-0.075,
                        show=False,
                    )
                    print(
                        "Centralized stacked UEU parallel plot with heat-grid TOTEX written: "
                        f"{stacked_global_full_path} "
                        f"(height={stacked_fig_height:.3f} in, fs={stacked_axis_font_size})"
                    )

                    stacked_global_full_2_path = os.path.join(
                        main_out_dir,
                        f"cen_COMPARE_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                        f"{height_suffix}{font_suffix}_stacked_global_max_full_2.pdf",
                    )
                    plot_parallel_coordinates_tradeoff_fronts_stacked_ueus(
                        rows_by_ueu=rows_by_ueu_for_points,
                        ueu_order=compare_ueu_order,
                        scaling_mode="global_max",
                        filename=stacked_global_full_2_path,
                        figsize=(width_inch, stacked_fig_height),
                        font_size=font_size,
                        axis_font_size=full_axis_font_size,
                        legend_font_size=full_axis_font_size,
                        legend_title_font_size=font_size,
                        plot_mode="thin_bars",
                        include_seasonal_storage=True,
                        include_heat_grid_retrofit_temp_case=True,
                        subplot_left=0.095,
                        subplot_right=0.995,
                        y_label_x=-0.075,
                        show=False,
                    )
                    print(
                        "Centralized stacked UEU parallel plot with heat-grid case written: "
                        f"{stacked_global_full_2_path} "
                        f"(height={stacked_fig_height:.3f} in, fs={full_axis_font_size})"
                    )
                    if not missing_delta_compare:
                        delta_stacked_global_full_2_path = os.path.join(
                            main_out_dir,
                            f"COMPARE_cen_minus_dec_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                            f"{height_suffix}{font_suffix}_stacked_global_max_full_2.pdf",
                        )
                        plot_parallel_coordinates_delta_tradeoff_fronts_stacked_ueus(
                            rows_by_ueu=delta_rows_by_ueu_for_points,
                            ueu_order=compare_ueu_order,
                            scaling_mode="global_max",
                            filename=delta_stacked_global_full_2_path,
                            figsize=(width_inch, stacked_fig_height),
                            font_size=font_size,
                            axis_font_size=full_axis_font_size,
                            legend_font_size=full_axis_font_size,
                            legend_title_font_size=font_size,
                            plot_mode="thin_bars",
                            subplot_left=0.095,
                            subplot_right=0.995,
                            y_label_x=-0.075,
                            show=False,
                        )
                        print(
                            "Centralized-minus-decentralized stacked UEU delta "
                            f"parallel plot written: {delta_stacked_global_full_2_path} "
                            f"(height={stacked_fig_height:.3f} in, fs={full_axis_font_size})"
                        )
                        delta_stacked_per_ueu_full_2_path = os.path.join(
                            main_out_dir,
                            f"COMPARE_cen_minus_dec_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                            f"{height_suffix}{font_suffix}_stacked_per_ueu_full_2.pdf",
                        )
                        plot_parallel_coordinates_delta_tradeoff_fronts_stacked_ueus(
                            rows_by_ueu=delta_rows_by_ueu_for_points,
                            ueu_order=compare_ueu_order,
                            scaling_mode="per_ueu",
                            filename=delta_stacked_per_ueu_full_2_path,
                            figsize=(width_inch, stacked_fig_height),
                            font_size=font_size,
                            axis_font_size=full_axis_font_size,
                            legend_font_size=full_axis_font_size,
                            legend_title_font_size=font_size,
                            plot_mode="thin_bars",
                            subplot_left=0.095,
                            subplot_right=0.995,
                            y_label_x=-0.075,
                            show=False,
                        )
                        print(
                            "Centralized-minus-decentralized stacked UEU delta "
                            f"parallel plot with per-UEU scaling written: "
                            f"{delta_stacked_per_ueu_full_2_path} "
                            f"(height={stacked_fig_height:.3f} in, fs={full_axis_font_size})"
                        )

    run_cross_ueu_comparison_plots = cen_or_dec != "cen" and len(ueu_list) > 1
    for n_points in ((5, 6, 7) if run_parallel_coordinate_compare_plots else ()):
        if not run_cross_ueu_comparison_plots:
            continue
        rows_by_ueu_for_points = parallel_rows_compare_by_points.get(n_points, {})
        missing_parallel_compare = [name for name in compare_ueu_order if name not in rows_by_ueu_for_points]
        if missing_parallel_compare:
            print(
                "WARNING: Skipping stacked UEU parallel-coordinates comparison plot "
                f"for p={n_points} (missing data for: {', '.join(missing_parallel_compare)})."
            )
            continue

        for height_suffix, height_scale in stacked_parallel_height_variants:
            stacked_fig_height = (
                height_inch
                * single_parallel_height_factor
                * 3.0
                * stacked_parallel_reference_scale
                * height_scale
            )

            for font_suffix, stacked_axis_font_size in stacked_parallel_font_size_variants:
                stacked_per_ueu_path = os.path.join(
                    out_dir,
                    f"{cen_or_dec}_COMPARE_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                    f"{height_suffix}{font_suffix}_stacked_per_ueu.pdf",
                )
                plot_parallel_coordinates_tradeoff_fronts_stacked_ueus(
                    rows_by_ueu=rows_by_ueu_for_points,
                    ueu_order=compare_ueu_order,
                    scaling_mode="per_ueu",
                    filename=stacked_per_ueu_path,
                    figsize=(width_inch, stacked_fig_height),
                    font_size=font_size,
                    axis_font_size=stacked_axis_font_size,
                    legend_font_size=stacked_axis_font_size,
                    legend_title_font_size=font_size,
                    plot_mode="thin_bars",
                    show=False,
                )
                print(
                    "Stacked UEU parallel plot written: "
                    f"{stacked_per_ueu_path} "
                    f"(height={stacked_fig_height:.3f} in, fs={stacked_axis_font_size})"
                )

                stacked_global_path = os.path.join(
                    out_dir,
                    f"{cen_or_dec}_COMPARE_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                    f"{height_suffix}{font_suffix}_stacked_global_max.pdf",
                )
                plot_parallel_coordinates_tradeoff_fronts_stacked_ueus(
                    rows_by_ueu=rows_by_ueu_for_points,
                    ueu_order=compare_ueu_order,
                    scaling_mode="global_max",
                    filename=stacked_global_path,
                    figsize=(width_inch, stacked_fig_height),
                    font_size=font_size,
                    axis_font_size=stacked_axis_font_size,
                    legend_font_size=stacked_axis_font_size,
                    legend_title_font_size=font_size,
                    plot_mode="thin_bars",
                    show=False,
                )
                print(
                    "Stacked UEU parallel plot written: "
                    f"{stacked_global_path} "
                    f"(height={stacked_fig_height:.3f} in, fs={stacked_axis_font_size})"
                )

                stacked_global_flow_path = os.path.join(
                    out_dir,
                    f"{cen_or_dec}_COMPARE_parallel_coordinates_tradeoffs_per_100m2_p{n_points}"
                    f"{height_suffix}{font_suffix}_stacked_global_max_flow.pdf",
                )
                plot_parallel_coordinates_tradeoff_fronts_stacked_ueus(
                    rows_by_ueu=rows_by_ueu_for_points,
                    ueu_order=compare_ueu_order,
                    scaling_mode="global_max",
                    filename=stacked_global_flow_path,
                    figsize=(width_inch, stacked_fig_height),
                    font_size=font_size,
                    axis_font_size=stacked_axis_font_size,
                    legend_font_size=stacked_axis_font_size,
                    legend_title_font_size=font_size,
                    plot_mode="thin_bars",
                    include_flow_temperature=True,
                    show=False,
                )
                print(
                    "Stacked UEU parallel plot with avg. flow temperature written: "
                    f"{stacked_global_flow_path} "
                    f"(height={stacked_fig_height:.3f} in, fs={stacked_axis_font_size})"
                )

    # AFTER LOOP: one comparison plot across UEUs
    # (ABS Pareto fronts, points colored by peak; marker shape distinguishes UEU)
    # ============================================================
    pareto_sets_abs = {
        ueu_display(ueu_short): ueu_results[ueu_display(ueu_short)]["pareto_plotdata_abs"]
        for ueu_short in ueu_results.keys()
    }

    if not run_only_compare_plots:
        plot_compare_pareto_fronts_peak(
            pareto_sets=pareto_sets_abs,
            filename=os.path.join(out_dir, f"{cen_or_dec}_COMPARE_pareto_fronts_abs_peak_colored.pdf"),
            figsize=(width_inch, height_inch),
            font_size=font_size,
            xlabel=r"Ann. GWP in kg CO$_2$-eq.",
            ylabel=r"Ann. TOTEX in EUR",
            cbar_label=r"Peak grid ex. power in kW",
            show=False,
        )
    import os
    import numpy as np
    import matplotlib.pyplot as plt

    import os
    import numpy as np
    import matplotlib.pyplot as plt

    HEAT_DENSITY_COMPARE_ORDER = [
        "Low heat density",
        "Medium heat density",
        "High heat density",
    ]
    HEAT_DENSITY_COLORS = {
        "Low heat density": "#0072B2",
        "Medium heat density": "#009E73",
        "High heat density": "#D55E00",
    }
    HEAT_DENSITY_LEGEND_LABELS = {
        "Low heat density": "Low heat density",
        "Medium heat density": "Medium heat density",
        "High heat density": "High heat density",
    }
    PARETO_FRONT_LINE_COLORS = {
        "Low heat density": "#CC79A7",
        "Medium heat density": "#56B4E9",
        "High heat density": "#B39DDB",
    }
    PARETO_FRONT_LINE_STYLES = {
        "Low heat density": ":",
        "Medium heat density": "-.",
        "High heat density": "--",
    }
    PARETO_FRONT_LINE_WIDTH = 1.14

    def _ordered_heat_density_keys(keys):
        keys = list(keys)
        ordered = [k for k in HEAT_DENSITY_COMPARE_ORDER if k in keys]
        ordered.extend(k for k in keys if k not in ordered)
        return ordered

    def _compare_totex_ylabel(label):
        return str(label).replace("Ann. TOTEX in ", "Ann. TOTEX in\n", 1)

    def plot_compare_per100_perhh_pareto_fronts_peak(
            ueu_results,
            filename,
            figsize=(8, 4),
            font_size=9,
            font_family="TeX Gyre Termes",
            ueu_order=None,
            color_by_density=False,
            connect_fronts=False,
            overlay_density_front_lines=False,
            # axis labels
            xlabel_per100=r"Ann. GWP in kg CO$_2$-eq. per 100 m$^2$",
            ylabel_per100=r"Ann. TOTEX in EUR per 100 m$^2$",
            xlabel_perhh=r"Ann. GWP in kg CO$_2$-eq. per household",
            ylabel_perhh=r"Ann. TOTEX in EUR per household",
            # colorbar labels
            cbar_label_per100=r"Peak grid ex. power in kW per 100 m$^2$",
            cbar_label_perhh=r"Peak grid ex. power in kW per household",
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
        content_font_size = 8
        plt.style.use("default")
        plt.rcParams.update({
            "font.family": font_family,
            "font.size": content_font_size,
            "axes.labelsize": content_font_size,
            "xtick.labelsize": content_font_size,
            "ytick.labelsize": content_font_size,
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
        ueu_keys = _ordered_heat_density_keys(ueu_order or ueu_results.keys())
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
            gridspec_kw={"wspace": 1.12}
        )

        def scatter(ax, data, vmin, vmax):
            sc = None
            for k in ueu_keys:
                x, y, p = data[k]
                if len(x):
                    if color_by_density:
                        order = np.argsort(x)
                        color = HEAT_DENSITY_COLORS.get(k, "#4D4D4D")
                        if connect_fronts:
                            ax.plot(
                                x[order],
                                y[order],
                                color=PARETO_FRONT_LINE_COLORS.get(k, "#4D4D4D"),
                                linestyle=PARETO_FRONT_LINE_STYLES.get(k, "-"),
                                linewidth=PARETO_FRONT_LINE_WIDTH,
                                alpha=0.85,
                                zorder=2,
                            )
                        ax.scatter(
                            x,
                            y,
                            color=color,
                            s=14,
                            marker=marker_map[k],
                            edgecolors="white",
                            linewidths=0.25,
                            alpha=0.86,
                            zorder=3,
                        )
                    else:
                        sc = ax.scatter(
                            x, y,
                            c=p, cmap=cmap, vmin=vmin, vmax=vmax,
                            s=15,
                            marker=marker_map[k],
                            edgecolors="none",  # <- no black outline
                            linewidths=0.0,
                            zorder=3,
                        )
            ax.grid(True, alpha=0.25)
            ax.margins(x=0.0, y=0.0)
            return sc

        def overlay_front_lines(ax, data):
            for k in ueu_keys:
                x, y, _ = data[k]
                if len(x):
                    order = np.argsort(x)
                    ax.plot(
                        x[order],
                        y[order],
                        color=PARETO_FRONT_LINE_COLORS.get(k, "#4D4D4D"),
                        linestyle=PARETO_FRONT_LINE_STYLES.get(k, "-"),
                        linewidth=PARETO_FRONT_LINE_WIDTH,
                        alpha=0.95,
                        zorder=7,
                    )

        sc_per100 = scatter(axes[0], panels["per100"], *vlims["per100"])
        axes[0].set_xlabel(_linebreak_after_in_label(xlabel_per100))
        axes[0].set_ylabel(_compare_totex_ylabel(ylabel_per100))

        sc_perhh = scatter(axes[1], panels["perhh"], *vlims["perhh"])
        axes[1].set_xlabel(_linebreak_after_in_label(xlabel_perhh))
        axes[1].set_ylabel(_compare_totex_ylabel(ylabel_perhh))

        if overlay_density_front_lines and not color_by_density:
            overlay_front_lines(axes[0], panels["per100"])
            overlay_front_lines(axes[1], panels["perhh"])

        if debug_print:
            print("---- AXIS LIMITS AFTER SNAPPING ----")

        _apply_nice_axis_using_data(axes[0], panel_ranges["per100"]["x"], panel_ranges["per100"]["y"], ntarget=5)
        _apply_nice_axis_using_data(axes[1], panel_ranges["perhh"]["x"], panel_ranges["perhh"]["y"], ntarget=5)
        for ax in axes:
            ax.tick_params(axis="both", labelsize=content_font_size)
            ax.xaxis.label.set_size(content_font_size)
            ax.yaxis.label.set_size(content_font_size)

        # -----------------------------
        # LEGEND (markers, black)
        # -----------------------------
        marker_legend_handles = [
            Line2D(
                [0], [0],
                marker=marker_map[k],
                linestyle="None",
                markerfacecolor=HEAT_DENSITY_COLORS.get(k, "none") if color_by_density else "none",
                markeredgecolor="black",
                color="black",
                markersize=5,
                label=HEAT_DENSITY_LEGEND_LABELS.get(k, k),
            )
            for k in ueu_keys
        ]
        line_legend_handles = []
        if connect_fronts or overlay_density_front_lines:
            line_legend_handles = [
                Line2D(
                    [0], [0],
                    linestyle=PARETO_FRONT_LINE_STYLES.get(k, "-"),
                    linewidth=PARETO_FRONT_LINE_WIDTH,
                    color=PARETO_FRONT_LINE_COLORS.get(k, "#4D4D4D"),
                    label="Pareto front",
                )
                for k in ueu_keys
            ]
        legend_handles = marker_legend_handles + line_legend_handles
        if line_legend_handles:
            # Matplotlib fills multi-column legends column-wise. With 2 columns,
            # this gives 3 rows: heat-density marker at left, matching front at right.
            legend_ncol_effective = 2
            legend_bbox = (0.5, 0.965)
            legend_columnspacing = 0.90
            legend_labelspacing = 0.24
            legend_handlelength = 1.35
        else:
            legend_ncol_effective = min(legend_ncol, len(legend_handles))
            legend_bbox = (0.5, 0.985)
            legend_columnspacing = 1.35
            legend_labelspacing = 0.30
            legend_handlelength = 1.55

        fig.legend(
            handles=legend_handles,
            frameon=False,
            loc="upper center",
            bbox_to_anchor=legend_bbox,
            ncol=legend_ncol_effective,
            columnspacing=legend_columnspacing,
            handlelength=legend_handlelength,
            handletextpad=0.45,
            labelspacing=legend_labelspacing,
            fontsize=font_size,
        )

        fig.subplots_adjust(
            left=0.155,
            right=0.875,
            bottom=0.26,
            top=0.66 if line_legend_handles else 0.74,
            wspace=0.76,
        )

        # -----------------------------
        # COLORBARS (default ticks, no "nice ending")
        # -----------------------------
        for ax, sc, label in zip(
                axes,
                [sc_per100, sc_perhh],
            [cbar_label_per100, cbar_label_perhh],
        ):
            if sc is not None and not color_by_density:
                cbar = fig.colorbar(sc, ax=ax, pad=0.012, shrink=0.90, fraction=0.040)
                cbar.set_label(_linebreak_after_in_label(label), fontsize=content_font_size)
                _apply_integer_colorbar_ticks(cbar)
                cbar.ax.yaxis.labelpad = 1
                cbar.ax.tick_params(labelsize=content_font_size)

        try:
            _savefig_fixed_pdf_width(fig, filename, dpi=dpi)
        except PermissionError:
            fallback_path = Path(filename)
            fallback_filename = fallback_path.with_name(
                f"{fallback_path.stem}_updated{fallback_path.suffix}"
            )
            _savefig_fixed_pdf_width(fig, fallback_filename, dpi=dpi)
            print(
                "WARNING: Could not overwrite locked PDF. "
                f"Wrote updated plot to: {fallback_filename}"
            )
        if show:
            plt.show()
        else:
            plt.close(fig)


    def plot_compare_per100_perhh_small_multiples_by_density(
            ueu_results,
            filename,
            figsize=(8, 5),
            font_size=9,
            font_family="TeX Gyre Termes",
            xlabel_per100=r"Ann. GWP in kg CO$_2$-eq. per 100 m$^2$",
            ylabel_per100=r"Ann. TOTEX in EUR per 100 m$^2$",
            xlabel_perhh=r"Ann. GWP in kg CO$_2$-eq. per household",
            ylabel_perhh=r"Ann. TOTEX in EUR per household",
            dpi=600,
            show=False,
    ):
        import numpy as np
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter

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

        ueu_keys = _ordered_heat_density_keys(ueu_results.keys())
        panels = {"per100": {}, "perhh": {}}
        for k in ueu_keys:
            r = ueu_results[k]
            for key, name in [
                ("per100", "pareto_plotdata_per100"),
                ("perhh", "pareto_plotdata_per_household"),
            ]:
                panels[key][k] = (
                    np.asarray(r[name]["co2"], float),
                    np.asarray(r[name]["totex"], float),
                )

        def _finite_minmax(values):
            values = np.asarray(values, float)
            values = values[np.isfinite(values)]
            if values.size == 0:
                return 0.0, 1.0
            return float(values.min()), float(values.max())

        def _nice_125_step(span, ntarget=5):
            if span <= 0 or not np.isfinite(span):
                return 1.0
            raw = span / max(ntarget - 1, 1)
            exp = np.floor(np.log10(raw))
            frac = raw / (10 ** exp)
            mult = 1 if frac <= 1 else 2 if frac <= 2 else 5 if frac <= 5 else 10
            return mult * (10 ** exp)

        def _nice_ticks_and_limits(vmin, vmax, ntarget=5):
            if vmin == vmax:
                delta = 1.0 if np.isclose(vmin, 0.0) else abs(vmin) * 0.1
                vmin, vmax = vmin - delta, vmax + delta
            step = _nice_125_step(vmax - vmin, ntarget=ntarget)
            vmin_n = np.floor(vmin / step) * step
            vmax_n = np.ceil(vmax / step) * step
            ticks = np.arange(vmin_n, vmax_n + 0.5 * step, step)
            ticks[np.isclose(ticks, 0.0)] = 0.0
            return ticks, vmin_n, vmax_n

        def _fmt_number(x, pos=None):
            if np.isclose(x, round(x)):
                return f"{int(round(x))}"
            return f"{x:.4f}".rstrip("0").rstrip(".")

        axis_limits = {}
        for panel_key in ("per100", "perhh"):
            all_x = [panels[panel_key][k][0] for k in ueu_keys if panels[panel_key][k][0].size]
            all_y = [panels[panel_key][k][1] for k in ueu_keys if panels[panel_key][k][1].size]
            x_min, x_max = _finite_minmax(np.concatenate(all_x) if all_x else [0.0, 1.0])
            y_min, y_max = _finite_minmax(np.concatenate(all_y) if all_y else [0.0, 1.0])
            xticks, xmin, xmax = _nice_ticks_and_limits(x_min, x_max)
            yticks, ymin, ymax = _nice_ticks_and_limits(y_min, y_max)
            axis_limits[panel_key] = (xmin, xmax, ymin, ymax, xticks, yticks)

        fig, axes = plt.subplots(
            nrows=len(ueu_keys),
            ncols=2,
            figsize=figsize,
            sharex="col",
            sharey="col",
            gridspec_kw={"hspace": 0.16, "wspace": 0.28},
        )
        if len(ueu_keys) == 1:
            axes = np.asarray([axes])

        formatter = FuncFormatter(_fmt_number)
        for row_idx, ueu_key in enumerate(ueu_keys):
            color = HEAT_DENSITY_COLORS.get(ueu_key, "#4D4D4D")
            for col_idx, panel_key in enumerate(("per100", "perhh")):
                ax = axes[row_idx, col_idx]
                x, y = panels[panel_key][ueu_key]
                if x.size:
                    order = np.argsort(x)
                    ax.plot(x[order], y[order], color=color, linewidth=1.0, alpha=0.80)
                    ax.scatter(
                        x,
                        y,
                        color=color,
                        s=16,
                        edgecolors="white",
                        linewidths=0.25,
                        alpha=0.88,
                    )
                xmin, xmax, ymin, ymax, xticks, yticks = axis_limits[panel_key]
                ax.set_xlim(xmin, xmax)
                ax.set_ylim(ymin, ymax)
                ax.set_xticks(xticks)
                ax.set_yticks(yticks)
                ax.xaxis.set_major_formatter(formatter)
                ax.yaxis.set_major_formatter(formatter)
                ax.grid(True, alpha=0.24, linewidth=0.6)
                if col_idx == 0:
                    ax.set_ylabel(_compare_totex_ylabel(ylabel_per100))
                    ax.text(
                        0.02,
                        0.95,
                        ueu_key,
                        transform=ax.transAxes,
                        ha="left",
                        va="top",
                        color=color,
                        fontweight="bold",
                    )
                else:
                    ax.set_ylabel(_compare_totex_ylabel(ylabel_perhh))
                if row_idx == len(ueu_keys) - 1:
                    ax.set_xlabel(xlabel_per100 if panel_key == "per100" else xlabel_perhh)

        fig.tight_layout()
        _savefig_fixed_pdf_width(fig, filename, dpi=dpi)
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
        xlabel_abs=r"Ann. GWP in kg CO$_2$-eq.",
        ylabel_abs=r"Ann. TOTEX in EUR",
        xlabel_per100=r"Ann. GWP in kg CO$_2$-eq. per 100 m$^2$",
        ylabel_per100=r"Ann. TOTEX in EUR per 100 m$^2$",
        xlabel_perhh=r"Ann. GWP in kg CO$_2$-eq. per household",
        ylabel_perhh=r"Ann. TOTEX in EUR per household",
        # colorbar labels
        cbar_label_abs=r"Peak grid ex. power in kW",
        cbar_label_per100=r"Peak grid ex. power in kW per 100 m$^2$",
        cbar_label_perhh=r"Peak grid ex. power in kW per household",
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
        ueu_keys = _ordered_heat_density_keys(ueu_results.keys())
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
            gridspec_kw={"wspace": 0.58}
        )

        def scatter(ax, data, vmin, vmax):
            sc = None
            for k in ueu_keys:
                x, y, p = data[k]
                if len(x):
                    sc = ax.scatter(
                        x, y,
                        c=p, cmap=cmap, vmin=vmin, vmax=vmax,
                        s=15,
                        marker=marker_map[k],
                        #edgecolors="black",
                        linewidths=0.1,
                    )
            ax.grid(True, alpha=0.25)
            ax.margins(x=0.0, y=0.0)  # extra safety: no autoscale padding
            return sc

        sc1 = scatter(axes[0], panels["abs"], *vlims["abs"])
        axes[0].set_xlabel(_linebreak_after_in_label(xlabel_abs))
        axes[0].set_ylabel(_compare_totex_ylabel(ylabel_abs))

        sc2 = scatter(axes[1], panels["per100"], *vlims["per100"])
        axes[1].set_xlabel(_linebreak_after_in_label(xlabel_per100))
        axes[1].set_ylabel(_compare_totex_ylabel(ylabel_per100))

        sc3 = scatter(axes[2], panels["perhh"], *vlims["perhh"])
        axes[2].set_xlabel(_linebreak_after_in_label(xlabel_perhh))
        axes[2].set_ylabel(_compare_totex_ylabel(ylabel_perhh))

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
                markersize=5,
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
            bbox_to_anchor=(0.5, 0.98),
            columnspacing=0.85,
            handletextpad=0.35,
            handlelength=1.15,
        )

        # Three panels plus three colorbars are tight on 11.8 cm. Reserve fixed
        # top/bottom space instead of letting tight_layout stretch the PDF.
        fig.subplots_adjust(left=0.105, right=0.925, bottom=0.31, top=0.74, wspace=0.82)

        # -----------------------------
        # COLORBARS
        # -----------------------------
        for ax, sc, label in zip(
            axes,
            [sc1, sc2, sc3],
            [cbar_label_abs, cbar_label_per100, cbar_label_perhh],
        ):
            if sc is not None:
                cbar = fig.colorbar(sc, ax=ax, pad=0.010, shrink=0.72, fraction=0.028)
                cbar.set_label(_linebreak_after_in_label(label), fontsize=font_size - 1)
                _apply_integer_colorbar_ticks(cbar)
                cbar.ax.yaxis.labelpad = 1
                cbar.ax.tick_params(labelsize=font_size - 1)
                if False:
                    _apply_nice_cbar(cbar, ntarget=5)

        _savefig_fixed_pdf_width(fig, filename, dpi=dpi)
        if show:
            plt.show()
        else:
            plt.close(fig)


    if run_cross_ueu_comparison_plots:
        compare_pareto_height_variants = [
            ("_h100", 1.00),
            ("_h90", 0.90),
            ("_h80", 0.80),
            ("_h70", 0.70),
            ("_h60", 0.60),
        ]
        compare_pareto_width = width_inch
        compare_pareto_base_height = height_inch * 0.77

        for height_suffix, height_scale in compare_pareto_height_variants:
            compare_fig_height = compare_pareto_base_height * height_scale

            plot_compare_per100_perhh_pareto_fronts_peak(
                ueu_results=ueu_results,
                filename=os.path.join(
                    out_dir,
                    f"{cen_or_dec}_COMPARE_abs_vs_per100_vs_perhh_pareto_fronts_peak_colored{height_suffix}.pdf",
                ),
                figsize=(compare_pareto_width, compare_fig_height),
                font_size=font_size,
                ueu_order=HEAT_DENSITY_COMPARE_ORDER,
                legend_ncol=3,
                show=False,
            )
            plot_compare_per100_perhh_pareto_fronts_peak(
                ueu_results=ueu_results,
                filename=os.path.join(
                    out_dir,
                    f"{cen_or_dec}_COMPARE_abs_vs_per100_vs_perhh_pareto_fronts_peak_colored_front_lines"
                    f"{height_suffix}.pdf",
                ),
                figsize=(compare_pareto_width, compare_fig_height),
                font_size=font_size,
                ueu_order=HEAT_DENSITY_COMPARE_ORDER,
                overlay_density_front_lines=True,
                legend_ncol=3,
                show=False,
            )
            if not run_only_compare_plots:
                plot_compare_per100_perhh_pareto_fronts_peak(
                    ueu_results=ueu_results,
                    filename=os.path.join(
                        out_dir,
                        f"{cen_or_dec}_COMPARE_per100_vs_perhh_pareto_fronts_heat_density_lines{height_suffix}.pdf",
                    ),
                    figsize=(compare_pareto_width, compare_fig_height),
                    font_size=font_size,
                    ueu_order=HEAT_DENSITY_COMPARE_ORDER,
                    color_by_density=True,
                    connect_fronts=True,
                    legend_ncol=3,
                    show=False,
                )
                plot_compare_per100_perhh_small_multiples_by_density(
                    ueu_results=ueu_results,
                    filename=os.path.join(
                        out_dir,
                        f"{cen_or_dec}_COMPARE_per100_vs_perhh_pareto_fronts_heat_density_small_multiples{height_suffix}.pdf",
                    ),
                    figsize=(compare_pareto_width, compare_fig_height * 1.7),
                    font_size=font_size,
                    show=False,
                )
