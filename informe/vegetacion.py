"""Vegetation type of the selected cells from INEGI's land use and vegetation map, Serie VII
(1:250 000), clipped to the study area (informe/datos/usv7_aoi.geojson, from CONAFOR's IDEFOR WFS).

    .venv/bin/python -W ignore informe/vegetacion.py
Adds "inegi" to informe/destino.json: eligible ha by vegetation group for each selection.
Eligible ha of a 1 km cell are split in proportion to the area of each INEGI polygon inside it.
"""
import json
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from pipeline import layers  # noqa: E402
import destino as DS  # noqa: E402
import matematicas as MT  # noqa: E402

# INEGI class -> vegetation group (reference ecosystem). Secondary vegetation keeps its primary type.
GROUPS = [
    ("Matorral submontano", ("MATORRAL SUBMONTANO",)),
    ("Matorral desértico rosetófilo y micrófilo", ("MATORRAL DESÉRTICO ROSETÓFILO", "MATORRAL DESÉRTICO MICRÓFILO")),
    ("Matorral espinoso tamaulipeco y mezquital", ("MATORRAL ESPINOSO TAMAULIPECO", "MEZQUITAL", "SELVA BAJA ESPINOSA")),
    ("Chaparral", ("CHAPARRAL",)),
    ("Bosque de encino y encino-pino", ("BOSQUE DE ENCINO",)),
    ("Bosque de pino y pino-encino", ("BOSQUE DE PINO",)),
    ("Bosque de oyamel y ayarín", ("BOSQUE DE OYAMEL", "BOSQUE DE AYARÍN")),
    ("Pastizal inducido, cultivado o agricultura", ("PASTIZAL INDUCIDO", "PASTIZAL CULTIVADO", "AGRICULTURA")),
]
OTHER = "Otros"


def group(desc):
    d = (desc or "").upper().replace("VEGETACION", "VEGETACIÓN")
    d = d.replace("VEGETACIÓN SECUNDARIA ARBUSTIVA DE ", "").replace("VEGETACIÓN SECUNDARIA ARBÓREA DE ", "") \
         .replace("VEGETACIÓN SECUNDARIA HERBÁCEA DE ", "")
    for name, keys in GROUPS:
        if any(d.startswith(k) for k in keys):
            return name
    return OTHER


def main():
    feats = json.loads((ROOT / "datos" / "usv7_aoi.geojson").read_text())["features"]
    polys = [shape(f["geometry"]).buffer(0) for f in feats]
    groups = [group(f["properties"].get("DESCRIPCIO")) for f in feats]
    tree = STRtree(polys)

    layers.init()
    rows, A, P, C, k, sup = MT.cells_arrays()
    D = json.loads((ROOT / "destino.json").read_text())
    ratio = {sid: D["et"][MT.SUPPLY_NAMES[sid]]["ratio"] for sid in DS.PHI}

    def g_mean(s):
        e = (DS.E_MIN + ratio[s]) / 2
        return (1 - e) * np.mean(DS.PHI[s]) - np.mean(DS.TAU[s])
    R = 10 * P * C * A * DS.rho(P)
    Gm = np.array([g_mean(s) for s in sup]) * np.where(sup == DS.EC, 0.6, 1.0)
    sel = {f"bruta_{H}": DS.best_first(R * k, A, H) for H in DS.BUDGETS}
    sel.update({f"neta_{H}": DS.best_first(R * Gm, A, H) for H in DS.BUDGETS})

    names = [g for g, _ in GROUPS] + [OTHER]
    frac = {}
    for i in sorted({int(i) for x in sel.values() for i in np.flatnonzero(x > 0)}):
        cell = shape(rows[i]["geometry"]); share = dict.fromkeys(names, 0.0)
        for j in tree.query(cell):
            a = polys[j].intersection(cell).area
            if a > 0:
                share[groups[j]] += a
        tot = sum(share.values())
        frac[i] = {g: v / tot for g, v in share.items()} if tot else {OTHER: 1.0}
    out = {}
    for key, x in sel.items():
        ha = dict.fromkeys(names, 0.0)
        for i in np.flatnonzero(x > 0):
            for g, f in frac[int(i)].items():
                ha[g] += f * x[i] * A[i]
        out[key] = {g: round(v) for g, v in ha.items()}
        print(key, out[key], flush=True)
    D["inegi"] = out
    (ROOT / "destino.json").write_text(json.dumps(D, ensure_ascii=False))
    print("updated destino.json")


if __name__ == "__main__":
    main()
