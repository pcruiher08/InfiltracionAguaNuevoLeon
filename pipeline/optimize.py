"""Choose where to restore to maximize water retained for each supply source.

Candidates are 1 km cells over the supply catchments. For each cell:

    retained m³/yr  = rain × runoff coefficient × eligible area × RETENTION
    delivered m³/yr = retained × connectivity tier (1.0 direct, 0.6 El Cuchillo)

Eligible area = slope 8–35°, not urban/water, not dense cover (NDVI < 0.55):
where barriers or trenches can be built. Given a budget of hectares, cells
are taken by delivered m³ per hectare (fractional-knapsack greedy, which is
optimal when each cell can be partially treated).

These m³ are an ORDER-OF-MAGNITUDE estimate to rank options, not a water
balance: the runoff coefficient is a simple slope/cover rule and RETENTION
comes from the barrier optimizer's typical result (~40 % retained).
"""
import ee

from pipeline import layers
from pipeline.config import CONNECTIVITY_TIERS

CELL_M = 1000
MIN_ELIGIBLE_HA = 15     # ignore slivers
RETENTION = 0.40         # share of runoff retained by contour barriers (barriers.py: 41–43 %)
DENSE_NDVI = 0.55
SUPPLY = {  # paint order: El Cuchillo first so nested catchments keep their own id
    "el_cuchillo": (4, "Presa El Cuchillo"),
    "cerro_prieto": (2, "Presa Cerro Prieto"),
    "santa_catarina": (3, "Acuífero Santa Catarina (pozos SADM)"),
    "la_boca": (1, "Presa La Boca"),
}
_cache = {}


def runoff_coefficient(slope, ndvi):
    """Simple rational-method style C: steeper and barer → more runoff (0.05–0.75)."""
    bare = ee.Image(1).subtract(ndvi.subtract(0.1).divide(0.6).clamp(0, 1))
    return slope.divide(35).clamp(0, 1).multiply(0.35).add(bare.multiply(0.35)).add(0.05)


def supply_id():
    img = ee.Image(0)
    cats = layers.catchments()
    for key, (sid, _) in SUPPLY.items():
        img = img.paint(cats[key], sid)
    return img.rename("supply")


def cell_table():
    """One row per 1 km cell with eligible ha, rain, C, priority, connectivity, supply id."""
    if "cells" in _cache:
        return _cache["cells"]
    raw = layers.raw()
    slope, ndvi = raw.select("slope_deg"), raw.select("ndvi")
    eligible = (slope.gte(8).And(slope.lte(35)).And(ndvi.lt(DENSE_NDVI))
                .And(layers.valid_mask()).And(layers.aoi_mask()))
    c = runoff_coefficient(slope, ndvi)
    img = ee.Image.cat([
        ee.Image.pixelArea().divide(1e4).updateMask(eligible).rename("eligible_ha"),
        c.updateMask(eligible).rename("c"),
        raw.select("rain_mm").updateMask(eligible).rename("rain_mm"),
        layers.priority_index().updateMask(eligible).rename("priority"),
        layers.connectivity().updateMask(eligible).rename("connectivity"),
    ])
    grid = layers.aoi().coveringGrid(ee.Projection("EPSG:32614").atScale(CELL_M))
    fc = img.reduceRegions(grid, ee.Reducer.sum().combine(ee.Reducer.mean(), sharedInputs=True), 90)
    fc = fc.filter(ee.Filter.gte("eligible_ha_sum", MIN_ELIGIBLE_HA))
    fc = supply_id().reduceRegions(fc, ee.Reducer.mode().setOutputs(["supply"]), 90)
    fc = fc.map(lambda f: f.transform("EPSG:4326", 1))  # grid cells come back in UTM
    # Fetch in pages to stay under getInfo's 5,000-element cap
    n = fc.size().getInfo()
    feats = []
    for off in range(0, n, 2000):
        feats += ee.FeatureCollection(fc.toList(2000, off)).getInfo()["features"]
    rows = []
    for f in feats:
        p = f["properties"]
        ha = p.get("eligible_ha_sum") or 0
        sid = p.get("supply")
        if ha < MIN_ELIGIBLE_HA or not sid or p.get("c_mean") is None:
            continue
        ring = f["geometry"]["coordinates"][0]
        lon = sum(x for x, _ in ring[:-1]) / (len(ring) - 1)
        lat = sum(y for _, y in ring[:-1]) / (len(ring) - 1)
        tier = p.get("connectivity_mean") or 0
        retained = p["rain_mm_mean"] / 1000 * p["c_mean"] * ha * 1e4 * RETENTION
        rows.append({
            "lon": round(lon, 5), "lat": round(lat, 5), "geometry": f["geometry"],
            "supply": int(sid), "eligible_ha": round(ha, 1), "c": round(p["c_mean"], 3),
            "rain_mm": round(p["rain_mm_mean"]), "priority": round(p.get("priority_mean") or 0, 3),
            "connectivity": round(tier, 2), "retained_m3": round(retained),
            "delivered_m3": round(retained * tier),
        })
    _cache["cells"] = rows
    return rows


def _greedy(cells, budget_ha, names):
    chosen, used = [], 0.0
    for r in cells:
        if used >= budget_ha:
            break
        take = min(r["eligible_ha"], budget_ha - used)
        frac = take / r["eligible_ha"]
        chosen.append({**r, "treated_ha": round(take, 1),
                       "delivered_m3": round(r["delivered_m3"] * frac), "supply_name": names[r["supply"]]})
        used += take
    return chosen, used


def optimize(budget_ha=3000, mode="max"):
    """mode 'max': greedy by delivered m³/ha over all cells (pure optimum).
    mode 'balanced': budget split equally among supply sources, greedy within each."""
    cells = sorted(cell_table(), key=lambda r: -r["delivered_m3"] / r["eligible_ha"])
    names = {sid: name for sid, name in SUPPLY.values()}
    if mode == "balanced":
        sids = sorted({r["supply"] for r in cells})
        chosen, used = [], 0.0
        for sid in sids:
            c, u = _greedy([r for r in cells if r["supply"] == sid], budget_ha / len(sids), names)
            chosen += c; used += u
        chosen.sort(key=lambda r: -r["delivered_m3"] / r["treated_ha"])
    else:
        chosen, used = _greedy(cells, budget_ha, names)
    for i, r in enumerate(chosen, 1):
        r["rank"] = i
    by_supply = {}
    for r in chosen:
        s = by_supply.setdefault(r["supply_name"], {"cells": 0, "ha": 0.0, "m3": 0})
        s["cells"] += 1; s["ha"] += r["treated_ha"]; s["m3"] += r["delivered_m3"]
    # Diminishing-returns curve: m³ delivered vs hectares treated
    curve, acc_ha, acc_m3 = [], 0.0, 0
    for r in cells:
        acc_ha += r["eligible_ha"]; acc_m3 += r["delivered_m3"]
        curve.append((acc_ha, acc_m3))
    marks = [500, 1000, 2000, 3000, 5000, 10000, 20000, 50000]
    curve_pts = [{"ha": m, "m3": next((v for h, v in curve if h >= m), curve[-1][1])} for m in marks if m <= curve[-1][0]]
    return {
        "budget_ha": budget_ha, "mode": mode,
        "totals": {"cells": len(chosen), "ha": round(used), "m3_per_year": sum(r["delivered_m3"] for r in chosen),
                   "candidates": len(cells), "eligible_ha_total": round(sum(r["eligible_ha"] for r in cells))},
        "by_supply": {k: {**v, "ha": round(v["ha"])} for k, v in by_supply.items()},
        "curve": curve_pts,
        "cells": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": r["geometry"],
             "properties": {k: v for k, v in r.items() if k != "geometry"}} for r in chosen]},
        "assumptions": [
            "m³/año = lluvia media × coeficiente de escurrimiento × hectáreas elegibles × 40 % retenido × conexión con abasto.",
            "Coeficiente de escurrimiento: 0.05 + 0.35·(pendiente/35°) + 0.35·(suelo desnudo); regla simple, no calibrada.",
            "40 % retenido sale del optimizador de barreras (41–43 % en sitios de prueba).",
            "Conexión: 1.0 si drena directo a La Boca, Cerro Prieto o Santa Catarina; 0.6 en el resto de El Cuchillo.",
            "Es una estimación de orden de magnitud para comparar opciones, no un balance hídrico.",
        ],
    }
