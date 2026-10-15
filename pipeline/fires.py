"""Post-fire monitor: fire events in the AOI, burn severity, re-scored sites.

Every fire triggers an action plan: detections (FIRMS active fire + MODIS
burned area) are grouped into events, burn severity is measured with
Sentinel-2 dNBR, and each event gets the priority index (with the fire
criterion forced to "recent"), a work recommendation and a proposal sheet.
"""
from datetime import date, timedelta

import ee

from pipeline import ficha, layers, obras
from pipeline.config import DATASETS

FIRMS = "FIRMS"
DEMO_WINDOW = ("2025-02-01", "2025-05-31")  # dry season verified to have events in the AOI
EVENT_SCALE = 500       # m; grid used to group detections into events
MAX_CANDIDATES = 25     # events sampled before filtering
UPLAND_MIN_SLOPE = 8    # degrees; same "laderas" cut as the map
MIN_UPLAND_HA = 25      # footprint on slopes needed to count as an upland fire
MAX_EVENTS = 15
MIN_CONFIDENCE = 50     # FIRMS detection confidence (%)
PERSISTENT_DAYS = 10    # FIRMS pixel hot on > N days in the prior year = industrial source
MIN_DNBR_HA = 5         # FIRMS-only events need this much dNBR-burned area ...
MIN_DNBR_FRAC = 0.25    # ... and this share of the footprint (seasonal background is ~10–15%)

# Standard USGS dNBR burn severity thresholds (Key & Benson 2006, FIREMON),
# unscaled: < 0.10 unburned, then low / moderate-low / moderate-high / high.
DNBR_THRESHOLDS = (0.10, 0.27, 0.44, 0.66)
SEVERITY = ["sin señal", "baja", "moderada-baja", "moderada-alta", "alta"]
SEVERITY_PALETTE = ["#f5a3a3", "#e34948", "#a52a2a", "#5e1414"]  # baja → alta

_DAY_MS = 86_400_000


def window(start=None, end=None, days=90):
    """(start, end) ISO strings; defaults to the last `days` days."""
    end = end or date.today().isoformat()
    start = start or (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    return start, end


def _epoch_day(d):
    return ee.Date(d).millis().divide(_DAY_MS).floor()


# --- detections -----------------------------------------------------------------

def _firms_days(start, end):
    """FIRMS detections as an image collection of 'day' (days since 1970)."""
    col = ee.ImageCollection(FIRMS).filterBounds(layers.aoi())
    hot = lambda i: i.select("confidence").gte(MIN_CONFIDENCE).selfMask()
    prior = col.filterDate(ee.Date(start).advance(-1, "year"), start).map(hot).count()
    not_persistent = prior.unmask(0).lte(PERSISTENT_DAYS)

    def to_day(img):
        day = _epoch_day(img.date())
        return (hot(img).multiply(0).add(day).toFloat().rename("day")
                .updateMask(not_persistent))
    return col.filterDate(start, end).map(to_day)


def _mcd_days(start, end):
    """MODIS MCD64A1 burned pixels as 'day' (BurnDate is day-of-year)."""
    def to_day(img):
        jan1 = _epoch_day(ee.Date.fromYMD(img.date().get("year"), 1, 1))
        bd = img.select("BurnDate")
        return bd.add(jan1).subtract(1).toFloat().rename("day").updateMask(bd.gt(0))
    col = (ee.ImageCollection(DATASETS["burned"])
           .filterDate(ee.Date(start).advance(-1, "month"), end).map(to_day))
    lo, hi = _epoch_day(start), _epoch_day(end)
    return col.map(lambda i: i.updateMask(i.gte(lo).And(i.lte(hi))))


def detections(start, end):
    """Bands: day_min, day_max (epoch days) and mcd (1 = MODIS burned area)."""
    mcd = _mcd_days(start, end)
    days = mcd.merge(_firms_days(start, end))
    # Only where the index exists (analysis area) and not on built-up land
    valid = layers.scores().select("slope").mask().And(layers.landcover().neq(50))
    return (days.min().rename("day_min")
            .addBands(days.max().rename("day_max"))
            .addBands(mcd.count().gt(0).unmask(0).rename("mcd"))
            .updateMask(valid))


def event_polygons(start, end, uplands_only=True):
    """Connected detection clusters on a 500 m grid, largest first.

    With uplands_only, ranks by footprint on slopes >= 8° (lowland farm burns
    are out of scope for upland soil restoration).
    """
    det = detections(start, end)
    ha = ee.Image.pixelArea().divide(1e4)
    upland = layers.raw().select("slope_deg").gte(UPLAND_MIN_SLOPE).unmask(0)
    img = ee.Image.cat([det.select("day_min").gte(0).rename("label"), ha, ha.multiply(upland)])
    polys = img.reduceToVectors(
        geometry=layers.aoi(), crs="EPSG:4326", scale=EVENT_SCALE,
        geometryType="polygon", eightConnected=True, labelProperty="label",
        reducer=ee.Reducer.sum().forEach(["footprint_ha", "upland_ha"]),
        maxPixels=1e10, bestEffort=True)
    if uplands_only:
        return polys.filter(ee.Filter.gte("upland_ha", MIN_UPLAND_HA)).sort("upland_ha", False)
    return polys.sort("footprint_ha", False)


# --- burn severity ---------------------------------------------------------------

def _nbr(start, end):
    def mask_clouds(img):
        scl = img.select("SCL")
        return img.updateMask(scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)))
    col = (ee.ImageCollection(DATASETS["s2"])
           .filterBounds(layers.aoi()).filterDate(start, end)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
           .map(mask_clouds))
    return col.median().normalizedDifference(["B8", "B12"]).rename("nbr")


def dnbr(start, end):
    """Pre-fire NBR median (90 days before) minus post-fire median.

    Post-fire = 45 days after the window; if that hasn't happened yet, the
    last 30 days of the window (a recent fire can still be in progress).
    """
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    post_end = min(e + timedelta(days=45), date.today())
    post = (e, post_end) if (post_end - e).days >= 20 else (e - timedelta(days=30), e)
    pre = _nbr((s - timedelta(days=90)).isoformat(), start)
    return pre.subtract(_nbr(post[0].isoformat(), post[1].isoformat())).rename("dnbr")


def severity_classes(d):
    """0 = sin señal, 1 = baja … 4 = alta (USGS thresholds)."""
    out = ee.Image(0)
    for t in DNBR_THRESHOLDS:
        out = out.add(d.gte(t))
    return out.rename("severity")


def severity_class(value):
    return SEVERITY[sum(value >= t for t in DNBR_THRESHOLDS)] if value is not None else "s/d"


def severity_tile(start, end, polys=None):
    """Tile URL of dNBR severity classes inside the detected events."""
    polys = polys if polys is not None else event_polygons(start, end)
    cls = severity_classes(dnbr(start, end))
    img = cls.updateMask(cls.gt(0)).clipToCollection(polys)
    vis = {"min": 1, "max": 4, "palette": SEVERITY_PALETTE}
    return img.getMapId(vis)["tile_fetcher"].url_format


# --- events -----------------------------------------------------------------------

def _rescored(weights):
    """Priority index with the fire criterion forced to 1 (burned now)."""
    sc = layers.scores().addBands(ee.Image(1).rename("fire"), overwrite=True)
    return layers.priority_index(weights, sc)


_HELPER_BANDS = {"dnbr", "high_frac", "dnbr_burned_frac", "mcd_frac", "day_min", "day_max"}


def _sample(polys, start, end, weights):
    d = dnbr(start, end)
    det = detections(start, end)
    base = (layers.raw().addBands(layers.scores()).addBands(_rescored(weights))
            .addBands(det.select("mcd").unmask(0).rename("mcd_frac"))
            .addBands(det.select(["day_min", "day_max"])))
    reducer = ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True)

    def per_event(f):
        g = f.geometry()
        # dNBR offset (as in MTBS): median dNBR of an unburned 2 km ring around
        # the event, removing seasonal change that isn't fire
        ring = g.buffer(2000, 100).difference(g, 100)
        off = d.reduceRegion(ee.Reducer.median(), ring, 60, bestEffort=True).get("dnbr")
        off = ee.Number(ee.Algorithms.If(off, off, 0))
        dc = d.subtract(off)
        burned = dc.gte(DNBR_THRESHOLDS[0])
        img = (base.addBands(dc.updateMask(burned).rename("dnbr"))
               .addBands(severity_classes(dc).eq(4).updateMask(burned).rename("high_frac"))
               .addBands(burned.unmask(0).rename("dnbr_burned_frac")))
        stats = img.reduceRegion(reducer, g, 30, maxPixels=1e9, tileScale=4)
        lc = layers.landcover().reduceRegion(ee.Reducer.mode(), g, 30, maxPixels=1e9).get("Map")
        return f.set(stats).set({
            "landcover_mode": lc, "dnbr_offset": off,
            "area_poly_ha": g.area(1).divide(1e4), "centroid": g.centroid(1).coordinates()})
    return polys.map(per_event)


def _iso(epoch_day):
    return (date(1970, 1, 1) + timedelta(days=int(epoch_day))).isoformat() if epoch_day is not None else None


def _fire_section(ev):
    src = "MODIS MCD64A1" if ev["source"] == "modis" else "FIRMS + dNBR Sentinel-2"
    return "\n".join([
        "### Evento de incendio",
        f"| Dato | Valor |", "|---|---|",
        f"| Fechas detectadas | {ev['start']} a {ev['end']} |",
        f"| Superficie quemada | {ev['area_ha']:,.0f} ha ({src}) |",
        f"| Severidad (dNBR medio) | {ev['severity']} ({ev['dnbr']:.2f}) |" if ev["dnbr"] is not None
        else "| Severidad (dNBR) | sin imágenes Sentinel-2 válidas |",
        f"| Severidad alta | {ev['high_pct']:.0f}% del área quemada |",
        "",
        "_Severidad con umbrales estándar USGS de dNBR. La ficha re-evalúa el sitio "
        "considerando el incendio como reciente._",
        "",
    ])


def _event(i, f, start, end):
    p = f["properties"]
    mean = lambda k: p.get(f"{k}_mean")
    stats = {k[:-5]: v for k, v in p.items() if k.endswith("_mean") and k[:-5] not in _HELPER_BANDS}
    if stats.get("priority") is None:  # outside the analysis area
        return None, False
    lc = p.get("landcover_mode")
    stats["landcover_mode"] = round(lc) if lc is not None else None
    poly_ha = p["area_poly_ha"]
    mcd_ha = (mean("mcd_frac") or 0) * poly_ha
    dnbr_ha = (mean("dnbr_burned_frac") or 0) * poly_ha
    lon, lat = p["centroid"]
    ev_end = _iso(p.get("day_max_max")) or end
    # The precomputed asset may predate the fire; obras/ficha read burned >= 1
    # as "burned in the last 3 years".
    recent = date.fromisoformat(ev_end) >= date.today() - timedelta(days=3 * 365)
    stats["burned"] = 1 if recent else 0.5
    stats["fire"] = 1
    stats["area_ha"] = poly_ha
    ev = {
        "id": f"F{i + 1:02d}", "lat": lat, "lon": lon,
        "area_ha": round(mcd_ha if mcd_ha > 0 else dnbr_ha, 1),
        "source": "modis" if mcd_ha > 0 else "firms",
        "start": _iso(p.get("day_min_min")) or start, "end": ev_end,
        "dnbr": mean("dnbr"), "severity": severity_class(mean("dnbr")),
        "high_pct": 100 * (mean("high_frac") or 0),
        "priority": stats["priority"],
    }
    rec = obras.recommend(stats)
    md = ficha.render(lat, lon, stats, rec).split("\n", 2)
    ev["recommendation"] = rec
    ev["ficha"] = "\n".join([md[0], "", _fire_section(ev) + md[2]])
    ev["ficha"] = ev["ficha"].replace("## Ficha de obra", f"## Ficha de obra post-incendio {ev['id']}", 1)
    ev["stats"] = stats
    dnbr_ok = dnbr_ha >= MIN_DNBR_HA and (mean("dnbr_burned_frac") or 0) >= MIN_DNBR_FRAC
    return ev, stats["priority"] is not None and (mcd_ha > 0 or dnbr_ok)


def events(start, end, weights=None, uplands_only=True):
    """Top fire events of the window, each with severity, priority and a ficha."""
    polys = event_polygons(start, end, uplands_only)
    cand = polys.limit(MAX_CANDIDATES)
    fc = _sample(cand, start, end, weights).getInfo()
    out = []
    for f in fc["features"]:
        ev, confirmed = _event(len(out), f, start, end)
        if confirmed:
            out.append((ev, f["geometry"]))
        if len(out) == MAX_EVENTS:
            break
    geojson = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": g,
         "properties": {"id": ev["id"], "severity": ev["severity"], "area_ha": ev["area_ha"]}}
        for ev, g in out]}
    return {
        "window": {"start": start, "end": end, "uplands_only": uplands_only},
        "events": [ev for ev, _ in out],
        "geojson": geojson,
        "severity_tile_url": severity_tile(start, end, cand),
        "severity_palette": SEVERITY_PALETTE,
        "severity_labels": SEVERITY[1:],
    }
