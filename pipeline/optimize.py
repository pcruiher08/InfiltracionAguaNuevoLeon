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
# Annual share of runoff retained by contour barriers, by rainfall regime.
# From the min-cost-flow barrier model (storage + infiltration during the event,
# 1,500 m in a 1.2 km window): ~29 % of a 5 mm storm, 15 % of 10 mm, 7.5 % of 20 mm,
# 3.8 % of 40 mm; weighted by each site's CHIRPS daily rain 2019–2026. Wetter
# catchments get more of their rain in large storms that overflow the barriers.
RETENTION_RAIN = (420, 640, 1190)
RETENTION_FRAC = (0.160, 0.130, 0.078)


def retention(rain_mm):
    import numpy as np
    return float(np.interp(rain_mm, RETENTION_RAIN, RETENTION_FRAC))
# Expected net gain of each supply source per m³ retained (E[(1 - e)·phi - tau], times k for El
# Cuchillo), from the probabilistic analysis in informe/destino.py: retention in the dam catchments
# mostly holds back runoff that already reached the reservoir, so its expected net gain is negative.
NET_FACTOR = {1: -0.303, 2: -0.354, 3: 0.067, 4: -0.196}
NET_P_POS = {1: 4.7, 2: 3.9, 3: 66.9, 4: 3.6}  # % probability that the source gains water
DENSE_NDVI = 0.55
SECONDS_YEAR = 31_536_000
ZMM_DEMAND_LS = 16_500          # regular consumption (deck: 13,500 available vs 16,500 L/s in 2022)
ZMM_DAY_M3 = ZMM_DEMAND_LS / 1000 * 86_400
DROUGHT = ("2021-07-01", "2022-07-01")  # 12 months leading to the 2022 crisis
DROUGHT_LABEL = "jul 2021–jun 2022 (antes de la crisis de 2022)"
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
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(*DROUGHT).sum()
          .updateMask(eligible).rename("rain_drought"),
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
        retained = p["rain_mm_mean"] / 1000 * p["c_mean"] * ha * 1e4 * retention(p["rain_mm_mean"])
        rain_d = p.get("rain_drought_mean") or p["rain_mm_mean"]
        retained_d = rain_d / 1000 * p["c_mean"] * ha * 1e4 * retention(rain_d)
        rows.append({
            "lon": round(lon, 5), "lat": round(lat, 5), "geometry": f["geometry"],
            "supply": int(sid), "eligible_ha": round(ha, 1), "c": round(p["c_mean"], 3),
            "rain_mm": round(p["rain_mm_mean"]), "priority": round(p.get("priority_mean") or 0, 3),
            "connectivity": round(tier, 2), "retained_m3": round(retained),
            "delivered_m3": round(retained * tier),
            "net_m3": round(retained * NET_FACTOR[int(sid)]),
            "rain_drought_mm": round(rain_d),
            "delivered_drought_m3": round(retained_d * tier),
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
        chosen.append({**r, "treated_ha": round(take, 1), "delivered_m3": round(r["delivered_m3"] * frac),
                       "net_m3": round(r["net_m3"] * frac),
                       "delivered_drought_m3": round(r["delivered_drought_m3"] * frac),
                       "supply_name": names[r["supply"]]})
        used += take
    return chosen, used


def ls(m3_year):
    return round(m3_year / SECONDS_YEAR * 1000, 1)


def drought_check(chosen, mode, budget_ha):
    """Same selection under drought-year rain, and how stable the selection is
    if we re-optimize with drought rain instead of the long-term mean."""
    m3_d = sum(r["delivered_drought_m3"] for r in chosen)
    m3_n = sum(r["delivered_m3"] for r in chosen)
    ranked = sorted(cell_table(), key=lambda r: -r["delivered_drought_m3"] / r["eligible_ha"])
    names = {sid: name for sid, name in SUPPLY.values()}
    if mode == "balanced":
        sids = sorted({r["supply"] for r in ranked})
        alt = [c for sid in sids for c in _greedy([r for r in ranked if r["supply"] == sid], budget_ha / len(sids), names)[0]]
    else:
        alt, _ = _greedy(ranked, budget_ha, names)
    key = lambda r: (r["lon"], r["lat"])
    ha_sel = {key(r): r["treated_ha"] for r in chosen}
    overlap = sum(min(ha_sel.get(key(r), 0), r["treated_ha"]) for r in alt)
    return {"period": DROUGHT_LABEL, "m3_per_year": m3_d, "ls": ls(m3_d),
            "pct_of_normal": round(100 * m3_d / max(m3_n, 1)),
            "selection_overlap_pct": round(100 * overlap / max(budget_ha, 1))}


def for_target(target_ls):
    """Inverse question: hectares (max-water order) needed to deliver target L/s."""
    need = target_ls / 1000 * SECONDS_YEAR
    acc_ha = acc_m3 = 0
    for r in sorted(cell_table(), key=lambda r: -r["delivered_m3"] / r["eligible_ha"]):
        if acc_m3 + r["delivered_m3"] >= need:
            acc_ha += r["eligible_ha"] * (need - acc_m3) / r["delivered_m3"]
            return {"target_ls": target_ls, "ha": round(acc_ha), "reachable": True}
        acc_ha += r["eligible_ha"]; acc_m3 += r["delivered_m3"]
    return {"target_ls": target_ls, "ha": round(acc_ha), "reachable": False, "max_ls": ls(acc_m3)}


def optimize(budget_ha=3000, mode="max", target_ls=None):
    if target_ls:
        budget_ha = for_target(target_ls)["ha"]
    """mode 'max': greedy by gross delivered m³/ha over all cells (pure optimum).
    mode 'balanced': budget split equally among supply sources, greedy within each.
    mode 'net': greedy by expected net gain per ha, only cells with a positive expected gain."""
    cells = sorted(cell_table(), key=lambda r: -r["delivered_m3"] / r["eligible_ha"])
    if mode == "net":
        cells = sorted((r for r in cell_table() if r["net_m3"] > 0), key=lambda r: -r["net_m3"] / r["eligible_ha"])
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
        s = by_supply.setdefault(r["supply_name"], {"cells": 0, "ha": 0.0, "m3": 0, "net_m3": 0, "p_pos": NET_P_POS[r["supply"]]})
        s["cells"] += 1; s["ha"] += r["treated_ha"]; s["m3"] += r["delivered_m3"]; s["net_m3"] += r["net_m3"]
    # Diminishing-returns curve: m³ delivered vs hectares treated
    curve, acc_ha, acc_m3 = [], 0.0, 0
    key = "net_m3" if mode == "net" else "delivered_m3"
    for r in cells:
        acc_ha += r["eligible_ha"]; acc_m3 += r[key]
        curve.append((acc_ha, acc_m3))
    marks = [500, 1000, 2000, 3000, 5000, 10000, 20000, 50000]
    curve_pts = [{"ha": m, "m3": next((v for h, v in curve if h >= m), curve[-1][1])} for m in marks if m <= curve[-1][0]]
    m3 = sum(r["delivered_m3"] for r in chosen)
    net = sum(r["net_m3"] for r in chosen)
    return {
        "budget_ha": budget_ha, "mode": mode, "target": for_target(target_ls) if target_ls else None,
        "impact": {"ls": ls(m3), "pct_zmm_demand": round(100 * ls(m3) / ZMM_DEMAND_LS, 2),
                   "days_of_zmm_supply": round(m3 / ZMM_DAY_M3, 1), "zmm_demand_ls": ZMM_DEMAND_LS,
                   "net_ls": ls(net)},
        "drought": drought_check(chosen, mode, budget_ha),
        "totals": {"cells": len(chosen), "ha": round(used), "m3_per_year": m3,
                   "candidates": len(cells), "eligible_ha_total": round(sum(r["eligible_ha"] for r in cells))},
        "by_supply": {k: {**v, "ha": round(v["ha"])} for k, v in by_supply.items()},
        "curve": [{**c, "ls": ls(c["m3"])} for c in curve_pts],
        "cells": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": r["geometry"],
             "properties": {k: v for k, v in r.items() if k != "geometry"}} for r in chosen]},
        "assumptions": [
            "m³/año = lluvia media × coeficiente de escurrimiento × hectáreas elegibles × fracción retenida × conexión con abasto.",
            "Coeficiente de escurrimiento: 0.05 + 0.35·(pendiente/35°) + 0.35·(suelo desnudo); regla simple, no calibrada.",
            "Fracción retenida anual (8–16 %): modelo de flujo de costo mínimo con la capacidad de las barreras y la lluvia diaria CHIRPS; menor donde llueve más en tormentas grandes.",
            "Conectividad hidrológica k: 1.0 si drena directo a La Boca, Cerro Prieto o el río Santa Catarina; 0.6 en el resto de El Cuchillo.",
            "Agua bruta: supone que toda el agua retenida llega a la fuente; es una cota superior.",
            "Ganancia neta esperada: descuenta la evapotranspiración y el escurrimiento que ya llegaba a las presas (informe, sección P9). Es positiva sólo en la cuenca del río Santa Catarina (acuífero Campo Buenos Aires) (probabilidad ~67 %); en las presas es negativa.",
            "Calibrado con el escurrimiento natural de Cerro Prieto (CONAGUA), el agua bruta y la neta bajan ~18 %.",
            "Es una estimación de orden de magnitud para comparar opciones, no un balance hídrico.",
            f"L/s = m³/año ÷ segundos del año. Días de abasto: frente a {ZMM_DEMAND_LS:,} L/s de consumo regular de la ZMM.",
            f"Sequía: misma fórmula con la lluvia real CHIRPS de {DROUGHT_LABEL}.",
        ],
    }
