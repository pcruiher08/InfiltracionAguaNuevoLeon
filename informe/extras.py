"""Optimization summaries used by the report: both gross-water modes at 3,000 ha, the hectares needed
for given targets, and the retention table.

    .venv/bin/python -W ignore informe/extras.py
Writes informe/extras.json.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from pipeline import layers, optimize as O  # noqa: E402

KEEP = ("impact", "drought")


def main():
    layers.init()
    out = {}
    for mode in ("max", "balanced", "net"):
        r = O.optimize(3000, mode)
        out[mode] = {k: r[k] for k in KEEP}
        out[mode]["m3"] = r["totals"]["m3_per_year"]
        out[mode]["by_supply"] = r["by_supply"]
        print(mode, r["impact"], flush=True)
    out["targets"] = [O.for_target(t) for t in (25, 50, 100, 200)]
    out["retention"] = {"rain": list(O.RETENTION_RAIN), "frac": list(O.RETENTION_FRAC)}
    (ROOT / "extras.json").write_text(json.dumps(out, ensure_ascii=False))
    print("wrote extras.json", out["targets"])


if __name__ == "__main__":
    main()
