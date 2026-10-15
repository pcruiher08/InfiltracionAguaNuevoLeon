# Infiltración ZMM — Reto 1 (Grok Monterrey Build Day)

Prioritizes upland sites in the Santa Catarina, Ramos and Pilón basins for soil
restoration that favors infiltration, and recommends a work type with transparent rules and renders a site proposal sheet ("ficha de obra").

> The index measures **relative potential**, not infiltrated volume.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
earthengine authenticate          # one-time, opens browser
cp .env.example .env              # fill EE_PROJECT
uvicorn api.main:app --reload     # http://localhost:8000
```

## Layout
- `pipeline/config.py` — AOI, dataset IDs, default weights
- `pipeline/layers.py` — EE criterion scores (0–1), weighted index, site sampling
- `api/main.py` — `/api/tiles`, `/api/robustness`, `/api/site`, serves `web/`
- `pipeline/obras.py` — rule engine: slope/soil/cover/fire → work type, spacing
- `pipeline/ficha.py` — Markdown proposal sheet template (no LLM at runtime)
- `web/index.html` — Leaflet map, weight sliders, robustness layer, click → sheet + .md download
