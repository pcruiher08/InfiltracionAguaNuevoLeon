"""Reconcile the storm simulation (pipeline/simulate.py) with the MCMF retention for the same site and storm.

    .venv/bin/python -W ignore informe/conciliacion.py
Writes informe/conciliacion.json: extra infiltration and outflow reduction with barriers only, gully check dams only,
and both; and the MCMF retention of contour barriers for the same 40 mm storm.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from pipeline import barriers_mcmf as M, layers, simulate as SIM  # noqa: E402

LON, LAT = -100.45, 25.45


def run(z, filled, recv, win, works):
    n = z.size; cap = np.zeros(n); inf = np.full(n, SIM.INF_HILL)
    for kind, cells, f in works:
        cap[cells] = SIM.CAP_BARRIER * f if kind == "barrera" else SIM.CAP_DAM
        inf[cells] = SIM.INF_BARRIER * f if kind == "barrera" else SIM.INF_DAM
    r0, r1, c0, c1 = win
    inside = np.zeros(z.shape, bool); inside[r0:r1, c0:c1] = True; inside = inside.ravel()
    _, _, _, s0, t0 = SIM._run(filled, recv, np.zeros(n), np.full(n, SIM.INF_HILL), inside)
    _, _, _, s1, t1 = SIM._run(filled, recv, cap, inf, inside)
    return t0, t1


def main():
    layers.init()
    z, filled, recv, to_ll, win, chosen, dams = SIM._setup(LON, LAT, 1500, 1200)
    out = {}
    for name, works in (("barreras", [("barrera", c["cells"], SIM.barrier_cell_factor(c)) for c in chosen]),
                        ("presas", [("presa", c["cells"], 1) for c in dams]),
                        ("ambas", [("barrera", c["cells"], SIM.barrier_cell_factor(c)) for c in chosen] + [("presa", c["cells"], 1) for c in dams])):
        t0, t1 = run(z, filled, recv, win, works)
        out[name] = {"t0": t0, "t1": t1}
    out["n_barriers"] = len(chosen); out["n_dams"] = len(dams)
    out["barrier_cells"] = int(sum(len(c["cells"]) for c in chosen)); out["barrier_m"] = round(sum(c["length_m"] for c in chosen))
    out["dam_cells"] = int(sum(len(c["cells"]) for c in dams))
    r = M.optimize(LON, LAT, 1500, storm_mm=40)
    out["mcmf"] = {"retained_m3": r["totals"]["retained_m3"], "runoff_m3": r["totals"]["storm_runoff_m3"],
                   "greedy_layout_retained_m3": r["comparison"]["greedy_retained_m3"]}
    (ROOT / "conciliacion.json").write_text(json.dumps(out, ensure_ascii=False, default=float))
    print(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
