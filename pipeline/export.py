"""Precompute raw layers + criterion scores once and store them as an EE asset.

Live computation (2-year Sentinel-2 median, SMAP, CHIRPS…) takes 25–40 s per
map tile; reading a precomputed asset is near-instant. Re-run this whenever
the layer logic or calibration in layers.py changes.

    python -m pipeline.export          # starts the export task
    python -m pipeline.export --status # shows task state
"""
import sys

import ee

from pipeline import layers
from pipeline.config import ASSET_ID, EE_PROJECT, SCALE


def build():
    raw = ee.Image.cat([
        layers.slope_deg().rename("slope_deg"),
        layers.ndvi_dry(),
        layers.texture_class().rename("texture_class"),
        layers.sand_minus_clay(),
        layers.burned(),
        layers.soil_moisture(),
        layers.annual_rain(),
        layers.landcover().rename("landcover"),
    ])
    return raw.addBands(layers.live_scores()).toFloat().clip(layers.aoi())


def start():
    task = ee.batch.Export.image.toAsset(
        image=build(),
        description="infiltracion_scores",
        assetId=ASSET_ID,
        region=layers.aoi(),
        scale=SCALE,
        maxPixels=1e10,
    )
    task.start()
    print("started", task.id, "->", ASSET_ID)


def status():
    for t in ee.batch.Task.list()[:5]:
        print(t.status().get("description"), t.status().get("state"), t.status().get("error_message", ""))


if __name__ == "__main__":
    layers.init(use_asset=False)
    print("project", EE_PROJECT)
    status() if "--status" in sys.argv else start()
