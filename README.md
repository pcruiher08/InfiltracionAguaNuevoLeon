# Infiltración ZMM: dónde y cómo restaurar suelo para que infiltre más agua

**Reto 1 · Infiltración**, Grok Monterrey Build Day (14 oct 2026). Planteado por Antonio Hernández Ramírez (Pronatura Noreste).

**Equipo:** Pablo César Ruíz Hernández · David Martin Oliva Zavala · Jesus Zaddkiel Martinez Alor

> *¿Dónde restaurar suelos en partes altas para favorecer la infiltración?*

En 2022, Cerro Prieto y La Boca bajaron a menos del 5 % de su capacidad, y la ZMM tuvo ~13,500 L/s disponibles contra ~16,500 L/s de consumo. La recuperación posterior ayuda, pero no elimina la vulnerabilidad ante sequías prolongadas. Esta herramienta prioriza **dónde** intervenir en las cuencas altas que abastecen a Monterrey, recomienda **qué obra** hacer en cada sitio y optimiza **exactamente dónde** trazar las barreras.

> El índice compara **potencial relativo**. **No** mide volumen de agua infiltrada.

**Demo en línea (versión estática):** https://pcruiher08.github.io/InflitracionAguaNuevoLeon/ — prioridad, robustez, cuencas de abasto y 8 sitios con barreras ya optimizadas. La versión completa e interactiva corre localmente (ver *Cómo correrlo*); la estática se regenera con `python -m pipeline.build_static`.

**Documento en PDF:** [`docs/infiltracion-zmm.pdf`](docs/infiltracion-zmm.pdf) · [en línea](https://pcruiher08.github.io/InflitracionAguaNuevoLeon/infiltracion-zmm.pdf).

---

## La solución en 5 piezas

| # | Pieza | Pregunta que responde |
|---|---|---|
| 1 | **Mapa de prioridad** con pesos ajustables | ¿Dónde conviene restaurar? |
| 2 | **Mapa de robustez** | ¿Qué sitios son prioritarios sin importar cómo se ponderen los criterios? |
| 3 | **Ficha de obra** por sitio (motor de reglas) | ¿Qué obra hacer aquí y por qué? |
| 4 | **Optimización de captación para las presas** | Con *N* hectáreas, ¿dónde restaurar para retener más agua que llegue a cada fuente de abasto? |
| 5 | **Optimizador de ubicación de barreras** | ¿Exactamente dónde trazar las barreras para interceptar más escurrimiento? |

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

### 5. Optimización de captación para las presas

Responde la pregunta de fondo: **¿dónde restaurar para que llegue más agua a las fuentes de abasto?** (`pipeline/optimize.py`, `POST /api/optimize`).

1. **Candidatas:** todo el territorio de las cuencas de abasto se divide en **celdas de 1 km**: 3,902 celdas con área elegible.
2. **Área elegible:** dentro de cada celda solo cuentan las hectáreas donde se pueden hacer obras: pendiente de 8° a 35°, sin zona urbana ni agua y sin cobertura densa (NDVI < 0.55). En total son 192,040 ha.
3. **Agua retenida por celda:**
    - Fórmula: *lluvia media × coeficiente de escurrimiento × hectáreas elegibles × 40 % retenido*.
    - El coeficiente sube con la pendiente y con el suelo desnudo: más agua escurre y hay más que frenar.
    - El 40 % sale del propio optimizador de barreras, que retiene 41–43 % en los sitios de prueba.
4. **Agua que llega al abasto:** el agua retenida se multiplica por la conexión con la fuente (1.0 si drena directo a La Boca, Cerro Prieto o Santa Catarina; 0.6 en el resto de El Cuchillo). Cada celda se asigna a su fuente de abasto.
5. **Optimización:** dado un presupuesto de hectáreas, se eligen las celdas con más **m³ entregados por hectárea**. Es un algoritmo voraz de mochila fraccional, que es **óptimo** cuando las celdas se pueden tratar parcialmente. Hay dos modos:
    - **Máxima agua total:** el óptimo puro.
    - **Repartir entre presas:** el presupuesto se divide en partes iguales entre las 4 fuentes y se optimiza dentro de cada una.

**Resultado con 3,000 ha:**

| Fuente | Máxima agua total | | Repartir entre presas | |
|---|---|---|---|---|
| Presa La Boca | 936 ha | 1.73 M m³ | 750 ha | 1.45 M m³ |
| Acuífero Santa Catarina (pozos SADM) | 1,720 ha | 2.56 M m³ | 750 ha | 1.15 M m³ |
| Presa Cerro Prieto | 344 ha | 0.50 M m³ | 750 ha | 1.07 M m³ |
| Presa El Cuchillo | 0 ha | 0.00 M m³ | 750 ha | 0.78 M m³ |
| **Total** | 3,000 ha | **4.8 M m³/año** | 3,000 ha | **4.5 M m³/año** |

**Rendimientos decrecientes** (modo de máxima agua): 500 ha → 1.0 M m³ · 1,000 ha → 1.9 M m³ · 2,000 ha → 3.4 M m³ · 3,000 ha → 4.8 M m³ · 5,000 ha → 7.6 M m³ · 10,000 ha → 14.5 M m³ · 20,000 ha → 27.4 M m³ · 50,000 ha → 63.1 M m³.

- **La Boca rinde más por hectárea:** su cuenca recibe más lluvia que las demás.
- **El Cuchillo rinde menos:** su conexión con el abasto vale 0.6.
- **Repartir cuesta poco:** cubrir las 4 fuentes da ~7 % menos agua total que el óptimo puro.

> Los m³ son una **estimación de orden de magnitud** para comparar opciones, no un balance hídrico. El coeficiente de escurrimiento es una regla simple y la retención de 40 % es un supuesto.

### 6. Optimizador de ubicación de barreras

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

Los 8 sitios sugeridos **no se eligen a mano**. Salen directamente de la **optimización de captación**:

1. Se corre la optimización en modo **repartir entre presas** con 3,000 ha.
2. De cada fuente de abasto se toman sus **2 mejores celdas**, las que más agua retenida entregan por hectárea, y se analiza el punto central de cada una.
3. Solo se conservan los sitios donde el motor de reglas recomienda una **obra de barreras, zanjas o reforestación con barreras**. Si una celda no califica, se pasa a la siguiente de la misma fuente.
4. En cada sitio se optimizan las barreras con 1,500 m lineales.

| # | Fuente de abasto | Lugar en la optimización | m³/ha/año al abasto | Lluvia · coef. escurrimiento | Prioridad · robustez | Obra recomendada | Barreras · m · % interceptado |
|---|---|---|---|---|---|---|---|
| 1 | Presa La Boca | #1 | 2,407 | 1181 mm · 0.51 | 0.53 · 40% | Barreras de material vegetal muerto en curvas de nivel | 35 · 1,492 m · 63% |
| 2 | Presa La Boca | #12 | 1,908 | 1181 mm · 0.404 | 0.58 · 52% | Barreras de material vegetal muerto en curvas de nivel | 37 · 1,500 m · 61% |
| 3 | Acuífero Santa Catarina (pozos SADM) | #31 | 1,540 | 642 mm · 0.6 | 0.57 · 38% | Reforestación con nativas + barreras de material vegetal | 35 · 1,482 m · 70% |
| 4 | Acuífero Santa Catarina (pozos SADM) | #34 | 1,536 | 642 mm · 0.598 | 0.55 · 35% | Reforestación con nativas + barreras de material vegetal | 38 · 1,498 m · 65% |
| 5 | Presa Cerro Prieto | #45 | 1,479 | 708 mm · 0.522 | 0.63 · 60% | Barreras de piedra acomodada | 36 · 1,499 m · 65% |
| 6 | Presa Cerro Prieto | #46 | 1,455 | 658 mm · 0.554 | 0.62 · 45% | Reforestación con nativas + barreras de material vegetal | 38 · 1,489 m · 69% |
| 7 | Presa El Cuchillo | #59 | 1,182 | 665 mm · 0.573 | 0.67 · 88% | Barreras de piedra acomodada | 39 · 1,499 m · 78% |
| 8 | Presa El Cuchillo | #63 | 1,040 | 870 mm · 0.498 | 0.50 · 29% | Barreras de material vegetal muerto en curvas de nivel | 38 · 1,488 m · 53% |

**Cómo leer la tabla:**

- **Un sitio entra porque entrega mucha agua por hectárea a su fuente de abasto.** Eso pasa cuando coinciden **mucha lluvia**, **mucho escurrimiento que frenar** (pendiente y poca cobertura) y **conexión directa**.
- **La Boca encabeza la optimización.** Su cuenca es la más lluviosa (~1,000 mm o más en las mejores celdas), así que cada hectárea restaurada ahí entrega más agua.
- **El índice de prioridad mide otra cosa.** Algunos sitios óptimos para captar agua tienen prioridad media (~0.5) o robustez baja: el índice pesa también degradación, incendios y suelo, mientras que la optimización mira solo el agua que llega al abasto. **Las dos vistas se complementan**: la prioridad dice dónde el suelo más lo necesita y la optimización dice dónde rinde más el agua.
- **Ningún sitio cae en cauces ni en zonas urbanas.** El cálculo solo cuenta área elegible, y el motor de reglas descarta lo que no admite obra.

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

Cifras con la cobertura completa de las cuencas de abasto (`scores_v2`), en laderas de 8° o más.

1. **La prioridad se concentra en las laderas de la Sierra Madre.** Hay ~**141,200 ha de prioridad alta** y ~175,500 ha de prioridad media.
2. **Más de dos tercios de la prioridad alta drenan directo a una fuente de abasto.** ~**99,600 ha (71 %)** están en las cuencas de La Boca, Cerro Prieto o Santa Catarina. Restaurar ahí beneficia directamente a la ZMM.
3. **La prioridad es robusta.** ~**90,600 ha (64 % de la prioridad alta)** se mantienen como prioridad alta en al menos la mitad de 40 ponderaciones aleatorias.
4. **Los incendios abren una ventana de acción.** ~**17,100 ha** de prioridad alta tuvieron incendios entre 2019 y 2026; ahí urge actuar y el material quemado sirve para barreras.
5. **Con 3,000 ha bien elegidas se retienen del orden de 4.8 millones de m³/año** que llegan al abasto. Es una estimación de orden de magnitud. Para dimensionarla: equivale a ~152 L/s continuos, frente al déficit de ~3,000 L/s de 2022. **La restauración no sustituye otras fuentes, pero suma y es barata por hectárea.**
6. **Dónde restaurar depende del objetivo:**
    - Para maximizar agua: **La Boca y Santa Catarina**.
    - Para cubrir todas las fuentes: repartir cuesta solo ~7 % del agua total.
7. **Las laderas muy empinadas no son para obras.** Por encima de ~35–45° conviene la exclusión y la regeneración natural.
8. **El trazo importa tanto como el sitio.** Con 1,500 m de barreras bien ubicadas se intercepta el escurrimiento de ~45–75 % de una ventana de 1.2 km, y los rendimientos decrecen. Conviene repartir el presupuesto entre varios sitios en lugar de saturar uno.

---

## Limitaciones (dichas con honestidad)

- **El índice es relativo.** No estima metros cúbicos infiltrados.
- **El DEM de 30 m no resuelve el intervalo vertical de 1 m.** El trazo de barreras es **preliminar** y debe validarse en campo con levantamiento topográfico o dron.
- **La textura del suelo de OpenLandMap casi no varía en la zona** (todo es franco arcilloso). Un mapa edafológico de INEGI o de Pronatura mejoraría este criterio.
- **Hay supuestos sin calibrar:** el coeficiente de escurrimiento y la retención de 40 % de la optimización de captación, los niveles de conectividad, los umbrales de cárcava (5 ha) y cauce (100 ha), y la retención por barrera (60 %). Son parámetros explícitos en el código.
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
  optimize.py     Optimización de captación: celdas de 1 km → m³ al abasto → selección por presupuesto
  build_static.py Genera la versión estática de GitHub Pages
api/
  main.py         /api/config, /api/tiles, /api/summary, /api/basins, /api/robustness, /api/site
  barriers_api.py /api/barriers
  (main.py)       /api/optimize
web/
  index.html      Mapa, controles, leyenda, ficha
  barriers.js     Panel del optimizador de barreras
  optimize.js     Panel de optimización de captación
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
- Jesus Zaddkiel Martinez Alor
