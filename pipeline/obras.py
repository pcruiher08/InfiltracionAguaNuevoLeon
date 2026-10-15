"""Rule-based work recommendation. Deterministic and auditable: every
recommendation carries the reasons that produced it.

Thresholds are orientative — validate against CONAFOR's soil conservation
manual and with Pronatura before presenting numbers as recommendations.
"""
import math

# sand% - clay% from OpenLandMap; spans ~0–12 in the AOI (texture class is
# uniformly "clay loam" there, so it can't discriminate on its own)
COARSE_MIN = 8   # coarser / likely stonier soils
CLAYEY_MAX = 3   # finest soils in the AOI
DENSE_NDVI = 0.55  # dry-season NDVI above this = dense cover; conserve it
VERTICAL_INTERVAL_M = 1.0      # vertical drop between barrier lines


def _spacing_m(slope_deg):
    return VERTICAL_INTERVAL_M / math.tan(math.radians(max(slope_deg, 1)))


def recommend(stats: dict) -> dict:
    slope = stats.get("slope_deg") or 0
    ndvi = stats.get("ndvi") or 0
    coarse = stats.get("sand_minus_clay") or 0
    burned = stats.get("burned") or 0
    reasons = []
    landcover = stats.get("landcover_mode")

    if landcover in (50, 80):
        what = "zona urbana" if landcover == 50 else "cuerpo de agua"
        return {"obra": "Fuera de alcance", "razones": [
            f"Cobertura dominante: {what}. El análisis cubre laderas y terrenos naturales."]}
    if slope < 8 and (stats.get("priority") or 0) < 0.45:
        return {"obra": "Fuera de alcance (terreno plano)", "razones": [
            f"Pendiente {slope:.0f}° < 8°: poco escurrimiento que frenar; no es zona de obra en laderas."]}
    if slope > 35:
        work = "No intervenir con obras: exclusión y regeneración natural"
        reasons.append(f"Pendiente {slope:.0f}° > 35°: obras inestables y riesgo para brigadas")
    elif burned >= 1:
        work = "Barreras de material vegetal muerto"
        reasons.append("Incendio en los últimos 3 años: reutilizar el material quemado")
        reasons.append("Suelo quemado tiende a repeler agua; urge frenar escurrimiento antes de lluvias")
    elif slope >= 8 and coarse >= COARSE_MIN:
        work = "Barreras de piedra acomodada"
        reasons.append(f"Pendiente {slope:.0f}° y suelo grueso (arena−arcilla {coarse:.0f}%): "
                       "probable material pétreo en sitio")
    elif slope < 15 and ndvi < 0.35 and coarse > CLAYEY_MAX:
        work = "Zanja-bordo + reforestación con nativas"
        reasons.append(f"Pendiente suave ({slope:.0f}°) y cobertura baja (NDVI {ndvi:.2f})")
    elif ndvi < 0.35:
        work = "Reforestación con nativas + barreras de material vegetal"
        reasons.append(f"Cobertura baja (NDVI {ndvi:.2f})")
    elif ndvi < DENSE_NDVI and slope >= 8:
        # Median dry-season NDVI in the AOI is ~0.39, so 0.35–0.55 is ordinary
        # scrub/open forest: still worth slowing runoff on slopes.
        work = "Barreras de material vegetal muerto en curvas de nivel"
        reasons.append(f"Cobertura media (NDVI {ndvi:.2f}) en ladera de {slope:.0f}°: "
                       "frenar escurrimiento con material vegetal del sitio")
    else:
        work = "Conservación de cobertura existente (prioridad baja de obra)"
        reasons.append(f"Cobertura aceptable (NDVI {ndvi:.2f})")

    out = {"obra": work, "razones": reasons}
    if "Barreras" in work and slope <= 35:
        spacing = _spacing_m(slope)
        out["espaciamiento_m"] = round(spacing, 1)
        out["metros_lineales_por_ha"] = round(10_000 / spacing)
    return out
