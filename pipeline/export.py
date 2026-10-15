"""Precompute raw layers + criterion scores once and store them as an EE asset.

Live computation (2-year Sentinel-2 median, SMAP, CHIRPS…) takes 25–40 s per
map tile; reading a precomputed asset is near-instant. Re-run this whenever
the layer logic or calibration in layers.py changes.

    python -m pipeline.export          # starts the export task (to ASSET_ID)
    python -m pipeline.export --asset projects/<p>/assets/scores_v2
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
    return raw.addBands(layers.live_scores()).toFloat().updateMask(layers.aoi_mask())


def start(asset_id=ASSET_ID):
    task = ee.batch.Export.image.toAsset(
        image=build(),
        description="infiltracion_scores",
        assetId=asset_id,
        region=layers.bbox(),
        scale=SCALE,
        maxPixels=1e10,
    )
    task.start()
    print("started", task.id, "->", asset_id)


def status():
    for t in ee.batch.Task.list()[:5]:
        print(t.status().get("description"), t.status().get("state"), t.status().get("error_message", ""))


if __name__ == "__main__":
    layers.init(use_asset=False)
    print("project", EE_PROJECT)
    if "--status" in sys.argv:
        status()
    else:
        start(sys.argv[sys.argv.index("--asset") + 1] if "--asset" in sys.argv else ASSET_ID)
