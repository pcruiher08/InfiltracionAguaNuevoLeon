# Estado del proyecto — Reto 1 · Infiltración (ZMM)

Documento de trabajo a **14 de octubre de 2026**. Resume qué se investigó, qué datos se usan,
qué construimos, qué se probó y qué podemos (y no podemos) afirmar hoy.

> **Idea central:** es una herramienta de **priorización transparente**, no un modelo hidrológico.
> El índice mide **potencial relativo** de infiltración/restauración, **no volumen infiltrado**.

---

## 1. El reto

**Pregunta:** ¿dónde restaurar suelos en partes altas para favorecer la infiltración?

Contexto dado por los organizadores:

| Dato | Valor | Estado de verificación |
|---|---|---|
| Capacidad de Cerro Prieto y La Boca en lo más crítico de 2022 | < 5 % | Solo respaldado por un texto de opinión del grupo legislativo PAN (HCNL, mar 2023). Falta fuente técnica (Conagua/SADM). |
| Disponible vs. consumo regular (2022) | 13,500 vs 16,500 L/s | Misma fuente. Conagua 2022 da demanda de 16,180 L/s. |
| Capacidad de las presas principales al 12 oct 2026 | 63.5 % (925.5 Mm³) | **Confirmado** (SADM y Conagua vía MVS: 925.539 Mm³). El 63.5 % es un cálculo propio (925.539 / 1,458.1); con la suma real de NAMO daría 63.7 %. Citar como "~63.5 %" con fecha. |

Estado actual por presa (SADM, 12 oct 2026): Cerro Prieto 82.9 %, La Boca 97.9 %, El Cuchillo 57.6 %.
Nota: la declaratoria de febrero de 2022 reportó Cerro Prieto 9.88 %, La Boca 25.28 % y El Cuchillo 53.98 %
(según prensa; **el PDF oficial es una infografía de 1 página y no pudo leerse**). Esto no coincide con el
"< 5 %" del reto, que probablemente es un mínimo posterior; conviene confirmarlo.

Las dos opciones planteadas por el reto:
- **Opción A — Índice de prioridad:** cruza humedad, vegetación, pendiente, suelo e incendios → mapa alta/media/baja.
- **Opción B — Cartera de obras:** barreras de piedra o de material vegetal muerto, según el sitio.

Este repo implementa **ambas**.

---

## 2. Qué construimos

App web (FastAPI + Earth Engine + Leaflet). Estructura:

| Archivo | Función |
|---|---|
| `pipeline/config.py` | Área de estudio, IDs de datasets, pesos y cortes de clase |
| `pipeline/layers.py` | Puntajes 0–1 por criterio en Earth Engine, índice ponderado, robustez, muestreo por sitio |
| `pipeline/obras.py` | Reglas para recomendar tipo de obra (determinista, con razones) |
| `pipeline/ficha.py` | Ficha de obra en Markdown (sin LLM en tiempo de ejecución) |
| `api/main.py` | Endpoints `/api/config`, `/api/tiles`, `/api/robustness`, `/api/site` |
| `web/index.html` | Mapa, sliders de pesos, capa de robustez, clic → ficha + descarga `.md` |
| `analysis/` | Scripts de la validación descrita en la sección 5 |

### Qué hace
1. **Mapa de prioridad** (baja / media / alta) sobre las cuencas altas de Santa Catarina, Ramos y Pilón.
2. **Pesos ajustables:** el usuario cambia la importancia de cada criterio y el mapa se recalcula.
3. **Mapa de robustez:** corre 40 ponderaciones aleatorias y muestra dónde un píxel sale "alta prioridad"
   sin importar cómo se ponderen los criterios.
4. **Ficha por sitio:** al hacer clic recomienda la obra, espaciamiento y metros lineales por hectárea,
   con las razones, riesgos y nivel de confianza.

### Datos usados (todos abiertos, en Earth Engine)

| Criterio | Dataset | ID en Earth Engine | Peso |
|---|---|---|---|
| Pendiente | NASADEM | `NASA/NASADEM_HGT/001` | 0.25 |
| Vegetación degradada | Sentinel-2 SR (NDVI, feb–may, últimos 2 años) | `COPERNICUS/S2_SR_HARMONIZED` | 0.30 |
| Suelo permeable | OpenLandMap (arena − arcilla) | `OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02`, `..._CLAY-...` | 0.10 |
| Incendios | MODIS área quemada (500 m) | `MODIS/061/MCD64A1` | 0.15 |
| Humedad (suelo seco) | SMAP L4 (~9 km) | `NASA/SMAP/SPL4SMGP/008` | 0.10 |
| Lluvia | CHIRPS diario | `UCSB-CHG/CHIRPS/DAILY` | 0.10 |
| Máscara (excluye urbano y agua) y cobertura en la ficha | ESA WorldCover | `ESA/WorldCover/v200` | — |

Las 9 capas se verificaron cargando en Earth Engine (proyecto `infiltracionaguanuevoleon`).

**Cómo puntúa la pendiente:** el puntaje sube de 0° a 8° y baja linealmente hasta 0 en 45°; la mejor zona
es 8–25° (suficiente escorrentía y aún trabajable).

### Reglas de obra (`pipeline/obras.py`)
En orden de prioridad:
1. Pendiente > 35° → **no intervenir** (exclusión y regeneración natural).
2. Incendio en los últimos 3 años → **barreras de material vegetal muerto**.
3. Pendiente ≥ 8° y suelo grueso → **barreras de piedra acomodada**.
4. Pendiente < 15°, NDVI < 0.35 y suelo no arcilloso → **zanja-bordo + reforestación con nativas**.
5. NDVI < 0.35 → **reforestación con nativas + barreras de material vegetal**.
6. Si no → **conservar la cobertura existente**.

Espaciamiento: `1 m / tan(pendiente)` entre líneas de barrera. **Los umbrales son orientativos** y deben
validarse con CONAFOR y Pronatura antes de presentarse como recomendaciones.

---

## 3. Cómo correrlo

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install "earthengine-api==1.6.0"   # solo si tu Python es 3.9 (ver sección 4)
.venv/bin/earthengine authenticate      # tu cuenta necesita acceso al proyecto de Earth Engine
uvicorn api.main:app --reload           # http://localhost:8000
```

Tiempos medidos: tiles ~2 s; consulta de un sitio ~18 s.

---

## 4. Cambios hechos en esta rama (`run-local-test`)

1. **`api/main.py`:** `dict[str, float] | None` no funciona en Python 3.9 → `Optional[Dict[str, float]]`.
2. **`pipeline/ficha.py`:** la cobertura salía "s/d" porque Earth Engine devuelve `10.000000000000002`
   en lugar de `10`; ahora se redondea antes de buscar en el diccionario.
3. **`analysis/`:** scripts de muestreo y análisis (sección 5).
4. Este documento.

Nota de entorno: `earthengine-api` 1.6.15 requiere Python ≥ 3.10 (el CLI falla en 3.9 con
`unsupported operand type(s) for |`). Con Python 3.9 funciona `earthengine-api==1.6.0`.
`requirements.txt` **no se modificó**; solo se verificó la 1.6.0.

---

## 5. Pruebas hechas y resultados

Todo el análisis usa una muestra de **4,334 puntos** (escala 500 m, semilla fija) extraída en una sola
llamada a Earth Engine (~4 s). Reproducible con `analysis/sample_points.py` y `analysis/analyze_sample.py`.

### 5.1 Criterio de humedad (SMAP)
- La distribución es **bimodal**: percentiles 5/25/50/80/95 = 0.067 / 0.077 / 0.089 / 0.288 / 0.346.
- El código normaliza de 0.06 a 0.15, así que el **38 % de los puntos** queda con puntaje 0.
- Reescalar a 0.06–0.25 casi no mueve el índice (p80: 0.559 → 0.567); los cortes 0.45/0.55 siguen razonables.
- **Conclusión:** el criterio es grueso (~9 km) y aporta poco con peso 0.10. Reescalarlo no es prioridad.

### 5.2 Validación contra cicatrices de incendio 2022
Se tomaron las cicatrices de MODIS de marzo a mayo de 2022 en pendiente > 8° (solo **31 píxeles**) y se
revisó qué porcentaje cae en el 20 % superior del índice.

| Escenario | Quemados en el 20 % superior | No quemados en el 20 % superior |
|---|---|---|
| Pesos por defecto | 6 % | 20 % |
| Humedad reescalada | 10 % | 20 % |
| Sin criterio de incendio (no circular) | 3 % | 20 % |

Sin el criterio de incendio, el índice promedio en zonas quemadas (0.506) es **menor** que fuera (0.555).

**Resultado: el índice NO prioriza las zonas quemadas en 2022.** Hipótesis (sin probar):
- El NDVI usa los últimos 2 años (2024–2026) y la vegetación ya se recuperó parcialmente.
- El criterio de incendio pesa solo 0.15.
- 31 píxeles es una muestra chica y MODIS a 500 m es grueso para este incendio.

### 5.3 Servidor
Los cuatro endpoints y la página web responden. **No se revisó visualmente el mapa** (HTML/JavaScript de Leaflet).
Ejemplo (-100.3, 25.35): prioridad media (0.49), barreras de piedra, líneas cada ~4.4 m, ~2,265 m lineales/ha.

---

## 6. Qué podemos decir hoy

**Con respaldo**
- Usa datos abiertos y reproducibles; cada recomendación explica por qué.
- Cubre las dos opciones del reto de punta a punta (mapa, robustez, ficha descargable).
- Dice explícitamente que mide potencial relativo, no volumen infiltrado.
- El contexto de urgencia es real: presas en ~63.5 % (12 oct 2026) y 30 % menos que hace un año según MVS (25 sep 2026).

**Sin respaldo (no afirmar)**
- Que el índice esté **validado**. No hay contraste con sitios reales (incendios de CONAFOR, obras de Pronatura, pozos).
  Los cortes alta/media/baja se calibraron el 2026-10-14 con la propia distribución del mapa.
- Que el índice priorice zonas quemadas: la prueba de 5.2 dice lo contrario.
- Que las obras recomendadas sean viables: los umbrales son orientativos.
- Cuánta agua se infiltraría.
- Que el área de estudio sea la cuenca real: es un rectángulo (`[-100.65, 24.75, -99.55, 25.75]`).

**Sobre el umbral de 35°:** no es un umbral oficial. El Reglamento de Zonificación de Monterrey usa porcentaje
(> 45 %, ~24°, no urbanizable; 30–45 % exige estudio geológico) y el Atlas de Riesgo estatal habla de > 30° para
inestabilidad. Presentarlo como "criterio técnico a validar".

---

## 7. Datos y verificación de la charla del orador

Se contrastó lo que dijo el orador con fuentes públicas. Para el pitch:

| Afirmación | Veredicto | Cómo decirlo |
|---|---|---|
| 27 mil ha quemadas; "La Contera", "La Cebolla" | **No confirmada.** | El incendio documentado de 2022 es Sierra de Santiago; las cifras van de ~5 mil ha (Protección Civil) a 14–20 mil ha (prensa/UANL). No usar "27 mil". |
| Sentinel-2 para SO₂/NO₂/CO | **Error** | Esos gases los mide Sentinel-5P/TROPOMI. Sentinel-2 es para vegetación y agua. |
| "LANSA" | Casi seguro Landsat | Inferencia, no confirmada. |
| "ENSIMA" | Es **SIMA** | Sistema Integral de Monitoreo Ambiental. |
| Cuchillo al 50 % | Parcial | SADM: 57.6 % al 12 oct 2026. Citar con fecha. |
| Cuchillo II aporta 5 m³/s; ZMM demanda ~16 m³/s | Confirmado | Conagua 2022: 16,180 L/s; otras fuentes 14–17 m³/s. |
| > 3,000 muertes/año por aire | Parcial | Rango 1,700–3,700 según estudio (INSP 3,700; IHME > 3,000; OCCAM 1,700). Citar fuente. |
| Cadereyta como fuente de SO₂ | Confirmado | La participación varía de 46 % a > 90 % según la fuente. |
| NDVI/NDWI | Confirmado | Aclarar cuál NDWI (McFeeters para agua; Gao hoy es NDMI). |

Las afirmaciones sobre aire y contaminación no pertenecen al Reto 1; se anotan por si salen en el pitch.

### Datos extra
- **`Distritos de riego.gpkg`** (SharePoint de Pronatura): solo **2 polígonos**, ciclo 2018-2019, EPSG:32614.
  Las Lajas (NL, 4,046 ha, 11.3 Mm³) y Bajo Río San Juan (Tamaulipas, 75,912 ha, 453.7 Mm³, 3,854 usuarios).
  Sirve para la hipótesis del orador sobre el agua liberada de El Cuchillo (NDVI sobre ese polígono), **no** para
  el índice de infiltración (son zonas de riego, no de captación).
- **Niveles de presas (SADM):** HTML sin API ni histórico; scraping viable, hay que guardar snapshots propios.
  La página tiene fechas inconsistentes (pie del 12 oct 2026, imágenes de julio 2025).
- **Datasets alternativos:** INEGI CEM 3.0 (15 m, con advertencia sobre su resolución efectiva), curvas de nivel
  1:50,000, red hidrográfica, uso de suelo Serie VII y edafología; polígonos de distritos de riego en CONAGUA (REST).

---

## 8. Limitaciones conocidas del repo

1. **Criterio de humedad** casi sin poder discriminante (sección 5.1).
2. **Sin validación externa** y cortes de clase calibrados con la misma distribución.
3. **Área de estudio rectangular**, no las cuencas reales (la nota en `config.py` sugiere HydroSHEDS nivel 8/9).
4. **MODIS a 500 m** para incendios; Sentinel-2 dNBR (10–20 m) sería más fino.
5. **Peso del suelo bajo (0.10):** OpenLandMap casi no varía en el área.
6. **El mapa no se revisó visualmente** en esta sesión.

## 9. Pendientes y opciones

| Opción | Esfuerzo | Notas |
|---|---|---|
| Dejar el índice como está y presentar la limitación con honestidad | 0 | Recomendada con poco tiempo. |
| Subir el peso de incendio (0.15 → 0.25–0.30) | ~5 min | Es forzar el resultado; habría que decirlo. |
| dNBR de Sentinel-2 (antes/después) en lugar de MODIS | ~20–30 min | Más fino; podría mejorar la validación. |
| Panel de contexto con niveles de presas (SADM) | ~30 min | Abre el pitch; requiere snapshots propios. |
| Usar el polígono Bajo Río San Juan + NDVI | ~30 min | Apoya la historia del agua liberada; fuera del Reto 1. |
| Fijar `earthengine-api<1.6.1` en `requirements.txt` | 1 min | Para equipos con Python 3.9. |
| Validar con Pronatura/CONAFOR en campo | — | El paso más valioso. |

**Falta por obtener:** el script de infiltración de Earth Engine que dieron los organizadores (pide login; no pudo
leerse) y el PDF de la declaratoria de 2022 (infografía, requiere lectura manual u OCR).
