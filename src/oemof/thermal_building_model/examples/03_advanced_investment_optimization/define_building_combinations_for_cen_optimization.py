import random

def min_max_choice_per_building(buildings_dict, refurbishments):
    # buildings_dict: {building_id: {refurb: building_obj}}
    min_choice = {}
    max_choice = {}

    for bid, variants in buildings_dict.items():
        caps = [(r, float(variants[r].capex_annuity)) for r in refurbishments if r in variants]

        if not caps:
            raise ValueError(f"Gebäude {bid} hat keine der refurbishments-Optionen: {refurbishments}")

        r_min = min(caps, key=lambda x: x[1])[0]
        r_max = max(caps, key=lambda x: x[1])[0]

        min_choice[bid] = r_min
        max_choice[bid] = r_max

    return min_choice, max_choice


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


def build_scenarios(matching_buildings_sfh, matching_buildings_mfh, refurbishments, n_random=400, seed=1):
    # zusammenführen
    buildings_all = {}
    buildings_all.update(matching_buildings_sfh)
    buildings_all.update(matching_buildings_mfh)

    building_ids = list(buildings_all.keys())
    dims = len(building_ids)

    # Extremfälle (pro Gebäude min/max capex_annuity über refurbishments)
    min_choice, max_choice = min_max_choice_per_building(buildings_all, refurbishments)

    scenarios = [
        {"name": "capex_min_per_building", "choice": min_choice},
        {"name": "capex_max_per_building", "choice": max_choice},
    ]

    # LHS Samples
    U = latin_hypercube_discrete(n_samples=n_random, dims=dims, seed=seed)

    for s in range(n_random):
        choice = {}
        for d, bid in enumerate(building_ids):
            choice[bid] = u_to_refurb(U[s][d], refurbishments)
        scenarios.append({"name": f"lhs_{s:04d}", "choice": choice})

    return scenarios, buildings_all


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
