"""Two estimates of e, the fraction of the water infiltrated behind the barriers that returns to the atmosphere.

    .venv/bin/python -W ignore informe/evapotranspiracion.py
Writes informe/evapotranspiracion.json.

(1) Satellite ensemble: mean annual actual evapotranspiration over rain on the eligible slopes of each supply
    catchment, 2015-2023, from four products (MODIS MOD16A2GF, PML, TerraClimate, FLDAS). This is the share of
    ordinary, diffuse rain that evaporates: an upper bound for e, since ponded water infiltrates deeper.
(2) Daily soil-water budget of the zone behind a barrier whose roots reach the infiltrated water (3 to 15 m:
    the ponded strip plus neighbouring and planted vegetation), driven by CHIRPS daily rain and
    TerraClimate potential evapotranspiration for the Santa Catarina selection. The strip receives its own rain
    plus the runoff retained by the barrier; water above the root-zone storage drains below the roots, and actual
    evapotranspiration is Kc · PET · S / Smax. The model is run with and without the retained runoff, and
        e = (ET with barrier - ET without barrier) / retained runoff
    is the share of the extra water that evaporates. Root-zone storage, crop coefficient, capacity per metre,
    runoff coefficient and drained area per metre are sampled by Monte Carlo.
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
import destino as DS  # noqa: E402
import matematicas as MT  # noqa: E402

Y0, Y1 = 2015, 2023
STRIP_M = 3.0                     # ponded strip width (m)
ROOT_W = (3.0, 15.0)              # width (m) of the vegetation whose roots reach the water drained below the strip
N_MC = 400
RNG = np.random.default_rng(29)
SC = "Acuífero Santa Catarina (pozos SADM)"


def annual(col, band, scale, kind):
    """Mean annual total (mm) of a collection; kind: 'sum' of composites or 'monthly_rate' (kg m-2 s-1)."""
    imgs = []
    for y in range(Y0, Y1 + 1):
        c = col.filterDate(f"{y}-01-01", f"{y + 1}-01-01").select(band)
        if kind == "sum":
            imgs.append(c.sum().multiply(scale))
        elif kind == "mean_rate":                     # mm/day averaged over the year
            imgs.append(c.mean().multiply(365 * scale))
        else:                                         # monthly mean flux in kg m-2 s-1
            imgs.append(c.sum().multiply(86400 * 30.44 * scale))
    return ee.ImageCollection(imgs).mean()


def satellite_ratios():
    pml_et = ee.ImageCollection("projects/pml_evapotranspiration/PML/OUTPUT/PML_V22a").select("ET")   # 8-day, 0.01 mm/day
    products = {
        "MODIS MOD16A2GF": annual(ee.ImageCollection("MODIS/061/MOD16A2GF"), "ET", 0.1, "sum"),
        "PML": annual(pml_et, "ET", 0.01, "mean_rate"),
        "TerraClimate": annual(ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE"), "aet", 0.1, "sum"),
        "FLDAS": annual(ee.ImageCollection("NASA/FLDAS/NOAH01/C/GL/M/V001"), "Evap_tavg", 1.0, "flux"),
    }
    rain = annual(ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY"), "precipitation", 1.0, "sum").rename("rain")
    elig = DS.eligible()
    img = ee.Image.cat([v.rename(k.split()[0]) for k, v in products.items()] + [rain]).updateMask(elig).addBands(O.supply_id())
    names = [k.split()[0] for k in products] + ["rain"]
    g = img.reduceRegion(ee.Reducer.mean().repeat(len(names)).group(groupField=len(names), groupName="supply"),
                         layers.aoi(), 1000, maxPixels=1e10, bestEffort=True).get("groups").getInfo()
    out = {}
    for r in g:
        sid = int(r["supply"])
        if sid not in DS.PHI:
            continue
        vals = dict(zip(names, r["mean"]))
        out[MT.SUPPLY_NAMES[sid]] = {"rain_mm": round(vals["rain"]),
                                     **{k: round(vals[k.split()[0]] / vals["rain"], 3) for k in products}}
    return out, list(products)


def daily_series():
    geom = layers.catchments()["santa_catarina"].geometry()
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(f"{Y0}-01-01", f"{Y1 + 1}-01-01").select("precipitation")
    fc = chirps.map(lambda i: ee.Feature(None, {"t": i.date().format("YYYY-MM-dd"),
                                               "p": i.reduceRegion(ee.Reducer.mean(), geom, 5000).get("precipitation")}))
    days = fc.aggregate_array("t").getInfo(); p = np.array(fc.aggregate_array("p").getInfo(), float)
    tc = ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE").filterDate(f"{Y0}-01-01", f"{Y1 + 1}-01-01").select("pet")
    fm = tc.map(lambda i: ee.Feature(None, {"m": i.date().format("YYYY-MM"),
                                           "pet": i.reduceRegion(ee.Reducer.mean(), geom, 4000).get("pet")}))
    pet_m = dict(zip(fm.aggregate_array("m").getInfo(), fm.aggregate_array("pet").getInfo()))
    import calendar
    pet = np.array([pet_m[d[:7]] * 0.1 / calendar.monthrange(int(d[:4]), int(d[5:7]))[1] for d in days])
    return days, p, pet


def bucket(p, pet, runon_mm, smax, kc):
    """Daily root-zone budget of the strip; returns total ET and drainage (mm over the strip)."""
    s = 0.5 * smax; et_tot = dr_tot = 0.0
    for pi, ei, ri in zip(p, pet, runon_mm):
        s += pi + ri
        if s > smax:
            dr_tot += s - smax; s = smax
        et = min(s, kc * ei * s / smax); s -= et; et_tot += et
    return et_tot, dr_tot


def main():
    layers.init()
    ratios, products = satellite_ratios()
    print("ratios", ratios, flush=True)
    days, p, pet = daily_series()
    print("days", len(days), "rain/yr", round(p.sum() / (Y1 - Y0 + 1)), "pet/yr", round(pet.sum() / (Y1 - Y0 + 1)), flush=True)
    rows, A, P, C, k, sup = MT.cells_arrays()
    sel = sup == 3
    c_sc = float(np.average(C[sel], weights=A[sel]))
    # hillslope area (m²) whose runoff reaches each metre of barrier in the field treatment (informe/campo.py)
    area_m = np.array([v["area_m2_per_m"] for v in json.loads((ROOT / "campo.json").read_text())["sites"].values()])
    es, drs = [], []
    for _ in range(N_MC):
        smax = RNG.uniform(50, 400); kc = RNG.uniform(0.6, 1.1); cap = RNG.uniform(0.9, 2.0); w = RNG.uniform(*ROOT_W)
        c = c_sc * RNG.uniform(0.7, 1.3); am = RNG.choice(area_m)
        runon_m3 = np.minimum(cap, p / 1000 * c * am)                  # m³ per metre retained by the barrier each day
        runon = runon_m3 * 1000 / w                                     # mm over the area the roots reach
        et1, dr1 = bucket(p, pet, runon, smax, kc)
        et0, dr0 = bucket(p, pet, np.zeros_like(p), smax, kc)
        e = (et1 - et0) / runon.sum()
        es.append(e); drs.append((dr1 - dr0) / runon.sum())
    es = np.array(es)
    out = {"years": [Y0, Y1], "products": products, "ratios": ratios,
           "climate": {"rain_mm_yr": round(float(p.sum() / (Y1 - Y0 + 1))), "pet_mm_yr": round(float(pet.sum() / (Y1 - Y0 + 1)))},
           "bucket": {"n": N_MC, "c_sc": round(c_sc, 3), "area_m2_per_m": round(float(area_m.mean()), 1),
                      "smax_mm": [50, 400], "kc": [0.6, 1.1], "root_width_m": list(ROOT_W),
                      "e": [round(float(np.percentile(es, 5)), 3), round(float(es.mean()), 3), round(float(np.percentile(es, 95)), 3)],
                      "e_samples": [round(float(v), 4) for v in es]}}
    # net gain in the Santa Catarina basin with e from the strip model instead of U(0.3, ET/P)
    D = json.loads((ROOT / "destino.json").read_text())
    n = 200_000
    e_s = RNG.choice(es, n); ph = RNG.uniform(*D["phi"][SC], n); ta = RNG.uniform(*D["tau"][SC], n)
    G = (1 - e_s) * ph - ta
    ph_k = RNG.uniform(0.2, 0.9, n); G_k = (1 - e_s) * ph_k - ta
    # lateral interflow and epikarst uptake: a share of the water drained below the strip moves downslope within the
    # rooting zone and evaporates like ordinary rain (satellite ET/P of the basin, excluding values above 1)
    sat = [v for k_, v in ratios[SC].items() if k_ != "rain_mm" and v <= 1]
    iota = RNG.uniform(0.2, 0.6, n); rr = RNG.uniform(min(sat), max(sat), n)
    e_i = e_s + (1 - e_s) * iota * rr
    G_i = (1 - e_i) * ph - ta
    gross = D["selections"]["neta_30000"]["gross_ls"]; w0 = D["selections"]["neta_30000"]["net_mean"]
    g_prior = D["factor"][SC]["mean"]
    out["net"] = {"g_mean": round(float(G.mean()), 3), "p_pos": round(100 * float((G > 0).mean()), 1),
                  "net_ls_30000": round(float(w0 * G.mean() / g_prior), 1),
                  "karst_g_mean": round(float(G_k.mean()), 3), "karst_p_pos": round(100 * float((G_k > 0).mean()), 1),
                  "karst_net_ls_30000": round(float(w0 * G_k.mean() / g_prior), 1),
                  "interflow_e": round(float(e_i.mean()), 3), "interflow_g_mean": round(float(G_i.mean()), 3),
                  "interflow_p_pos": round(100 * float((G_i > 0).mean()), 1),
                  "interflow_net_ls_30000": round(float(w0 * G_i.mean() / g_prior), 1)}
    # cost competitiveness with El Cuchillo II (2.9 M pesos per L/s of capital): G needed per cost per hectare
    R_ha = gross * 31_536_000 / 1000 / 30_000
    need = {c: c * 31_536 / (14_680e6 / 5_000) / R_ha for c in (25_000, 50_000)}
    out["net"]["p_competitive"] = {str(c): round(100 * float((G >= g).mean()), 1) for c, g in need.items()}
    out["net"]["g_needed"] = {str(c): round(g, 2) for c, g in need.items()}
    cost_mean = 37_500 * 30_000
    out["net"]["mxn_per_net_ls"] = round(cost_mean / out["net"]["net_ls_30000"])
    (ROOT / "evapotranspiracion.json").write_text(json.dumps(out, ensure_ascii=False))
    print(json.dumps({k: v for k, v in out.items() if k != "bucket"}, ensure_ascii=False, indent=1))
    print("bucket e", out["bucket"]["e"], "c_sc", out["bucket"]["c_sc"])


if __name__ == "__main__":
    main()
