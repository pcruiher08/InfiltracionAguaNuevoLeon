"""Soil loss (RUSLE) avoided by the barriers and sediment kept out of the dams.

    .venv/bin/python -W ignore informe/sedimento.py
Writes informe/sedimento.json.

A = R K LS C P  (t/ha/yr). Per 1 km cell, the mean of R K LS0 C over eligible pixels is computed
in Earth Engine with LS0 for a 22.13 m slope length; the slope length, the support-practice
factor P of the barriers, the sediment delivery ratio and the bulk density are sampled by Monte Carlo.
"""
import json
import sys
from pathlib import Path

import ee
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from pipeline import layers, optimize as O  # noqa: E402
from pipeline.config import DATASETS  # noqa: E402
import destino as DS  # noqa: E402
import matematicas as MT  # noqa: E402

N_MC = 4000
RNG = np.random.default_rng(23)
BUDGETS = (3_000, 30_000)
DAMS = (DS.LB, DS.CP)                 # El Cuchillo is excluded: the cells drain to it only through long channels
OC = "OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02"
YEARS = 50


def erosion_image():
    raw = layers.raw()
    P = raw.select("rain_mm")
    # Renard & Freimund (1994): annual rain -> erosivity (MJ mm ha-1 h-1 yr-1)
    R = P.pow(1.61).multiply(0.0483).where(P.gt(850), P.pow(2).multiply(0.004105).subtract(P.multiply(1.219)).add(587.8))
    sand = ee.Image(DATASETS["sand"]).select("b0"); clay = ee.Image(DATASETS["clay"]).select("b0")
    silt = ee.Image(100).subtract(sand).subtract(clay).max(0)
    oc = ee.Image(OC).select("b0").multiply(0.5)                       # % organic carbon (stored as 5 g/kg units)
    sn1 = ee.Image(1).subtract(sand.divide(100))
    # Williams (1995), EPIC: K from sand, silt, clay and organic carbon (t ha h ha-1 MJ-1 mm-1)
    f_cs = ee.Image(0.2).add(ee.Image(0.3).multiply(sand.multiply(-0.0256).multiply(ee.Image(1).subtract(silt.divide(100))).exp()))
    f_clsi = silt.divide(clay.add(silt).max(1)).pow(0.3)
    f_oc = ee.Image(1).subtract(oc.multiply(0.25).divide(oc.add(ee.Image(3.72).subtract(oc.multiply(2.95)).exp())))
    f_hs = ee.Image(1).subtract(sn1.multiply(0.7).divide(sn1.add(ee.Image(-5.51).add(sn1.multiply(22.9)).exp())))
    K = f_cs.multiply(f_clsi).multiply(f_oc).multiply(f_hs).multiply(0.1317)
    # McCool et al. (1987) steepness for slopes >= 9 %; length factor applied later
    th = raw.select("slope_deg").multiply(np.pi / 180)
    S = th.sin().multiply(16.8).subtract(0.5)
    # van der Knijff et al. (2000): cover factor from NDVI
    ndvi = raw.select("ndvi").clamp(0, 0.95)
    Cf = ndvi.multiply(-2).divide(ee.Image(1).subtract(ndvi)).exp()
    return R.multiply(K).multiply(S).multiply(Cf).rename("a0"), K.rename("k"), Cf.rename("cf"), R.rename("r")


def cell_erosion(rows):
    a0, K, Cf, R = erosion_image()
    img = ee.Image.cat([a0, K, Cf, R]).updateMask(DS.eligible())
    out = {}
    for off in range(0, len(rows), 400):
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry(rows[i]["geometry"]), {"i": i}) for i in range(off, min(off + 400, len(rows)))])
        for f in img.reduceRegions(fc, ee.Reducer.mean(), 30).getInfo()["features"]:
            p = f["properties"]; out[p["i"]] = [p.get(b) for b in ("a0", "k", "cf", "r")]
        print("  cells", off, flush=True)
    return out


def main():
    layers.init()
    rows, A, P, C, k, sup = MT.cells_arrays()
    ce = cell_erosion(rows)
    a0 = np.array([ce.get(i, [None])[0] or 0.0 for i in range(len(rows))])
    D = json.loads((ROOT / "destino.json").read_text())
    ratio = {s: D["et"][MT.SUPPLY_NAMES[s]]["ratio"] for s in DS.PHI}
    R = 10 * P * C * A * DS.rho(P)
    dam = np.isin(sup, DAMS)
    # selections: the gross-water one (only its dam cells count) and one that maximizes sediment kept out of the dams
    sel = {f"bruta_{H}": DS.best_first(R * k, A, H) for H in BUDGETS}
    sel.update({f"sedimento_{H}": DS.best_first(np.where(dam, a0 * A, 0.0), A, H) for H in BUDGETS})

    g_dam = {s: [] for s in DAMS}
    res = {key: {"t": [], "m3": [], "water_m3": [], "ratio": []} for key in sel}
    for _ in range(N_MC):
        lam = RNG.uniform(30, 100); Pf = RNG.uniform(0.2, 0.6); sdr = RNG.uniform(0.1, 0.4)
        rho_b = RNG.uniform(1.1, 1.5); rf = RNG.uniform(0.8, 1.2)
        L = (lam / 22.13) ** 0.5
        G = {}
        for s in DAMS:
            e = RNG.uniform(DS.E_MIN, ratio[s]); ph = RNG.uniform(*DS.PHI[s]); ta = RNG.uniform(*DS.TAU[s])
            G[s] = (1 - e) * ph - ta
        g_cell = np.array([G.get(s, 0.0) for s in sup])
        for key, x in sel.items():
            w = x * A * dam
            t = float((w * a0 * rf * L * (1 - Pf) * sdr).sum())             # t/yr kept out of the dams
            m3 = t / rho_b
            water = float((x * R * g_cell * dam).sum())                     # net water change at the dams, m³/yr
            res[key]["t"].append(t); res[key]["m3"].append(m3); res[key]["water_m3"].append(water)
            res[key]["ratio"].append(m3 / max(-water, 1.0))
    q = lambda a: [round(float(np.percentile(a, p)), 0) for p in (5, 50, 95)]
    names = MT.SUPPLY_NAMES
    a_w = lambda m: float(np.average(a0[m], weights=A[m])) if m.any() else 0.0
    out = {"n": N_MC, "years": YEARS, "priors": {"lambda_m": [30, 100], "P": [0.2, 0.6], "SDR": [0.1, 0.4], "bulk_t_m3": [1.1, 1.5], "R_factor": [0.8, 1.2]},
           "erosion_t_ha_yr_lambda22": {names[s]: round(a_w(sup == s), 1) for s in DS.PHI},
           "selections": {}}
    for key, x in sel.items():
        r = res[key]
        out["selections"][key] = {"ha_dams": round(float((x * A * dam).sum())),
                                  "ha_by_dam": {names[s]: round(float((x * A)[sup == s].sum())) for s in DAMS},
                                  "t_yr": q(r["t"]), "m3_yr": q(r["m3"]), "m3_50yr": q(np.array(r["m3"]) * YEARS),
                                  "water_m3_yr": q(r["water_m3"]),
                                  "erosion_t_ha": round(a_w((x > 0) & dam), 1)}
        print(key, out["selections"][key], flush=True)
    (ROOT / "sedimento.json").write_text(json.dumps(out, ensure_ascii=False))
    print("wrote sedimento.json")


if __name__ == "__main__":
    main()
