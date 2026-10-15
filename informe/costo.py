"""Cost per L/s of restoration (gross and net) against the El Cuchillo II aqueduct.

    .venv/bin/python informe/costo.py
Reads informe/destino.json (net-water samples) and writes informe/costo.json.
Restoration cost per hectare ~ U(25,000, 50,000) MXN: the upper bound is the maximum CONAFOR support
for forest restoration (RF.1, 50,000 MXN/ha over 5 years, Reglas de Operación 2026).
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
COST_HA = (25_000, 50_000)
CUCHILLO = {"mxn": 14_680e6, "ls": 5_000}          # capital cost and design flow of El Cuchillo II
RNG = np.random.default_rng(31)

D = json.loads((ROOT / "destino.json").read_text())
ref = CUCHILLO["mxn"] / CUCHILLO["ls"]
out = {"cost_ha": COST_HA, "cuchillo_mxn_per_ls": ref, "selections": {}}
for key in ("bruta_3000", "neta_3000", "bruta_30000", "neta_30000"):
    s = D["selections"][key]; H = s["ha"]
    net = np.array(s["samples"]); cost = RNG.uniform(*COST_HA, len(net)) * H
    out["selections"][key] = {
        "ha": H, "cost_mxn": [float(COST_HA[0] * H), float(COST_HA[1] * H)],
        "mxn_per_gross_ls": [COST_HA[0] * H / s["gross_ls"], COST_HA[1] * H / s["gross_ls"]],
        "mxn_per_net_ls": float(cost.mean() / net.mean()) if net.mean() > 0 else None,
        "p_cheaper_than_cuchillo": round(100 * float((net > cost / ref).mean()), 1),
        "net_needed_ls": [COST_HA[0] * H / ref, COST_HA[1] * H / ref]}
    print(key, out["selections"][key])
(ROOT / "costo.json").write_text(json.dumps(out, ensure_ascii=False))
