"""Purely biophysical priority index (fifth peer review): the same criteria and weights without hydrological
connectivity, renormalized, and connectivity applied afterwards as a filter.

    .venv/bin/python -W ignore informe/biofisico.py
Writes informe/biofisico.json.

Inside the supply catchments k is 1 (La Boca, Cerro Prieto, Santa Catarina) or 0.6 (El Cuchillo), so the published
index is I = 0.8 I_b + 0.2 k: within each tier it is an increasing function of the biophysical index I_b and orders
pixels identically; k only lowers El Cuchillo by 0.08. The biophysical classes use the percentiles of I_b at the same
ranks as the published classes (same high and low shares), and also the fixed thresholds 0.45 and 0.55.
"""
import json
import sys
from pathlib import Path

import ee

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from pipeline import layers, optimize  # noqa: E402
from pipeline.config import CLASS_THRESHOLDS  # noqa: E402
from pipeline.stats import SUPPLY_NAMES  # noqa: E402

SCALE = 90


def area_by(img_key):
    ha = ee.Image.pixelArea().divide(1e4).addBands(img_key.rename("key"))
    g = ha.reduceRegion(ee.Reducer.sum().group(groupField=1, groupName="key"), layers.aoi(), SCALE,
                        maxPixels=1e10, bestEffort=True).get("groups").getInfo()
    return {int(x["key"]): x["sum"] for x in g}


def main():
    layers.init()
    up = layers.raw().select("slope_deg").gte(8)
    idx = layers.priority_index().updateMask(up)
    ib = layers.priority_index({"connectivity": 0}).updateMask(up)
    cls = layers.priority_classes(idx)
    # shares of the published classes on slopes >= 8 degrees
    a = area_by(cls)
    tot = sum(a.values()); p_lo = 100 * a.get(1, 0) / tot; p_hi = 100 * (1 - a.get(3, 0) / tot)
    q = ib.reduceRegion(ee.Reducer.percentile([p_lo, p_hi]), layers.aoi(), SCALE, maxPixels=1e10, bestEffort=True).getInfo()
    t_lo, t_hi = sorted(q.values())
    cls_b = layers.priority_classes(ib, t_lo, t_hi)
    cls_bf = layers.priority_classes(ib, *CLASS_THRESHOLDS)
    sup = optimize.supply_id()
    k = layers.connectivity()
    # key: published class, biophysical class (matched), biophysical class (fixed thresholds), supply id
    key = cls.multiply(1000).add(cls_b.multiply(100)).add(cls_bf.multiply(10)).add(sup)
    g = area_by(key)
    names = {1: "baja", 2: "media", 3: "alta"}
    out = {"thresholds_matched": [round(t_lo, 3), round(t_hi, 3)], "thresholds_fixed": list(CLASS_THRESHOLDS),
           "ranks": [round(p_lo, 1), round(p_hi, 1)], "uplands_ha": round(tot)}
    hi = lambda pos: sum(v for kk, v in g.items() if (kk // pos) % 10 == 3)
    both = sum(v for kk, v in g.items() if kk // 1000 == 3 and (kk // 100) % 10 == 3)
    out["high_ha"] = {"publicado": round(hi(1000)), "biofisico": round(hi(100)), "biofisico_fijo": round(hi(10))}
    out["both_high_ha"] = round(both)
    out["overlap_pct_of_published"] = round(100 * both / hi(1000), 1)
    union = hi(1000) + hi(100) - both
    out["jaccard"] = round(both / union, 3)
    same = sum(v for kk, v in g.items() if kk // 1000 == (kk // 100) % 10)
    out["same_class_pct"] = round(100 * same / tot, 1)
    by = {}
    for kk, v in g.items():
        sid = kk % 10
        if sid not in SUPPLY_NAMES:
            continue
        d = by.setdefault(SUPPLY_NAMES[sid], {"publicado": 0, "biofisico": 0, "biofisico_fijo": 0, "ambos": 0})
        if kk // 1000 == 3: d["publicado"] += v
        if (kk // 100) % 10 == 3: d["biofisico"] += v
        if (kk // 10) % 10 == 3: d["biofisico_fijo"] += v
        if kk // 1000 == 3 and (kk // 100) % 10 == 3: d["ambos"] += v
    out["high_by_supply"] = {s: {kk: round(v) for kk, v in d.items()} for s, d in by.items()}
    # connectivity as an a-posteriori filter: biophysical high priority in directly connected basins (k = 1)
    hb = ee.Image.pixelArea().divide(1e4).updateMask(cls_b.eq(3))
    r = ee.Image.cat([hb.updateMask(k.eq(1)).rename("directa"), hb.updateMask(k.lt(1)).rename("cuchillo")]) \
        .reduceRegion(ee.Reducer.sum(), layers.aoi(), SCALE, maxPixels=1e10, bestEffort=True).getInfo()
    hp = ee.Image.pixelArea().divide(1e4).updateMask(cls.eq(3))
    rp = hp.updateMask(k.eq(1)).reduceRegion(ee.Reducer.sum(), layers.aoi(), SCALE, maxPixels=1e10, bestEffort=True).values().get(0).getInfo()
    out["filter"] = {"biofisico_directa_ha": round(r["directa"]), "biofisico_cuchillo_ha": round(r["cuchillo"]),
                     "publicado_directa_ha": round(rp)}
    corr = ee.Image.cat([idx.rename("a"), ib.rename("b")]).reduceRegion(
        ee.Reducer.pearsonsCorrelation(), layers.aoi(), 180, maxPixels=1e10, bestEffort=True).getInfo()
    out["pearson"] = round(corr["correlation"], 3)
    # mean index in a 250 m radius around the suggested sites (chosen by net gain, not by the index)
    sites = json.loads((ROOT.parent / "docs" / "data" / "sites.json").read_text())
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(s["lon"], s["lat"]).buffer(250), {"i": i}) for i, s in enumerate(sites)])
    img = layers.priority_index().rename("publicado").addBands(layers.priority_index({"connectivity": 0}).rename("biofisico"))
    fs = sorted(img.reduceRegions(fc, ee.Reducer.mean(), 30).getInfo()["features"], key=lambda f: f["properties"]["i"])
    out["sites"] = [{k: round(f["properties"][k], 3) for k in ("publicado", "biofisico")} for f in fs]
    (ROOT / "biofisico.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
