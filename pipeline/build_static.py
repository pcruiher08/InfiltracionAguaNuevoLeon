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

from pipeline import barriers, ficha, layers, obras
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


def demo_sites(n=8, step=0.06):
    """Scan a grid over the uplands and keep the highest-priority barrier sites, spread out."""
    w, s, e, nn = AOI_BBOX
    lons = [w + step * i for i in range(int((e - w) / step) + 1)]
    lats = [s + step * j for j in range(int((nn - s) / step) + 1)]
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([lo, la])) for lo in lons for la in lats])
    img = layers.raw().addBands(layers.scores()).addBands(layers.priority_index())
    rows = img.reduceRegions(pts.filterBounds(layers.aoi()), ee.Reducer.mean(), 30).getInfo()["features"]
    cands = []
    for f in rows:
        st = {k: v for k, v in f["properties"].items() if v is not None}
        if (st.get("priority") or 0) < CLASS_THRESHOLDS[1] or not 8 <= (st.get("slope_deg") or 0) <= 35:
            continue
        lon, lat = f["geometry"]["coordinates"]
        cands.append((st["priority"], lon, lat))
    cands.sort(reverse=True)
    chosen = []
    for p, lon, lat in cands:
        if any(abs(lon - a) < 0.12 and abs(lat - b) < 0.12 for _, a, b in chosen):
            continue
        chosen.append((p, lon, lat))
    sites = []
    for _, lon, lat in chosen:
        if len(sites) >= n:
            break
        stats = layers.site_stats(ee.Geometry.Point([lon, lat]))
        rec = obras.recommend(stats)
        if not rec["obra"].startswith(BARRIER_WORK):
            continue
        bar = barriers.optimize(lon, lat, 1500, 1200)
        sites.append({"lat": lat, "lon": lon, "stats": stats, "recommendation": rec,
                      "ficha": ficha.render(lat, lon, stats, rec), "barriers": bar})
        print(f"site {lat:.3f},{lon:.3f} p={stats['priority']:.2f} {rec['obra']}")
    (OUT / "sites.json").write_text(json.dumps(sites))
    return len(sites)


if __name__ == "__main__":
    layers.init()
    OUT.mkdir(parents=True, exist_ok=True)
    summary = overlays()
    catchments()
    n = demo_sites()
    (OUT / "meta.json").write_text(json.dumps({"bbox": AOI_BBOX, "summary": summary, "n_sites": n}))
    print("summary", summary)
