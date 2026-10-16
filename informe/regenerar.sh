#!/usr/bin/env bash
# Regenerate every analysis, figure and the PDF from the data, in dependency order.
#   bash informe/regenerar.sh          # everything (Earth Engine; about 1 to 2 hours)
#   bash informe/regenerar.sh --pdf    # only figures, maps and the PDF from the saved JSON files
set -euo pipefail
cd "$(dirname "$0")/.."
PY=".venv/bin/python -W ignore"

if [[ "${1:-}" != "--pdf" ]]; then
  $PY -m pipeline.build_static            # site selection, map overlays, protected areas (docs/data)
  $PY -m pipeline.stats                   # web/stats.json (uses docs/data/sites.json)
  $PY informe/extras.py                   # optimization summaries and targets
  rm -f informe/math.json                 # matematicas.py is resumable; start clean
  $PY informe/matematicas.py              # Monte Carlo, duality, Gumbel, Pareto
  $PY informe/abasto.py                   # program-scale contribution vs the 2022 deficit
  $PY informe/destino.py                  # probabilistic fate of the retained water
  if [[ ! -f informe/datos/usv7_aoi.geojson ]]; then  # INEGI Serie VII via CONAFOR IDEFOR
    curl -s -m 300 -o informe/datos/usv7_aoi.geojson "https://idefor.cnf.gob.mx/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=geonode:cdv_usuev250svii_cnal_wgs84&outputFormat=application/json&bbox=-100.7,24.37,-99.2,25.77"
  fi
  $PY informe/vegetacion.py               # vegetation types of the selected cells
  $PY informe/calibracion.py              # runoff factor vs CONAGUA natural runoff (Cerro Prieto)
  $PY informe/calibracion.py --posterior  # Bayesian reweighting of the destino.py samples
  $PY informe/costo.py                    # cost per L/s
  $PY informe/sedimento.py                # RUSLE and dam sedimentation
  $PY informe/sensibilidad.py             # karst and barrier siltation (after destino and sedimento)
  $PY informe/evapotranspiracion.py       # satellite ET ensemble and soil-water budget of the barrier strip
  $PY informe/clima.py                    # protected areas and CMIP6 drought frequency
  $PY informe/oraculos.py                 # MCMF vs Dinic vs topological fill (about 15 min)
fi
$PY informe/figuras.py
$PY informe/mapas.py
$PY informe/aplanar.py                  # flatten PNGs (no alpha) for PDF viewers
$PY informe/generar.py
(cd informe && tectonic informe.tex && tectonic presentacion.tex)
cp informe/informe.pdf docs/infiltracion-zmm.pdf
cp informe/presentacion.pdf docs/presentacion-zmm.pdf
echo "listo: informe, presentación y copias en docs/"
