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

"""Renders the Hull Analysis page (formerly Boat Check): a reverse-
chronological port/starboard performance heatmap (most recent race on the
left) and the season-wide hull-drag (bottom fouling) trend. Reads
boat_setup_analysis.json (computed by boat_setup_analysis.py at build time,
using hull_performance.py's aggregation) and boat_setup_notes.md
(hand-authored/edited directly, like season_summary.md), so this page never
needs a live database connection -- consistent with the app's READ_ONLY
view-only deployment mode. The Boat Setup Log table now lives on its own
page (see render_rig_tune.py)."""
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
  .sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
  }

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

  .heatmap-controls {
    display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-end;
    padding: 10px 24px; font-size: 12.5px; color: var(--dim);
  }
  .control-group { display: flex; flex-direction: column; gap: 5px; }
  .control-group.disabled { opacity: 0.4; pointer-events: none; }
  .control-group select {
    background: var(--panel-2); color: var(--paper); border: 1px solid var(--hair);
    border-radius: var(--radius); padding: 5px 8px; font-size: 13px;
  }
  .filter-title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--dim-2); }
  .filter-chip {
    display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px;
    margin-right: 12px; cursor: pointer; user-select: none; white-space: nowrap;
  }
  .heatmap-frame {
    display: flex; margin: 6px 24px 0; border: 1px solid var(--hair);
    border-radius: var(--radius); overflow: hidden;
  }
  .heatmap-row-labels {
    flex: 0 0 auto; width: 168px; background: var(--panel-2); border-right: 1px solid var(--hair);
  }
  .heatmap-row-label {
    display: flex; flex-direction: column; justify-content: center; padding: 0 10px;
    font-size: 11.5px; color: var(--dim); line-height: 1.2; box-sizing: border-box;
  }
  .heatmap-row-label.group-start { border-top: 1px solid var(--hair); }
  .heatmap-row-label .wind-part { font-weight: 700; color: var(--paper); font-size: 11.5px; display: block; }
  .heatmap-row-label .tack-angle-part { color: var(--dim); }
  .heatmap-scroll {
    flex: 1; min-width: 0; overflow-x: auto; overflow-y: hidden; background: var(--panel-2);
  }
  .heatmap-scroll svg { display: block; }
  .heatmap-scroll rect:focus-visible { outline: 2px solid var(--paper); outline-offset: -2px; }
  .heatmap-legend { display: flex; gap: 18px; flex-wrap: wrap; align-items: center; padding: 12px 24px; font-size: 12.5px; color: var(--dim); }
  .heatmap-legend .row { display: flex; align-items: center; gap: 6px; }
  .heatmap-legend .swatch { width: 16px; height: 12px; border-radius: 2px; display: inline-block; }
  .heatmap-legend .swatch.hatch {
    background-color: var(--panel-2);
    background-image: radial-gradient(var(--hair) 1.1px, transparent 1.2px);
    background-size: 7px 7px;
    border: 1px solid var(--hair);
  }
  .heatmap-tooltip {
    position: fixed; pointer-events: none; background: var(--panel);
    border: 1px solid var(--grid-strong); border-radius: var(--radius);
    padding: 8px 10px; font-size: 12.5px; line-height: 1.55; max-width: 260px; white-space: normal;
    box-shadow: 0 4px 16px rgba(0,0,0,0.35); opacity: 0; transition: opacity 0.08s; z-index: 40;
  }
  .heatmap-tooltip.show { opacity: 1; }

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
    <div class="section-sub">Boat speed vs. polar target by wind range, tack, and sailing angle &mdash; most recent race on the left.</div>
  </div>
  <p class="sr-only" id="heatmapDescription">A heatmap of Critical Mass's boat speed against its polar target, broken
    down by wind-speed range (0-6, 6-12, 12-20, and 20-plus knots), tack (port or starboard), and sailing-angle band
    (upwind, reach, downwind). Columns are races, ordered with the most recent race on the left and the start of the
    season on the right. Cell colour shows performance percentage versus target: coral red for well below target,
    a neutral tone at target, and green for above target. Cells with no logged data, or too few samples for a
    reliable reading, are shown with a diagonal hatch pattern rather than a colour, so they are never mistaken for a
    measured zero. Vertical dashed lines mark logged rig-tune, sail-change, hull-cleaning, repair, and crew-change
    events at the point in the season they occurred. Every cell's exact values are available as text in its
    hover or keyboard-focus tooltip, and the view can be switched between percentage-vs-target, actual speed, and
    starboard-minus-port difference, with wind range, tack, and angle band each independently show/hideable.</p>
  <div class="heatmap-controls">
    <div class="control-group">
      <label class="filter-title" for="heatmapMode">View</label>
      <select id="heatmapMode">
        <option value="percent">% vs. target</option>
        <option value="speed">Actual speed (kn)</option>
        <option value="diff">Starboard &minus; port (kn)</option>
      </select>
    </div>
    <div class="control-group" id="windFilterGroup"></div>
    <div class="control-group" id="tackFilterGroup"></div>
    <div class="control-group" id="angleFilterGroup"></div>
  </div>
  <div class="heatmap-frame">
    <div class="heatmap-row-labels" id="heatmapRowLabels"></div>
    <div class="heatmap-scroll" id="heatmapScroll">
      <svg id="heatmapSvg" xmlns="http://www.w3.org/2000/svg" role="img" aria-describedby="heatmapDescription"></svg>
    </div>
  </div>
  <div class="heatmap-legend" id="heatmapLegend"></div>
  <div class="heatmap-tooltip mono" id="heatmapTooltip" role="tooltip"></div>
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

<footer>Tack and hull-drag analysis: nav_1hz/polar_performance samples, computed once at build time.</footer>

<script id="boat-setup-analysis" type="application/json">__ANALYSIS_JSON__</script>
<script>
(function () {
  const svgNS = "http://www.w3.org/2000/svg";
  const ANALYSIS = JSON.parse(document.getElementById("boat-setup-analysis").textContent);

  // ------------------------------------------------------- heatmap
  const WIND_RANGES = ["0-6", "6-12", "12-20", "20+"];
  const TACKS = ["port", "starboard"];
  const ANGLE_BANDS = ["upwind", "reach", "downwind"];
  const ANGLE_LABELS = { upwind: "Upwind", reach: "Reach", downwind: "Downwind" };
  const TACK_LABELS = { port: "Port", starboard: "Stbd" };
  const EVENT_LABELS = {
    "rig-tune": "Rig tune", "sail-change": "Sail change", "hull-cleaning": "Hull cleaning",
    "repair": "Repair", "crew-change": "Crew change", "other": "Event",
  };
  const EVENT_COLORS = {
    "rig-tune": "var(--mark)", "sail-change": "var(--gybe)", "hull-cleaning": "var(--starboard)",
    "repair": "var(--port)", "crew-change": "var(--dim)", "other": "var(--dim-2)",
  };
  const MIN_SAMPLES = 5;
  const ROW_H = 22, HEADER_H = 86, COL_W = 30;

  const sessions = ANALYSIS.sessions || [];
  const observations = ANALYSIS.performance_observations || [];
  const events = ANALYSIS.events || [];

  const obsMap = {};
  observations.forEach(o => {
    obsMap[o.sessionId] = obsMap[o.sessionId] || {};
    obsMap[o.sessionId][o.windRange] = obsMap[o.sessionId][o.windRange] || {};
    obsMap[o.sessionId][o.windRange][o.tack] = obsMap[o.sessionId][o.windRange][o.tack] || {};
    obsMap[o.sessionId][o.windRange][o.tack][o.angleBand] = o;
  });

  const diffMap = {};
  const diffList = [];
  sessions.forEach(s => {
    WIND_RANGES.forEach(wr => {
      ANGLE_BANDS.forEach(ab => {
        const byWind = (obsMap[s.id] || {})[wr] || {};
        const portObs = (byWind.port || {})[ab];
        const stbdObs = (byWind.starboard || {})[ab];
        if (!portObs || !stbdObs) return;
        const entry = {
          value: stbdObs.actualSpeedKnots - portObs.actualSpeedKnots,
          n: portObs.sampleCount + stbdObs.sampleCount,
          insufficient: portObs.sampleCount < MIN_SAMPLES || stbdObs.sampleCount < MIN_SAMPLES,
          portObs, stbdObs,
        };
        diffMap[`${s.id}|${wr}|${ab}`] = entry;
        diffList.push(entry);
      });
    });
  });

  function percentOf(obs) {
    return obs.targetSpeedKnots ? ((obs.actualSpeedKnots / obs.targetSpeedKnots) - 1) * 100 : null;
  }

  const validObs = observations.filter(o => o.sampleCount >= MIN_SAMPLES);
  const percentValues = validObs.map(percentOf).filter(v => v !== null);
  const PERCENT_MAX_ABS = percentValues.length ? Math.max(...percentValues.map(Math.abs)) : 50;
  const speedValues = validObs.map(o => o.actualSpeedKnots);
  const SPEED_MIN = speedValues.length ? Math.min(...speedValues) : 0;
  const SPEED_MAX = speedValues.length ? Math.max(...speedValues) : 1;
  const diffValid = diffList.filter(d => !d.insufficient).map(d => d.value);
  const DIFF_MAX_ABS = diffValid.length ? Math.max(...diffValid.map(Math.abs)) : 1;

  const filters = {
    windRanges: new Set(WIND_RANGES),
    tacks: new Set(TACKS),
    angleBands: new Set(ANGLE_BANDS),
  };
  let mode = "percent";

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function hexToRgb(hex) {
    hex = hex.replace("#", "");
    if (hex.length === 3) hex = hex.split("").map(c => c + c).join("");
    const num = parseInt(hex, 16);
    return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
  }
  function mixRgb(a, b, t) {
    const r = Math.round(a[0] + (b[0] - a[0]) * t);
    const g = Math.round(a[1] + (b[1] - a[1]) * t);
    const bl = Math.round(a[2] + (b[2] - a[2]) * t);
    return `rgb(${r},${g},${bl})`;
  }

  function getVisibleRows() {
    const rows = [];
    WIND_RANGES.forEach(wr => {
      if (!filters.windRanges.has(wr)) return;
      let groupStart = true;
      if (mode === "diff") {
        ANGLE_BANDS.forEach(ab => {
          if (!filters.angleBands.has(ab)) return;
          rows.push({ windRange: wr, tack: null, angleBand: ab, groupStart });
          groupStart = false;
        });
      } else {
        TACKS.forEach(tack => {
          if (!filters.tacks.has(tack)) return;
          ANGLE_BANDS.forEach(ab => {
            if (!filters.angleBands.has(ab)) return;
            rows.push({ windRange: wr, tack, angleBand: ab, groupStart });
            groupStart = false;
          });
        });
      }
    });
    return rows;
  }

  function cellInfo(row, session) {
    if (mode === "diff") {
      const d = diffMap[`${session.id}|${row.windRange}|${row.angleBand}`];
      if (!d) return { status: "missing" };
      if (d.insufficient) return { status: "insufficient", n: d.n, portObs: d.portObs, stbdObs: d.stbdObs };
      return { status: "ok", value: d.value, n: d.n, portObs: d.portObs, stbdObs: d.stbdObs };
    }
    const byWind = (obsMap[session.id] || {})[row.windRange] || {};
    const obs = (byWind[row.tack] || {})[row.angleBand];
    if (!obs) return { status: "missing" };
    if (obs.sampleCount < MIN_SAMPLES) return { status: "insufficient", n: obs.sampleCount, obs };
    if (mode === "speed") return { status: "ok", value: obs.actualSpeedKnots, n: obs.sampleCount, obs };
    const pct = percentOf(obs);
    if (pct === null) return { status: "insufficient", n: obs.sampleCount, obs };
    return { status: "ok", value: pct, n: obs.sampleCount, obs };
  }

  function fillFor(info, palette) {
    if (info.status !== "ok") return "url(#missingHatch)";
    if (mode === "speed") {
      const t = SPEED_MAX > SPEED_MIN ? (info.value - SPEED_MIN) / (SPEED_MAX - SPEED_MIN) : 0.5;
      return mixRgb(palette.neutral, palette.sequential, t);
    }
    const maxAbs = mode === "diff" ? DIFF_MAX_ABS : PERCENT_MAX_ABS;
    const t = maxAbs ? Math.max(-1, Math.min(1, info.value / maxAbs)) : 0;
    return t >= 0 ? mixRgb(palette.neutral, palette.positive, t) : mixRgb(palette.neutral, palette.negative, -t);
  }

  function tooltipHtml(row, session, info) {
    const windLabel = row.windRange + " kn";
    const tackLabel = row.tack ? TACK_LABELS[row.tack] : "Starboard &minus; Port";
    const angleLabel = ANGLE_LABELS[row.angleBand];
    const lines = [`<strong>${session.name}</strong>`, `${windLabel} &middot; ${tackLabel} &middot; ${angleLabel}`];
    if (info.status === "missing") {
      lines.push("No data logged for this cell.");
    } else if (mode === "diff") {
      if (info.status === "insufficient") {
        lines.push(`Insufficient samples (n=${info.n}) to compare tacks reliably.`);
      } else {
        lines.push(`Starboard ${info.stbdObs.actualSpeedKnots.toFixed(2)} kn, port ${info.portObs.actualSpeedKnots.toFixed(2)} kn`);
        lines.push(`Difference: ${info.value >= 0 ? "+" : ""}${info.value.toFixed(2)} kn (n=${info.n})`);
      }
    } else {
      const obs = info.obs;
      if (info.status === "insufficient") lines.push(`Insufficient samples (n=${info.n}) for a reliable reading.`);
      lines.push(`Actual: ${obs.actualSpeedKnots.toFixed(2)} kn &middot; Target: ${obs.targetSpeedKnots != null ? obs.targetSpeedKnots.toFixed(2) + " kn" : "n/a"}`);
      const pct = percentOf(obs);
      if (pct !== null) lines.push(`Performance: ${pct >= 0 ? "+" : ""}${pct.toFixed(1)}% vs. target`);
      lines.push(`n=${obs.sampleCount} sample(s)`);
    }
    const related = events.filter(e => e.date === session.date);
    if (related.length) lines.push(`<em>${related.map(e => e.label).join(", ")} logged this date</em>`);
    return lines.join("<br>");
  }

  function placeEvents() {
    return events.map(e => ({
      event: e,
      boundaryIndex: sessions.filter(s => s.date >= e.date).length,
    }));
  }

  function buildFilterGroup(container, title, options, labelFn, setRef, onChange) {
    container.innerHTML = "";
    const heading = document.createElement("span");
    heading.className = "filter-title";
    heading.textContent = title;
    container.appendChild(heading);
    const row = document.createElement("div");
    options.forEach(opt => {
      const wrap = document.createElement("label");
      wrap.className = "filter-chip";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = true;
      wrap.appendChild(input);
      wrap.appendChild(document.createTextNode(" " + labelFn(opt)));
      input.addEventListener("change", () => {
        if (input.checked) setRef.add(opt); else setRef.delete(opt);
        onChange();
      });
      row.appendChild(wrap);
    });
    container.appendChild(row);
  }

  function buildLegend() {
    const legend = document.getElementById("heatmapLegend");
    legend.innerHTML = "";
    let rowsHtml;
    if (mode === "speed") {
      rowsHtml = `
        <span class="row"><span class="swatch" style="background:${cssVar("--panel-2")}"></span>${SPEED_MIN.toFixed(1)} kn</span>
        <span class="row"><span class="swatch" style="background:${cssVar("--gybe")}"></span>${SPEED_MAX.toFixed(1)} kn</span>`;
    } else {
      const maxAbs = mode === "diff" ? DIFF_MAX_ABS : PERCENT_MAX_ABS;
      const unit = mode === "diff" ? " kn" : "%";
      const sign = mode === "diff" ? "" : "";
      rowsHtml = `
        <span class="row"><span class="swatch" style="background:${cssVar("--port")}"></span>-${maxAbs.toFixed(1)}${unit}${sign}</span>
        <span class="row"><span class="swatch" style="background:${cssVar("--panel-2")}"></span>0${unit}</span>
        <span class="row"><span class="swatch" style="background:${cssVar("--starboard")}"></span>+${maxAbs.toFixed(1)}${unit}</span>`;
    }
    legend.innerHTML = rowsHtml + `<span class="row"><span class="swatch hatch"></span>missing / insufficient data</span>`;
  }

  function buildHeatmap() {
    const rows = getVisibleRows();
    const svg = document.getElementById("heatmapSvg");
    const labelWrap = document.getElementById("heatmapRowLabels");
    const tooltip = document.getElementById("heatmapTooltip");

    const palette = {
      negative: hexToRgb(cssVar("--port")),
      positive: hexToRgb(cssVar("--starboard")),
      neutral: hexToRgb(cssVar("--panel-2")),
      sequential: hexToRgb(cssVar("--gybe")),
    };

    const plotW = Math.max(1, sessions.length) * COL_W;
    const plotH = Math.max(1, rows.length) * ROW_H;
    const W = plotW + 4;
    const H = HEADER_H + plotH + 4;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.innerHTML = "";

    // A dot pattern rather than a diagonal hatch -- fine diagonal lines at
    // this cell size moire badly when many hatched cells sit side by side,
    // which a sparse dot grid doesn't.
    const defs = document.createElementNS(svgNS, "defs");
    defs.innerHTML = `<pattern id="missingHatch" width="7" height="7" patternUnits="userSpaceOnUse">
      <rect width="7" height="7" fill="var(--panel-2)"></rect>
      <circle cx="3.5" cy="3.5" r="1.1" fill="var(--hair)"></circle>
    </pattern>`;
    svg.appendChild(defs);

    rows.forEach((row, ri) => {
      if (row.groupStart && ri > 0) {
        const y = HEADER_H + ri * ROW_H;
        const sep = document.createElementNS(svgNS, "line");
        sep.setAttribute("x1", 0); sep.setAttribute("x2", plotW);
        sep.setAttribute("y1", y); sep.setAttribute("y2", y);
        sep.setAttribute("stroke", "var(--hair)"); sep.setAttribute("stroke-width", "1.5");
        svg.appendChild(sep);
      }
    });

    sessions.forEach((session, ci) => {
      const x = ci * COL_W;
      rows.forEach((row, ri) => {
        const y = HEADER_H + ri * ROW_H;
        const info = cellInfo(row, session);
        const rect = document.createElementNS(svgNS, "rect");
        rect.setAttribute("x", x + 1); rect.setAttribute("y", y + 1);
        rect.setAttribute("width", COL_W - 2); rect.setAttribute("height", ROW_H - 2);
        rect.setAttribute("rx", 2);
        rect.setAttribute("fill", fillFor(info, palette));
        rect.setAttribute("tabindex", "0");
        rect.setAttribute("role", "img");
        rect.setAttribute("aria-label", tooltipHtml(row, session, info).replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim());
        const show = (clientX, clientY) => {
          tooltip.innerHTML = tooltipHtml(row, session, info);
          tooltip.classList.add("show");
          tooltip.style.left = Math.min(window.innerWidth - 270, clientX + 14) + "px";
          tooltip.style.top = (clientY + 14) + "px";
        };
        rect.addEventListener("mouseenter", ev => show(ev.clientX, ev.clientY));
        rect.addEventListener("mousemove", ev => show(ev.clientX, ev.clientY));
        rect.addEventListener("mouseleave", () => tooltip.classList.remove("show"));
        rect.addEventListener("focus", () => {
          const box = rect.getBoundingClientRect();
          show(box.left, box.top + box.height + 6);
        });
        rect.addEventListener("blur", () => tooltip.classList.remove("show"));
        svg.appendChild(rect);
      });
    });

    sessions.forEach((session, ci) => {
      const x = ci * COL_W + COL_W / 2;
      const label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", x); label.setAttribute("y", HEADER_H - 8);
      label.setAttribute("fill", "var(--dim)"); label.setAttribute("font-size", "10.5");
      label.setAttribute("text-anchor", "start");
      label.setAttribute("transform", `rotate(-55 ${x} ${HEADER_H - 8})`);
      label.textContent = session.date;
      svg.appendChild(label);
    });

    // Event lines run the full height of the plot; their labels live in a
    // dedicated lane strip at the very top (separate from the rotated
    // per-race date labels below it), cycling across a few vertical lanes
    // so labels for closely-spaced events don't stack on top of each
    // other -- and skipping the label entirely (keeping just the line and
    // its hover/title text) when two events are close enough that even
    // staggered lanes would still collide.
    const EVENT_LANE_Y = [9, 20, 31];
    const placements = placeEvents().sort((a, b) => a.boundaryIndex - b.boundaryIndex);
    let lastLabelX = -9999, lane = 0;
    placements.forEach(p => {
      const x = Math.max(2, Math.min(plotW - 2, p.boundaryIndex * COL_W));
      const color = EVENT_COLORS[p.event.type] || "var(--dim)";
      const line = document.createElementNS(svgNS, "line");
      line.setAttribute("x1", x); line.setAttribute("x2", x);
      line.setAttribute("y1", 2); line.setAttribute("y2", H - 2);
      line.setAttribute("stroke", color); line.setAttribute("stroke-width", "1.5");
      line.setAttribute("stroke-dasharray", "4,3");
      const titleEl = document.createElementNS(svgNS, "title");
      titleEl.textContent = `${EVENT_LABELS[p.event.type] || "Event"} — ${p.event.date}: ${p.event.description || p.event.label}`;
      line.appendChild(titleEl);
      svg.appendChild(line);

      const gap = x - lastLabelX;
      if (gap < 12) return; // too close even for a staggered lane -- rely on the line's hover title
      lane = gap < 46 ? (lane + 1) % EVENT_LANE_Y.length : 0;
      lastLabelX = x;
      const text = document.createElementNS(svgNS, "text");
      text.setAttribute("x", x + 3); text.setAttribute("y", EVENT_LANE_Y[lane]);
      text.setAttribute("fill", color); text.setAttribute("font-size", "10");
      text.textContent = EVENT_LABELS[p.event.type] || p.event.label;
      svg.appendChild(text);
    });

    labelWrap.innerHTML = "";
    const spacer = document.createElement("div");
    spacer.style.height = HEADER_H + "px";
    labelWrap.appendChild(spacer);
    rows.forEach(row => {
      const div = document.createElement("div");
      div.className = "heatmap-row-label" + (row.groupStart ? " group-start" : "");
      div.style.height = ROW_H + "px";
      const windPart = row.groupStart ? `<span class="wind-part">${row.windRange} kn</span>` : "";
      const tackAngle = row.tack ? `${TACK_LABELS[row.tack]} &middot; ${ANGLE_LABELS[row.angleBand]}` : ANGLE_LABELS[row.angleBand];
      div.innerHTML = `${windPart}<span class="tack-angle-part">${tackAngle}</span>`;
      labelWrap.appendChild(div);
    });
  }

  function initHeatmap() {
    buildFilterGroup(document.getElementById("windFilterGroup"), "Wind", WIND_RANGES, w => w + " kn", filters.windRanges, buildHeatmap);
    buildFilterGroup(document.getElementById("tackFilterGroup"), "Tack", TACKS, t => TACK_LABELS[t], filters.tacks, buildHeatmap);
    buildFilterGroup(document.getElementById("angleFilterGroup"), "Angle", ANGLE_BANDS, a => ANGLE_LABELS[a], filters.angleBands, buildHeatmap);
    document.getElementById("heatmapMode").addEventListener("change", ev => {
      mode = ev.target.value;
      document.getElementById("tackFilterGroup").classList.toggle("disabled", mode === "diff");
      buildLegend();
      buildHeatmap();
    });
    buildLegend();
    buildHeatmap();
  }

  // ------------------------------------------------------- hull drag chart
  const HULL_COLORS = { "0-8": "var(--gybe)", "8-12": "var(--starboard)", "12-20": "var(--mark)", "20+": "var(--port)" };

  function buildHullChart() {
    const svg = document.getElementById("hullChart");
    const tooltip = document.getElementById("hullTooltip");
    const wrap = svg.parentElement;
    const rect = wrap.getBoundingClientRect();
    const W = Math.max(360, rect.width), H = Math.max(320, rect.height);

    const dateSet = new Set();
    Object.values(ANALYSIS.hull_drag || {}).forEach(entries => entries.forEach(e => dateSet.add(e.race_date)));
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

  initHeatmap();
  buildHullChart();
  window.addEventListener("resize", buildHullChart);
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
        "sessions": [], "performance_observations": [], "events": [],
        "wind_bands_hull": [], "hull_drag": {},
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
