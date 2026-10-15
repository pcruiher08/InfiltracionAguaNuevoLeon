"""Program-scale contribution to the ZMM supply system, under mean rain and under the
rain of the 12 months before the 2022 crisis, with Monte Carlo intervals.

    .venv/bin/python -W ignore informe/abasto.py
Writes informe/abasto.json.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from pipeline import barriers_mcmf as M, layers, optimize as O  # noqa: E402
import matematicas as MT  # noqa: E402

DEMAND_LS = O.ZMM_DEMAND_LS          # regular consumption
AVAILABLE_2022_LS = 13_500           # supply available during the 2022 crisis (challenge deck)
DEFICIT_LS = DEMAND_LS - AVAILABLE_2022_LS
BUDGETS = (3_000, 10_000, 30_000, 60_000)
N_MC = 2000
RNG = np.random.default_rng(7)
SEC_Y = MT.SEC_Y
rho = lambda p: np.interp(p, O.RETENTION_RAIN, O.RETENTION_FRAC)


def best_first(v, A, budgets):
    """Fractional optimum for several budgets at once: total value and chosen fraction per cell."""
    order = np.argsort(-v / A); cumA = np.cumsum(A[order]); out = []
    for H in budgets:
        x = np.zeros_like(A)
        full = order[cumA <= H]; x[full] = 1
        k = np.searchsorted(cumA, H, side="right")
        if k < len(order):
            prev = cumA[k - 1] if k else 0.0
            x[order[k]] = (H - prev) / A[order[k]]
        out.append(x)
    return out


def main():
    layers.init()
    rows, A, P, C, k, sup = MT.cells_arrays()
    Pd = np.array([r["rain_drought_mm"] for r in rows], float)
    total_ha = float(A.sum()); budgets = list(BUDGETS) + [total_ha]
    vn = MT.value(A, P, C, k, rho(P)); vd = MT.value(A, Pd, C, k, rho(Pd))
    xs = best_first(vn, A, budgets)

    # Monte Carlo with the same parameter ranges as section 5.9, for every budget and both rain regimes
    mc_n = np.zeros((N_MC, len(budgets))); mc_d = np.zeros_like(mc_n)
    for n in range(N_MC):
        c_f = RNG.uniform(0.7, 1.3); cap = RNG.uniform(0.9, 2.0); bias = RNG.normal(1, 0.1)
        kk = np.where(np.isclose(k, 0.6), RNG.uniform(0.4, 0.8), k)
        Cn = np.clip(C * c_f, 0.02, 0.9); s = cap / M.CAP_M3_PER_M
        v1 = MT.value(A, P * bias, Cn, kk, rho(P * bias) * s)
        v2 = MT.value(A, Pd * bias, Cn, kk, rho(Pd * bias) * s)
        for j, x in enumerate(best_first(v1, A, budgets)):   # selection made with mean rain,
            mc_n[n, j] = (x * v1).sum(); mc_d[n, j] = (x * v2).sum()   # then exposed to the drought
    q = lambda a: [round(float(np.percentile(a, p) / SEC_Y * 1000), 1) for p in (5, 50, 95)]

    out = {"demand_ls": DEMAND_LS, "available_2022_ls": AVAILABLE_2022_LS, "deficit_ls": DEFICIT_LS,
           "total_eligible_ha": round(total_ha), "scenarios": []}
    for j, (H, x) in enumerate(zip(budgets, xs)):
        ln, ld = (x * vn).sum() / SEC_Y * 1000, (x * vd).sum() / SEC_Y * 1000
        by = {MT.SUPPLY_NAMES[s]: {"ls": round(float((x * vn)[sup == s].sum() / SEC_Y * 1000), 1),
                                   "ls_drought": round(float((x * vd)[sup == s].sum() / SEC_Y * 1000), 1),
                                   "ha": round(float((x * A)[sup == s].sum()))} for s in MT.SUPPLY_NAMES}
        out["scenarios"].append({
            "ha": round(H), "ls": round(float(ln), 1), "ls_drought": round(float(ld), 1),
            "hm3": round(float(ln) * SEC_Y / 1e9, 2), "hm3_drought": round(float(ld) * SEC_Y / 1e9, 2),
            "pct_demand": round(100 * float(ln) / DEMAND_LS, 2),
            "pct_deficit_drought": round(100 * float(ld) / DEFICIT_LS, 1),
            "days_supply": round(float(ln) * 365 / DEMAND_LS, 1),
            "mc_ls": q(mc_n[:, j]), "mc_ls_drought": q(mc_d[:, j]), "by_supply": by})
        print(out["scenarios"][-1]["ha"], out["scenarios"][-1]["ls"], out["scenarios"][-1]["ls_drought"],
              out["scenarios"][-1]["mc_ls_drought"], flush=True)
    (ROOT / "abasto.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("wrote abasto.json")


if __name__ == "__main__":
    main()
