"""Análisis local de analysis/sample.json (generado por sample_points.py).

Uso (desde la raíz del repo):  python analysis/sample_points.py && python analysis/analyze_sample.py
Evalúa (1) la distribución del criterio de humedad y (2) si el índice prioriza
las cicatrices de incendio de 2022 (MODIS MCD64A1, mar–may 2022, pendiente > 8°).
"""
import json

rows = json.load(open("analysis/sample.json"))
W = {"slope": 0.25, "vegetation": 0.30, "soil": 0.10, "fire": 0.15, "moisture": 0.10, "rain": 0.10}


def pct(xs, p):
    xs = sorted(xs)
    return xs[int(p / 100 * (len(xs) - 1))]


def new_moisture(r, lo=0.06, hi=0.25):
    return min(1, max(0, 1 - (r["sm"] - lo) / (hi - lo)))


steep = [r for r in rows if r["slope_deg"] > 8]
sm = [r["sm"] for r in rows if r.get("sm") is not None]
print("n =", len(rows), "| pendiente > 8°:", len(steep))
print("SMAP sm p5/p25/p50/p80/p95:", [round(pct(sm, p), 3) for p in (5, 25, 50, 80, 95)])
mo = [r["moisture"] for r in rows]
print("puntaje de humedad actual en 0:", round(100 * sum(m == 0 for m in mo) / len(mo)), "%")


def score(r, w, use_new_moisture):
    t = sum(w.values())
    return sum((new_moisture(r) if (k == "moisture" and use_new_moisture) else r[k]) * v for k, v in w.items()) / t


def validate(label, w, use_new_moisture):
    ins = [r for r in steep if r["scar"] == 1]
    out = [r for r in steep if r["scar"] == 0]
    f = lambda r: score(r, w, use_new_moisture)
    cut = pct([f(r) for r in steep], 80)
    print(f"{label}: quemados n={len(ins)} | índice dentro {sum(map(f, ins)) / len(ins):.3f} "
          f"fuera {sum(map(f, out)) / len(out):.3f} | % en top 20%: dentro "
          f"{100 * sum(f(r) > cut for r in ins) / len(ins):.0f}% fuera {100 * sum(f(r) > cut for r in out) / len(out):.0f}%")


validate("pesos default", W, False)
validate("humedad reescalada 0.06–0.25", W, True)
validate("SIN criterio fire (no circular)", {**W, "fire": 0}, True)
