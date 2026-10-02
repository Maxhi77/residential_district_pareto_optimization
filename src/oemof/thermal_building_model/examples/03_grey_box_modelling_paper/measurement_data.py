"""Load grey-box measurement data from supported local input formats."""

import os
import warnings
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = (
    "Time",
    "T_amb [°C]",
    "P_appliance [W]",
    "P_kitchen [W]",
    "Qdot_selected [W]",
)

DEFAULT_BUILDINGS = ("B1",)
BUILDING_IDS = ("B1", "B2", "B3")
DEFAULT_QDOT_SOURCE = "heating_circuit"
DEFAULT_TSET_ZONE_AREAS = {
    "B": 12.74,
    "C2": 28.06 + 39.01,
    "K": 26.08,
    "R1": 25.99,
    "R2": 25.85,
    "R3": 47.18,
    "R4": 64.47,
    "R5": 77.31,
}

def load_measurement_data(
    source,
    experiment,
    sheet_name="Experiment 3",
):
    """
    Load measurement data for a selected experiment.

    Parameters
    ----------
    source : str or Path
        File or folder containing the measurement data.

    experiment : int
        Experiment number, e.g. 2 or 3.

    sheet_name : str
        Only used for Excel input.
    """

    source_path = Path(source)

    if experiment == 2:
        if source_path.is_dir():
            return _load_experiment_2_csv_folder(source_path)

        data = pd.read_excel(
            pd.ExcelFile(source_path),
            sheet_name=sheet_name,
        )

        if (
            "Q_hp,prim [W]" in data.columns
            and "Qdot_selected [W]" not in data.columns
        ):
            data = data.rename(
                columns={
                    "Q_hp,prim [W]": "Qdot_selected [W]"
                }
            )

        _validate_required_columns(data, source_path)

        return data

    elif experiment == 3:
        if not source_path.is_dir():
            raise ValueError(
                "Experiment 3 expects a CSV folder as input."
            )

        return _load_experiment_3_csv_folder(
            source_path
        )

    else:
        raise ValueError(
            f"Unsupported experiment: {experiment}"
        )

    # Experiment 2
    data = pd.read_excel(
        pd.ExcelFile(source_path),
        sheet_name=sheet_name
    )

    if "Q_hp,prim [W]" in data.columns and "Qdot_selected [W]" not in data.columns:
        data = data.rename(
            columns={"Q_hp,prim [W]": "Qdot_selected [W]"}
        )

    # =====================================================
    # HIER KOMMT BLOCK 4 HIN
    # Exp2_indoor_temperatures.csv einlesen
    # =====================================================

    indoor_temperature_path = (
        source_path.parent / "Exp2_indoor_temperatures.csv"
    )

    if indoor_temperature_path.exists():

        indoor_temperatures = pd.read_csv(
            indoor_temperature_path
        )

        data = pd.merge(
            data,
            indoor_temperatures,
            on="Time",
            how="left",
        )

        area_weights = _resolve_tset_area_weights()

        selected_buildings = ["B1"]

        # flächengewichtetes T_set
        tset_columns = _resolve_temperature_columns(
            indoor_temperatures,
            selected_buildings,
            "Tset",
        )

        if tset_columns:
            data["T_set [°C]"] = _weighted_temperature(
                data,
                tset_columns,
                area_weights,
            )

        # flächengewichtetes T_indoor
        tzone_columns = _resolve_temperature_columns(
            indoor_temperatures,
            selected_buildings,
            "Tzone",
        )

        if tzone_columns:
            data["T_indoor [°C]"] = _weighted_temperature(
                data,
                tzone_columns,
                area_weights,
            )

    # erst danach validieren
    _validate_required_columns(data, source_path)

    return data
def _resolve_experiment_3_csv_folder(folder):
    if _has_experiment_3_csv_files(folder):
        return folder

    experiment_3_folder = folder / "Experiment 3"
    if _has_experiment_3_csv_files(experiment_3_folder):
        return experiment_3_folder

    return folder


def _has_experiment_3_csv_files(folder):
    return (folder / "Exp3_weather.csv").exists() and (
        folder / "Exp3_heat_flows.csv"
    ).exists()


def _load_experiment_3_csv_folder(folder):
    weather_path = folder / "Exp3_weather.csv"
    heat_flows_path = folder / "Exp3_heat_flows.csv"
    indoor_temperatures_path = folder / "Exp3_indoor_temperatures.csv"
    if not weather_path.exists() or not heat_flows_path.exists():
        raise FileNotFoundError(
            "CSV folder input requires Exp3_weather.csv and Exp3_heat_flows.csv: "
            f"{folder}"
        )

    weather = pd.read_csv(weather_path)
    heat_flows = pd.read_csv(heat_flows_path)
    data = pd.merge(weather, heat_flows, on="Time", how="inner")
    indoor_temperatures = None
    if indoor_temperatures_path.exists():
        indoor_temperatures = pd.read_csv(indoor_temperatures_path)
        data = pd.merge(data, indoor_temperatures, on="Time", how="inner")

    selected_buildings = _resolve_buildings(heat_flows)
    qdot_columns = _resolve_qdot_columns(heat_flows, selected_buildings)

    output = pd.DataFrame()
    output["Time"] = data["Time"]
    output["T_amb [°C]"] = pd.to_numeric(data["Tamb [°C]"], errors="coerce")
    output["Qsol [W/m2]"] = pd.to_numeric(data["Qsol [W/m2]"], errors="coerce")

    for building in selected_buildings:
        building_columns = qdot_columns[building]
        output[f"{building}_Qdot_dh [W]"] = _sum_columns(
            data, building_columns["dh"]
        )
        output[f"{building}_Qdot_heating_circuit [W]"] = _sum_columns(
            data, building_columns["heating_circuit"]
        )

    output["Qdot_dh [W]"] = _sum_columns(
        output, [f"{building}_Qdot_dh [W]" for building in selected_buildings]
    )
    output["Qdot_heating_circuit [W]"] = _sum_columns(
        output,
        [
            f"{building}_Qdot_heating_circuit [W]"
            for building in selected_buildings
        ],
    )
    output["Qdot_selected [W]"] = _resolve_selected_qdot(output, data, heat_flows)
    output["P_appliance [W]"] = 0.0
    output["P_kitchen [W]"] = 0.0
    if indoor_temperatures is not None:

        selected_prefixes = tuple(
            f"{building}_"
            for building in selected_buildings
        )

        temperature_columns = [
            column
            for column in indoor_temperatures.columns
            if column.startswith(selected_prefixes)
               and (
                       "_Tzone" in column
                       or "_Tset" in column
               )
        ]

        for column in temperature_columns:
            output[column] = pd.to_numeric(
                data[column],
                errors="coerce",
            )

        area_weights = _resolve_tset_area_weights()

        # --------------------------------------------------
        # Flächengewichtete Solltemperatur
        # --------------------------------------------------

        tset_columns = _resolve_temperature_columns(
            indoor_temperatures,
            selected_buildings,
            "Tset",
        )

        if tset_columns:
            output["T_set [°C]"] = _weighted_temperature(
                data,
                tset_columns,
                area_weights,
            )
        else:
            warnings.warn(
                f"No usable Tset columns found in "
                f"{indoor_temperatures_path}",
                RuntimeWarning,
                stacklevel=2,
            )

        # --------------------------------------------------
        # Flächengewichtete Innenraumtemperatur
        # --------------------------------------------------

        tzone_columns = _resolve_temperature_columns(
            indoor_temperatures,
            selected_buildings,
            "Tzone",
        )

        if tzone_columns:
            output["T_indoor [°C]"] = _weighted_temperature(
                data,
                tzone_columns,
                area_weights,
            )
        else:
            warnings.warn(
                f"No usable Tzone columns found in "
                f"{indoor_temperatures_path}",
                RuntimeWarning,
                stacklevel=2,
            )

    warnings.warn(
        "Experiment 3 CSV input does not contain P_appliance/P_kitchen columns. "
        "Internal gains are set to zero. Qdot is split into district-heating "
        "input and underfloor heating-circuit input.",
        RuntimeWarning,
        stacklevel=2,
    )
    _validate_required_columns(output, folder)
    return output


def _resolve_buildings(heat_flows):
    configured = os.environ.get("GREY_BOX_BUILDINGS")
    if configured:
        buildings = [building.strip() for building in configured.split(",") if building.strip()]
    else:
        buildings = list(DEFAULT_BUILDINGS)

    invalid = [building for building in buildings if building not in BUILDING_IDS]
    if invalid:
        raise ValueError(
            "Configured GREY_BOX_BUILDINGS must use B1, B2, and/or B3. "
            f"Invalid values: {invalid}"
        )

    missing = [
        building
        for building in buildings
        if not any(column.startswith(f"{building}_") for column in heat_flows.columns)
    ]
    if missing:
        raise ValueError(
            f"Configured GREY_BOX_BUILDINGS are missing from Exp3_heat_flows.csv: {missing}"
        )

    return buildings


def _resolve_qdot_columns(heat_flows, buildings):
    return {
        building: {
            "dh": _building_dh_columns(heat_flows, building),
            "heating_circuit": _building_heating_circuit_columns(heat_flows, building),
        }
        for building in buildings
    }


def _building_dh_columns(heat_flows, building):
    column = f"{building}_DH_Qth [W]"
    return [column] if column in heat_flows.columns else []


def _building_heating_circuit_columns(heat_flows, building):
    return [
        column
        for column in heat_flows.columns
        if column.startswith(f"{building}_")
        and column.endswith("_Qth [W]")
        and "_DH_" not in column
    ]


def _sum_columns(data, columns):
    if not columns:
        return 0.0
    return (
        data[columns]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .sum(axis=1)
    )


def _resolve_selected_qdot(output, raw_data, heat_flows):
    configured = os.environ.get("GREY_BOX_HEAT_FLOW_COLUMNS")
    if configured:
        columns = [column.strip() for column in configured.split(",") if column.strip()]
        missing = [column for column in columns if column not in heat_flows.columns]
        if missing:
            raise ValueError(
                "Configured GREY_BOX_HEAT_FLOW_COLUMNS are missing from "
                f"Exp3_heat_flows.csv: {missing}"
            )
        return _sum_columns(raw_data, columns)

    qdot_source = os.environ.get("GREY_BOX_QDOT_SOURCE", DEFAULT_QDOT_SOURCE)
    if qdot_source == "heating_circuit":
        return output["Qdot_heating_circuit [W]"]
    if qdot_source == "dh":
        return output["Qdot_dh [W]"]

    raise ValueError(
        "GREY_BOX_QDOT_SOURCE must be 'heating_circuit' or 'dh'. "
        f"Got: {qdot_source}"
    )


def calculate_solar_gains_from_qsol(qsol, building_parameters):
    """Convert measured global solar radiation to transmitted window gains."""
    window_area = _total_window_area(building_parameters)
    frame_fraction = getattr(building_parameters, "frame_area_fraction_of_window", 0.0)
    reduction_factor = getattr(
        building_parameters, "radiation_non_perpendicular_to_the_glazing", 1.0
    )
    solar_transmittance = _first_value(
        getattr(building_parameters, "g_gl_n_window", {"default": 1.0})
    )
    effective_window_area = (
        window_area * (1.0 - frame_fraction) * reduction_factor * solar_transmittance
    )
    return (
        pd.Series(qsol)
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .clip(lower=0.0)
        .mul(effective_window_area)
        .tolist()
    )


def _total_window_area(building_parameters):
    specific = getattr(building_parameters, "a_window_specific", None)
    if specific:
        return sum(float(value) for value in specific.values())
    return sum(float(value) for value in getattr(building_parameters, "a_window", {}).values())


def _first_value(values):
    if isinstance(values, dict):
        return float(next(iter(values.values())))
    return float(values)


def _resolve_tset_columns_unweighted_legacy(indoor_temperatures):
    configured = os.environ.get("GREY_BOX_TSET_COLUMNS")
    if configured:
        columns = [column.strip() for column in configured.split(",") if column.strip()]
        missing = [column for column in columns if column not in indoor_temperatures.columns]
        if missing:
            raise ValueError(
                "Configured GREY_BOX_TSET_COLUMNS are missing from "
                f"Exp3_indoor_temperatures.csv: {missing}"
            )
        return columns
    return [column for column in indoor_temperatures.columns if column.endswith("_Tset [°C]")]


def _resolve_temperature_columns(
    indoor_temperatures,
    selected_buildings,
    temperature_type,
):
    """
    Find temperature columns for the selected buildings.

    temperature_type:
        "Tset"  -> setpoint temperature
        "Tzone" -> actual zone / indoor temperature
    """

    selected_prefixes = tuple(
        f"{building}_" for building in selected_buildings
    )

    return [
        column
        for column in indoor_temperatures.columns
        if column.startswith(selected_prefixes)
        and f"_{temperature_type}" in column
        and column.endswith("C]")
    ]


def _resolve_tset_area_weights():
    configured = os.environ.get("GREY_BOX_TSET_AREA_WEIGHTS")
    if not configured:
        return DEFAULT_TSET_ZONE_AREAS

    weights = DEFAULT_TSET_ZONE_AREAS.copy()
    for entry in configured.split(","):
        if not entry.strip():
            continue
        if "=" not in entry:
            raise ValueError(
                "GREY_BOX_TSET_AREA_WEIGHTS entries must use 'zone=area', "
                f"got: {entry}"
            )
        key, value = entry.split("=", 1)
        weights[key.strip()] = float(value.strip())
    return weights


def _weighted_temperature(data, temperature_columns, area_weights):
    values = data[temperature_columns].apply(
        pd.to_numeric,
        errors="coerce"
    )

    weights = pd.Series(
        [
            _area_weight_for_temperature_column(
                column,
                area_weights
            )
            for column in temperature_columns
        ],
        index=temperature_columns,
        dtype=float,
    )

    weighted_values = values.mul(weights, axis=1)

    valid_weights = (
        values.notna()
        .mul(weights, axis=1)
        .sum(axis=1)
    )

    return (
        weighted_values.sum(axis=1)
        .div(valid_weights)
        .where(valid_weights > 0)
    )
def _area_weight_for_temperature_column(column, area_weights):

    # z.B.
    # B1_R1_Tset [°C]  -> B1_R1
    # B1_R1_Tzone [°C] -> B1_R1

    building_zone = (
        column
        .split("_Tset", 1)[0]
        .split("_Tzone", 1)[0]
    )

    # B1_R1 -> R1
    if "_" in building_zone:
        zone = building_zone.split("_", 1)[1]
    else:
        zone = building_zone

    for key in (building_zone, zone):
        if key in area_weights:
            return area_weights[key]

    raise ValueError(
        f"No area weight configured for temperature column "
        f"'{column}'."
    )
def _area_weight_for_tset_column(column, area_weights):
    building_zone = _building_zone_from_tset_column(column)
    zone = _zone_from_tset_column(column)
    for key in (building_zone, zone):
        if key in area_weights:
            return area_weights[key]
    raise ValueError(
        f"No area weight configured for Tset column '{column}'. Add it via "
        "GREY_BOX_TSET_AREA_WEIGHTS, for example 'R1=25.99'."
    )


def _building_zone_from_tset_column(column):
    return column.split("_Tset", 1)[0]


def _zone_from_tset_column(column):
    building_zone = _building_zone_from_tset_column(column)
    if "_" not in building_zone:
        return building_zone
    return building_zone.split("_", 1)[1]


def _validate_required_columns(data, source):
    missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"Measurement data from {source} missing columns: {missing}")
