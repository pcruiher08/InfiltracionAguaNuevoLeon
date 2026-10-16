"""Map figures for the report, rendered from data (no screenshots).

    .venv/bin/python informe/mapas.py
"""
import base64
import io
import json
import math
import sys
import urllib.request
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import ee  # noqa: E402

from pipeline import barriers as B, barriers_mcmf as M, layers, simulate  # noqa: E402

OUT = ROOT / "figuras"
DOCS = ROOT.parent / "docs" / "data"
for f in (ROOT / "fonts").glob("Figtree-*.ttf"):
    font_manager.fontManager.addfont(str(f))
plt.rcParams.update({"font.family": "Figtree Light", "font.size": 9, "figure.dpi": 220,
                     "savefig.bbox": "tight", "savefig.facecolor": "white"})
SCOL = {"Presa La Boca": "#2a78d6", "Acuífero Santa Catarina (pozos SADM)": "#eb6834",
        "Presa Cerro Prieto": "#1baf7a", "Presa El Cuchillo": "#eda100"}
SITE = (-100.45, 25.45)  # Santa Catarina test site for the barrier/storm figures


def thumb(img, region, dim=2200):
    url = img.getThumbURL({"region": region, "dimensions": dim, "format": "png", "crs": "EPSG:4326"})
    return np.asarray(Image.open(io.BytesIO(urllib.request.urlopen(url).read())).convert("RGBA"))


def hillshade_np(z, az=315, alt=45, res=30):
    gy, gx = np.gradient(z, res)
    slope = np.arctan(np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
    a, al = math.radians(az), math.radians(alt)
    return np.clip(np.sin(al) * np.cos(slope) + np.cos(al) * np.sin(slope) * np.cos(a - aspect), 0, 1)


def north_arrow(ax, x=0.94, y=0.94):
    ax.annotate("N", xy=(x, y), xytext=(x, y - 0.11), xycoords="axes fraction", ha="center", va="center",
                fontsize=8, fontweight="bold", arrowprops=dict(arrowstyle="-|>", lw=1.2, color="#1d1b18"), zorder=9,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=.8))


def base_axes(ax, ext, km=20, ticks=True):
    w, e, s, n = ext
    lat0 = (s + n) / 2
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    ax.set_aspect(1 / math.cos(math.radians(lat0)))
    if ticks:
        xt = np.linspace(w, e, 4)[1:-1]; yt = np.linspace(s, n, 4)[1:-1]
        ax.set_xticks(xt, [f"{abs(v):.2f}° O" for v in xt], fontsize=6.5)
        ax.set_yticks(yt, [f"{v:.2f}° N" for v in yt], fontsize=6.5, rotation=90, va="center")
        ax.tick_params(length=2, color="#9c9890", labelcolor="#6b675f")
    else:
        ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values(): sp.set_color("#cfcac0")
    # scale bar (bottom right) and north arrow
    dlon = km / (111.32 * math.cos(math.radians(lat0)))
    x1 = e - (e - w) * 0.05; x0 = x1 - dlon; y = s + (n - s) * 0.05
    ax.plot([x0, x1], [y, y], color="#1d1b18", lw=2.5, solid_capstyle="butt", zorder=9)
    ax.text((x0 + x1) / 2, y + (n - s) * 0.015, f"{km} km", ha="center", va="bottom", fontsize=7, zorder=9,
            bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=.8))
    north_arrow(ax, 0.94, 0.24)


def draw_catchments(ax, gj, labels=True):
    for f in gj["features"]:
        g = f["geometry"]
        if g["type"] == "Point":
            x, y = g["coordinates"]
            ax.plot(x, y, "o", ms=5, mfc="#1d1b18", mec="white", mew=1.2, zorder=6)
            if labels:
                ax.annotate(f["properties"]["name"].replace(" (Monterrey)", ""), (x, y), xytext=(5, 3),
                            textcoords="offset points", fontsize=7.5, zorder=7,
                            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=.85))
            continue
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            ring = np.array(poly[0]); ax.plot(ring[:, 0], ring[:, 1], color="#3d3a35", lw=1.1, zorder=5)


def regional_maps():
    layers.init()
    gj = json.loads((DOCS / "catchments.geojson").read_text())
    lonlat = np.array([c for f in gj["features"] if f["geometry"]["type"] != "Point"
                       for poly in ([f["geometry"]["coordinates"]] if f["geometry"]["type"] == "Polygon" else f["geometry"]["coordinates"])
                       for c in poly[0]])
    pad = 0.04
    ext = [lonlat[:, 0].min() - pad, lonlat[:, 0].max() + pad, lonlat[:, 1].min() - pad, lonlat[:, 1].max() + pad]
    region = ee.Geometry.Rectangle([ext[0], ext[2], ext[1], ext[3]])
    dem = ee.Image(B.DEM_ID).select("elevation")
    hs = thumb(ee.Terrain.hillshade(dem).visualize(min=120, max=255, palette=["8a857c", "fcfcfb"]), region)
    up = layers.raw().select("slope_deg").gte(8)
    cls = layers.priority_classes(layers.priority_index().updateMask(up))
    pr = thumb(cls.updateMask(cls.gt(1)).visualize(min=1, max=3, palette=["86b6ef", "2a78d6", "0d366b"]), region)

    # Fig 1 · catchments + priority
    fig, ax = plt.subplots(figsize=(7, 7.2))
    ax.imshow(hs, extent=ext, zorder=1); ax.imshow(pr, extent=ext, alpha=.85, zorder=2)
    draw_catchments(ax, gj); base_axes(ax, ext)
    ax.legend(handles=[Patch(color="#0d366b", label="Prioridad alta"), Patch(color="#2a78d6", label="Prioridad media"),
                       Line2D([], [], color="#3d3a35", lw=1.1, label="Cuencas de abasto")],
              loc="lower left", fontsize=8, frameon=True, framealpha=.9)
    fig.savefig(OUT / "m1_cuencas.png"); plt.close(fig); print("wrote m1_cuencas")

    # Fig 5 · optimal cells by expected net gain (all in the Santa Catarina catchment) and protected areas
    cells = json.loads((DOCS / "cells.geojson").read_text())
    anp = json.loads((DOCS / "anp.geojson").read_text())
    xy = np.array([p for f in cells["features"] for p in f["geometry"]["coordinates"][0]])
    pad = 0.06
    z = [xy[:, 0].min() - pad, xy[:, 0].max() + pad, xy[:, 1].min() - pad, xy[:, 1].max() + pad]
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    ax.imshow(hs, extent=ext, zorder=1); ax.imshow(pr, extent=ext, alpha=.35, zorder=2)
    for f in cells["features"]:
        ring = np.array(f["geometry"]["coordinates"][0])
        ax.fill(ring[:, 0], ring[:, 1], color=SCOL[f["properties"]["supply_name"]], ec="white", lw=.4, zorder=4)
    for f in anp["features"]:
        from shapely.geometry import shape
        geom = shape(f["geometry"])
        parts = getattr(geom, "geoms", [geom])
        for poly in (q for part in parts for q in getattr(part, "geoms", [part])):
            if poly.geom_type != "Polygon":
                continue
            ring = np.array(poly.exterior.coords)
            ax.plot(ring[:, 0], ring[:, 1], color="#0a9055", lw=1.4 if f["properties"]["desig"] == "Parque Nacional" else .8,
                    ls=(0, (3, 2)), zorder=5)
    draw_catchments(ax, gj, labels=False)
    base_axes(ax, z, km=5)
    fig.legend(handles=[Patch(color=SCOL["Acuífero Santa Catarina (pozos SADM)"], label="Celdas seleccionadas (cuenca del río Santa Catarina)"),
                        Line2D([], [], color="#0a9055", ls=(0, (3, 2)), label="Áreas naturales protegidas (WDPA)")],
               loc="lower center", ncol=2, fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(OUT / "m2_optimizacion.png"); plt.close(fig); print("wrote m2_optimizacion")


def site_frame(ax, g, lon, lat, gj, inset=False):
    """Geographic ticks, 300 m scale bar, north arrow and (optionally) a locator inset."""
    r0, r1, c0, c1 = g["win"]; to_ll = g["to_ll"]
    xs = np.linspace(c0, c1, 3); ys = np.linspace(r0, r1, 3)
    lons, _ = to_ll(xs, np.full(3, (r0 + r1) / 2)); _, lats = to_ll(np.full(3, (c0 + c1) / 2), ys)
    ax.set_xticks(xs, [f"{abs(v):.3f}° O" for v in lons], fontsize=6)
    ax.set_yticks(ys, [f"{v:.3f}° N" for v in lats], fontsize=6, rotation=90, va="center")
    ax.tick_params(length=2, color="#9c9890", labelcolor="#6b675f")
    x0, y = c0 + 1, r1 + 1.6
    ax.plot([x0, x0 + 10], [y, y], color="#1d1b18", lw=2.5, solid_capstyle="butt", zorder=9)
    ax.text(x0 + 5, y - 0.6, "300 m", ha="center", va="bottom", fontsize=6.5, zorder=9,
            bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=.85))
    north_arrow(ax)
    if inset:
        ins = ax.figure.add_axes([0.87, 0.90, 0.12, 0.17])
        for f in gj["features"]:
            gg = f["geometry"]
            if gg["type"] == "Point":
                continue
            for poly in (gg["coordinates"] if gg["type"] == "MultiPolygon" else [gg["coordinates"]]):
                ring = np.array(poly[0]); ins.fill(ring[:, 0], ring[:, 1], color="#efece6", ec="#3d3a35", lw=.5)
        ins.plot(lon, lat, marker="*", ms=8, color="#d95926", mec="white", mew=.6)
        ins.set_title("Ubicación", fontsize=6.5, pad=2, color="#6b675f")
        ins.set_aspect(1 / math.cos(math.radians(lat))); ins.set_xticks([]); ins.set_yticks([])
        ins.patch.set_facecolor("white"); ins.patch.set_alpha(.92)
        for sp in ins.spines.values(): sp.set_color("#9c9890")


def site_maps():
    layers.init()
    lon, lat = SITE
    gj = json.loads((DOCS / "catchments.geojson").read_text())
    res = M.optimize(lon, lat, 1500, storm_mm=10)
    g = res["_grid"]; z = g["z"]; acc = g["acc"]; r0, r1, c0, c1 = g["win"]; contour = g["contour"]
    hs = hillshade_np(z)
    drain = np.ma.masked_less(np.log10(acc * B.CELL_HA), 0)  # channels ≥ 1 ha

    def panel(ax, idx, title, sub):
        ax.imshow(hs, cmap="gray", vmin=-0.2, vmax=1.15, interpolation="bilinear")
        ax.imshow(drain, cmap=ListedColormap(["#86b6ef", "#5598e7", "#2a78d6"]), alpha=.8, interpolation="nearest")
        for j in idx:
            pts = contour[j]["pts"]; ax.plot(pts[:, 0], pts[:, 1], color="#1d1b18", lw=2.2, solid_capstyle="round")
        ax.add_patch(Rectangle((c0 - .5, r0 - .5), c1 - c0, r1 - r0, fill=False, ls=(0, (4, 3)), ec="#1d1b18", lw=.8))
        ax.set_xlim(c0 - 4, c1 + 3); ax.set_ylim(r1 + 3, r0 - 4)
        ax.set_title(f"{title}\n{sub}", fontsize=8.5, loc="left")

    rg = M.retained(g["recv"], g["runoff"], contour, set(g["greedy"]))
    rm = M.retained(g["recv"], g["runoff"], contour, set(g["chosen"]))
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.9))
    panel(axs[0], g["greedy"], "Greedy por área interceptada", f"{len(g['greedy'])} barreras · retiene {rg:,.0f} m³")
    panel(axs[1], g["chosen"], "MCMF (con capacidad)", f"{len(g['chosen'])} barreras · retiene {rm:,.0f} m³")
    for k, ax in enumerate(axs):
        site_frame(ax, g, lon, lat, gj, inset=(k == 0))
    fig.suptitle(f"Cuenca del río Santa Catarina · centro de la ventana {lat:.3f}° N, {abs(lon):.3f}° O", fontsize=8.5, x=0.02, ha="left", y=1.02)
    fig.legend(handles=[Line2D([], [], color="#1d1b18", lw=2.2, label="Barrera en curva de nivel"),
                        Patch(color="#2a78d6", label="Escurrimiento concentrado (1 ha o más aguas arriba)"),
                        Line2D([], [], color="#1d1b18", ls=(0, (4, 3)), lw=.8, label="Ventana de 1.2 km")],
               loc="lower center", ncol=3, fontsize=7.5, frameon=False, bbox_to_anchor=(0.5, -0.03))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(OUT / "m3_barreras.png"); plt.close(fig); print("wrote m3_barreras", rg, rm)

    # Storm: total water through each cell without barriers, and where it dropped with barriers
    sim = simulate.simulate(lon, lat)
    rows, cols = sim["grid"]["rows"], sim["grid"]["cols"]
    dec = lambda b64: np.frombuffer(base64.b64decode(b64), np.uint8).astype(float)
    flux = dec(sim["difference"]["flux_without"]).reshape(rows, cols) / 255
    red = dec(sim["difference"]["reduction"]).reshape(rows, cols) / 255
    s = sim["summary"]
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.9))
    for ax, data, cmap, title in (
            (axs[0], np.ma.masked_less(flux, 0.04), "Blues", "Sin barreras: agua que pasó por cada celda"),
            (axs[1], np.ma.masked_less(red, 0.02), "Oranges", f"Con barreras: dónde bajó el flujo (−{s['outflow_reduction_pct']:.0f} % sale)")):
        ax.imshow(hs, cmap="gray", vmin=-0.2, vmax=1.15, interpolation="bilinear")
        im = ax.imshow(data, cmap=cmap, vmin=0, vmax=1 if ax is axs[0] else 0.5, alpha=.9, interpolation="nearest")
        ax.add_patch(Rectangle((c0 - .5, r0 - .5), c1 - c0, r1 - r0, fill=False, ls=(0, (4, 3)), ec="#1d1b18", lw=.8))
        ax.set_xlim(c0 - 4, c1 + 3); ax.set_ylim(r1 + 3, r0 - 4)
        site_frame(ax, g, lon, lat, gj, inset=(ax is axs[0]))
        ax.set_title(title, fontsize=8.5, loc="left")
        cb = fig.colorbar(im, ax=ax, fraction=.046, pad=.02)
        cb.ax.tick_params(labelsize=7)
        cb.set_label("relativo (0–1)" if ax is axs[0] else "fracción del flujo retenida", fontsize=7)
    fig.suptitle(f"Cuenca del río Santa Catarina · centro de la ventana {lat:.3f}° N, {abs(lon):.3f}° O · tormenta de 40 mm",
                 fontsize=8.5, x=0.02, ha="left", y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "m4_simulacion.png"); plt.close(fig); print("wrote m4_simulacion", s)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    what = sys.argv[1:] or ["regional", "site"]
    if "regional" in what: regional_maps()
    if "site" in what: site_maps()
