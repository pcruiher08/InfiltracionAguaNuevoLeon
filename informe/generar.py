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
    if s.startswith("-"):
        s = "\u2212" + s[1:] if s.strip("-0.,") else s[1:]
    return s


def sg(v, d=1):
    """Signed number with a true minus sign."""
    s = f"{v:+.{d}f}"
    return s.replace("-", "\u2212") if s.strip("+-0.") else s[1:]


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
PARK = {"Cumbres de Monterrey": "PN", "C.A.D.N.R. 026 Bajo Río San Juan": "APRN", None: "No"}
for i, s in enumerate(SITES, 1):
    w, t = s["why"], s["barriers"]["totals"]
    obra = s["recommendation"]["obra"].replace("Barreras de material vegetal muerto en curvas de nivel", "Material vegetal muerto") \
        .replace("Reforestación con nativas + barreras de material vegetal", "Reforestación + material vegetal") \
        .replace("Barreras de piedra acomodada", "Piedra acomodada").replace("Zanja-bordo + reforestación con nativas", "Zanja-bordo + reforestación")
    sites_rows.append(f"{i} & {w['opt_rank']} & {n(w['m3_per_ha'])} & {n(w['net_m3_per_ha'])} & {n(w['rain_mm'])} & "
                      f"{s['stats']['priority']:.2f} · {round(100 * w['robustness'])}\\% & {obra} & {round(t['intercepted_pct'])}\\% & {PARK.get(w.get('park'), 'Otra')} \\\\")

opt_rows = []
for k in ORDER:
    a = mx["by_supply"].get(k, {"ha": 0, "m3": 0}); b = bal["by_supply"].get(k, {"ha": 0, "m3": 0})
    opt_rows.append(f"{k.replace(' (pozos SADM)', '')} & {n(a['ha'])} & {n(ls(a['m3']), 1)} & {n(b['ha'])} & {n(ls(b['m3']), 1)} \\\\")

V = {
    "alta": n(alta), "media": n(media), "robusta": n(robusta), "robusta_pct": pct(100 * robusta / alta),
    "directa": n(directa), "directa_pct": pct(100 * directa / alta), "quemada": n(S["burned_high"]),
    "p50": f"{S['class_percentiles']['priority_p50']:.2f}", "p80": f"{S['class_percentiles']['priority_p80']:.2f}",
    "sc_alta": n(hc["Acuífero Santa Catarina (pozos SADM)"]["alta"]), "lb_alta": n(hc["Presa La Boca"]["alta"]),
    "c_veg_a": f"{crit['alta']['vegetation']:.2f}", "c_veg_b": f"{crit['baja']['vegetation']:.2f}",
    "c_sm_a": f"{crit['alta']['moisture']:.2f}", "c_sm_b": f"{crit['baja']['moisture']:.2f}",
    "c_sl_a": f"{crit['alta']['slope']:.2f}", "c_sl_b": f"{crit['baja']['slope']:.2f}",
    "c_con_a": f"{crit['alta']['connectivity']:.2f}", "c_con_b": f"{crit['baja']['connectivity']:.2f}",
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
    "gain_max": f"{gain_max:.1f}", "gain_40": f"{sg(min(gain_40), 1)} a {sg(max(gain_40), 1)}",
    "ret5": f"{min(ret5):.0f} a {max(ret5):.0f}\\%", "ret40": f"{min(ret40):.1f} a {max(ret40):.1f}\\%",
    "rho": ", ".join(f"{100 * f:.0f}\\%" for f in EX["retention"]["frac"][:-1]) + f" y {100 * EX['retention']['frac'][-1]:.0f}\\% para "
           + ", ".join(f"{r:,}" for r in EX["retention"]["rain"][:-1]) + f" y {EX['retention']['rain'][-1]:,} mm",
    "opt_rows": "\n".join(opt_rows), "sites_rows": "\n".join(sites_rows),
    "sitios_parque": n(sum(1 for s in SITES if s["why"].get("park") == "Cumbres de Monterrey")),
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
    lo, mean_d, hi = s["mc_ls_drought"]; mean_n = s["mc_ls"][1]          # Monte Carlo mean and 90 % interval
    label = n(s["ha"]) if s is not all_s else f"{n(s['ha'])} (todas)"
    ab_rows.append(f"{label} & {n(mean_n)} & {n(mean_d)} & {n(lo)} a {n(hi)} & "
                   f"{pct(100 * mean_n / AB['demand_ls'], 1)} & {pct(100 * mean_d / AB['deficit_ls'], 1)} \\\\")
    k = key.get(s["ha"], "aball")
    V.update({f"{k}_d": n(mean_d), f"{k}_pct": pct(100 * mean_d / AB["deficit_ls"]),
              f"{k}_lo": n(lo), f"{k}_hi": n(hi), f"{k}_dem": pct(100 * mean_d / AB["demand_ls"], 1)})
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
    V.update({f"et_{ab}": pct(100 * et), f"g_{ab}": f"{sg(f['mean'], 2)}".replace("+", ""), f"pg_{ab}": pct(f["p_pos"]),
              f"go_{ab}": n(fo["mean"], 2), f"pgo_{ab}": pct(fo["p_pos"], 1)})
SEL = DE["selections"]
lab = {"bruta": "Máximo de agua bruta", "neta": "Máxima ganancia neta esperada"}
neta_rows = []
for key in ("bruta_3000", "neta_3000", "bruta_30000", "neta_30000"):
    r = SEL[key]; kind, H = key.split("_")
    neta_rows.append(f"{lab[kind]}, {n(int(H))} ha & {n(r['gross_ls'])} & {n(r['net_mean'], 1)} & {n(r['net_ls'][1])} & {n(r['net_ls'][0])} a {n(r['net_ls'][2])} & {pct(r['p_pos'])} \\\\")
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
          "n30b_g": n(SEL["bruta_30000"]["gross_ls"]), "n30b": n(SEL["bruta_30000"]["net_mean"]), "n30b_pp": pct(SEL["bruta_30000"]["p_pos"]),
          "n30b_cp": n(SEL["bruta_30000"]["ha_by_supply"]["Presa Cerro Prieto"]),
          "n30n": n(SEL["neta_30000"]["net_mean"]), "n30n_lo": n(SEL["neta_30000"]["net_ls"][0]), "n30n_hi": n(SEL["neta_30000"]["net_ls"][2]),
          "n30n_pp": pct(SEL["neta_30000"]["p_pos"]), "n30n_mean": n(SEL["neta_30000"]["net_mean"]),
          "n3n": n(SEL["neta_3000"]["net_mean"], 1), "n3n_mean": n(SEL["neta_3000"]["net_mean"], 1),
          "spearman_top": spear, "belt_rows": "\n".join(belt_rows),
          "inegi_pino3": n(b3["Bosque de pino y pino-encino"]), "inegi_sub3": n(b3["Matorral submontano"]),
          "inegi_enc3": n(b3["Bosque de encino y encino-pino"]), "inegi_oya3": n(b3["Bosque de oyamel y ayarín"]),
          "inegi_des30": n(b30["Matorral desértico rosetófilo y micrófilo"])})

# ---------------------------------------------------------------- erosion and dam sedimentation (sedimento.py)
SE = json.loads((ROOT / "sedimento.json").read_text())
lab_s = {"bruta": "Máximo de agua bruta", "sedimento": "Máximo suelo retenido en presas"}
sed_rows = []
for key in ("bruta_3000", "sedimento_3000", "bruta_30000", "sedimento_30000"):
    r = SE["selections"][key]; kind, H = key.split("_")
    k3 = lambda v: n(v / 1000)
    z1 = lambda v: (lambda t: "0.0" if t == "-0.0" else t)(n(v / 1e6, 1))
    sed_rows.append(f"{lab_s[kind]}, {n(int(H))} ha & {n(r['ha_dams'])} & {k3(r['m3_yr'][1])} ({k3(r['m3_yr'][0])} a {k3(r['m3_yr'][2])}) & "
                    f"{n(r['m3_50yr'][1] / 1e6, 1)} & {z1(r['water_m3_yr'][1])} ({z1(r['water_m3_yr'][0])} a {z1(r['water_m3_yr'][2])}) \\\\")
s30 = SE["selections"]["sedimento_30000"]
V.update({"sed_n": n(SE["n"]), "sed3_50": n(SE["selections"]["sedimento_3000"]["m3_50yr"][1] / 1e6, 1), "sed_rows": "\n".join(sed_rows),
          "er_cp": n(SE["erosion_t_ha_yr_lambda22"]["Presa Cerro Prieto"]), "er_lb": n(SE["erosion_t_ha_yr_lambda22"]["Presa La Boca"]),
          "sed30_m3": n(s30["m3_yr"][1]), "sed30_lo": n(s30["m3_yr"][0]), "sed30_hi": n(s30["m3_yr"][2]),
          "sed30_50": n(s30["m3_50yr"][1] / 1e6, 1), "sed30_pct": pct(100 * s30["m3_50yr"][1] / 300e6, 1),
          "sed30_w": n(s30["water_m3_yr"][1] / 1e6, 1), "sed30_wabs": n(-s30["water_m3_yr"][1] / 1e6, 1)})

# ---------------------------------------------------------------- cost (costo.py)
CO = json.loads((ROOT / "costo.json").read_text())
mill = lambda v: n(v / 1e6, 1)
cost_rows = []
for key in ("bruta_3000", "neta_3000", "bruta_30000", "neta_30000"):
    r = CO["selections"][key]; kind, H = key.split("_")
    per_net = mill(r["mxn_per_net_ls"]) if r["mxn_per_net_ls"] else "no definido"
    cost_rows.append(f"{lab[kind]}, {n(int(H))} ha & {n(r['cost_mxn'][0] / 1e6)} a {n(r['cost_mxn'][1] / 1e6)} & "
                     f"{mill(r['mxn_per_gross_ls'][0])} a {mill(r['mxn_per_gross_ls'][1])} & {per_net} & {pct(r['p_cheaper_than_cuchillo'], 1)} \\\\")
c30 = CO["selections"]["neta_30000"]
V.update({"cost_rows": "\n".join(cost_rows), "cb30_lo": mill(c30["mxn_per_gross_ls"][0]), "cb30_hi": mill(c30["mxn_per_gross_ls"][1]),
          "cn30": n(c30["mxn_per_net_ls"] / 1e6), "cp30": pct(c30["p_cheaper_than_cuchillo"], 1)})

# ---------------------------------------------------------------- calibration (calibracion.py)
CA = json.loads((ROOT / "calibracion.json").read_text()); PO = CA["posterior"]
cs = lambda k: (SEL[k], PO["selections"][k])
b3, b3c = cs("bruta_3000"); b30, b30c = cs("bruta_30000"); n3, n3c = cs("neta_3000"); n30, n30c = cs("neta_30000")
cal_rows = [
    f"Agua bruta (máximo de agua bruta) & {n(b3['gross_ls'], 1)} & {n(b3c['gross_ls'], 1)} & {n(b30['gross_ls'])} & {n(b30c['gross_ls'])} \\\\",
    f"Agua neta, media & {n(n3['net_mean'], 1)} & {n(n3c['net_mean'], 1)} & {n(n30['net_mean'], 1)} & {n(n30c['net_mean'], 1)} \\\\",
    f"Agua neta, intervalo de 90\\% & {n(n3['net_ls'][0], 1)} a {n(n3['net_ls'][2], 1)} & {n(n3c['net_ls'][0], 1)} a {n(n3c['net_ls'][2], 1)} & "
    f"{n(n30['net_ls'][0])} a {n(n30['net_ls'][2])} & {n(n30c['net_ls'][0])} a {n(n30c['net_ls'][2])} \\\\",
    f"$\\Pr[W_{{\\text{{neta}}}}>0]$ & {pct(n3['p_pos'])} & {pct(n3c['p_pos'])} & {pct(n30['p_pos'])} & {pct(n30c['p_pos'])} \\\\"]
V.update({"cal_rows": "\n".join(cal_rows), "cal_qobs": n(CA["q_obs_mm"], 1), "cal_ce": f"{CA['ce_obs']:.2f}", "cal_p": n(CA["rain_mm"]),
          "cal_qmod": n(CA["q_model_mm"], 1), "cal_f": f"{CA['f_hat']:.2f}", "cal_fpost": f"{PO['f_post_mean']:.2f}", "cal_ess": n(PO["ess"]),
          "cal_drop": pct(100 * (1 - PO["f_post_mean"] / PO["f_prior_mean"])), "cal_rest": n(CA["rain_mm"] - CA["q_obs_mm"])})

# ---------------------------------------------------------------- protected areas and future climate (clima.py)
CL = json.loads((ROOT / "clima.json").read_text()); PR = CL["protegidas"]
a3, a30 = PR["neta_3000"], PR["neta_30000"]
anp_rows = [f"{k} & {n(a3.get(k, 0))} & {n(a30.get(k, 0))} \\\\" for k in sorted(set(a3) | set(a30), key=lambda k: -a30.get(k, 0))]
cum = "Cumbres de Monterrey (Parque Nacional)"
sit = [i for i, s in enumerate(SITES, 1) if s["why"].get("park") == "Cumbres de Monterrey"]
WORDS = ["Ninguno", "Uno", "Dos", "Tres", "Cuatro", "Cinco", "Seis", "Siete", "Ocho"]
sit_txt = f"{WORDS[len(sit)]} de los ocho sitios sugeridos están dentro del parque." if sit else "Ninguno de los 8 sitios sugeridos está dentro del parque."
fq = lambda v: pct(100 * v)
def crow(lbl, f):
    return f"{lbl} & {f('ssp245')} & {f('ssp585')} \\\\"
clima_rows = [
    crow("Cambio de la lluvia media de julio a junio", lambda sc: f"{sg(CL[sc]['change_mean'], 1)}\\% ({sg(CL[sc]['change_range'][0], 1)} a {sg(CL[sc]['change_range'][1], 1)})"),
    crow(f"Frecuencia de un año como 2021 a 2022 (histórica: {fq(CL['q_star'])})", lambda sc: f"{fq(CL[sc]['freq_mean'])} ({fq(CL[sc]['freq_range'][0])} a {fq(CL[sc]['freq_range'][1])})"),
    crow("Modelos con sequías más frecuentes", lambda sc: f"{CL[sc]['models_more_droughts']} de {CL['n_models']}"),
    crow("Cambio del agua bruta con 3,000 ha", lambda sc: f"{sg(CL[sc]['gross_change_pct'], 1)}\\%")]
V.update({"anp_rows": "\n".join(anp_rows), "anp_cumbres3": n(a3.get(cum, 0)), "anp_cumbres30": n(a30.get(cum, 0)), "anp_sitios": sit_txt,
          "anp_resp": f"La superficie más valiosa para el abasto está dentro del Parque Nacional Cumbres de Monterrey: {n(a3.get(cum, 0))} de las 3,000 ha y {n(a30.get(cum, 0))} de las 30,000 ha seleccionadas por ganancia neta. La restauración es compatible con un parque nacional, pero requiere autorización de la CONANP.",
          "clima_nmod": str(CL["n_models"]), "clima_rows": "\n".join(clima_rows), "clima_p21": n(CL["chirps"]["p_2021_22"]),
          "clima_pm": n(CL["chirps"]["mean"]), "clima_q": fq(CL["q_star"]), "clima_T": n(1 / CL["q_star"]),
          "clima_more245": str(CL["ssp245"]["models_more_droughts"]), "clima_more585": str(CL["ssp585"]["models_more_droughts"]),
          "clima_f245": fq(CL["ssp245"]["freq_mean"]), "clima_f585": fq(CL["ssp585"]["freq_mean"]),
          "clima_g245": f"{sg(CL['ssp245']['gross_change_pct'], 1)}\\%", "clima_g585": f"{sg(CL['ssp585']['gross_change_pct'], 1)}\\%"})

# ---------------------------------------------------------------- Campo Buenos Aires aquifer (CONAGUA, DR 1907)
AQ = {"recarga": 57.0, "concesion": 62.803450, "area_trib": 1120, "area_recarga": 450}
hm3 = lambda l_s: l_s * SEC_Y / 1e9
n30s = SEL["neta_30000"]; e_sc = (DE["e_min"] + DE["et"]["Acuífero Santa Catarina (pozos SADM)"]["ratio"]) / 2
phi_sc = sum(DE["phi"]["Acuífero Santa Catarina (pozos SADM)"]) / 2
R_sc = hm3(n30s["gross_ls"]); rech = (1 - e_sc) * phi_sc * R_sc
net_u, net_c = hm3(n30s["net_mean"]), hm3(PO["selections"]["neta_30000"]["net_mean"])
deficit = AQ["concesion"] - AQ["recarga"]
V.update({"aq_rech": n(AQ["recarga"], 1), "aq_conc": n(AQ["concesion"], 1), "aq_def": n(deficit, 1),
          "aq_trib": n(AQ["area_trib"]), "aq_area": n(AQ["area_recarga"]), "aq_mm": n(AQ["recarga"] / AQ["area_recarga"] * 1000),
          "aq_R": n(R_sc, 1), "aq_inc": n(rech, 1), "aq_inc_pct": pct(100 * rech / AQ["recarga"], 1),
          "aq_inc_mm": n(rech / 300 * 1000), "aq_net_u": n(net_u, 2), "aq_net_c": n(net_c, 2),
          "aq_net_pct": f"{100 * net_c / AQ['recarga']:.1f} a {pct(100 * net_u / AQ['recarga'], 1)}", "aq_def_pct_u": pct(100 * net_u / deficit), "aq_def_pct_c": pct(100 * net_c / deficit)})

# ---------------------------------------------------------------- retention oracles (oraculos.py)
import statistics as _st
OR = json.loads((ROOT / "oraculos.json").read_text())
E, SL = OR["evals"], OR["selections"]
med = lambda k: _st.median(e[f"{k}_ms"] for e in E)
err = lambda k: [100 * (e[k] / e["mcmf"] - 1) for e in E if e["mcmf"] > 0]
sel_t = {k: sum(x["seconds"] for x in SL if x["oracle"] == k) for k in ("mcmf", "dinic", "fill")}
sel_r = {k: [] for k in ("dinic", "fill")}
for x in SL:
    if x["oracle"] != "mcmf":
        ref = next(y["retained_exact"] for y in SL if y["oracle"] == "mcmf" and y["site"] == x["site"] and y["storm_mm"] == x["storm_mm"])
        sel_r[x["oracle"]].append(100 * (x["retained_exact"] / ref - 1) if ref > 0 else 0.0)
labels = {"mcmf": "\\emph{Minimum-cost maximum-flow} (\\emph{network simplex})", "dinic": "\\emph{Maximum flow} (Dinic)",
          "fill": "\\emph{Topological greedy fill}"}
orac_rows = []
for k in ("mcmf", "dinic", "fill"):
    e = err(k) if k != "mcmf" else [0.0]
    sel = "referencia" if k == "mcmf" else f"{sg(_st.mean(sel_r[k]), 1)}\\%"
    orac_rows.append(f"{labels[k]} & {n(med(k), 1)} & {n(med('mcmf') / med(k), 1)}× & {sg(_st.mean(e), 2)}\\% & {sg(min(e), 2)}\\% & {n(sel_t[k], 1)} & {sel} \\\\")
fe = err("fill")
by = lambda mm: _st.mean(100 * (e["fill"] / e["mcmf"] - 1) for e in E if e["storm_mm"] == mm and e["mcmf"] > 0)
V.update({"orac_rows": "\n".join(orac_rows), "orac_nevals": n(len(E)), "orac_nsites": n(len(OR["sites"])),
          "orac_nrand": n(OR["n_random"]), "orac_nsel": n(len(SL) // 3),
          "orac_storms": ", ".join(str(m) for m in sorted({e["storm_mm"] for e in E})[:-1]) + f" y {max(e['storm_mm'] for e in E)}",
          "orac_dinic_maxerr": n(max(abs(e["dinic"] - e["mcmf"]) for e in E), 2),
          "orac_speed_dinic": n(med("mcmf") / med("dinic"), 1), "orac_speed_fill": n(med("mcmf") / med("fill"), 1),
          "orac_fill_mean": pct(abs(_st.mean(fe)), 2), "orac_fill_max": pct(abs(min(fe)), 1),
          "orac_fill_exact": pct(100 * sum(abs(x) < 0.01 for x in fe) / len(fe)),
          "orac_fill_5": pct(abs(by(5)), 2), "orac_fill_40": pct(abs(by(40)), 2),
          "orac_fill_opt": pct(abs(_st.mean(100 * (e["fill"] / e["mcmf"] - 1) for e in E if e["kind"] == "optimizado" and e["mcmf"] > 0)), 1),
          "orac_fill_rand": pct(abs(_st.mean(100 * (e["fill"] / e["mcmf"] - 1) for e in E if e["kind"] == "aleatorio" and e["mcmf"] > 0)), 1),
          "orac_sel_tiempo_dinic": pct(100 * sel_t["dinic"] / sel_t["mcmf"], 1),
          "orac_sel_fill": f"{sg(_st.mean(sel_r['fill']), 1)}\\% en promedio"})

# ---------------------------------------------------------------- conditions for scaling up
TAUS, PHIS = (0.1, 0.25, 0.4), (0.5, 0.7, 0.9)
R_ha = SEL["neta_30000"]["gross_ls"] * SEC_Y / 1000 / 30000                 # m³ retained per ha and year (Santa Catarina)
g_need = lambda c: c * SEC_Y / 1000 / (CO["cuchillo_mxn_per_ls"]) / R_ha
sc_tau = DE["tau"]["Acuífero Santa Catarina (pozos SADM)"]; sc_phi = DE["phi"]["Acuífero Santa Catarina (pozos SADM)"]
V.update({"esc_head": " & ".join(f"{t:.2f}" for t in TAUS),
          "esc_rows": "\n".join(f"{p:.2f} & " + " & ".join(f"{max(0, 1 - t / p):.2f}" for t in TAUS) + " \\\\" for p in PHIS),
          "esc_R": n(R_ha), "esc_g25": f"{g_need(25000):.2f}", "esc_g50": f"{g_need(50000):.2f}",
          "esc_gmax": f"{(1 - DE['e_min']) * sc_phi[1] - sc_tau[0]:.2f}",
          "et_sc_dec": f"{DE['et']['Acuífero Santa Catarina (pozos SADM)']['ratio']:.2f}"})

BODY = (ROOT / "cuerpo.tex").read_text()
for k, v in V.items():
    BODY = BODY.replace(f"«{k}»", v)
missing = [m for m in __import__("re").findall(r"«(\w+)»", BODY)]
if missing:
    raise SystemExit(f"placeholders without value: {missing}")
(ROOT / "informe.tex").write_text((ROOT / "preambulo.tex").read_text() + BODY)
print("wrote informe.tex")

# ---------------------------------------------------------------- slide deck (same numbers)
SLIDES = (ROOT / "presentacion_plantilla.tex").read_text()
for k, v in V.items():
    SLIDES = SLIDES.replace(f"«{k}»", v)
missing = __import__("re").findall(r"«(\w+)»", SLIDES)
if missing:
    raise SystemExit(f"slide placeholders without value: {missing}")
(ROOT / "presentacion.tex").write_text(SLIDES)
print("wrote presentacion.tex")
