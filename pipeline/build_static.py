"""Build the static GitHub Pages version into docs/data/.

Pages cannot call Earth Engine, so this precomputes: priority and robustness
overlays (PNG, EPSG:3857), catchment outlines, class hectares, and a set of
demo sites with their proposal sheet and optimized barriers.

    python -m pipeline.build_static
"""
import json
import sys
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


def protected_areas():
    """WDPA polygons over the study area (simplified) for the map layer."""
    fc = ee.FeatureCollection("WCMC/WDPA/current/polygons").filterBounds(layers.aoi())
    fc = fc.filter(ee.Filter.inList("DESIG", ["Parque Nacional", "Monumento Natural", "Área de Protección de los Recursos Naturales",
                                              "Zona Sujeta a Conservación Ecológica", "Santuario Biológico"]))
    gj = fc.map(lambda f: ee.Feature(f.geometry().simplify(120), {"name": f.get("NAME"), "desig": f.get("DESIG")})).getInfo()
    gj = {"type": "FeatureCollection", "features": gj["features"]}
    for path in (OUT / "anp.geojson", OUT.parent.parent / "web" / "anp.geojson"):
        path.write_text(json.dumps(gj, ensure_ascii=False))
    print("wrote anp.geojson", len(gj["features"]))
    return gj


def supply_optimization(budget_ha=3000):
    """The three optimization modes at a fixed budget; the net-gain selection is drawn on the map."""
    res = {}
    for mode in ("max", "balanced", "net"):
        r = optimize.optimize(budget_ha, mode)
        res[mode] = {"totals": r["totals"], "by_supply": r["by_supply"], "curve": r["curve"], "impact": r["impact"]}
        if mode == "net":
            (OUT / "cells.geojson").write_text(json.dumps(r["cells"]))
            res["assumptions"] = r["assumptions"]
            net = r
    return res, net


def _km(a, b):
    import math
    dx = (a[0] - b[0]) * 111.32 * math.cos(math.radians(a[1])); dy = (a[1] - b[1]) * 110.57
    return math.hypot(dx, dy)


def demo_sites(net, n_sites=8, min_km=3.0, anp=None):
    """Best cells of the net-gain optimization where barrier works apply, at least min_km apart."""
    from shapely.geometry import Point, shape
    parks = [(f["properties"]["name"], shape(f["geometry"])) for f in (anp or {}).get("features", [])]
    rob = layers.robustness().unmask(0)
    cells = sorted(net["cells"]["features"], key=lambda f: f["properties"]["rank"])
    sites = []
    for f in cells:
        p = f["properties"]
        if len(sites) >= n_sites:
            break
        if any(_km((p["lon"], p["lat"]), (s["lon"], s["lat"])) < min_km for s in sites):
            continue
        pt = ee.Geometry.Point([p["lon"], p["lat"]])
        stats = layers.site_stats(pt)
        rec = obras.recommend(stats)
        if not rec["obra"].startswith(BARRIER_WORK):
            continue
        r = rob.reduceRegion(ee.Reducer.mean(), pt.buffer(250), 30).get("robustez").getInfo() or 0
        bar = barriers.optimize(p["lon"], p["lat"], 1500, 1200)
        park = next((name for name, g in parks if g.contains(Point(p["lon"], p["lat"]))), None)
        why = {"supply": p["supply_name"], "opt_rank": p["rank"], "m3_year": p["delivered_m3"],
               "m3_per_ha": round(p["delivered_m3"] / p["treated_ha"]), "net_m3_per_ha": round(p["net_m3"] / p["treated_ha"]),
               "p_pos": optimize.NET_P_POS[p["supply"]], "rain_mm": p["rain_mm"], "park": park,
               "c": p["c"], "connectivity": p["connectivity"], "robustness": round(r, 2)}
        sites.append({"lat": p["lat"], "lon": p["lon"], "stats": stats, "recommendation": rec,
                      "ficha": ficha.render(p["lat"], p["lon"], stats, rec), "barriers": bar, "why": why})
        print(f"site {p['supply_name']} #{p['rank']} {why['m3_per_ha']} m3/ha {rec['obra']}")
    (OUT / "sites.json").write_text(json.dumps(sites))
    return sites


if __name__ == "__main__":
    layers.init()
    OUT.mkdir(parents=True, exist_ok=True)
    summary = overlays() if "--no-overlays" not in sys.argv else json.loads((OUT / "meta.json").read_text())["summary"]
    catchments()
    anp = protected_areas()
    opt, net = supply_optimization()
    sites = demo_sites(net, anp=anp)
    (OUT / "meta.json").write_text(json.dumps({"bbox": AOI_BBOX, "summary": summary, "optimization": opt,
                                               "n_sites": len(sites)}, ensure_ascii=False))
    print("summary", summary)
