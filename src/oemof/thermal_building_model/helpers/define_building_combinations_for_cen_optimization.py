import random

import math
from typing import Dict, List, Tuple, Callable, Any

def build_scenarios(
    matching_buildings_sfh: Dict[str, Dict[str, Any]],
    matching_buildings_mfh: Dict[str, Dict[str, Any]],
    n_random: int = 400,
    seed: int = 1,
):
    """
    Builds scenarios by selecting exactly ONE refurbishment option per building.

    Input format (as you have it):
        matching_buildings_sfh[building_id][refurbishment] = ThermalBuilding(...)
        matching_buildings_mfh[building_id][refurbishment] = ThermalBuilding(...)

    Output:
        scenarios: list of {"name": str, "choice": {building_id: refurbishment_key}}
        buildings_all: merged dict (sfh+mfh)
        available_by_building: {building_id: [refurbishment_keys...]}
    """

    # -------------------------
    # merge buildings
    # -------------------------
    buildings_all = {}
    buildings_all.update(matching_buildings_sfh or {})
    buildings_all.update(matching_buildings_mfh or {})

    building_ids = list(buildings_all.keys())
    if not building_ids:
        raise ValueError("No buildings found in matching_buildings_sfh/mfh.")

    # -------------------------
    # available refurbishment keys per building
    # -------------------------
    available_by_building = {bid: list(buildings_all[bid].keys()) for bid in building_ids}

    # sanity check
    for bid, opts in available_by_building.items():
        if not opts:
            raise ValueError(f"Building {bid} has no refurbishment options.")

    # -------------------------
    # IMPORTANT: define how to score a (building, refurbishment) choice
    # You MUST adapt this to your data.
    # -------------------------
    def score_fn(building_id: str, refurbishment: str, obj: Any) -> float:
        """
        Returns a number to minimize (for capex_min) / maximize (for capex_max).

        ADAPT ONE OF THESE OPTIONS:

        Option A (common): obj is dict-like and contains 'capex_annuity'
            return float(obj["capex_annuity"])

        Option B: obj has attribute capex_annuity
            return float(obj.capex_annuity)

        Option C: you store capex in a separate dict outside this function
            return float(capex_annuity[building_id][refurbishment])

        If you do NOT have capex available (yet), you can still run scenarios by
        returning 0.0 here (then min/max scenarios are identical).
        """
        # --- Option A: dict-style ---
        if isinstance(obj, dict) and "capex_annuity" in obj:
            return float(obj["capex_annuity"])

        # --- Option B: attribute-style ---
        if hasattr(obj, "capex_annuity"):
            return float(getattr(obj, "capex_annuity"))

        # --- Fallback: no score available ---
        return 0.0

    # -------------------------
    # choose min/max option per building (robust even if only 1 option exists)
    # -------------------------
    min_choice, max_choice = min_max_choice_per_building(
        buildings_all=buildings_all,
        available_by_building=available_by_building,
        score_fn=score_fn,
    )

    scenarios = [
        {"name": "capex_min_per_building", "choice": min_choice},
        {"name": "capex_max_per_building", "choice": max_choice},
    ]

    # -------------------------
    # Latin Hypercube sampling over discrete options
    # -------------------------
    U = latin_hypercube_unit(n_samples=n_random, dims=len(building_ids), seed=seed)

    for s in range(n_random):
        choice = {}
        for d, bid in enumerate(building_ids):
            opts = available_by_building[bid]              # only options that exist for THIS building
            choice[bid] = u_to_discrete_choice(U[s][d], opts)
        scenarios.append({"name": f"lhs_{s:04d}", "choice": choice})

    return scenarios, buildings_all, available_by_building


def min_max_choice_per_building(
    buildings_all: Dict[str, Dict[str, Any]],
    available_by_building: Dict[str, List[str]],
    score_fn: Callable[[str, str, Any], float],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    For each building, select refurbishment option with minimum / maximum score.
    Works also if there is only a single option.
    """
    min_choice = {}
    max_choice = {}

    for bid, opts in available_by_building.items():
        scored = []
        for r in opts:
            if bid in buildings_all and r in buildings_all[bid]:
                obj = buildings_all[bid][r]
                scored.append((r, score_fn(bid, r, obj)))

        if not scored:
            raise ValueError(
                f"Building {bid} has none of the provided refurbishment options: {opts}. "
                f"Available keys in buildings_all[{bid}] are: {list(buildings_all.get(bid, {}).keys())}"
            )

        min_choice[bid] = min(scored, key=lambda x: x[1])[0]
        max_choice[bid] = max(scored, key=lambda x: x[1])[0]

    return min_choice, max_choice


# -------------------------
# Sampling helpers
# -------------------------
def latin_hypercube_unit(n_samples: int, dims: int, seed: int = 1) -> List[List[float]]:
    """
    Simple LHS in [0,1) for discrete choice mapping.
    Returns U with shape [n_samples][dims].
    """
    import random
    random.seed(seed)

    U = [[0.0] * dims for _ in range(n_samples)]
    # for each dimension, build a stratified permutation
    for d in range(dims):
        strata = [(i + random.random()) / n_samples for i in range(n_samples)]
        random.shuffle(strata)
        for s in range(n_samples):
            U[s][d] = strata[s]
    return U


def u_to_discrete_choice(u: float, options: List[str]) -> str:
    """
    Map u in [0,1) to one of the discrete options.
    If options has length 1 -> always returns that one (your 'advanced' case).
    """
    if not options:
        raise ValueError("u_to_discrete_choice got empty options.")
    if len(options) == 1:
        return options[0]
    idx = min(int(math.floor(u * len(options))), len(options) - 1)
    return options[idx]

def latin_hypercube_discrete(n_samples: int, dims: int, seed: int = 1):
    rng = random.Random(seed)
    U = [[0.0] * dims for _ in range(n_samples)]

    for d in range(dims):
        vals = [(i + rng.random()) / n_samples for i in range(n_samples)]
        rng.shuffle(vals)
        for i in range(n_samples):
            U[i][d] = vals[i]
    return U


def u_to_refurb(u: float, options):
    k = int(u * len(options))
    if k == len(options):
        k -= 1
    return options[k]



def scenario_total_capex(choice_dict, buildings_all):
    total = 0.0
    for bid, refurb in choice_dict.items():
        total += float(buildings_all[bid][refurb].capex_annuity)
    return total
def scenario_signature(choice_dict):
    """
    Eindeutige, hashbare Repräsentation eines Szenarios
    """
    return tuple(sorted(choice_dict.items()))

def remove_duplicate_scenarios(scenarios):
    seen = set()
    unique_scenarios = []

    for sc in scenarios:
        sig = scenario_signature(sc["choice"])
        if sig not in seen:
            seen.add(sig)
            unique_scenarios.append(sc)

    print(f"Entfernt: {len(scenarios) - len(unique_scenarios)} Duplikate")
    return unique_scenarios
