"""Extra mathematics for the report: uncertainty (Monte Carlo), duality / shadow
prices, Gumbel return periods and the water–equity Pareto frontier.

    .venv/bin/python -W ignore informe/matematicas.py
Writes informe/math.json and figures g9–g12 in informe/figuras/.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))
import ee  # noqa: E402

from pipeline import barriers_mcmf as M, layers, optimize as O  # noqa: E402

SEC_Y = 31_536_000
H = 3000                     # hectares budget
N_MC = 2000
RNG = np.random.default_rng(42)
SUPPLY_NAMES = {sid: name for sid, name in O.SUPPLY.values()}
GUMBEL_SITES = {"La Boca": (-100.20, 25.45), "Santa Catarina": (-100.45, 25.50),
                "Cerro Prieto": (-99.95, 24.75), "El Cuchillo (Pilón)": (-100.05, 25.00)}
SITE = (-100.45, 25.45)
ls = lambda m3: m3 / SEC_Y * 1000


def cells_arrays():
    rows = O.cell_table()
    A = np.array([r["eligible_ha"] for r in rows]); P = np.array([r["rain_mm"] for r in rows], float)
    C = np.array([r["c"] for r in rows]); k = np.array([r["connectivity"] for r in rows])
    sup = np.array([r["supply"] for r in rows])
    return rows, A, P, C, k, sup


def value(A, P, C, k, rho):
    return P / 1000 * C * A * 1e4 * rho * k


def knapsack(v, A, budget):
    """Fractional knapsack: chosen fraction per cell, total value and dual λ* (value per ha of the marginal cell)."""
    order = np.argsort(-v / A); x = np.zeros_like(A); used = 0.0; lam = 0.0
    for i in order:
        if used >= budget:
            break
        take = min(A[i], budget - used); x[i] = take / A[i]; used += take; lam = v[i] / A[i]
    return x, float((x * v).sum()), lam


def balanced(v, A, sup, budget, alpha=1.0):
    """Each supply gets at least alpha·budget/4 (greedy within it); the rest goes to the global greedy."""
    sids = sorted(set(sup)); x = np.zeros_like(A)
    for s in sids:
        idx = np.flatnonzero(sup == s)
        xs, _, _ = knapsack(v[idx], A[idx], alpha * budget / len(sids)); x[idx] = xs
    rem = budget - (x * A).sum()
    free = A * (1 - x)
    if rem > 0:
        order = np.argsort(-v / A)
        for i in order:
            if rem <= 0:
                break
            if free[i] <= 0:
                continue
            take = min(free[i], rem); x[i] += take / A[i]; rem -= take
    return x


# ---------------------------------------------------------------- 1 · Monte Carlo
def monte_carlo(A, P, C, k, sup):
    tot_max, tot_bal, by_sup = [], [], {s: [] for s in SUPPLY_NAMES}
    chosen = np.zeros_like(A)
    base_rho = np.array([O.retention(p) for p in P])
    for _ in range(N_MC):
        c_f = RNG.uniform(0.7, 1.3); ff = RNG.uniform(*O.FIELD_FACTOR); bias = RNG.normal(1, 0.1)
        k_ec = RNG.uniform(0.4, 0.8)
        kk = np.where(np.isclose(k, 0.6), k_ec, k)
        Pb = P * bias
        rho = np.array([O.retention(p) for p in Pb]) * ff
        v = value(A, Pb, np.clip(C * c_f, 0.02, 0.9), kk, rho)
        x, tot, _ = knapsack(v, A, H)
        tot_max.append(ls(tot)); chosen += (x > 0.5)
        xb = balanced(v, A, sup, H)
        tot_bal.append(ls((xb * v).sum()))
        for s in SUPPLY_NAMES:
            by_sup[s].append(ls((x * v)[sup == s].sum()))
    q = lambda a: [round(float(v), 1) for v in (np.percentile(a, 5), np.mean(a), np.percentile(a, 95))]  # p5, mean, p95
    prob = chosen / N_MC
    base_x, _, _ = knapsack(value(A, P, C, k, base_rho), A, H)
    sel = base_x > 0.5
    return {"n": N_MC, "max_ls": q(tot_max), "balanced_ls": q(tot_bal),
            "by_supply_max_ls": {SUPPLY_NAMES[s]: q(v) for s, v in by_sup.items()},
            "selection_prob_of_base_cells": {"p_ge_80": round(float((prob[sel] >= 0.8).mean() * 100), 1),
                                             "p_ge_50": round(float((prob[sel] >= 0.5).mean() * 100), 1),
                                             "n_cells": int(sel.sum())},
            "samples_max": [round(v, 2) for v in tot_max]}


# ---------------------------------------------------------------- 2 · duality
def knapsack_duals(A, P, C, k, sup):
    rho = np.array([O.retention(p) for p in P]); v = value(A, P, C, k, rho)
    out = []
    for h in (500, 1000, 2000, 3000, 5000, 10000, 20000, 40000):
        _, tot, lam = knapsack(v, A, h)
        out.append({"ha": h, "ls": round(ls(tot), 1), "lambda_m3_ha": round(lam, 1), "marginal_ls_per_1000ha": round(ls(lam * 1000), 2)})
    per_sup = {}
    for s, name in SUPPLY_NAMES.items():
        idx = np.flatnonzero(sup == s)
        _, _, lam = knapsack(v[idx], A[idx], H / 4)
        per_sup[name] = round(ls(lam * 1000), 2)
    return {"curve": out, "balanced_marginal_ls_per_1000ha": per_sup}


def capacity_duals():
    """Shadow prices of storage at one site: m³ retained per extra m³ of storage, added as
    capacity on the chosen barriers vs as new barriers (more meters, same capacity per meter)."""
    lon, lat = SITE
    out = []
    for mm in (10, 40):
        base = M.optimize(lon, lat, 1500, storm_mm=mm); g = base["_grid"]
        F0 = base["totals"]["retained_m3"]; chosen = set(g["chosen"]); contour = g["contour"]
        # (a) +25 % capacity on the same barriers
        for cd in contour: cd["cap_m3_base"] = cd["cap_m3"]
        for cd in contour: cd["cap_m3"] = cd["cap_m3_base"] * 1.25
        F_cap = M.retained(g["recv"], g["runoff"], contour, chosen)
        for cd in contour: cd["cap_m3"] = cd["cap_m3_base"]
        added_cap = 0.25 * sum(contour[j]["cap_m3"] for j in chosen)
        # (b) same added storage as new barriers: +25 % meters
        more = M.optimize(lon, lat, 1500 * 1.25, storm_mm=mm)
        F_len = more["totals"]["retained_m3"]
        added_len = (more["totals"]["length_m"] - base["totals"]["length_m"]) * M.CAP_M3_PER_M
        sat = base["totals"]["full_barriers"] / max(base["totals"]["n_barriers"], 1)
        out.append({"storm_mm": mm, "F0": F0, "saturated_pct": round(100 * sat, 1),
                    "shadow_capacity": round((F_cap - F0) / max(added_cap, 1e-9), 3),
                    "shadow_meters": round((F_len - F0) / max(added_len, 1e-9), 3),
                    "gain_capacity_m3": round(F_cap - F0), "gain_meters_m3": round(F_len - F0)})
        print("  duals", mm, out[-1])
    return out


# ---------------------------------------------------------------- 3 · Gumbel
def gumbel():
    col = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
    years = list(range(1981, 2026))
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(xy), {"name": n}) for n, xy in GUMBEL_SITES.items()])
    rows = []
    for y in years:  # one request per year keeps Earth Engine under its concurrency limit
        img = col.filterDate(f"{y}-01-01", f"{y + 1}-01-01").max()
        rows += img.sampleRegions(pts, scale=5000).getInfo()["features"]
    out = {}
    for name in GUMBEL_SITES:
        x = np.array([r["properties"]["precipitation"] for r in rows if r["properties"]["name"] == name], float)
        beta = x.std(ddof=1) * math.sqrt(6) / math.pi; mu = x.mean() - 0.5772 * beta
        xt = {T: round(mu - beta * math.log(-math.log(1 - 1 / T)), 1) for T in (2, 5, 10, 25, 50)}
        T40 = 1 / (1 - math.exp(-math.exp(-(40 - mu) / beta)))
        emp = np.sort(x)[::-1]; Temp = (len(x) + 1) / np.arange(1, len(x) + 1)
        out[name] = {"mu": round(mu, 2), "beta": round(beta, 2), "n_years": len(x), "return_levels": xt,
                     "T_40mm": round(T40, 2), "annual_max": [round(v, 1) for v in x],
                     "empirical": [[round(t, 2), round(v, 1)] for t, v in zip(Temp, emp)]}
        print("  gumbel", name, xt, "T(40mm)=", round(T40, 2))
    return out


# ---------------------------------------------------------------- 4 · Pareto
def pareto(A, P, C, k, sup):
    rho = np.array([O.retention(p) for p in P]); v = value(A, P, C, k, rho)
    out = []
    for a in np.linspace(0, 1, 21):
        x = balanced(v, A, sup, H, alpha=a)
        per = np.array([ls((x * v)[sup == s].sum()) for s in sorted(SUPPLY_NAMES)])
        jain = per.sum() ** 2 / (len(per) * (per ** 2).sum())
        out.append({"alpha": round(float(a), 2), "ls": round(float(per.sum()), 2), "jain": round(float(jain), 3),
                    "per_supply": {SUPPLY_NAMES[s]: round(float(p), 2) for s, p in zip(sorted(SUPPLY_NAMES), per)}})
    return out


def _default(o):
    return float(o) if isinstance(o, np.floating) else int(o) if isinstance(o, np.integer) else str(o)


if __name__ == "__main__":
    layers.init()
    out = ROOT / "math.json"
    res = json.loads(out.read_text()) if out.exists() else {}
    save = lambda: out.write_text(json.dumps(res, ensure_ascii=False, default=_default))
    rows, A, P, C, k, sup = cells_arrays()
    for key, fn in (("monte_carlo", lambda: monte_carlo(A, P, C, k, sup)), ("knapsack_duals", lambda: knapsack_duals(A, P, C, k, sup)),
                    ("pareto", lambda: pareto(A, P, C, k, sup)), ("gumbel", gumbel), ("capacity_duals", capacity_duals)):
        if key not in res:      # resumable: each step is saved as soon as it finishes
            res[key] = fn(); save(); print("done", key, flush=True)
    print("wrote math.json")
