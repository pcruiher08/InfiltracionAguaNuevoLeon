"""Barrier placement optimizer: where, inside a site, to build contour barriers
and gully check dams so they intercept the most runoff for a given budget of
linear meters.

Method (all hydrology in numpy, on a 30 m DEM in UTM 14N):
  1. DEM window around the clicked point (+ margin so upslope inflow counts).
  2. Priority-flood pit filling, D8 flow directions, flow accumulation.
  3. Candidate lines = contours at a practical vertical interval, cut into
     ~45 m segments; where a contour crosses concentrated flow (gully) it is
     broken and that crossing becomes a check-dam candidate instead.
  4. Value of a candidate = upslope area whose runoff passes through it.
     Greedy selection by value per meter; each selected work retains a
     fraction of the runoff of its upslope cells, so later works downslope on
     the same flow path only get credit for what is still flowing.

Results are relative (contributing area), not infiltrated volume, and the DEM
is 30 m: lines are a preliminary layout to be validated in the field.
"""
import heapq
import math

import contourpy
import ee
import numpy as np

DEM_ID = "NASA/NASADEM_HGT/001"
CRS = "EPSG:32614"  # UTM 14N: pixel spacing in meters
RES = 30            # m; native DEM resolution, no upsampling
SEGMENT_M = 45      # target length of a contour barrier segment
SAMPLE_M = 5        # sampling step along contours
MIN_SEGMENT_M = 20  # shorter pieces are not practical barriers
GULLY_HA = 5        # accumulation above this = concentrated flow (cárcava)
MAX_GULLY_HA = 100  # above this = arroyo/cauce mayor, beyond small check dams
DRAIN_HA = 1        # drainage lines drawn above this accumulation
CHECK_DAM_M = 6     # nominal crest length of a check dam
MAX_DAMS = 40       # check dams returned (largest upslope area first)
EFFICIENCY = 0.6    # assumed share of incoming runoff a barrier retains
SLOPE_RANGE = (3, 35)  # local slope (deg) where contour barriers make sense
CELL_HA = RES * RES / 1e4

# D8 neighbor offsets (drow, dcol) and their distances in cells
D8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
D8_DIST = [math.hypot(dr, dc) for dr, dc in D8]


def fetch_dem(lon, lat, window_m, margin_m):
    """Elevation + lon/lat grids for a square window in UTM, one EE call each
    for the origin and the pixels. Returns (elev, lon_grid, lat_grid)."""
    x, y = ee.Geometry.Point([lon, lat]).transform(CRS, 1).coordinates().getInfo()
    n = int(round((window_m + 2 * margin_m) / RES))
    x0 = round(x / RES) * RES - n * RES / 2
    y0 = round(y / RES) * RES + n * RES / 2
    img = (ee.Image(DEM_ID).select("elevation").toFloat().resample("bilinear")
           .addBands(ee.Image.pixelLonLat()))
    arr = ee.data.computePixels({
        "expression": img, "fileFormat": "NUMPY_NDARRAY",
        "grid": {"dimensions": {"width": n, "height": n}, "crsCode": CRS,
                 "affineTransform": {"scaleX": RES, "shearX": 0, "translateX": x0,
                                     "shearY": 0, "scaleY": -RES, "translateY": y0}},
    })
    return (arr["elevation"].astype(float), arr["longitude"].astype(float),
            arr["latitude"].astype(float))


def pixel_to_lonlat(lon_g, lat_g):
    """Quadratic fit (col, row) -> (lon, lat); exact to well under a meter at
    this window size and works for fractional / edge coordinates."""
    rows, cols = np.indices(lon_g.shape)
    c, r = cols.ravel().astype(float), rows.ravel().astype(float)
    A = np.column_stack([np.ones_like(c), c, r, c * c, c * r, r * r])
    k_lon = np.linalg.lstsq(A, lon_g.ravel(), rcond=None)[0]
    k_lat = np.linalg.lstsq(A, lat_g.ravel(), rcond=None)[0]

    def f(col, row):
        col, row = np.asarray(col, float), np.asarray(row, float)
        t = np.stack([np.ones_like(col), col, row, col * col, col * row, row * row], -1)
        return np.round(t @ k_lon, 6), np.round(t @ k_lat, 6)
    return f


def fill_pits(z):
    """Priority-flood fill with a tiny epsilon so every cell drains to an edge."""
    nr, nc = z.shape
    filled = z.copy()
    done = np.zeros(z.shape, bool)
    heap = []
    for r in range(nr):
        for c in range(nc):
            if r in (0, nr - 1) or c in (0, nc - 1):
                heapq.heappush(heap, (filled[r, c], r, c))
                done[r, c] = True
    while heap:
        h, r, c = heapq.heappop(heap)
        for dr, dc in D8:
            rr, cc = r + dr, c + dc
            if 0 <= rr < nr and 0 <= cc < nc and not done[rr, cc]:
                done[rr, cc] = True
                filled[rr, cc] = max(filled[rr, cc], h + 1e-3)
                heapq.heappush(heap, (filled[rr, cc], rr, cc))
    return filled


def flow_directions(filled):
    """D8 receiver (flat index) per cell; -1 for edge cells (flow leaves the grid)."""
    nr, nc = filled.shape
    pad = np.pad(filled, 1, mode="edge")
    best = np.zeros(filled.shape)
    recv = np.full(filled.shape, -1, int)
    rows, cols = np.indices(filled.shape)
    for (dr, dc), d in zip(D8, D8_DIST):
        drop = (filled - pad[1 + dr:1 + dr + nr, 1 + dc:1 + dc + nc]) / d
        better = drop > best
        best[better] = drop[better]
        recv[better] = ((rows + dr) * nc + (cols + dc))[better]
    edge = (rows == 0) | (rows == nr - 1) | (cols == 0) | (cols == nc - 1)
    recv[edge] = -1
    return recv.ravel()


def accumulation(filled, recv):
    """Upslope contributing cells (including the cell itself)."""
    acc = np.ones(filled.size)
    for i in np.argsort(-filled.ravel(), kind="stable"):
        if recv[i] >= 0:
            acc[recv[i]] += acc[i]
    return acc


def donors_of(recv):
    """Reverse D8 graph: list of donor cells per cell."""
    donors = [[] for _ in range(recv.size)]
    for i, j in enumerate(recv):
        if j >= 0:
            donors[j].append(i)
    return donors


def upstream(cells, donors):
    """All cells draining through any of `cells` (including them)."""
    seen = set(cells)
    stack = list(cells)
    while stack:
        for d in donors[stack.pop()]:
            if d not in seen:
                seen.add(d)
                stack.append(d)
    return np.fromiter(seen, int, len(seen))


def slope_deg(z):
    gy, gx = np.gradient(z, RES)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def smooth3(z):
    """3x3 mean, to keep 30 m noise out of the contour lines."""
    p = np.pad(z, 1, mode="edge")
    return sum(p[1 + dr:1 + dr + z.shape[0], 1 + dc:1 + dc + z.shape[1]]
               for dr in (-1, 0, 1) for dc in (-1, 0, 1)) / 9


def vertical_interval(mean_slope):
    """Practical contour interval for a 30 m DEM: the ~1 m nominal VI would put
    lines closer than the DEM resolves, so aim for ~one pixel of horizontal
    spacing, bounded to 2–5 m."""
    return int(np.clip(math.ceil(math.tan(math.radians(mean_slope)) * RES), 2, 5))


def resample_line(pts, step):
    """Points every `step` (same units as pts) along a polyline."""
    seg = np.hypot(*np.diff(pts, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    if cum[-1] < step:
        return pts[[0, -1]] if len(pts) > 1 else pts
    s = np.append(np.arange(0, cum[-1], step), cum[-1])
    return np.column_stack([np.interp(s, cum, pts[:, 0]), np.interp(s, cum, pts[:, 1])])


def candidates(z_smooth, acc, local_slope, interval, win):
    """Contour segments and check-dam points inside the window `win`
    (r0, r1, c0, c1 in grid indices). Coordinates are (col, row) floats."""
    r0, r1, c0, c1 = win
    nc = acc.shape[1]
    sub = z_smooth[r0:r1, c0:c1]
    gen = contourpy.contour_generator(np.arange(c0, c1), np.arange(r0, r1), sub,
                                      line_type="Separate")
    gully = acc * CELL_HA >= GULLY_HA
    levels = np.arange(math.ceil(sub.min() / interval) * interval, sub.max(), interval)
    step = SAMPLE_M / RES
    segs, dams = [], {}
    for level in levels:
        for line in gen.lines(level):
            pts = resample_line(np.asarray(line), step)
            cell = np.round(pts[:, 1]).astype(int) * nc + np.round(pts[:, 0]).astype(int)
            is_gully = gully.ravel()[cell]
            # split into runs of hillslope / gully samples
            breaks = np.flatnonzero(np.diff(is_gully.astype(int))) + 1
            for run in np.split(np.arange(len(pts)), breaks):
                if is_gully[run[0]]:
                    k = run[np.argmax(acc.ravel()[cell[run]])]
                    c = cell[k]
                    if acc.ravel()[c] * CELL_HA <= MAX_GULLY_HA and c not in dams:
                        dams[c] = {"type": "cárcava", "pts": pts[k:k + 1], "cells": [c],
                                   "length_m": CHECK_DAM_M, "level": float(level)}
                    continue
                n_per = max(2, int(round(SEGMENT_M / SAMPLE_M)))
                chunks = [run[i:i + n_per + 1] for i in range(0, len(run) - 1, n_per)]
                if len(chunks) > 1 and len(chunks[-1]) * SAMPLE_M < SEGMENT_M / 3:
                    chunks[-2] = np.concatenate([chunks[-2], chunks[-1][1:]])
                    chunks.pop()
                for ch in chunks:
                    if len(ch) < 2:
                        continue
                    p = pts[ch]
                    length = float(np.hypot(*np.diff(p, axis=0).T).sum() * RES)
                    cells = list(dict.fromkeys(cell[ch].tolist()))
                    s = float(local_slope.ravel()[cells].mean())
                    if length < MIN_SEGMENT_M or not SLOPE_RANGE[0] <= s <= SLOPE_RANGE[1]:
                        continue
                    segs.append({"type": "curva de nivel", "pts": p, "cells": cells,
                                 "length_m": length, "level": float(level), "slope_deg": s})
    return segs + list(dams.values())


def greedy(cands, n_cells, budget_m):
    """Pick contour barriers by marginal intercepted area per meter until the
    budget is spent. `remaining[c]` is the share of cell c's runoff still
    flowing (not yet retained by a barrier upslope)."""
    remaining = np.ones(n_cells)
    covered = np.zeros(n_cells, bool)
    chosen, spent = [], 0.0
    pool = list(range(len(cands)))
    while pool:
        gains = np.array([EFFICIENCY * remaining[cands[i]["up"]].sum() for i in pool])
        per_m = gains / np.array([cands[i]["length_m"] for i in pool])
        fits = np.array([spent + cands[i]["length_m"] <= budget_m for i in pool])
        if not fits.any():
            break
        per_m[~fits] = -1
        k = int(np.argmax(per_m))
        if gains[k] < 0.5:  # less than half a cell of new runoff: stop
            break
        i = pool.pop(k)
        cd = cands[i]
        cd["value_ha"] = float(gains[k] * CELL_HA)
        remaining[cd["up"]] *= 1 - EFFICIENCY
        covered[cd["up"]] = True
        spent += cd["length_m"]
        chosen.append(cd)
    return chosen, covered, remaining, spent


def drainage_lines(acc, recv, to_ll, win):
    """Channel cells (acc >= DRAIN_HA) chained into polylines from heads/confluences."""
    nr, nc = acc.shape
    a = acc.ravel()
    chan = a * CELL_HA >= DRAIN_HA
    r0, r1, c0, c1 = win
    inwin = np.zeros((nr, nc), bool)
    inwin[r0:r1, c0:c1] = True
    inwin = inwin.ravel()
    n_up = np.zeros(a.size, int)
    for i in np.flatnonzero(chan):
        if recv[i] >= 0:
            n_up[recv[i]] += 1
    feats = []
    for start in np.flatnonzero(chan & inwin & (n_up != 1)):
        path = [start]
        j = recv[start]
        while j >= 0 and inwin[j]:
            path.append(j)
            if n_up[j] != 1:
                break
            j = recv[j]
        if len(path) < 2:
            continue
        lon, lat = to_ll(np.array(path) % nc, np.array(path) // nc)
        feats.append({"type": "Feature",
                      "properties": {"acc_ha": round(float(a[path].max() * CELL_HA), 1)},
                      "geometry": {"type": "LineString",
                                   "coordinates": np.column_stack([lon, lat]).tolist()}})
    return {"type": "FeatureCollection", "features": feats}


def optimize(lon, lat, budget_m=1500, window_m=1200):
    """Full pipeline for one site. Returns GeoJSON + totals + params + notes."""
    margin_m = max(150, window_m * 0.25)
    z, lon_g, lat_g = fetch_dem(lon, lat, window_m, margin_m)
    to_ll = pixel_to_lonlat(lon_g, lat_g)
    m = int(round(margin_m / RES))
    win = (m, z.shape[0] - m, m, z.shape[1] - m)

    filled = fill_pits(z)
    recv = flow_directions(filled)
    acc = accumulation(filled, recv).reshape(z.shape)
    donors = donors_of(recv)
    zs = smooth3(z)
    local_slope = slope_deg(zs)
    r0, r1, c0, c1 = win
    mean_slope = float(local_slope[r0:r1, c0:c1].mean())
    interval = vertical_interval(mean_slope)

    cands = candidates(zs, acc, local_slope, interval, win)
    for cd in cands:
        cd["up"] = upstream(cd["cells"], donors)
    contour = [c for c in cands if c["type"] == "curva de nivel"]
    chosen, covered, remaining, spent = greedy(contour, z.size, budget_m)
    # Check dams: every gully crossing within small-dam range, ranked by upslope
    # area; reported separately (they are point works, not linear budget).
    dams = sorted((c for c in cands if c["type"] == "cárcava"), key=lambda c: -len(c["up"]))
    n_dams_total = len(dams)
    dams = dams[:MAX_DAMS]
    for cd in dams:
        cd["value_ha"] = len(cd["up"]) * CELL_HA

    feats = []
    for rank, cd in enumerate(chosen + dams, 1):
        lo, la = to_ll(cd["pts"][:, 0], cd["pts"][:, 1])
        coords = np.column_stack([lo, la]).tolist()
        geom = ({"type": "Point", "coordinates": coords[0]} if cd["type"] == "cárcava"
                else {"type": "LineString", "coordinates": coords})
        props = {"rank": rank, "type": cd["type"], "length_m": round(cd["length_m"], 1),
                 "value_ha": round(cd["value_ha"], 2), "elev_m": round(cd["level"], 1),
                 "upslope_ha": round(len(cd["up"]) * CELL_HA, 2)}
        if "slope_deg" in cd:
            props["slope_deg"] = round(cd["slope_deg"], 1)
        feats.append({"type": "Feature", "properties": props, "geometry": geom})

    winmask = np.zeros(z.shape, bool)
    winmask[r0:r1, c0:c1] = True
    winmask = winmask.ravel()
    corners = to_ll(np.array([c0, c1, c1, c0, c0]) - 0.5, np.array([r0, r0, r1, r1, r0]) - 0.5)
    spacing_nominal = 1.0 / math.tan(math.radians(max(mean_slope, 1)))
    return {
        "selected": {"type": "FeatureCollection", "features": feats},
        "drainage": drainage_lines(acc, recv, to_ll, win),
        "window": {"type": "Feature", "properties": {},
                   "geometry": {"type": "Polygon",
                                "coordinates": [np.column_stack(corners).tolist()]}},
        "totals": {
            "n_barriers": len(chosen),
            "n_check_dams": len(dams),
            "n_check_dams_total": n_dams_total,
            "length_m": round(spent, 1),
            "check_dam_length_m": len(dams) * CHECK_DAM_M,
            "intercepted_pct": round(100 * float(covered[winmask].mean()), 1),
            "retained_pct": round(100 * float(1 - remaining[winmask].mean()), 1),
            "candidates": len(contour),
        },
        "params": {
            "budget_m": budget_m, "window_m": window_m, "margin_m": margin_m,
            "dem": DEM_ID, "resolution_m": RES, "crs": CRS,
            "mean_slope_deg": round(mean_slope, 1), "vertical_interval_m": interval,
            "candidate_spacing_m": round(interval / math.tan(math.radians(max(mean_slope, 1))), 1),
            "nominal_spacing_m": round(spacing_nominal, 1),
            "segment_m": SEGMENT_M, "gully_ha": GULLY_HA, "max_gully_ha": MAX_GULLY_HA,
            "check_dam_m": CHECK_DAM_M, "efficiency": EFFICIENCY,
        },
        "notes": [
            "Trazo preliminar con DEM de 30 m: validar en campo con levantamiento topográfico o dron.",
            f"Curvas candidatas cada {interval} m de desnivel (el DEM de 30 m no resuelve el "
            f"intervalo nominal de 1 m; en campo, trazar líneas intermedias a ~{spacing_nominal:.0f} m).",
            "Valor = área ladera arriba cuyo escurrimiento cruza la obra (relativo, no volumen).",
            f"Se asume que cada obra retiene ~{EFFICIENCY:.0%} del escurrimiento que le llega; "
            "obras ladera abajo sólo reciben crédito por lo que sigue escurriendo.",
            f"Cruces con flujo concentrado (≥ {GULLY_HA} ha de aporte) → presas de piedra/gaviones "
            f"en cárcava (~{CHECK_DAM_M} m c/u, fuera del presupuesto lineal); cauces > {MAX_GULLY_HA} ha "
            "quedan fuera de obras pequeñas.",
            "% interceptado = parte del área de la ventana cuyo escurrimiento de ladera cruza al "
            "menos una barrera (sin contar presas en cárcavas).",
        ],
    }
