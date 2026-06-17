import copy
import pickle
import re
import sqlite3
from pathlib import Path

import pandas as pd

try:
    import geopandas as gpd
except ModuleNotFoundError:
    gpd = None

try:
    from oemof import solph
    from oemof.thermal_building_model.helpers.calculate_pv_electricity_yield import simulate_pv_yield
    from oemof.thermal_building_model.helpers.path_helper import get_project_root
    from oemof.thermal_building_model.input.economics.investment_components import pv_system_config
    from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import ThermalBuilding
    from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import PVSystem
except ModuleNotFoundError:
    solph = None
    simulate_pv_yield = None
    get_project_root = None
    pv_system_config = None
    ThermalBuilding = None
    PVSystem = None


EXAMPLES_BASE_DIR = Path(__file__).resolve().parents[1] / "03_applied_energy_optimization"
OUTPUT_DIR = Path(__file__).resolve().parent
EV_SUFFIX_NO = "no_EV"
EV_SUFFIX_YES = "yes_EV"
NUMBER_OF_TIME_STEPS = 8760
REFERENCE_PROFILES_FILENAME = "demands_and_pv_potential.pkl"
WARM_WATER_REFERENCE_TEMP_C = 35.0
WARM_WATER_COLD_TEMP_C = 10.0
WARM_WATER_DEMAND_TEMP_C = 50.0
WATER_HEAT_CAPACITY_KJ_PER_KG_K = 4.18
PHYSICAL_BASE_FACTOR = 1000.0
UEU_CASES_TO_PROCESS = [
    "processed_bds_in_DENI03403000SEC5658",
    "processed_bds_in_DENI03403000SEC4580",
    "processed_bds_in_DENI03403000SEC5101"
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


def _as_float(value, default=0.0):
    if pd.isna(value):
        return float(default)
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_per_100(total, area):
    if total is None or area <= 0:
        return None
    return total / area * 100.0


def _safe_per_area(total, area):
    if total is None or area <= 0:
        return None
    return total / area


def _mean_per_area_x100(building_rows: list[dict], per_area_key: str) -> float | None:
    if not building_rows:
        return None
    values = pd.to_numeric(
        pd.Series([row.get(per_area_key) for row in building_rows]),
        errors="coerce",
    ).dropna()
    if values.empty:
        return None
    return float(values.mean() * 100.0)


def _convert_warm_water_volume_to_heat_profile(
    warm_water_volume_profile: pd.Series,
    demand_temperature: float = WARM_WATER_DEMAND_TEMP_C,
) -> pd.Series:
    """Convert warm water profile from liters/hour to thermal demand in kW."""
    if demand_temperature <= WARM_WATER_COLD_TEMP_C:
        raise ValueError(
            f"demand_temperature must be > {WARM_WATER_COLD_TEMP_C} C, got {demand_temperature}"
        )
    fraction_of_hot_water = (
        (WARM_WATER_REFERENCE_TEMP_C - WARM_WATER_COLD_TEMP_C)
        / (demand_temperature - WARM_WATER_COLD_TEMP_C)
    )
    thermal_conversion_factor = (
        (demand_temperature - WARM_WATER_COLD_TEMP_C)
        * WATER_HEAT_CAPACITY_KJ_PER_KG_K
        * (1000 / 3600.0)
    ) / PHYSICAL_BASE_FACTOR
    return warm_water_volume_profile * thermal_conversion_factor * fraction_of_hot_water


def _sum_numeric(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce")
    return float(numeric.fillna(0.0).sum())


def _count_rows(df: pd.DataFrame) -> int:
    return int(len(df))


def _structural_stats(df: pd.DataFrame) -> dict:
    required_columns = {"net_floor_area", "number_of_apartments", "number_of_residents"}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(
            f"Missing required columns for structural stats: {sorted(missing_columns)}"
        )
    return {
        "buildings_count": _count_rows(df),
        "net_floor_area_sum": _sum_numeric(df["net_floor_area"]),
        "households_sum": _sum_numeric(df["number_of_apartments"]),
        "residents_sum": _sum_numeric(df["number_of_residents"]),
    }


def _get_structural_stats_by_type(gdf_ueu: pd.DataFrame) -> dict:
    if "tabula_building_type" not in gdf_ueu.columns:
        raise ValueError("Missing 'tabula_building_type' column in gpkg.")

    gdf = gdf_ueu.copy()
    gdf["tabula_building_type"] = gdf["tabula_building_type"].astype(str).str.upper()
    sfh_df = gdf.loc[gdf["tabula_building_type"] == "SFH"].copy()
    mfh_df = gdf.loc[gdf["tabula_building_type"] == "MFH"].copy()
    combined_df = pd.concat([sfh_df, mfh_df], ignore_index=True)

    return {
        "sfh": _structural_stats(sfh_df),
        "mfh": _structural_stats(mfh_df),
        "total": _structural_stats(combined_df),
    }


def _resolve_construction_period_label(building_row: pd.Series) -> str:
    construction_period = building_row.get("construction_period")
    if not pd.isna(construction_period):
        label = str(construction_period).strip()
        if label:
            return label

    tabula_year_class = building_row.get("tabula_year_class")
    if not pd.isna(tabula_year_class):
        try:
            tabula_class_int = int(float(tabula_year_class))
            return f"tabula_class_{tabula_class_int:02d}_year_{_year_from_tabula(tabula_class_int)}"
        except Exception:
            return f"tabula_class_{tabula_year_class}"
    return "unknown"


def _sanitize_metric_token(raw_label: str) -> str:
    token = re.sub(r"[^0-9a-zA-Z]+", "_", str(raw_label).strip().lower())
    token = token.strip("_")
    return token if token else "unknown"


def _construction_period_distribution_stats(gdf_ueu: pd.DataFrame) -> dict:
    if "tabula_building_type" not in gdf_ueu.columns:
        raise ValueError("Missing 'tabula_building_type' column in gpkg.")

    gdf = gdf_ueu.copy()
    gdf["tabula_building_type"] = gdf["tabula_building_type"].astype(str).str.upper()
    gdf["construction_period_label"] = gdf.apply(_resolve_construction_period_label, axis=1)
    counts_total = gdf["construction_period_label"].value_counts().sort_index()
    counts_sfh = gdf.loc[
        gdf["tabula_building_type"] == "SFH", "construction_period_label"
    ].value_counts().sort_index()
    counts_mfh = gdf.loc[
        gdf["tabula_building_type"] == "MFH", "construction_period_label"
    ].value_counts().sort_index()
    periods = sorted(set(counts_total.index) | set(counts_sfh.index) | set(counts_mfh.index))
    stats = {
        "construction_periods_unique_total": int(len(counts_total)),
        "construction_periods_unique_sfh": int(len(counts_sfh)),
        "construction_periods_unique_mfh": int(len(counts_mfh)),
    }
    total_buildings = len(gdf)
    total_sfh_buildings = int((gdf["tabula_building_type"] == "SFH").sum())
    total_mfh_buildings = int((gdf["tabula_building_type"] == "MFH").sum())

    used_tokens: set[str] = set()
    for period in periods:
        base_token = _sanitize_metric_token(period)
        token = base_token
        suffix = 2
        while token in used_tokens:
            token = f"{base_token}_{suffix}"
            suffix += 1
        used_tokens.add(token)

        stats[f"construction_period_{token}_label"] = period
        period_count = int(counts_total.get(period, 0))
        period_count_sfh = int(counts_sfh.get(period, 0))
        period_count_mfh = int(counts_mfh.get(period, 0))
        stats[f"construction_period_{token}_count_total"] = period_count
        stats[f"construction_period_{token}_count_sfh"] = period_count_sfh
        stats[f"construction_period_{token}_count_mfh"] = period_count_mfh
        stats[f"construction_period_{token}_share_total_pct"] = (
            period_count / total_buildings * 100.0 if total_buildings else None
        )
        stats[f"construction_period_{token}_share_sfh_pct"] = (
            period_count_sfh / total_sfh_buildings * 100.0 if total_sfh_buildings else None
        )
        stats[f"construction_period_{token}_share_mfh_pct"] = (
            period_count_mfh / total_mfh_buildings * 100.0 if total_mfh_buildings else None
        )

    return stats


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


def _load_reference_gdf(cluster_root):
    gpkg_ueu = cluster_root / f"{cluster_root.name}.gpkg"
    if not gpkg_ueu.exists():
        raise FileNotFoundError(f"Reference gpkg not found: {gpkg_ueu}")
    if gpd is not None:
        return gpd.read_file(gpkg_ueu)

    with sqlite3.connect(gpkg_ueu) as conn:
        layers_df = pd.read_sql_query(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features' ORDER BY table_name",
            conn,
        )
        if layers_df.empty:
            raise ValueError(f"No feature layers found in {gpkg_ueu}")
        layer_names = layers_df["table_name"].astype(str).tolist()
        preferred_layer = cluster_root.name if cluster_root.name in layer_names else layer_names[0]
        return pd.read_sql_query(f'SELECT * FROM "{preferred_layer}"', conn)


def _load_demand_for_building(building_id, cluster_root, ev_suffix):
    reference_dir = cluster_root / "reference"
    demand_path = reference_dir / f"{building_id}_demand_{ev_suffix}.pkl"
    if not demand_path.exists():
        demand_path = cluster_root / f"{building_id}_demand_{ev_suffix}.pkl"
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

    electricity_profile = demand[electricity_cols].sum(axis=1)
    warm_water_volume_profile = demand[warm_water_cols].sum(axis=1)
    warm_water_profile = _convert_warm_water_volume_to_heat_profile(
        warm_water_volume_profile
    )
    electricity_total = float(electricity_profile.sum())
    warm_water_total = float(warm_water_profile.sum())
    electricity_peak = float(electricity_profile.max())
    warm_water_peak = float(warm_water_profile.max())
    return electricity_total, warm_water_total, electricity_peak, warm_water_peak


def _build_thermal_building(building_row, building_type, refurbishment_status, time_index):
    building_id = building_row["building_id"]
    return ThermalBuilding(
        name=f"building_{building_id}_{refurbishment_status}",
        floor_area=_as_float(building_row["net_floor_area"]),
        number_of_occupants=int(_as_float(building_row["number_of_residents"], default=1)),
        number_of_household=int(_as_float(building_row["number_of_apartments"], default=1)),
        country="DE",
        construction_year=_year_from_tabula(building_row["tabula_year_class"]),
        class_building="average",
        building_type=building_type,
        refurbishment_status=refurbishment_status,
        heat_level_calculation=True,
        time_index=time_index,
    )


def _calculate_heating_total(building_row, building_type, refurbishment_status, time_index):
    building = _build_thermal_building(
        building_row=building_row,
        building_type=building_type,
        refurbishment_status=refurbishment_status,
        time_index=time_index,
    )
    return float(sum(building.value_list)), building


def _calculate_pv_potential_total(building_row, epw_path, available_roof_area):
    pv_yield_per_wp = simulate_pv_yield(
        pv_nominal_power_in_watt=1,
        tilt=_as_float(building_row["tilt"]),
        azimuth=_as_float(building_row["azimuth"]),
        epw_path=str(epw_path),
    )

    max_installable_capacity = 0.0
    for _, config in pv_system_config.items():
        pv_dataclass = PVSystem(
            investment=True,
            name=f"pv_system_{building_row['building_id']}",
            value_list=pv_yield_per_wp.tolist(),
            investment_component=copy.deepcopy(config),
        )
        pv_dataclass.update_maximum_investment_pv_capacity_based_on_area(available_roof_area)
        max_installable_capacity = max(
            max_installable_capacity,
            float(pv_dataclass.investment_component.maximum_capacity),
        )

    return float(sum(value * max_installable_capacity for value in pv_yield_per_wp))


def _sum_and_peak(values) -> tuple[float, float]:
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").fillna(0.0)
    if numeric.empty:
        return 0.0, 0.0
    return float(numeric.sum()), float(numeric.max())


def _load_precomputed_reference_profiles(cluster_root: Path) -> dict[str, dict]:
    profiles: dict[str, dict] = {}
    # Start with generic reference and let type-specific payloads overwrite if present.
    for ref_dir in ("reference", "sfh_reference", "mfh_reference"):
        path = cluster_root / ref_dir / REFERENCE_PROFILES_FILENAME
        if not path.exists():
            continue
        try:
            with open(path, "rb") as fh:
                payload = pickle.load(fh)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        heating_data_no_ref = (
            payload.get("building_heating_demand_no_refurbishment")
            or payload.get("building_heating_demand")
            or {}
        )
        heating_data_advanced = (
            payload.get("building_heating_demand_advanced_refurbishment")
            or {}
        )
        pv_data = payload.get("pv_potential", {}) or {}
        weights = payload.get("buildings_in_cluster", {}) or {}

        building_ids = set(heating_data_no_ref) | set(heating_data_advanced) | set(pv_data)
        for building_id in building_ids:
            bid = str(building_id)
            weight = _as_float(weights.get(building_id, weights.get(bid, 1.0)), default=1.0)
            profiles[bid] = {
                "heating_series_no_ref": heating_data_no_ref.get(building_id, heating_data_no_ref.get(bid)),
                "heating_series_advanced": heating_data_advanced.get(
                    building_id, heating_data_advanced.get(bid)
                ),
                "pv_series": pv_data.get(building_id, pv_data.get(bid)),
                "weight": weight if weight > 0 else 1.0,
            }
    return profiles


def _init_energy_accumulator() -> dict:
    return {
        "total_electricity_no_ev": 0.0,
        "total_electricity_yes_ev": 0.0,
        "total_dhw": 0.0,
        "total_heating_no_ref": 0.0,
        "total_heating_advanced": 0.0,
        "total_pv_potential": 0.0,
        "peak_electricity_no_ev_sum": 0.0,
        "peak_electricity_yes_ev_sum": 0.0,
        "peak_dhw_sum": 0.0,
        "peak_heating_no_ref_sum": 0.0,
        "peak_heating_advanced_sum": 0.0,
        "peak_pv_sum": 0.0,
        "peak_counter_demand": 0,
        "peak_counter_heating": 0,
    }


def _summarize_ueu(cluster_root, epw_path, time_index):
    gdf_ueu = _load_reference_gdf(cluster_root)
    if "tabula_building_type" not in gdf_ueu.columns:
        raise ValueError(
            f"Missing 'tabula_building_type' in reference gpkg for {cluster_root.name}."
        )
    structural_stats = _get_structural_stats_by_type(gdf_ueu)
    construction_period_stats = _construction_period_distribution_stats(gdf_ueu)
    total_floor_area_structural = structural_stats["total"]["net_floor_area_sum"]
    total_residents_structural = structural_stats["total"]["residents_sum"]
    number_of_sfh_structural = structural_stats["sfh"]["buildings_count"]
    number_of_mfh_structural = structural_stats["mfh"]["buildings_count"]
    precomputed_profiles = _load_precomputed_reference_profiles(cluster_root)

    heating_metrics_available = (
        ThermalBuilding is not None and time_index is not None
    )
    pv_metrics_available = all(
        dep is not None
        for dep in (simulate_pv_yield, pv_system_config, PVSystem, ThermalBuilding)
    ) and epw_path is not None and time_index is not None

    total_floor_area = 0.0
    total_residents = 0.0
    energy_acc = {
        "sfh": _init_energy_accumulator(),
        "mfh": _init_energy_accumulator(),
    }
    number_of_sfh = 0
    number_of_mfh = 0
    ev_yes_fallback_buildings = 0
    skipped_buildings = []
    partial_metric_warnings = []
    building_kpi_rows = []

    for _, building_row in gdf_ueu.iterrows():
        building_type = str(building_row.get("tabula_building_type", "")).upper()
        if building_type not in {"SFH", "MFH"}:
            skipped_buildings.append((building_row.get("building_id"), "invalid building type"))
            continue

        building_id = building_row["building_id"]
        try:
            (
                electricity_total_no_ev,
                warm_water_total,
                electricity_peak_no_ev,
                dhw_peak,
            ) = _load_demand_for_building(
                building_id,
                cluster_root,
                EV_SUFFIX_NO,
            )
            try:
                (
                    electricity_total_yes_ev,
                    _,
                    electricity_peak_yes_ev,
                    _,
                ) = _load_demand_for_building(
                    building_id,
                    cluster_root,
                    EV_SUFFIX_YES,
                )
            except Exception:
                electricity_total_yes_ev = electricity_total_no_ev
                electricity_peak_yes_ev = electricity_peak_no_ev
                ev_yes_fallback_buildings += 1
        except Exception as exc:
            skipped_buildings.append((building_id, str(exc)))
            continue

        heating_no_ref = None
        heating_advanced = None
        heating_peak_no_ref = None
        heating_peak_advanced = None
        pv_potential_total = None
        pv_peak = None
        no_ref_building = None
        precomputed_profile = precomputed_profiles.get(str(building_id))
        if precomputed_profile is not None:
            heating_series_no_ref = precomputed_profile.get("heating_series_no_ref")
            if heating_series_no_ref is not None:
                heating_sum, heating_peak_raw = _sum_and_peak(heating_series_no_ref)
                weight = _as_float(precomputed_profile.get("weight", 1.0), default=1.0)
                heating_no_ref = heating_sum * weight
                heating_peak_no_ref = heating_peak_raw * weight

            heating_series_advanced = precomputed_profile.get("heating_series_advanced")
            if heating_series_advanced is not None:
                heating_advanced_sum, heating_advanced_peak_raw = _sum_and_peak(
                    heating_series_advanced
                )
                weight = _as_float(precomputed_profile.get("weight", 1.0), default=1.0)
                heating_advanced = heating_advanced_sum * weight
                heating_peak_advanced = heating_advanced_peak_raw * weight

            pv_series = precomputed_profile.get("pv_series")
            if pv_series is not None:
                pv_sum_raw, pv_peak_raw = _sum_and_peak(pv_series)
                weight = _as_float(precomputed_profile.get("weight", 1.0), default=1.0)
                pv_potential_total = pv_sum_raw * weight
                pv_peak = pv_peak_raw * weight

        needs_no_ref_heating = heating_no_ref is None or heating_peak_no_ref is None
        needs_advanced_heating = heating_advanced is None or heating_peak_advanced is None
        if needs_no_ref_heating and not heating_metrics_available:
            skipped_buildings.append(
                (
                    building_id,
                    "Missing heating profile and ThermalBuilding/time_index unavailable.",
                )
            )
            continue
        if heating_metrics_available and (needs_no_ref_heating or needs_advanced_heating):
            try:
                heating_no_ref_calculated, no_ref_building = _calculate_heating_total(
                    building_row=building_row,
                    building_type=building_type,
                    refurbishment_status="no_refurbishment",
                    time_index=time_index,
                )
                heating_advanced_calculated, advanced_building = _calculate_heating_total(
                    building_row=building_row,
                    building_type=building_type,
                    refurbishment_status="advanced_refurbishment",
                    time_index=time_index,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to calculate heating metrics (including advanced_refurbishment) "
                    f"for building '{building_id}' in UEU '{cluster_root.name}': {exc}"
                ) from exc

            if needs_no_ref_heating:
                heating_no_ref = heating_no_ref_calculated
                heating_peak_no_ref = float(max(no_ref_building.value_list))
            if needs_advanced_heating:
                heating_advanced = heating_advanced_calculated
                heating_peak_advanced = float(max(advanced_building.value_list))

        if pv_potential_total is None and pv_metrics_available:
            try:
                if no_ref_building is None:
                    no_ref_building = _build_thermal_building(
                        building_row=building_row,
                        building_type=building_type,
                        refurbishment_status="no_refurbishment",
                        time_index=time_index,
                    )
                available_roof_area = no_ref_building.get_roof_area_for_pv(
                    _as_float(building_row["roof_surface_area"])
                )
                pv_potential_total = _calculate_pv_potential_total(
                    building_row=building_row,
                    epw_path=epw_path,
                    available_roof_area=available_roof_area,
                )
                pv_peak = None
            except Exception as exc:
                partial_metric_warnings.append((building_id, f"pv skipped: {exc}"))

        group_key = "sfh" if building_type == "SFH" else "mfh"
        acc = energy_acc[group_key]
        building_floor_area = _as_float(building_row["net_floor_area"])
        construction_period_label = _resolve_construction_period_label(building_row)

        building_kpi_rows.append(
            {
                "ueu_case": cluster_root.name,
                "building_id": building_id,
                "tabula_building_type": building_type,
                "construction_period": construction_period_label,
                "net_floor_area": building_floor_area,
                "number_of_residents": _as_float(building_row.get("number_of_residents")),
                "number_of_apartments": _as_float(building_row.get("number_of_apartments")),
                "electricity_demand_abs_no_ev": electricity_total_no_ev,
                "electricity_demand_abs_yes_ev": electricity_total_yes_ev,
                "dhw_heat_demand_abs": warm_water_total,
                "heating_demand_abs_no_refurbishment": heating_no_ref,
                "heating_demand_abs_advanced_refurbishment": heating_advanced,
                "pv_potential_per_area_kwh_m2a": _safe_per_area(
                    pv_potential_total,
                    building_floor_area,
                ),
                "electricity_demand_per_area_no_ev_kwh_m2a": _safe_per_area(
                    electricity_total_no_ev,
                    building_floor_area,
                ),
                "electricity_demand_per_area_yes_ev_kwh_m2a": _safe_per_area(
                    electricity_total_yes_ev,
                    building_floor_area,
                ),
                "dhw_heat_demand_per_area_kwh_m2a": _safe_per_area(
                    warm_water_total,
                    building_floor_area,
                ),
                "heating_demand_per_area_no_refurbishment_kwh_m2a": _safe_per_area(
                    heating_no_ref,
                    building_floor_area,
                ),
                "heating_demand_per_area_advanced_refurbishment_kwh_m2a": _safe_per_area(
                    heating_advanced,
                    building_floor_area,
                ),
                "yearly_heating_demand_per_area_no_refurbishment_kwh_m2a": _safe_per_area(
                    heating_no_ref,
                    building_floor_area,
                ),
                "yearly_heating_demand_per_area_advanced_refurbishment_kwh_m2a": _safe_per_area(
                    heating_advanced,
                    building_floor_area,
                ),
                "pv_potential_abs": pv_potential_total,
                "peak_electricity_abs_no_ev": electricity_peak_no_ev,
                "peak_electricity_abs_yes_ev": electricity_peak_yes_ev,
                "peak_dhw_abs": dhw_peak,
                "peak_heating_abs_no_refurbishment": heating_peak_no_ref,
                "peak_heating_abs_advanced_refurbishment": heating_peak_advanced,
                "peak_pv_potential_abs": pv_peak,
                "peak_electricity_per_area_no_ev_kw_m2": _safe_per_area(
                    electricity_peak_no_ev,
                    building_floor_area,
                ),
                "peak_electricity_per_area_yes_ev_kw_m2": _safe_per_area(
                    electricity_peak_yes_ev,
                    building_floor_area,
                ),
                "peak_dhw_per_area_kw_m2": _safe_per_area(
                    dhw_peak,
                    building_floor_area,
                ),
                "peak_heating_per_area_no_refurbishment_kw_m2": _safe_per_area(
                    heating_peak_no_ref,
                    building_floor_area,
                ),
                "peak_heating_per_area_advanced_refurbishment_kw_m2": _safe_per_area(
                    heating_peak_advanced,
                    building_floor_area,
                ),
                "peak_pv_potential_per_area_kw_m2": _safe_per_area(
                    pv_peak,
                    building_floor_area,
                ),
            }
        )

        total_floor_area += building_floor_area
        total_residents += _as_float(building_row["number_of_residents"])
        acc["total_electricity_no_ev"] += electricity_total_no_ev
        acc["total_electricity_yes_ev"] += electricity_total_yes_ev
        acc["total_dhw"] += warm_water_total
        if heating_no_ref is not None:
            acc["total_heating_no_ref"] += heating_no_ref
        if heating_advanced is not None:
            acc["total_heating_advanced"] += heating_advanced
        if pv_potential_total is not None:
            acc["total_pv_potential"] += pv_potential_total

        acc["peak_electricity_no_ev_sum"] += electricity_peak_no_ev
        acc["peak_electricity_yes_ev_sum"] += electricity_peak_yes_ev
        acc["peak_dhw_sum"] += dhw_peak
        acc["peak_counter_demand"] += 1

        if heating_peak_no_ref is not None:
            acc["peak_heating_no_ref_sum"] += heating_peak_no_ref
            acc["peak_counter_heating"] += 1
        if heating_peak_advanced is not None:
            acc["peak_heating_advanced_sum"] += heating_peak_advanced
        if pv_peak is not None:
            acc["peak_pv_sum"] += pv_peak

        if building_type == "SFH":
            number_of_sfh += 1
        elif building_type == "MFH":
            number_of_mfh += 1

    total_electricity_demand_no_ev = (
        energy_acc["sfh"]["total_electricity_no_ev"] + energy_acc["mfh"]["total_electricity_no_ev"]
    )
    total_electricity_demand_yes_ev = (
        energy_acc["sfh"]["total_electricity_yes_ev"] + energy_acc["mfh"]["total_electricity_yes_ev"]
    )
    total_warm_water_demand = energy_acc["sfh"]["total_dhw"] + energy_acc["mfh"]["total_dhw"]

    total_building_heat_no_ref_raw = (
        energy_acc["sfh"]["total_heating_no_ref"] + energy_acc["mfh"]["total_heating_no_ref"]
    )
    total_building_heat_advanced_raw = (
        energy_acc["sfh"]["total_heating_advanced"] + energy_acc["mfh"]["total_heating_advanced"]
    )
    total_pv_potential_raw = (
        energy_acc["sfh"]["total_pv_potential"] + energy_acc["mfh"]["total_pv_potential"]
    )

    total_building_heat_no_ref = (
        total_building_heat_no_ref_raw
        if total_building_heat_no_ref_raw > 0
        else None
    )
    total_building_heat_advanced = (
        total_building_heat_advanced_raw
        if total_building_heat_advanced_raw > 0
        else None
    )
    total_pv_potential = total_pv_potential_raw if total_pv_potential_raw > 0 else None

    sum_electricity_peak_no_ev = (
        energy_acc["sfh"]["peak_electricity_no_ev_sum"] + energy_acc["mfh"]["peak_electricity_no_ev_sum"]
    )
    sum_electricity_peak_yes_ev = (
        energy_acc["sfh"]["peak_electricity_yes_ev_sum"] + energy_acc["mfh"]["peak_electricity_yes_ev_sum"]
    )
    sum_dhw_peak = energy_acc["sfh"]["peak_dhw_sum"] + energy_acc["mfh"]["peak_dhw_sum"]
    sum_heating_peak_no_ref = (
        energy_acc["sfh"]["peak_heating_no_ref_sum"] + energy_acc["mfh"]["peak_heating_no_ref_sum"]
    )
    sum_heating_peak_advanced = (
        energy_acc["sfh"]["peak_heating_advanced_sum"] + energy_acc["mfh"]["peak_heating_advanced_sum"]
    )
    sum_pv_peak = energy_acc["sfh"]["peak_pv_sum"] + energy_acc["mfh"]["peak_pv_sum"]
    peak_counter = energy_acc["sfh"]["peak_counter_demand"] + energy_acc["mfh"]["peak_counter_demand"]
    peak_counter_heating = (
        energy_acc["sfh"]["peak_counter_heating"] + energy_acc["mfh"]["peak_counter_heating"]
    )

    avg_electricity_peak_no_ev = sum_electricity_peak_no_ev / peak_counter if peak_counter else None
    avg_electricity_peak_yes_ev = sum_electricity_peak_yes_ev / peak_counter if peak_counter else None
    avg_dhw_peak = sum_dhw_peak / peak_counter if peak_counter else None
    avg_heating_peak_no_ref = (
        sum_heating_peak_no_ref / peak_counter_heating if peak_counter_heating else None
    )
    avg_heating_peak_advanced = (
        sum_heating_peak_advanced / peak_counter_heating if peak_counter_heating else None
    )
    x100_total_dhw_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "dhw_heat_demand_per_area_kwh_m2a"
    )
    x100_total_heating_no_ref_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "heating_demand_per_area_no_refurbishment_kwh_m2a"
    )
    x100_total_heating_advanced_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "heating_demand_per_area_advanced_refurbishment_kwh_m2a"
    )
    x100_total_electricity_no_ev_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "electricity_demand_per_area_no_ev_kwh_m2a"
    )
    x100_total_electricity_yes_ev_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "electricity_demand_per_area_yes_ev_kwh_m2a"
    )
    x100_total_pv_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "pv_potential_per_area_kwh_m2a"
    )
    x100_peak_electricity_no_ev_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "peak_electricity_per_area_no_ev_kw_m2"
    )
    x100_peak_electricity_yes_ev_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "peak_electricity_per_area_yes_ev_kw_m2"
    )
    x100_peak_dhw_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "peak_dhw_per_area_kw_m2"
    )
    x100_peak_heating_no_ref_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "peak_heating_per_area_no_refurbishment_kw_m2"
    )
    x100_peak_heating_advanced_from_buildings = _mean_per_area_x100(
        building_kpi_rows, "peak_heating_per_area_advanced_refurbishment_kw_m2"
    )

    summary = {
        "ueu_case": cluster_root.name,
        "buildings_count_total": structural_stats["total"]["buildings_count"],
        "buildings_count_sfh": structural_stats["sfh"]["buildings_count"],
        "buildings_count_mfh": structural_stats["mfh"]["buildings_count"],
        "households_sum_total": structural_stats["total"]["households_sum"],
        "households_sum_sfh": structural_stats["sfh"]["households_sum"],
        "households_sum_mfh": structural_stats["mfh"]["households_sum"],
        "residents_sum_total": structural_stats["total"]["residents_sum"],
        "residents_sum_sfh": structural_stats["sfh"]["residents_sum"],
        "residents_sum_mfh": structural_stats["mfh"]["residents_sum"],
        "net_floor_area_sum_total": structural_stats["total"]["net_floor_area_sum"],
        "net_floor_area_sum_sfh": structural_stats["sfh"]["net_floor_area_sum"],
        "net_floor_area_sum_mfh": structural_stats["mfh"]["net_floor_area_sum"],
        "total_electricity_demand_abs_no_ev_total": total_electricity_demand_no_ev,
        "total_electricity_demand_abs_no_ev_sfh": energy_acc["sfh"]["total_electricity_no_ev"],
        "total_electricity_demand_abs_no_ev_mfh": energy_acc["mfh"]["total_electricity_no_ev"],
        "total_electricity_demand_abs_yes_ev_total": total_electricity_demand_yes_ev,
        "total_electricity_demand_abs_yes_ev_sfh": energy_acc["sfh"]["total_electricity_yes_ev"],
        "total_electricity_demand_abs_yes_ev_mfh": energy_acc["mfh"]["total_electricity_yes_ev"],
        "total_dhw_heat_demand_abs_total": total_warm_water_demand,
        "total_dhw_heat_demand_abs_sfh": energy_acc["sfh"]["total_dhw"],
        "total_dhw_heat_demand_abs_mfh": energy_acc["mfh"]["total_dhw"],
        "total_heating_demand_abs_no_refurbishment_total": total_building_heat_no_ref,
        "total_heating_demand_abs_no_refurbishment_sfh": (
            energy_acc["sfh"]["total_heating_no_ref"]
            if energy_acc["sfh"]["total_heating_no_ref"] > 0 else None
        ),
        "total_heating_demand_abs_no_refurbishment_mfh": (
            energy_acc["mfh"]["total_heating_no_ref"]
            if energy_acc["mfh"]["total_heating_no_ref"] > 0 else None
        ),
        "total_heating_demand_abs_advanced_refurbishment_total": total_building_heat_advanced,
        "total_heating_demand_abs_advanced_refurbishment_sfh": (
            energy_acc["sfh"]["total_heating_advanced"]
            if energy_acc["sfh"]["total_heating_advanced"] > 0 else None
        ),
        "total_heating_demand_abs_advanced_refurbishment_mfh": (
            energy_acc["mfh"]["total_heating_advanced"]
            if energy_acc["mfh"]["total_heating_advanced"] > 0 else None
        ),
        "total_pv_potential_abs_total": total_pv_potential,
        "total_pv_potential_abs_sfh": (
            energy_acc["sfh"]["total_pv_potential"] if energy_acc["sfh"]["total_pv_potential"] > 0 else None
        ),
        "total_pv_potential_abs_mfh": (
            energy_acc["mfh"]["total_pv_potential"] if energy_acc["mfh"]["total_pv_potential"] > 0 else None
        ),
        "peak_electricity_abs_sum_no_ev_total": sum_electricity_peak_no_ev,
        "peak_electricity_abs_sum_no_ev_sfh": energy_acc["sfh"]["peak_electricity_no_ev_sum"],
        "peak_electricity_abs_sum_no_ev_mfh": energy_acc["mfh"]["peak_electricity_no_ev_sum"],
        "peak_electricity_abs_sum_yes_ev_total": sum_electricity_peak_yes_ev,
        "peak_electricity_abs_sum_yes_ev_sfh": energy_acc["sfh"]["peak_electricity_yes_ev_sum"],
        "peak_electricity_abs_sum_yes_ev_mfh": energy_acc["mfh"]["peak_electricity_yes_ev_sum"],
        "peak_dhw_abs_sum_total": sum_dhw_peak,
        "peak_dhw_abs_sum_sfh": energy_acc["sfh"]["peak_dhw_sum"],
        "peak_dhw_abs_sum_mfh": energy_acc["mfh"]["peak_dhw_sum"],
        "peak_heating_abs_sum_no_refurbishment_total": (
            sum_heating_peak_no_ref if sum_heating_peak_no_ref > 0 else None
        ),
        "peak_heating_abs_sum_no_refurbishment_sfh": (
            energy_acc["sfh"]["peak_heating_no_ref_sum"] if energy_acc["sfh"]["peak_heating_no_ref_sum"] > 0 else None
        ),
        "peak_heating_abs_sum_no_refurbishment_mfh": (
            energy_acc["mfh"]["peak_heating_no_ref_sum"] if energy_acc["mfh"]["peak_heating_no_ref_sum"] > 0 else None
        ),
        "peak_heating_abs_sum_advanced_refurbishment_total": (
            sum_heating_peak_advanced if sum_heating_peak_advanced > 0 else None
        ),
        "peak_heating_abs_sum_advanced_refurbishment_sfh": (
            energy_acc["sfh"]["peak_heating_advanced_sum"] if energy_acc["sfh"]["peak_heating_advanced_sum"] > 0 else None
        ),
        "peak_heating_abs_sum_advanced_refurbishment_mfh": (
            energy_acc["mfh"]["peak_heating_advanced_sum"] if energy_acc["mfh"]["peak_heating_advanced_sum"] > 0 else None
        ),
        "peak_pv_potential_abs_sum_total": sum_pv_peak if sum_pv_peak > 0 else None,
        "peak_pv_potential_abs_sum_sfh": (
            energy_acc["sfh"]["peak_pv_sum"] if energy_acc["sfh"]["peak_pv_sum"] > 0 else None
        ),
        "peak_pv_potential_abs_sum_mfh": (
            energy_acc["mfh"]["peak_pv_sum"] if energy_acc["mfh"]["peak_pv_sum"] > 0 else None
        ),
        "total_floor_area": total_floor_area,
        "number_of_sfh": number_of_sfh,
        "number_of_mfh": number_of_mfh,
        **construction_period_stats,
        "number_of_residents_per_total_floor_area_x100": _safe_per_100(total_residents, total_floor_area),
        "total_dhw_heat_demand_per_total_floor_area_x100": x100_total_dhw_from_buildings,
        "total_heating_demand_per_total_floor_area_x100_no_refurbishment": x100_total_heating_no_ref_from_buildings,
        "total_heating_demand_per_total_floor_area_x100_advanced_refurbishment": x100_total_heating_advanced_from_buildings,
        "total_electricity_demand_per_total_floor_area_x100_no_ev": x100_total_electricity_no_ev_from_buildings,
        "total_electricity_demand_per_total_floor_area_x100_yes_ev": x100_total_electricity_yes_ev_from_buildings,
        "total_pv_potential_per_total_floor_area_x100": x100_total_pv_from_buildings,
        "avg_electricity_peak_per_total_floor_area_x100_no_ev": x100_peak_electricity_no_ev_from_buildings,
        "avg_electricity_peak_per_total_floor_area_x100_yes_ev": x100_peak_electricity_yes_ev_from_buildings,
        "avg_dhw_peak_per_total_floor_area_x100": x100_peak_dhw_from_buildings,
        "avg_heating_peak_per_total_floor_area_x100_no_refurbishment": x100_peak_heating_no_ref_from_buildings,
        "avg_heating_peak_per_total_floor_area_x100_advanced_refurbishment": x100_peak_heating_advanced_from_buildings,
        # Backward-compatible aliases (kept as no_EV values)
        "total_electricity_demand_per_total_floor_area_x100": x100_total_electricity_no_ev_from_buildings,
        "avg_electricity_peak_per_total_floor_area_x100": x100_peak_electricity_no_ev_from_buildings,
        "processed_buildings": peak_counter,
        "skipped_buildings": len(skipped_buildings),
        "ev_yes_fallback_buildings": ev_yes_fallback_buildings,
        "partial_metric_warnings": len(partial_metric_warnings),
    }
    return summary, skipped_buildings, building_kpi_rows


def _export_ueu_outputs(
    ueu_case: str,
    summary: dict,
    building_rows_for_ueu: list[dict],
    skipped_buildings: list[tuple],
):
    summary_df = pd.DataFrame([summary])
    building_kpi_df = pd.DataFrame(building_rows_for_ueu)
    if not building_kpi_df.empty:
        building_kpi_df = building_kpi_df.sort_values(
            ["tabula_building_type", "building_id"]
        ).reset_index(drop=True)
    skipped_df = pd.DataFrame(
        [
            {"ueu_case": ueu_case, "building_id": building_id, "reason": reason}
            for building_id, reason in skipped_buildings
        ]
    )

    summary_excel_path = OUTPUT_DIR / f"reference_ueu_summary_{ueu_case}.xlsx"
    buildings_excel_path = OUTPUT_DIR / f"reference_ueu_buildings_{ueu_case}.xlsx"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with pd.ExcelWriter(summary_excel_path) as writer:
            summary_df.to_excel(writer, sheet_name="reference_summary", index=False)
            if not skipped_df.empty:
                skipped_df.to_excel(writer, sheet_name="skipped_buildings", index=False)
        print(f"saved summary excel: {summary_excel_path}")

        if not building_kpi_df.empty:
            with pd.ExcelWriter(buildings_excel_path) as writer:
                building_kpi_df.to_excel(writer, sheet_name="buildings", index=False)
            print(f"saved buildings excel: {buildings_excel_path}")
    except ModuleNotFoundError as exc:
        summary_csv_path = OUTPUT_DIR / f"reference_ueu_summary_{ueu_case}.csv"
        summary_df.to_csv(summary_csv_path, index=False)
        print(f"Excel export skipped ({exc}). Saved summary csv: {summary_csv_path}")

        if not building_kpi_df.empty:
            buildings_csv_path = OUTPUT_DIR / f"reference_ueu_buildings_{ueu_case}.csv"
            building_kpi_df.to_csv(buildings_csv_path, index=False)
            print(f"saved buildings csv: {buildings_csv_path}")

        if not skipped_df.empty:
            skipped_csv_path = OUTPUT_DIR / f"reference_ueu_skipped_buildings_{ueu_case}.csv"
            skipped_df.to_csv(skipped_csv_path, index=False)
            print(f"saved skipped buildings csv: {skipped_csv_path}")


def main():
    epw_path = None
    if get_project_root is not None:
        main_path = Path(get_project_root())
        candidate_epw_path = (
            main_path
            / "thermal_building_model"
            / "input"
            / "weather_files"
            / "03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv"
        )
        if candidate_epw_path.exists():
            epw_path = candidate_epw_path
        else:
            print(f"Weather file not found: {candidate_epw_path}. Energy KPIs will be skipped.")
    else:
        print("Optional dependencies missing (e.g. pvlib/oemof). Energy KPIs will be skipped.")

    if not UEU_CASES_TO_PROCESS:
        raise ValueError("UEU_CASES_TO_PROCESS is empty.")

    cluster_roots, missing_ueus = _resolve_cluster_roots_from_ueu_cases(
        EXAMPLES_BASE_DIR,
        UEU_CASES_TO_PROCESS,
    )
    if missing_ueus:
        print(f"Skipped missing UEU folders: {missing_ueus}")
    if not cluster_roots:
        print("No valid UEU folders selected.")
        return

    time_index = (
        solph.create_time_index(2025, number=NUMBER_OF_TIME_STEPS - 1)
        if solph is not None
        else None
    )
    exported_ueus = 0

    for cluster_root in cluster_roots:
        print(f"processing reference UEU: {cluster_root.name}")
        try:
            summary, skipped_buildings, building_rows_for_ueu = _summarize_ueu(
                cluster_root, epw_path, time_index
            )
        except Exception as exc:
            print(f"failed UEU {cluster_root.name}: {exc}")
            continue

        _export_ueu_outputs(
            ueu_case=cluster_root.name,
            summary=summary,
            building_rows_for_ueu=building_rows_for_ueu,
            skipped_buildings=skipped_buildings,
        )
        exported_ueus += 1

    if exported_ueus == 0:
        print("No UEU summaries created.")
    else:
        print(f"finished UEU-specific exports for {exported_ueus} UEU(s).")


if __name__ == "__main__":
    main()
