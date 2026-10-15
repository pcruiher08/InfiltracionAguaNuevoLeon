"""Precompute statistics for web/stats.html into web/stats.json.

    python -m pipeline.stats
"""
import json
from pathlib import Path

import ee
import numpy as np

from pipeline import barriers, barriers_mcmf, layers, optimize, simulate
from pipeline.config import CLASS_THRESHOLDS

OUT = Path(__file__).resolve().parent.parent / "web" / "stats.json"
SUPPLY_NAMES = {sid: name for sid, name in optimize.SUPPLY.values()}
CRITERIA = ["slope", "vegetation", "soil", "fire", "moisture", "rain", "connectivity"]
DEMO_SITES = [(-100.05, 25.0, "Pilón"), (-100.45, 25.45, "Santa Catarina"), (-100.1188, 25.4342, "La Boca")]


def _uplands_classes():
    up = layers.raw().select("slope_deg").gte(8)
    idx = layers.priority_index().updateMask(up)
    return idx, layers.priority_classes(idx)


def ha_by_catchment():
    idx, cls = _uplands_classes()
    img = ee.Image.pixelArea().divide(1e4).addBands(cls.multiply(10).add(optimize.supply_id()).rename("key"))
    groups = img.reduceRegion(ee.Reducer.sum().group(groupField=1, groupName="key"),
                              layers.aoi(), 90, maxPixels=1e10, bestEffort=True).get("groups").getInfo()
    out = {}
    for g in groups:
        c, sid = divmod(int(g["key"]), 10)
        if sid not in SUPPLY_NAMES:
            continue
        cname = {1: "baja", 2: "media", 3: "alta"}[c]
        out.setdefault(SUPPLY_NAMES[sid], {"alta": 0, "media": 0, "baja": 0})[cname] = round(g["sum"])
    return out


def criteria_by_class():
    idx, cls = _uplands_classes()
    img = layers.scores().select(CRITERIA).addBands(cls)
    groups = img.reduceRegion(ee.Reducer.mean().repeat(len(CRITERIA)).group(groupField=len(CRITERIA), groupName="clase"),
                              layers.aoi(), 120, maxPixels=1e10, bestEffort=True).get("groups").getInfo()
    names = {1: "baja", 2: "media", 3: "alta"}
    return {names[int(g["clase"])]: dict(zip(CRITERIA, [round(v, 3) for v in g["mean"]])) for g in groups}


def robustness_hist():
    idx, cls = _uplands_classes()
    rob = layers.robustness().unmask(0).updateMask(cls.eq(3))
    ha = ee.Image.pixelArea().divide(1e4).addBands(rob.multiply(10).floor().min(9).rename("bin"))
    groups = ha.reduceRegion(ee.Reducer.sum().group(groupField=1, groupName="bin"),
                             layers.aoi(), 90, maxPixels=1e10, bestEffort=True).get("groups").getInfo()
    bins = {int(g["bin"]): round(g["sum"]) for g in groups}
    return [{"from": b / 10, "to": (b + 1) / 10, "ha": bins.get(b, 0)} for b in range(10)]


def water_curves():
    cells = optimize.cell_table()
    out = {}
    for key, field in (("normal", "delivered_m3"), ("sequia", "delivered_drought_m3")):
        ranked = sorted(cells, key=lambda r: -r[field] / r["eligible_ha"])
        ha = np.cumsum([r["eligible_ha"] for r in ranked])
        m3 = np.cumsum([r[field] for r in ranked])
        marks = np.unique(np.concatenate([np.linspace(0, 60000, 61), [ha[-1]]]))
        out[key] = [{"ha": int(h), "ls": round(float(np.interp(h, np.concatenate([[0], ha]),
                                                               np.concatenate([[0], m3]))) / optimize.SECONDS_YEAR * 1000, 1)}
                    for h in marks if h <= ha[-1]]
    return out


def productivity_by_supply():
    cells = optimize.cell_table()
    edges = list(range(0, 801, 25))
    out = {}
    for sid, name in SUPPLY_NAMES.items():
        v = np.array([r["delivered_m3"] / r["eligible_ha"] for r in cells if r["supply"] == sid])
        w = np.array([r["eligible_ha"] for r in cells if r["supply"] == sid])
        h, _ = np.histogram(np.clip(v, 0, edges[-1] - 1), bins=edges, weights=w)
        out[name] = {"bins": [{"from": a, "to": b, "ha": round(float(x))} for a, b, x in zip(edges, edges[1:], h)],
                     "median": round(float(np.median(v))), "ha": round(float(w.sum())), "cells": int(len(v))}
    return out


def barrier_budget_curves():
    out = {}
    for lon, lat, name in DEMO_SITES:
        pts = []
        for b in (250, 500, 750, 1000, 1500, 2000, 3000, 4000):
            t = barriers.optimize(lon, lat, b, 1200)["totals"]
            pts.append({"budget_m": b, "intercepted_pct": t["intercepted_pct"], "n": t["n_barriers"]})
        out[name] = pts
    return out


def storm_sites():
    sites_file = Path(__file__).resolve().parent.parent / "docs" / "data" / "sites.json"
    sites = json.loads(sites_file.read_text()) if sites_file.exists() else []
    rows = []
    for i, s in enumerate(sites, 1):
        r = simulate.simulate(s["lon"], s["lat"])["summary"]
        rows.append({"site": i, "supply": s.get("why", {}).get("supply", ""),
                     "outflow_reduction_pct": r["outflow_reduction_pct"], "peak_reduction_pct": r["peak_reduction_pct"],
                     "extra_infiltration_m3": r["extra_infiltration_m3"]})
    return rows


def mcmf_vs_greedy():
    """Retained m³ (capacity-respecting) for the min-cost-flow placement vs the area greedy, by storm size."""
    out = {}
    for lon, lat, name in DEMO_SITES[:2]:
        rows = []
        for mm in (5, 10, 20, 40):
            r = barriers_mcmf.optimize(lon, lat, 1500, storm_mm=mm)
            rows.append({"storm_mm": mm, "runoff_m3": r["totals"]["storm_runoff_m3"], "mcmf_m3": r["totals"]["retained_m3"],
                         "greedy_m3": r["comparison"]["greedy_retained_m3"], "full": r["totals"]["full_barriers"],
                         "n": r["totals"]["n_barriers"]})
            print("  mcmf", name, mm)
        out[name] = rows
    return out


if __name__ == "__main__":
    layers.init()
    stats = {}
    for name, fn in [("ha_by_catchment", ha_by_catchment), ("criteria_by_class", criteria_by_class),
                     ("robustness_hist", robustness_hist), ("water_curves", water_curves),
                     ("productivity_by_supply", productivity_by_supply),
                     ("barrier_budget_curves", barrier_budget_curves), ("storm_sites", storm_sites),
                     ("mcmf_vs_greedy", mcmf_vs_greedy)]:
        stats[name] = fn()
        print("done", name)
    stats["thresholds"] = CLASS_THRESHOLDS
    OUT.write_text(json.dumps(stats, ensure_ascii=False))
    print("wrote", OUT)
