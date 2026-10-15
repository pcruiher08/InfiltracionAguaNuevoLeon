"""Calibrate the runoff coefficient against CONAGUA's official natural runoff for Cerro Prieto.

    .venv/bin/python -W ignore informe/calibracion.py              # Earth Engine: model vs observed runoff
    .venv/bin/python informe/calibracion.py --posterior            # reweight the destino.py samples
Writes informe/calibracion.json.

Cerro Prieto dam catchment = Río Pablillo 1 + Río Camacho + Río Pablillo 2 (Región Hidrológica 25).
Natural mean annual runoff Cp from CONAGUA's open data (Disponibilidad media de agua superficial
por cuenca); areas from the DOF technical study of 28 July 2017.
"""
import json
import sys
from pathlib import Path

import ee

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from pipeline import layers, optimize as O  # noqa: E402

CP_HM3 = {"Río Pablillo 1": 111.254, "Río Camacho": 88.55, "Río Pablillo 2": 62.777}
AREA_KM2 = {"Río Pablillo 1": 974.97, "Río Camacho": 431.93, "Río Pablillo 2": 169.87}


def main():
    layers.init()
    raw = layers.raw()
    c = O.runoff_coefficient(raw.select("slope_deg"), raw.select("ndvi")).rename("c")
    rain = raw.select("rain_mm")
    geom = layers.catchments()["cerro_prieto"]
    geom = geom.geometry() if hasattr(geom, "geometry") else geom
    img = ee.Image.cat([rain, c, rain.multiply(c).rename("pc")]).updateMask(layers.valid_mask())
    st = img.reduceRegion(ee.Reducer.mean(), geom, 90, maxPixels=1e10, bestEffort=True).getInfo()
    area_hb = ee.Image.pixelArea().reduceRegion(ee.Reducer.sum(), geom, 90, maxPixels=1e10, bestEffort=True).getInfo()["area"] / 1e6
    q_obs_mm = sum(CP_HM3.values()) / sum(AREA_KM2.values()) * 1000          # hm³ / km² -> mm
    q_mod_mm = st["pc"]
    out = {"cp_hm3": CP_HM3, "area_km2": AREA_KM2, "area_hydrobasins_km2": round(area_hb),
           "rain_mm": round(st["rain_mm"], 1), "c_model_mean": round(st["c"], 3),
           "q_obs_mm": round(q_obs_mm, 1), "q_model_mm": round(q_mod_mm, 1),
           "ce_obs": round(q_obs_mm / st["rain_mm"], 3), "f_hat": round(q_obs_mm / q_mod_mm, 3)}
    print(out)
    (ROOT / "calibracion.json").write_text(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__" and "--posterior" not in sys.argv:
    main()


# ---------------------------------------------------------------- Bayesian update of the Monte Carlo samples
SIGMA_REL = (0.10 ** 2 * 3) ** 0.5      # CHIRPS bias, catchment-boundary mismatch and Cp, ~10 % each


def posterior():
    """Reweight the destino.py samples by the likelihood of the calibrated runoff factor (importance sampling)."""
    import numpy as np
    cal = json.loads((ROOT / "calibracion.json").read_text())
    D = json.loads((ROOT / "destino.json").read_text())
    f = np.array(D["f_C_samples"]); fh = cal["f_hat"]; sd = SIGMA_REL * fh
    w = np.exp(-0.5 * ((f - fh) / sd) ** 2); w /= w.sum()
    ess = 1 / (w ** 2).sum()

    def wq(x, p):
        o = np.argsort(x); cw = np.cumsum(w[o]); return float(x[o][np.searchsorted(cw, p / 100)])
    out = {"sigma": round(sd, 3), "ess": round(float(ess)), "f_post_mean": round(float((w * f).sum()), 3),
           "f_prior_mean": round(float(f.mean()), 3), "selections": {}}
    for key, s in D["selections"].items():
        x = np.array(s["samples"][:len(f)]); xd = np.array(s["samples_drought"][:len(f)])
        out["selections"][key] = {"net_ls": [round(wq(x, p), 1) for p in (5, 50, 95)], "net_mean": round(float((w * x).sum()), 1),
                                  "p_pos": round(100 * float(w[x > 0].sum()), 1),
                                  "gross_ls": round(s["gross_ls"] * out["f_post_mean"] / out["f_prior_mean"], 1),
                                  "net_drought_mean": round(float((w * xd).sum()), 1)}
    cal["posterior"] = out
    (ROOT / "calibracion.json").write_text(json.dumps(cal, ensure_ascii=False))
    print(out)


if __name__ == "__main__" and "--posterior" in sys.argv:
    posterior()
