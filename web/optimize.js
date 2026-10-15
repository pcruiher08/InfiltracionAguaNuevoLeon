// Supply optimization panel: where to restore to maximize water delivered to each source.
(() => {
  const { map, post } = window.app;
  const COLORS = { "Presa La Boca":"#2a78d6", "Acuífero Santa Catarina (pozos SADM)":"#eb6834",
                   "Presa Cerro Prieto":"#1baf7a", "Presa El Cuchillo":"#eda100" };
  const fmt = n => Math.round(n).toLocaleString("es-MX");
  const panel = document.getElementById("optimize-panel");
  let group = null, mode = "max";
  panel.innerHTML = `
    <h2>Optimizar captación para las presas</h2>
    <div class="muted">Elige dónde restaurar para maximizar el agua retenida que llega a cada fuente de abasto.</div>
    <label class="w">Hectáreas a restaurar <span id="op-hv">3,000 ha</span></label>
    <input type="range" id="op-ha" min="500" max="20000" step="500" value="3000">
    <div class="seg" style="margin-top:6px">
      <label><input type="radio" name="op-mode" value="max" checked><span>Máxima agua total</span></label>
      <label><input type="radio" name="op-mode" value="balanced"><span>Repartir entre presas</span></label>
    </div>
    <button id="op-run">Optimizar</button>
    <div class="row" style="gap:6px;margin-top:10px">
      <span class="muted">¿Cuánto hay que restaurar para</span>
      <input id="op-ls" type="number" min="10" max="3000" step="10" value="500"
        style="width:70px;padding:4px 6px;font:inherit;color:var(--fg);background:transparent;border:1px solid var(--line);border-radius:6px">
      <span class="muted">L/s?</span>
    </div>
    <button id="op-target" style="margin-top:4px">Calcular hectáreas</button>
    <div id="op-out"></div>`;
  const ha = panel.querySelector("#op-ha"), hv = panel.querySelector("#op-hv"), out = panel.querySelector("#op-out");
  ha.oninput = () => hv.textContent = `${fmt(ha.value)} ha`;
  panel.querySelectorAll("input[name=op-mode]").forEach(r => r.onchange = () => mode = r.value);

  async function run(btn, body, label) {
    btn.disabled = true; const old = btn.textContent; btn.textContent = label;
    try {
      const r = await post("/api/optimize", body);
      if (r.target) { ha.value = Math.min(20000, r.budget_ha); hv.textContent = `${fmt(r.budget_ha)} ha`; }
      draw(r); summarize(r);
    } catch (e) { out.innerHTML = `<div class="muted">Error: ${String(e.message).slice(0, 160)}</div>`; }
    finally { btn.disabled = false; btn.textContent = old; }
  }
  panel.querySelector("#op-run").onclick = ev => run(ev.target, { budget_ha:+ha.value, mode }, "Optimizando…");
  panel.querySelector("#op-target").onclick = ev =>
    run(ev.target, { target_ls:+panel.querySelector("#op-ls").value, mode:"max" }, "Calculando…");

  function draw(r) {
    if (group) map.removeLayer(group);
    group = L.geoJSON(r.cells, {
      style: f => ({ color:"#ffffff", weight:1, fillColor:COLORS[f.properties.supply_name] || "#6b675f", fillOpacity:.7 }),
      onEachFeature: (f, l) => {
        const p = f.properties;
        l.bindTooltip(`#${p.rank} · ${p.supply_name}<br>${fmt(p.treated_ha)} ha · ~${fmt(p.delivered_m3)} m³/año<br>lluvia ${p.rain_mm} mm · C ${p.c}`);
        l.on("click", ev => { L.DomEvent.stopPropagation(ev); map.fire("click", { latlng:L.latLng(p.lat, p.lon) }); });
      },
    }).addTo(map);
    const op = document.getElementById("opacity");
    if (op && +op.value > 0.3) { op.value = 0.3; op.dispatchEvent(new Event("input")); }
    map.fitBounds(group.getBounds(), { padding:[20, 20] });
  }

  function summarize(r) {
    const t = r.totals;
    const rows = Object.entries(r.by_supply).sort((a, b) => b[1].m3 - a[1].m3).map(([k, v]) =>
      `<div class="stat"><span><span class="sw" style="background:${COLORS[k]}"></span>${k}</span><b>${fmt(v.ha)} ha · ${(v.m3 / 1e6).toFixed(2)} M m³</b></div>`).join("");
    const curve = r.curve.map(c => `${fmt(c.ha)} ha → ${fmt(c.ls)} L/s`).join(" · ");
    const im = r.impact, d = r.drought, tg = r.target;
    const targetLine = tg ? `<div style="margin-top:10px;padding:8px;border-radius:6px;background:color-mix(in srgb, var(--accent) 12%, transparent)">
        Para <b>+${fmt(tg.target_ls)} L/s</b> hay que restaurar <b>~${fmt(tg.ha)} ha</b> en las mejores celdas${tg.reachable ? "" : ` (máximo alcanzable: ${fmt(tg.max_ls)} L/s)`}.</div>` : "";
    out.innerHTML = `${targetLine}
      <div style="font-size:22px;font-weight:700;margin-top:10px">+${fmt(im.ls)} L/s</div>
      <div style="font-size:13px">≈ <b>${im.days_of_zmm_supply} días de abasto</b> de la ZMM al año · ${im.pct_zmm_demand}% de los ${fmt(im.zmm_demand_ls)} L/s de consumo</div>
      <div class="muted">~${(t.m3_per_year / 1e6).toFixed(1)} millones de m³/año retenidos · ${t.cells} celdas de 1 km · ${fmt(t.ha)} ha de ${fmt(t.eligible_ha_total)} ha elegibles</div>
      <div style="margin-top:10px;padding:8px;border:1px solid var(--line);border-radius:6px">
        <b>Prueba de sequía</b> <span class="muted">· lluvia real de ${d.period}</span>
        <div class="stat"><span>Agua que aún se capta</span><b>+${fmt(d.ls)} L/s (${d.pct_of_normal}% de un año normal)</b></div>
        <div class="stat"><span>Sitios que se mantienen si se optimiza con la lluvia de sequía</span><b>${d.selection_overlap_pct}%</b></div>
        <div class="muted" style="margin-top:4px">${d.selection_overlap_pct >= 70 ? "La selección es estable: los mismos sitios siguen siendo los mejores en un año seco." : "La selección cambia en sequía: conviene priorizar los sitios que aparecen en ambos escenarios."}</div>
      </div>
      ${rows}
      <div class="muted" style="margin-top:6px"><b>Rendimientos decrecientes (máxima agua):</b> ${curve}</div>
      <div class="muted" style="margin-top:6px">Haz clic en una celda para ver su ficha y optimizar sus barreras.</div>
      <details><summary>Supuestos</summary><ul class="muted">${r.assumptions.map(a => `<li>${a}</li>`).join("")}</ul></details>`;
  }
})();
