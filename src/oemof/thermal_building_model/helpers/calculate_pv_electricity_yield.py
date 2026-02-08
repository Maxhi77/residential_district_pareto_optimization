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
def simulate_pv_yield(pv_nominal_power_in_watt, epw_path, tilt=35, azimuth=180, both_side_average=True):
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
    if not both_side_average:
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
    else:
        # Standort aus EPW
        site = Location(meta["latitude"], meta["longitude"], tz=meta["TZ"])

        # Zwei Dachseiten: azimuth und azimuth+180
        az1 = azimuth % 360
        az2 = (azimuth + 180) % 360

        def _run_one_side(surface_azimuth):
            system = PVSystem(
                surface_tilt=tilt,
                surface_azimuth=surface_azimuth,
                module_parameters={"pdc0": pv_nominal_power_in_watt, "gamma_pdc": -0.004},
                inverter_parameters={"pdc0": pv_nominal_power_in_watt},
                temperature_model_parameters=pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"],
            )
            mc = ModelChain(system, site, aoi_model="physical", spectral_model="no_loss")
            mc.run_model(data)

            # mc.results.ac ist typisch das, was du willst (nach Inverter)
            # Falls ac nicht verfügbar: auf dc ausweichen
            if mc.results.ac is not None:
                return mc.results.ac
            return mc.results.dc

        p1 = _run_one_side(az1)
        p2 = _run_one_side(az2)

        # Mittelwert (weil gleiche Dachflächen / gleiche installierte Leistung je Seite angenommen)
        p_avg = 0.5 * (p1 + p2)#
        return p_avg



