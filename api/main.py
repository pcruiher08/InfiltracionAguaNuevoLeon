"""FastAPI backend: EE tile URLs for the index, site sampling, rule-based proposal sheets."""
from pathlib import Path

import ee
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from pipeline import ficha, layers, obras  # noqa: E402
from pipeline.config import AOI_BBOX, DEFAULT_WEIGHTS  # noqa: E402

app = FastAPI(title="Infiltración ZMM")

PALETTE = ["#f7fcb9", "#addd8e", "#41ab5d", "#006837"]


class WeightsIn(BaseModel):
    weights: dict[str, float] | None = None


class SiteIn(WeightsIn):
    lon: float
    lat: float


@app.on_event("startup")
def startup():
    layers.init()


@app.get("/api/config")
def config():
    return {"weights": DEFAULT_WEIGHTS, "bbox": AOI_BBOX}


@app.post("/api/tiles")
def tiles(body: WeightsIn):
    idx = layers.priority_index(body.weights)
    index_map = idx.getMapId({"min": 0.3, "max": 0.65, "palette": PALETTE})
    classes_map = layers.priority_classes(idx).getMapId(
        {"min": 1, "max": 3, "palette": ["#fee08b", "#fc8d59", "#d73027"]})
    return {
        "index": index_map["tile_fetcher"].url_format,
        "classes": classes_map["tile_fetcher"].url_format,
    }


@app.post("/api/robustness")
def robustness(body: WeightsIn):
    rob = layers.robustness()
    return {"url": rob.getMapId({"min": 0, "max": 1, "palette": ["#ffffff00", "#c6dbef", "#4292c6", "#08306b"]})["tile_fetcher"].url_format}


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
