from __future__ import annotations

import os
from typing import Any

import geopandas as gpd

from oemof.thermal_building_model.helpers.optimization_io import (
    is_reference_k,
    k_to_folder_token,
    safe_load_cluster_pickle,
)


def discover_available_k_values(base_path: str, cluster_name: str, building_type: str | None = None) -> list[int]:
    cluster_root = os.path.join(base_path, cluster_name)
    if not os.path.isdir(cluster_root):
        return []

    if building_type == "SFH":
        prefixes = ("sfh_cluster_k",)
    elif building_type == "MFH":
        prefixes = ("mfh_cluster_k",)
    elif building_type is None:
        prefixes = ("sfh_cluster_k", "mfh_cluster_k")
    else:
        raise ValueError(f"Unsupported building_type '{building_type}'")

    k_values = set()
    for folder_name in os.listdir(cluster_root):
        folder_path = os.path.join(cluster_root, folder_name)
        if not os.path.isdir(folder_path):
            continue
        for prefix in prefixes:
            if folder_name.startswith(prefix):
                suffix = folder_name[len(prefix):]
                if suffix.isdigit():
                    k_values.add(int(suffix))
    return sorted(k_values)


def load_cluster_for_k_and_type(
    base_path: str,
    cluster_name: str,
    k_value: Any,
    building_type: str,
    *,
    add_reference_buildings_in_cluster: bool = False,
) -> tuple[Any, str]:
    cluster_root = os.path.join(base_path, cluster_name)
    if is_reference_k(k_value):
        gpkg_ueu = os.path.join(cluster_root, f"{cluster_name}.gpkg")
        if not os.path.exists(gpkg_ueu):
            raise FileNotFoundError(f"Reference gpkg not found: {gpkg_ueu}")
        gdf_ueu = gpd.read_file(gpkg_ueu)
        reference_cluster = gdf_ueu.loc[gdf_ueu["tabula_building_type"] == building_type].copy()
        if add_reference_buildings_in_cluster:
            reference_cluster["buildings_in_cluster"] = 1
        return reference_cluster, os.path.join(cluster_root, "reference")

    k_token = k_to_folder_token(k_value)
    if building_type == "SFH":
        prefix = "sfh"
    elif building_type == "MFH":
        prefix = "mfh"
    else:
        raise ValueError(f"Unsupported building_type '{building_type}'")

    cluster_dir = os.path.join(cluster_root, f"{prefix}_cluster_{k_token}")
    cluster_path = os.path.join(cluster_dir, f"{prefix}_cluster.pkl")
    return safe_load_cluster_pickle(cluster_path), cluster_dir


def load_cluster_for_type(
    base_path: str,
    cluster_name: str,
    building_type: str,
    k_value: Any,
    *,
    add_reference_buildings_in_cluster: bool = False,
):
    cluster, _ = load_cluster_for_k_and_type(
        base_path,
        cluster_name,
        k_value,
        building_type,
        add_reference_buildings_in_cluster=add_reference_buildings_in_cluster,
    )
    return cluster


def load_clusters_for_k(base_path: str, cluster_name: str, k_value: Any):
    sfh_cluster, sfh_dir = load_cluster_for_k_and_type(base_path, cluster_name, k_value, "SFH")
    mfh_cluster, mfh_dir = load_cluster_for_k_and_type(base_path, cluster_name, k_value, "MFH")
    return sfh_cluster, mfh_cluster, sfh_dir, mfh_dir


def load_clusters_for_k_pair(base_path: str, cluster_name: str, sfh_k_value: Any, mfh_k_value: Any):
    sfh_cluster, sfh_dir = load_cluster_for_k_and_type(base_path, cluster_name, sfh_k_value, "SFH")
    mfh_cluster, mfh_dir = load_cluster_for_k_and_type(base_path, cluster_name, mfh_k_value, "MFH")
    return sfh_cluster, mfh_cluster, sfh_dir, mfh_dir


def collect_building_ids_for_k(
    base_path: str,
    cluster_name: str,
    k_value: Any,
    building_type: str | None = None,
) -> list[Any]:
    sfh_cluster, mfh_cluster, _, _ = load_clusters_for_k(base_path, cluster_name, k_value)
    building_ids = []
    if building_type in (None, "SFH") and not sfh_cluster.empty and "building_id" in sfh_cluster.columns:
        building_ids.extend(sfh_cluster["building_id"].tolist())
    if building_type in (None, "MFH") and not mfh_cluster.empty and "building_id" in mfh_cluster.columns:
        building_ids.extend(mfh_cluster["building_id"].tolist())
    return list(dict.fromkeys(building_ids))
