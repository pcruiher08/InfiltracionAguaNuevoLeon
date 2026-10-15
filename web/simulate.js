// Storm runoff simulation: animates water flowing downslope without vs with the barriers.
(() => {
  const { map, post } = window.app;
  const panel = document.getElementById("sim-panel");
  const SKIP = /^fuera de alcance/i;  // urban, water or flat: nothing to simulate
  const fmt = n => Math.round(n).toLocaleString("es-MX");
  let site = null, sim = null, overlay = null, frame = 0, timer = null, scen = "without";
  const canvas = document.createElement("canvas");

  app.onSite(s => {
    stop(); site = s; sim = null;
    if (overlay) { map.removeLayer(overlay); overlay = null; }
    const obra = (s.recommendation && s.recommendation.obra) || "";
    panel.innerHTML = !SKIP.test(obra) ? `
      <div style="border:1px solid var(--line);border-radius:8px;padding:10px;margin-top:10px">
        <b>Simulación de tormenta</b>
        <div class="muted">Tormenta de 40 mm: el agua baja por la ladera sin barreras y con las barreras optimizadas.</div>
        <button id="sim-run">Simular escurrimiento</button>
        <div id="sim-out"></div></div>` : "";
    const b = panel.querySelector("#sim-run");
    if (b) {
      b.onclick = run;
      setTimeout(() => panel.scrollIntoView({ behavior: "smooth", block: "center" }), 300);
      if (autoRun) { autoRun = false; b.click(); }
    }
  });

  // One-click demo: known Pilón slope site, runs the simulation automatically
  let autoRun = false;
  const demo = document.getElementById("sim-demo");
  if (demo) demo.onclick = () => {
    autoRun = true;
    map.setView([25.0, -100.05], 14);
    map.fire("click", { latlng: L.latLng(25.0, -100.05) });
  };

  async function run(ev) {
    const btn = ev.target; btn.disabled = true; btn.textContent = "Simulando…";
    // make sure the barriers are drawn for the same budget
    const bp = document.getElementById("bp-run");
    if (bp && !document.querySelector("#bp-out .bp-dl")) bp.click();
    if (!bp) app.setStatus("Simulando con barreras optimizadas para este sitio…");
    const budget = +(document.getElementById("bp-budget") || { value: 1500 }).value;
    try {
      sim = await post("/api/simulate", { lon: site.lon, lat: site.lat, budget_m: budget });
      const dec = b64 => { const bin = atob(b64), u = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u; };
      sim.without.u8 = dec(sim.without.frames);
      sim.with.u8 = dec(sim.with.frames);
      sim.with.pond = dec(sim.with.ponded);
      sim.difference.red = dec(sim.difference.reduction);
      sim.difference.flux = dec(sim.difference.flux_without);
      canvas.width = sim.grid.cols; canvas.height = sim.grid.rows;
      // hide the blue priority layer so the water reads clearly
      const op = document.getElementById("opacity");
      if (op && +op.value > 0.05) { op.value = 0.05; op.dispatchEvent(new Event("input")); }
      renderPanel(); scen = "without"; frame = 0; draw(); play();
    } catch (e) {
      panel.querySelector("#sim-out").innerHTML = `<div class="muted">Error: ${String(e.message).slice(0, 160)}</div>`;
    } finally { btn.disabled = false; btn.textContent = "Simular de nuevo"; }
  }

  function renderPanel() {
    const s = sim.summary, a = sim.without.totals, b = sim.with.totals;
    const kv = (k, x, y) => `<div class="stat"><span>${k}</span><b>${x}</b><b>${y}</b></div>`;
    panel.querySelector("#sim-out").innerHTML = `
      <div class="seg" style="margin-top:8px">
        <label><input type="radio" name="sim-s" value="without" checked><span>Sin barreras</span></label>
        <label><input type="radio" name="sim-s" value="with"><span>Con barreras</span></label>
        <label><input type="radio" name="sim-s" value="diff"><span>Diferencia</span></label>
      </div>
      <div id="sim-key" class="muted"></div>
      <div class="row" style="gap:6px;margin:6px 0">
        <button id="sim-play" style="margin:0">⏸</button>
        <input type="range" id="sim-t" min="0" max="${sim.grid.frames - 1}" value="0" style="flex:1">
        <span id="sim-tl" class="muted" style="width:44px;text-align:right"></span>
      </div>
      <svg id="sim-chart" viewBox="0 0 300 90" style="width:100%;height:90px"></svg>
      <div class="muted"><span style="color:#9c9890">━</span> sin barreras &nbsp; <span style="color:#1c5cab">━</span> con barreras · agua que sale de la ventana</div>
      <div style="font-size:15px;font-weight:600;margin-top:8px">−${s.outflow_reduction_pct}% escurrimiento · −${s.peak_reduction_pct}% pico</div>
      <div class="muted">+${fmt(s.extra_infiltration_m3)} m³ infiltrados en esta tormenta (${s.n_barriers} barreras, ${s.n_dams} presas en cárcavas)</div>
      <div class="stat" style="margin-top:6px"><span></span><b>Sin</b><b>Con</b></div>
      ${kv("Sale de la ventana", fmt(a.outflow) + " m³", fmt(b.outflow) + " m³")}
      ${kv("Infiltra en ladera", fmt(a.infiltrated_hill) + " m³", fmt(b.infiltrated_hill) + " m³")}
      ${kv("Infiltra tras obras", "—", fmt(b.infiltrated_works) + " m³")}
      <details><summary>Cómo funciona</summary><ul class="muted">${sim.notes.map(n => `<li>${n}</li>`).join("")}
        <li>El agua que sale puede superar la lluvia sobre la ventana porque también entra escurrimiento desde ladera arriba.</li></ul></details>`;
    panel.querySelectorAll("input[name=sim-s]").forEach(r => r.onchange = () => { scen = r.value; draw(); });
    panel.querySelector("#sim-play").onclick = () => timer ? stop() : play();
    panel.querySelector("#sim-t").oninput = e => { stop(); frame = +e.target.value; draw(); };
    chart();
  }

  function chart() {
    const svg = panel.querySelector("#sim-chart");
    const a = sim.without.outflow, b = sim.with.outflow, n = a.length, mx = Math.max(...a, ...b);
    const path = s => s.map((v, i) => `${i ? "L" : "M"}${(i / (n - 1) * 296 + 2).toFixed(1)},${(86 - v / mx * 80).toFixed(1)}`).join("");
    svg.innerHTML = `<line x1="2" y1="86" x2="298" y2="86" stroke="var(--line)"/>
      <path d="${path(a)}" fill="none" stroke="#9c9890" stroke-width="2"/>
      <path d="${path(b)}" fill="none" stroke="#1c5cab" stroke-width="2"/>
      <line id="sim-cur" x1="2" y1="4" x2="2" y2="86" stroke="var(--fg)" stroke-width="1" stroke-dasharray="3 3"/>`;
  }

  const KEYS = {
    without: `<span style="color:#1c5cab">■</span> agua escurriendo (más oscuro = más agua)`,
    with: `<span style="color:#1c5cab">■</span> agua escurriendo &nbsp; <span style="color:#00b3a4">■</span> agua retenida por barreras y presas`,
    diff: `<span style="color:#d95926">■</span> cuánto bajó el flujo total de la tormenta con barreras (más intenso = más reducción); <span style="color:#9c9890">■</span> sin cambio`,
  };
  function px(d, i, r, g, b, a) { d[i * 4] = r; d[i * 4 + 1] = g; d[i * 4 + 2] = b; d[i * 4 + 3] = a; }

  function draw() {
    const { rows, cols } = sim.grid, N = rows * cols, off = frame * N;
    const ctx = canvas.getContext("2d"), img = ctx.createImageData(cols, rows), d = img.data;
    panel.querySelector("#sim-key").innerHTML = KEYS[scen];
    for (let i = 0; i < N; i++) {
      if (scen === "diff") {
        const f = sim.difference.flux[i], red = sim.difference.red[i] / 255;
        if (f < 10) { d[i * 4 + 3] = 0; continue; }
        if (red < 0.05) px(d, i, 156, 152, 144, 110);                      // flowed, no change
        else px(d, i, 240 - 70 * red, 150 - 90 * red, 106 - 90 * red, 120 + 135 * red); // orange: reduced
        continue;
      }
      const v = sim[scen].u8[off + i];
      const pond = scen === "with" ? sim.with.pond[off + i] : 0;
      if (pond > 10) { px(d, i, 0, 179, 164, 140 + pond * 0.45); continue; } // ponded behind works
      if (v < 6) { d[i * 4 + 3] = 0; continue; }
      const t = v / 255;  // light → deep blue
      px(d, i, Math.round(170 - 160 * t), Math.round(215 - 150 * t), Math.round(255 - 80 * t), Math.round(90 + 165 * t));
    }
    ctx.putImageData(img, 0, 0);
    const url = canvas.toDataURL();
    if (!overlay) overlay = L.imageOverlay(url, sim.grid.bounds, { opacity: .95, className: "sim-pix" }).addTo(map);
    else overlay.setUrl(url);
    const step = frame * sim.params.frame_every;
    panel.querySelector("#sim-t").value = frame;
    panel.querySelector("#sim-tl").textContent = `t ${step}`;
    const cur = panel.querySelector("#sim-cur");
    if (cur) { const x = (step / (sim.without.outflow.length - 1) * 296 + 2).toFixed(1); cur.setAttribute("x1", x); cur.setAttribute("x2", x); }
  }

  function play() {
    stop(); const b = panel.querySelector("#sim-play"); if (b) b.textContent = "⏸";
    timer = setInterval(() => { frame = (frame + 1) % sim.grid.frames; draw(); }, 120);
  }
  function stop() {
    if (timer) clearInterval(timer); timer = null;
    const b = panel.querySelector("#sim-play"); if (b) b.textContent = "▶";
  }
})();
