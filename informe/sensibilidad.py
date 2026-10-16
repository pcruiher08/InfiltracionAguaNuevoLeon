"""Two sensitivity analyses raised in peer review, from saved results (no Earth Engine).

    .venv/bin/python informe/sensibilidad.py
Writes informe/sensibilidad.json.

(1) Karst: in fractured limestone, infiltrated water can follow faults out of the Santa Catarina catchment.
    The fraction that reaches the aquifer, phi, is widened from U(0.5, 0.9) to U(0.2, 0.9) (moderate loss) and
    U(0.1, 0.5) (high loss), and the net gain G = (1 - e) phi - tau is recomputed.
(1b) Interflow: the share iota of the water drained below the strip that moves downslope within the rooting zone and
    evaporates like ordinary rain is not measured; instead of the range U(0.2, 0.6), G is swept over iota from 0 to 1
    with the soil-water bucket e, and the values of iota where the mean G and P(G > 0) cross zero and 50 % are reported.
(2) Sediment filling the barriers: soil kept by the barriers settles in the ponded strip. With the RUSLE soil loss
    of the selected Santa Catarina cells and the hillslope area each metre of barrier drains in the field treatment
    (informe/campo.py), the years until the ponded storage (0.9 m³/m) fills are estimated, and the long-term retention
    without sediment clearance, when only infiltration through the strip (0.54 m³/m) remains.
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SC = "Acuífero Santa Catarina (pozos SADM)"
N = 200_000
RNG = np.random.default_rng(17)
POND, INFIL = 0.9, 0.54                 # m³ per metre of barrier (pipeline/barriers_mcmf.py)
WINDOW_HA = 144                         # 1.2 km × 1.2 km analysis window


def karst():
    D = json.loads((ROOT / "destino.json").read_text())
    et = D["et"][SC]["ratio"]; tau = D["tau"][SC]; gross = D["selections"]["neta_30000"]["gross_ls"]
    out = {}
    for name, phi in (("base", D["phi"][SC]), ("karst_moderado", [0.2, 0.9]), ("karst_alto", [0.1, 0.5])):
        e = RNG.uniform(D["e_min"], et, N); p = RNG.uniform(*phi, N); t = RNG.uniform(*tau, N)
        G = (1 - e) * p - t
        out[name] = {"phi": phi, "g_mean": round(float(G.mean()), 3), "p_pos": round(100 * float((G > 0).mean()), 1),
                     "net_ls_30000": round(float(gross * G.mean()), 1)}
    # share of the variance of G explained by each parameter (squared linear correlation), base and moderate karst
    for name in ("base", "karst_moderado"):
        phi = out[name]["phi"]
        e = RNG.uniform(D["e_min"], et, N); p = RNG.uniform(*phi, N); t = RNG.uniform(*tau, N)
        G = (1 - e) * p - t
        out[name]["var_share"] = {k: round(float(np.corrcoef(v, G)[0, 1] ** 2), 2) for k, v in (("e", e), ("phi", p), ("tau", t))}
    return out


def interflow():
    D = json.loads((ROOT / "destino.json").read_text()); E = json.loads((ROOT / "evapotranspiracion.json").read_text())
    es = np.array(E["bucket"]["e_samples"]); sat = [v for k, v in E["ratios"][SC].items() if k != "rain_mm" and v <= 1]
    w0 = D["selections"]["neta_30000"]["net_mean"]; g_prior = D["factor"][SC]["mean"]
    rows = []
    for iota in np.round(np.arange(0, 1.0001, 0.05), 2):
        e = RNG.choice(es, N); rr = RNG.uniform(min(sat), max(sat), N)
        ei = e + (1 - e) * iota * rr
        G = (1 - ei) * RNG.uniform(*D["phi"][SC], N) - RNG.uniform(*D["tau"][SC], N)
        rows.append({"iota": float(iota), "e": round(float(ei.mean()), 3), "g_mean": round(float(G.mean()), 3),
                     "p_pos": round(100 * float((G > 0).mean()), 1), "net_ls_30000": round(float(w0 * G.mean() / g_prior), 1)})
    io = np.array([r["iota"] for r in rows]); g = np.array([r["g_mean"] for r in rows]); pp = np.array([r["p_pos"] for r in rows])
    cross = lambda y, lvl: float(np.interp(-lvl, -y, io)) if y.min() < lvl < y.max() else None   # y decreases with iota
    return {"rows": rows, "iota_g0": cross(g, 0.0), "iota_p50": cross(pp, 50.0), "iota_p90": cross(pp, 90.0)}


def sediment():
    S = json.loads((ROOT / "sedimento.json").read_text())
    a0 = S["erosion_t_ha_yr_lambda22"][SC]                                   # t/ha/yr, 22 m slope, no practices
    F = json.loads((ROOT / "campo.json").read_text())["sites"]
    area_m = np.array([v["area_m2_per_m"] / 1e4 for v in F.values()])         # ha drained per metre, field treatment
    lam = RNG.uniform(30, 100, N); pc = RNG.uniform(0.2, 0.6, N); rho = RNG.uniform(1.1, 1.5, N); rf = RNG.uniform(0.8, 1.2, N)
    am = RNG.choice(area_m, N)
    out = {"a0": a0, "area_m2_per_m": round(float(area_m.mean() * 1e4), 1), "scenarios": {}}
    for k, f in (("rusle", 1.0), ("rusle_3", 1 / 3), ("rusle_10", 0.1)):
        dep = a0 * f * (lam / 22.13) ** 0.5 * rf * (1 - pc) * am / rho          # m³ of sediment per metre per year
        yrs = POND / dep
        out["scenarios"][k] = {"factor": f, "m3_per_m_yr": [round(float(np.percentile(dep, q)), 2) for q in (5, 95)] + [round(float(dep.mean()), 2)],
                               "years_to_fill": [round(float(np.percentile(yrs, q)), 2) for q in (5, 95)] + [round(float(yrs.mean()), 2)],
                               "years_to_fill_median": round(float(np.median(yrs)), 2)}
    # without clearance only the infiltration through the strip remains (0.54 m³/m, 40 m³ per check dam); the
    # field treatment rarely fills, so the retention falls less than the capacity (informe/campo.py)
    keep = F["Santa Catarina"]["rho_silted"] / F["Santa Catarina"]["rho"]
    D = json.loads((ROOT / "destino.json").read_text())["selections"]["neta_30000"]
    out["capacity_left"] = round(keep, 3)
    out["long_term"] = {"gross_ls": round(D["gross_ls"] * keep, 1), "net_ls": round(D["net_mean"] * keep, 1),
                        "gross_ls_nominal": D["gross_ls"], "net_ls_nominal": D["net_mean"]}
    return out


if __name__ == "__main__":
    res = {"karst": karst(), "interflow": interflow(), "sediment": sediment()}
    (ROOT / "sensibilidad.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps(res, ensure_ascii=False, indent=1))
