import os
import pprint as pp
import logging
from matplotlib import pyplot as plt
import pandas as pd

from oemof.thermal_building_model.helpers.path_helper import get_project_root
from oemof.thermal_building_model.helpers import calculate_gain_by_sun
from oemof.thermal_building_model.tabula.tabula_reader import Building
from oemof.thermal_building_model.m_5RC import M5RC

import oemof.solph as solph
from oemof.solph import views
from oemof.tools import logger

"""
General description
-------------------
This examples optimizes the internal building temperature.
It is suppose to show how to use the building component M5RC.
For the generation of a M5RC the tabula building data set is used.
In the end it compares the heat demand calculated by oemof and the tabula data sheet.


Installation requirements
-------------------------
This example requires the version v0.5.x of oemof.solph. Install by:

    pip install 'oemof.solph>=0.5,<0.6'

"""

__copyright__ = "oemof developer group"
__license__ = "MIT"

EXAMPLE_DIR = os.path.dirname(__file__)
MEASUREMENT_FILE = os.environ.get(
    "GREY_BOX_MEASUREMENT_FILE",
    os.path.join(EXAMPLE_DIR, "Datensatz_Musterhaus_KIT_2024_12_13.xlsx"),
)


def main():
    #  create solver
    solver = "gurobi"  # 'glpk', 'gurobi',....
    main_path = get_project_root()

    # Datei laden
    file_path = MEASUREMENT_FILE

    # Excel-Datei öffnen und das Blatt 'Experiment 1' auswählen
    xls = pd.ExcelFile(file_path)
    experiment1_df = pd.read_excel(xls, sheet_name='Experiment 2')
    # Zeitstempel und Temperatur-Spalte extrahieren
    experiment1_df['Time'] = pd.to_datetime(experiment1_df['Time'])
    experiment1_df['T_amb [°C]'] = experiment1_df['T_amb [°C]'].astype(float)
    experiment1_df['P_appliance [W]'] = experiment1_df['P_appliance [W]'].astype(float)
    experiment1_df['P_kitchen [W]'] = experiment1_df['P_kitchen [W]'].astype(float)
    experiment1_df['Q_hp,prim [W]'] = experiment1_df['Q_hp,prim [W]'].astype(float)
    # Index auf den Zeitstempel setzen
    experiment1_df.set_index('Time', inplace=True)
    # Resampling auf stündliche Mittelwerte
    hourly_avg_temp = experiment1_df['T_amb [°C]'].resample('H').mean()
    hourly_avg_p_appl = experiment1_df['P_appliance [W]'].resample('H').mean()
    hourly_avg_p_kit = experiment1_df['P_kitchen [W]'].resample('H').mean()
    hourly_avg_q_demand = experiment1_df['Q_hp,prim [W]'].resample('H').mean()
    # Die stündlichen Durchschnittswerte anzeigen
    # Optional: Liste der stündlichen Durchschnittswerte ausgeben
    hourly_avg_list = hourly_avg_temp.tolist()
    hourly_avg_p_appl = hourly_avg_p_appl.tolist()
    hourly_avg_p_kit = hourly_avg_p_kit.tolist()
    internal_gains = [a + b for a, b in zip(hourly_avg_p_appl, hourly_avg_p_kit)]
    print("Stündliche Durchschnittswerte der Temperatur:", hourly_avg_list)
    t_outside = hourly_avg_list
    time_index=hourly_avg_temp.index
    number_of_time_steps = len(t_outside)
    pv_data = pd.read_csv(
        os.path.join(
            main_path,
            "thermal_building_model",
            "input",
            "sfh_example",
            "pvwatts_hourly_1kW.csv",
        )
    )
    from building_parameters import building_params_ifc as building_params

    # Generates 5RC Building-Model
    building_example = Building(
        country="DE",
        construction_year=2016,
        class_building="very light",
        building_type="SFH",
        refurbishment_status="advanced_refurbishment",
        number_of_time_steps=number_of_time_steps,
        building_parameters=building_params
    )

    building_example.calculate_all_parameters()

    # Pre-Calculation of solar gains with weather_data and building_data
    location = calculate_gain_by_sun.Location(
        #latitude=48.973,
        #longitude=8.33,
        epwfile_path=os.path.join(
            os.path.dirname(__file__),
            "DWD_Station_4177_2024.epw",
        ),
    )


    if True:
        solar_gains = building_example.calc_solar_gaings_through_windows(
            time_index=time_index,
            object_location_of_building=location,
            number_of_time_steps=8760
        )
    else:
        solar_gains = []

    # Internal gains of residents, machines (f.e. fridge, computer,...) and lights have to be added manually
    a_1_5 = 25.99 + 25.85 + 47.18 + 64.47 + 77.31
    a_b = 12.74
    a_k  = 26.08
    a_c = 28.06 + 39.01
    t_set_heating = []
    t_set_cooling = []
    for _ in range(number_of_time_steps ):
        t_set_heating.append((21*a_1_5 +  24*a_b + 18*a_k + 18*a_c)/(a_1_5+a_b+a_k+a_c))
        t_set_cooling.append(25)
        #solar_gains.append(0)
    # initiate the logger (see the API docs for more information)
    logger.define_logging(
        logfile="oemof_example.log",
        screen_level=logging.INFO,
        file_level=logging.INFO,
    )

    logging.info("Initialize the energy system")
    date_time_index = time_index
    if False:
        date_time_index = solph.create_time_index(
        2012, number=number_of_time_steps)
    es = solph.EnergySystem(timeindex=date_time_index,
                            infer_last_interval=False)

    # create electricity, heat and cooling flow
    b_heat = solph.buses.Bus(label="b_heat")
    es.add(b_heat)
    b_cool = solph.buses.Bus(label="b_cool")
    es.add(b_cool)
    b_elect = solph.buses.Bus(label="electricity_from_grid")
    es.add(b_elect)

    es.add(
        solph.components.Source(
            label="elect_from_grid",
            outputs={b_elect: solph.flows.Flow(variable_costs=30)},
        )
    )

    es.add(
        solph.components.Sink(
            label="elect_into_grid",
            inputs={b_elect: solph.flows.Flow(variable_costs=-0.001)},
        )
    )
    es.add(
        solph.components.Converter(
            label="ElectricalHeater",
            inputs={b_elect: solph.flows.Flow()},
            outputs={b_heat: solph.flows.Flow(nominal_value=20000)},
            conversion_factors={b_elect: 1},
        )
    )
    es.add(
        solph.components.Converter(
            label="ElectricalCooler",
            inputs={
                b_cool: solph.flows.Flow(nominal_value=20000),
                b_elect: solph.flows.Flow(),
            },
            outputs={},
            conversion_factors={b_cool: 0.9, b_elect: 1},
        )
    )
    if False:
        es.add(solph.components.Source(
            label="pv",
            outputs={
                b_elect: solph.Flow(
                    fix=pv_data["AC System Output (W)"],
                    nominal_value= 1000000
                    ),}
                ))

    es.add(
        M5RC(
            label="GenericBuilding",
            inputs={b_heat: solph.flows.Flow(variable_costs=0)},
            outputs={b_cool: solph.flows.Flow(variable_costs=5)},
            solar_gains=solar_gains,
            t_outside=t_outside,
            internal_gains=internal_gains,
            t_set_heating=t_set_heating,
            t_set_cooling=t_set_cooling,
            building_config=building_example.building_config,
            t_inital=21,
        )
    )

    ##########################################################################
    # Optimise the energy system and plot the results
    ##########################################################################

    logging.info("Optimise the energy system")

    # initialise the operational model
    model = solph.Model(es)

    # if tee_switch is true solver messages will be displayed
    logging.info("Solve the optimization problem")
    model.solve(solver=solver)

    logging.info("Store the energy system with the results.")

    # The processing module of the outputlib can be used to extract the results
    # from the model transfer them into a homogeneous structured dictionary.

    # add results to the energy system to make it possible to store them.
    es.results["main"] = solph.processing.results(model)
    es.results["meta"] = solph.processing.meta_results(model)
    results = es.results["main"]


    custom_building = views.node(results, "GenericBuilding")
    heating_demand = custom_building["sequences"][(("b_heat", "GenericBuilding"), "flow")].sum()
    floor_area = building_example.floor_area
    relative_heating_demand= heating_demand / floor_area
    print("annual heating demand in kWh: "+str(heating_demand/1000))

    print("annual heating demand in kWh/m^2: "+str(relative_heating_demand/1000))
    plt.plot(t_outside)
    plt.title("Tair")  # Titel für den ersten Plot
    plt.show()
    plt.plot(solar_gains)
    plt.title("Solar Gains in Watt")
    plt.show()
    plt.plot(internal_gains)
    plt.title("Internal Gains in Watt")
    # Titel für den ersten Plot
    plt.show()
    fig, ax = plt.subplots(figsize=(10, 5))
    custom_building["sequences"][(("GenericBuilding", "None"), "t_air")].plot(
        ax=ax, kind="line", drawstyle="steps-post"
    )

    ax.set_ylabel("t_air in Celsius")
    plt.show()
    # Erstelle das ursprüngliche Diagramm


    # Angenommene Daten aus custom_building und hourly_avg_q_demand
    custom_building = views.node(results, "GenericBuilding")
    flow_data = custom_building["sequences"][(("b_heat", "GenericBuilding"), "flow")]

    # hourly_avg_q_demand muss die gleiche Länge und den gleichen Index wie flow_data haben
    # Wir kombinieren beide Zeitreihen und entfernen NaN-Werte
    combined_data = pd.DataFrame({
        'Flow': flow_data,#(24*6):(24*9)
        'Hourly_Avg_Q_Demand': hourly_avg_q_demand #(24*6):(24*9)
    }).dropna()  # Entfernt Zeilen, die NaN-Werte enthalten

    # Erstelle das ursprüngliche Diagramm
    fig, ax = plt.subplots(figsize=(10, 5))

    # Plot für das erste Datenobjekt (GenericBuilding Flow)
    combined_data['Flow'].plot(ax=ax, kind="line", drawstyle="steps-post", label="5R1C")

    # Plot für hourly_avg_q_demand in einer anderen Farbe
    combined_data['Hourly_Avg_Q_Demand'].plot(ax=ax, color='red', label="KIT")

    # Achsenbeschriftung
    ax.set_ylabel("heat demand in Watt")

    # Legende hinzufügen
    ax.legend()

    # Zeige das Diagramm an
    plt.show()
    print("heat demand 5R1C in kWh: "+str(sum(combined_data['Flow'])))
    print("heat demand KIT in kWh: "+str(sum(combined_data['Hourly_Avg_Q_Demand'])))

    # 4h gleitender Durchschnitt (rolling mean)
    window_size = 8
    combined_data['Flow_4h_avg'] = combined_data['Flow'].rolling(window=window_size).mean()
    combined_data['Hourly_Avg_Q_Demand_4h_avg'] = combined_data['Hourly_Avg_Q_Demand'].rolling(
        window=window_size).mean()

    # Plot Original und geglättete Daten
    fig, ax = plt.subplots(figsize=(12, 6))

    # Geglättete Daten
    combined_data['Flow_4h_avg'].plot(ax=ax, label="5R1C (4h Mittel)")
    combined_data['Hourly_Avg_Q_Demand_4h_avg'].plot(ax=ax, color='red',  label="KIT (4h Mittel)")

    ax.set_ylabel("heat demand in Watt 4h Average")
    ax.legend()
    plt.show()


    fig, ax = plt.subplots(figsize=(10, 5))
    custom_building = views.node(results, "GenericBuilding")
    custom_building["sequences"][(("GenericBuilding", "b_cool"), "flow")].plot(
        ax=ax, kind="line", drawstyle="steps-post"
    )
    ax.set_ylabel("cooling demand in Watt")
    plt.show()

    # print the solver results
    print("********* Meta results *********")
    pp.pprint(es.results["meta"])
    print("")


if __name__ == "__main__":
    main()
