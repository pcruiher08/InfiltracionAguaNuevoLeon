// barriers panel — owned by the barriers workstream. Uses window.app (see index.html).
(() => {
  const app = window.app;
  const panel = document.getElementById("barriers-panel");
  if (!app || !panel) return;

  const PRESETS = [500, 1500, 3000];
  const DARK = "#1d1b18", DAM = "#8f3510", DRAIN = "#7b9bbd";
  let group = null, last = null, site = null;

  const style = document.createElement("style");
  style.textContent = `
    #barriers-panel { margin-top:10px; }
    #barriers-panel:empty { display:none; }
    #barriers-panel .bp-box { border:1px solid var(--line); border-radius:8px; padding:10px; }
    #barriers-panel .bp-title { font-weight:600; margin-bottom:4px; color:var(--fg); }
    #barriers-panel .bp-presets { display:flex; gap:6px; margin:6px 0; }
    #barriers-panel .bp-presets button { flex:1; margin:0; padding:4px 6px; font-size:12px;
      background:transparent; color:var(--fg); border:1px solid var(--line); }
    #barriers-panel .bp-presets button.on { border-color:var(--accent); color:var(--accent); font-weight:600; }
    #barriers-panel .bp-budget { display:flex; align-items:center; gap:6px; font-size:13px; color:var(--fg); }
    #barriers-panel .bp-budget input { width:90px; padding:4px 6px; font:inherit; color:var(--fg);
      background:transparent; border:1px solid var(--line); border-radius:6px; }
    #barriers-panel .bp-sum { margin-top:8px; color:var(--fg); }
    #barriers-panel .bp-note { margin-top:6px; }
    #barriers-panel ul { margin:6px 0 0; padding-left:18px; }
    #barriers-panel .bp-dl { background:transparent; color:var(--accent); border:1px solid var(--accent); }
    .bp-legend { display:flex; flex-direction:column; gap:3px; margin-top:6px; font-size:12px; color:var(--muted); }
    .bp-legend i { display:inline-block; width:18px; vertical-align:middle; margin-right:6px; }
  `;
  document.head.appendChild(style);

  const isBarrierWork = obra => obra && /barrera|zanja/i.test(obra) &&
    !/^(fuera de alcance|no intervenir|conservaci)/i.test(obra);

  function clear() {
    if (group) { app.map.removeLayer(group); group = null; }
    last = null;
  }

  function renderForm() {
    const budget = app.state.barrierBudget || 1500;
    panel.innerHTML = `<div class="bp-box">
      <div class="bp-title">Ubicación de barreras</div>
      <div class="muted">Traza en una ventana de ~1.2 km dónde construir para interceptar más escurrimiento.</div>
      <div class="bp-presets">${PRESETS.map(p =>
        `<button type="button" data-p="${p}" class="${p === budget ? "on" : ""}">${app.fmt(p)} m</button>`).join("")}</div>
      <label class="bp-budget">Presupuesto <input id="bp-budget" type="number" min="50" max="20000" step="50" value="${budget}"> m lineales</label>
      <button id="bp-run" type="button">Optimizar ubicación de barreras</button>
      <div id="bp-out"></div></div>`;
    const input = panel.querySelector("#bp-budget");
    panel.querySelectorAll(".bp-presets button").forEach(b => b.onclick = () => {
      input.value = b.dataset.p; syncPresets();
    });
    input.oninput = syncPresets;
    panel.querySelector("#bp-run").onclick = run;
  }

  function syncPresets() {
    const v = +panel.querySelector("#bp-budget").value;
    panel.querySelectorAll(".bp-presets button").forEach(b => b.classList.toggle("on", +b.dataset.p === v));
  }

  async function run() {
    const btn = panel.querySelector("#bp-run"), out = panel.querySelector("#bp-out");
    const budget = Math.max(50, +panel.querySelector("#bp-budget").value || 1500);
    app.state.barrierBudget = budget;
    const s = site;
    btn.disabled = true; out.innerHTML = `<div class="muted bp-note">Calculando flujo y curvas de nivel…</div>`;
    app.setStatus("Optimizando barreras…");
    try {
      const r = await app.post("/api/barriers", { lon:s.lon, lat:s.lat, budget_m:budget });
      if (s !== site) return;  // a newer site was clicked meanwhile
      clear(); last = r; draw(r); summarize(r, out);
    } catch (e) {
      out.innerHTML = `<div class="muted bp-note">Error: ${String(e.message).slice(0, 160)}</div>`;
    } finally { btn.disabled = false; app.setStatus(""); }
  }

  function draw(r) {
    group = L.layerGroup().addTo(app.map);
    const win = L.geoJSON(r.window, { style:{ color:DARK, weight:1.5, dashArray:"6 5", fill:false }, interactive:false });
    win.addTo(group);
    L.geoJSON(r.drainage, { interactive:false,
      style:f => ({ color:DRAIN, opacity:.85, weight: f.properties.acc_ha >= 20 ? 2.2 : f.properties.acc_ha >= 5 ? 1.6 : 1 }) }).addTo(group);
    L.geoJSON(r.selected, {
      filter:f => f.properties.type === "curva de nivel", bubblingMouseEvents:false,
      style:{ color:DARK, weight:4, opacity:.95, lineCap:"round" },
      onEachFeature:(f, l) => l.bindTooltip(
        `#${f.properties.rank} · barrera en curva de nivel<br>${f.properties.length_m} m · cota ${f.properties.elev_m} m<br>` +
        `intercepta ~${f.properties.value_ha} ha ladera arriba (nuevo)`, { sticky:true }),
    }).addTo(group);
    L.geoJSON(r.selected, {
      filter:f => f.properties.type === "cárcava",
      pointToLayer:(f, ll) => L.circleMarker(ll, { bubblingMouseEvents:false, radius:4, color:"#ffffff", weight:1, fillColor:DAM, fillOpacity:1 }),
      onEachFeature:(f, l) => l.bindTooltip(
        `Presa de piedra / gaviones en cárcava<br>aporte ${f.properties.upslope_ha} ha · cota ${f.properties.elev_m} m`),
    }).addTo(group);
    app.map.fitBounds(win.getBounds(), { padding:[20, 20] });
    // Fade the priority layer so barriers and drainage read clearly on top
    const op = document.getElementById("opacity");
    if (op && +op.value > 0.3) { op.value = 0.3; op.dispatchEvent(new Event("input")); }
  }

  function summarize(r, out) {
    const t = r.totals, p = r.params;
    out.innerHTML = `
      <div class="bp-sum"><b>${t.n_barriers} barreras · ${app.fmt(Math.round(t.length_m))} m · intercepta ~${Math.round(t.intercepted_pct)}% del escurrimiento de la ventana (relativo)</b></div>
      <div class="muted">${t.n_check_dams} presas en cárcavas${t.n_check_dams_total > t.n_check_dams ? ` (de ${t.n_check_dams_total} cruces detectados)` : ""} ·
        pendiente media ${p.mean_slope_deg}° · curvas cada ${p.vertical_interval_m} m de desnivel ·
        espaciamiento de campo ~${p.nominal_spacing_m} m (IV 1 m)</div>
      <div class="bp-legend">
        <span><i style="border-top:4px solid ${DARK}"></i>Barrera en curva de nivel (número = prioridad)</span>
        <span><i style="height:9px;width:9px;border-radius:50%;background:${DAM};margin-left:4px;margin-right:11px"></i>Presa en cárcava</span>
        <span><i style="border-top:2px solid ${DRAIN}"></i>Escurrimiento concentrado (DEM 30 m)</span>
        <span><i style="border-top:2px dashed ${DARK}"></i>Ventana de análisis</span>
      </div>
      <div class="muted bp-note">Trazo preliminar con DEM de 30 m — validar en campo con levantamiento topográfico o dron.</div>
      <details><summary>Supuestos del cálculo</summary><ul class="muted">${r.notes.slice(1).map(n => `<li>${n}</li>`).join("")}</ul></details>
      <button id="bp-dl" class="bp-dl" type="button">Descargar barreras (GeoJSON)</button>`;
    out.querySelector("#bp-dl").onclick = download;
  }

  function download() {
    if (!last || !site) return;
    const fc = { ...last.selected, properties:{ params:last.params, totals:last.totals, notes:last.notes } };
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(fc)], { type:"application/geo+json" }));
    a.download = `barreras_${site.lat.toFixed(4)}_${site.lon.toFixed(4)}.geojson`; a.click();
  }

  app.onSite(s => {
    clear(); site = s;
    if (isBarrierWork(s.recommendation && s.recommendation.obra)) renderForm();
    else panel.innerHTML = "";
  });
})();
