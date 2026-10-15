"""Investment portfolio: given a budget (MXN), pick the restoration sites with the
most priority benefit per peso and write a one-page plan.

Candidates are ~500 m grid cells (0.005°) over the AOI. Computing them in Earth
Engine is the slow part (~1 min), so the candidate table is cached per weight
set; selection for any budget / cost table is then instant (pure Python).

COSTS ARE ASSUMED PLACEHOLDERS — replace with Pronatura / CONAFOR figures.
"""
import threading

import ee

from pipeline import layers, obras
from pipeline.config import AOI_BBOX, CLASS_THRESHOLDS, DEFAULT_WEIGHTS

CELL_DEG = 0.005          # grid cell size (~500 m N-S × ~455 m E-W at 25° N)
SLOPE_RANGE = (8, 35)     # workable slopes for soil works (obras.py: > 35° = do not intervene)
MIN_SITE_FRAC = 0.10      # keep cells where ≥ 10% of the area is workable "alta" (~3 ha)
ROADS = "projects/sat-io/open-datasets/GRIP4/Central-South-America"  # GRIP4 includes Mexico
BASINS = "WWF/HydroSHEDS/v1/Basins/hybas_7"
WITH_ROBUSTNESS = True    # 40 extra index evaluations; adds ~seconds to the cold call

# ASSUMED cost per intervened hectare (MXN/ha), labor + materials, flat terrain
# next to a road. Placeholders of a plausible order of magnitude only — NOT
# real quotes. Work types missing here (or set to 0) are not financed.
DEFAULT_COSTS = {
    "Barreras de material vegetal muerto": 8_000,
    "Barreras de piedra acomodada": 15_000,
    "Reforestación con nativas + barreras de material vegetal": 14_000,
    "Zanja-bordo + reforestación con nativas": 20_000,
}
# Access factor: cost × (1 + ACCESS_PER_KM × km beyond ACCESS_FREE_KM), capped.
ACCESS_FREE_KM = 0.5
ACCESS_PER_KM = 0.10
ACCESS_MAX = 1.8

SUPUESTOS = [
    "Costos por hectárea SUPUESTOS (orden de magnitud), editables: reemplazar con costos reales de Pronatura/CONAFOR.",
    f"Factor de acceso: +{ACCESS_PER_KM:.0%} del costo por km de distancia al camino más cercano "
    f"después de {ACCESS_FREE_KM} km (tope ×{ACCESS_MAX}). Caminos: GRIP4 (Meijer et al. 2018), puede omitir brechas.",
    f"Sitios candidatos: celdas de ~500 m cuya prioridad media en laderas trabajables "
    f"({SLOPE_RANGE[0]}–{SLOPE_RANGE[1]}°) es «alta» (> {CLASS_THRESHOLDS[1]}).",
    "Superficie a intervenir = hectáreas de prioridad alta y pendiente trabajable dentro de la celda.",
    "Obra por celda con las reglas de pipeline/obras.py sobre los promedios de esa superficie; "
    "no se financian celdas con cobertura aceptable ni pendientes > 35°.",
    "Selección voraz por (prioridad × ha) / costo hasta agotar el presupuesto; no es un óptimo exacto.",
    "El índice expresa potencial relativo de infiltración; no estima volumen infiltrado.",
]

_cache: dict = {}
_lock = threading.Lock()


def _key(weights):
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total = sum(w.values()) or 1
    return tuple(sorted((k, round(v / total, 4)) for k, v in w.items()))


def _grid():
    w, _, _, n = AOI_BBOX
    return ee.Projection("EPSG:4326", [CELL_DEG, 0, w, 0, -CELL_DEG, n])


def _road_km():
    roads = ee.FeatureCollection(ROADS).filterBounds(layers.aoi().buffer(20_000))
    px = ee.Image(0).paint(roads, 1).selfMask()
    return (px.fastDistanceTransform(256).sqrt().multiply(ee.Image.pixelArea().sqrt())
            .divide(1000).rename("road_km").reproject(crs="EPSG:4326", scale=90))


def _cell_image(weights):
    aoi = layers.aoi()
    idx = layers.priority_index(weights)
    raw, sc = layers.raw(), layers.scores()
    slope = raw.select("slope_deg")
    workable = slope.gte(SLOPE_RANGE[0]).And(slope.lte(SLOPE_RANGE[1]))
    site = idx.gt(CLASS_THRESHOLDS[1]).And(workable)
    bands = [
        site.unmask(0).rename("site_frac"),
        idx.updateMask(workable).rename("prio_work"),
        idx.updateMask(site).rename("priority"),
        raw.updateMask(site),
        sc.updateMask(site).regexpRename("^", "s_"),
        _road_km().updateMask(site),
    ]
    if WITH_ROBUSTNESS:
        bands.append(layers.robustness().unmask(0).updateMask(site))
    grid = _grid()
    cell = ee.Image.cat(bands).setDefaultProjection(raw.projection()).clip(aoi).reduceResolution(ee.Reducer.mean(), maxPixels=1024).reproject(grid)
    basin = ee.Image(0).int64().paint(ee.FeatureCollection(BASINS).filterBounds(aoi), "HYBAS_ID")
    cell = cell.addBands([
        ee.Image.pixelArea().divide(1e4).rename("cell_ha").reproject(grid),
        ee.Image.pixelLonLat().reproject(grid),
        basin.rename("basin").reproject(grid),
    ])
    keep = cell.select("site_frac").gte(MIN_SITE_FRAC).And(cell.select("prio_work").gt(CLASS_THRESHOLDS[1]))
    return cell.updateMask(keep)


def _fetch(weights):
    """Run the EE reduction and return one dict per candidate cell (pre-cost)."""
    layers.init()
    img = _cell_image(weights)
    names = img.bandNames().getInfo()
    cols = img.reduceRegion(ee.Reducer.toList().repeat(len(names)), layers.aoi(),
                            crs=_grid(), maxPixels=1e8).getInfo()["list"]
    w, _, _, n = AOI_BBOX
    out = []
    for row in zip(*cols):
        c = dict(zip(names, row))
        stats = ({k: c.get(k) for k in layers.RAW_BANDS} | {k: c.get("s_" + k) for k in layers.SCORE_BANDS}
                 | {"priority": c["priority"]})
        rec = obras.recommend(stats)
        r, q = int((n - c["latitude"]) // CELL_DEG), int((c["longitude"] - w) // CELL_DEG)
        out.append({
            "id": f"{r:03d}-{q:03d}",
            "lat": round(n - (r + 0.5) * CELL_DEG, 5), "lon": round(w + (q + 0.5) * CELL_DEG, 5),
            "row": r, "col": q,
            "area_ha": round(c["site_frac"] * c["cell_ha"], 1),
            "priority": round(c["priority"], 3),
            "priority_cell": round(c["prio_work"], 3),
            "robustness": round(c["robustez"], 2) if "robustez" in c else None,
            "road_km": round(c["road_km"], 2),
            "subbasin": int(c["basin"]) or None,
            "obra": rec["obra"], "razones": rec["razones"],
            "stats": {k: round(v, 3) for k, v in stats.items() if v is not None},
        })
    return out


def candidates(weights=None):
    """Cached candidate table for a weight set."""
    k = _key(weights)
    with _lock:
        if k not in _cache:
            _cache[k] = _fetch(weights)
        return _cache[k]


def access_factor(km, per_km=ACCESS_PER_KM):
    return min(ACCESS_MAX, 1 + per_km * max(0.0, km - ACCESS_FREE_KM))


def select(cands, budget_mxn, costs=None, per_km=ACCESS_PER_KM):
    """Greedy knapsack by (priority × ha) / cost. Skips sites that don't fit and keeps going."""
    table = {**DEFAULT_COSTS, **(costs or {})}
    priced = []
    for c in cands:
        per_ha = table.get(c["obra"]) or 0
        if per_ha <= 0 or c["area_ha"] <= 0:
            continue
        f = access_factor(c["road_km"], per_km)
        cost = c["area_ha"] * per_ha * f
        priced.append({**c, "cost_mxn": round(cost), "access_factor": round(f, 2),
                       "cost_per_ha": per_ha, "benefit": c["priority"] * c["area_ha"]})
    priced.sort(key=lambda c: c["benefit"] / c["cost_mxn"], reverse=True)
    chosen, left = [], budget_mxn
    for c in priced:
        if c["cost_mxn"] <= left:
            chosen.append(c)
            left -= c["cost_mxn"]
    return chosen, priced, table


def _group(sites, key):
    out = {}
    for s in sites:
        g = out.setdefault(s[key] or "s/d", {"sites": 0, "area_ha": 0.0, "cost_mxn": 0})
        g["sites"] += 1
        g["area_ha"] = round(g["area_ha"] + s["area_ha"], 1)
        g["cost_mxn"] += s["cost_mxn"]
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["cost_mxn"]))


def _cell_geojson(sites):
    feats = []
    for s in sites:
        w, n = AOI_BBOX[0] + s["col"] * CELL_DEG, AOI_BBOX[3] - s["row"] * CELL_DEG
        e, so = w + CELL_DEG, n - CELL_DEG
        feats.append({"type": "Feature",
                      "geometry": {"type": "Polygon", "coordinates": [[[w, n], [e, n], [e, so], [w, so], [w, n]]]},
                      "properties": {k: s[k] for k in ("id", "obra", "area_ha", "priority", "cost_mxn")}})
    return {"type": "FeatureCollection", "features": feats}


def _mxn(x):
    return f"${x:,.0f}"


def plan_md(budget, sites, totals, by_work, by_basin, table, n_cands):
    lines = [
        "# Plan de inversión · Restauración de suelos para infiltración (cuencas altas ZMM)",
        "",
        "## Objetivo",
        "Restaurar suelo en laderas de prioridad alta de las cuencas que abastecen a la Zona Metropolitana "
        "de Monterrey, para frenar escurrimiento y favorecer la infiltración, maximizando el beneficio por peso invertido.",
        "",
        "## Presupuesto",
        f"Presupuesto disponible: **{_mxn(budget)} MXN**. Asignado: **{_mxn(totals['cost_mxn'])} MXN** "
        f"({totals['budget_used_pct']:.0f}%) en **{totals['sites']} sitios** y **{totals['area_ha']:,.1f} ha**. "
        f"Costo medio: {_mxn(totals['cost_per_ha'])} MXN/ha. Candidatos evaluados: {n_cands:,}.",
        "",
        "> **Costos supuestos — reemplazar con costos reales de Pronatura/CONAFOR.**",
        "",
        "## Sitios seleccionados" + (f" (primeros 15 de {len(sites)})" if len(sites) > 15 else ""),
        "",
        "| # | Sitio | Lat, Lon | Obra | ha | Prioridad | Camino (km) | Costo (MXN) |",
        "|---|---|---|---|---|---|---|---|",
        *[f"| {i} | {s['id']} | {s['lat']:.4f}, {s['lon']:.4f} | {s['obra']} | {s['area_ha']:.1f} | "
          f"{s['priority']:.2f} | {s['road_km']:.1f} | {_mxn(s['cost_mxn'])} |"
          for i, s in enumerate(sites[:15], 1)],
        "",
        "## Totales por tipo de obra",
        "",
        "| Obra | Costo supuesto (MXN/ha) | Sitios | ha | Costo (MXN) |",
        "|---|---|---|---|---|",
        *[f"| {k} | {_mxn(table.get(k, 0))} | {v['sites']} | {v['area_ha']:,.1f} | {_mxn(v['cost_mxn'])} |"
          for k, v in by_work.items()],
    ]
    if by_basin:
        lines += ["", "## Totales por subcuenca (HydroSHEDS nivel 7)", "",
                  "| Subcuenca (HYBAS_ID) | Sitios | ha | Costo (MXN) |", "|---|---|---|---|",
                  *[f"| {k} | {v['sites']} | {v['area_ha']:,.1f} | {_mxn(v['cost_mxn'])} |" for k, v in by_basin.items()]]
    lines += [
        "", "## Supuestos", "", *[f"- {s}" for s in SUPUESTOS],
        "", "## Siguientes pasos", "",
        "1. Validación de campo de cada sitio: acceso, pedregosidad, profundidad de suelo y cobertura real.",
        "2. Verificar tenencia de la tierra y si el sitio está en el Parque Nacional Cumbres de Monterrey u otra ANP.",
        "3. Sustituir los costos supuestos por cotizaciones de Pronatura/CONAFOR y recalcular el portafolio.",
        "4. Generar la ficha de obra de cada sitio (clic en el mapa) y priorizar antes de la temporada de lluvias.",
        "5. Definir línea base y monitoreo (cobertura, humedad de suelo, escurrimiento) para medir resultados.",
        "",
        "_Plan generado automáticamente con reglas transparentes; orientativo, no sustituye el proyecto ejecutivo._",
    ]
    return "\n".join(lines)


def build(budget_mxn, weights=None, costs=None, per_km=ACCESS_PER_KM):
    cands = candidates(weights)
    chosen, priced, table = select(cands, budget_mxn, costs, per_km)
    area = round(sum(s["area_ha"] for s in chosen), 1)
    cost = sum(s["cost_mxn"] for s in chosen)
    totals = {
        "sites": len(chosen), "area_ha": area, "cost_mxn": cost,
        "budget_mxn": budget_mxn, "remaining_mxn": round(budget_mxn - cost),
        "budget_used_pct": round(100 * cost / budget_mxn, 1) if budget_mxn else 0,
        "cost_per_ha": round(cost / area) if area else 0,
        "benefit": round(sum(s["benefit"] for s in chosen), 2),
        "candidates": len(cands), "financeable": len(priced),
    }
    by_work, by_basin = _group(chosen, "obra"), _group(chosen, "subbasin")
    keep = ("id", "lat", "lon", "area_ha", "priority", "robustness", "road_km", "access_factor",
            "subbasin", "obra", "razones", "cost_per_ha", "cost_mxn")
    return {
        "selected": [{k: s[k] for k in keep} for s in chosen],
        "totals": totals,
        "by_work_type": by_work,
        "by_subbasin": by_basin,
        "costs": table,
        "access": {"free_km": ACCESS_FREE_KM, "per_km": per_km, "max": ACCESS_MAX},
        "supuestos": SUPUESTOS,
        "geojson": _cell_geojson(chosen),
        "plan_md": plan_md(budget_mxn, chosen, totals, by_work, by_basin, table, len(cands)),
    }
