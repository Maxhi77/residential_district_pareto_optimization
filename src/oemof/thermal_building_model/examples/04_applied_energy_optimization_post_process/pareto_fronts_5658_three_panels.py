"""Three side-by-side Pareto-front panels for UEU DENI03403000SEC5658.

Default: 3 panels show the three CENTRALIZED temperature/retrofit strategies
(t50/cmin, t80/cmax, t80/cmin) separately, always compared against the SAME
DECENTRALIZED annual GWP--annual TOTEX front. This is NOT a three-objective
projection figure: all three panels use the same two objective axes and limits.

Common legend above: centralized = orange dotted; decentralized = blue dashed.
PDF width fixed at 11.8 cm; exports several overall figure heights.
Input paths, floor-area normalisation, and heat-grid corrections mirror the
preceding pareto_fronts_5658_dec_cen_heights.py script.

Run: python pareto_fronts_5658_three_panels.py
For a figure with the *combined* central front repeated in 3 panels instead:
    python pareto_fronts_5658_three_panels.py --panel-mode repeat-combined
(Note: repeated panels have identical data and shared limits; the only difference
 is their panel title. This option reproduces the three-across visual reference.)

Requires: numpy, matplotlib, geopandas for GeoPackage-based area calculation.
All input pickle files must be trusted, locally produced optimization results.
"""

from __future__ import annotations

import argparse
import copy
import os
import pickle
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

import matplotlib.pyplot as plt
import numpy as np

UEU = "DENI03403000SEC5658"
UEU_FOLDER = f"processed_bds_in_{UEU}"
CENTRALIZED_CLUSTER = "combined_cluster_sfh_reference_mfh_reference"
CENTRALIZED_CASES = (
    ("t50", "cmin"),
    ("t80", "cmax"),
    ("t80", "cmin"),
)

# Exactly the plotting-page width and reference height in the supplied script.
PDF_WIDTH_CM = 11.8
BASE_HEIGHT_CM = 6.5 * 1.34  # 8.71 cm at h100, as preceding script
HEIGHT_VARIANTS = {
    "h100": 1.00,
    "h90": 0.90,
    "h80": 0.80,
    "h70": 0.70,
    "h60": 0.60,
    "h50": 0.50,
    "h40": 0.40,
}
FONT_FAMILY = "TeX Gyre Termes"
FONT_SIZE = 9
DPI = 600

# Taken from the original script's Seaborn colorblind fallback palette:
COLOR_DEC = "#0173B2"   # colorblind palette[0], blue
COLOR_CEN = "#D55E00"   # colorblind palette[3], orange/red

X_LABEL = r"Ann. GWP in kg CO$_2$-eq. per 100 m$^2$"
Y_LABEL = r"Ann. TOTEX in EUR per 100 m$^2$"

# Optional hard-coded paths: leave as None to use original script defaults.
EXAMPLES_ROOT_OVERRIDE = None
DECENTRALIZED_PKL_OVERRIDE = None
CENTRALIZED_ROOT_OVERRIDE = None
HEAT_GRID_PLANNING_DIR_OVERRIDE = None
GPKG_OVERRIDE = None
OUTPUT_DIR_OVERRIDE = None
FLOOR_AREA_M2_OVERRIDE = None  # use only if the UEU gpkg is not accessible


def path_or_none(value):
    return Path(value).expanduser() if value else None


def find_examples_root(cli_value=None):
    explicit = path_or_none(cli_value or EXAMPLES_ROOT_OVERRIDE or os.getenv("EXAMPLES_ROOT"))
    if explicit is not None:
        return explicit
    script_dir = Path(__file__).resolve().parent
    for candidate in (script_dir, *script_dir.parents):
        if (candidate / "03_applied_energy_optimization").exists():
            return candidate
    # Same relationship as supplied script: __file__.parent.parent
    return script_dir.parent


def decentralized_path(examples_root, override=None):
    value = path_or_none(override or DECENTRALIZED_PKL_OVERRIDE)
    if value is not None:
        return value / "combined_front.pkl" if value.is_dir() else value
    return (
        examples_root / "03_applied_energy_optimization" / UEU_FOLDER
        / "post_processed_dec_k_combinations_2026_04_30"
        / "sfh_reference_mfh_reference" / "combined_front.pkl"
    )


def centralized_root(override=None):
    value = path_or_none(
        override or CENTRALIZED_ROOT_OVERRIDE
        or os.getenv("CENTRALIZED_POST_PROCESSED_ROOT")
    )
    if value is not None:
        return value
    candidates = [
        Path("/jump/mh/centralized_post_processed"),
        Path.home() / "centralized_post_processed",
        Path(r"M:\04_ArchivMA\Hillen Maximilian\Veröffentlichungen\UEU\centralized_post_processed"),
        Path(__file__).resolve().parent / "centralized" / "centralized_post_processed",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[2] if os.name == "nt" else candidates[0]


def heat_grid_dir(override=None):
    value = path_or_none(
        override or HEAT_GRID_PLANNING_DIR_OVERRIDE
        or os.getenv("HEAT_GRID_PLANNING_DIR")
    )
    if value is not None:
        return value
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / "centralized" / "heat_grid_planning",
        script_dir.parent / "centralized" / "heat_grid_planning",
    ]
    return next((path for path in candidates if path.exists()), candidates[0])


def load_pickle_front(path):
    if not path.is_file():
        raise FileNotFoundError(f"Input front not found: {path}")
    with path.open("rb") as fh:
        data = pickle.load(fh)  # Only load your own trusted optimization pickles.

    def is_front(obj):
        return isinstance(obj, list) and (
            not obj or (isinstance(obj[0], dict)
                        and {"co2", "totex", "peak"}.issubset(obj[0]))
        )

    if is_front(data):
        front = data
    elif isinstance(data, (list, tuple)):
        candidates = ([data[2]] if len(data) > 2 else []) + list(data)
        front = next((item for item in candidates if is_front(item)), None)
    elif isinstance(data, dict):
        candidates = [data.get("centralized_front"), data.get("combined_front")]
        candidates.extend(data.values())
        front = next((item for item in candidates if is_front(item)), None)
    else:
        front = None
    if front is None or not front:
        raise ValueError(f"No nonempty Pareto record list in {path}")
    return copy.deepcopy(front)


# Same semantics as the original 'summary' sheet parser; no openpyxl required.
_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def read_xlsx_summary(path):
    with ZipFile(path) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ET.fromstring(z.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in si.findall(".//main:t", _NS))
                       for si in shared.findall("main:si", _NS)]
        book = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in rels.findall("rel:Relationship", _NS)}
        target = None
        for sheet in book.findall(".//main:sheet", _NS):
            if sheet.attrib.get("name") == "summary":
                rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
                target = targets[rid]
        if target is None:
            raise ValueError(f"Missing 'summary' worksheet in {path}")
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        root = ET.fromstring(z.read(target))

    rows = []
    for r in root.findall(".//main:sheetData/main:row", _NS):
        cells = {}
        for cell in r.findall("main:c", _NS):
            letters = "".join(c for c in cell.attrib["r"] if c.isalpha())
            index = 0
            for letter in letters:
                index = index * 26 + ord(letter.upper()) - ord("A") + 1
            index -= 1
            if cell.attrib.get("t") == "inlineStr":
                value = "".join(t.text or "" for t in cell.findall(".//main:t", _NS))
            else:
                v = cell.find("main:v", _NS)
                value = "" if v is None else (v.text or "")
                if cell.attrib.get("t") == "s" and value:
                    value = strings[int(value)]
            cells[index] = value
        rows.append(cells)
    if not rows:
        raise ValueError(f"Empty 'summary' worksheet in {path}")
    header = rows[0]
    return [{header[k]: record.get(k, "") for k in header} for record in rows[1:]]


def load_heat_grid_overrides(base_dir):
    path = base_dir / f"fictional_heat_grid_costs_{UEU}_reference_reference.xlsx"
    if not path.exists():
        raise FileNotFoundError(
            f"Required centralized heat-grid-planning override XLSX missing: {path}\n"
            "Set --heat-grid-dir to the folder used in the original script. "
            "No uncorrected fallback is used to avoid changing the central Pareto front."
        )
    rows = read_xlsx_summary(path)
    result = {}
    required = {"ueu_case", "temperature_level", "refurbishment_scenario",
                "total_capex_eur_annualized", "total_gwp_kg_co2_eq_annualized"}
    for row in rows:
        if not required.issubset(row):
            raise ValueError(f"Missing required summary columns in {path}")
        if UEU not in str(row["ueu_case"]):
            continue
        case = f"{row['temperature_level']}_{row['refurbishment_scenario']}"
        result[case] = (float(row["total_capex_eur_annualized"]),
                        float(row["total_gwp_kg_co2_eq_annualized"]))
    missing = [f"{temperature}_{retrofit}" for temperature, retrofit in CENTRALIZED_CASES
               if f"{temperature}_{retrofit}" not in result]
    if missing:
        raise ValueError(f"No override for {missing} in {path}")
    return result


def apply_heat_grid_override(records, case, corrected):
    # Same record-level annual TOTEX/GWP adjustment as the original script.
    new_cost, new_gwp = corrected
    for r in records:
        selection = r.get("selection", {})
        heat_grid = selection.get("heat_grid")
        if not isinstance(heat_grid, dict):
            raise ValueError(f"Missing selection['heat_grid'] for {case}")
        parts = [value for key, value in heat_grid.items()
                 if isinstance(key, str) and key.startswith("heat_grid_investment")
                 and isinstance(value, dict)]
        old_cost = sum(float(part.get("investment_cost", 0) or 0) for part in parts)
        old_gwp = sum(float(part.get("investment_co2", 0) or 0) for part in parts)
        r["totex"] = float(r["totex"]) + new_cost - old_cost
        r["co2"] = float(r["co2"]) + new_gwp - old_gwp
    print(f"  Heat-grid override {case}: TOTEX = {new_cost:,.2f} EUR/a; "
          f"GWP = {new_gwp:,.2f} kg CO2-eq./a")
    return records


def load_floor_area(examples_root, gpkg_override=None, floor_area_override=None):
    if floor_area_override is not None:
        area = float(floor_area_override)
        if not np.isfinite(area) or area <= 0:
            raise ValueError("--floor-area must be positive")
        return area
    gpkg = path_or_none(gpkg_override or GPKG_OVERRIDE)
    if gpkg is None:
        gpkg = (examples_root / "03_applied_energy_optimization" / UEU_FOLDER
                / f"{UEU_FOLDER}.gpkg")
    if not gpkg.exists():
        raise FileNotFoundError(
            f"UEU GeoPackage not found: {gpkg}\n"
            "Provide --gpkg PATH or --floor-area VALUE (m²)."
        )
    import geopandas as gpd
    df = gpd.read_file(gpkg)
    if "net_floor_area" not in df:
        raise KeyError(f"Column 'net_floor_area' missing in {gpkg}")
    # Equivalent to the original SFH+MFH reference-building stock.
    if "tabula_building_type" not in df:
        raise KeyError(f"Column 'tabula_building_type' missing in {gpkg}")
    df = df.loc[df["tabula_building_type"].isin(["SFH", "MFH"])]
    area = float(df["net_floor_area"].sum())
    if area <= 0 or not np.isfinite(area):
        raise ValueError(f"Invalid floor area from {gpkg}: {area}")
    return area


def pareto_front_co2_totex(records, area_m2):
    # The original get_pareto_front(data_2d) uses the strictly descending
    # TOTEX envelope of points sorted by (co2, totex).
    scale = float(area_m2) / 100.0
    points = []
    for rec in records:
        x = float(rec["co2"]) / scale
        y = float(rec["totex"]) / scale
        if np.isfinite(x) and np.isfinite(y):
            points.append((x, y))
    if not points:
        raise ValueError("No finite (co2, totex) records")
    points.sort(key=lambda point: (point[0], point[1]))
    envelope = []
    best_cost = float("inf")
    for x, y in points:
        if y < best_cost:
            envelope.append((x, y))
            best_cost = y
    return np.asarray(envelope, dtype=float)


def set_style():
    # Journal font setup matching the supplied example.
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": FONT_FAMILY,
        "font.size": FONT_SIZE,
        "axes.titlesize": 8,
        "axes.labelsize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": FONT_SIZE,
        "mathtext.fontset": "cm",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def padded_bounds(arrays, axis):
    """Identical physical axis limits across all three plots."""
    vals = np.concatenate([a[:, axis] for a in arrays])
    vals = vals[np.isfinite(vals)]
    if not len(vals):
        raise ValueError("No finite Pareto-front data for axis limits")
    vmin, vmax = float(np.min(vals)), float(np.max(vals))
    extra = max(0.055 * (vmax - vmin), 0.055 * max(abs(vmax), 1.0))
    return vmin - extra, vmax + extra


PANEL_TITLES = {
    "t50_cmin": r"$50\,^\circ\mathrm{C}$ / min. retrofit",
    "t80_cmax": r"$80\,^\circ\mathrm{C}$ / max. retrofit",
    "t80_cmin": r"$80\,^\circ\mathrm{C}$ / min. retrofit",
}


def plot_three_panels(front_dec, cen_fronts_by_case, output_dir, height_variants,
                      panel_mode="strategies", png=False):
    """Export 3-column, common-legend PDFs at exactly 11.8 cm width.

    strategies (default): decentralized vs one centralized STRATEGY per panel.
    repeat-combined: repeat combined central vs decentralized in three panels.
                     Useful only for visual inspection of the 3-column layout.
    """
    if panel_mode not in {"strategies", "repeat-combined"}:
        raise ValueError(f"Unknown panel mode: {panel_mode}")
    if set(cen_fronts_by_case) != set(PANEL_TITLES):
        raise ValueError("Expected exactly the centralized cases t50_cmin, t80_cmax, t80_cmin")

    set_style()
    case_order = ["t50_cmin", "t80_cmax", "t80_cmin"]
    combined_cen = pareto_front_of_points(np.concatenate(
        [cen_fronts_by_case[case] for case in case_order], axis=0))

    if panel_mode == "strategies":
        axes_data = [(PANEL_TITLES[case], cen_fronts_by_case[case]) for case in case_order]
    else:
        axes_data = [(label, combined_cen) for label in ("(a)", "(b)", "(c)")]

    # The bounds do not depend on height, guaranteeing scientific comparability.
    all_fronts = [front_dec] + [cen_fronts_by_case[case] for case in case_order]
    xlim = padded_bounds(all_fronts, 0)
    ylim = padded_bounds(all_fronts, 1)

    output_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for suffix, factor in height_variants.items():
        fig_height_cm = BASE_HEIGHT_CM * factor
        fig, axes = plt.subplots(1, 3, figsize=(PDF_WIDTH_CM / 2.54,
                                                 fig_height_cm / 2.54),
                                 sharex=True, sharey=True)
        for ax, (title, front_cen) in zip(axes, axes_data):
            # Only the two Pareto-front curves: no scatter, colourbars or projections.
            ax.plot(front_cen[:, 0], front_cen[:, 1],
                    color=COLOR_CEN, linestyle=":", linewidth=1.35,
                    dash_capstyle="round", zorder=3)
            ax.plot(front_dec[:, 0], front_dec[:, 1],
                    color=COLOR_DEC, linestyle="--", linewidth=1.35,
                    zorder=2)
            ax.set_xlim(xlim)
            ax.set_ylim(ylim)
            ax.set_title(title, fontsize=8, pad=5)
            ax.grid(True, alpha=0.3, linewidth=0.6)
            ax.set_axisbelow(True)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=3, min_n_ticks=2))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=2))
            ax.tick_params(axis="both", which="major", pad=1.3, labelsize=8)

        # Use shared labels, since the three axes otherwise become excessively narrow.
        fig.supxlabel(r"Ann. GWP in kg CO$_2$-eq. per 100 m$^2$",
                     fontsize=8, y=0.034)
        fig.supylabel("Ann. TOTEX in EUR" + "\n" + r"per 100 m$^2$",
                     fontsize=8, x=0.018)

        legend_lines = [
            Line2D([0], [0], color=COLOR_CEN, linestyle=":", linewidth=1.6,
                   dash_capstyle="round"),
            Line2D([0], [0], color=COLOR_DEC, linestyle="--", linewidth=1.6),
        ]
        fig.legend(legend_lines,
                   ["Pareto-front centralized", "Pareto-front decentralized"],
                   loc="upper center", bbox_to_anchor=(0.5, 0.965), ncol=2,
                   frameon=False, handlelength=2.4,
                   handletextpad=0.55, columnspacing=1.0, borderaxespad=0.0)

        # Absolute margins in cm remain stable across the height sweep.
        top = max(0.48, 1.0 - 1.50 / fig_height_cm)
        bottom = min(0.45, 1.07 / fig_height_cm)
        if top - bottom < 0.23:
            top = bottom + 0.23
        fig.subplots_adjust(left=0.165, right=0.985,
                            bottom=bottom, top=top, wspace=0.25)

        file = output_dir / f"5658_pareto_fronts_3panels_{panel_mode}_{suffix}.pdf"
        # NO bbox_inches='tight': preserve exactly 11.8 cm MediaBox width.
        fig.savefig(file, dpi=DPI, format="pdf")
        saved.append(file)
        print(f"  Saved: {file}")
        if png:
            fig.savefig(file.with_suffix(".png"), dpi=300, format="png")
        plt.close(fig)
    return saved


def pareto_front_of_points(points):
    """2D non-dominated envelope from already-normalised (GWP,TOTEX) pairs."""
    arr = np.asarray(points, dtype=float)
    arr = arr[np.isfinite(arr).all(axis=1)]
    arr = arr[np.lexsort((arr[:, 1], arr[:, 0]))]
    best_y = float("inf")
    keep = []
    for x, y in arr:
        if y < best_y:
            keep.append((x, y))
            best_y = y
    return np.asarray(keep, dtype=float).reshape((-1, 2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--examples-root", help="Project examples directory")
    p.add_argument("--decentralized-pkl", help="Decentralized combined_front.pkl or parent folder")
    p.add_argument("--centralized-root", help="Root containing processed_bds_in_... directories")
    p.add_argument("--heat-grid-dir", help="Folder containing fictional_heat_grid_costs_* XLSX")
    p.add_argument("--gpkg", help="UEU GeoPackage")
    p.add_argument("--floor-area", type=float, help="Explicit UEU net floor area (m²)")
    p.add_argument("--out-dir", help="PDF output directory")
    p.add_argument("--heights", nargs="*", default=None,
                   choices=tuple(HEIGHT_VARIANTS), help="e.g. --heights h100 h80 h60")
    p.add_argument("--panel-mode", choices=("strategies", "repeat-combined"),
                   default="strategies",
                   help="3 central strategies vs decentral (default), or repeated combined fronts")
    p.add_argument("--png", action="store_true", help="Also export PNG previews")
    args = p.parse_args()

    examples_root = find_examples_root(args.examples_root)
    out_dir = path_or_none(args.out_dir or OUTPUT_DIR_OVERRIDE)
    if out_dir is None:
        out_dir = (Path(os.getenv("PARETO_PLOT_OUTPUT_ROOT", ""))
                   if os.getenv("PARETO_PLOT_OUTPUT_ROOT")
                   else Path(__file__).resolve().parent / "pareto_fronts_5658")
    heights = {key: HEIGHT_VARIANTS[key]
               for key in (args.heights or tuple(HEIGHT_VARIANTS))}
    print(f"Examples root: {examples_root}")
    area = load_floor_area(examples_root, args.gpkg, args.floor_area or FLOOR_AREA_M2_OVERRIDE)
    print(f"UEU 5658 total net floor area: {area:,.2f} m²")

    dec_file = decentralized_path(examples_root, args.decentralized_pkl)
    print(f"Decentralized source: {dec_file}")
    dec_records = load_pickle_front(dec_file)

    cen_root = centralized_root(args.centralized_root)
    xlsx_dir = heat_grid_dir(args.heat_grid_dir)
    overrides = load_heat_grid_overrides(xlsx_dir)
    cen_records = []
    cen_cases = {}
    seen_paths = set()
    for temperature, retrofit in CENTRALIZED_CASES:
        case = f"{temperature}_{retrofit}"
        file = (cen_root / UEU_FOLDER / CENTRALIZED_CLUSTER
                / temperature / retrofit / "centralized_front.pkl")
        print(f"Centralized source {case}: {file}")
        canonical = str(file.resolve()).lower()
        if canonical in seen_paths:
            raise ValueError(f"Duplicate centralized input file: {file}")
        seen_paths.add(canonical)
        case_records = load_pickle_front(file)
        apply_heat_grid_override(case_records, case, overrides[case])
        cen_cases[case] = case_records
        cen_records.extend(case_records)

    dec_front = pareto_front_co2_totex(dec_records, area)
    cen_fronts = {key: pareto_front_co2_totex(records, area)
                  for key, records in cen_cases.items()}
    cen_front = pareto_front_of_points(np.concatenate(list(cen_fronts.values()), axis=0))
    print(f"2D Pareto points: decentralized={len(dec_front)}, "
          f"centralized combined={len(cen_front)}, "
          + ", ".join(f"{key}={len(front)}" for key, front in cen_fronts.items()))
    paths = plot_three_panels(dec_front, cen_fronts, out_dir, heights,
                              panel_mode=args.panel_mode, png=args.png)
    print(f"Finished: {len(paths)} PDFs in {out_dir}")


if __name__ == "__main__":
    main()
