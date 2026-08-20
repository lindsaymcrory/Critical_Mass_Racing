#!/usr/bin/env python3

# Copyright 2026 Lindsay McRory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Renders the Hull Analysis page (formerly Boat Check): season-wide
port/starboard tack symmetry and hull-drag (bottom fouling) trend. Reads
boat_setup_analysis.json (computed by boat_setup_analysis.py at build time)
and boat_setup_notes.md (hand-authored/edited directly, like
season_summary.md), so this page never needs a live database connection --
consistent with the app's READ_ONLY view-only deployment mode. The Boat
Setup Log table now lives on its own page (see render_rig_tune.py)."""
import json
import re
from pathlib import Path

from render_race_page import _coach_markdown_to_html

ROOT = Path(__file__).parent
ANALYSIS_PATH = ROOT / "boat_setup_analysis.json"
NOTES_PATH = ROOT / "boat_setup_notes.md"

PAGE_TEMPLATE = """<title>Hull Analysis — Critical Mass Racing</title>
<style>
  :root {
    --ink: #0a1a20; --panel: #122a32; --panel-2: #0e222a;
    --grid: #1f3e48; --grid-strong: #2a4e59; --paper: #e7ede9;
    --dim: #7fa3ab; --dim-2: #547881;
    --starboard: #3fbf7f; --port: #ef5a4c; --mark: #f5b942; --gybe: #5aa7e0;
    --hair: #24444f; --radius: 3px;
  }
  :root[data-theme="light"] {
    --ink: #eef3f1; --panel: #ffffff; --panel-2: #f4f8f7;
    --grid: #d7e2df; --grid-strong: #c3d3cf; --paper: #10262c;
    --dim: #4c6b71; --dim-2: #7d9ba1; --hair: #d2ddda;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; background: var(--ink); color: var(--paper);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .mono { font-family: ui-monospace, "SF Mono", "Cascadia Mono", "Roboto Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
  a { color: inherit; }
  a.back { text-decoration: none; color: var(--dim); font-size: 12px; }
  a.back:hover { color: var(--paper); }

  header {
    display: flex; align-items: center; gap: 22px; flex-wrap: wrap;
    padding: 16px 24px; border-bottom: 1px solid var(--hair); background: var(--panel-2);
    position: sticky; top: 0; z-index: 30;
  }
  .brand { display: flex; flex-direction: column; gap: 2px; }
  .brand .title { font-size: 19px; font-weight: 700; letter-spacing: 0.02em; }
  .brand .sub { font-size: 13px; color: var(--dim); }
  .intro { padding: 16px 24px 4px; font-size: 15px; color: var(--dim); max-width: 820px; }

  section { border-bottom: 1px solid var(--hair); padding-bottom: 8px; }
  .section-head { padding: 20px 24px 4px; }
  .section-title { font-size: 14.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }
  .section-sub { font-size: 14px; color: var(--dim); margin-top: 4px; }

  .chart-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px; padding: 12px 24px;
  }
  .chart-card {
    background: var(--panel-2); border: 1px solid var(--hair); border-radius: var(--radius);
    position: relative; height: 300px;
  }
  .chart-card svg { width: 100%; height: 100%; display: block; }
  .chart-card .card-title {
    position: absolute; top: 8px; left: 12px; font-size: 13px; font-weight: 700; color: var(--dim); z-index: 2;
  }
  .hull-chart-wrap {
    background: var(--panel-2); border: 1px solid var(--hair); border-radius: var(--radius);
    margin: 12px 24px; height: 380px; position: relative;
  }
  .hull-chart-wrap svg { width: 100%; height: 100%; display: block; }
  .chart-legend { display: flex; gap: 16px; flex-wrap: wrap; padding: 0 24px 8px; font-size: 13px; color: var(--dim); }
  .chart-legend .row { display: flex; align-items: center; gap: 6px; }
  .chart-legend .ln { width: 16px; height: 4px; border-radius: 2px; display: inline-block; }

  .tooltip {
    position: absolute; pointer-events: none; background: var(--panel);
    border: 1px solid var(--grid-strong); border-radius: var(--radius);
    padding: 8px 10px; font-size: 12.5px; line-height: 1.5; white-space: nowrap;
    box-shadow: 0 4px 16px rgba(0,0,0,0.35); opacity: 0; transition: opacity 0.08s; z-index: 20;
  }
  .tooltip.show { opacity: 1; }

  .note-box {
    margin: 4px 24px 20px; padding: 16px 20px;
    border: 1px solid var(--hair); border-radius: var(--radius);
    background: var(--panel); font-size: 14.5px; line-height: 1.6; max-width: 900px;
  }
  .note-box ul { margin: 4px 0; padding-left: 20px; }
  .note-box li { margin: 5px 0; }

  footer { padding: 12px 24px; background: var(--panel-2); font-size: 12px; color: var(--dim-2); }
  ::-webkit-scrollbar { width: 9px; height: 9px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--hair); border-radius: 5px; }
</style>

<header>
  <a class="back" href="/">&larr; All races</a>
  <div class="brand">
    <div class="title">Hull Analysis</div>
    <div class="sub">Speed &amp; Bottom</div>
  </div>
</header>

<p class="intro">Analyse boat performance for the season and uncover what may be holding it back.</p>

<section id="tack-section">
  <div class="section-head">
    <span class="section-title">Port vs. Starboard Performance</span>
    <div class="section-sub">Boat speed by sailing angle and wind range, port vs. starboard tack.</div>
  </div>
  <div class="chart-grid" id="polarGrid"></div>
  <div class="chart-legend">
    <span class="row"><span class="ln" style="border-top:3px dashed var(--port);height:0;width:16px"></span>port (dashed)</span>
    <span class="row"><span class="ln" style="background:var(--starboard)"></span>starboard (solid)</span>
  </div>
  <div class="section-head" style="padding-top:6px">
    <div class="section-sub">Starboard minus port speed, by angle &mdash; above zero favours starboard, below favours port.</div>
  </div>
  <div class="chart-grid" id="diffGrid"></div>
  <div class="note-box">__RIG_NOTES_HTML__</div>
</section>

<section id="hull-section" style="border-bottom: none">
  <div class="section-head">
    <span class="section-title">Hull Drag Analysis</span>
    <div class="section-sub">Detecting performance loss caused by bottom fouling.</div>
  </div>
  <div class="hull-chart-wrap">
    <svg id="hullChart" xmlns="http://www.w3.org/2000/svg"></svg>
    <div class="tooltip mono" id="hullTooltip"></div>
  </div>
  <div class="chart-legend" id="hullLegend"></div>
  <div class="note-box">__HULL_NOTES_HTML__</div>
</section>

<footer>Tack and hull-drag analysis: nav_1hz samples with boat speed &ge; 1.5 kn, computed once at build time.</footer>

<script id="boat-setup-analysis" type="application/json">__ANALYSIS_JSON__</script>
<script>
(function () {
  const svgNS = "http://www.w3.org/2000/svg";
  const ANALYSIS = JSON.parse(document.getElementById("boat-setup-analysis").textContent);

  function bandLabel(lo, hi) { return hi === null ? `${lo}+ kn` : `${lo}-${hi} kn`; }
  function bandKey(lo, hi) { return hi === null ? `${lo}+` : `${lo}-${hi}`; }

  function makeCard(parent, title) {
    const card = document.createElement("div");
    card.className = "chart-card";
    card.innerHTML = `<div class="card-title">${title}</div><svg xmlns="${svgNS}"></svg><div class="tooltip mono"></div>`;
    parent.appendChild(card);
    return card;
  }

  function toXY(angle, radius, side, originX, originY, scale) {
    const rad = angle * Math.PI / 180;
    return [originX + side * radius * Math.sin(rad) * scale, originY - radius * Math.cos(rad) * scale];
  }

  function pointTooltip(el, card, text) {
    const tooltip = card.querySelector(".tooltip");
    el.addEventListener("mouseenter", (ev) => {
      const wrapRect = card.getBoundingClientRect();
      tooltip.innerHTML = text;
      tooltip.classList.add("show");
      tooltip.style.left = (ev.clientX - wrapRect.left + 10) + "px";
      tooltip.style.top = (ev.clientY - wrapRect.top + 10) + "px";
    });
    el.addEventListener("mouseleave", () => tooltip.classList.remove("show"));
  }

  function drawPolarMini(card, portPts, stbdPts) {
    const svg = card.querySelector("svg");
    const rect = card.getBoundingClientRect();
    const W = Math.max(240, rect.width), H = Math.max(260, rect.height);
    const allSpeeds = [...portPts, ...stbdPts].map(p => p.avg_stw);
    const maxSpeed = (allSpeeds.length ? Math.max(...allSpeeds) : 1) * 1.15;
    const originX = W / 2, originY = H * 0.5;
    const usable = Math.min(W / 2, H * 0.46);
    const scale = usable / maxSpeed;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";

    const ringStep = maxSpeed > 8 ? 2 : 1;
    for (let r = ringStep; r <= maxSpeed; r += ringStep) {
      const [x0, y0] = toXY(0, r, -1, originX, originY, scale);
      const [x180, y180] = toXY(180, r, -1, originX, originY, scale);
      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", `M ${x0} ${y0} A ${r * scale} ${r * scale} 0 0 0 ${x180} ${y180}`);
      path.setAttribute("fill", "none"); path.setAttribute("stroke", "var(--grid)"); path.setAttribute("stroke-width", "1.5");
      svg.appendChild(path);
    }
    [20, 90, 180].forEach(a => {
      [-1, 1].forEach(side => {
        const [x, y] = toXY(a, maxSpeed, side, originX, originY, scale);
        const line = document.createElementNS(svgNS, "line");
        line.setAttribute("x1", originX); line.setAttribute("y1", originY);
        line.setAttribute("x2", x); line.setAttribute("y2", y);
        line.setAttribute("stroke", "var(--grid)"); line.setAttribute("stroke-width", "1.5");
        svg.appendChild(line);
      });
    });

    function drawSide(pts, side, color, dashed) {
      if (!pts.length) return;
      const sorted = [...pts].sort((a, b) => a.angle - b.angle);
      const d = sorted.map((p, i) => {
        const [x, y] = toXY(p.angle, p.avg_stw, side, originX, originY, scale);
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", d); path.setAttribute("fill", "none");
      path.setAttribute("stroke", color); path.setAttribute("stroke-width", "4");
      if (dashed) path.setAttribute("stroke-dasharray", "7,4");
      svg.appendChild(path);
      sorted.forEach(p => {
        const [x, y] = toXY(p.angle, p.avg_stw, side, originX, originY, scale);
        const c = document.createElementNS(svgNS, "circle");
        c.setAttribute("cx", x); c.setAttribute("cy", y); c.setAttribute("r", "3");
        c.setAttribute("fill", color);
        pointTooltip(c, card, `${p.angle}&deg; &middot; ${p.avg_stw.toFixed(2)} kn<br>n=${p.n}`);
        svg.appendChild(c);
      });
    }
    drawSide(portPts, -1, "var(--port)", true);
    drawSide(stbdPts, 1, "var(--starboard)", false);
  }

  function drawDiffMini(card, angles, portPts, stbdPts) {
    const svg = card.querySelector("svg");
    const rect = card.getBoundingClientRect();
    const W = Math.max(240, rect.width), H = Math.max(260, rect.height);
    const portByAngle = Object.fromEntries(portPts.map(p => [p.angle, p]));
    const stbdByAngle = Object.fromEntries(stbdPts.map(p => [p.angle, p]));
    const diffs = angles
      .filter(a => portByAngle[a] && stbdByAngle[a])
      .map(a => ({ angle: a, diff: stbdByAngle[a].avg_stw - portByAngle[a].avg_stw, n: portByAngle[a].n + stbdByAngle[a].n }));
    const maxAbs = diffs.length ? Math.max(0.2, ...diffs.map(d => Math.abs(d.diff))) * 1.2 : 1;
    const padL = 30, padR = 12, padT = 12, padB = 22;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const span = angles[angles.length - 1] - angles[0];
    const xScale = a => padL + ((a - angles[0]) / span) * plotW;
    const yScale = v => padT + plotH / 2 - (v / maxAbs) * (plotH / 2);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";

    const zero = document.createElementNS(svgNS, "line");
    zero.setAttribute("x1", padL); zero.setAttribute("x2", W - padR);
    zero.setAttribute("y1", yScale(0)); zero.setAttribute("y2", yScale(0));
    zero.setAttribute("stroke", "var(--grid-strong)"); zero.setAttribute("stroke-width", "2.5");
    svg.appendChild(zero);

    if (diffs.length > 1) {
      const d = diffs.map((p, i) => `${i === 0 ? "M" : "L"}${xScale(p.angle).toFixed(1)},${yScale(p.diff).toFixed(1)}`).join(" ");
      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", d); path.setAttribute("fill", "none");
      path.setAttribute("stroke", "var(--mark)"); path.setAttribute("stroke-width", "4");
      svg.appendChild(path);
    }
    diffs.forEach(p => {
      const c = document.createElementNS(svgNS, "circle");
      c.setAttribute("cx", xScale(p.angle)); c.setAttribute("cy", yScale(p.diff)); c.setAttribute("r", "3");
      c.setAttribute("fill", "var(--mark)");
      pointTooltip(c, card, `${p.angle}&deg; &middot; ${p.diff >= 0 ? "+" : ""}${p.diff.toFixed(2)} kn<br>n=${p.n}`);
      svg.appendChild(c);
    });
  }

  function buildTackCharts() {
    const grid = document.getElementById("polarGrid");
    const diffGrid = document.getElementById("diffGrid");
    grid.innerHTML = ""; diffGrid.innerHTML = "";
    ANALYSIS.wind_bands_tack.forEach(([lo, hi]) => {
      const label = bandLabel(lo, hi);
      const key = bandKey(lo, hi);
      const band = ANALYSIS.tack_performance[key] || { port: [], starboard: [] };
      drawPolarMini(makeCard(grid, label), band.port, band.starboard);
      drawDiffMini(makeCard(diffGrid, label), ANALYSIS.angle_buckets, band.port, band.starboard);
    });
  }

  const HULL_COLORS = { "0-8": "var(--gybe)", "8-12": "var(--starboard)", "12-20": "var(--mark)", "20+": "var(--port)" };

  function buildHullChart() {
    const svg = document.getElementById("hullChart");
    const tooltip = document.getElementById("hullTooltip");
    const wrap = svg.parentElement;
    const rect = wrap.getBoundingClientRect();
    const W = Math.max(360, rect.width), H = Math.max(320, rect.height);

    const dateSet = new Set();
    Object.values(ANALYSIS.hull_drag).forEach(entries => entries.forEach(e => dateSet.add(e.race_date)));
    const dates = [...dateSet].sort();
    svg.innerHTML = "";
    if (!dates.length) return;

    const allSpeeds = Object.values(ANALYSIS.hull_drag).flatMap(entries => entries.map(e => e.avg_stw));
    const maxSpeed = Math.max(...allSpeeds) * 1.15;
    const padL = 40, padR = 16, padT = 16, padB = 46;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const xScale = d => dates.length === 1 ? padL + plotW / 2 : padL + (dates.indexOf(d) / (dates.length - 1)) * plotW;
    const yScale = v => padT + plotH - (v / maxSpeed) * plotH;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

    for (let i = 0; i <= 4; i++) {
      const v = (maxSpeed / 4) * i;
      const y = yScale(v);
      const line = document.createElementNS(svgNS, "line");
      line.setAttribute("x1", padL); line.setAttribute("x2", W - padR);
      line.setAttribute("y1", y); line.setAttribute("y2", y);
      line.setAttribute("stroke", "var(--grid)"); line.setAttribute("stroke-width", "1.5");
      svg.appendChild(line);
      const label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", padL - 6); label.setAttribute("y", y + 3);
      label.setAttribute("fill", "var(--dim)"); label.setAttribute("font-size", "11.5"); label.setAttribute("text-anchor", "end");
      label.textContent = v.toFixed(1);
      svg.appendChild(label);
    }
    dates.forEach(d => {
      const x = xScale(d);
      const label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", x); label.setAttribute("y", H - padB + 16);
      label.setAttribute("fill", "var(--dim)"); label.setAttribute("font-size", "11.5"); label.setAttribute("text-anchor", "middle");
      label.setAttribute("transform", `rotate(-35 ${x} ${H - padB + 16})`);
      label.textContent = d;
      svg.appendChild(label);
    });

    const legendEl = document.getElementById("hullLegend");
    legendEl.innerHTML = "";
    Object.entries(ANALYSIS.hull_drag).forEach(([band, entries]) => {
      const color = HULL_COLORS[band] || "var(--dim)";
      const sorted = [...entries].sort((a, b) => a.race_date.localeCompare(b.race_date));
      if (sorted.length > 1) {
        const d = sorted.map((e, i) => `${i === 0 ? "M" : "L"}${xScale(e.race_date).toFixed(1)},${yScale(e.avg_stw).toFixed(1)}`).join(" ");
        const path = document.createElementNS(svgNS, "path");
        path.setAttribute("d", d); path.setAttribute("fill", "none");
        path.setAttribute("stroke", color); path.setAttribute("stroke-width", "4");
        svg.appendChild(path);
      }
      sorted.forEach(e => {
        const c = document.createElementNS(svgNS, "circle");
        c.setAttribute("cx", xScale(e.race_date)); c.setAttribute("cy", yScale(e.avg_stw)); c.setAttribute("r", "3.2");
        c.setAttribute("fill", color);
        c.addEventListener("mouseenter", (ev) => {
          const wrapRect = wrap.getBoundingClientRect();
          tooltip.innerHTML = `<strong>${band} kn</strong><br>${e.race_date} &middot; ${e.avg_stw.toFixed(2)} kn<br>n=${e.n}`;
          tooltip.classList.add("show");
          tooltip.style.left = (ev.clientX - wrapRect.left + 10) + "px";
          tooltip.style.top = (ev.clientY - wrapRect.top + 10) + "px";
        });
        c.addEventListener("mouseleave", () => tooltip.classList.remove("show"));
        svg.appendChild(c);
      });
      const row = document.createElement("span");
      row.className = "row";
      row.innerHTML = `<span class="ln" style="background:${color}"></span>${band} kn TWS`;
      legendEl.appendChild(row);
    });
  }

  buildTackCharts();
  buildHullChart();
  window.addEventListener("resize", () => { buildTackCharts(); buildHullChart(); });
})();
</script>
"""


def _split_notes(text):
    """Splits boat_setup_notes.md on its top-level '## ' headers, stripping
    each header line (the page already shows its own section titles)."""
    if not text.strip():
        return "", ""
    parts = re.split(r"\n(?=## )", text.strip())
    stripped = ["\n".join(p.split("\n")[1:]).strip() for p in parts]
    rig = stripped[0] if len(stripped) > 0 else ""
    hull = stripped[1] if len(stripped) > 1 else ""
    return rig, hull


def render_page():
    analysis = json.loads(ANALYSIS_PATH.read_text()) if ANALYSIS_PATH.exists() else {
        "wind_bands_tack": [], "wind_bands_hull": [], "angle_buckets": [],
        "tack_performance": {}, "hull_drag": {},
    }
    notes_text = NOTES_PATH.read_text() if NOTES_PATH.exists() else ""
    rig_notes, hull_notes = _split_notes(notes_text)
    rig_html = _coach_markdown_to_html(rig_notes) if rig_notes else "<p><em>No notes yet.</em></p>"
    hull_html = _coach_markdown_to_html(hull_notes) if hull_notes else "<p><em>No notes yet.</em></p>"

    return (PAGE_TEMPLATE
            .replace("__ANALYSIS_JSON__", json.dumps(analysis))
            .replace("__RIG_NOTES_HTML__", rig_html)
            .replace("__HULL_NOTES_HTML__", hull_html))


if __name__ == "__main__":
    print(render_page()[:2000])
