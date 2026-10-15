"""Build the static GitHub Pages version into docs/data/.

Pages cannot call Earth Engine, so this precomputes: priority and robustness
overlays (PNG, EPSG:3857), catchment outlines, class hectares, and a set of
demo sites with their proposal sheet and optimized barriers.

    python -m pipeline.build_static
"""
import json
import urllib.request
from pathlib import Path

import ee

from pipeline import barriers, ficha, layers, obras, optimize
from pipeline.config import AOI_BBOX, CLASS_THRESHOLDS, SUPPLY_POINTS

OUT = Path(__file__).resolve().parent.parent / "docs" / "data"
BLUE_CLASSES = ["86b6ef", "2a78d6", "0d366b"]
ORANGE_ROB = ["f0956a", "d95926", "8f3510"]
DIM = 2600  # px on the long side of the overlays
BARRIER_WORK = ("Barreras", "Zanja", "Reforestación")


def _png(img, vis, name):
    url = img.visualize(**vis).getThumbURL({
        "region": layers.bbox(), "dimensions": DIM, "format": "png", "crs": "EPSG:3857"})
    urllib.request.urlretrieve(url, OUT / name)
    print("wrote", name)


def overlays():
    uplands = layers.raw().select("slope_deg").gte(8)
    idx = layers.priority_index().updateMask(uplands)
    classes = layers.priority_classes(idx)
    _png(classes.updateMask(classes.gt(1)), {"min": 1, "max": 3, "palette": BLUE_CLASSES}, "priority.png")
    rob = layers.robustness().updateMask(uplands)
    _png(rob.updateMask(rob.gte(0.5)), {"min": 0.5, "max": 1, "palette": ORANGE_ROB}, "robustness.png")

    ha = ee.Image.pixelArea().divide(1e4)
    alta = idx.gt(CLASS_THRESHOLDS[1])
    media = idx.gt(CLASS_THRESHOLDS[0]).And(alta.Not())
    r = ee.Image.cat([ha.updateMask(alta).rename("alta"), ha.updateMask(media).rename("media"),
                      ha.updateMask(rob.unmask(0).gte(0.5).And(alta)).rename("robusta")]
                     ).reduceRegion(ee.Reducer.sum(), layers.aoi(), 90, maxPixels=1e10, bestEffort=True).getInfo()
    return {k: round(v) for k, v in r.items()}


def catchments():
    feats = []
    for k, fc in layers.catchments().items():
        geom = fc.geometry().dissolve(100).simplify(150)
        feats.append({"type": "Feature", "properties": {"key": k}, "geometry": geom.getInfo()})
    pts = [{"type": "Feature", "properties": {"name": n}, "geometry": {"type": "Point", "coordinates": [lon, lat]}}
           for n, (lon, lat) in SUPPLY_POINTS.items()]
    (OUT / "catchments.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats + pts}))
    print("wrote catchments.geojson")


def supply_optimization(budget_ha=3000):
    """Both optimization modes at a fixed budget; selected cells for the map."""
    res = {}
    for mode in ("max", "balanced"):
        r = optimize.optimize(budget_ha, mode)
        res[mode] = {"totals": r["totals"], "by_supply": r["by_supply"], "curve": r["curve"]}
        if mode == "balanced":
            (OUT / "cells.geojson").write_text(json.dumps(r["cells"]))
            res["assumptions"] = r["assumptions"]
            balanced = r
    return res, balanced


def demo_sites(balanced, per_supply=2):
    """Best cells of each supply source (balanced optimization) where barrier works apply."""
    rob = layers.robustness().unmask(0)
    cells = sorted(balanced["cells"]["features"], key=lambda f: f["properties"]["rank"])
    taken, sites = {}, []
    for f in cells:
        p = f["properties"]
        if taken.get(p["supply_name"], 0) >= per_supply:
            continue
        pt = ee.Geometry.Point([p["lon"], p["lat"]])
        stats = layers.site_stats(pt)
        rec = obras.recommend(stats)
        if not rec["obra"].startswith(BARRIER_WORK):
            continue
        r = rob.reduceRegion(ee.Reducer.mean(), pt.buffer(250), 30).get("robustez").getInfo() or 0
        bar = barriers.optimize(p["lon"], p["lat"], 1500, 1200)
        why = {"supply": p["supply_name"], "opt_rank": p["rank"], "m3_year": p["delivered_m3"],
               "m3_per_ha": round(p["delivered_m3"] / p["treated_ha"]), "rain_mm": p["rain_mm"],
               "c": p["c"], "connectivity": p["connectivity"], "robustness": round(r, 2)}
        sites.append({"lat": p["lat"], "lon": p["lon"], "stats": stats, "recommendation": rec,
                      "ficha": ficha.render(p["lat"], p["lon"], stats, rec), "barriers": bar, "why": why})
        taken[p["supply_name"]] = taken.get(p["supply_name"], 0) + 1
        print(f"site {p['supply_name']} #{p['rank']} {why['m3_per_ha']} m3/ha {rec['obra']}")
    (OUT / "sites.json").write_text(json.dumps(sites))
    return sites


if __name__ == "__main__":
    layers.init()
    OUT.mkdir(parents=True, exist_ok=True)
    summary = overlays()
    catchments()
    opt, balanced = supply_optimization()
    sites = demo_sites(balanced)
    (OUT / "meta.json").write_text(json.dumps({"bbox": AOI_BBOX, "summary": summary, "optimization": opt,
                                               "n_sites": len(sites)}, ensure_ascii=False))
    print("summary", summary)
