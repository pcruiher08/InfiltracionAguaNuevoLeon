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
    <div id="op-out"></div>`;
  const ha = panel.querySelector("#op-ha"), hv = panel.querySelector("#op-hv"), out = panel.querySelector("#op-out");
  ha.oninput = () => hv.textContent = `${fmt(ha.value)} ha`;
  panel.querySelectorAll("input[name=op-mode]").forEach(r => r.onchange = () => mode = r.value);

  panel.querySelector("#op-run").onclick = async ev => {
    const btn = ev.target; btn.disabled = true; btn.textContent = "Optimizando…";
    try {
      const r = await post("/api/optimize", { budget_ha:+ha.value, mode });
      draw(r); summarize(r);
    } catch (e) { out.innerHTML = `<div class="muted">Error: ${String(e.message).slice(0, 160)}</div>`; }
    finally { btn.disabled = false; btn.textContent = "Optimizar"; }
  };

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
    const curve = r.curve.map(c => `${fmt(c.ha)} ha → ${(c.m3 / 1e6).toFixed(1)} M m³`).join(" · ");
    out.innerHTML = `
      <div style="font-size:15px;font-weight:600;margin-top:10px">~${(t.m3_per_year / 1e6).toFixed(1)} millones de m³/año retenidos</div>
      <div class="muted">${t.cells} celdas de 1 km · ${fmt(t.ha)} ha de ${fmt(t.eligible_ha_total)} ha elegibles</div>
      ${rows}
      <div class="muted" style="margin-top:6px"><b>Rendimientos decrecientes (máxima agua):</b> ${curve}</div>
      <div class="muted" style="margin-top:6px">Haz clic en una celda para ver su ficha y optimizar sus barreras.</div>
      <details><summary>Supuestos</summary><ul class="muted">${r.assumptions.map(a => `<li>${a}</li>`).join("")}</ul></details>`;
  }
})();
