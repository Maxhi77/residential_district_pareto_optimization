from __future__ import annotations

import copy

from oemof.thermal_building_model.helpers.calculate_pv_electricity_yield import simulate_pv_yield
from oemof.thermal_building_model.helpers.lpg_demand_preprocessing import (
    EV_SUFFIX_HALF,
    EV_SUFFIX_NO,
    EV_SUFFIX_TOTAL,
    EV_SUFFIX_YES,
    EV_SUFFIX_YES2,
    build_even_ev_assignment,
    build_household_presence_profile,
    build_mixed_electricity_profile_per_household,
    calculate_min_max_nominal_air,
    extract_has_ev_list,
)
from oemof.thermal_building_model.input.economics.investment_components import (
    pv_system_config as decentralized_pv_system_config,
)
from oemof.thermal_building_model.input.economics.investment_components_heat_grid import (
    pv_system_config as centralized_pv_system_config,
)
from oemof.thermal_building_model.oemof_facades.infrastructure.demands import (
    ElectricityDemand,
    WarmWater,
)
from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import (
    ThermalBuilding,
)
from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import (
    PVSystem,
)


YEAR_MAP = {
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


def _normalize_scenario_name(name) -> str:
    if name is None:
        return "ref"
    return str(name).strip().lower()


def _load_building_demands(building_row, directory_path, ev):
    building_id = building_row["building_id"]
    number_of_households = int(building_row["number_of_apartments"])

    ev_mode = str(ev).strip()
    ev_suffix_with_ev = EV_SUFFIX_YES2 if ev_mode == EV_SUFFIX_YES2 else EV_SUFFIX_YES
    require_ev_household_titles = ev_mode in {EV_SUFFIX_YES, EV_SUFFIX_YES2}
    has_ev_list = extract_has_ev_list(
        building_row=building_row,
        expected_households=number_of_households,
        building_id=building_id,
        require_field=require_ev_household_titles,
    )
    if ev_mode == EV_SUFFIX_NO:
        has_ev_list = [0] * number_of_households
    elif ev_mode == EV_SUFFIX_TOTAL:
        has_ev_list = [1] * number_of_households
    elif ev_mode == EV_SUFFIX_HALF:
        ev_households = int(round(number_of_households / 2.0))
        has_ev_list = build_even_ev_assignment(number_of_households, ev_households)

    mixed_electricity, demand_no_ev, _ = build_mixed_electricity_profile_per_household(
        building_id=building_id,
        directory_path=directory_path,
        has_ev_list=has_ev_list,
        ev_suffix_with_ev=ev_suffix_with_ev,
        strict_car_column_for_ev_households=True,
        force_load_with_ev_file=require_ev_household_titles,
    )
    demand_electricity = (mixed_electricity * 1000).tolist()
    warm_water_cols = [col for col in demand_no_ev.columns if str(col).startswith("Warm Water_")]
    if not warm_water_cols:
        raise ValueError(
            f"building '{building_id}': no warm water columns found in no_EV demand file."
        )
    demand_warm_water = demand_no_ev[warm_water_cols].sum(axis=1).tolist()
    return demand_electricity, demand_warm_water, demand_no_ev


def _temperature_setpoints_for_scenario(
    scenario_name,
    demand_no_ev,
    number_of_occupants,
    number_of_households,
):
    scenario_name = _normalize_scenario_name(scenario_name)
    if scenario_name not in {"ntr16", "ems22", "ems24"}:
        return None, None

    if scenario_name == "ntr16":
        temp_mode = "ntr"
        reduced_temp = 16.0
        normal_temp = 19.0
    elif scenario_name == "ems22":
        temp_mode = "ems"
        reduced_temp = 16.0
        normal_temp = 22.0
    else:
        temp_mode = "ems"
        reduced_temp = 16.0
        normal_temp = 24.0

    presence_hh1 = build_household_presence_profile(demand_no_ev, household_index=1)
    estimated_hh1_people = (
        presence_hh1["outside"] + presence_hh1["sleeping"] + presence_hh1["awake"]
    )
    fallback_people = max(1, int(round(float(number_of_occupants) / max(1, number_of_households))))
    if len(estimated_hh1_people) > 0:
        number_of_habitant_hh1 = int(round(float(estimated_hh1_people.max())))
        number_of_habitant_hh1 = max(1, number_of_habitant_hh1)
    else:
        number_of_habitant_hh1 = fallback_people

    t_set_heating = calculate_min_max_nominal_air(
        presence_hh1,
        number_of_habitant=number_of_habitant_hh1,
        mode=temp_mode,
        reduced_temp=reduced_temp,
        normal_temp=normal_temp,
    )
    return t_set_heating, None


def _build_pv_systems(building_id, building, building_roof_area, tilt, azimuth, epw_path, data, pv_config):
    pv_yield_per_wp = simulate_pv_yield(
        pv_nominal_power_in_watt=1,
        tilt=tilt,
        azimuth=azimuth,
        epw_path=epw_path,
    )

    dict_pv_systems = {}
    for key, config in pv_config.items():
        pv_system_config_building = copy.deepcopy(config)
        pv = PVSystem(
            investment=True,
            name=f"pv_system_{building_id}_{key}",
            value_list=pv_yield_per_wp.tolist(),
            investment_component=pv_system_config_building,
        )
        pv.update_maximum_investment_pv_capacity_based_on_area(
            building.get_roof_area_for_pv(building_roof_area)
        )
        data[pv.name] = pv.value_list
        dict_pv_systems[key] = pv
    return dict_pv_systems


def process_cluster_decentralized(
    building_row,
    building_type,
    epw_path,
    directory_path,
    data,
    refurbish,
    number_of_time_steps,
    data_classes_comp,
    ev,
    time_index,
    price_scenario_name="ref",
):
    building_id = building_row["building_id"]
    tabula_year_class = building_row["tabula_year_class"]
    building_floor_area = building_row["net_floor_area"]
    building_roof_area = building_row["roof_surface_area"]
    number_of_occupants = building_row["number_of_residents"]
    number_of_households = int(building_row["number_of_apartments"])
    azimuth = building_row["azimuth"]
    tilt = building_row["tilt"]
    year_of_construction = YEAR_MAP.get(tabula_year_class, 2000)

    demand_electricity, demand_warm_water, demand_no_ev = _load_building_demands(
        building_row=building_row,
        directory_path=directory_path,
        ev=ev,
    )
    t_set_heating, t_set_cooling = _temperature_setpoints_for_scenario(
        price_scenario_name,
        demand_no_ev,
        number_of_occupants,
        number_of_households,
    )

    electricity_demand = ElectricityDemand(name=f"e_demand_{building_id}", value_list=demand_electricity)
    heat_demand = WarmWater(name=f"ww_demand_{building_id}", value_list=demand_warm_water, level=40)
    building = ThermalBuilding(
        name=f"building_{building_id}",
        floor_area=building_floor_area,
        number_of_occupants=number_of_occupants,
        number_of_household=number_of_households,
        country="DE",
        construction_year=year_of_construction,
        class_building="average",
        building_type=building_type,
        refurbishment_status=refurbish,
        heat_level_calculation=True,
        time_index=time_index,
        t_set_heating=t_set_heating,
        t_set_cooling=t_set_cooling,
    )

    heat_demand_worst_case_building = ThermalBuilding(
        name=f"building_{building_id}",
        floor_area=building_floor_area,
        number_of_occupants=number_of_occupants,
        number_of_household=number_of_households,
        country="DE",
        construction_year=year_of_construction,
        class_building="average",
        building_type=building_type,
        refurbishment_status="no_refurbishment",
        heat_level_calculation=True,
        time_index=time_index,
        t_set_heating=t_set_heating,
        t_set_cooling=t_set_cooling,
    )
    heat_demand_worst_case = max(heat_demand_worst_case_building.value_list) + max(heat_demand.value_list)

    dict_pv_systems = _build_pv_systems(
        building_id=building_id,
        building=building,
        building_roof_area=building_roof_area,
        tilt=tilt,
        azimuth=azimuth,
        epw_path=epw_path,
        data=data,
        pv_config=decentralized_pv_system_config,
    )

    data[electricity_demand.name] = electricity_demand.value_list
    data[heat_demand.name] = heat_demand.value_list
    data[building.name] = building.value_list

    data_classes_comp[building_id] = {
        "electricity_demand": electricity_demand,
        "pv_system": dict_pv_systems,
        "building": building,
        "heat_demand": heat_demand,
        "building_type": building_type,
    }
    return data, data_classes_comp, heat_demand_worst_case


def process_cluster_centralized(
    building,
    building_id,
    building_row,
    epw_path,
    building_type,
    directory_path,
    data,
    number_of_time_steps,
    data_classes_comp,
    ev,
    time_index,
):
    building_id = building_row["building_id"]
    tabula_year_class = building_row["tabula_year_class"]
    building_floor_area = building_row["net_floor_area"]
    building_roof_area = building_row["roof_surface_area"]
    azimuth = building_row["azimuth"]
    tilt = building_row["tilt"]
    number_of_occupants = building_row["number_of_residents"]
    number_of_households = int(building_row["number_of_apartments"])
    number_of_buildings_in_cluster = building_row["buildings_in_cluster"]
    year_of_construction = YEAR_MAP.get(tabula_year_class, 2000)

    demand_electricity, demand_warm_water, _ = _load_building_demands(
        building_row=building_row,
        directory_path=directory_path,
        ev=ev,
    )

    electricity_demand = ElectricityDemand(name=f"e_demand_{building_id}", value_list=demand_electricity)
    heat_demand = WarmWater(name=f"ww_demand_{building_id}", value_list=demand_warm_water, level=40)

    heat_demand_worst_case_building = ThermalBuilding(
        name=f"building_{building_id}",
        floor_area=building_floor_area,
        number_of_occupants=number_of_occupants,
        number_of_household=number_of_households,
        country="DE",
        construction_year=year_of_construction,
        class_building="average",
        building_type=building_type,
        refurbishment_status="no_refurbishment",
        heat_level_calculation=True,
        time_index=time_index,
    )
    heat_demand_worst_case = (
        max(heat_demand_worst_case_building.value_list) + max(heat_demand.value_list)
    ) * number_of_buildings_in_cluster

    dict_pv_systems = _build_pv_systems(
        building_id=building_id,
        building=building,
        building_roof_area=building_roof_area,
        tilt=tilt,
        azimuth=azimuth,
        epw_path=epw_path,
        data=data,
        pv_config=centralized_pv_system_config,
    )

    data[electricity_demand.name] = electricity_demand.value_list
    data[heat_demand.name] = heat_demand.value_list
    data[building.name] = building.value_list

    data_classes_comp[building_id] = {
        "electricity_demand": electricity_demand,
        "pv_system": dict_pv_systems,
        "building": building,
        "heat_demand": heat_demand,
        "building_type": building_type,
    }
    return data, data_classes_comp, heat_demand_worst_case
