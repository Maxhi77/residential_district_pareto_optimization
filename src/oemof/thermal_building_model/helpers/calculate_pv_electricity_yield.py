from pvlib.pvsystem import PVSystem
from pvlib.modelchain import ModelChain
from pvlib.iotools import read_epw
from pvlib.location import Location
import pvlib
# Standort definieren
from pvlib.pvsystem import PVSystem
from pvlib.modelchain import ModelChain
from pvlib.iotools import read_epw
from pvlib.location import Location
import matplotlib.pyplot as plt
import pandas as pd
import pvlib
import json
import os
def simulate_pv_yield(pv_nominal_power_in_watt, epw_path, tilt=35, azimuth=180, show_plot=True):
    # EPW einlesen
    try:
        data, meta = read_epw(epw_path)
    except Exception as e:
        print(f"Fehler beim Einlesen der EPW-Datei: {e}")
        folder_path = os.path.dirname(epw_path)
        data = pd.read_csv( os.path.join(folder_path, 'data.csv'), index_col=0, parse_dates=True)  # Lade CSV-Daten
        with open(os.path.join(folder_path, 'meta.json'), 'r') as f:  # Lade JSON-Metadaten
            meta = json.load(f)

    # Standort aus EPW
    site = Location(meta['latitude'], meta['longitude'], tz=meta['TZ'])

    # DC-Leistung in W
    pdc0_watt = pv_nominal_power_in_watt

    # Einfaches PV-System
    system = PVSystem(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        module_parameters={'pdc0': pdc0_watt, 'gamma_pdc': -0.004},
        inverter_parameters={'pdc0': pdc0_watt},
        temperature_model_parameters=pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass']
    )

    # ModelChain aufbauen und starten
    mc = ModelChain(system, site, aoi_model='physical', spectral_model='no_loss')
    mc.run_model(data)


    return mc.results.ac

