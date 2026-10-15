"""Deterministic site proposal sheet ("ficha de obra") in Markdown."""
from pipeline.config import CLASS_THRESHOLDS

TEXTURES = {
    1: "arcilla", 2: "arcilla limosa", 3: "arcilla arenosa", 4: "franco arcillosa",
    5: "franco arcillo-limosa", 6: "franco arcillo-arenosa", 7: "franca", 8: "franco limosa",
    9: "franco arenosa", 10: "limo", 11: "arena franca", 12: "arena",
}
LANDCOVER = {
    10: "bosque", 20: "matorral", 30: "pastizal", 40: "cultivo", 50: "urbano",
    60: "suelo desnudo / escasa vegetación", 70: "nieve", 80: "agua", 90: "humedal",
    95: "manglar", 100: "musgo/liquen",
}
CRITERIA = {
    "slope": "Pendiente", "vegetation": "Vegetación degradada", "soil": "Suelo permeable",
    "fire": "Incendios", "moisture": "Suelo seco", "rain": "Lluvia",
    "connectivity": "Conexión con fuentes de abasto",
}
CONNECTIVITY_TXT = {1.0: "drena directo a una fuente de abasto de la ZMM",
                    0.6: "cuenca de El Cuchillo (abasto lejano)", 0.0: "fuera de cuencas de abasto"}


def _level(p):
    lo, hi = CLASS_THRESHOLDS
    return "alta" if p > hi else "media" if p > lo else "baja"


def _confidence(stats):
    slope, ndvi = stats.get("slope_deg") or 0, stats.get("ndvi")
    if ndvi is None or slope > 35:
        return "baja", "Visita de campo para verificar acceso, pedregosidad y cobertura real."
    if 0.3 <= ndvi <= 0.45:
        return "media", "Fotografías de campo para confirmar el grado de degradación de la cobertura."
    return "media-alta", "Muestreo de suelo (profundidad y pedregosidad) para dimensionar la obra."


def render(lat, lon, stats, rec):
    p = stats.get("priority") or 0
    drivers = sorted(((stats.get(k) or 0, v) for k, v in CRITERIA.items()), reverse=True)[:2]
    burned = stats.get("burned") or 0
    fire_txt = ("quemado en los últimos 3 años" if burned >= 1
                else "quemado en años anteriores" if burned > 0 else "sin incendios registrados")
    conf, improve = _confidence(stats)

    lines = [
        f"## Ficha de obra · {lat:.4f}, {lon:.4f}",
        "",
        "### Diagnóstico",
        f"Prioridad **{_level(p)}** (índice {p:.2f}). Factores principales: "
        f"{drivers[0][1].lower()} ({drivers[0][0]:.2f}) y {drivers[1][1].lower()} ({drivers[1][0]:.2f}).",
        "",
        "| Variable | Valor |", "|---|---|",
        f"| Pendiente | {stats.get('slope_deg', 0):.0f}° |",
        f"| NDVI temporada seca | {stats.get('ndvi') or 0:.2f} |",
        f"| Textura de suelo | {TEXTURES.get(round(stats.get('texture_class') or 0), 's/d')} "
        f"(arena−arcilla {stats.get('sand_minus_clay') or 0:.0f}%) |",
        f"| Cobertura dominante | {LANDCOVER.get(stats.get('landcover_mode'), 's/d')} |",
        f"| Incendios | {fire_txt} |",
        f"| Lluvia media anual | {stats.get('rain_mm') or 0:.0f} mm |",
        f"| Conexión con abasto | {CONNECTIVITY_TXT.get(round(stats.get('connectivity') or 0, 1), 'parcial')} |",
        "",
        "### Obra recomendada",
        f"**{rec['obra']}**",
        *[f"- {r}" for r in rec["razones"]],
        "",
        "### Dimensionamiento orientativo",
    ]
    if "espaciamiento_m" in rec:
        lines.append(f"Líneas cada ~{rec['espaciamiento_m']} m (intervalo vertical de 1 m), "
                     f"≈ {rec['metros_lineales_por_ha']:,} m lineales por hectárea. Validar en campo.")
    else:
        lines.append("No aplica dimensionamiento de barreras para esta recomendación.")
    lines += [
        "",
        "### Riesgos y restricciones",
        "- Verificar si el sitio está dentro del Parque Nacional Cumbres de Monterrey u otra ANP.",
        "- Confirmar acceso para brigadas y disponibilidad de material.",
        *(["- Pendiente > 35°: riesgo para brigadas y obras inestables."] if (stats.get("slope_deg") or 0) > 35 else []),
        "",
        "### Confianza",
        f"**{conf}**. Mejoraría con: {improve}",
        "",
        "_El índice expresa potencial relativo de infiltración; no estima volumen infiltrado._",
    ]
    return "\n".join(lines)
