"""Barrier density and gully check dams in the min-cost flow selection (fifth peer review).

    .venv/bin/python -W ignore informe/densidad.py
Writes informe/densidad.json.

(1) Density: phi(P), the share of a storm's runoff the barriers retain, was obtained with 1,500 m of barriers in a
    1.2 km window (about 10 m/ha). Here the same lazy greedy with the exact (Dinic) oracle selects layouts of
    1,500 to 24,000 m and the full treatment (every contour candidate of the window), all chosen for the 40 mm design
    storm and then evaluated, fixed, for storms of 2 to 80 mm. Weighting phi by the daily CHIRPS rain of each site
    (2019-2026) gives rho at each density; its ratio to rho at 1,500 m rescales the published rho.
(2) Check dams: the gully check-dam candidates enter the same selection, with a capacity of 100 m³ (60 m³ ponded plus
    about 40 m³ infiltrated during the event, pipeline/simulate.py) and a cost equivalent to L_eq metres of contour
    barrier (15, 30 and 60 m; an assumption, not a quoted price).
"""
import json
import sys
from pathlib import Path

import ee
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from pipeline import barriers as B, barriers_mcmf as M, layers  # noqa: E402
from pipeline.stats import DEMO_SITES  # noqa: E402

WINDOW_M = 1200
WINDOW_HA = WINDOW_M ** 2 / 1e4
BUDGETS = (1500, 3000, 6000, 12000, 24000)
STORMS = (2, 5, 10, 20, 40, 80)
DESIGN = 40
DAM_CAP = 100.0
DAM_LEQ = (15, 30, 60)


def network(lon, lat):
    margin_m = max(150, WINDOW_M * 0.25)
    z, _, _ = B.fetch_dem(lon, lat, WINDOW_M, margin_m)
    m = int(round(margin_m / B.RES)); win = (m, z.shape[0] - m, m, z.shape[1] - m)
    filled = B.fill_pits(z); recv = B.flow_directions(filled)
    acc = B.accumulation(filled, recv).reshape(z.shape); donors = B.donors_of(recv)
    zs = B.smooth3(z); slope = B.slope_deg(zs)
    r0, r1, c0, c1 = win
    interval = B.vertical_interval(float(slope[r0:r1, c0:c1].mean()))
    cands = B.candidates(zs, acc, slope, interval, win)
    for cd in cands:
        cd["up"] = B.upstream(cd["cells"], donors)
    contour = [c for c in cands if c["type"] == "curva de nivel"]
    for cd in contour:
        cd["cap_m3"] = M.CAP_M3_PER_M * cd["length_m"]
    dams = [dict(c, cap_m3=DAM_CAP) for c in cands if c["type"] == "cárcava"]
    M.STORM_MM = DESIGN
    r40 = M.runoff_m3(slope).ravel()
    return recv, r40, contour, dams, interval, float(slope[r0:r1, c0:c1].mean())


def phi_curve(recv, r40, cands, chosen):
    """Share of runoff retained by a fixed layout, per storm (runoff scales with the storm depth)."""
    return {P: M.retained_dinic(recv, r40 * P / DESIGN, cands, set(chosen)) / float((r40 * P / DESIGN).sum())
            for P in STORMS}


def daily_rain(lon, lat):
    col = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate("2019-01-01", "2026-10-01").select("precipitation")
    rows = col.getRegion(ee.Geometry.Point(lon, lat), 5000).getInfo()
    i = rows[0].index("precipitation")
    return np.array([r[i] for r in rows[1:] if r[i] is not None], float)


def rho(phi, p):
    """Volume-weighted retention over the daily rain: phi interpolated between storms, capacity-limited above 80 mm."""
    xs = np.array(STORMS, float); ys = np.array([phi[s] for s in STORMS])
    f = np.where(p <= xs[-1], np.interp(p, xs, ys), ys[-1] * xs[-1] / np.maximum(p, 1e-9))
    w = p[p > 0]; f = f[p > 0]
    return float((f * w).sum() / w.sum())


def main():
    layers.init()
    out = {"window_ha": WINDOW_HA, "storms": list(STORMS), "design_mm": DESIGN, "dam_cap_m3": DAM_CAP,
           "dam_leq_m": list(DAM_LEQ), "sites": {}}
    for lon, lat, name in DEMO_SITES:
        recv, r40, contour, dams, interval, slope = network(lon, lat)
        p = daily_rain(lon, lat)
        total_m = float(sum(c["length_m"] for c in contour))
        site = {"interval_m": interval, "slope_deg": round(slope, 1), "n_contour": len(contour), "n_dams": len(dams),
                "full_m": round(total_m), "full_m_per_ha": round(total_m / WINDOW_HA), "rain_mm_yr": round(float(p.sum()) / 7.75),
                "runoff_40_m3": round(float(r40.sum())), "layouts": []}
        budgets = [b for b in BUDGETS if b < total_m] + [total_m]
        for b in budgets:
            chosen = list(range(len(contour))) if b == total_m else M.select(recv, r40, contour, b)[0]
            used = sum(contour[j]["length_m"] for j in chosen)
            ph = phi_curve(recv, r40, contour, chosen)
            site["layouts"].append({"budget_m": round(b), "used_m": round(used), "m_per_ha": round(used / WINDOW_HA, 1),
                                    "n": len(chosen), "phi": {str(k): round(v, 4) for k, v in ph.items()},
                                    "rho": round(rho(ph, p), 4),
                                    "m3_per_m_40": round(ph[DESIGN] * float(r40.sum()) / max(used, 1), 3),
                                    "kind": "completo" if b == total_m else "seleccion"})
            print(name, round(b), len(chosen), round(used), {k: round(v, 3) for k, v in ph.items()}, flush=True)
        # check dams compete with the barriers for the same budget
        mixed = []
        for leq in DAM_LEQ:
            pool = contour + [dict(d, length_m=float(leq)) for d in dams]
            for b in (1500, 6000):
                chosen = M.select(recv, r40, pool, b)[0]
                nd = sum(1 for j in chosen if j >= len(contour))
                ret = M.retained_dinic(recv, r40, pool, set(chosen))
                base = next(l for l in site["layouts"] if l["budget_m"] == b) if b < total_m else None
                mixed.append({"leq_m": leq, "budget_m": b, "n_dams": nd, "n_barriers": len(chosen) - nd,
                              "barrier_m": round(sum(pool[j]["length_m"] for j in chosen if j < len(contour))),
                              "retained_40_m3": round(ret), "phi_40": round(ret / float(r40.sum()), 4),
                              "barriers_only_phi_40": base["phi"][str(DESIGN)] if base else None})
                print(name, "dams", leq, b, nd, round(ret), flush=True)
        # the simulation's layout: 1,500 m of barriers plus up to 40 check dams outside the budget
        top = sorted(range(len(dams)), key=lambda k: -len(dams[k]["up"]))[:B.MAX_DAMS]
        sel = M.select(recv, r40, contour, 1500)[0]
        pool = contour + [dams[k] for k in top]
        ret = M.retained_dinic(recv, r40, pool, set(sel) | set(range(len(contour), len(pool))))
        site["outside_budget"] = {"n_dams": len(top), "retained_40_m3": round(ret), "phi_40": round(ret / float(r40.sum()), 4)}
        site["mixed"] = mixed
        out["sites"][name] = site
    (ROOT / "densidad.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("wrote densidad.json")


if __name__ == "__main__":
    main()
