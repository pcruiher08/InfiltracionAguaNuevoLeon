# Infiltración ZMM: dónde y cómo restaurar suelo para que infiltre más agua

**Reto 1 · Infiltración**, Grok Monterrey Build Day (14 oct 2026). Planteado por Antonio Hernández Ramírez (Pronatura Noreste).

**Equipo:** Pablo César Ruíz Hernández · David Martin Oliva Zavala · Jesus Zaddkiel

> *¿Dónde restaurar suelos en partes altas para favorecer la infiltración?*

En 2022, Cerro Prieto y La Boca bajaron a menos del 5 % de su capacidad, y la ZMM tuvo ~13,500 L/s disponibles contra ~16,500 L/s de consumo. La recuperación posterior ayuda, pero no elimina la vulnerabilidad ante sequías prolongadas. Esta herramienta prioriza **dónde** intervenir en las cuencas altas que abastecen a Monterrey, recomienda **qué obra** hacer en cada sitio y optimiza **exactamente dónde** trazar las barreras.

> El índice compara **potencial relativo**. **No** mide volumen de agua infiltrada.

**Demo en línea (versión estática):** https://pcruiher08.github.io/InflitracionAguaNuevoLeon/ — prioridad, robustez, cuencas de abasto y 8 sitios con barreras ya optimizadas. La versión completa e interactiva corre localmente (ver *Cómo correrlo*); la estática se regenera con `python -m pipeline.build_static`.

**Documento en PDF:** [`docs/infiltracion-zmm.pdf`](docs/infiltracion-zmm.pdf) · [en línea](https://pcruiher08.github.io/InflitracionAguaNuevoLeon/infiltracion-zmm.pdf).

---

## La solución en 4 piezas

| # | Pieza | Pregunta que responde |
|---|---|---|
| 1 | **Mapa de prioridad** con pesos ajustables | ¿Dónde conviene restaurar? |
| 2 | **Mapa de robustez** | ¿Qué sitios son prioritarios sin importar cómo se ponderen los criterios? |
| 3 | **Ficha de obra** por sitio (motor de reglas) | ¿Qué obra hacer aquí y por qué? |
| 4 | **Optimizador de ubicación de barreras** | ¿Exactamente dónde trazar las barreras para interceptar más escurrimiento? |

Todo es **determinista y auditable**: no hay modelos de lenguaje en la aplicación. Cada recomendación muestra las razones que la produjeron.

---

## Cómo funciona

### 1. Área de análisis: las cuencas que abastecen a la ZMM

En lugar de un rectángulo, el análisis cubre la **unión de las cuencas de abasto**, ~10,500 km². Para delimitarlas:

- Se ubicaron las presas con datos de agua superficial (JRC): La Boca ≈ 3.8 km², Cerro Prieto ≈ 20 km², El Cuchillo ≈ 43 km².
- Desde cada fuente se trazó la cuenca aguas arriba con **HydroBASINS nivel 12**, recorriendo los enlaces `HYBAS_ID → NEXT_DOWN`.

| Cuenca | Área | Papel en el abasto | Conectividad |
|---|---|---|---|
| Presa La Boca | 347 km² | Presa de abasto directo | **1.0** |
| Presa Cerro Prieto (río Pablillo) | 1,758 km² | Presa de abasto directo | **1.0** |
| Río Santa Catarina aguas arriba de Monterrey | 1,392 km² | Recarga de pozos y galerías de SADM | **1.0** |
| Resto de la cuenca de El Cuchillo | 8,744 km² (incluye las anteriores salvo Cerro Prieto) | Abasto mayor, pero lejano | **0.6** |

Los niveles de conectividad (1.0 y 0.6) son un **supuesto explícito**, ajustable en `pipeline/config.py`.

### 2. Índice de prioridad

Se calculan siete criterios en Google Earth Engine. Cada uno se normaliza a 0–1, donde 1 significa más prioridad para restaurar, y luego se combinan con una suma ponderada.

| Criterio | Qué captura | Peso por defecto |
|---|---|---|
| Pendiente | Laderas que generan escurrimiento y aún se pueden trabajar. Máximo entre 8° y 25°; baja a 0 hacia los 45°. | 0.20 |
| Vegetación degradada | NDVI bajo en temporada seca (Sentinel-2, feb–may): hay más que ganar | 0.25 |
| Suelo permeable | Arena − arcilla (%). Pesa poco porque en la zona casi no varía. | 0.05 |
| Incendios | Área quemada entre 2019 y 2026: 1 si fue en los últimos 3 años, 0.5 si antes | 0.10 |
| Suelo seco | Humedad superficial SMAP en temporada seca | 0.10 |
| Lluvia | Precipitación media anual (CHIRPS): más agua por captar | 0.10 |
| **Conexión con abasto** | Si drena directo a una fuente de la ZMM (ver tabla anterior) | 0.20 |

- **Clases:** alta si el índice supera 0.55, media entre 0.45 y 0.55, baja por debajo. Los umbrales se calibraron con la distribución real en laderas de más de 8°: equivalen a la mediana (~p50) y a ~p80.
- **Exclusiones:** zonas urbanas y cuerpos de agua (ESA WorldCover). El mapa muestra por defecto solo laderas de 8° o más.

### 3. Robustez

Se recalcula el índice con **40 combinaciones aleatorias de pesos**. Para cada píxel se cuenta en qué porcentaje de esas combinaciones queda como prioridad alta. Los sitios con ≥ 50 % son prioritarios **sin importar cómo ponderen los criterios los expertos**: convierte el desacuerdo entre expertos en un resultado, en lugar de una debilidad.

### 4. Ficha de obra (motor de reglas)

Al hacer clic en un sitio se muestrean las métricas en un radio de 250 m y se aplican reglas explícitas (`pipeline/obras.py`):

- **Urbano, agua, o plano con prioridad baja** → fuera de alcance.
- **Pendiente > 35°** → no construir obras; exclusión y regeneración natural.
- **Quemado recientemente** → barreras de material vegetal muerto, reutilizando el material quemado.
- **Pendiente ≥ 8° con suelo grueso** → barreras de piedra acomodada.
- **Pendiente suave con cobertura baja** → zanja-bordo + reforestación con nativas.
- **Ladera (≥ 8°) con cobertura media** (NDVI 0.35–0.55, lo típico en la zona) → barreras de material vegetal muerto en curvas de nivel.
- **Cobertura densa** (NDVI ≥ 0.55) → conservar la cobertura existente.

Para las barreras, el espaciamiento se calcula como intervalo vertical (1 m) / tan(pendiente), de donde salen los metros lineales por hectárea. La ficha se descarga en Markdown e incluye diagnóstico, datos, obra recomendada, dimensionamiento, riesgos y nivel de confianza.

### 5. Optimizador de ubicación de barreras

Dentro de una ventana de ~1.2 km alrededor del sitio (`pipeline/barriers.py`):

1. **Relieve:** se descarga el DEM (NASADEM, 30 m) en UTM 14N, con margen extra para incluir el escurrimiento que llega desde ladera arriba.
2. **Hidrología en numpy:** relleno de depresiones (priority-flood), direcciones de flujo D8 y acumulación de flujo.
3. **Candidatas:** curvas de nivel cada 2–5 m de desnivel, según la pendiente, cortadas en segmentos de ~45 m.
4. **Cárcavas:** donde una curva cruza flujo concentrado (≥ 5 ha aguas arriba), el cruce se marca como **presa de piedra o gaviones en cárcava**. Los cauces de más de 100 ha se excluyen.
5. **Optimización:** dado un presupuesto en metros lineales, se eligen de forma voraz los segmentos que **interceptan más área de ladera arriba por metro**. Cada barrera retiene ~60 % de lo que le llega, así que las que quedan más abajo solo reciben crédito por lo que sigue escurriendo.
6. **Resultado:** barreras numeradas por prioridad, presas en cárcavas, red de escurrimiento, % de escurrimiento interceptado (relativo) y descarga en GeoJSON para SIG o apps de campo. Tarda ~0.5 s por sitio.

| Sitio | Presupuesto | Barreras | % de la ventana interceptado |
|---|---|---|---|
| Pilón (-100.05, 25.00) | 1,500 m | 37 | 60 % |
| Santa Catarina (-100.45, 25.45) | 1,500 m | 37 | 61 % |
| Santa Catarina (-100.45, 25.45) | 3,000 m | 74 | 77 % |

Duplicar el presupuesto rinde cada vez menos (61 % → 77 %), que es el comportamiento esperado de una buena optimización: los primeros metros van a donde más se intercepta.

---

## ¿Por qué estos sitios?

La demo en línea muestra 8 sitios de ejemplo. **No son una selección manual.** Salen de un procedimiento reproducible (`pipeline/build_static.py`):

1. **Barrido:** se recorre una malla de puntos cada 0.06° (~6 km) sobre las cuencas de abasto.
2. **Filtro de prioridad:** se queda con los puntos de **prioridad alta** (índice > 0.55) en laderas **trabajables** (8°–35°).
3. **Orden:** se ordenan por índice de prioridad, de mayor a menor.
4. **Dispersión:** se descartan los puntos a menos de ~12 km de uno ya elegido, para cubrir distintas zonas de la Sierra.
5. **Obra:** solo se conservan los sitios donde el motor de reglas recomienda una **obra de barreras o zanjas**. Así se excluyen los sitios a conservar o a no intervenir.
6. **Barreras:** en cada sitio se optimizan barreras con un presupuesto de 1,500 m lineales.

| # | Sitio (lat, lon) | Cuenca | Prioridad | Robustez* | Pendiente · NDVI | Qué la hace prioritaria | Obra recomendada | Barreras · m · % interceptado |
|---|---|---|---|---|---|---|---|---|
| 1 | 25.69, -100.58 | Santa Catarina | 0.72 | 85% | 12° · NDVI 0.32 | conexión con abasto, pendiente trabajable, suelo permeable | Barreras de piedra acomodada | 36 · 1,497 m · 56% |
| 2 | 25.51, -100.58 | Santa Catarina | 0.57 | 61% | 26° · NDVI 0.51 | conexión con abasto, suelo seco, pendiente trabajable | Barreras de material vegetal muerto en curvas de nivel | 39 · 1,492 m · 57% |
| 3 | 25.33, -100.40 | Santa Catarina | 0.64 | 95% | 31° · NDVI 0.42 | suelo permeable, conexión con abasto, suelo seco | Barreras de piedra acomodada | 36 · 1,488 m · 67% |
| 4 | 25.21, -100.22 | El Cuchillo | 0.58 | 38% | 11° · NDVI 0.25 | pendiente trabajable, vegetación degradada, conexión con abasto | Zanja-bordo + reforestación con nativas | 37 · 1,488 m · 50% |
| 5 | 25.45, -100.40 | Santa Catarina | 0.56 | 48% | 26° · NDVI 0.43 | conexión con abasto, pendiente trabajable, suelo permeable | Barreras de material vegetal muerto en curvas de nivel | 38 · 1,493 m · 44% |
| 6 | 24.97, -100.10 | El Cuchillo | 0.56 | 36% | 22° · NDVI 0.26 | pendiente trabajable, suelo permeable, vegetación degradada | Barreras de piedra acomodada | 35 · 1,486 m · 52% |
| 7 | 25.21, -100.40 | El Cuchillo | 0.55 | 66% | 31° · NDVI 0.41 | suelo permeable, suelo seco, pendiente trabajable | Barreras de piedra acomodada | 38 · 1,496 m · 77% |
| 8 | 25.69, -100.40 | Santa Catarina | 0.56 | 59% | 33° · NDVI 0.42 | conexión con abasto, suelo seco, suelo permeable | Barreras de piedra acomodada | 40 · 1,499 m · 70% |

\* **Robustez:** porcentaje de 40 ponderaciones aleatorias de los criterios en que el sitio queda como prioridad alta.

**Cómo leer la tabla:**

- **El sitio 1 es el de mayor prioridad (0.72) y muy robusto (85 %).** Drena directo a la cuenca del Santa Catarina, que recarga pozos y galerías de SADM; tiene pendiente trabajable (12°), suelo de los más gruesos de la zona y cobertura baja (NDVI 0.32). **Pero queda junto a la autopista Monterrey–Saltillo:** el optimizador aún no excluye caminos, así que hay que verificarlo en campo.
- **El sitio 3 es el más robusto (95 %).** Es prioritario casi con cualquier ponderación: suelo grueso, buena conexión con el abasto, suelo seco y una quema anterior a 2023.
- **Los sitios 4 y 6 tienen robustez menor al 40 %.** Son prioritarios con los pesos por defecto, sobre todo por pendiente y vegetación degradada, pero drenan a El Cuchillo (conexión 0.6). Si un experto le da menos peso a la vegetación o más a la conexión, bajan. Son buenos candidatos, pero **no los primeros**.
- **Cinco de los ocho están en la cuenca del Santa Catarina.** Ahí coinciden la conexión directa con el abasto (recarga de pozos de SADM), las laderas trabajables y los suelos más gruesos.
- **Ninguno está en La Boca ni en Cerro Prieto.** La cuenca de La Boca es pequeña (347 km²) y la malla de ~6 km con 12 km de separación casi no la muestrea. Del sur de Cerro Prieto faltan datos en la versión actual del asset (`scores_v1`); entran con `scores_v2`. **No significa que ahí no haya prioridad.**

### ¿Por qué las barreras quedan donde quedan?

En cada sitio, el optimizador elige las barreras así:

- **Valor de una barrera:** cada segmento de curva de nivel vale el **área de ladera arriba cuyo escurrimiento lo cruza**.
- **Selección:** se eligen primero los segmentos que interceptan **más área por metro construido**.
- **Sin duplicar crédito:** una barrera justo debajo de otra ya elegida solo recibe crédito por el ~40 % del escurrimiento que la de arriba no retiene. Por eso las barreras quedan **repartidas por la ladera**, cruzando los flujos principales, y no amontonadas en una sola línea de drenaje.
- **Cárcavas:** donde el flujo se concentra (≥ 5 ha aguas arriba), una barrera lineal no aguanta. Ahí se proponen **presas de piedra o gaviones en cárcava**, ordenadas por área de aporte.
- **Rango de pendiente:** las curvas en tramos con pendiente menor a 3° o mayor a 35° se descartan.

---

## Datos utilizados (todos abiertos)

| Dato | Fuente | Uso |
|---|---|---|
| Elevación 30 m | NASA NASADEM (`NASA/NASADEM_HGT/001`) | Pendiente, curvas de nivel, flujo |
| Imágenes 10 m | Copernicus Sentinel-2 SR (`COPERNICUS/S2_SR_HARMONIZED`) | NDVI de temporada seca, 2024–2026 |
| Cobertura del suelo | ESA WorldCover v200 | Excluir zonas urbanas y agua |
| Textura, arena y arcilla | OpenLandMap (USDA) | Permeabilidad del suelo |
| Área quemada | MODIS MCD64A1 v6.1 | Incendios 2019–2026 |
| Precipitación | CHIRPS diario | Lluvia media anual 2019–2026 |
| Humedad del suelo | NASA SMAP L4 v8 | Humedad superficial en temporada seca |
| Cuencas | WWF HydroSHEDS / HydroBASINS nivel 12 | Delimitar cuencas de abasto y conectividad |
| Agua superficial | JRC Global Surface Water 1.4 | Ubicar las presas |
| Mapa base | Esri Light Gray Canvas + World Hillshade | Visualización |

---

## Qué podemos concluir

Las cifras corresponden a laderas de 8° o más y a la cobertura analizada hasta ahora. El sur de la cuenca de Cerro Prieto se incorpora con la exportación `scores_v2`.

1. **La prioridad se concentra en las laderas de la Sierra Madre.** Hay ~**110,900 ha de prioridad alta** y ~136,700 ha de prioridad media, sobre todo en las cuencas del Santa Catarina y del Pilón/Ramos.
2. **Dos tercios de la prioridad alta drenan directo a una fuente de abasto.** ~**70,700 ha (64 %)** están en las cuencas de La Boca, Cerro Prieto o Santa Catarina, y ~40,200 ha en el resto de la cuenca de El Cuchillo. Restaurar ahí beneficia directamente a la ZMM.
3. **La prioridad es robusta.** ~**77,500 ha (70 % de la prioridad alta)** se mantienen como prioridad alta en al menos la mitad de 40 ponderaciones aleatorias. Hay un núcleo de sitios donde los expertos coincidirían sin importar sus pesos.
4. **Los incendios abren una ventana de acción.** ~**16,100 ha** de prioridad alta tuvieron incendios entre 2019 y 2026. Ahí el suelo repele el agua y el material quemado sirve para barreras, así que la urgencia es mayor y el costo menor.
5. **Las laderas muy empinadas no son para obras.** Por encima de ~35–45° conviene la exclusión y la regeneración natural. La cresta central de la Sierra aparece vacía a propósito.
6. **El trazo importa tanto como el sitio.** Con 1,500 m de barreras bien ubicadas se intercepta el escurrimiento de ~60 % de una ventana de 1.2 km. Los rendimientos decrecen después, así que conviene repartir el presupuesto entre varios sitios en lugar de saturar uno.

---

## Limitaciones (dichas con honestidad)

- **El índice es relativo.** No estima metros cúbicos infiltrados.
- **El DEM de 30 m no resuelve el intervalo vertical de 1 m.** El trazo de barreras es **preliminar** y debe validarse en campo con levantamiento topográfico o dron.
- **La textura del suelo de OpenLandMap casi no varía en la zona** (todo es franco arcilloso). Un mapa edafológico de INEGI o de Pronatura mejoraría este criterio.
- **Hay supuestos sin calibrar:** los niveles de conectividad, los umbrales de cárcava (5 ha) y cauce (100 ha), y la retención por barrera (60 %). Son parámetros explícitos en el código.
- **SMAP** tiene resolución gruesa (~9 km) y **MODIS** detecta área quemada a 500 m.
- **El optimizador no excluye** caminos, construcciones ni cobertura dentro de la ventana, y no considera el acceso.
- **No se verifican las restricciones de ANP** (Parque Nacional Cumbres de Monterrey). La ficha lo señala como riesgo a revisar.

---

## Cómo se hizo

- **Herramientas:** Google Earth Engine (Python) para todo el análisis raster, FastAPI como backend, Leaflet en el navegador y numpy + contourpy para la hidrología local.
- **Desarrollo agéntico:** se construyó en un día con agentes de código. La pieza central y la integración se hicieron en la sesión principal; el optimizador de barreras lo construyó un agente en paralelo, contra un contrato de API fijo.
- **Calibración con datos reales**, no con supuestos de escritorio:
  - Se midieron percentiles de cada capa en la zona y se ajustaron los rangos de normalización: lluvia 350–850 mm y humedad 0.06–0.15 m³/m³.
  - Se descubrió que la clase de textura es constante en toda el área y se cambió a arena − arcilla continua.
  - Los umbrales de clase salen de la distribución real del índice en laderas.
- **Rendimiento:** calcular en vivo tardaba 25–40 s por tesela del mapa. Las capas se precalculan una vez como asset de Earth Engine (`pipeline/export.py`) y el mapa responde en ~0.3 s; el análisis de un sitio, en ~0.7 s.
- **Visualización:**
  - Prioridad en una sola escala de azul (agua) y robustez en naranja; ambas paletas se validaron para daltonismo.
  - Mapa base con relieve sombreado, con las etiquetas por encima de los datos.
  - Contornos de las cuencas de abasto y las presas, para orientar.

---

## Cómo correrlo

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
earthengine authenticate          # una vez; tu cuenta necesita acceso al proyecto de Earth Engine
python -m pipeline.export          # una vez (~20–30 min): precalcula las capas como asset
uvicorn api.main:app --port 8765   # http://localhost:8765
```

- El proyecto de Earth Engine por defecto es `infiltracionaguanuevoleon`. Para usar otro, define `EE_PROJECT` en `.env`.
- La app usa el asset `scores_v2` si existe; si no, `scores_v1`; si no hay ninguno, calcula en vivo (lento).
- Vuelve a correr `pipeline.export` si cambias la lógica o la calibración de las capas. Los cambios de pesos y de visualización son instantáneos.

## Estructura

```
pipeline/
  config.py       Cuencas, datasets, pesos, umbrales, asset
  catchments.json IDs de HydroBASINS de cada cuenca de abasto
  layers.py       Criterios en Earth Engine, índice, robustez, conectividad, muestreo de sitio
  export.py       Precálculo de capas como asset de Earth Engine
  obras.py        Motor de reglas: sitio → tipo de obra, razones, espaciamiento
  ficha.py        Ficha de obra en Markdown
  barriers.py     Optimizador de ubicación de barreras (DEM → flujo → curvas → selección)
api/
  main.py         /api/config, /api/tiles, /api/summary, /api/basins, /api/robustness, /api/site
  barriers_api.py /api/barriers
web/
  index.html      Mapa, controles, leyenda, ficha
  barriers.js     Panel del optimizador de barreras
```

## Próximos pasos

- **Validar en campo** con Pronatura un conjunto de sitios de prioridad alta y robusta, y calibrar los umbrales.
- **Monitor post-incendio:** detectar incendios nuevos (FIRMS + severidad dNBR) y generar fichas automáticamente.
- **Portafolio de inversión:** dado un presupuesto, elegir el mejor conjunto de sitios con costos reales de Pronatura y CONAFOR.
- **Mejores datos:** DEM más fino (LiDAR de INEGI o dron) para el trazo, y edafología de INEGI para el suelo.

---

## Equipo

- Pablo César Ruíz Hernández
- David Martin Oliva Zavala
- Jesus Zaddkiel
