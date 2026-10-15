"""Generate informe.tex = preambulo.tex + body, with every number taken from the data.

    .venv/bin/python informe/generar.py && cd informe && tectonic informe.tex
Inputs: web/stats.json, docs/data/meta.json, docs/data/sites.json, informe/extras.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
S = json.loads((ROOT.parent / "web" / "stats.json").read_text())
META = json.loads((ROOT.parent / "docs" / "data" / "meta.json").read_text())
SITES = json.loads((ROOT.parent / "docs" / "data" / "sites.json").read_text())
EX = json.loads((ROOT / "extras.json").read_text())
MA = json.loads((ROOT / "math.json").read_text())
AB = json.loads((ROOT / "abasto.json").read_text())
DE = json.loads((ROOT / "destino.json").read_text())

SHORT = {"Presa La Boca": "La Boca", "Acuífero Santa Catarina (pozos SADM)": "Santa Catarina",
         "Presa Cerro Prieto": "Cerro Prieto", "Presa El Cuchillo": "El Cuchillo"}
ORDER = ["Presa La Boca", "Acuífero Santa Catarina (pozos SADM)", "Presa Cerro Prieto", "Presa El Cuchillo"]


def n(v, d=0):
    s = f"{v:,.{d}f}"
    return s


def pct(v, d=0):
    return f"{v:.{d}f}\\%"


# ---------------------------------------------------------------- derived numbers
hc = S["ha_by_catchment"]
alta = sum(v["alta"] for v in hc.values()); media = sum(v["media"] for v in hc.values())
directa = sum(hc[k]["alta"] for k in ORDER[:3])
rob = S["robustness_hist"]; robusta = sum(b["ha"] for b in rob if b["from"] >= 0.5)
crit = S["criteria_by_class"]
mx, bal = EX["max"], EX["balanced"]
SEC_Y = 31_536_000
ls = lambda m3: m3 / SEC_Y * 1000
storm = S["storm_sites"]
avg_out = sum(r["outflow_reduction_pct"] for r in storm) / len(storm)
avg_peak = sum(r["peak_reduction_pct"] for r in storm) / len(storm)
inf_lo = min(r["extra_infiltration_m3"] for r in storm); inf_hi = max(r["extra_infiltration_m3"] for r in storm)
bb = S["barrier_budget_curves"]
at = lambda name, m: next(p["intercepted_pct"] for p in bb[name] if p["budget_m"] == m)
b500 = [at(k, 500) for k in bb]; b1500 = [at(k, 1500) for k in bb]; b3000 = [at(k, 3000) for k in bb]
mc = S["mcmf_vs_greedy"]
gain = lambda r: 100 * (r["mcmf_m3"] / r["greedy_m3"] - 1)
mc_rows = [(site, r) for site, rows in mc.items() for r in rows]
gain_max = max(gain(r) for _, r in mc_rows); gain_40 = [gain(r) for _, r in mc_rows if r["storm_mm"] == 40]
ret5 = [100 * r["mcmf_m3"] / r["runoff_m3"] for _, r in mc_rows if r["storm_mm"] == 5]
ret40 = [100 * r["mcmf_m3"] / r["runoff_m3"] for _, r in mc_rows if r["storm_mm"] == 40]
prod = S["productivity_by_supply"]
tg = {t["target_ls"]: t["ha"] for t in EX["targets"]}
wc = S["water_curves"]["normal"]
per1000 = [ls_ for ls_ in []]
ls_at = lambda ha: min(wc, key=lambda p: abs(p["ha"] - ha))["ls"]
slope_first = ls_at(1000) / 1; slope_last = (ls_at(60000) - ls_at(50000)) / 10

sites_rows = []
for i, s in enumerate(SITES, 1):
    w, t = s["why"], s["barriers"]["totals"]
    obra = s["recommendation"]["obra"].replace("Barreras de material vegetal muerto en curvas de nivel", "Material vegetal muerto") \
        .replace("Reforestación con nativas + barreras de material vegetal", "Reforestación + material vegetal") \
        .replace("Barreras de piedra acomodada", "Piedra acomodada").replace("Zanja-bordo + reforestación con nativas", "Zanja-bordo + reforestación")
    sites_rows.append(f"{i} & {SHORT[w['supply']]} & {w['opt_rank']} & {n(w['m3_per_ha'])} & {n(w['rain_mm'])} & "
                      f"{s['stats']['priority']:.2f} · {round(100 * w['robustness'])}\\% & {obra} & {round(t['intercepted_pct'])}\\% \\\\")

opt_rows = []
for k in ORDER:
    a = mx["by_supply"].get(k, {"ha": 0, "m3": 0}); b = bal["by_supply"].get(k, {"ha": 0, "m3": 0})
    opt_rows.append(f"{k.replace(' (pozos SADM)', '')} & {n(a['ha'])} & {n(ls(a['m3']), 1)} & {n(b['ha'])} & {n(ls(b['m3']), 1)} \\\\")

V = {
    "alta": n(alta), "media": n(media), "robusta": n(robusta), "robusta_pct": pct(100 * robusta / alta),
    "directa": n(directa), "directa_pct": pct(100 * directa / alta), "quemada": n(EX["quemada_ha"]),
    "sc_alta": n(hc["Acuífero Santa Catarina (pozos SADM)"]["alta"]), "lb_alta": n(hc["Presa La Boca"]["alta"]),
    "c_veg_a": f"{crit['alta']['vegetation']:.2f}", "c_veg_b": f"{crit['baja']['vegetation']:.2f}",
    "c_sm_a": f"{crit['alta']['moisture']:.2f}", "c_sm_b": f"{crit['baja']['moisture']:.2f}",
    "c_sl_a": f"{crit['alta']['slope']:.2f}", "c_sl_b": f"{crit['baja']['slope']:.2f}",
    "max_ls": n(mx["impact"]["ls"], 0), "max_days": n(mx["impact"]["days_of_zmm_supply"], 1),
    "bal_ls": n(bal["impact"]["ls"], 0), "bal_days": n(bal["impact"]["days_of_zmm_supply"], 1),
    "max_m3": n(mx["m3"] / 1e6, 2), "bal_m3": n(bal["m3"] / 1e6, 2),
    "bal_cost": pct(100 * (1 - bal["m3"] / mx["m3"])),
    "dr_ls": n(mx["drought"]["ls"], 0), "dr_pct": pct(mx["drought"]["pct_of_normal"]), "dr_overlap": pct(mx["drought"]["selection_overlap_pct"]),
    "t25": n(tg[25]), "t50": n(tg[50]), "t100": n(tg[100]), "t200": n(tg[200]),
    "ls_per1000": n(ls_at(1000), 0), "ls_per1000_last": n(slope_last, 0),
    "prod_lb": n(prod["Presa La Boca"]["median"]), "prod_sc": n(prod["Acuífero Santa Catarina (pozos SADM)"]["median"]),
    "prod_cp": n(prod["Presa Cerro Prieto"]["median"]), "prod_ec": n(prod["Presa El Cuchillo"]["median"]),
    "b500": f"{min(b500):.0f} a {max(b500):.0f}\\%", "b1500": f"{min(b1500):.0f} a {max(b1500):.0f}\\%", "b3000": f"{min(b3000):.0f} a {max(b3000):.0f}\\%",
    "avg_out": pct(avg_out), "avg_peak": pct(avg_peak), "inf_lo": n(inf_lo), "inf_hi": n(inf_hi),
    "best_out": pct(max(r["outflow_reduction_pct"] for r in storm)),
    "gain_max": f"{gain_max:.1f}", "gain_40": f"{min(gain_40):+.1f} a {max(gain_40):+.1f}",
    "ret5": f"{min(ret5):.0f} a {max(ret5):.0f}\\%", "ret40": f"{min(ret40):.1f} a {max(ret40):.1f}\\%",
    "rho": " · ".join(f"{r:,} mm: {100 * f:.0f}\\%" for r, f in zip(EX["retention"]["rain"], EX["retention"]["frac"])),
    "opt_rows": "\n".join(opt_rows), "sites_rows": "\n".join(sites_rows),
    "max_tot_ls": n(ls(mx["m3"]), 1), "bal_tot_ls": n(ls(bal["m3"]), 1),
}

mc = MA["monte_carlo"]; kd = MA["knapsack_duals"]; pa = MA["pareto"]; gu = MA["gumbel"]; cd = {r["storm_mm"]: r for r in MA["capacity_duals"]}
dual_at = lambda ha: next(p["marginal_ls_per_1000ha"] for p in kd["curve"] if p["ha"] == ha)
pa_at = lambda a: min(pa, key=lambda r: abs(r["alpha"] - a))
t40 = [g["T_40mm"] for g in gu.values()]; x10 = [g["return_levels"]["10"] for g in gu.values()]
fill = [r for site, rows in S["mcmf_vs_greedy"].items() for r in rows]
V.update({
    "mc_mean": n(sum(mc["samples_max"]) / len(mc["samples_max"]), 1),
    "mc_se": f"{(__import__('statistics').stdev(mc['samples_max']) / len(mc['samples_max']) ** 0.5):.2f}",
    "mc_p5": n(mc["max_ls"][0]), "mc_p50": n(mc["max_ls"][1]), "mc_p95": n(mc["max_ls"][2]),
    "mcb_p5": n(mc["balanced_ls"][0]), "mcb_p50": n(mc["balanced_ls"][1]), "mcb_p95": n(mc["balanced_ls"][2]),
    "mc_p80": pct(mc["selection_prob_of_base_cells"]["p_ge_80"]),
    "dual_3000": n(dual_at(3000), 1), "dual_20000": n(dual_at(20000), 1),
    "dual_bal": "; ".join(f"{SHORT[k]}: {v:.1f}" for k, v in kd["balanced_marginal_ls_per_1000ha"].items()) + " L/s por 1,000 ha",
    "w0": n(pa_at(0)["ls"], 1), "j0": f"{pa_at(0)['jain']:.2f}", "w1": n(pa_at(1)["ls"], 1), "j1": f"{pa_at(1)['jain']:.2f}",
    "w05": n(pa_at(0.5)["ls"], 1), "j05": f"{pa_at(0.5)['jain']:.2f}",
    "pareto_slope": f"{0.1 * (pa_at(0)['ls'] - pa_at(1)['ls']) / (pa_at(1)['jain'] - pa_at(0)['jain']):.2f}",
    "t40_range": f"{min(t40):.1f} a {max(t40):.1f}", "x10_range": f"{min(x10):.0f} a {max(x10):.0f}",
    "fill_mm": "10",
    "sat40": pct(cd[40]["saturated_pct"]), "sc40": f"{cd[40]['shadow_capacity']:.2f}", "sm40": f"{cd[40]['shadow_meters']:.2f}",
    "sat10": pct(cd[10]["saturated_pct"]), "sc10": f"{cd[10]['shadow_capacity']:.2f}", "sm10": f"{cd[10]['shadow_meters']:.2f}",
})

# ---------------------------------------------------------------- contribution to the supply system (abasto.py)
sc = {s["ha"]: s for s in AB["scenarios"]}; all_s = AB["scenarios"][-1]
key = {3000: "ab3", 10000: "ab10", 30000: "ab30", 60000: "ab60"}
ab_rows = []
for s in AB["scenarios"]:
    lo, _, hi = s["mc_ls_drought"]
    label = n(s["ha"]) if s is not all_s else f"{n(s['ha'])} (todas)"
    ab_rows.append(f"{label} & {n(s['ls'])} & {n(s['ls_drought'])} & {n(lo)} a {n(hi)} & "
                   f"{pct(100 * s['ls'] / AB['demand_ls'], 1)} & {pct(s['pct_deficit_drought'], 1)} \\\\")
    k = key.get(s["ha"], "aball")
    V.update({f"{k}_d": n(s["ls_drought"]), f"{k}_pct": pct(s["pct_deficit_drought"]),
              f"{k}_lo": n(lo), f"{k}_hi": n(hi), f"{k}_dem": pct(100 * s["ls_drought"] / AB["demand_ls"], 1)})
V.update({"abasto_rows": "\n".join(ab_rows), "ab_all_ha": n(all_s["ha"]),
          "ab60_sc": n(sc[60000]["by_supply"]["Acuífero Santa Catarina (pozos SADM)"]["ls_drought"]),
          "ab60_cp": n(sc[60000]["by_supply"]["Presa Cerro Prieto"]["ls_drought"])})

# ---------------------------------------------------------------- fate of retained water and vegetation belts (destino.py)
FULL = {"Presa La Boca": "lb", "Presa Cerro Prieto": "cp", "Acuífero Santa Catarina (pozos SADM)": "sc", "Presa El Cuchillo": "ec"}
dec = lambda v: f"{v:.2f}"
prior_rows = []
for name in ORDER:
    ab = FULL[name]; et = DE["et"][name]["ratio"]; ph = DE["phi"][name]; ta = DE["tau"][name]
    extra = " ($\\times k_{\\text{EC}}$)" if ab == "ec" else ""
    prior_rows.append(f"{SHORT[name]}{extra} & $\\mathcal U({dec(DE['e_min'])},\\,{dec(et)})$ & $\\mathcal U({dec(ph[0])},\\,{dec(ph[1])})$ & $\\mathcal U({dec(ta[0])},\\,{dec(ta[1])})$ \\\\")
    f = DE["factor"][name]; fo = DE["factor_optimista"][name]
    V.update({f"et_{ab}": pct(100 * et), f"g_{ab}": f"{f['mean']:+.2f}".replace("+", ""), f"pg_{ab}": pct(f["p_pos"]),
              f"go_{ab}": f"{fo['mean']:.2f}", f"pgo_{ab}": pct(fo["p_pos"], 1)})
SEL = DE["selections"]
lab = {"bruta": "Máximo de agua bruta", "neta": "Máxima ganancia neta esperada"}
neta_rows = []
for key in ("bruta_3000", "neta_3000", "bruta_30000", "neta_30000"):
    r = SEL[key]; kind, H = key.split("_")
    neta_rows.append(f"{lab[kind]}, {n(int(H))} ha & {n(r['gross_ls'])} & {n(r['net_ls'][1])} & {n(r['net_ls'][0])} a {n(r['net_ls'][2])} & {pct(r['p_pos'])} \\\\")
nice = {"f_C": "el coeficiente de escurrimiento", "kappa": "la capacidad por metro", "b": "el sesgo de CHIRPS", "k_EC": "la conectividad de El Cuchillo"}
def pname(lbl):
    if lbl in nice: return nice[lbl]
    par, src = lbl.split("_", 1)
    return {"e": "la evapotranspiración", "phi": "la fracción que llega a la fuente", "tau": "el escurrimiento que ya llegaba"}[par] + " en " + SHORT[src]
top = DE["spearman"][:4]
spear = ", ".join(f"{pname(l)} ($r_s={r:+.2f}$)" for l, r in top[:-1]) + f" y {pname(top[-1][0])} ($r_s={top[-1][1]:+.2f}$)"
b3, b30 = DE["inegi"]["neta_3000"], DE["inegi"]["neta_30000"]
belt_rows = [f"{k} & {n(b3[k])} & {n(b30[k])} \\\\" for k in b3 if b3[k] + b30[k] > 0]
V.update({"fate_n": n(DE["n"]), "prior_rows": "\n".join(prior_rows), "neta_rows": "\n".join(neta_rows),
          "n30b_g": n(SEL["bruta_30000"]["gross_ls"]), "n30b": n(SEL["bruta_30000"]["net_ls"][1]), "n30b_pp": pct(SEL["bruta_30000"]["p_pos"]),
          "n30b_cp": n(SEL["bruta_30000"]["ha_by_supply"]["Presa Cerro Prieto"]),
          "n30n": n(SEL["neta_30000"]["net_ls"][1]), "n30n_lo": n(SEL["neta_30000"]["net_ls"][0]), "n30n_hi": n(SEL["neta_30000"]["net_ls"][2]),
          "n30n_pp": pct(SEL["neta_30000"]["p_pos"]), "n30n_mean": n(SEL["neta_30000"]["net_mean"]),
          "n3n": n(SEL["neta_3000"]["net_ls"][1]), "n3n_mean": n(SEL["neta_3000"]["net_mean"], 1),
          "spearman_top": spear, "belt_rows": "\n".join(belt_rows),
          "inegi_pino3": n(b3["Bosque de pino y pino-encino"]), "inegi_sub3": n(b3["Matorral submontano"]),
          "inegi_enc3": n(b3["Bosque de encino y encino-pino"]), "inegi_oya3": n(b3["Bosque de oyamel y ayarín"]),
          "inegi_des30": n(b30["Matorral desértico rosetófilo y micrófilo"])})

BODY = (ROOT / "cuerpo.tex").read_text()
for k, v in V.items():
    BODY = BODY.replace(f"«{k}»", v)
missing = [m for m in __import__("re").findall(r"«(\w+)»", BODY)]
if missing:
    raise SystemExit(f"placeholders without value: {missing}")
(ROOT / "informe.tex").write_text((ROOT / "preambulo.tex").read_text() + BODY)
print("wrote informe.tex")
