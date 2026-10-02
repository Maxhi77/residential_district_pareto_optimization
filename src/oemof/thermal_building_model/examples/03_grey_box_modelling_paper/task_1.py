import os
import pprint as pp
import logging

import pandas as pd
from matplotlib import pyplot as plt

import oemof.solph as solph
from oemof.solph import views
from oemof.tools import logger

from oemof.thermal_building_model.tabula.tabula_reader import Building
from oemof.thermal_building_model.m_5RC import M5RC

from measurement_data import (
    calculate_solar_gains_from_qsol,
    load_measurement_data,
)

from evaluation_metrics import (
    evaluate_temperature,
    period_rmse,
    peak_error,
)

from temperature_plots import plot_zone_temperatures


# =========================================================
# Konfiguration
# =========================================================

EXPERIMENT = 3

BUILDINGS = (
    "B1",
    "B2",
    "B3",
)

DATA_ROOT = (
    r"C:\Users\hill_mx\Desktop\Input_kevin_paper"
    r"\Experiment_2425\Experiment_2425"
)

MEASUREMENT_SOURCE = os.path.join(
    DATA_ROOT,
    f"Experiment {EXPERIMENT}",
)

RESULTS_ROOT = (
    r"C:\Users\hill_mx\Desktop\Input_kevin_paper\results\task_1"
)

SOLVER = "gurobi"


# =========================================================
# Hilfsfunktion:
# Ergebnisse eines einzelnen Gebäudes berechnen
# =========================================================

def run_building(building_id):
    """
    Runs the complete simulation and evaluation
    for one building.

    Parameters
    ----------
    building_id : str
        Building ID, e.g. "B1", "B2" or "B3".

    Returns
    -------
    dict
        Summary results for the building.
    """

    print("\n")
    print("=" * 70)
    print(f"START BUILDING: {building_id}")
    print("=" * 70)

    # ---------------------------------------------------------
    # Ergebnisordner erzeugen
    # B1 -> building1
    # B2 -> building2
    # B3 -> building3
    # ---------------------------------------------------------

    building_number = building_id.replace("B", "")

    results_dir = os.path.join(
        RESULTS_ROOT,
        f"building{building_number}",
    )

    os.makedirs(
        results_dir,
        exist_ok=True,
    )

    print(f"Experiment: {EXPERIMENT}")
    print(f"Building:   {building_id}")
    print(f"Input:      {MEASUREMENT_SOURCE}")
    print(f"Results:    {results_dir}")

    # ---------------------------------------------------------
    # Dem measurement_data-Loader explizit mitteilen,
    # welches Gebäude geladen werden soll
    # ---------------------------------------------------------

    os.environ["GREY_BOX_BUILDINGS"] = building_id

    # =========================================================
    # Messdaten laden
    # =========================================================

    measurement_df = load_measurement_data(
        MEASUREMENT_SOURCE,
        experiment=EXPERIMENT,
    )

    # =========================================================
    # Zeitachse
    # =========================================================

    measurement_df["Time"] = pd.to_datetime(
        measurement_df["Time"]
    )

    # =========================================================
    # Messgrößen numerisch konvertieren
    # =========================================================

    measurement_df["T_amb [°C]"] = pd.to_numeric(
        measurement_df["T_amb [°C]"],
        errors="coerce",
    )

    measurement_df["P_appliance [W]"] = pd.to_numeric(
        measurement_df["P_appliance [W]"],
        errors="coerce",
    )

    measurement_df["P_kitchen [W]"] = pd.to_numeric(
        measurement_df["P_kitchen [W]"],
        errors="coerce",
    )

    measurement_df["Qdot_selected [W]"] = pd.to_numeric(
        measurement_df["Qdot_selected [W]"],
        errors="coerce",
    )

    # Time als Index
    measurement_df.set_index(
        "Time",
        inplace=True,
    )

    # =========================================================
    # Stündliche Eingangsdaten
    # =========================================================

    hourly_avg_temp = (
        measurement_df["T_amb [°C]"]
        .resample("h")
        .mean()
    )

    hourly_avg_p_appl = (
        measurement_df["P_appliance [W]"]
        .resample("h")
        .mean()
    )

    hourly_avg_p_kit = (
        measurement_df["P_kitchen [W]"]
        .resample("h")
        .mean()
    )

    hourly_avg_q_demand = (
        measurement_df["Qdot_selected [W]"]
        .resample("h")
        .mean()
    )

    # =========================================================
    # Solarstrahlung
    # =========================================================

    if "Qsol [W/m2]" not in measurement_df.columns:
        raise ValueError(
            "Measurement data must contain 'Qsol [W/m2]'."
        )

    hourly_avg_qsol = (
        measurement_df["Qsol [W/m2]"]
        .resample("h")
        .mean()
        .ffill()
        .bfill()
    )

    # =========================================================
    # Solltemperatur
    # =========================================================

    if "T_set [°C]" not in measurement_df.columns:
        raise ValueError(
            f"No area-weighted T_set available for {building_id}."
        )

    hourly_avg_t_set = (
        measurement_df["T_set [°C]"]
        .resample("h")
        .mean()
        .ffill()
        .bfill()
    )

    # =========================================================
    # Gemessene Innenraumtemperatur
    # =========================================================

    if "T_indoor [°C]" not in measurement_df.columns:
        raise ValueError(
            f"No area-weighted T_indoor available for {building_id}."
        )

    hourly_avg_t_indoor = (
        measurement_df["T_indoor [°C]"]
        .resample("h")
        .mean()
        .ffill()
        .bfill()
    )

    # =========================================================
    # Zeitreihen vorbereiten
    # =========================================================

    t_outside = hourly_avg_temp.tolist()

    internal_gains = [
        appliance + kitchen
        for appliance, kitchen in zip(
            hourly_avg_p_appl.tolist(),
            hourly_avg_p_kit.tolist(),
        )
    ]

    time_index = hourly_avg_temp.index

    number_of_time_steps = len(
        time_index
    )

    print(
        f"Number of hourly time steps: "
        f"{number_of_time_steps}"
    )

    print(
        f"Measured T_indoor range: "
        f"{hourly_avg_t_indoor.min():.3f} - "
        f"{hourly_avg_t_indoor.max():.3f} °C"
    )

    # =========================================================
    # Gebäudemodell erzeugen
    # =========================================================

    from building_parameters import (
        building_params_ifc as building_params
    )

    building_example = Building(
        country="DE",
        construction_year=2016,
        class_building="very heavy",
        building_type="SFH",
        refurbishment_status="advanced_refurbishment",
        number_of_time_steps=number_of_time_steps,
        building_parameters=building_params,
    )

    building_example.calculate_all_parameters()

    # =========================================================
    # Solare Gewinne
    # =========================================================

    solar_gains = calculate_solar_gains_from_qsol(
        hourly_avg_qsol.tolist(),
        building_params,
    )

    # =========================================================
    # Temperaturgrenzen des Modells
    # =========================================================

    # Aktuell wie in deinem bisherigen Skript:
    # gemessene Solltemperatur wird NICHT als Heizgrenze genutzt.
    #
    # Falls du sie später verwenden möchtest:
    #
    # t_set_heating = hourly_avg_t_set.tolist()

    t_set_heating = [
        2
    ] * number_of_time_steps

    t_set_cooling = [
        35
    ] * number_of_time_steps

    # =========================================================
    # Energy System
    # =========================================================

    es = solph.EnergySystem(
        timeindex=time_index,
        infer_last_interval=False,
    )

    # =========================================================
    # Busse
    # =========================================================

    b_heat = solph.buses.Bus(
        label="b_heat"
    )

    b_cool = solph.buses.Bus(
        label="b_cool"
    )

    b_elect = solph.buses.Bus(
        label="electricity_from_grid"
    )

    es.add(
        b_heat,
        b_cool,
        b_elect,
    )

    # =========================================================
    # Stromquelle
    # =========================================================

    es.add(
        solph.components.Source(
            label="elect_from_grid",
            outputs={
                b_elect: solph.flows.Flow(
                    variable_costs=30
                )
            },
        )
    )

    # =========================================================
    # Stromsenke
    # =========================================================

    es.add(
        solph.components.Sink(
            label="elect_into_grid",
            inputs={
                b_elect: solph.flows.Flow(
                    variable_costs=-0.001
                )
            },
        )
    )

    # =========================================================
    # Gemessener Heizwärmestrom
    # =========================================================

    es.add(
        solph.components.Source(
            label="HeatFlowToBuilding",
            outputs={
                b_heat: solph.flows.Flow(
                    nominal_value=1,
                    fix=hourly_avg_q_demand,
                )
            },
        )
    )

    # =========================================================
    # Kühlung
    # =========================================================

    es.add(
        solph.components.Converter(
            label="ElectricalCooler",
            inputs={
                b_cool: solph.flows.Flow(
                    nominal_value=20000
                ),
                b_elect: solph.flows.Flow(),
            },
            outputs={},
            conversion_factors={
                b_cool: 0.9,
                b_elect: 1,
            },
        )
    )

    # =========================================================
    # 5R1C Gebäude
    # =========================================================

    es.add(
        M5RC(
            label="GenericBuilding",
            inputs={
                b_heat: solph.flows.Flow(
                    variable_costs=0
                )
            },
            outputs={
                b_cool: solph.flows.Flow(
                    variable_costs=5
                )
            },
            solar_gains=solar_gains,
            t_outside=t_outside,
            internal_gains=internal_gains,
            t_set_heating=t_set_heating,
            t_set_cooling=t_set_cooling,
            building_config=building_example.building_config,
            t_inital=21.3,
        )
    )

    # =========================================================
    # Optimierung
    # =========================================================

    logging.info(
        "Optimise building %s",
        building_id,
    )

    model = solph.Model(es)

    model.solve(
        solver=SOLVER
    )

    # =========================================================
    # Ergebnisse verarbeiten
    # =========================================================

    es.results["main"] = (
        solph.processing.results(model)
    )

    es.results["meta"] = (
        solph.processing.meta_results(model)
    )

    results = es.results["main"]

    custom_building = views.node(
        results,
        "GenericBuilding",
    )

    # =========================================================
    # Heizenergie
    # =========================================================

    flow_data = custom_building[
        "sequences"
    ][
        (
            ("b_heat", "GenericBuilding"),
            "flow",
        )
    ]

    heating_demand = flow_data.sum()

    floor_area = (
        building_example.floor_area
    )

    relative_heating_demand = (
        heating_demand / floor_area
    )

    print(
        f"\n{building_id} heating demand: "
        f"{heating_demand / 1000:.3f} kWh"
    )

    print(
        f"{building_id} heating demand: "
        f"{relative_heating_demand / 1000:.3f} "
        f"kWh/m²"
    )

    # =========================================================
    # Raumtemperaturen plotten
    # =========================================================

    plot_zone_temperatures(
        measurement_df,
        building=building_id,
        results_dir=results_dir,
    )

    # =========================================================
    # Außentemperatur
    # =========================================================

    fig, ax = plt.subplots(
        figsize=(10, 5)
    )

    ax.plot(
        time_index,
        t_outside,
    )

    ax.set_title(
        f"Outside Air Temperature - {building_id}"
    )

    ax.set_ylabel(
        "Temperature [°C]"
    )

    ax.set_xlabel(
        "Time"
    )

    fig.autofmt_xdate()

    fig.savefig(
        os.path.join(
            results_dir,
            "outside_air_temperature.png",
        ),
        dpi=300,
        bbox_inches="tight",
    )

    plt.show()
    plt.close(fig)

    # =========================================================
    # Solar Gains
    # =========================================================

    fig, ax = plt.subplots(
        figsize=(10, 5)
    )

    ax.plot(
        time_index,
        solar_gains,
    )

    ax.set_title(
        f"Solar Gains - {building_id}"
    )

    ax.set_ylabel(
        "Solar Gains [W]"
    )

    ax.set_xlabel(
        "Time"
    )

    fig.autofmt_xdate()

    fig.savefig(
        os.path.join(
            results_dir,
            "solar_gains.png",
        ),
        dpi=300,
        bbox_inches="tight",
    )

    plt.show()
    plt.close(fig)

    # =========================================================
    # Internal Gains
    # =========================================================

    fig, ax = plt.subplots(
        figsize=(10, 5)
    )

    ax.plot(
        time_index,
        internal_gains,
    )

    ax.set_title(
        f"Internal Gains - {building_id}"
    )

    ax.set_ylabel(
        "Internal Gains [W]"
    )

    ax.set_xlabel(
        "Time"
    )

    fig.autofmt_xdate()

    fig.savefig(
        os.path.join(
            results_dir,
            "internal_gains.png",
        ),
        dpi=300,
        bbox_inches="tight",
    )

    plt.show()
    plt.close(fig)

    # =========================================================
    # Simulierte Innenraumtemperatur
    # =========================================================

    t_air_simulated = custom_building[
        "sequences"
    ][
        (
            ("GenericBuilding", "None"),
            "t_air",
        )
    ]

    # =========================================================
    # Vergleich:
    # Simulation vs. Messung
    # =========================================================

    fig, ax = plt.subplots(
        figsize=(12, 6)
    )

    t_air_simulated.plot(
        ax=ax,
        kind="line",
        drawstyle="steps-post",
        label=f"5R1C {building_id}",
    )

    hourly_avg_t_indoor.plot(
        ax=ax,
        label=f"Measured {building_id}",
    )

    hourly_avg_t_set.plot(
        ax=ax,
        linestyle="--",
        label=f"T_set {building_id}",
    )

    ax.set_title(
        f"Indoor Temperature Comparison - {building_id}"
    )

    ax.set_ylabel(
        "Indoor Temperature [°C]"
    )

    ax.set_xlabel(
        "Time"
    )

    ax.legend()

    fig.savefig(
        os.path.join(
            results_dir,
            "temperaturvergleich.png",
        ),
        dpi=300,
        bbox_inches="tight",
    )

    plt.show()
    plt.close(fig)

    # =========================================================
    # Temperatur-Evaluation
    # =========================================================

    temperature_metrics = evaluate_temperature(
        reference=hourly_avg_t_indoor,
        prediction=t_air_simulated,
    )

    print("\n")
    print("-" * 50)
    print(
        f"TEMPERATURE EVALUATION {building_id}"
    )
    print("-" * 50)

    for metric, value in (
        temperature_metrics.items()
    ):
        print(
            f"{metric}: {value:.4f}"
        )

    # =========================================================
    # Stündlicher RMSE
    # =========================================================

    hourly_rmse = period_rmse(
        reference=hourly_avg_t_indoor,
        prediction=t_air_simulated,
        period="h",
    )

    # =========================================================
    # 12-Stunden-RMSE
    # =========================================================

    halfday_rmse = period_rmse(
        reference=hourly_avg_t_indoor,
        prediction=t_air_simulated,
        period="12h",
    )
    # =========================================================
    # Zusammenfassende Periodenmetriken
    # =========================================================

    mean_hourly_rmse = hourly_rmse.mean()
    max_hourly_rmse = hourly_rmse.max()

    mean_halfday_rmse = halfday_rmse.mean()
    max_halfday_rmse = halfday_rmse.max()
    # =========================================================
    # Peak Error
    # =========================================================

    temperature_peak_error = peak_error(
        reference=hourly_avg_t_indoor,
        prediction=t_air_simulated,
    )

    print("\nPeak evaluation:")

    for metric, value in (
        temperature_peak_error.items()
    ):
        print(
            f"{metric}: {value}"
        )

    # =========================================================
    # Evaluation speichern
    # =========================================================

    pd.DataFrame(
        [temperature_metrics]
    ).to_csv(
        os.path.join(
            results_dir,
            "temperature_evaluation.csv",
        ),
        index=False,
    )

    hourly_rmse.to_csv(
        os.path.join(
            results_dir,
            "temperature_rmse_hourly.csv",
        )
    )

    halfday_rmse.to_csv(
        os.path.join(
            results_dir,
            "temperature_rmse_12h.csv",
        )
    )

    pd.DataFrame(
        [temperature_peak_error]
    ).to_csv(
        os.path.join(
            results_dir,
            "temperature_peak_error.csv",
        ),
        index=False,
    )

    # =========================================================
    # Heizleistungsvergleich
    # =========================================================

    combined_data = pd.DataFrame(
        {
            "Flow": flow_data,
            "Measured_Q_Demand": (
                hourly_avg_q_demand
            ),
        }
    ).dropna()

    fig, ax = plt.subplots(
        figsize=(12, 6)
    )

    combined_data[
        "Flow"
    ].plot(
        ax=ax,
        kind="line",
        drawstyle="steps-post",
        label=f"5R1C {building_id}",
    )

    combined_data[
        "Measured_Q_Demand"
    ].plot(
        ax=ax,
        label=f"Measured {building_id}",
    )

    ax.set_title(
        f"Heat Demand Comparison - {building_id}"
    )

    ax.set_ylabel(
        "Heat Demand [W]"
    )

    ax.set_xlabel(
        "Time"
    )

    ax.legend()

    fig.savefig(
        os.path.join(
            results_dir,
            "heat_demand.png",
        ),
        dpi=300,
        bbox_inches="tight",
    )

    plt.show()
    plt.close(fig)

    # =========================================================
    # 4-Stunden gleitender Mittelwert
    # =========================================================

    # Da die Daten stündlich sind:
    # window=4 entspricht 4 Stunden.

    window_size = 4

    combined_data[
        "Flow_4h_avg"
    ] = (
        combined_data["Flow"]
        .rolling(window=window_size)
        .mean()
    )

    combined_data[
        "Measured_Q_Demand_4h_avg"
    ] = (
        combined_data[
            "Measured_Q_Demand"
        ]
        .rolling(window=window_size)
        .mean()
    )

    fig, ax = plt.subplots(
        figsize=(12, 6)
    )

    combined_data[
        "Flow_4h_avg"
    ].plot(
        ax=ax,
        label=f"5R1C {building_id} - 4h mean",
    )

    combined_data[
        "Measured_Q_Demand_4h_avg"
    ].plot(
        ax=ax,
        label=f"Measured {building_id} - 4h mean",
    )

    ax.set_title(
        f"4h Mean Heat Demand - {building_id}"
    )

    ax.set_ylabel(
        "Heat Demand [W]"
    )

    ax.set_xlabel(
        "Time"
    )

    ax.legend()

    fig.savefig(
        os.path.join(
            results_dir,
            "heat_demand_4h_average.png",
        ),
        dpi=300,
        bbox_inches="tight",
    )

    plt.show()
    plt.close(fig)

    # =========================================================
    # Cooling demand
    # =========================================================

    cooling_flow = custom_building[
        "sequences"
    ][
        (
            ("GenericBuilding", "b_cool"),
            "flow",
        )
    ]

    fig, ax = plt.subplots(
        figsize=(10, 5)
    )

    cooling_flow.plot(
        ax=ax,
        kind="line",
        drawstyle="steps-post",
    )

    ax.set_title(
        f"Cooling Demand - {building_id}"
    )

    ax.set_ylabel(
        "Cooling Demand [W]"
    )

    ax.set_xlabel(
        "Time"
    )

    fig.savefig(
        os.path.join(
            results_dir,
            "cooling_demand.png",
        ),
        dpi=300,
        bbox_inches="tight",
    )

    plt.show()
    plt.close(fig)

    # =========================================================
    # Zeitreihen ebenfalls als CSV speichern
    # =========================================================

    output_timeseries = pd.DataFrame(
        {
            "T_air_measured [°C]":
                hourly_avg_t_indoor,
            "T_air_simulated [°C]":
                t_air_simulated,
            "T_set [°C]":
                hourly_avg_t_set,
            "T_ambient [°C]":
                hourly_avg_temp,
            "Q_heat_measured [W]":
                hourly_avg_q_demand,
            "Q_heat_simulated [W]":
                flow_data,
        }
    )

    output_timeseries.to_csv(
        os.path.join(
            results_dir,
            "timeseries_results.csv",
        )
    )

    # =========================================================
    # Zusammenfassung für dieses Gebäude
    # =========================================================

    summary = {
        "Building": building_id,

        "Heating demand [kWh]":
            heating_demand / 1000,

        "Heating demand [kWh/m2]":
            relative_heating_demand / 1000,

        "Measured T_min [°C]":
            hourly_avg_t_indoor.min(),

        "Measured T_max [°C]":
            hourly_avg_t_indoor.max(),

        "Measured T_mean [°C]":
            hourly_avg_t_indoor.mean(),

        # Periodengenauigkeit
        "Mean hourly RMSE [K]":
            mean_hourly_rmse,

        "Max hourly RMSE [K]":
            max_hourly_rmse,

        "Mean 12h RMSE [K]":
            mean_halfday_rmse,

        "Max 12h RMSE [K]":
            max_halfday_rmse,
    }
    # Evaluationsmetriken ergänzen
    summary.update(
        temperature_metrics
    )

    # einige Peakmetriken ergänzen
    summary[
        "Peak error [K]"
    ] = temperature_peak_error[
        "Peak error [K]"
    ]

    summary[
        "Absolute peak error [K]"
    ] = temperature_peak_error[
        "Absolute peak error [K]"
    ]

    summary[
        "Peak timing error [h]"
    ] = temperature_peak_error[
        "Peak timing error [h]"
    ]

    print("\n")
    print("=" * 70)
    print(f"FINISHED BUILDING: {building_id}")
    print("=" * 70)

    return summary


# =========================================================
# Main
# =========================================================

def main():

    os.makedirs(
        RESULTS_ROOT,
        exist_ok=True,
    )

    # Logger nur einmal initialisieren
    logger.define_logging(
        logfile=os.path.join(
            RESULTS_ROOT,
            "oemof_example.log",
        ),
        screen_level=logging.INFO,
        file_level=logging.INFO,
    )

    # Hier sammeln wir die Ergebnisse aller Gebäude
    all_building_results = []

    # =========================================================
    # LOOP über B1, B2 und B3
    # =========================================================

    for building_id in BUILDINGS:

        summary = run_building(
            building_id
        )

        all_building_results.append(
            summary
        )

    # =========================================================
    # Gesamtübersicht speichern
    # =========================================================

    summary_df = pd.DataFrame(
        all_building_results
    )

    summary_path = os.path.join(
        RESULTS_ROOT,
        "all_buildings_summary.csv",
    )

    summary_df.to_csv(
        summary_path,
        index=False,
    )

    # =========================================================
    # Gesamtübersicht ausgeben
    # =========================================================

    print("\n")
    print("=" * 70)
    print("ALL BUILDINGS FINISHED")
    print("=" * 70)

    print(
        summary_df.to_string(
            index=False
        )
    )

    print(
        "\nSummary saved to:"
    )

    print(
        summary_path
    )


# =========================================================
# Start
# =========================================================

if __name__ == "__main__":
    main()