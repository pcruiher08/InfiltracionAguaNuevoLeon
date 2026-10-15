"""Storm runoff simulation in a site window, without vs with the optimized barriers.

Cell-based routing on the same 30 m DEM / D8 graph as barriers.py:
  * A storm adds rain uniformly during the first RAIN_STEPS steps.
  * Each step every cell infiltrates up to its rate; the rest moves one cell
    downslope (≈ 30 m per step). Water leaving the grid is runoff out.
  * Barrier and check-dam cells pond what reaches them up to a storage
    capacity and infiltrate it faster; only the excess spills downslope.

Didactic model to compare scenarios on the same terrain and storm — not a
calibrated hydrological model (no soil moisture, no velocity physics).
"""
import base64
import math

import numpy as np

from pipeline import barriers as B

RAIN_MM = 40          # storm depth
RAIN_STEPS = 8        # steps with rain
STEPS = 150           # total steps (≈ 30 m of travel each)
FRAME_EVERY = 2
# One step ≈ 2.4 min (150 steps ≈ 6 h event). Depths are over a 30 × 30 m cell.
INF_HILL = 1.0        # mm/step on degraded hillslope (~25 mm/h)
# A barrier ponds a ~3 m strip upslope (10 % of the cell), ~0.3 m deep:
CAP_BARRIER = 30.0    # mm over the cell ≈ 27 m³ per barrier cell (0.9 m³ per meter)
INF_BARRIER = 0.12    # mm/step over the cell = 30 mm/h through the ponded strip
CAP_DAM = 67.0        # check dam ≈ 60 m³
INF_DAM = 0.3
CELL_M2 = B.RES * B.RES


def _setup(lon, lat, budget_m, window_m):
    margin_m = max(150, window_m * 0.25)
    z, lon_g, lat_g = B.fetch_dem(lon, lat, window_m, margin_m)
    to_ll = B.pixel_to_lonlat(lon_g, lat_g)
    m = int(round(margin_m / B.RES))
    win = (m, z.shape[0] - m, m, z.shape[1] - m)
    filled = B.fill_pits(z)
    recv = B.flow_directions(filled)
    acc = B.accumulation(filled, recv).reshape(z.shape)
    donors = B.donors_of(recv)
    zs = B.smooth3(z)
    local_slope = B.slope_deg(zs)
    r0, r1, c0, c1 = win
    interval = B.vertical_interval(float(local_slope[r0:r1, c0:c1].mean()))
    cands = B.candidates(zs, acc, local_slope, interval, win)
    for cd in cands:
        cd["up"] = B.upstream(cd["cells"], donors)
    contour = [c for c in cands if c["type"] == "curva de nivel"]
    chosen, _, _, _ = B.greedy(contour, z.size, budget_m)
    dams = sorted((c for c in cands if c["type"] == "cárcava"), key=lambda c: -len(c["up"]))[:B.MAX_DAMS]
    return z, filled, recv, to_ll, win, chosen, dams


def _run(filled, recv, cap, inf, inside):
    """Route one storm. Returns frames (moving water mm per cell), the series of
    water leaving the analysis window downslope, and window totals (m³)."""
    n = filled.size
    leaves = inside & ((recv < 0) | ~inside[np.maximum(recv, 0)])  # window cells draining outward
    water = np.zeros(n)        # water arriving at each cell this step (mm)
    stored = np.zeros(n)       # ponded behind works (mm)
    frames, ponded, out_series = [], [], []
    flux = np.zeros(n)  # total water that passed through each cell (mm)
    tot = {"rain": 0.0, "infiltrated_hill": 0.0, "infiltrated_works": 0.0, "outflow": 0.0}
    rain_step = RAIN_MM / RAIN_STEPS
    is_work = cap > 0
    for t in range(STEPS):
        if t < RAIN_STEPS:
            water += rain_step
            tot["rain"] += rain_step * inside.sum()
        # ponded water infiltrates through the strip
        f_store = np.minimum(stored, inf * is_work)
        stored -= f_store
        tot["infiltrated_works"] += f_store[inside].sum()
        # infiltration of arriving water on every cell
        f = np.minimum(water, INF_HILL)
        water -= f
        tot["infiltrated_hill"] += f[inside].sum()
        # works pond incoming water up to capacity
        room = np.maximum(cap - stored, 0)
        take = np.minimum(water, room)
        stored += take
        water -= take
        # route the rest one cell downslope
        nxt = np.zeros(n)
        out = water[leaves].sum()
        np.add.at(nxt, recv[recv >= 0], water[recv >= 0])
        tot["outflow"] += out
        out_series.append(out * CELL_M2 / 1000)  # m³ leaving this step
        flux += water
        if t % FRAME_EVERY == 0:
            frames.append(water.copy())
            ponded.append(stored.copy())
        water = nxt
    tot["still_moving"] = water[inside].sum()
    tot["still_ponded"] = stored[inside].sum()
    totals = {k: round(v * CELL_M2 / 1000) for k, v in tot.items()}
    return frames, ponded, flux, out_series, totals


def _encode(frames, vmax):
    """Frames → base64 uint8 (linear scale, clipped at vmax) for a light payload."""
    arr = np.stack(frames) if isinstance(frames, list) else frames[None]
    q = np.clip(arr / vmax * 255, 0, 255).astype(np.uint8)
    return base64.b64encode(q.tobytes()).decode()


def simulate(lon, lat, budget_m=1500, window_m=1200):
    z, filled, recv, to_ll, win, chosen, dams = _setup(lon, lat, budget_m, window_m)
    n = z.size
    cap = np.zeros(n)
    inf = np.full(n, INF_HILL)
    for cd in chosen:
        cap[cd["cells"]] = CAP_BARRIER
        inf[cd["cells"]] = INF_BARRIER
    for cd in dams:
        cap[cd["cells"]] = CAP_DAM
        inf[cd["cells"]] = INF_DAM
    r0, r1, c0, c1 = win
    inside = np.zeros(z.shape, bool)
    inside[r0:r1, c0:c1] = True
    inside = inside.ravel()
    f0, _, flux0, s0, t0 = _run(filled, recv, np.zeros(n), np.full(n, INF_HILL), inside)
    f1, p1, flux1, s1, t1 = _run(filled, recv, cap, inf, inside)
    moving = np.stack(f0)
    vmax = max(float(np.percentile(moving[moving > 1], 90)), 1.0)  # linear; channels saturate gently
    # share of each cell's storm flux removed by the works (0..1), only where water flowed
    reduction = np.where(flux0 > 5, np.clip(1 - flux1 / np.maximum(flux0, 1e-9), 0, 1), 0)

    nr, nc = z.shape
    lo, la = to_ll(np.array([-0.5, nc - 0.5]), np.array([-0.5, nr - 0.5]))
    peak0, peak1 = float(max(s0)), float(max(s1))
    return {
        "grid": {"rows": nr, "cols": nc, "frames": len(f0), "vmax_mm": round(vmax, 1),
                 "bounds": [[float(min(la)), float(min(lo))], [float(max(la)), float(max(lo))]]},
        "window": B.window_polygon(to_ll, win) if hasattr(B, "window_polygon") else None,
        "without": {"frames": _encode(f0, vmax), "outflow": [round(float(v), 1) for v in s0], "totals": t0},
        "with": {"frames": _encode(f1, vmax), "ponded": _encode(p1, CAP_BARRIER),
                 "outflow": [round(float(v), 1) for v in s1], "totals": t1},
        "difference": {"reduction": _encode(reduction, 1.0),
                       "flux_without": _encode(flux0, float(np.percentile(flux0[flux0 > 5], 95)))},
        "summary": {
            "rain_m3": t0["rain"],
            "outflow_reduction_pct": round(100 * (1 - t1["outflow"] / max(t0["outflow"], 1)), 1),
            "peak_reduction_pct": round(100 * (1 - peak1 / max(peak0, 1e-9)), 1),
            "peak_m3_step": [round(peak0, 1), round(peak1, 1)],
            "extra_infiltration_m3": (t1["infiltrated_hill"] + t1["infiltrated_works"] + t1["still_ponded"])
                                     - (t0["infiltrated_hill"] + t0["infiltrated_works"] + t0["still_ponded"]),
            "n_barriers": len(chosen), "n_dams": len(dams),
        },
        "params": {"rain_mm": RAIN_MM, "rain_steps": RAIN_STEPS, "steps": STEPS, "frame_every": FRAME_EVERY,
                   "inf_hill_mm": INF_HILL, "inf_barrier_mm": INF_BARRIER,
                   "cap_barrier_mm": CAP_BARRIER, "cap_dam_mm": CAP_DAM, "cell_m": B.RES},
        "notes": [
            f"Tormenta de {RAIN_MM} mm sobre toda la ventana; cada paso el agua avanza ~30 m ladera abajo.",
            "Sin barreras: solo infiltra la ladera degradada. Con barreras: cada obra encharca una franja de ~3 m "
            "hasta su capacidad (~0.9 m³ por metro) y la infiltra a ~30 mm/h; el excedente sigue escurriendo.",
            "Modelo didáctico para comparar escenarios sobre el mismo terreno y la misma tormenta, "
            "no un modelo hidrológico calibrado.",
        ],
    }
