"""Compare three retention oracles for barrier placement: min-cost max-flow (network simplex, OR-Tools),
maximum flow with Dinic's algorithm, and a topological greedy fill.

    .venv/bin/python -W ignore informe/oraculos.py
Writes informe/oraculos.json.

For each site and design storm: (1) the three oracles evaluate the same barrier sets (the set chosen by
the min-cost flow and 30 random sets of 1,500 m), recording retained m³ and time per call; (2) the whole
lazy greedy (CELF) selection is run with each oracle, and its result is evaluated with the exact oracle.
"""
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from pipeline import barriers_mcmf as M, layers  # noqa: E402

BUDGET = 1500
STORMS = (5, 10, 20, 40)
SEL_STORMS = (10, 40)
N_RANDOM = 30
ORACLES = {"mcmf": M.retained, "dinic": M.retained_dinic, "fill": M.retained_fill}


def random_set(cands, rng):
    order = list(range(len(cands))); rng.shuffle(order)
    out, spent = set(), 0.0
    for j in order:
        if spent + cands[j]["length_m"] <= BUDGET:
            out.add(j); spent += cands[j]["length_m"]
    return out


def timed(f, *a):
    t = time.perf_counter(); v = f(*a); return v, 1000 * (time.perf_counter() - t)


def main():
    layers.init()
    sites = [("Santa Catarina (demostración)", -100.45, 25.45), ("Pilón", -100.05, 25.0), ("La Boca", -100.1188, 25.4342)]
    sug = json.loads((ROOT.parent / "docs" / "data" / "sites.json").read_text())
    sites += [(f"Sitio sugerido {i}", s["lon"], s["lat"]) for i, s in enumerate(sug[:2], 1)]
    rng = random.Random(3)
    evals, selections = [], []
    for name, lon, lat in sites:
        recv, r40, cands = M.setup(lon, lat, storm_mm=40)
        for mm in STORMS:
            r = r40 * mm / 40                               # runoff is linear in the storm depth
            opt, _ = M.select(recv, r, cands, BUDGET)
            sets = [("optimizado", set(opt))] + [("aleatorio", random_set(cands, rng)) for _ in range(N_RANDOM)]
            for kind, S in sets:
                row = {"site": name, "storm_mm": mm, "kind": kind, "n": len(S), "runoff_m3": float(r.sum())}
                for k, f in ORACLES.items():
                    v, ms = timed(f, recv, r, cands, S)
                    row[k] = round(v, 2); row[f"{k}_ms"] = round(ms, 2)
                evals.append(row)
            if mm in SEL_STORMS:
                for k, f in ORACLES.items():
                    t = time.perf_counter(); chosen, calls = M.select_with(f, recv, r, cands, BUDGET)
                    sec = time.perf_counter() - t
                    selections.append({"site": name, "storm_mm": mm, "oracle": k, "calls": calls, "seconds": round(sec, 2),
                                       "retained_exact": round(M.retained(recv, r, cands, set(chosen)), 1), "n": len(chosen)})
            print(name, mm, "done", flush=True)
    (ROOT / "oraculos.json").write_text(json.dumps({"evals": evals, "selections": selections, "budget_m": BUDGET,
                                                    "n_random": N_RANDOM, "sites": [s[0] for s in sites]}, ensure_ascii=False))
    print("wrote oraculos.json")


if __name__ == "__main__":
    main()
