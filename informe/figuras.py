"""Figures for the LaTeX report (informe/figuras/*.png) from web/stats.json.

    .venv/bin/python informe/figuras.py <dir with map screenshots>
"""
import json
import sys

import numpy as np
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "figuras"
S = json.loads((ROOT.parent / "web" / "stats.json").read_text())

for f in (ROOT / "fonts").glob("Figtree-*.ttf"):
    font_manager.fontManager.addfont(str(f))
plt.rcParams.update({
    "font.family": "Figtree Light", "font.size": 10, "axes.edgecolor": "#cfcac0", "axes.labelcolor": "#4a4740",
    "xtick.color": "#6b675f", "ytick.color": "#6b675f", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#efece6", "grid.linewidth": 0.8, "axes.axisbelow": True,
    "figure.dpi": 200, "savefig.bbox": "tight", "savefig.facecolor": "white", "legend.frameon": False,
})
ALTA, MEDIA, BAJA = "#0d366b", "#2a78d6", "#86b6ef"
SUP = ["Presa La Boca", "Acuífero Santa Catarina (pozos SADM)", "Presa Cerro Prieto", "Presa El Cuchillo"]
SHORT = dict(zip(SUP, ["La Boca", "Río Santa Catarina", "Cerro Prieto", "El Cuchillo"]))
SCOL = dict(zip(SUP, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]))
CRIT = {"slope": "Pendiente", "vegetation": "Vegetación degradada", "soil": "Suelo permeable", "fire": "Incendios",
        "moisture": "Suelo seco", "rain": "Lluvia", "connectivity": "Conexión con abasto"}
fmt = lambda v: f"{v:,.0f}"


def top_legend(ax):
    n = len(ax.get_legend_handles_labels()[0])
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncol=n, handlelength=1.4, columnspacing=1.2, fontsize=9)


def save(fig, name):
    fig.savefig(OUT / f"{name}.png")
    plt.close(fig)
    print("wrote", name)


def ha_catchment():
    d = S["ha_by_catchment"]
    fig, ax = plt.subplots(figsize=(7, 2.8))
    y = range(len(SUP))[::-1]
    alta = [d[k]["alta"] for k in SUP]; media = [d[k]["media"] for k in SUP]
    ax.barh(list(y), alta, color=ALTA, height=0.6, label="Alta", edgecolor="white", linewidth=1)
    ax.barh(list(y), media, left=alta, color=MEDIA, height=0.6, label="Media", edgecolor="white", linewidth=1)
    for yi, a, m in zip(y, alta, media):
        ax.text(a + m + 1500, yi, f"{fmt(a)} ha alta", va="center", fontsize=9, color="#4a4740")
    ax.set_yticks(list(y), [SHORT[k] for k in SUP]); ax.grid(axis="y", visible=False)
    ax.set_xlabel("hectáreas (laderas de 8° o más)"); ax.xaxis.set_major_formatter(lambda v, _: fmt(v))
    ax.set_xlim(0, max(a + m for a, m in zip(alta, media)) * 1.22)
    top_legend(ax)
    save(fig, "g1_ha_cuenca")


def criteria():
    d = S["criteria_by_class"]; keys = list(CRIT)
    fig, ax = plt.subplots(figsize=(7, 4))
    h = 0.26
    for j, (cl, col) in enumerate([("alta", ALTA), ("media", MEDIA), ("baja", BAJA)]):
        ys = [len(keys) - 1 - i - (j - 1) * h for i in range(len(keys))]
        ax.barh(ys, [d[cl][k] for k in keys], height=h * 0.9, color=col, label=cl.capitalize())
    for i, k in enumerate(keys):
        ax.text(d["alta"][k] + 0.01, len(keys) - 1 - i + h, f"{d['alta'][k]:.2f}", va="center", fontsize=8, color="#4a4740")
    ax.set_yticks(range(len(keys))[::-1], [CRIT[k] for k in keys]); ax.grid(axis="y", visible=False)
    ax.set_xlim(0, 1); ax.set_xlabel("puntaje promedio del criterio (0–1)")
    top_legend(ax)
    save(fig, "g2_criterios")


def robustness():
    b = S["robustness_hist"]
    fig, ax = plt.subplots(figsize=(7, 2.9))
    cols = ["#d95926" if x["from"] >= 0.5 else "#f0b79b" for x in b]
    ax.bar([x["from"] * 100 + 5 for x in b], [x["ha"] for x in b], width=9, color=cols)
    ax.set_xticks(range(0, 101, 10)); ax.set_xlabel("% de 40 ponderaciones aleatorias en que el sitio es prioridad alta")
    ax.set_ylabel("hectáreas"); ax.yaxis.set_major_formatter(lambda v, _: fmt(v)); ax.grid(axis="x", visible=False)
    tot = sum(x["ha"] for x in b); rob = sum(x["ha"] for x in b if x["from"] >= 0.5)
    ax.text(97, max(x["ha"] for x in b) * 0.92, f"Robusta (50 % o más): {100 * rob / tot:.0f} %", ha="right", color="#a8401a", fontsize=9)
    save(fig, "g3_robustez")


def water():
    w = S["water_curves"]
    fig, ax = plt.subplots(figsize=(7, 3.3))
    for key, col, lab in (("normal", "#2a78d6", "Año normal"), ("sequia", "#eb6834", "Sequía (jul 2021 a jun 2022)")):
        pts = [p for p in w[key] if p["ha"] <= 60000]
        ax.plot([p["ha"] for p in pts], [p["ls"] for p in pts], color=col, lw=2, label=lab)
    ex = json.loads((ROOT / "extras.json").read_text())
    t100 = next(t["ha"] for t in ex["targets"] if t["target_ls"] == 100)
    for x, lab, h in ((3000, "3,000 ha", 0.93), (t100, "+100 L/s", 0.80)):
        ax.axvline(x, color="#9c9890", ls=(0, (3, 3)), lw=1)
        ax.text(x + 500, ax.get_ylim()[1] * h, lab, fontsize=8, color="#4a4740",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))
    ax.set_xlabel("hectáreas restauradas (mejores celdas primero)"); ax.set_ylabel("L/s de agua bruta retenida")
    ax.xaxis.set_major_formatter(lambda v, _: fmt(v)); ax.set_xlim(0, 60000); ax.set_ylim(0)
    top_legend(ax)
    save(fig, "g4_agua_hectareas")


def productivity():
    P = S["productivity_by_supply"]
    fig, axs = plt.subplots(2, 2, figsize=(7, 4), sharex=True, sharey=True)
    for ax, k in zip(axs.flat, SUP):
        b = P[k]["bins"]; tot = P[k]["ha"]
        step = b[0]["to"] - b[0]["from"]
        ax.bar([x["from"] + step / 2 for x in b], [100 * x["ha"] / tot for x in b], width=step * 0.9, color=SCOL[k])
        ax.axvline(P[k]["median"], color="#1d1b18", ls=(0, (3, 3)), lw=1)
        ax.set_title(f"{SHORT[k]} · mediana {fmt(P[k]['median'])}", fontsize=9, loc="left", color="#1d1b18")
        ax.grid(axis="x", visible=False)
    for ax in axs[1]: ax.set_xlabel("m³/ha/año de agua bruta")
    for ax in axs[:, 0]: ax.set_ylabel("% del área elegible")
    fig.tight_layout()
    save(fig, "g5_productividad")


def barriers():
    B = S["barrier_budget_curves"]
    fig, ax = plt.subplots(figsize=(7, 3))
    for (name, pts), col in zip(B.items(), ["#2a78d6", "#eb6834", "#1baf7a"]):
        ax.plot([0] + [p["budget_m"] for p in pts], [0] + [p["intercepted_pct"] for p in pts], color=col, lw=2, marker="o", ms=3, label=name)
    ax.set_xlabel("metros lineales de barrera"); ax.set_ylabel("% de la ventana interceptado")
    ax.set_ylim(0, 100); ax.set_xlim(0, 4000); ax.xaxis.set_major_formatter(lambda v, _: fmt(v))
    top_legend(ax)
    save(fig, "g6_barreras_presupuesto")


def storm():
    R = S["storm_sites"]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    y = list(range(len(R)))[::-1]; h = 0.38
    ax.barh([v + h / 2 for v in y], [r["outflow_reduction_pct"] for r in R], height=h, color="#2a78d6", label="Escurrimiento total")
    ax.barh([v - h / 2 for v in y], [r["peak_reduction_pct"] for r in R], height=h, color="#eb6834", label="Pico")
    for v, r in zip(y, R):
        ax.text(r["outflow_reduction_pct"] + 0.5, v + h / 2, f"−{r['outflow_reduction_pct']:.0f} %", va="center", fontsize=8, color="#4a4740")
    ax.set_yticks(y, [f"{r['site']}. {SHORT.get(r['supply'], '')}" for r in R]); ax.grid(axis="y", visible=False)
    ax.set_xlabel("reducción con barreras (%)"); ax.set_xlim(0, 50); top_legend(ax)
    save(fig, "g7_tormenta_sitios")


def mcmf():
    """Retained m³ by storm size: area greedy vs min-cost flow (capacity-aware)."""
    D = S.get("mcmf_vs_greedy")
    if not D:
        return
    fig, axs = plt.subplots(1, len(D), figsize=(7, 3), sharey=True)
    axs = np.atleast_1d(axs)
    for ax, (name, rows) in zip(axs, D.items()):
        x = np.arange(len(rows)); w = 0.38
        ax.bar(x - w / 2, [r["greedy_m3"] for r in rows], w, color="#9c9890", label="Greedy por área")
        ax.bar(x + w / 2, [r["mcmf_m3"] for r in rows], w, color="#2a78d6", label="MCMF")
        for xi, r in zip(x, rows):
            ax.text(xi + w / 2, r["mcmf_m3"] + 30, f"{100 * r['mcmf_m3'] / r['runoff_m3']:.0f} %", ha="center", fontsize=7.5, color="#4a4740")
        ax.set_xticks(x, [f"{r['storm_mm']} mm" for r in rows]); ax.set_title(name, fontsize=9, loc="left")
        ax.grid(axis="x", visible=False); ax.set_xlabel("tormenta")
    axs[0].set_ylabel("m³ retenidos (1,500 m de barreras)")
    axs[0].yaxis.set_major_formatter(lambda v, _: fmt(v))
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper left", ncol=2, fontsize=9, bbox_to_anchor=(0.06, 1.08), frameon=False)
    fig.text(0.99, -0.02, "% sobre la barra: fracción del escurrimiento de la ventana retenida", ha="right", fontsize=7, color="#6b675f")
    fig.tight_layout()
    save(fig, "g8_mcmf")


def _math():
    f = ROOT / "math.json"
    return json.loads(f.read_text()) if f.exists() else None


def uncertainty():
    D = _math()
    if not D:
        return
    mc = D["monte_carlo"]; x = np.array(mc["samples_max"])
    fig, ax = plt.subplots(figsize=(7, 2.8))
    ax.hist(x, bins=40, color="#86b6ef", edgecolor="white", linewidth=.5)
    p5, p50, p95 = mc["max_ls"]
    for v, ls_, lab in ((p5, (0, (3, 3)), f"P5 {p5:.0f}"), (p50, "-", f"media {p50:.0f}"), (p95, (0, (3, 3)), f"P95 {p95:.0f}")):
        ax.axvline(v, color="#0d366b", ls=ls_, lw=1.2)
        ax.text(v, ax.get_ylim()[1] * 0.95, f" {lab} L/s", fontsize=8, color="#0d366b", va="top")
    ax.set_xlabel("L/s de agua bruta con 3,000 ha (máxima agua), 2,000 escenarios de parámetros")
    ax.set_ylabel("escenarios"); ax.grid(axis="x", visible=False)
    save(fig, "g9_incertidumbre")


def duals():
    D = _math()
    if not D:
        return
    c = D["knapsack_duals"]["curve"]; cd = D["capacity_duals"]
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3), gridspec_kw={"width_ratios": [1.25, 1]})
    ax = axs[0]
    ax.plot([p["ha"] for p in c], [p["marginal_ls_per_1000ha"] for p in c], color="#2a78d6", lw=2, marker="o", ms=3)
    ax.set_xscale("log"); ax.set_xlabel("hectáreas restauradas (escala log)")
    ax.set_ylabel("L/s por 1,000 ha adicionales"); ax.set_title("Variable dual del presupuesto: valor marginal de la hectárea", fontsize=8.5, loc="left")
    ax.xaxis.set_major_formatter(lambda v, _: fmt(v)); ax.set_ylim(0)
    ax = axs[1]
    xs = np.arange(len(cd)); w = 0.38
    ax.bar(xs - w / 2, [r["shadow_capacity"] for r in cd], w, color="#eb6834", label="más capacidad")
    ax.bar(xs + w / 2, [r["shadow_meters"] for r in cd], w, color="#9c9890", label="más metros")
    for xi, r in zip(xs, cd):
        ax.text(xi, max(r["shadow_capacity"], r["shadow_meters"]) + .05, f"{r['saturated_pct']:.0f} % de barreras llenas", ha="center", fontsize=7, color="#4a4740")
    ax.set_xticks(xs, [f"{r['storm_mm']} mm" for r in cd]); ax.set_ylim(0, 1.25); ax.grid(axis="x", visible=False)
    ax.set_ylabel("m³ retenidos por m³ adicional"); ax.set_title("Precio sombra del almacenamiento", fontsize=8.5, loc="left")
    ax.legend(fontsize=8, loc="lower center", bbox_to_anchor=(0.5, -0.38), ncol=2, frameon=False)
    fig.tight_layout()
    save(fig, "g10_duales")


def gumbel_fig():
    D = _math()
    if not D:
        return
    G = D["gumbel"]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    cols = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
    T = np.logspace(np.log10(1.05), np.log10(100), 80)
    for (name, g), col in zip(G.items(), cols):
        x = g["mu"] - g["beta"] * np.log(-np.log(1 - 1 / T))
        ax.plot(T, x, color=col, lw=2, label=f"{name} · 40 mm cada {g['T_40mm']:.1f} años")
        e = np.array(g["empirical"]); ax.scatter(e[:, 0], e[:, 1], s=7, color=col, alpha=.6, zorder=3)
    ax.axhline(40, color="#1d1b18", ls=(0, (3, 3)), lw=1)
    ax.text(98, 33, "tormenta de diseño, 40 mm", fontsize=7.5, color="#1d1b18", ha="right", va="top",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))
    ax.set_xscale("log"); ax.set_xlabel("periodo de retorno (años)"); ax.set_ylabel("lluvia máxima diaria (mm)")
    ax.set_xticks([1, 2, 5, 10, 25, 50, 100], ["1", "2", "5", "10", "25", "50", "100"])
    ax.legend(fontsize=7.5, loc="upper left", frameon=False)
    save(fig, "g11_gumbel")


def pareto_fig():
    D = _math()
    if not D:
        return
    R = D["pareto"]
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot([r["jain"] for r in R], [r["ls"] for r in R], color="#2a78d6", lw=2, marker="o", ms=3.5)
    for r in R:
        if r["alpha"] in (0.0, 0.25, 0.5, 0.75, 1.0):
            ax.annotate(f"$\\alpha$ = {r['alpha']:.2f}", (r["jain"], r["ls"]), xytext=(6, 4), textcoords="offset points", fontsize=7.5, color="#4a4740")
    ax.set_xlabel("equidad entre las cuatro fuentes (índice de Jain, 1 = igual para todas)")
    ax.set_ylabel("L/s de agua bruta (3,000 ha)")
    save(fig, "g12_pareto")


def supply_fig():
    p = ROOT / "abasto.json"
    if not p.exists():
        return
    A = json.loads(p.read_text()); R = A["scenarios"]
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    y = np.arange(len(R))[::-1]; h = 0.36
    for off, key, mc, col, lab in ((h / 2, "ls", "mc_ls", "#2a78d6", "Lluvia media"),
                                   (-h / 2, "ls_drought", "mc_ls_drought", "#eb6834", "Lluvia de jul 2021 a jun 2022")):
        v = np.array([r[mc][1] for r in R]); lo = np.array([r[mc][0] for r in R]); hi = np.array([r[mc][2] for r in R])  # mean, p5, p95
        ax.barh(y + off, v, height=h, color=col, label=lab)
        ax.errorbar(v, y + off, xerr=[v - lo, hi - v], fmt="none", ecolor="#4a4740", elinewidth=0.8, capsize=2)
    xmax = 1.15 * max(r["mc_ls"][2] for r in R)
    for yi, r in zip(y, R):
        ax.text(r["mc_ls"][2] + 0.01 * xmax, yi + h / 2, f"{r['mc_ls'][1]:,.0f}", va="center", fontsize=7.5, color="#4a4740")
        ax.text(r["mc_ls_drought"][2] + 0.01 * xmax, yi - h / 2, f"{r['mc_ls_drought'][1]:,.0f} L/s · {100 * r['mc_ls_drought'][1] / A['deficit_ls']:.0f} % del déficit",
                va="center", fontsize=7.5, color="#4a4740", bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none"), zorder=3)
    ax.axvline(A["deficit_ls"], color="#1d1b18", ls=(0, (3, 3)), lw=1)
    ax.text(A["deficit_ls"] + 0.01 * xmax, y[0] + 0.55, "déficit de 2022: 3,000 L/s", ha="left", fontsize=7.5, color="#1d1b18")
    labels = [fmt(r["ha"]) + (" ha (todas las elegibles)" if r is R[-1] else " ha") for r in R]
    xmax = 1.15 * max(r["mc_ls"][2] for r in R)
    ax.set_yticks(y, labels); ax.set_xlim(0, xmax); ax.grid(axis="y", visible=False)
    ax.set_xlabel("L/s de agua bruta retenida (cota superior del aporte al abasto)"); ax.xaxis.set_major_formatter(lambda v, _: fmt(v))
    top_legend(ax)
    save(fig, "g13_abasto")


def fate_figs():
    p = ROOT / "destino.json"
    if not p.exists():
        return
    D = json.loads(p.read_text())
    fig, ax = plt.subplots(figsize=(7, 3.2))
    names = [n for n in SUP if n in D["factor_samples"]]
    data = [D["factor_samples"][n] for n in names]
    parts = ax.violinplot(data, vert=False, showextrema=False, widths=0.8)
    for body, n in zip(parts["bodies"], names):
        body.set_facecolor(SCOL[n]); body.set_alpha(0.75); body.set_edgecolor("white")
    for y, n in enumerate(names, 1):
        f = D["factor"][n]
        ax.plot(f["mean"], y, "o", color="white", ms=4, mec="#1d1b18", mew=0.8)
        ax.text(0.62, y, f"P(G > 0) = {f['p_pos']:.0f} %", va="center", fontsize=8, color="#4a4740")
    ax.axvline(0, color="#1d1b18", lw=1)
    ax.set_yticks(range(1, len(names) + 1), [SHORT[n] for n in names]); ax.set_xlim(-0.9, 0.9)
    ax.set_xlabel("G: m³ netos que gana la fuente por cada m³ retenido"); ax.grid(axis="y", visible=False)
    save(fig, "g14_destino")

    fig, ax = plt.subplots(figsize=(7, 3.2))
    for key, col, lab in (("bruta_30000", "#9c9890", "Selección por agua bruta"), ("neta_30000", "#eb6834", "Selección por ganancia neta esperada")):
        sm = D["selections"][key]["samples"]
        ax.hist(sm, bins=60, color=col, alpha=0.7, label=lab, range=(-250, 250))
    ax.axvline(0, color="#1d1b18", lw=1)
    g = D["selections"]["bruta_30000"]["gross_ls"]
    ax.set_xlabel(f"L/s netos con 30,000 ha (el agua bruta retenida es de {g:,.0f} L/s)")
    ax.set_ylabel("escenarios"); ax.grid(axis="x", visible=False); top_legend(ax)
    save(fig, "g15_neto")


def oracle_figs():
    p = ROOT / "oraculos.json"
    if not p.exists():
        return
    O = json.loads(p.read_text()); E = O["evals"]
    storms = sorted({e["storm_mm"] for e in E})
    cols = dict(zip(storms, ["#86b6ef", "#2a78d6", "#eb6834", "#8f3510"]))
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for mm in storms:
        sub = [e for e in E if e["storm_mm"] == mm]
        ax.scatter([e["mcmf"] for e in sub], [100 * (e["fill"] / e["mcmf"] - 1) if e["mcmf"] > 0 else 0 for e in sub],
                   s=10, color=cols[mm], label=f"{mm} mm", alpha=.8, edgecolor="white", linewidth=.3)
    ax.axhline(0, color="#1d1b18", lw=1)
    ax.set_xscale("log"); ax.set_xticks([500, 700, 1000, 1500, 2000]); ax.xaxis.set_minor_formatter(lambda v, _: "")
    ax.xaxis.set_major_formatter(lambda v, _: fmt(v))
    ax.set_xlabel("agua retenida exacta F(S), m³ (minimum-cost maximum-flow = Dinic)")
    ax.set_ylabel("error del topological greedy fill (%)")
    top_legend(ax)
    save(fig, "g16_oraculos_error")

    fig, ax = plt.subplots(figsize=(7, 2.8))
    names = [("mcmf", "Minimum-cost maximum-flow\n(network simplex)"), ("dinic", "Maximum flow\n(Dinic)"), ("fill", "Topological\ngreedy fill")]
    data = [[e[f"{k}_ms"] for e in E] for k, _ in names]
    parts = ax.boxplot(data, vert=False, widths=.5, patch_artist=True, showfliers=False,
                       medianprops=dict(color="#1d1b18"), whiskerprops=dict(color="#6b675f"), capprops=dict(color="#6b675f"))
    for b, c in zip(parts["boxes"], ["#2a78d6", "#eb6834", "#1baf7a"]):
        b.set_facecolor(c); b.set_alpha(.8); b.set_edgecolor("white")
    ax.set_yticks([1, 2, 3], [lab for _, lab in names], fontsize=8)
    ax.set_xscale("log"); ax.set_xticks([1, 2, 5, 10, 20, 50, 100]); ax.xaxis.set_minor_formatter(lambda v, _: "")
    ax.xaxis.set_major_formatter(lambda v, _: fmt(v)); ax.set_xlabel("milisegundos por evaluación de F(S) (escala log)"); ax.grid(axis="y", visible=False)
    save(fig, "g17_oraculos_tiempo")


def iota_fig():
    p = ROOT / "sensibilidad.json"
    if not p.exists():
        return
    F = json.loads(p.read_text())["interflow"]; R = F["rows"]
    io = [100 * r["iota"] for r in R]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7, 2.8))
    for ax in (a1, a2):
        ax.axvspan(20, 60, color="#efece6", zorder=0)
        ax.set_xlabel(r"$\iota$: agua drenada que toman las raíces ladera abajo (%)"); ax.set_xlim(0, 100)
    a1.plot(io, [r["net_ls_30000"] for r in R], color="#eb6834", lw=2)
    a1.axhline(0, color="#1d1b18", lw=1); a1.set_ylabel("ganancia neta media (L/s)")
    a1.axvline(100 * F["iota_g0"], color="#6b675f", lw=1, ls=":")
    a2.plot(io, [r["p_pos"] for r in R], color="#2a78d6", lw=2)
    a2.axhline(50, color="#1d1b18", lw=1); a2.set_ylabel("P(G > 0) (%)"); a2.set_ylim(0, 102)
    if F["iota_p50"] is not None:
        a2.axvline(100 * F["iota_p50"], color="#6b675f", lw=1, ls=":")
    fig.tight_layout()
    save(fig, "g_iota")


def density_fig():
    p, q = ROOT / "densidad.json", ROOT / "campo.json"
    if not (p.exists() and q.exists()):
        return
    D = json.loads(p.read_text())["sites"]; F = json.loads(q.read_text())["sites"]
    cols = dict(zip(D, ["#2a78d6", "#eb6834", "#1baf7a"]))
    fig, axes = plt.subplots(1, 2, figsize=(7, 3), sharey=True)
    for ax, storm in zip(axes, ("40", "5")):
        for name, v in D.items():
            L = v["layouts"]
            ax.plot([l["m_per_ha"] for l in L], [100 * l["phi"][storm] for l in L], "o-", color=cols[name], ms=4, lw=1.6,
                    label=name if storm == "40" else None)
            ax.plot(F[name]["m_per_ha"], 100 * F[name]["phi"][storm], "D", color=cols[name], ms=6, mec="white", mew=0.8)
        ax.set_xscale("log"); ax.set_xticks([10, 30, 100, 300, 700]); ax.xaxis.set_minor_formatter(lambda v, _: "")
        ax.xaxis.set_major_formatter(lambda v, _: fmt(v)); ax.set_ylim(0, 80)
        ax.set_xlabel("metros de barrera por hectárea"); ax.set_title(f"tormenta de {storm} mm", fontsize=9, color="#4a4740")
    axes[0].set_ylabel("escurrimiento retenido (%)")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.0), fontsize=9)
    save(fig, "g_densidad")


def maps(src):
    """Crop the app screenshots to the map area (drop the sidebar)."""
    for name, out in (("fig_cuencas", "m1_cuencas"), ("fig_optim", "m2_optimizacion"),
                      ("fig_barreras", "m3_barreras"), ("fig_sim", "m4_simulacion")):
        p = Path(src) / f"{name}.jpg"
        if not p.exists():
            continue
        im = Image.open(p)
        side = 300 if name != "fig_barreras" else 300
        im.crop((side, 0, im.width, im.height)).save(OUT / f"{out}.png")
        print("wrote", out)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for fn in (ha_catchment, criteria, robustness, water, productivity, barriers, storm, mcmf,
               uncertainty, duals, gumbel_fig, pareto_fig, supply_fig, fate_figs, oracle_figs, iota_fig, density_fig):
        fn()
    # map figures are rendered from data by informe/mapas.py
