"""Barrier placement as a minimum-cost flow on the D8 drainage network.

Graph (one design storm):
    s → cell i            capacity r_i (runoff the cell produces), cost 0
    cell i → receiver(i)  capacity ∞, cost 0          (water keeps flowing downslope)
    cell i → t            capacity ∞, cost 0          if i drains out of the grid (lost runoff)
    cell i → B_j          capacity ∞, cost 0          for each cell i crossed by barrier j
    B_j → t               capacity c_j (storage), cost −1 + λ·L_j / f̂_j

Pushing all runoff from s to t at minimum cost routes as much water as
possible into barriers (negative cost = water retained), never more than
each barrier can store. Building a barrier has a fixed cost proportional to
its length L_j; fixed-charge flow is NP-hard, so it is linearized with
dynamic slope scaling (Kim & Pardalos, 1999): the per-unit charge is
λ·L_j / f̂_j, with f̂_j the flow the barrier received in the previous solve,
iterated until the set of used barriers stabilizes. λ (m³ that a meter of
barrier must retain to be worth building) is found by bisection so the used
length fits the budget.

Unlike the greedy method, this accounts for barrier capacity: a barrier
cannot retain more water than it can store, so the rest keeps flowing to the
barriers below.
"""
import math

import numpy as np
from ortools.graph.python import min_cost_flow

from pipeline import barriers as B

STORM_MM = 40          # design storm
POND_M3_PER_M = 0.9    # ponded storage per meter of contour barrier (~0.3 m deep × 3 m wide)
INFIL_M3_PER_M = 0.54  # infiltrated behind it during the event (3 m strip × 30 mm/h × 6 h)
CAP_M3_PER_M = POND_M3_PER_M + INFIL_M3_PER_M
SCALE = 10             # flow units per m³ (integer solver)
COST_SCALE = 1000      # cost units per m³ retained
BIG = 10**12
DSSP_ITERS = 8
BISECT_ITERS = 14


def runoff_m3(local_slope):
    """Design-storm runoff per cell: P × C × area, C rising with slope (bare-ish hillslope)."""
    c = 0.05 + 0.35 * np.clip(local_slope / 35, 0, 1) + 0.35 * 0.5
    return STORM_MM / 1000 * c * B.RES * B.RES


def _solve(recv, r, cands, unit_cost):
    """One min-cost flow. unit_cost[j] in cost units per flow unit (None = barrier excluded).
    Returns retained m³ per barrier."""
    n = recv.size
    S, T = n, n + 1
    bnode = lambda j: n + 2 + j
    mcf = min_cost_flow.SimpleMinCostFlow()
    tails, heads, caps, costs = [], [], [], []
    ri = np.round(r * SCALE).astype(np.int64)
    idx = np.arange(n)
    tails += [S] * n; heads += idx.tolist(); caps += ri.tolist(); costs += [0] * n
    down = np.where(recv >= 0, recv, T)
    tails += idx.tolist(); heads += down.tolist(); caps += [BIG] * n; costs += [0] * n
    for j, cd in enumerate(cands):
        if unit_cost[j] is None:
            continue
        for c in cd["cells"]:
            tails.append(c); heads.append(bnode(j)); caps.append(BIG); costs.append(0)
        tails.append(bnode(j)); heads.append(T); caps.append(int(cd["cap_m3"] * SCALE)); costs.append(int(unit_cost[j]))
    mcf.add_arcs_with_capacity_and_unit_cost(np.array(tails), np.array(heads), np.array(caps), np.array(costs))
    total = int(ri.sum())
    mcf.set_node_supply(S, total)
    mcf.set_node_supply(T, -total)
    status = mcf.solve()
    if status != mcf.OPTIMAL:
        raise RuntimeError(f"min cost flow failed: {status}")
    flows = mcf.flows(np.arange(mcf.num_arcs()))
    out = np.zeros(len(cands))
    arc = 2 * n
    for j, cd in enumerate(cands):
        if unit_cost[j] is None:
            continue
        arc += len(cd["cells"])
        out[j] = flows[arc] / SCALE
        arc += 1
    return out


def retained(recv, r, cands, chosen_idx):
    """m³ retained by a given set of barriers (pure max-retention flow, capacities respected)."""
    unit = [(-COST_SCALE // SCALE if j in chosen_idx else None) for j in range(len(cands))]
    return float(_solve(recv, r, cands, unit).sum())


def upstream_runoff(cands, r):
    """Runoff (m³) produced upslope of each candidate: standalone upper bound on what it can catch."""
    return np.array([r[cd["up"]].sum() for cd in cands])


def select(recv, r, cands, budget_m):
    """Lazy greedy (CELF) with an exact retention oracle.

    Each step adds the barrier with the largest marginal retained volume per
    meter, f(S ∪ {j}) − f(S), where f is the capacity-respecting maximum
    retention. With these costs the min-cost flow equals a maximum flow on the
    network without outlets, so the oracle is Dinic's algorithm (same values,
    about two orders of magnitude faster in the full selection; informe, P14).
    The final per-barrier flows still come from one min-cost flow solve. Retention is monotone and close to
    submodular, so stale gains are valid upper bounds and only the top of the
    queue needs re-evaluation.
    """
    import heapq
    lengths = np.array([cd["length_m"] for cd in cands])
    caps = np.array([cd["cap_m3"] for cd in cands])
    bound = np.minimum(caps, upstream_runoff(cands, r))
    heap = [(-bound[j] / lengths[j], j, -1) for j in range(len(cands)) if lengths[j] <= budget_m]
    heapq.heapify(heap)
    chosen, spent, base, it = [], 0.0, 0.0, 0
    while heap:
        neg, j, seen = heapq.heappop(heap)
        if spent + lengths[j] > budget_m:
            continue
        if seen == it:                       # gain is fresh for the current set: take it
            if -neg * lengths[j] < 0.5:      # less than half a m³: stop
                break
            chosen.append(j); spent += lengths[j]; base += -neg * lengths[j]; it += 1
            continue
        gain = retained_dinic(recv, r, cands, set(chosen) | {j}) - base
        heapq.heappush(heap, (-gain / lengths[j], j, it))
    unit = [(-COST_SCALE // SCALE if j in chosen else None) for j in range(len(cands))]
    f = _solve(recv, r, cands, unit)
    return chosen, f


def optimize(lon, lat, budget_m=1500, window_m=1200, storm_mm=None):
    global STORM_MM
    if storm_mm: STORM_MM = storm_mm
    margin_m = max(150, window_m * 0.25)
    z, lon_g, lat_g = B.fetch_dem(lon, lat, window_m, margin_m)
    to_ll = B.pixel_to_lonlat(lon_g, lat_g)
    m = int(round(margin_m / B.RES))
    win = (m, z.shape[0] - m, m, z.shape[1] - m)
    filled = B.fill_pits(z)
    recv = B.flow_directions(filled)
    acc = B.accumulation(filled, recv).reshape(z.shape)
    donors = B.donors_of(recv)
    zs = B.smooth3(z)
    local_slope = B.slope_deg(zs)
    r0, r1, c0, c1 = win
    interval = B.vertical_interval(float(local_slope[r0:r1, c0:c1].mean()))
    cands_all = B.candidates(zs, acc, local_slope, interval, win)
    for cd in cands_all:
        cd["up"] = B.upstream(cd["cells"], donors)
    contour = [c for c in cands_all if c["type"] == "curva de nivel"]
    for cd in contour:
        cd["cap_m3"] = CAP_M3_PER_M * cd["length_m"]
    r = runoff_m3(local_slope).ravel()

    chosen_idx, f = select(recv, r, contour, budget_m)
    greedy_sel, _, _, _ = B.greedy([dict(c) for c in contour], z.size, budget_m)
    # map greedy picks back to indices in `contour` (greedy works on copies: match by geometry)
    gk = {(round(c["level"], 3), tuple(c["cells"])) for c in greedy_sel}
    greedy_idx = {j for j, c in enumerate(contour) if (round(c["level"], 3), tuple(c["cells"])) in gk}
    ret_mcmf = retained(recv, r, contour, set(chosen_idx))
    ret_greedy = retained(recv, r, contour, greedy_idx)
    runoff_total = float(r.sum())

    feats = []
    for rank, j in enumerate(chosen_idx, 1):
        cd = contour[j]
        lo, la = to_ll(cd["pts"][:, 0], cd["pts"][:, 1])
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": np.column_stack([lo, la]).tolist()},
                      "properties": {"rank": rank, "type": "curva de nivel", "length_m": round(cd["length_m"], 1),
                                     "retained_m3": round(float(f[j]), 1), "capacity_m3": round(cd["cap_m3"], 1),
                                     "full": bool(f[j] >= 0.99 * cd["cap_m3"])}})
    corners = to_ll(np.array([c0, c1, c1, c0, c0]) - 0.5, np.array([r0, r0, r1, r1, r0]) - 0.5)
    used_len = sum(contour[j]["length_m"] for j in chosen_idx)
    return {
        "method": "lazy greedy (CELF) con flujo máximo de Dinic como oráculo",
        "selected": {"type": "FeatureCollection", "features": feats},
        "drainage": B.drainage_lines(acc, recv, to_ll, win),
        "window": {"type": "Feature", "properties": {},
                   "geometry": {"type": "Polygon", "coordinates": [np.column_stack(corners).tolist()]}},
        "totals": {"n_barriers": len(chosen_idx), "length_m": round(used_len, 1),
                   "storm_runoff_m3": round(runoff_total), "retained_m3": round(ret_mcmf),
                   "retained_pct": round(100 * ret_mcmf / runoff_total, 1),
                   "full_barriers": sum(1 for x in feats if x["properties"]["full"])},
        "comparison": {"greedy_retained_m3": round(ret_greedy), "greedy_n": len(greedy_idx),
                       "greedy_length_m": round(sum(contour[j]["length_m"] for j in greedy_idx), 1),
                       "gain_pct": round(100 * (ret_mcmf / max(ret_greedy, 1e-9) - 1), 1)},
        "params": {"storm_mm": STORM_MM, "cap_m3_per_m": CAP_M3_PER_M, "vertical_interval_m": interval,
                   "budget_m": budget_m, "candidates": len(contour)},
        "_grid": {"z": z, "recv": recv, "acc": acc, "win": win, "to_ll": to_ll, "contour": contour,
                  "chosen": chosen_idx, "greedy": sorted(greedy_idx), "runoff": r},
    }


# ---------------------------------------------------------------- alternative retention oracles
def _graph_parts(recv, r, cands, chosen_idx):
    """Integer capacities shared by the max-flow oracles (same scaling as the min-cost flow)."""
    ri = np.round(r * SCALE).astype(np.int64)
    chosen = sorted(chosen_idx)
    caps = {j: int(cands[j]["cap_m3"] * SCALE) for j in chosen}
    return ri, chosen, caps


def retained_dinic(recv, r, cands, chosen_idx):
    """Maximum retention as a pure maximum flow, solved with Dinic's algorithm.

    Same network as the min-cost flow but without the cell → outlet arcs: the sink t is
    reachable only through barriers, so the maximum s–t flow is the maximum water the
    chosen barriers can retain while respecting drainage and capacity.
    """
    ri, chosen, caps = _graph_parts(recv, r, cands, chosen_idx)
    n = recv.size
    S, T = n, n + 1
    N = n + 2 + len(chosen)
    head, to, cap, nxt = [-1] * N, [], [], []

    def add(u, v, c):
        to.append(v); cap.append(c); nxt.append(head[u]); head[u] = len(to) - 1
        to.append(u); cap.append(0); nxt.append(head[v]); head[v] = len(to) - 1

    # only cells that can reach a chosen barrier matter
    useful = np.zeros(n, bool)
    for j in chosen:
        useful[cands[j]["up"]] = True
    for i in np.flatnonzero(useful & (ri > 0)):
        add(S, int(i), int(ri[i]))
    for i in np.flatnonzero(useful):
        if recv[i] >= 0 and useful[recv[i]]:
            add(int(i), int(recv[i]), BIG)
    for k, j in enumerate(chosen):
        b = n + 2 + k
        for c in cands[j]["cells"]:
            if useful[c]:
                add(int(c), b, BIG)
        add(b, T, caps[j])

    flow = 0
    while True:
        level = [-1] * N; level[S] = 0; q = [S]
        for u in q:                                   # BFS: level graph
            e = head[u]
            while e != -1:
                if cap[e] > 0 and level[to[e]] < 0:
                    level[to[e]] = level[u] + 1; q.append(to[e])
                e = nxt[e]
        if level[T] < 0:
            break
        it = head[:]
        while True:                                   # blocking flow with iterative DFS
            stack, path = [S], []
            while stack:
                u = stack[-1]
                if u == T:
                    break
                e = it[u]
                while e != -1 and not (cap[e] > 0 and level[to[e]] == level[u] + 1):
                    e = nxt[e]
                it[u] = e
                if e == -1:
                    stack.pop()
                    if path:
                        it[stack[-1]] = nxt[it[stack[-1]]]; path.pop()
                    level[u] = -1
                else:
                    stack.append(to[e]); path.append(e)
            if not stack:
                break
            push = min(cap[e] for e in path)
            for e in path:
                cap[e] -= push; cap[e ^ 1] += push
            flow += push
    return flow / SCALE


def retained_fill(recv, r, cands, chosen_idx):
    """Topological greedy fill: route runoff downslope once, from the ridges to the outlets, and let
    each chosen barrier keep what reaches it until it is full. Linear time; no optimality guarantee."""
    n = recv.size
    rem = np.zeros(len(cands))
    owners = {}
    for j in chosen_idx:
        rem[j] = cands[j]["cap_m3"]
        for c in cands[j]["cells"]:
            owners.setdefault(c, []).append(j)
    indeg = np.zeros(n, np.int64)
    has = recv >= 0
    np.add.at(indeg, recv[has], 1)
    q = r.astype(float).copy()
    stack = list(np.flatnonzero(indeg == 0))
    kept = 0.0
    while stack:                                       # Kahn's order: every donor before its receiver
        i = stack.pop()
        for j in owners.get(i, ()):
            take = min(q[i], rem[j])
            q[i] -= take; rem[j] -= take; kept += take
        d = recv[i]
        if d >= 0:
            q[d] += q[i]
            indeg[d] -= 1
            if indeg[d] == 0:
                stack.append(d)
    return kept


def select_with(oracle, recv, r, cands, budget_m):
    """Same lazy greedy (CELF) as select(), with any retention oracle; returns chosen ids and oracle calls."""
    import heapq
    lengths = np.array([cd["length_m"] for cd in cands])
    caps = np.array([cd["cap_m3"] for cd in cands])
    bound = np.minimum(caps, upstream_runoff(cands, r))
    heap = [(-bound[j] / lengths[j], j, -1) for j in range(len(cands)) if lengths[j] <= budget_m]
    heapq.heapify(heap)
    chosen, spent, base, it, calls = [], 0.0, 0.0, 0, 0
    while heap:
        neg, j, seen = heapq.heappop(heap)
        if spent + lengths[j] > budget_m:
            continue
        if seen == it:
            if -neg * lengths[j] < 0.5:
                break
            chosen.append(j); spent += lengths[j]; base += -neg * lengths[j]; it += 1
            continue
        gain = oracle(recv, r, cands, set(chosen) | {j}) - base; calls += 1
        heapq.heappush(heap, (-gain / lengths[j], j, it))
    return chosen, calls


def setup(lon, lat, window_m=1200, storm_mm=STORM_MM):
    """Drainage network, contour candidates and design-storm runoff for one site (no optimization)."""
    global STORM_MM
    STORM_MM = storm_mm
    margin_m = max(150, window_m * 0.25)
    z, lon_g, lat_g = B.fetch_dem(lon, lat, window_m, margin_m)
    m = int(round(margin_m / B.RES))
    win = (m, z.shape[0] - m, m, z.shape[1] - m)
    filled = B.fill_pits(z)
    recv = B.flow_directions(filled)
    acc = B.accumulation(filled, recv).reshape(z.shape)
    donors = B.donors_of(recv)
    zs = B.smooth3(z)
    local_slope = B.slope_deg(zs)
    r0, r1, c0, c1 = win
    interval = B.vertical_interval(float(local_slope[r0:r1, c0:c1].mean()))
    cands = B.candidates(zs, acc, local_slope, interval, win)
    for cd in cands:
        cd["up"] = B.upstream(cd["cells"], donors)
    contour = [c for c in cands if c["type"] == "curva de nivel"]
    for cd in contour:
        cd["cap_m3"] = CAP_M3_PER_M * cd["length_m"]
    return recv, runoff_m3(local_slope).ravel(), contour
