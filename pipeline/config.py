"""Shared configuration: area of interest, dataset IDs, default weights."""

# Upper basins that feed the ZMM supply: Santa Catarina (Cumbres),
# Ramos/San Juan (La Boca) and Pilón (Cerro Prieto). Rough bbox for the demo;
# refine with HydroSHEDS level-8/9 basins once the pipeline works.
AOI_BBOX = [-100.65, 24.75, -99.55, 25.75]  # [west, south, east, north]

# Analysis window
START = "2019-01-01"
END = "2026-10-01"
DRY_SEASON_MONTHS = (2, 5)  # Feb–May: vegetation contrast is clearest

DATASETS = {
    "dem": "NASA/NASADEM_HGT/001",
    "s2": "COPERNICUS/S2_SR_HARMONIZED",
    "landcover": "ESA/WorldCover/v200",
    "texture": "OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02",
    "sand": "OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02",
    "clay": "OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02",
    "burned": "MODIS/061/MCD64A1",
    "rain": "UCSB-CHG/CHIRPS/DAILY",
    "soil_moisture": "NASA/SMAP/SPL4SMGP/008",
}

# Criterion -> default weight. Weights are renormalized to sum to 1.
DEFAULT_WEIGHTS = {
    "slope": 0.25,       # workable slopes that generate runoff
    "vegetation": 0.30,  # degraded cover = more to gain
    "soil": 0.10,        # permeable texture; low weight: OpenLandMap barely varies here
    "fire": 0.15,        # recently burned = urgent, hydrophobic soils
    "moisture": 0.10,    # dry soils = storage capacity / degradation
    "rain": 0.10,        # more rain = more water to capture
}

# Class cut points (baja | media | alta), calibrated 2026-10-14 on the index
# distribution over slopes > 8°: ~p50 and ~p80 of the uplands.
CLASS_THRESHOLDS = (0.45, 0.55)

# Scale used when computing the index (meters)
SCALE = 30
