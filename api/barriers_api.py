"""barriers endpoints — owned by the barriers workstream. Mounted in api/main.py."""
import ee
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pipeline import barriers, barriers_mcmf

router = APIRouter()


class BarriersIn(BaseModel):
    lon: float
    lat: float
    budget_m: float = Field(1500, gt=0, le=20000)
    window_m: float = Field(1200, ge=300, le=3000)
    method: str = "area"        # "area": greedy by intercepted area | "flujo": max retention with capacity (Dinic oracle)
    storm_mm: float = Field(10, gt=0, le=200)


@router.post("/barriers")
def optimize_barriers(body: BarriersIn):
    """Where to place contour barriers / check dams in a window around a site."""
    try:
        if body.method == "flujo":
            r = barriers_mcmf.optimize(body.lon, body.lat, body.budget_m, body.window_m, storm_mm=body.storm_mm)
            r.pop("_grid", None)
            t = r["totals"]
            r["notes"] = ["", f"Tormenta de diseño de {body.storm_mm:g} mm; cada barrera almacena e infiltra {barriers_mcmf.CAP_M3_PER_M} m³ por metro.",
                          "Selección lazy greedy (CELF); el agua retenida se calcula como flujo máximo con el algoritmo de Dinic, "
                          "equivalente al flujo máximo de costo mínimo (informe, P14).",
                          f"Las barreras llenas ({t['full_barriers']} de {t['n_barriers']}) indican que limita la capacidad, no la posición."]
            return r
        return barriers.optimize(body.lon, body.lat, body.budget_m, body.window_m)
    except ee.EEException as e:
        raise HTTPException(502, str(e))
