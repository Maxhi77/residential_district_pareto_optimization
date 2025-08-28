from typing import Dict, Any, Iterable, List, Tuple, Optional
import math

Number = float

# ---------- Utilities ----------

def _as_float(x) -> Optional[Number]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None

def dominates(a: Tuple[Number,Number,Number], b: Tuple[Number,Number,Number], tau: float = 1e-9) -> bool:
    # a dominiert b (alle Ziele <=, mindestens eines <)
    return ((a[0] <= b[0] + tau) and (a[1] <= b[1] + tau) and (a[2] <= b[2] + tau)) and \
           ((a[0] <  b[0] - tau) or  (a[1] <  b[1] - tau) or  (a[2] <  b[2] - tau))

def pareto_prune_points(points: List[Tuple[Number,Number,Number]], tau: float = 1e-9) -> List[int]:
    """
    Klassisches Pareto-Pruning (alle Ziele minimieren).
    points: Liste von (co2, peak, totex)
    Rückgabe: Indizes der nicht dominierten Punkte (stabile Reihenfolge).
    """
    indexed = list(enumerate(points))
    indexed.sort(key=lambda kv: (kv[1][0], kv[1][1], kv[1][2]))  # stabil

    front_idx: List[int] = []
    keep_pts: List[Tuple[Number,Number,Number]] = []
    for idx, p in indexed:
        dominated_flag = False
        for q in keep_pts:
            if dominates(q, p, tau=tau):
                dominated_flag = True
                break
        if dominated_flag:
            continue

        survivors_i, survivors_p = [], []
        for i_old, q in zip(front_idx, keep_pts):
            if dominates(p, q, tau=tau):
                continue
            survivors_i.append(i_old)
            survivors_p.append(q)
        front_idx = survivors_i + [idx]
        keep_pts  = survivors_p + [p]

    front_idx.sort()
    return front_idx

# ---------- Gebäude: Optionen einsammeln + Pareto ----------

def collect_options_for_building(
    building_dict_for_one: Dict[str, Dict[Any, Dict[str, Any]]],
    refurbishment_strategies: Iterable[str],
) -> List[Dict[str, Any]]:
    """
    Erwartet Struktur:
      building[strategy][(co2_restrict, peak_restrict, strategy)] -> { 'co2','peak','totex', ... }
    Gibt Liste Records mit Zielen + Metadaten zurück.
    """
    out: List[Dict[str,Any]] = []
    for strat in refurbishment_strategies:
        bucket = building_dict_for_one.get(strat)
        if not bucket:
            continue
        for key, rec in bucket.items():
            if not isinstance(key, tuple) or len(key) < 2 or rec is None:
                continue
            co2  = _as_float(rec.get('co2'))
            peak = _as_float(rec.get('peak'))
            totex= _as_float(rec.get('totex'))
            if (co2 is None) or (peak is None) or (totex is None):
                continue
            out.append({
                'strategy': strat,
                'key': key,          # (co2_restriction, peak_restriction, strategy)
                'co2': co2,
                'peak': peak,
                'totex': totex,
                'record': rec,       # Originaldaten, falls später benötigt
            })
    return out

def pareto_prune_building(
    building_dict_for_one: Dict[str, Dict[Any, Dict[str, Any]]],
    refurbishment_strategies: Iterable[str],
    tau: float = 1e-9,
) -> List[Dict[str, Any]]:
    opts = collect_options_for_building(building_dict_for_one, refurbishment_strategies)
    if not opts:
        return []
    pts = [(o['co2'], o['peak'], o['totex']) for o in opts]
    keep = pareto_prune_points(pts, tau=tau)
    return [opts[i] for i in keep]

# ---------- ε-Dominanz (optional, hält Mengen klein) ----------

def epsilon_bucket_key(c: Number, p: Number, k: Number, eps_rel: Tuple[float,float,float]) -> Tuple[int,int,int]:
    # log1p-Bucketing robust bei Skalenunterschieden; Werte müssen >=0 sein
    ex, ey, ez = max(eps_rel[0],1e-12), max(eps_rel[1],1e-12), max(eps_rel[2],1e-12)
    return (
        math.floor(math.log1p(max(c,0.0))/ex),
        math.floor(math.log1p(max(p,0.0))/ey),
        math.floor(math.log1p(max(k,0.0))/ez),
    )

def epsilon_reduce(records: List[Dict[str,Any]], eps_rel=(0.01,0.01,0.01)) -> List[Dict[str,Any]]:
    """
    Pro Rasterzelle behalte den 'besten' Vertreter (hier: geringste Summe).
    """
    buckets: Dict[Tuple[int,int,int], Dict[str,Any]] = {}
    for r in records:
        key = epsilon_bucket_key(r['co2'], r['peak'], r['totex'], eps_rel)
        best = buckets.get(key)
        if best is None or (r['co2'] + r['peak'] + r['totex']) < (best['co2'] + best['peak'] + best['totex']):
            buckets[key] = r
    return list(buckets.values())

# ---------- Kombination mehrerer Gebäude ----------

def combine_two_fronts(
    frontA: List[Dict[str,Any]],
    frontB: List[Dict[str,Any]],
    idA: str,
    idB: str,
    tau: float = 1e-9,
    eps_rel: Optional[Tuple[float,float,float]] = None,
    max_points: Optional[int] = None,
) -> List[Dict[str,Any]]:
    """
    Bildet alle Summen aus frontA × frontB, pruned danach Pareto (optional mit ε und Cap).
    Jeder Record enthält 'selection': {building_id: chosen_record}.
    """
    # Kreuzprodukt erzeugen (ggf. vorher ε reduzieren, um Explosion zu vermeiden)
    A = frontA
    B = frontB
    if eps_rel is not None:
        A = epsilon_reduce(A, eps_rel)
        B = epsilon_reduce(B, eps_rel)

    merged: List[Dict[str,Any]] = []
    for a in A:
        for b in B:
            rec = {
                'co2':  a['co2']  + b['co2'],
                'peak': a['peak'] + b['peak'],
                'totex':a['totex']+ b['totex'],
                'selection': {
                    **(a.get('selection', {idA: a})),
                    **(b.get('selection', {idB: b})),
                }
            }
            merged.append(rec)

    # Optional nochmal ε (stärker) vorm Pareto, um die Menge klein zu halten
    if eps_rel is not None:
        merged = epsilon_reduce(merged, eps_rel)

    # Pareto-Pruning
    pts = [(m['co2'], m['peak'], m['totex']) for m in merged]
    keep = pareto_prune_points(pts, tau=tau)
    pruned = [merged[i] for i in keep]

    # Optional: Obergrenze -> behalte die „gleichmäßig guten“ (nach einfacher Score oder Crowding)
    if max_points is not None and len(pruned) > max_points:
        # simple Score (gewichtet gleich): normalisieren und sortieren
        cmax = max(r['co2'] for r in pruned); cmin = min(r['co2'] for r in pruned)
        pmax = max(r['peak'] for r in pruned); pmin = min(r['peak'] for r in pruned)
        kmax = max(r['totex'] for r in pruned); kmin = min(r['totex'] for r in pruned)
        def nz(x): return (x[0]-x[1]) if abs(x[0]-x[1])>1e-12 else 1.0
        dc, dp, dk = nz((cmax,cmin)), nz((pmax,pmin)), nz((kmax,kmin))
        def score(r):
            return ((r['co2']-cmin)/dc + (r['peak']-pmin)/dp + (r['totex']-kmin)/dk) / 3.0
        pruned.sort(key=score)
        pruned = pruned[:max_points]

    return pruned

def combine_all_buildings(
    building_dict: Dict[str, Dict[str, Dict[Any, Dict[str,Any]]]],
    refurbishment_strategies: Iterable[str],
    tau: float = 1e-9,
    eps_rel_each: Optional[Tuple[float,float,float]] = None,  # ε beim Gebäude-Pruning
    eps_rel_merge: Optional[Tuple[float,float,float]] = (0.01,0.01,0.01),  # ε beim Mergen
    max_points_after_each_merge: Optional[int] = 5000,        # Cap nach jedem Merge
) -> Tuple[Dict[str,List[Dict[str,Any]]], List[Dict[str,Any]]]:
    """
    1) Pareto pro Gebäude
    2) Iterativ kombinieren (Gebäude 1+2 -> 12, dann +3 -> 123, …)
    Rückgabe:
      - per_building_fronts: Pareto-Listen je Gebäude
      - combined_front: Pareto-Front über alle Gebäude
    """
    # 1) Per-Gebäude Pareto
    per_building_fronts: Dict[str,List[Dict[str,Any]]] = {}
    for bid, bdata in building_dict.items():
        front = pareto_prune_building(bdata, refurbishment_strategies, tau=tau)
        if eps_rel_each is not None and len(front) > 0:
            front = epsilon_reduce(front, eps_rel_each)
            # nochmal streng prunen
            pts = [(r['co2'], r['peak'], r['totex']) for r in front]
            keep = pareto_prune_points(pts, tau=tau)
            front = [front[i] for i in keep]
        # packe die Auswahl-Hülle rein (ein Gebäude → trivial)
        front = [{**r, 'selection': {bid: r}} for r in front]
        per_building_fronts[bid] = front

    # 2) Iterativ mergen
    bids = list(per_building_fronts.keys())
    if not bids:
        return per_building_fronts, []
    current = per_building_fronts[bids[0]]
    for i in range(1, len(bids)):
        nxt = per_building_fronts[bids[i]]
        current = combine_two_fronts(
            current, nxt, bids[0] if i==1 else "merged", bids[i],
            tau=tau,
            eps_rel=eps_rel_merge,
            max_points=max_points_after_each_merge,
        )

    # finaler, strenger Pareto-Schritt (ohne ε, damit wirklich exakt)
    if current:
        pts = [(r['co2'], r['peak'], r['totex']) for r in current]
        keep = pareto_prune_points(pts, tau=tau)
        current = [current[i] for i in keep]

    return per_building_fronts, current
