"""FastAPI backend: EE tile URLs for the index, site sampling, rule-based proposal sheets."""
from pathlib import Path

import ee
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from api import fires_api, portfolio_api  # noqa: E402
from pipeline import ficha, layers, obras  # noqa: E402
from pipeline.config import AOI_BBOX, DEFAULT_WEIGHTS  # noqa: E402

app = FastAPI(title="Infiltración ZMM")
app.include_router(fires_api.router, prefix="/api")
app.include_router(portfolio_api.router, prefix="/api")

# Single-hue ramps, validated for CVD/contrast (dataviz validate_palette.js)
BLUE_SEQ = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]  # continuous index
BLUE_CLASSES = ["#86b6ef", "#2a78d6", "#0d366b"]                   # baja, media, alta
ORANGE_ROB = ["#f0956a", "#d95926", "#8f3510"]                      # robustness 50–100%
UPLAND_MIN_SLOPE = 8


class WeightsIn(BaseModel):
    weights: dict[str, float] | None = None
    uplands_only: bool = True
    show_low: bool = False


class SiteIn(WeightsIn):
    lon: float
    lat: float


@app.on_event("startup")
def startup():
    layers.init()


@app.get("/api/config")
def config():
    return {"weights": DEFAULT_WEIGHTS, "bbox": AOI_BBOX}


def _url(img, vis):
    return img.getMapId(vis)["tile_fetcher"].url_format


def _display_mask(body: WeightsIn):
    return layers.raw().select("slope_deg").gte(UPLAND_MIN_SLOPE) if body.uplands_only else ee.Image(1)


@app.post("/api/tiles")
def tiles(body: WeightsIn):
    idx = layers.priority_index(body.weights).updateMask(_display_mask(body))
    classes = layers.priority_classes(idx)
    if not body.show_low:
        classes = classes.updateMask(classes.gt(1))
    return {
        "classes": _url(classes, {"min": 1, "max": 3, "palette": BLUE_CLASSES}),
        "index": _url(idx, {"min": 0.3, "max": 0.65, "palette": BLUE_SEQ}),
    }


@app.post("/api/summary")
def summary(body: WeightsIn):
    """Hectares per class inside the display mask (for the legend)."""
    classes = layers.priority_classes(
        layers.priority_index(body.weights).updateMask(_display_mask(body)))
    area = ee.Image.pixelArea().divide(1e4).addBands(classes)
    groups = area.reduceRegion(
        ee.Reducer.sum().group(groupField=1, groupName="clase"),
        layers.aoi(), 90, maxPixels=1e10, bestEffort=True,
    ).get("groups").getInfo()
    names = {1: "baja", 2: "media", 3: "alta"}
    return {names[g["clase"]]: round(g["sum"]) for g in groups if g["clase"] in names}


@app.get("/api/basins")
def basins():
    fc = ee.FeatureCollection("WWF/HydroSHEDS/v1/Basins/hybas_7").filterBounds(layers.aoi())
    return {"url": _url(fc.style(color="3d3a35", width=1.5, fillColor="00000000"), {})}


@app.post("/api/robustness")
def robustness(body: WeightsIn):
    rob = layers.robustness().updateMask(_display_mask(body))
    rob = rob.updateMask(rob.gte(0.5))
    return {"url": _url(rob, {"min": 0.5, "max": 1, "palette": ORANGE_ROB})}


@app.post("/api/site")
def site(body: SiteIn):
    try:
        stats = layers.site_stats(ee.Geometry.Point([body.lon, body.lat]), body.weights)
    except ee.EEException as e:
        raise HTTPException(502, str(e))
    rec = obras.recommend(stats)
    return {"stats": stats, "recommendation": rec,
            "ficha": ficha.render(body.lat, body.lon, stats, rec)}


app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "web", html=True), name="web")
