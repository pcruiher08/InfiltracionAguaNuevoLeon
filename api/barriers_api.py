"""barriers endpoints — owned by the barriers workstream. Mounted in api/main.py."""
import ee
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pipeline import barriers

router = APIRouter()


class BarriersIn(BaseModel):
    lon: float
    lat: float
    budget_m: float = Field(1500, gt=0, le=20000)
    window_m: float = Field(1200, ge=300, le=3000)


@router.post("/barriers")
def optimize_barriers(body: BarriersIn):
    """Where to place contour barriers / check dams in a window around a site."""
    try:
        return barriers.optimize(body.lon, body.lat, body.budget_m, body.window_m)
    except ee.EEException as e:
        raise HTTPException(502, str(e))
