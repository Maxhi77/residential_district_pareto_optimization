import os
import pickle
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from plot_pareto_front_dec import load_rep_info
import ast
import os
import pickle
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import os
import pickle
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


import os
import pickle
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import pandas as pd
import matplotlib.dates as mdates


import os
import pickle
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd
import matplotlib.dates as mdates

only_adults = {
    "CHR01 Couple both at Work": 2,
    "CHR02 Couple, 30 - 64 age, with work": 2,
    "CHR04 Couple, 30 - 64 years, 1 at work, 1 at home": 2,
    "CHR13 Student with Work": 1,
    "CHR19 Couple, 30 - 64 years, both at work, with homehelp": 3,
    "CHR35 Single woman, 30 - 64 years, with work": 1,
    "CHR37 Single man, 30 - 64 years, with work": 1,
    "CHR39 Couple, 30 - 64 years, with work": 2,
    "CHR55 Couple with work around 40": 2,
    "CHR52 Student Flatsharing": 3,
    "CHR14 3 adults: Couple, 30- 64 years, both at work + Senior at home": 3,
    "CHR15 Multigenerational Home: working couple, 2 children, 2 seniors": 6

}

only_seniors = {
    "CHR30 Single, Retired Man": 1,
    "CHR31 Single, Retired Woman": 1,
    "CHR54 Retired Couple, no work": 2,
    "CHR58 Retired Couple, no work, no cooking": 2,

}
families_with_1_child = {
    "CHR22 Single woman, 1 child, with work": 2,
    "CHR43 Single man with 1 child, with work": 2,
    "CHR45 Family with 1 child, 1 at work, 1 at home": 3,
    "CHR03 Family, 1 child, both at work": 3,
    "CHR60 Family, 1 toddler, one at work, one at home": 3,
    "CHR61 Family, 1 child, both at work, early living pattern": 3,
}

families_with_2_children = {
    "CHR08 Single woman, 2 children, with work": 3,

    "CHR42 Single man with 2 children, with work": 3,
    "CHR27 Family both at work, 2 children": 4,
    "CHR53 2 Parents, 1 Working, 2 Children": 4,
    "CHR60 Family, 1 toddler, one at work, one at home": 3,
    "CHR44 Family with 2 children, 1 at work, 1 at home": 4
}

families_with_3_children = {
    "CHR41 Family with 3 children, both at work": 5,
    "CHR50 Single woman with 3 children, without work": 4,
    "CHR05 Family, 3 children, both with work": 5,
    "CHR20 one at work, one work home, 3 children": 5,
}

# ---- resident lookup -------------------------------------------------
resident_lookup = {}
resident_lookup.update(only_adults)
resident_lookup.update(only_seniors)
resident_lookup.update(families_with_1_child)
resident_lookup.update(families_with_2_children)
resident_lookup.update(families_with_3_children)

# ---- helpers ---------------------------------------------------------
def parse_profile_list(x):
    if pd.isna(x):
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        return ast.literal_eval(x)
    return []

def count_residents(profile_list):
    total = 0
    for profile in profile_list:
        if profile not in resident_lookup:
            raise KeyError(f"Unknown household profile: {profile}")
        total += resident_lookup[profile]
    return total

import matplotlib.pyplot as plt
import numpy as np

import matplotlib.pyplot as plt
import numpy as np

import matplotlib.pyplot as plt
import numpy as np
import math

def _nice_upper_limit(x):
    """Round up to a nice axis limit: 1 / 2 / 2.5 / 5 / 10 * 10^n"""
    if x <= 0:
        return 1
    exp = math.floor(math.log10(x))
    base = x / 10**exp
    if base <= 1:
        nice = 1
    elif base <= 2:
        nice = 2
    elif base <= 2.5:
        nice = 2.5
    elif base <= 5:
        nice = 5
    else:
        nice = 10
    return nice * 10**exp

def plot_ueu_statistics_bars_2x2(
    ueu_statistics,
    out_path,
    figsize=(8.5, 4.2),
    font_size=9,
    font_family="TeX Gyre Termes",
    dpi=600,
    show=False,
):
    """
    2x2 vertical bar plots for UEU statistics (paper-ready).

    Layout:
    - 2 plots top, 2 plots bottom
    - y-axis label on each subplot (left)
    - x-axis labels only on bottom row
    - vertical bars
    """

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
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # -----------------------------
    # ORDER & LABELS
    # -----------------------------
    ordered_labels = [
        "Low heat density",
        "Medium heat density",
        "High heat density",
    ]

    keys = [k for k in ordered_labels if k in ueu_statistics]
    if not keys:
        raise ValueError("Expected UEU labels not found in ueu_statistics.")

    x_labels = [
        k.replace(" density", "\ndensity").replace(" area", "\narea")
        for k in keys
    ]
    x = np.arange(len(keys))

    # -----------------------------
    # KPI DATA
    # -----------------------------
    data = [
        (
            [ueu_statistics[k]["Number of residents per household"] for k in keys],
            "Residents per household",
        ),
        (
            [ueu_statistics[k]["Floor area per household"] for k in keys],
            r"Floor area per household in m$^2$",
        ),
        (
            [ueu_statistics[k]["Share SFH"] for k in keys],
            "Share of SFHs",
        ),
        (
            [ueu_statistics[k]["Number of households per MFH"] for k in keys],
            "Households per MFH",
        ),
    ]

    # -----------------------------
    # PLOT
    # -----------------------------
    fig, axes = plt.subplots(
        nrows=2,
        ncols=2,
        figsize=figsize,
        sharex=True,
        gridspec_kw={
            "wspace": 0.30,
            "hspace": 0.18,   # 👈 tighter vertical spacing
        }
    )

    axes = axes.flatten()

    bar_style = dict(
        color="0.35",
        edgecolor="black",
        linewidth=0.6
    )

    for i, (ax, (vals, ylabel)) in enumerate(zip(axes, data)):
        ax.bar(x, vals, **bar_style)
        ax.set_ylabel(ylabel)
        ax.set_ylim(0, _nice_upper_limit(max(vals)))
        ax.grid(True, axis="y", alpha=0.3)
        ax.set_axisbelow(True)

        # x-axis labels only for bottom row
        if i >= 2:
            ax.set_xticks(x)
            ax.set_xticklabels(x_labels)
        else:
            ax.set_xticks(x)
            ax.set_xticklabels([])

    # -----------------------------
    # LAYOUT
    # -----------------------------
    fig.subplots_adjust(
        left=0.10,
        right=0.98,
        top=0.98,
        bottom=0.20   # slightly tighter bottom
    )

    # -----------------------------
    # SAVE
    # -----------------------------
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)

    print(f"Saved: {out_path}")
import numpy as np
import matplotlib.pyplot as plt
def plot_ueu_statistics_bars_3x2(
    ueu_statistics,
    out_path,
    figsize=(8.5, 6.0),
    font_size=9,
    font_family="TeX Gyre Termes",
    dpi=600,
    show=False,
):
    """
    3x2 vertical bar plots for UEU statistics (paper-ready).

    Layout:
    Row 1:
        - Number of residents
        - Residents per household
    Row 2:
        - Floor area per household
        - Share SFH
    Row 3:
        - Households per grid length
        - Heat demand per grid length

    - y-axis label on every subplot
    - x-axis labels only on bottom row
    - legend above (UEU colors like the line plot)
    """
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

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
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # -----------------------------
    # ORDER & LABELS
    # -----------------------------
    ordered_labels = [
        "Low heat density",
        "Medium heat density",
        "High heat density",
    ]

    keys = [k for k in ordered_labels if k in ueu_statistics]
    if not keys:
        raise ValueError("Expected UEU labels not found in ueu_statistics.")

    x_labels = [
        k.replace(" density", "\ndensity").replace(" area", "\narea")
        for k in keys
    ]
    x = np.arange(len(keys))

    # -----------------------------
    # UEU COLORS (same as your line plot)
    # -----------------------------
    colors = ["#0072B2", "#009E73", "#D55E00"]  # blue, green, orange
    color_map = {k: colors[i % len(colors)] for i, k in enumerate(ordered_labels)}
    bar_colors = [color_map[k] for k in keys]

    legend_ueu = [Patch(facecolor=color_map[k], edgecolor="black", linewidth=0.6, label=k) for k in keys]

    # -----------------------------
    # KPI DATA (6 plots)
    # -----------------------------
    data = [
        (
            [ueu_statistics[k]["Number of residents per household"] for k in keys],
            "Residents per\nhousehold",
        ),
        (
            [ueu_statistics[k]["Floor area per household"] for k in keys],
            "Floor area per\nhousehold in m$^2$",
        ),
        (
            [ueu_statistics[k]["Share SFH"] for k in keys],
            "Share of\nSFHs",
        ),
        (
            [ueu_statistics[k]["Number of households per MFH"] for k in keys],
            "Households per\nMFH",
        ),
        (
            [ueu_statistics[k]["Household per grid length in m"] for k in keys],
            "Households per\n meter grid length",
        ),
        (
            [ueu_statistics[k]["Heat demand per grid length in kWh/m"] for k in keys],
            "Heat density of\n grid in kWh/m",
        ),
    ]

    # -----------------------------
    # PLOT
    # -----------------------------
    fig, axes = plt.subplots(
        nrows=3,
        ncols=2,
        figsize=figsize,
        sharex=True,
        gridspec_kw={
            "wspace": 0.30,
            "hspace": 0.18,
        }
    )

    axes = axes.flatten()

    for i, (ax, (vals, ylabel)) in enumerate(zip(axes, data)):
        ax.bar(
            x, vals,
            color=bar_colors,
            edgecolor="black",
            linewidth=0.6
        )
        ax.set_ylabel(ylabel)
        ax.set_ylim(0, _nice_upper_limit(max(vals)))
        ax.grid(True, axis="y", alpha=0.3)
        ax.set_axisbelow(True)

        # x-axis labels only on bottom row
        ax.set_xticks(x)
        if i >= 4:
            ax.set_xticklabels(x_labels)
        else:
            ax.set_xticklabels([])

    # -----------------------------
    # LEGEND (above, like your other plot)
    # -----------------------------
    fig.legend(
        handles=legend_ueu,
        loc="upper center",
        ncol=len(legend_ueu),
        frameon=False,
        bbox_to_anchor=(0.5, 0.99),
    )

    # -----------------------------
    # LAYOUT
    # -----------------------------
    fig.subplots_adjust(
        left=0.11,
        right=0.98,
        top=0.88,   # leave room for legend
        bottom=0.18
    )

    # -----------------------------
    # SAVE
    # -----------------------------
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)

    print(f"Saved: {out_path}")


def plot_ueu_statistics_bars(
    ueu_statistics,
    out_path,
    figsize=(12, 2.2),   # flatter
    font_size=9,
    font_family="TeX Gyre Termes",
    dpi=600,
    show=False,
):
    """
    1x4 vertical bar plots for UEU statistics (paper-ready).

    KPIs:
    - Residents per household
    - Floor area per household
    - Share SFH
    - Households per MFH

    Design principles:
    - no subplot titles
    - y-axis labels only
    - monochrome
    - grid on y-axis only
    """

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
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # -----------------------------
    # DATA
    # -----------------------------
    labels = list(ueu_statistics.keys())
    x = np.arange(len(labels))

    values = [
        ([ueu_statistics[k]["Number of residents per household"] for k in labels],
         "Residents per household"),
        ([ueu_statistics[k]["Floor area per household"] for k in labels],
         r"Floor area per household (m$^2$)"),
        ([ueu_statistics[k]["Share SFH"] for k in labels],
         "Share SFH (-)"),
        ([ueu_statistics[k]["Number of households per MFH"] for k in labels],
         "Households per MFH"),
    ]

    # -----------------------------
    # PLOT
    # -----------------------------
    fig, axes = plt.subplots(
        ncols=4,
        figsize=figsize,
        sharex=True,
        gridspec_kw={"wspace": 0.35}
    )

    bar_style = dict(
        color="0.35",
        edgecolor="black",
        linewidth=0.6
    )

    for ax, (vals, ylabel) in zip(axes, values):
        ax.bar(x, vals, **bar_style)
        ax.set_ylabel(ylabel)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.grid(True, axis="y", alpha=0.3)
        ax.set_axisbelow(True)

    # -----------------------------
    # LAYOUT
    # -----------------------------
    fig.subplots_adjust(
        left=0.07,
        right=0.99,
        top=0.98,
        bottom=0.36,   # room for x labels
        wspace=0.35
    )

    # -----------------------------
    # SAVE
    # -----------------------------
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)

    print(f"Saved: {out_path}")


def plot_ueu_cumulative_over_year_3modes(
    ueu_to_agg_pkl,
    ueu_meta,   # {label: {"floor_area_m2": ..., "households": ...}}
    out_dir,
    year=2025,
    figsize=(12, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    dpi=600,
    show=False,
):
    """
    Chronological cumulative annual energy demand (no sorting), plotted for 3 modes:
      - absolute
      - per 100 m²
      - per household

    3 panels per figure:
      - Electricity demand
      - Domestic hot water demand
      - Space heating demand

    Units: kWh (cumulative sum of hourly values).
    """

    # -----------------------------
    # GLOBAL STYLE
    # -----------------------------
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.labelsize": font_size,
        "axes.titlesize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
        "mathtext.fontset": "cm",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # -----------------------------
    # UEU styles (best practice: color + line style, no markers)
    # 3 "scientific" colors, colorblind-friendly-ish
    # -----------------------------
    ueu_keys = list(ueu_to_agg_pkl.keys())

    colors = ["#0072B2", "#009E73", "#D55E00"]  # blue, green, vermillion (Okabe-Ito palette)
    linestyles = ["-", "--", ":"]

    style_map = {}
    for i, k in enumerate(ueu_keys):
        style_map[k] = {
            "color": colors[i % len(colors)],
            "ls": linestyles[i % len(linestyles)],
        }

    # -----------------------------
    # KPI definitions
    # -----------------------------
    kpis = [
        ("aggregated_electricity_demand", "Electricity demand"),
        ("aggregated_warm_water_demand", "Domestic hot water demand"),
        ("aggregated_heat_demand", "Space heating demand"),
        ("aggregated_pv_system_max", "PV power potential"),
    ]

    # -----------------------------
    # Load all UEU data once, check lengths
    # -----------------------------
    ueu_data = {}
    series_len = None

    for label, pkl_path in ueu_to_agg_pkl.items():
        with open(pkl_path, "rb") as f:
            agg = pickle.load(f)

        ueu_data[label] = {}

        for key, _ in kpis:
            if key not in agg:
                raise KeyError(
                    f"{label}: missing '{key}' in {pkl_path}\n"
                    f"Available keys: {list(agg.keys())}"
                )

            arr = np.asarray(agg[key], dtype=float)
            if arr.ndim != 1:
                raise ValueError(f"{label}: '{key}' is not 1D")

            if series_len is None:
                series_len = len(arr)
            elif len(arr) != series_len:
                raise ValueError(
                    f"{label}: length mismatch for '{key}' (got {len(arr)}, expected {series_len})"
                )

            ueu_data[label][key] = arr

    if series_len is None:
        raise ValueError("No data loaded.")

    # -----------------------------
    # Time axis (hourly) + strict x-limits
    # -----------------------------
    start = pd.Timestamp(f"{year}-01-01 00:00:00")
    time_index = pd.date_range(start=start, periods=series_len, freq="H")

    # strict end for xlim (last timestamp in data)
    x_min = time_index[0]
    x_max = time_index[-1]

    # -----------------------------
    # Normalization
    # -----------------------------
    def scale_factor(label, mode):
        fa = float(ueu_meta[label]["floor_area_m2"])
        hh = float(ueu_meta[label]["households"])

        if mode == "abs":
            return 1.0
        elif mode == "per100m2":
            denom = fa / 100.0
            if denom <= 0:
                raise ValueError(f"{label}: floor area invalid: {fa}")
            return denom
        elif mode == "perhh":
            if hh <= 0:
                raise ValueError(f"{label}: households invalid: {hh}")
            return hh
        else:
            raise ValueError("mode must be 'abs', 'per100m2', or 'perhh'")

    modes = [
        ("abs",      "absolute",      "Cumulative annual energy demand (kWh)"),
        ("per100m2",  "per_100m2",     r"Cumulative annual energy demand (kWh per 100 m$^2$)"),
        ("perhh",     "per_household", "Cumulative annual energy demand (kWh per household)"),
    ]

    # Legend (UEU only) - color + line style
    legend_handles = [
        Line2D([0], [0],
               linestyle=style_map[label]["ls"],
               linewidth=1.6,
               color=style_map[label]["color"],
               label=label)
        for label in ueu_keys
    ]

    # -----------------------------
    # Plot each mode
    # -----------------------------
    for mode, mode_tag, ylabel in modes:
        fig, axes = plt.subplots(ncols=4, figsize=figsize, gridspec_kw={"wspace": 0.30})

        for ax, (kpi_key, title) in zip(axes, kpis):
            for label in ueu_keys:
                denom = scale_factor(label, mode)
                y = ueu_data[label][kpi_key] / denom
                y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

                cum_kwh = np.cumsum(y)

                ax.plot(
                    time_index,
                    cum_kwh,
                    linestyle=style_map[label]["ls"],
                    color=style_map[label]["color"],
                    linewidth=1.4,
                )

            ax.set_title(title)
            ax.set_xlabel("Date")
            ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.25)
            ax.set_ylim(bottom=0)

            # Make sure the plot really spans Jan..Dec with no weird padding
            ax.set_xlim(x_min, x_max)

            # Month ticks: Jan ... Dec
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
            ax.tick_params(axis="x", rotation=0)

        fig.legend(
            handles=legend_handles,
            frameon=False,
            loc="upper center",
            ncol=min(3, len(legend_handles)),
        )

        fig.tight_layout(rect=[0, 0, 1, 0.90])

        out_path = os.path.join(out_dir, f"UEU_CUM_over_year_{mode_tag}.pdf")
        fig.savefig(out_path, dpi=dpi, bbox_inches="tight")

        if show:
            plt.show()
        else:
            plt.close(fig)

        print(f"Saved: {out_path}")

import os
import pickle
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd
import matplotlib.dates as mdates

import os
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D

def plot_ueu_cumulative_over_year_3modes_both(
    ueu_to_agg_pkl_clustered,
    ueu_to_agg_pkl_unclustered,
    ueu_meta,
    out_dir,
    year=2025,
    figsize=(12, 4),
    font_size=9,
    font_family="TeX Gyre Termes",
    dpi=600,
    show=False,
):

    import os, pickle
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D

    # -----------------------------
    # STYLE
    # -----------------------------
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.labelsize": font_size,
        "axes.titlesize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
    })

    # -----------------------------
    # UEU styling
    # -----------------------------
    ueu_keys = list(ueu_to_agg_pkl_clustered.keys())

    colors = ["#0072B2", "#009E73", "#D55E00"]
    linestyles = ["-", "--", ":"]

    style_map = {
        k: {
            "color": colors[i % len(colors)],
            "ls": linestyles[i % len(linestyles)],
        }
        for i, k in enumerate(ueu_keys)
    }

    # -----------------------------
    # KPIs (ALL cumulative now)
    # -----------------------------
    kpis = [
        ("aggregated_electricity_demand", "Electricity demand"),
        ("aggregated_warm_water_demand",  "Domestic hot water demand"),
        ("aggregated_heat_demand",        "Space heating demand"),
        ("aggregated_pv_system_max",      "PV power potential"),
    ]

    # -----------------------------
    # Load helper
    # -----------------------------
    def _load(pkl, label):
        with open(pkl, "rb") as f:
            d = pickle.load(f)

        out = {}
        for k, _ in kpis:
            arr = np.asarray(d[k], float)
            if arr.ndim != 1:
                raise ValueError(f"{label}: {k} not 1D")
            out[k] = arr
        return out

    data_c = {}
    data_u = {}
    series_len = None

    for label in ueu_keys:
        dc = _load(ueu_to_agg_pkl_clustered[label], label + "_c")
        du = _load(ueu_to_agg_pkl_unclustered[label], label + "_u")

        for k, _ in kpis:
            if series_len is None:
                series_len = len(dc[k])
            if len(dc[k]) != series_len or len(du[k]) != series_len:
                raise ValueError("Length mismatch")

        data_c[label] = dc
        data_u[label] = du

    # -----------------------------
    # Time axis
    # -----------------------------
    time_index = pd.date_range(
        start=f"{year}-01-01",
        periods=series_len,
        freq="h"
    )

    # -----------------------------
    # Scaling
    # -----------------------------
    def scale(label, mode, ds):
        fa = ueu_meta[label][f"floor_area_m2_{ds}"]
        hh = ueu_meta[label][f"households_{ds}"]

        if mode == "abs":
            return 1
        if mode == "per100m2":
            return fa / 100
        if mode == "perhh":
            return hh

    modes = [
        ("abs", "absolute", "Cumulative annual energy (kWh)"),
        ("per100m2", "per_100m2", r"Cumulative annual energy (kWh per 100 m$^2$)"),
        ("perhh", "per_household", "Cumulative annual energy (kWh per household)"),
    ]

    # -----------------------------
    # Legends
    # -----------------------------
    legend_ueu = [
        Line2D([0], [0],
               linestyle=style_map[l]["ls"],
               color=style_map[l]["color"],
               lw=1.6,
               label=l)
        for l in ueu_keys
    ]

    legend_dataset = [
        Line2D([0], [0], linestyle="-", color="black",
               marker="^", markersize=7, lw=1.6,
               label="Representative (clustered)"),
        Line2D([0], [0], linestyle="-", color="black",
               marker="o", markersize=7, lw=1.6,
               label="Original (all buildings)"),
    ]

    # -----------------------------
    # Plot
    # -----------------------------
    for mode, tag, ylabel in modes:

        fig, axes = plt.subplots(
            ncols=4,
            figsize=figsize,
            gridspec_kw={"wspace": 0.30},
        )

        for ax, (kpi, title) in zip(axes, kpis):

            for label in ueu_keys:

                sc = scale(label, mode, "clustered")
                su = scale(label, mode, "unclustered")

                yc = np.cumsum(data_c[label][kpi] / sc)
                yu = np.cumsum(data_u[label][kpi] / su)

                # clustered (triangles)
                ax.plot(
                    time_index, yc,
                    color=style_map[label]["color"],
                    linestyle=style_map[label]["ls"],
                    marker="^",
                    markersize=5,
                    markevery=24*30,
                    linewidth=1.4,
                )

                # unclustered (circles)
                ax.plot(
                    time_index, yu,
                    color=style_map[label]["color"],
                    linestyle=style_map[label]["ls"],
                    marker="o",
                    markersize=5,
                    markevery=24*30,
                    linewidth=1.2,
                )

            ax.set_title(title)
            ax.set_ylabel(ylabel)
            ax.set_xlabel("Month")
            ax.grid(True, alpha=0.25)
            ax.set_ylim(bottom=0)

            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

        all_handles = legend_ueu + legend_dataset

        fig.legend(
            handles=all_handles,
            frameon=False,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.98),
            ncol=len(all_handles),
        )

        fig.tight_layout(rect=[0, 0, 1, 0.90])

        out = os.path.join(
            out_dir,
            f"UEU_CUM_over_year_{tag}_clustered_vs_original.pdf"
        )
        fig.savefig(out, dpi=dpi, bbox_inches="tight")

        if show:
            plt.show()
        else:
            plt.close(fig)

        print("Saved:", out)
def plot_ueu_cumulative_over_year_3modes_both_2x2(
    ueu_to_agg_pkl_clustered,
    ueu_to_agg_pkl_unclustered,
    ueu_meta,
    out_dir,
    year=2025,
    figsize=(8.5, 4.8),
    font_size=9,
    font_family="TeX Gyre Termes",
    dpi=600,
    show=False,
):
    import os, pickle
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D

    # -----------------------------
    # STYLE
    # -----------------------------
    plt.style.use("default")
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.labelsize": font_size,
        "axes.titlesize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # -----------------------------
    # UEU styling
    # -----------------------------
    ueu_keys = list(ueu_to_agg_pkl_clustered.keys())

    colors = ["#0072B2", "#009E73", "#D55E00"]
    linestyles = ["-", "--", ":"]

    style_map = {
        k: {"color": colors[i % len(colors)], "ls": linestyles[i % len(linestyles)]}
        for i, k in enumerate(ueu_keys)
    }

    # -----------------------------
    # KPIs
    # -----------------------------
    kpis = [
        ("aggregated_electricity_demand", "Electricity demand"),
        ("aggregated_warm_water_demand",  "Domestic hot water demand"),
        ("aggregated_heat_demand",        "Space heating demand"),
        ("aggregated_pv_system_max",      "PV power potential"),
    ]

    def _load(pkl):
        with open(pkl, "rb") as f:
            d = pickle.load(f)
        return {k: np.asarray(d[k], float) for k, _ in kpis}

    data_c, data_u = {}, {}
    series_len = None

    for label in ueu_keys:
        dc = _load(ueu_to_agg_pkl_clustered[label])
        du = _load(ueu_to_agg_pkl_unclustered[label])

        for k, _ in kpis:
            if series_len is None:
                series_len = len(dc[k])
            if len(dc[k]) != series_len or len(du[k]) != series_len:
                raise ValueError("Length mismatch")

        data_c[label] = dc
        data_u[label] = du

    time_index = pd.date_range(f"{year}-01-01", periods=series_len, freq="h")

    def scale(label, mode, ds):
        if mode == "abs":
            return 1.0
        if mode == "per100m2":
            return ueu_meta[label][f"floor_area_m2_{ds}"] / 100.0
        if mode == "perhh":
            return ueu_meta[label][f"households_{ds}"]

    modes = [
        ("abs", "absolute", "Cumulative energy\nin MWh"),
        ("per100m2", "per_100m2", "Cumulative energy\nin MWh per 100 m$^2$"),
        ("perhh", "per_household", "Cumulative energy\nin MWh per household"),
    ]

    legend_ueu = [
        Line2D([0], [0], color=style_map[l]["color"],
               ls=style_map[l]["ls"], lw=1.6, label=l)
        for l in ueu_keys
    ]

    legend_dataset = [
        Line2D([0], [0], color="black", marker="^",
               lw=1.4, label="Representative (clustered)"),
        Line2D([0], [0], color="black", marker="o",
               lw=1.2, label="Original (all buildings)"),
    ]

    # -----------------------------
    # Plot
    # -----------------------------
    for mode, tag, ylabel in modes:

        fig, axes = plt.subplots(
            2, 2, figsize=figsize, sharex=True,
            gridspec_kw={"wspace": 0.30, "hspace": 0.18}
        )
        axes = axes.flatten()

        for i, (ax, (kpi, title)) in enumerate(zip(axes, kpis)):

            for label in ueu_keys:
                yc = np.cumsum(
                    data_c[label][kpi] / scale(label, mode, "clustered")
                ) / 1000.0
                yu = np.cumsum(
                    data_u[label][kpi] / scale(label, mode, "unclustered")
                ) / 1000.0
                ax.grid(
                    True,
                    axis="y",  # nur horizontal
                    which="major",  # nur Hauptticks
                    color="0.85",  # helles Grau
                    linewidth=0.6,
                )
                ax.set_axisbelow(True)
                ax.plot(
                    time_index, yc,
                    color=style_map[label]["color"],
                    ls=style_map[label]["ls"],
                    lw=1.4,
                    marker="^",
                    markersize=4,
                    markeredgecolor="black",
                    markeredgewidth=0.6,
                    markevery=900,
                )

                ax.plot(
                    time_index, yu,
                    color=style_map[label]["color"],
                    ls=style_map[label]["ls"],
                    lw=1.2,
                    marker="o",
                    markersize=4,
                    markeredgecolor="black",
                    markeredgewidth=0.6,
                    markevery=900,
                )

            ax.set_title(title)
            ax.set_ylabel(ylabel, labelpad=2)
            ax.yaxis.set_label_coords(-0.12, 0.5)
            ax.grid(True, alpha=0.25)
            ax.set_ylim(bottom=0)
            ax.ticklabel_format(axis="y", style="plain")

            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

            if i < 2:
                ax.set_xticklabels([])
            else:
                ax.set_xlabel("Month")

        # -----------------------------
        # Legends (FIXED)
        # -----------------------------
        fig.legend(
            handles=legend_ueu,
            loc="upper center",
            ncol=len(legend_ueu),
            frameon=False,
        )

        fig.legend(
            handles=legend_dataset,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.96),
            ncol=2,
            frameon=False,
        )

        fig.subplots_adjust(left=0.12, right=0.98, top=0.86, bottom=0.18)

        out = os.path.join(out_dir, f"UEU_CUM_over_year_{tag}_2x2.pdf")
        fig.savefig(out, dpi=dpi, bbox_inches="tight")
        if show:
            plt.show()
        else:
            plt.close(fig)

        print("Saved:", out)




# ============================================================
# YOUR LOOP: build ueu_to_agg_pkl + ueu_meta, then plot 3 modes
# ============================================================

ueu_list = [
    "processed_bds_in_DENI03403000SEC4580",
    "processed_bds_in_DENI03403000SEC5658",
    "processed_bds_in_DENI03403000SEC5101",
]
# ============================================================
# Scientific naming of UEUs (no codes in plots)
# ============================================================

UEU_NAME_MAP = {
    "DENI03403000SEC4580": "Low heat density",
    "DENI03403000SEC5658": "Medium heat density",
    "DENI03403000SEC5101": "High heat density",
}

base_path = r"C:\Users\hill_mx\Desktop\From Luis\Case Studies\Small New"
out_dir   = r"C:\Users\hill_mx\Desktop\UEU testing results"

width_cm  = 15.11293
height_cm = 6.5 * 1.8
width_inch  = width_cm / 2.54
height_inch = height_cm / 2.54
font_size = 9

# ---- you need the aggregated pkl locations (adapt if different) ----
# If your aggregated pkls are in your project folder instead, set those paths here.
# Example here assumes: <base_path>/<ueu>/<ueu>_data_aggregated.pkl  (adjust!)
ueu_to_agg_pkl = {}
ueu_meta = {}
ueu_to_agg_pkl_unclustered= {}
ueu_statistics = {}
ev = "no_EV"
for ueu in ueu_list:

    ueu_short = ueu.removeprefix("processed_bds_in_")
    print(f"\n=== UEU: {ueu_short} ===")

    # --- load rep info to compute area + households (your code) ---
    path_mfh = os.path.join(base_path, ueu, "mfh_cluster.pkl")
    path_sfh = os.path.join(base_path, ueu, "sfh_cluster.pkl")

    # you already have these helpers in your project:
    sfh_rep_info = load_rep_info(path_sfh, "SFH", numeric=False)
    mfh_rep_info = load_rep_info(path_mfh, "MFH", numeric=False)

    import geopandas as gpd
    import os

    path_ueu = os.path.join(base_path, ueu + ".gpkg")

    ueu_all = gpd.read_file(path_ueu)

    total_floor_area_unaggregated = sum(ueu_all["net_floor_area"])
    print(total_floor_area_unaggregated)
    ueu_all["n_residents"] = (
        ueu_all["list_lpg_households"]
        .apply(parse_profile_list)
        .apply(count_residents)
    )
    total_number_of_residents_unaggregated  = sum(ueu_all["n_residents"])


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
    total_len_unaggregated = ueu_all["list_number_of_adults"].apply(lambda x: len(parse_list_cell(x))).sum()
    total_number_of_households_unaggregated = total_len_unaggregated

    rep_info = {**sfh_rep_info, **mfh_rep_info}



    total_floor_area_all = sum(info["total_floor_area"] for info in rep_info.values())
    total_number_of_households = sum(info["number_of_households"] for info in rep_info.values())
    total_number_of_residents = sum(info["number_of_residents"] for info in rep_info.values())

    print(total_floor_area_unaggregated)
    print(total_floor_area_all)

    scientific_name = UEU_NAME_MAP[ueu_short]
    mask_mfh = ueu_all["tabula_building_type"] == "MFH"
    total_number_of_households_unaggregated_mfh = (
        ueu_all.loc[mask_mfh, "list_number_of_adults"]
        .apply(lambda x: len(parse_list_cell(x)))
        .sum()
    )
    agg_pkl = os.path.join(base_path, ueu, f"{ueu}_data_aggregated_all_False_{ev}.pkl")
    agg_pkl_unclustered = os.path.join(base_path, ueu, f"{ueu}_data_aggregated_all_True_{ev}.pkl")
    scientific_name = UEU_NAME_MAP[ueu_short]

    ueu_to_agg_pkl[scientific_name] = agg_pkl
    ueu_to_agg_pkl_unclustered[scientific_name] = agg_pkl_unclustered

    if ueu == "processed_bds_in_DENI03403000SEC5101":
        heat_gird_length = 890.354
    elif ueu == "processed_bds_in_DENI03403000SEC4580":
        heat_gird_length = 2723.294
    elif ueu =="processed_bds_in_DENI03403000SEC5658":
        heat_gird_length = 1146.15

    with open(agg_pkl_unclustered, "rb") as f:
        pkl_agg_unclustered = pickle.load(f)

    ueu_statistics[scientific_name] = {
        "Number of residents": total_number_of_residents_unaggregated,
        "Number of residents per household": total_number_of_residents_unaggregated/total_number_of_households_unaggregated,
        "Floor area per household": total_floor_area_unaggregated/total_number_of_households_unaggregated,#
        "Share SFH":sum(ueu_all["tabula_building_type"]=="SFH") /(sum(ueu_all["tabula_building_type"]=="SFH")+sum(ueu_all["tabula_building_type"]=="MFH")),
        "Number of households per MFH": total_number_of_households_unaggregated_mfh/sum(ueu_all["tabula_building_type"]=="MFH"),
        "Household per grid length in m":  total_number_of_households_unaggregated/heat_gird_length,
        "Heat demand per grid length in kWh/m": sum(pkl_agg_unclustered["aggregated_heat_demand"])/1000 / heat_gird_length,
    }
    ueu_meta[scientific_name] = {
        "floor_area_m2_clustered": total_floor_area_all,  # <-- clustered
        "households_clustered": total_number_of_households,  # <-- clustered
        "residents_clustered": total_number_of_residents,  # optional

        "floor_area_m2_unclustered": total_floor_area_unaggregated,  # <-- unclustered/all
        "households_unclustered": total_number_of_households_unaggregated,
        "residents_unclustered": total_number_of_residents_unaggregated,  # optional
    }

    # aggregated pkl path (ADAPT THIS to your real location)
    # Option A (if you stored in project root as in earlier snippet):
    # agg_pkl = os.path.join(get_project_root(), f"{ueu}_data_aggregated.pkl")

    # Option B (if stored next to UEU folder):


plot_ueu_statistics_bars_2x2(
    ueu_statistics=ueu_statistics,
    out_path="UEU_statistics_bars_2x2.pdf",
    show=True,
    figsize=(width_inch, height_inch*0.9),
)
plot_ueu_statistics_bars_3x2(
    ueu_statistics=ueu_statistics,
    out_path="UEU_statistics_bars_3x2.pdf",
    show=True,
    figsize=(width_inch, height_inch*1.1),
)

plot_ueu_cumulative_over_year_3modes_both_2x2(
    ueu_to_agg_pkl_clustered=ueu_to_agg_pkl,
    ueu_to_agg_pkl_unclustered=ueu_to_agg_pkl_unclustered,
    ueu_meta=ueu_meta,
    out_dir=out_dir,
    year=2025,
    figsize=(width_inch, height_inch),
    font_size=font_size,
    show=True,
)

plot_ueu_cumulative_over_year_3modes_both(
    ueu_to_agg_pkl_clustered=ueu_to_agg_pkl,
    ueu_to_agg_pkl_unclustered=ueu_to_agg_pkl_unclustered,
    ueu_meta=ueu_meta,
    out_dir=out_dir,
    year=2025,
    figsize=(width_inch, height_inch),
    font_size=font_size,
    show=True,
)
plot_ueu_cumulative_over_year_3modes(
    ueu_to_agg_pkl=ueu_to_agg_pkl,
    ueu_meta=ueu_meta,
    out_dir=out_dir,
    year=2025,
    figsize=(width_inch, height_inch),
    font_size=font_size,
    show=True,
)
plot_ueu_statistics_bars(
    ueu_statistics,
    figsize=(width_inch, height_inch*0.3),
    out_path="UEU_structural_indicators.pdf",
    show=True
)