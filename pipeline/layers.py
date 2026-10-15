"""Earth Engine layers for the infiltration priority index.

Every criterion returns a 0–1 score where 1 = higher restoration priority.
The index is relative potential, NOT infiltrated volume.
"""
import random

import ee

from pipeline.config import (
    AOI_BBOX, ASSET_ID, CLASS_THRESHOLDS, DATASETS, EE_PROJECT, DEFAULT_WEIGHTS, DRY_SEASON_MONTHS, END, START,
)

SCORE_BANDS = ["slope", "vegetation", "soil", "fire", "moisture", "rain"]
RAW_BANDS = ["slope_deg", "ndvi", "texture_class", "sand_minus_clay", "burned", "sm", "rain_mm"]

_initialized = False
_asset = None  # precomputed ee.Image, or None to compute live


def init(use_asset=True):
    global _initialized, _asset
    if not _initialized:
        ee.Initialize(project=EE_PROJECT)
        _initialized = True
        if use_asset:
            try:
                ee.data.getAsset(ASSET_ID)
                _asset = ee.Image(ASSET_ID)
            except ee.EEException:
                print(f"[layers] {ASSET_ID} not found; computing live (slow). "
                      "Run: python -m pipeline.export")


def landcover():
    return ee.ImageCollection(DATASETS["landcover"]).first().select("Map")


def aoi():
    return ee.Geometry.Rectangle(AOI_BBOX)


def _norm(img, lo, hi):
    return img.subtract(lo).divide(hi - lo).clamp(0, 1)


# --- raw layers -------------------------------------------------------------

def slope_deg():
    return ee.Terrain.slope(ee.Image(DATASETS["dem"]).select("elevation"))


def ndvi_dry():
    def mask_clouds(img):
        scl = img.select("SCL")
        return img.updateMask(scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)))

    m0, m1 = DRY_SEASON_MONTHS
    col = (ee.ImageCollection(DATASETS["s2"])
           .filterBounds(aoi())
           .filterDate(ee.Date(END).advance(-2, "year"), END)
           .filter(ee.Filter.calendarRange(m0, m1, "month"))
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
           .map(mask_clouds))
    return col.median().normalizedDifference(["B8", "B4"]).rename("ndvi")


def texture_class():
    # USDA texture classes 1 (clay) .. 12 (sand), surface layer
    return ee.Image(DATASETS["texture"]).select("b0")


def sand_minus_clay():
    # Texture class is a constant "clay loam" across the AOI, so use the
    # continuous fractions (%) instead. Range here is roughly 0–12.
    sand = ee.Image(DATASETS["sand"]).select("b0")
    clay = ee.Image(DATASETS["clay"]).select("b0")
    return sand.subtract(clay).rename("sand_minus_clay")


def burned():
    """1 = burned in last 3 years, 0.5 = burned earlier in window, 0 = not burned."""
    col = ee.ImageCollection(DATASETS["burned"]).select("BurnDate")
    ever = col.filterDate(START, END).max().gt(0).unmask(0)
    recent = col.filterDate(ee.Date(END).advance(-3, "year"), END).max().gt(0).unmask(0)
    return ever.multiply(0.5).max(recent).rename("burned")


def soil_moisture():
    m0, m1 = DRY_SEASON_MONTHS
    # SMAP L4 is 3-hourly (01:30, 04:30, ...); one slot per day keeps it within memory
    return (ee.ImageCollection(DATASETS["soil_moisture"])
            .filterDate(ee.Date(END).advance(-2, "year"), END)
            .filter(ee.Filter.calendarRange(m0, m1, "month"))
            .filter(ee.Filter.calendarRange(13, 13, "hour"))
            .select("sm_surface").mean().rename("sm"))


def annual_rain():
    years = ee.Date(END).difference(ee.Date(START), "year")
    total = ee.ImageCollection(DATASETS["rain"]).filterDate(START, END).sum()
    return total.divide(years).rename("rain_mm")


def valid_mask():
    lc = _asset.select("landcover") if _asset is not None else landcover()
    return lc.neq(50).And(lc.neq(80))  # drop built-up and permanent water


# --- criterion scores ---------------------------------------------------------

def scores():
    return _asset.select(SCORE_BANDS) if _asset is not None else live_scores()


def raw():
    if _asset is not None:
        return _asset.select(RAW_BANDS)
    return ee.Image.cat([
        slope_deg().rename("slope_deg"),
        ndvi_dry(),
        texture_class().rename("texture_class"),
        sand_minus_clay(),
        burned(),
        soil_moisture(),
        annual_rain(),
    ])


def live_scores():
    s = slope_deg()
    # Peak 8–25°: enough runoff to matter, still workable. Fades out by 45°.
    slope_score = _norm(s, 0, 8).min(ee.Image(45).subtract(s).divide(20).clamp(0, 1))
    soil_score = _norm(sand_minus_clay(), 0, 12)
    return ee.Image.cat([
        slope_score.rename("slope"),
        ee.Image(1).subtract(_norm(ndvi_dry(), 0.1, 0.7)).rename("vegetation"),
        soil_score.rename("soil"),
        burned().rename("fire"),
        ee.Image(1).subtract(_norm(soil_moisture(), 0.06, 0.15)).rename("moisture"),
        _norm(annual_rain(), 350, 850).rename("rain"),
    ])


def priority_index(weights=None, sc=None):
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total = sum(w.values()) or 1
    sc = sc if sc is not None else scores()
    idx = ee.Image(0)
    for k, v in w.items():
        idx = idx.add(sc.select(k).unmask(0).multiply(v / total))
    return idx.rename("priority").updateMask(valid_mask()).clip(aoi())


def priority_classes(index, lo=CLASS_THRESHOLDS[0], hi=CLASS_THRESHOLDS[1]):
    """3 = alta, 2 = media, 1 = baja."""
    return index.gt(lo).add(index.gt(hi)).add(1).rename("clase")


def robustness(n=40, hi=CLASS_THRESHOLDS[1], seed=7):
    """Share of random weightings (Dirichlet-like) in which a pixel is 'alta'.

    High values = high priority regardless of how experts weigh the criteria.
    """
    rng = random.Random(seed)
    sc = scores()
    hits = []
    for _ in range(n):
        w = {k: rng.expovariate(1.0) for k in DEFAULT_WEIGHTS}
        hits.append(priority_index(w, sc).gt(hi))
    return ee.ImageCollection(hits).mean().rename("robustez").selfMask()


# --- site sampling ------------------------------------------------------------

def site_stats(geom, weights=None):
    img = raw().addBands(scores()).addBands(priority_index(weights))
    region = geom.buffer(250) if geom.type().getInfo() == "Point" else geom
    stats = img.reduceRegion(ee.Reducer.mean(), region, 30, maxPixels=1e9).getInfo()
    lc = landcover().reduceRegion(
        ee.Reducer.mode(), region, 10, maxPixels=1e9).getInfo()
    stats["landcover_mode"] = lc.get("Map")
    stats["area_ha"] = region.area(1).divide(1e4).getInfo()
    return stats
