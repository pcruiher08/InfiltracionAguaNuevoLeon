"""Shared configuration: area of interest, dataset IDs, default weights."""
import os

# Google Cloud project registered for Earth Engine (override with EE_PROJECT)
EE_PROJECT = os.environ.get("EE_PROJECT", "infiltracionaguanuevoleon")

# Precomputed layers (pipeline/export.py). The first one that exists is used.
ASSET_ID = f"projects/{EE_PROJECT}/assets/scores_v2"
ASSET_FALLBACKS = [ASSET_ID, f"projects/{EE_PROJECT}/assets/scores_v1"]

# Supply catchments, traced upstream through HydroBASINS level 12
# (HYBAS_ID / NEXT_DOWN) from each supply point; IDs in catchments.json.
# The AOI is their union. Connectivity tiers are a stated assumption:
#   1.0  drains directly to a supply source (La Boca, Cerro Prieto reservoirs;
#        Santa Catarina upstream of Monterrey, which recharges SADM wells/galleries)
#   0.6  rest of the El Cuchillo catchment (major supply, but distant)
CATCHMENTS_FILE = os.path.join(os.path.dirname(__file__), "catchments.json")
HYBAS_LEVEL12 = "WWF/HydroSHEDS/v1/Basins/hybas_12"
CONNECTIVITY_TIERS = {
    "la_boca": 1.0, "cerro_prieto": 1.0, "santa_catarina": 1.0, "el_cuchillo": 0.6,
}
# Score of the "connection to supply" criterion in the priority index, by expected net gain for the
# supply (informe, P9): Santa Catarina recharge is new water; in the dam catchments retention mostly
# holds back runoff that already reached the reservoir, so they score for sediment and floods only.
# CONNECTIVITY_TIERS (above) is still the hydrological connectivity k used for water volumes.
INDEX_CONNECTION = {
    "la_boca": 0.5, "cerro_prieto": 0.5, "santa_catarina": 1.0, "el_cuchillo": 0.3,
}
SUPPLY_POINTS = {  # reservoir centroids (JRC surface water) / river outlet
    "Presa La Boca": (-100.1381, 25.4243),
    "Presa Cerro Prieto": (-99.4228, 24.9187),
    "Presa El Cuchillo": (-99.3018, 25.6933),
    "Río Santa Catarina (Monterrey)": (-100.32, 25.665),
}
AOI_BBOX = [-100.70, 24.37, -99.20, 25.77]  # bounds of the catchment union

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
    "slope": 0.20,         # workable slopes that generate runoff
    "vegetation": 0.25,    # degraded cover = more to gain
    "soil": 0.05,          # permeable texture; low weight: OpenLandMap barely varies here
    "fire": 0.10,          # recently burned = urgent, hydrophobic soils
    "moisture": 0.10,      # dry soils = storage capacity / degradation
    "rain": 0.10,          # more rain = more water to capture
    "connectivity": 0.20,  # drains to a ZMM supply source (see CONNECTIVITY_TIERS)
}

# Class cut points (baja | media | alta), calibrated 2026-10-14 on the index
# distribution over slopes > 8°: ~p50 and ~p80 of the uplands.
CLASS_THRESHOLDS = (0.45, 0.55)

# Scale used when computing the index (meters)
SCALE = 30
