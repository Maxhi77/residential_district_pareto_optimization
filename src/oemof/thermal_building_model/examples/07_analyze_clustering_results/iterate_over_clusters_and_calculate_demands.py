import copy
import os
import pickle
import re
from pathlib import Path

import pandas as pd
import geopandas as gpd
from oemof import solph

from oemof.thermal_building_model.helpers.calculate_pv_electricity_yield import simulate_pv_yield
from oemof.thermal_building_model.helpers.path_helper import get_project_root
from oemof.thermal_building_model.input.economics.investment_components import pv_system_config
from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import ThermalBuilding
from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import PVSystem


EXAMPLES_BASE_DIR = (
    Path(__file__).resolve().parents[1] / "03_advanced_investment_optimization"
)
CLUSTER_FOLDER_PATTERN = re.compile(r"^(sfh|mfh)_cluster_k\d+$")
OUTPUT_FILENAME = "demands_and_pv_potential.pkl"
EV_SUFFIX = "no_EV"
NUMBER_OF_TIME_STEPS = 8760
UEU_CASES_TO_PROCESS = [
    "processed_bds_in_DENI03403000SEC5658",
]


def _year_from_tabula(tabula_year_class):
    year_map = {
        1: 1850,
        2: 1910,
        3: 1930,
        4: 1950,
        5: 1960,
        6: 1970,
        7: 1980,
        8: 1990,
        9: 2000,
        10: 2005,
        11: 2010,
        12: 2020,
    }
    return year_map.get(int(tabula_year_class), 2000)


def _discover_cluster_roots(base_dir):
    roots = []
    for candidate in sorted(base_dir.iterdir()):
        if not candidate.is_dir():
            continue
        has_cluster_folder = False
        for child in candidate.iterdir():
            if child.is_dir() and CLUSTER_FOLDER_PATTERN.match(child.name):
                has_cluster_folder = True
                break
        has_reference_gpkg = (candidate / f"{candidate.name}.gpkg").exists()
        if has_cluster_folder or has_reference_gpkg:
            roots.append(candidate)
    return roots


def _resolve_cluster_roots_from_ueu_cases(base_dir, ueu_cases):
    cluster_roots = []
    missing = []
    for ueu in ueu_cases:
        candidate = base_dir / ueu
        if candidate.is_dir():
            cluster_roots.append(candidate)
        else:
            missing.append(ueu)
    return cluster_roots, missing


def _load_cluster_frame(cluster_folder):
    folder_name = cluster_folder.name.lower()
    if folder_name.startswith("sfh_cluster_k"):
        cluster_file = cluster_folder / "sfh_cluster.pkl"
        building_type = "SFH"
    elif folder_name.startswith("mfh_cluster_k"):
        cluster_file = cluster_folder / "mfh_cluster.pkl"
        building_type = "MFH"
    else:
        raise ValueError(f"Unsupported cluster folder: {cluster_folder}")

    if not cluster_file.exists():
        raise FileNotFoundError(f"Missing cluster file: {cluster_file}")

    with open(cluster_file, "rb") as fh:
        data = pickle.load(fh)

    if isinstance(data, pd.DataFrame):
        cluster_df = data
    else:
        cluster_df = pd.DataFrame(data)
    return cluster_df, building_type


def _calculate_profiles_for_building(building_row, building_type, demand_dir, epw_path, time_index):
    building_id = building_row["building_id"]
    demand_path = demand_dir / f"{building_id}_demand_{EV_SUFFIX}.pkl"
    if not demand_path.exists():
        fallback_demand_path = demand_dir.parent / f"{building_id}_demand_{EV_SUFFIX}.pkl"
        if fallback_demand_path.exists():
            demand_path = fallback_demand_path
    if not demand_path.exists():
        raise FileNotFoundError(f"Missing demand file: {demand_path}")

    with open(demand_path, "rb") as fh:
        demand = pickle.load(fh)

    electricity_cols = [col for col in demand.columns if str(col).startswith("Electricity")]
    warm_water_cols = [col for col in demand.columns if str(col).startswith("Warm Water_")]
    if not electricity_cols or not warm_water_cols:
        raise ValueError(
            f"Demand columns missing for building '{building_id}'. "
            f"Electricity columns: {len(electricity_cols)}, warm water columns: {len(warm_water_cols)}"
        )

    electricity_demand = (demand[electricity_cols].sum(axis=1) * 1000).tolist()
    warm_water_demand = demand[warm_water_cols].sum(axis=1).tolist()

    tabula_year_class = building_row["tabula_year_class"]
    building_floor_area = building_row["net_floor_area"]
    building_roof_area = building_row["roof_surface_area"]
    number_of_occupants = building_row["number_of_residents"]
    number_of_households = building_row["number_of_apartments"]
    azimuth = building_row["azimuth"]
    tilt = building_row["tilt"]

    building = ThermalBuilding(
        name=f"building_{building_id}",
        floor_area=building_floor_area,
        number_of_occupants=number_of_occupants,
        number_of_household=number_of_households,
        country="DE",
        construction_year=_year_from_tabula(tabula_year_class),
        class_building="average",
        building_type=building_type,
        refurbishment_status="no_refurbishment",
        heat_level_calculation=True,
        time_index=time_index,
    )
    building_heating_demand = building.value_list

    pv_yield_per_wp = simulate_pv_yield(
        pv_nominal_power_in_watt=1,
        tilt=tilt,
        azimuth=azimuth,
        epw_path=str(epw_path),
    )

    available_roof_area = building.get_roof_area_for_pv(building_roof_area)
    max_installable_capacity = 0.0
    for _, config in pv_system_config.items():
        pv_dataclass = PVSystem(
            investment=True,
            name=f"pv_system_{building_id}",
            value_list=pv_yield_per_wp.tolist(),
            investment_component=copy.deepcopy(config),
        )
        pv_dataclass.update_maximum_investment_pv_capacity_based_on_area(available_roof_area)
        max_installable_capacity = max(
            max_installable_capacity,
            float(pv_dataclass.investment_component.maximum_capacity),
        )
    pv_potential = [a * max_installable_capacity * 1000 for a in pv_dataclass.value_list]

    return {
        "electricity_demand": electricity_demand,
        "warm_water_demand": warm_water_demand,
        "building_heating_demand": building_heating_demand,
        "pv_potential": pv_potential,
        "buildings_in_cluster": building_row["buildings_in_cluster"],
    }


def _empty_output_payload():
    return {
        "electricity_demand": {},
        "warm_water_demand": {},
        "building_heating_demand": {},
        "pv_potential": {},
        "buildings_in_cluster": {},
    }


def _append_building_output(output, building_id, profiles):
    output["electricity_demand"][building_id] = profiles["electricity_demand"]
    output["warm_water_demand"][building_id] = profiles["warm_water_demand"]
    output["building_heating_demand"][building_id] = profiles["building_heating_demand"]
    output["pv_potential"][building_id] = profiles["pv_potential"]
    output["buildings_in_cluster"][building_id] = profiles["buildings_in_cluster"]


def _process_cluster_frame(cluster_df, building_type, output_dir, demand_dir, epw_path, time_index):
    if "buildings_in_cluster" not in cluster_df.columns:
        cluster_df = cluster_df.copy()
        cluster_df["buildings_in_cluster"] = 1

    output = _empty_output_payload()
    failed_buildings = []
    for _, building_row in cluster_df.iterrows():
        building_id = building_row["building_id"]
        try:
            profiles = _calculate_profiles_for_building(
                building_row=building_row,
                building_type=building_type,
                demand_dir=demand_dir,
                epw_path=epw_path,
                time_index=time_index,
            )
        except Exception as exc:
            failed_buildings.append((building_id, str(exc)))
            continue
        _append_building_output(output, building_id, profiles)

    output_path = output_dir / OUTPUT_FILENAME
    with open(output_path, "wb") as fh:
        pickle.dump(output, fh)

    print(f"saved: {output_path}")
    if failed_buildings:
        print(f"failed buildings in {output_dir.name}: {len(failed_buildings)}")
        for building_id, message in failed_buildings[:10]:
            print(f"  - {building_id}: {message}")


def _process_cluster_folder(cluster_folder, demand_dir, epw_path, time_index):
    cluster_df, building_type = _load_cluster_frame(cluster_folder)
    _process_cluster_frame(
        cluster_df=cluster_df,
        building_type=building_type,
        output_dir=cluster_folder,
        demand_dir=demand_dir,
        epw_path=epw_path,
        time_index=time_index,
    )


def _process_reference_cluster(cluster_root, epw_path, time_index):
    gpkg_ueu = cluster_root / f"{cluster_root.name}.gpkg"
    if not gpkg_ueu.exists():
        return

    gdf_ueu = gpd.read_file(gpkg_ueu)
    if "tabula_building_type" not in gdf_ueu.columns:
        print(f"skip reference for {cluster_root.name}: missing 'tabula_building_type' in {gpkg_ueu.name}")
        return

    reference_demand_dir = cluster_root / "reference"
    if not reference_demand_dir.exists():
        reference_demand_dir = cluster_root

    for building_type in ("SFH", "MFH"):
        cluster_df = gdf_ueu.loc[gdf_ueu["tabula_building_type"] == building_type].copy()
        if cluster_df.empty:
            continue
        cluster_df["buildings_in_cluster"] = 1
        reference_output_dir = cluster_root / f"{building_type.lower()}_reference"
        reference_output_dir.mkdir(parents=True, exist_ok=True)
        _process_cluster_frame(
            cluster_df=cluster_df,
            building_type=building_type,
            output_dir=reference_output_dir,
            demand_dir=reference_demand_dir,
            epw_path=epw_path,
            time_index=time_index,
        )


def main():
    main_path = Path(get_project_root())
    epw_path = (
        main_path
        / "thermal_building_model"
        / "input"
        / "weather_files"
        / "03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv"
    )
    if not epw_path.exists():
        raise FileNotFoundError(f"Weather file not found: {epw_path}")

    if not UEU_CASES_TO_PROCESS:
        raise ValueError("UEU_CASES_TO_PROCESS is empty.")

    cluster_roots, missing_ueus = _resolve_cluster_roots_from_ueu_cases(
        EXAMPLES_BASE_DIR, UEU_CASES_TO_PROCESS
    )
    if missing_ueus:
        print(f"Skipped missing UEU folders: {missing_ueus}")
    if not cluster_roots:
        print("No valid UEU folders selected.")
        return

    time_index = solph.create_time_index(2025, number=NUMBER_OF_TIME_STEPS - 1)
    for cluster_root in cluster_roots:
        print(f"processing cluster root: {cluster_root.name}")
        for child in sorted(cluster_root.iterdir()):
            if not child.is_dir():
                continue
            if not CLUSTER_FOLDER_PATTERN.match(child.name):
                continue
            _process_cluster_folder(
                cluster_folder=child,
                demand_dir=cluster_root,
                epw_path=epw_path,
                time_index=time_index,
            )
        _process_reference_cluster(
            cluster_root=cluster_root,
            epw_path=epw_path,
            time_index=time_index,
        )


if __name__ == "__main__":
    main()
