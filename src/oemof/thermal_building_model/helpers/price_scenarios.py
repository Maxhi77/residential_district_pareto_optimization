from __future__ import annotations

import copy
from typing import Any


PRICE_SCENARIO_CONFIGS = {
    "ref": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "yes_ev": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "yes_ev2": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "yes_ev_total": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "yes_ev_half": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "electricity_minus20": {
        "electricity_factor": 0.8,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "electricity_plus20": {
        "electricity_factor": 1.2,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "electricity_minus40": {
        "electricity_factor": 0.6,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "electricity_plus40": {
        "electricity_factor": 1.4,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "electricity_feed_in_minus20": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 0.8,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "electricity_feed_in_plus20": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.2,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "electricity_feed_in_minus40": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 0.6,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "electricity_feed_in_plus40": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.4,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "gas_minus20": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 0.8,
        "bio_gas_factor": 0.8,
        "hydrogen_factor": 1.0,
    },
    "gas_plus20": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.2,
        "bio_gas_factor": 1.2,
        "hydrogen_factor": 1.0,
    },
    "gas_minus40": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 0.6,
        "bio_gas_factor": 0.6,
        "hydrogen_factor": 1.0,
    },
    "gas_plus40": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.4,
        "bio_gas_factor": 1.4,
        "hydrogen_factor": 1.0,
    },
    "hydrogen_minus20": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 0.8,
    },
    "hydrogen_plus20": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.2,
    },
    "hydrogen_minus40": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 0.6,
    },
    "hydrogen_plus40": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.4,
    },
    "ntr16": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "ems22": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "ems24": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
    "bau": {
        "electricity_factor": 1.0,
        "electricity_feed_in_factor": 1.0,
        "natural_gas_factor": 1.0,
        "bio_gas_factor": 1.0,
        "hydrogen_factor": 1.0,
    },
}

DEFAULT_PRICE_SCENARIO_SWEEP = [
    "ref",
    "bau",
    "electricity_minus20",
    "electricity_plus20",
    "electricity_minus40",
    "electricity_plus40",
    "electricity_feed_in_minus20",
    "electricity_feed_in_plus20",
    "electricity_feed_in_minus40",
    "electricity_feed_in_plus40",
    "gas_minus20",
    "gas_plus20",
    "gas_minus40",
    "gas_plus40",
    "hydrogen_minus20",
    "hydrogen_plus20",
    "hydrogen_minus40",
    "hydrogen_plus40",
]
DEFAULT_PRICE_SCENARIOS = list(DEFAULT_PRICE_SCENARIO_SWEEP)
PRICE_SCENARIO_REQUIRED_KEYS = {
    "electricity_factor",
    "electricity_feed_in_factor",
    "natural_gas_factor",
    "bio_gas_factor",
    "hydrogen_factor",
}


def normalize_price_scenario_name(name: Any) -> str:
    if name is None:
        return "ref"
    value = str(name).strip().lower()
    return value if value else "ref"


def resolve_price_scenario_config(price_scenario: Any) -> dict[str, float]:
    if isinstance(price_scenario, dict):
        missing = sorted(PRICE_SCENARIO_REQUIRED_KEYS.difference(price_scenario.keys()))
        if missing:
            raise ValueError(f"price_scenario dict is missing keys: {missing}")
        return copy.deepcopy(price_scenario)

    scenario_name = normalize_price_scenario_name(price_scenario)
    if scenario_name not in PRICE_SCENARIO_CONFIGS:
        raise ValueError(
            f"Unknown price scenario '{price_scenario}'. Supported: {sorted(PRICE_SCENARIO_CONFIGS.keys())}"
        )
    return copy.deepcopy(PRICE_SCENARIO_CONFIGS[scenario_name])


def scenario_output_cluster_name(cluster_name: str, price_scenario_name: Any) -> str:
    scenario_name = normalize_price_scenario_name(price_scenario_name)
    if scenario_name == "ref":
        return cluster_name
    return f"{cluster_name}_{scenario_name}"


def parse_price_scenarios(raw_csv: Any) -> list[str]:
    if raw_csv is None:
        return list(DEFAULT_PRICE_SCENARIOS)

    values = []
    seen = set()
    for token in str(raw_csv).split(","):
        scenario_name = normalize_price_scenario_name(token)
        scenario_names = DEFAULT_PRICE_SCENARIO_SWEEP if scenario_name == "all" else [scenario_name]
        for name in scenario_names:
            if name not in PRICE_SCENARIO_CONFIGS:
                raise ValueError(
                    f"Unknown price scenario '{name}'. Supported: {sorted(PRICE_SCENARIO_CONFIGS.keys())} or 'all'"
                )
            if name in seen:
                continue
            seen.add(name)
            values.append(name)

    return values if values else list(DEFAULT_PRICE_SCENARIOS)
