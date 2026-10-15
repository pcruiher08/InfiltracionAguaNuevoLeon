"""Protected areas over the selected cells, and future frequency of a 2021-2022 drought (NEX-GDDP-CMIP6).

    .venv/bin/python -W ignore informe/clima.py
Writes informe/clima.json.

Drought: the July 2021 - June 2022 rain on the study area is placed as a percentile q* of the CHIRPS
July-June totals (1981-2025). For each model, the threshold is its own historical (1985-2014) q* quantile,
which removes the model's bias; the future frequency is the share of July-June years (2041-2070) below it.
"""
import json
import sys
from pathlib import Path

import ee
import numpy as np
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from pipeline import layers  # noqa: E402
import destino as DS  # noqa: E402
import matematicas as MT  # noqa: E402

MODELS = ["ACCESS-CM2", "CanESM5", "EC-Earth3", "GFDL-ESM4", "IPSL-CM6A-LR", "MPI-ESM1-2-HR", "MRI-ESM2-0", "NorESM2-MM"]
HIST, FUT = (1985, 2014), (2041, 2070)


def hydro_year_totals(col, years, scale, factor=1.0):
    """AOI-mean July-June rain totals (mm) for July of each year in `years`."""
    aoi = layers.aoi()
    def one(y):
        y = ee.Number(y); s = ee.Date.fromYMD(y, 7, 1)
        tot = col.filterDate(s, s.advance(1, "year")).sum().multiply(factor)
        return ee.Feature(None, {"y": y, "p": tot.reduceRegion(ee.Reducer.mean(), aoi, scale, bestEffort=True).values().get(0)})
    fc = ee.FeatureCollection(ee.List(list(years)).map(one))
    return dict(zip(fc.aggregate_array("y").getInfo(), fc.aggregate_array("p").getInfo()))


def protected(rows, sel):
    fc = ee.FeatureCollection("WCMC/WDPA/current/polygons").filterBounds(layers.aoi())
    feats = fc.map(lambda f: f.simplify(100)).getInfo()["features"]
    parks = [(f["properties"]["NAME"], f["properties"]["DESIG"], shape(f["geometry"]).buffer(0)) for f in feats]
    out = {}
    for key, x in sel.items():
        ha = {}
        for i in np.flatnonzero(x > 0):
            cell = shape(rows[i]["geometry"])
            for name, desig, g in parks:
                if g.intersects(cell):
                    frac = g.intersection(cell).area / cell.area
                    ha[f"{name} ({desig})"] = ha.get(f"{name} ({desig})", 0) + frac * x[i] * rows[i]["eligible_ha"]
        out[key] = {k: round(v) for k, v in sorted(ha.items(), key=lambda kv: -kv[1]) if v >= 1}
    sites = json.loads((ROOT.parent / "docs" / "data" / "sites.json").read_text())
    from shapely.geometry import Point
    cumbres = [g for name, _, g in parks if name == "Cumbres de Monterrey"][0]
    out["sitios_en_cumbres"] = [i + 1 for i, s in enumerate(sites) if cumbres.contains(Point(s["lon"], s["lat"]))]
    return out


def main():
    layers.init()
    rows, A, P, C, k, sup = MT.cells_arrays()
    D = json.loads((ROOT / "destino.json").read_text())
    ratio = {s: D["et"][MT.SUPPLY_NAMES[s]]["ratio"] for s in DS.PHI}
    R = 10 * P * C * A * DS.rho(P)
    Gm = np.array([((1 - (DS.E_MIN + ratio[s]) / 2) * np.mean(DS.PHI[s]) - np.mean(DS.TAU[s])) for s in sup]) * np.where(sup == DS.EC, 0.6, 1.0)
    sel = {f"bruta_{H}": DS.best_first(R * k, A, H) for H in DS.BUDGETS}
    sel.update({f"neta_{H}": DS.best_first(R * Gm, A, H) for H in DS.BUDGETS})
    out = {"protegidas": protected(rows, sel)}
    print("protected", out["protegidas"], flush=True)

    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
    obs = hydro_year_totals(chirps, range(1981, 2025), 5000)
    p2021 = obs[2021]; vals = np.array([v for y, v in obs.items()])
    q_star = float((vals <= p2021).mean())
    out["chirps"] = {"p_2021_22": round(p2021), "mean": round(float(vals.mean())), "q_star": round(q_star, 3)}
    print("chirps", out["chirps"], flush=True)

    cmip = ee.ImageCollection("NASA/GDDP-CMIP6").select("pr")
    out["models"] = {}
    for m in MODELS:
        h = hydro_year_totals(cmip.filter(ee.Filter.eq("model", m)).filter(ee.Filter.eq("scenario", "historical")),
                              range(HIST[0], HIST[1] + 1), 25000, 86400)
        hv = np.array(list(h.values())); thr = float(np.quantile(hv, q_star))
        res = {"hist_mean": round(float(hv.mean())), "threshold": round(thr), "hist_freq": round(float((hv <= thr).mean()), 3)}
        for sc in ("ssp245", "ssp585"):
            f = hydro_year_totals(cmip.filter(ee.Filter.eq("model", m)).filter(ee.Filter.eq("scenario", sc)),
                                  range(FUT[0], FUT[1] + 1), 25000, 86400)
            fv = np.array(list(f.values()))
            res[sc] = {"mean_change_pct": round(100 * (fv.mean() / hv.mean() - 1), 1), "freq": round(float((fv <= thr).mean()), 3)}
        out["models"][m] = res
        print(m, res, flush=True)
    for sc in ("ssp245", "ssp585"):
        ch = np.array([r[sc]["mean_change_pct"] for r in out["models"].values()])
        fr = np.array([r[sc]["freq"] for r in out["models"].values()])
        # gross water of the 3,000 ha selection with the rain scaled by the ensemble-median change
        x = sel["bruta_3000"]; s = 1 + np.median(ch) / 100
        g0 = (x * R * k).sum(); g1 = (x * 10 * P * s * C * A * DS.rho(P * s) * k).sum()
        out[sc] = {"change_median": round(float(np.median(ch)), 1), "change_range": [round(float(ch.min()), 1), round(float(ch.max()), 1)],
                   "freq_median": round(float(np.median(fr)), 3), "freq_range": [round(float(fr.min()), 3), round(float(fr.max()), 3)],
                   "models_more_droughts": int(sum(r[sc]["freq"] > r["hist_freq"] for r in out["models"].values())), "gross_change_pct": round(100 * (g1 / g0 - 1), 1)}
    out["q_star"] = q_star; out["n_models"] = len(MODELS)
    (ROOT / "clima.json").write_text(json.dumps(out, ensure_ascii=False))
    print("ensemble", out["ssp245"], out["ssp585"])


if __name__ == "__main__":
    main()
