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

def epsilon_bucket_key(
    c: Number, p: Number, k: Number,
    eps_rel: Tuple[float,float,float],
    modes: Tuple[str,str,str]=('log','log','log'),
    scales: Tuple[float,float,float]=(1.0,1.0,10000.0),
) -> Tuple[int,int,int]:
    """
    modes: 'log' oder 'lin' je Achse
    scales: Vor-Skalierung je Achse (z.B. Totex in 10k-Schritten)
    """
    ex, ey, ez = (max(eps_rel[0],1e-12), max(eps_rel[1],1e-12), max(eps_rel[2],1e-12))
    def bucket(v, e, mode, s):
        v = max(v, 0.0)/s
        if mode == 'log':
            return math.floor(math.log1p(v)/e)
        else:  # 'lin'
            return math.floor(v/e)
    return (
        bucket(c, ex, modes[0], scales[0]),
        bucket(p, ey, modes[1], scales[1]),
        bucket(k, ez, modes[2], scales[2]),
    )

def epsilon_reduce(
    records: List[Dict[str,Any]],
    eps_rel: Tuple[float,float,float]=(0.01,0.01,0.01),
    modes: Tuple[str,str,str]=('log','log','log'),
    scales: Tuple[float,float,float]=(1.0,1.0,1.0),
) -> List[Dict[str,Any]]:
    """
    Pro Rasterzelle behalte den 'besten' Vertreter (hier: geringste Summe).
    Nutzt epsilon_bucket_key(..., modes, scales).
    """
    buckets: Dict[Tuple[int,int,int], Dict[str,Any]] = {}
    for r in records:
        key = epsilon_bucket_key(r['co2'], r['peak'], r['totex'], eps_rel, modes, scales)
        best = buckets.get(key)
        if best is None or (r['co2'] + r['peak'] + r['totex']) < (best['co2'] + best['peak'] + best['totex']):
            buckets[key] = r
    return list(buckets.values())


# ---------- Kombination mehrerer Gebäude ----------
def crowding_distance(records, keys=('co2','peak','totex')):
    n = len(records)
    if n == 0:
        return []
    dist = [0.0]*n
    for k in keys:
        order = sorted(range(n), key=lambda i: records[i][k])
        kmin = records[order[0]][k]; kmax = records[order[-1]][k]
        rng = (kmax - kmin) if kmax > kmin else 1.0
        dist[order[0]] = float('inf')
        dist[order[-1]] = float('inf')
        for r in range(1, n-1):
            prev_v = records[order[r-1]][k]
            next_v = records[order[r+1]][k]
            dist[order[r]] += (next_v - prev_v) / rng
    return dist

def select_by_crowding(records, k, keys=('co2','peak','totex')):
    if len(records) <= k:
        return records
    # ohne weitere Sortierung, wir haben schon Pareto-geprunet
    dist = crowding_distance(records, keys)
    idx = list(range(len(records)))
    idx.sort(key=lambda i: dist[i], reverse=True)
    return [records[i] for i in idx[:k]]
def combine_two_fronts(
    frontA: List[Dict[str,Any]],
    frontB: List[Dict[str,Any]],
    idA: str,
    idB: str,
    tau: float = 1e-9,
    eps_rel: Optional[Tuple[float,float,float]] = None,
    # NEU:
    modes: Tuple[str,str,str]=('log','log','lin'),
    scales: Tuple[float,float,float]=(1.0,1.0,10000.0),
    max_points: Optional[int] = None,
) -> List[Dict[str,Any]]:
    # Vorab ε-Reduktion auf A und B (falls gewünscht)
    A = frontA
    B = frontB
    if eps_rel is not None:
        A = epsilon_reduce(A, eps_rel, modes, scales)
        B = epsilon_reduce(B, eps_rel, modes, scales)

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

    # Nach dem Merge ggf. erneut ε-Reduktion
    if eps_rel is not None:
        merged = epsilon_reduce(merged, eps_rel, modes, scales)

    # Pareto
    pts = [(m['co2'], m['peak'], m['totex']) for m in merged]
    keep = pareto_prune_points(pts, tau=tau)
    pruned = [merged[i] for i in keep]

    # Cap via Crowding (deine neue Funktion)
    if max_points is not None and len(pruned) > max_points:
        pruned = select_by_crowding(pruned, max_points, keys=('co2','peak','totex'))

    return pruned

def combine_all_buildings(
    building_dict: Dict[str, Dict[str, Dict[Any, Dict[str,Any]]]],
    refurbishment_strategies: Iterable[str],
    tau: float = 1e-9,
    eps_rel_each: Optional[Tuple[float,float,float]] = None,
    eps_rel_merge: Optional[Tuple[float,float,float]] = (0.01,0.01,0.01),
    modes_each: Tuple[str,str,str]=('log','log','lin'),
    modes_merge: Tuple[str,str,str]=('log','log','lin'),
    scales_each: Tuple[float,float,float]=(1.0,1.0,10000.0),
    scales_merge: Tuple[float,float,float]=(1.0,1.0,10000.0),
    max_points_after_each_merge: Optional[int] = 5000,
) -> Tuple[Dict[str,List[Dict[str,Any]]], List[Dict[str,Any]]]:
    # 1) Per-Gebäude Pareto -> ε-Reduktion mit anisotropen Einstellungen
    per_building_fronts: Dict[str,List[Dict[str,Any]]] = {}
    for bid, bdata in building_dict.items():
        front = pareto_prune_building(bdata, refurbishment_strategies, tau=tau)
        if eps_rel_each is not None and len(front) > 0:
            front = epsilon_reduce(front, eps_rel_each, modes_each, scales_each)
            # streng prunen
            pts = [(r['co2'], r['peak'], r['totex']) for r in front]
            keep = pareto_prune_points(pts, tau=tau)
            front = [front[i] for i in keep]
        front = [{**r, 'selection': {bid: r}} for r in front]
        per_building_fronts[bid] = front

    # 2) Mergen mit denselben (oder eigenen) anisotropen Einstellungen
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
            modes=modes_merge,
            scales=scales_merge,
            max_points=max_points_after_each_merge,
        )

    # 3) finaler strenger Pareto-Schritt
    if current:
        pts = [(r['co2'], r['peak'], r['totex']) for r in current]
        keep = pareto_prune_points(pts, tau=tau)
        current = [current[i] for i in keep]

    return per_building_fronts, current

