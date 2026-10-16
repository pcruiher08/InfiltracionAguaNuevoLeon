"""Retention of the field treatment: every contour barrier the 30 m DEM resolves plus every gully check dam.

    .venv/bin/python -W ignore informe/campo.py
Writes informe/campo.json, the retention curve rho(P) used by the cell-scale model (pipeline/optimize.py).

The cost per hectare (CONAFOR subsidy cap, or the assumed cost) pays for the complete treatment of a hillslope, so
the water per hectare must come from the same layout. For each demonstration window the layout is fixed and
phi(P), the share of the runoff of a P mm storm it retains, is the maximum flow of section 5.6 (Dinic); weighting
phi by the daily CHIRPS rain gives rho. The same is repeated with the barriers full of sediment (only the
infiltration through the strip, 0.54 m³/m, and 40 m³ per check dam remain) and, for comparison, for 1,500 m of
barriers selected for the 40 mm storm (about 10 m/ha, the sparse layout of earlier versions).
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))
from pipeline import barriers_mcmf as M, layers  # noqa: E402
from pipeline.stats import DEMO_SITES  # noqa: E402
import densidad as DN  # noqa: E402

DAM_SILTED = 40.0       # m³ a silted check dam still infiltrates during the event (simulate.py: 0.3 mm/step, 150 steps)


def main():
    layers.init()
    out = {"window_ha": DN.WINDOW_HA, "storms": list(DN.STORMS), "sites": {}}
    for lon, lat, name in DEMO_SITES:
        recv, r40, contour, dams, interval, slope = DN.network(lon, lat)
        p = DN.daily_rain(lon, lat)
        full = contour + dams
        idx = set(range(len(full)))
        ph = DN.phi_curve(recv, r40, full, idx)
        silted = [dict(c, cap_m3=M.INFIL_M3_PER_M * c["length_m"]) for c in contour] + [dict(d, cap_m3=DAM_SILTED) for d in dams]
        ph_s = DN.phi_curve(recv, r40, silted, idx)
        sparse = M.select(recv, r40, contour, 1500)[0]
        ph_1500 = DN.phi_curve(recv, r40, contour, set(sparse))
        L = float(sum(c["length_m"] for c in contour))
        runoff = float(r40.sum())
        out["sites"][name] = {
            "lon": lon, "lat": lat, "rain_mm_yr": round(float(p.sum()) / 7.75), "slope_deg": round(slope, 1),
            "barrier_m": round(L), "m_per_ha": round(L / DN.WINDOW_HA), "n_barriers": len(contour), "n_dams": len(dams),
            "phi": {str(k): round(v, 4) for k, v in ph.items()}, "rho": round(DN.rho(ph, p), 4),
            "phi_silted": {str(k): round(v, 4) for k, v in ph_s.items()}, "rho_silted": round(DN.rho(ph_s, p), 4),
            "phi_1500": {str(k): round(v, 4) for k, v in ph_1500.items()}, "rho_1500": round(DN.rho(ph_1500, p), 4),
            # hillslope area whose runoff each metre of barrier receives (m² per m): retained share of a small storm
            "area_m2_per_m": round(ph[2] * DN.WINDOW_HA * 1e4 / L, 1),
            "runoff_40_m3": round(runoff),
        }
        print(name, out["sites"][name], flush=True)
    rows = sorted(out["sites"].values(), key=lambda s: s["rain_mm_yr"])
    out["curve"] = {"rain": [s["rain_mm_yr"] for s in rows], "rho": [s["rho"] for s in rows],
                    "rho_silted": [s["rho_silted"] for s in rows], "rho_1500": [s["rho_1500"] for s in rows]}
    (ROOT / "campo.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("curve", out["curve"])


if __name__ == "__main__":
    main()
