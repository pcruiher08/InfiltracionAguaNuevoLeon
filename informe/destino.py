"""Probabilistic fate of the water retained by the barriers.

    .venv/bin/python -W ignore informe/destino.py
Writes informe/destino.json (then run informe/vegetacion.py, which adds the INEGI vegetation types).

Retained water R_i infiltrates; a fraction e is lost to evapotranspiration, a fraction
phi_g of the rest reaches supply source g (recharge or delayed baseflow), and a fraction
tau_g of R_i would have reached g anyway as surface runoff without barriers. The net gain
per m³ retained is G_g = (1 - e) * phi_g - tau_g (times k_EC for El Cuchillo).
"""
import json
import sys
from pathlib import Path

import ee
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from pipeline import barriers_mcmf as M, layers, optimize as O  # noqa: E402
import matematicas as MT  # noqa: E402

N_MC = 4000
RNG = np.random.default_rng(11)
SEC_Y = MT.SEC_Y
BUDGETS = (3_000, 30_000)
DEFICIT_LS = 3_000
SC, LB, CP, EC = 3, 1, 2, 4          # supply ids (pipeline.optimize.SUPPLY)
E_MIN = 0.30                         # focused infiltration loses less to ET than diffuse rain
PHI = {SC: (0.5, 0.9), LB: (0.3, 0.8), CP: (0.3, 0.8), EC: (0.3, 0.8)}
TAU = {SC: (0.1, 0.4), LB: (0.3, 0.8), CP: (0.3, 0.8), EC: (0.3, 0.8)}
rho = lambda p: np.interp(p, O.RETENTION_RAIN, O.RETENTION_FRAC)
ls = lambda m3: m3 / SEC_Y * 1000


def eligible():
    raw = layers.raw()
    slope, ndvi = raw.select("slope_deg"), raw.select("ndvi")
    return (slope.gte(8).And(slope.lte(35)).And(ndvi.lt(O.DENSE_NDVI))
            .And(layers.valid_mask()).And(layers.aoi_mask()))


def et_ratio():
    """Mean annual MODIS ET / CHIRPS rain on eligible slopes, per supply catchment (2015–2024)."""
    col = ee.ImageCollection("MODIS/061/MOD16A2GF").select("ET")
    years = [col.filterDate(f"{y}-01-01", f"{y + 1}-01-01").sum().multiply(0.1) for y in range(2015, 2025)]
    et = ee.ImageCollection(years).mean().rename("et")
    rain = layers.raw().select("rain_mm")
    img = et.addBands(rain).updateMask(eligible()).addBands(O.supply_id())
    g = img.reduceRegion(ee.Reducer.mean().repeat(2).group(groupField=2, groupName="supply"),
                         layers.aoi(), 500, maxPixels=1e10, bestEffort=True).get("groups").getInfo()
    return {int(r["supply"]): {"et_mm": round(r["mean"][0]), "rain_mm": round(r["mean"][1]),
                               "ratio": round(r["mean"][0] / r["mean"][1], 3)} for r in g if int(r["supply"]) in PHI}


def best_first(v, A, H):
    order = np.argsort(-v / A); order = order[v[order] > 0]
    x = np.zeros_like(A); used = 0.0
    for i in order:
        if used >= H:
            break
        take = min(A[i], H - used); x[i] = take / A[i]; used += take
    return x


def main():
    layers.init()
    rows, A, P, C, k, sup = MT.cells_arrays()
    Pd = np.array([r["rain_drought_mm"] for r in rows], float)
    ratio = et_ratio(); print("ET/P", ratio, flush=True)
    R = 10 * P * C * A * rho(P)                       # m³/yr retained (before any loss)
    gross = R * k                                     # what the earlier sections call "delivered"
    sids = sorted(PHI)
    is_ec = sup == EC

    # expected net factor per source (uniform priors: mean of each interval)
    def g_mean(s):
        e = (E_MIN + ratio[s]["ratio"]) / 2
        return (1 - e) * np.mean(PHI[s]) - np.mean(TAU[s])
    Gm = np.array([g_mean(s) for s in sup]) * np.where(is_ec, 0.6, 1.0)
    sel = {("bruta", H): best_first(gross, A, H) for H in BUDGETS}
    sel.update({("neta", H): best_first(R * Gm, A, H) for H in BUDGETS})

    draws = {s: [] for s in sids}
    tot = {key: [] for key in sel}; tot_d = {key: [] for key in sel}
    by_sup = {key: {s: [] for s in sids} for key in sel}
    params = []
    for _ in range(N_MC):
        c_f = RNG.uniform(0.7, 1.3); cap = RNG.uniform(0.9, 2.0); bias = RNG.normal(1, 0.1); kec = RNG.uniform(0.4, 0.8)
        G = {}
        th = {}
        for s in sids:
            e = RNG.uniform(E_MIN, max(ratio[s]["ratio"], E_MIN + 0.05))
            ph = RNG.uniform(*PHI[s]); ta = RNG.uniform(*TAU[s])
            G[s] = ((1 - e) * ph - ta) * (kec if s == EC else 1.0)
            draws[s].append(G[s]); th[s] = (e, ph, ta)
        params.append([c_f, cap, bias, kec] + [v for s in sids for v in th[s]])
        g_cell = np.array([G[s] for s in sup])
        Cn = np.clip(C * c_f, 0.02, 0.9); scale = cap / M.CAP_M3_PER_M
        Rn = 10 * P * bias * Cn * A * rho(P * bias) * scale
        Rd = 10 * Pd * bias * Cn * A * rho(Pd * bias) * scale
        for key, x in sel.items():
            net = x * Rn * g_cell
            tot[key].append(ls(net.sum())); tot_d[key].append(ls((x * Rd * g_cell).sum()))
            for s in sids:
                by_sup[key][s].append(ls(net[sup == s].sum()))

    q = lambda a: [round(float(np.percentile(a, p)), 1) for p in (5, 50, 95)]
    names = MT.SUPPLY_NAMES
    out = {"n": N_MC, "e_min": E_MIN, "phi": {names[s]: PHI[s] for s in sids}, "tau": {names[s]: TAU[s] for s in sids},
           "et": {names[s]: ratio[s] for s in sids},
           "factor": {names[s]: {"mean": round(float(np.mean(draws[s])), 3), "q": [round(float(np.percentile(draws[s], p)), 3) for p in (5, 50, 95)],
                                 "p_pos": round(100 * float(np.mean(np.array(draws[s]) > 0)), 1)} for s in sids},
           "factor_samples": {names[s]: [round(v, 3) for v in draws[s][:1500]] for s in sids},
           "selections": {}}
    for (kind, H), x in sel.items():
        t = np.array(tot[(kind, H)]); td = np.array(tot_d[(kind, H)])
        out["selections"][f"{kind}_{H}"] = {
            "ha": H, "gross_ls": round(ls((x * gross).sum()), 1), "net_ls": q(t), "net_mean": round(float(t.mean()), 1),
            "net_drought_ls": q(td), "p_pos": round(100 * float((t > 0).mean()), 1),
            "p_half": round(100 * float((t >= 0.5 * ls((x * gross).sum())).mean()), 1),
            "p_deficit_5": round(100 * float((td >= 0.05 * DEFICIT_LS).mean()), 1),
            "p_deficit_10": round(100 * float((td >= 0.10 * DEFICIT_LS).mean()), 1),
            "ha_by_supply": {names[s]: round(float((x * A)[sup == s].sum())) for s in sids},
            "by_supply": {names[s]: q(by_sup[(kind, H)][s]) for s in sids},
            "samples": [round(v, 1) for v in t[:2000]]}
        print(kind, H, out["selections"][f"{kind}_{H}"]["gross_ls"], q(t), out["selections"][f"{kind}_{H}"]["p_pos"], flush=True)

    # Spearman rank correlation of the 30,000 ha (gross selection) net total with each parameter
    Pm = np.array(params); y = np.array(tot[("bruta", 30_000)])
    labels = ["f_C", "kappa", "b", "k_EC"] + [f"{p}_{names[s]}" for s in sids for p in ("e", "phi", "tau")]
    rk = lambda a: np.argsort(np.argsort(a))
    out["spearman"] = sorted(([lab, round(float(np.corrcoef(rk(Pm[:, j]), rk(y))[0, 1]), 3)] for j, lab in enumerate(labels)),
                             key=lambda r: -abs(r[1]))

    # optimistic priors: how robust is the sign of G_g?
    opt = {"phi_dam": (0.6, 0.95), "tau_dam": (0.1, 0.5), "phi_sc": (0.7, 0.95), "tau_sc": (0.0, 0.2), "e_min": 0.2}
    rng = np.random.default_rng(5); n = 200_000; out["optimista"] = opt; out["factor_optimista"] = {}
    for s in sids:
        dam = s != SC
        e = rng.uniform(opt["e_min"], ratio[s]["ratio"], n)
        G = (1 - e) * rng.uniform(*opt["phi_dam" if dam else "phi_sc"], n) - rng.uniform(*opt["tau_dam" if dam else "tau_sc"], n)
        G = G * (rng.uniform(0.4, 0.8, n) if s == EC else 1)
        out["factor_optimista"][names[s]] = {"mean": round(float(G.mean()), 3), "p_pos": round(100 * float((G > 0).mean()), 1)}
    (ROOT / "destino.json").write_text(json.dumps(out, ensure_ascii=False))
    print("wrote destino.json")


if __name__ == "__main__":
    main()
