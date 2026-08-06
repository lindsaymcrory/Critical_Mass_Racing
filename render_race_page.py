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

"""Renders one race's static Race Results HTML page: course plot, maneuver
analysis, and polar performance, in that order, each its own labeled
section. Combines the rendering JS from course_visualization.html and
polar_visualization.html (single-race: no session switcher needed, since
each race gets its own static page). Races with a hand-entered
"fleet_results" table in races.json also get a Fleet Comparison section
(see fleet_comparison.py) -- omitted entirely for every other race."""
import html as html_mod
import json
import re
import sqlite3
from pathlib import Path

import fleet_comparison
from export_course_data import export_for_race as export_course
from export_polar_data import export_for_race as export_polar
from polar import PolarTable

ROOT = Path(__file__).parent
DB_PATH = ROOT / "race_sessions.db"
POLAR_PATH = ROOT / "j80_Polars.csv"
RACES_DIR = ROOT / "races"

PAGE_TEMPLATE = """<title>__TITLE__ — Race Results</title>
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
  .mono {
    font-family: ui-monospace, "SF Mono", "Cascadia Mono", "Roboto Mono", Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
  }
  .label { text-transform: uppercase; letter-spacing: 0.09em; font-size: 11px; color: var(--dim); font-weight: 600; }
  a { color: inherit; }
  a.back { text-decoration: none; color: var(--dim); font-size: 12px; }
  a.back:hover { color: var(--paper); }

  header {
    display: flex; align-items: center; gap: 22px; flex-wrap: wrap;
    padding: 16px 24px; border-bottom: 1px solid var(--hair); background: var(--panel-2);
    position: sticky; top: 0; z-index: 30;
  }
  .brand { display: flex; flex-direction: column; gap: 2px; margin-right: auto; }
  .brand .title { font-size: 17px; font-weight: 700; letter-spacing: 0.02em; }
  .brand .sub { font-size: 11.5px; color: var(--dim); }
  .meta { display: flex; gap: 22px; flex-wrap: wrap; }
  .meta .item { display: flex; flex-direction: column; gap: 2px; }
  .meta .item .v { font-size: 13px; }
  .meta .item .v.warn { color: var(--mark); }

  section { border-bottom: 1px solid var(--hair); }
  .section-head {
    display: flex; align-items: baseline; justify-content: space-between;
    padding: 16px 24px 0;
  }
  .section-title { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }

  /* -- course plot -- */
  .chart-wrap { background: var(--panel-2); position: relative; height: 62vh; min-height: 420px; }
  #courseChart { width: 100%; height: 100%; display: block; }
  .legend {
    position: absolute; top: 14px; left: 14px; display: flex; flex-direction: column; gap: 6px;
    background: rgba(10, 26, 32, 0.72); backdrop-filter: blur(4px);
    padding: 10px 12px; border-radius: var(--radius); border: 1px solid var(--hair); font-size: 11px;
  }
  :root[data-theme="light"] .legend { background: rgba(255,255,255,0.82); }
  .legend .row { display: flex; align-items: center; gap: 8px; }
  .legend .sw { width: 12px; height: 12px; border-radius: 50%; flex: none; }
  .legend .ln { width: 16px; height: 3px; border-radius: 2px; flex: none; }
  .scale { position: absolute; bottom: 16px; right: 14px; display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--dim); }
  .scale .bar { height: 2px; background: var(--dim); }
  .trim-bar {
    display: flex; align-items: center; gap: 14px; padding: 12px 24px;
    background: var(--panel-2); border-top: 1px solid var(--hair);
  }
  .trim-bar input[type=range] { flex: 1; accent-color: var(--mark); cursor: pointer; }
  .trim-time { font-size: 12.5px; color: var(--paper); min-width: 92px; text-align: right; font-variant-numeric: tabular-nums; }
  .trim-btn {
    appearance: none; border: none; background: var(--mark); color: #201404;
    font: inherit; font-size: 12px; font-weight: 700; padding: 7px 14px;
    border-radius: var(--radius); cursor: pointer;
  }
  .trim-btn:hover { filter: brightness(1.05); }
  .trim-btn:disabled { opacity: 0.55; cursor: wait; }
  .trim-btn.secondary { background: transparent; color: var(--dim); border: 1px solid var(--hair); }
  .trim-btn.secondary:hover { color: var(--paper); border-color: var(--dim); filter: none; }
  .trim-status { font-size: 11.5px; color: var(--dim); }
  .trim-status.err { color: var(--port); }
  .marks-legend {
    top: auto; bottom: 14px; left: 14px; max-height: 46%; overflow-y: auto;
    display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; font-size: 10.5px;
  }
  .marks-legend .mnum {
    display: inline-flex; align-items: center; justify-content: center; width: 16px; height: 16px;
    border-radius: 50%; background: var(--mark); color: #201404; font-weight: 700; font-size: 9px;
  }
  .marks-legend .mname { color: var(--paper); align-self: center; }
  .tooltip {
    position: absolute; pointer-events: none; background: var(--panel);
    border: 1px solid var(--grid-strong); border-radius: var(--radius);
    padding: 8px 10px; font-size: 11px; line-height: 1.5; white-space: nowrap;
    box-shadow: 0 4px 16px rgba(0,0,0,0.35); opacity: 0; transition: opacity 0.08s; z-index: 20;
  }
  .tooltip .t-title { font-weight: 700; margin-bottom: 2px; }
  .tooltip.show { opacity: 1; }

  /* -- maneuver analysis -- */
  .stats {
    display: grid; grid-template-columns: repeat(6, 1fr); gap: 1px; background: var(--hair);
    margin: 14px 24px 0; border: 1px solid var(--hair); border-radius: var(--radius); overflow: hidden;
  }
  @media (max-width: 900px) { .stats { grid-template-columns: repeat(3, 1fr); } }
  .stat { background: var(--panel); padding: 12px 14px; }
  .stat .num { font-size: 20px; font-weight: 700; }
  .stat .num .unit { font-size: 11px; color: var(--dim); font-weight: 600; margin-left: 3px; }
  .log-wrap { margin: 4px 24px 20px; }
  .log-head { padding: 12px 0 8px; display: flex; align-items: baseline; justify-content: space-between; }
  .log { border: 1px solid var(--hair); border-radius: var(--radius); max-height: 420px; overflow-y: auto; }
  .maneuver-row {
    display: grid; grid-template-columns: 20px 62px 1fr 56px 44px; gap: 10px; align-items: center;
    padding: 8px 14px; border-top: 1px solid var(--hair); font-size: 12px; cursor: pointer;
  }
  .maneuver-row:first-child { border-top: none; }
  .maneuver-row:hover, .maneuver-row.hi { background: var(--panel-2); }
  .maneuver-row.head {
    cursor: default; padding: 10px 14px; font-size: 13px; text-transform: uppercase;
    letter-spacing: 0.07em; color: var(--paper); font-weight: 700;
    position: sticky; top: 0; background: var(--panel); z-index: 2;
    border-bottom: 1px solid var(--hair);
  }
  .maneuver-row.head:hover { background: var(--panel); }
  .m-deg { text-align: right; }
  .glyph { width: 10px; height: 10px; justify-self: center; }
  .glyph.diamond { transform: rotate(45deg); border-radius: 2px; }
  .glyph.triangle {
    width: 0; height: 0; background: none !important;
    border-left: 6px solid transparent; border-right: 6px solid transparent; border-bottom: 10px solid var(--gybe);
  }
  .glyph.star { border-radius: 50%; background: var(--mark); }
  .m-type { text-transform: capitalize; font-weight: 600; }
  .m-detail { color: var(--dim); font-size: 11px; }
  .m-dur { color: var(--dim); }

  /* -- polar performance -- */
  .polar-main { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 1px; background: var(--hair); }
  @media (max-width: 860px) { .polar-main { grid-template-columns: 1fr; } }
  .polar-chart-wrap { background: var(--panel-2); position: relative; height: 62vh; min-height: 480px; }
  #polarChart { width: 100%; height: 100%; display: block; }
  .polar-sidebar { background: var(--panel); }
  .side-section { padding: 14px; border-bottom: 1px solid var(--hair); }
  .side-section .label { margin-bottom: 10px; display: block; }
  .pos-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-top: 1px solid var(--hair); }
  .pos-row:first-of-type { border-top: none; }
  .pos-name { font-weight: 700; font-size: 13px; text-transform: capitalize; }
  .pos-n { font-size: 10.5px; color: var(--dim); }
  .pos-pct { font-size: 20px; font-weight: 700; }
  .pos-pct .unit { font-size: 11px; color: var(--dim); font-weight: 600; }
  .bar-track { height: 5px; border-radius: 3px; background: var(--hair); margin-top: 6px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 3px; background: var(--mark); }
  .curve-key { display: flex; flex-direction: column; gap: 8px; }
  .curve-key .row { display: flex; align-items: center; gap: 10px; font-size: 12px; }
  .curve-key .sw { width: 18px; height: 2px; flex: none; }
  .curve-key .details { color: var(--dim); font-size: 10.5px; }

  /* -- Fleet Comparison -- */
  .fleet-summary {
    margin: 4px 24px 20px; padding: 16px 20px;
    border: 1px solid var(--hair); border-radius: var(--radius);
    background: var(--panel); font-size: 13.5px; line-height: 1.6; max-width: 900px;
  }
  .fleet-table-wrap { margin: 4px 24px 24px; border: 1px solid var(--hair); border-radius: var(--radius); overflow-x: auto; }
  table.fleet-table { width: 100%; border-collapse: collapse; font-size: 12.5px; white-space: nowrap; }
  table.fleet-table th, table.fleet-table td { padding: 9px 14px; text-align: left; border-top: 1px solid var(--hair); }
  table.fleet-table th { text-transform: uppercase; letter-spacing: 0.06em; font-size: 10.5px; color: var(--dim); background: var(--panel-2); border-top: none; }
  table.fleet-table tr:first-child td { border-top: none; }
  table.fleet-table td.mono, table.fleet-table th.mono { font-family: ui-monospace, "SF Mono", "Cascadia Mono", monospace; }
  table.fleet-table tr.us { background: rgba(245, 185, 66, 0.1); }
  table.fleet-table tr.us td:first-child { border-left: 2px solid var(--mark); }
  .fleet-subhead { padding: 20px 24px 8px; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--dim); }

  footer {
    padding: 12px 24px; background: var(--panel-2);
    font-size: 10.5px; color: var(--dim-2); display: flex; gap: 18px; flex-wrap: wrap;
  }
  ::-webkit-scrollbar { width: 9px; height: 9px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--hair); border-radius: 5px; }
</style>

<header>
  <a class="back" href="/">&larr; All races</a>
  <div class="brand">
    <div class="title">__TITLE__</div>
    <div class="sub">__SERIES__ &middot; __BOAT__</div>
  </div>
  <div class="meta" id="metaPanel"></div>
</header>

<section id="course-section">
  <div class="section-head"><span class="section-title">Course Plot</span></div>
  <div class="chart-wrap">
    <svg id="courseChart" xmlns="http://www.w3.org/2000/svg"></svg>
    <div class="legend" id="legend"></div>
    <div class="legend marks-legend" id="marksLegend"></div>
    <div class="scale" id="scaleBar"></div>
    <div class="tooltip mono" id="courseTooltip"></div>
  </div>
  <div class="trim-bar">
    <span class="label">Trim finish</span>
    <input type="range" id="trimSlider" aria-label="Trim the end of the displayed track">
    <span class="mono trim-time" id="trimLabel"></span>
    <button id="saveTrimBtn" class="trim-btn" type="button">Save trim</button>
    <button id="clearTrimBtn" class="trim-btn secondary" type="button" hidden>Clear saved trim</button>
    <span class="trim-status" id="trimStatus"></span>
  </div>
</section>

<section id="maneuver-section">
  <div class="section-head"><span class="section-title">Maneuver Analysis</span></div>
  <div class="stats" id="stats"></div>
  <div class="log-wrap">
    <div class="log-head"><span class="label">Maneuver log</span><span class="label" id="logCount"></span></div>
    <div class="log" id="log"></div>
  </div>
</section>

<section id="polar-section">
  <div class="section-head"><span class="section-title">Polar Performance</span></div>
  <div class="polar-main">
    <div class="polar-chart-wrap">
      <svg id="polarChart" xmlns="http://www.w3.org/2000/svg"></svg>
      <div class="legend" id="polarLegend"></div>
      <div class="tooltip mono" id="polarTooltip"></div>
    </div>
    <div class="polar-sidebar">
      <div class="side-section"><span class="label">% of target speed by point of sail</span><div id="posStats"></div></div>
      <div class="side-section"><span class="label">Target curves shown</span><div class="curve-key" id="curveKey"></div></div>
    </div>
  </div>
</section>

__FLEET_COMPARISON_SECTION__
<footer>
  <span>Course: GPS position, 1 Hz, decimated 1:3</span>
  <span>Tack/gybe: hysteresis on apparent-wind side, min 45&deg; heading change, min 1.5 kn</span>
  <span>Polar target: j80_Polars.csv (crewed polar; may not reflect actual crew count)</span>
</footer>

<script id="race-meta" type="application/json">__RACE_META__</script>
<script id="course-data" type="application/json">__COURSE_DATA__</script>
<script id="polar-data" type="application/json">__POLAR_DATA__</script>
<script>
(function () {
  "use strict";
  const COURSE = JSON.parse(document.getElementById("course-data").textContent);
  const POLAR = JSON.parse(document.getElementById("polar-data").textContent);
  const svgNS = "http://www.w3.org/2000/svg";

  function fmtDateTime(s) {
    if (!s) return "";
    const dt = new Date(s.replace(" ", "T") + "Z");
    return dt.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function buildMeta() {
    const el = document.getElementById("metaPanel");
    const durMin = Math.round((new Date(COURSE.utc_end) - new Date(COURSE.utc_start)) / 60000);
    el.innerHTML = `
      <div class="item"><span class="label">Local start</span><span class="v mono">${COURSE.local_start_time} ADT</span></div>
      <div class="item"><span class="label">Logged span</span><span class="v mono">${durMin} min</span></div>
      ${COURSE.notes ? `<div class="item"><span class="label">Note</span><span class="v warn">${COURSE.notes}</span></div>` : ""}
    `;
  }

  /* ---------------- Course plot (course_visualization.html, single-race) ---------------- */
  (function () {
    const chart = document.getElementById("courseChart");
    const tooltip = document.getElementById("courseTooltip");
    const chartWrap = chart.parentElement;
    let hiRowEl = null;
    let markerEls = [];

    // Trim slider state: the log includes the post-race trip back to the
    // dock, so the displayed end time can be pulled back. Everything below
    // (track, markers, log, stats) is computed from the trimmed window.
    const fullTrack = COURSE.track;
    const minElapsed = fullTrack[0][0], maxElapsed = fullTrack[fullTrack.length - 1][0];
    let cutoffElapsed = maxElapsed;
    function visibleTrack() { return fullTrack.filter(p => p[0] <= cutoffElapsed); }
    function visibleManeuvers() {
      const vt = visibleTrack();
      const lastTs = vt.length ? vt[vt.length - 1][9] : "";
      return COURSE.maneuvers.filter(m => m.start_utc <= lastTs);
    }
    function fmtLocalTs(ts) {
      // The logger's clock is true UTC (verified by GPS cross-correlation
      // against a Vakaros track with explicit timezone offsets -- 2 m median
      // position agreement at zero clock offset). Display in ADT (UTC-3).
      const t = new Date(new Date(ts.replace(" ", "T") + "Z").getTime() - 3 * 3600 * 1000);
      return String(t.getUTCHours()).padStart(2, "0") + ":" +
             String(t.getUTCMinutes()).padStart(2, "0") + ":" +
             String(t.getUTCSeconds()).padStart(2, "0");
    }

    function speedColor(kn, minKn, maxKn) {
      const t = maxKn > minKn ? Math.max(0, Math.min(1, (kn - minKn) / (maxKn - minKn))) : 0.5;
      const stops = [[0.00,[64,110,168]],[0.35,[66,150,150]],[0.65,[219,168,68]],[1.00,[224,96,68]]];
      let a = stops[0], b = stops[stops.length - 1];
      for (let i = 0; i < stops.length - 1; i++) {
        if (t >= stops[i][0] && t <= stops[i + 1][0]) { a = stops[i]; b = stops[i + 1]; break; }
      }
      const span = b[0] - a[0] || 1;
      const lt = (t - a[0]) / span;
      const c = a[1].map((v, i) => Math.round(v + (b[1][i] - v) * lt));
      return `rgb(${c[0]},${c[1]},${c[2]})`;
    }

    function buildLegend() {
      document.getElementById("legend").innerHTML = `
        <div class="row"><span class="ln" style="background:${speedColor(0,0,1)}"></span>slow</div>
        <div class="row"><span class="ln" style="background:${speedColor(1,0,1)}"></span>fast (STW)</div>
        <div class="row"><span class="sw" style="background:var(--starboard);border-radius:2px;transform:rotate(45deg)"></span>tack &rarr; stbd</div>
        <div class="row"><span class="sw" style="background:var(--port);border-radius:2px;transform:rotate(45deg)"></span>tack &rarr; port</div>
        <div class="row"><span class="sw" style="width:0;height:0;background:none;border-left:5px solid transparent;border-right:5px solid transparent;border-bottom:9px solid var(--gybe);border-radius:0"></span>gybe</div>
        <div class="row"><span class="sw" style="background:var(--mark)"></span>rounding / mark</div>
      `;
    }

    function buildMarksLegend() {
      document.getElementById("marksLegend").innerHTML = COURSE.waypoints.map(wp =>
        `<span class="mnum">${wp.id}</span><span class="mname">${wp.name}</span>`
      ).join("");
    }

    function statBlock(num, unit, label) {
      return `<div class="stat"><div class="num">${num}<span class="unit">${unit}</span></div><div class="label">${label}</div></div>`;
    }
    function avgOf(arr) {
      const v = arr.filter(x => x !== null && x !== undefined);
      if (!v.length) return null;
      return v.reduce((a, b) => a + b, 0) / v.length;
    }

    function buildStats() {
      const el = document.getElementById("stats");
      const mans = visibleManeuvers();
      const tacks = mans.filter(m => m.type === "tack");
      const gybes = mans.filter(m => m.type === "gybe");
      const roundings = mans.filter(m => m.type === "rounding" || m.type === "rounding-turn");
      const avgLoss = avgOf(tacks.concat(gybes).map(m => m.speed_loss_pct));
      const avgDur = avgOf(tacks.concat(gybes).map(m => m.duration_s));
      const maxStw = Math.max(...visibleTrack().map(p => p[5] || 0));
      el.innerHTML =
        statBlock(tacks.length, "", "Tacks") + statBlock(gybes.length, "", "Gybes") +
        statBlock(roundings.length, "", "Roundings") + statBlock(maxStw.toFixed(1), "kn", "Max speed") +
        statBlock(avgDur !== null ? avgDur.toFixed(0) : "&mdash;", "s", "Avg duration") +
        statBlock(avgLoss !== null ? avgLoss.toFixed(0) : "&mdash;", "%", "Avg speed loss");
    }

    function isStarboardAfter(m) { return m.twa_after !== null && m.twa_after >= 0; }
    function typeLabel(t) {
      if (t === "rounding-turn") return "Rounding (bear-away)";
      if (t === "rounding") return "Rounding";
      return t;
    }
    function glyphFor(type, m) {
      if (type === "tack") return `<span class="glyph diamond" style="background:${isStarboardAfter(m) ? "var(--starboard)" : "var(--port)"}"></span>`;
      if (type === "gybe") return `<span class="glyph triangle"></span>`;
      return `<span class="glyph star"></span>`;
    }

    function buildLog() {
      const log = document.getElementById("log");
      const mans = visibleManeuvers();
      document.getElementById("logCount").textContent = mans.length + " events";
      log.innerHTML = "";

      const head = document.createElement("div");
      head.className = "maneuver-row head";
      head.innerHTML = `<span></span><span>Time</span><span>Maneuver</span>` +
        `<span class="m-deg">Turn</span><span class="m-deg">Dur</span>`;
      log.appendChild(head);

      mans.forEach((m, i) => {
        const row = document.createElement("div");
        row.className = "maneuver-row";
        row.tabIndex = 0;
        // Logger clock is true UTC (Vakaros-verified); display in ADT (UTC-3).
        const t = new Date(new Date(m.start_utc.replace(" ", "T") + "Z").getTime() - 3 * 3600 * 1000);
        const hh = String(t.getUTCHours()).padStart(2, "0");
        const mm = String(t.getUTCMinutes()).padStart(2, "0");
        const ss = String(t.getUTCSeconds()).padStart(2, "0");
        let detail = "";
        if (m.speed_loss_pct !== null) detail += `-${m.speed_loss_pct}% spd`;
        if (m.distance_to_mark !== null) detail += (detail ? " &middot; " : "") + `${m.distance_to_mark}m to mark`;
        row.innerHTML = `${glyphFor(m.type, m)}<span class="mono m-dur">${hh}:${mm}:${ss}</span>` +
          `<span><span class="m-type">${typeLabel(m.type)}</span><br><span class="m-detail">${detail}</span></span>` +
          `<span class="mono m-deg">${m.heading_change !== null ? Math.abs(m.heading_change) + "&deg;" : ""}</span>` +
          `<span class="mono m-dur m-deg">${m.duration_s !== null ? m.duration_s.toFixed(0) + "s" : ""}</span>`;
        row.addEventListener("mouseenter", () => highlightManeuver(i, row));
        row.addEventListener("focus", () => highlightManeuver(i, row));
        log.appendChild(row);
      });
    }

    function highlightManeuver(i, row) {
      if (hiRowEl) hiRowEl.classList.remove("hi");
      hiRowEl = row;
      row.classList.add("hi");
      markerEls.forEach((el, j) => el.setAttribute("stroke-width", j === i ? "2.5" : "1"));
      if (markerEls[i]) markerEls[i].parentNode.appendChild(markerEls[i]);
    }

    function drawChart() {
      const track = visibleTrack();
      // bounds come from the FULL track + marks so the view stays stable
      // while the trim slider moves
      const xs = fullTrack.map(p => p[1]).concat(COURSE.waypoints.map(w => w.x));
      const ys = fullTrack.map(p => p[2]).concat(COURSE.waypoints.map(w => w.y));
      const minX = Math.min(...xs), maxX = Math.max(...xs);
      const minY = Math.min(...ys), maxY = Math.max(...ys);
      const padFrac = 0.08;
      const spanX = (maxX - minX) || 100, spanY = (maxY - minY) || 100;
      const padX = spanX * padFrac, padY = spanY * padFrac;
      const rect = chartWrap.getBoundingClientRect();
      const W = Math.max(320, rect.width), H = Math.max(320, rect.height);
      const dataW = spanX + 2 * padX, dataH = spanY + 2 * padY;
      const scale = Math.min(W / dataW, H / dataH);
      const offX = (W - dataW * scale) / 2, offY = (H - dataH * scale) / 2;
      function sx(x) { return offX + (x - (minX - padX)) * scale; }
      function sy(y) { return H - (offY + (y - (minY - padY)) * scale); }

      chart.setAttribute("viewBox", `0 0 ${W} ${H}`);
      chart.innerHTML = "";

      const rawStep = dataW / 6;
      const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
      const steps = [1, 2, 5, 10].map(m => m * mag);
      const step = steps.reduce((a, b) => Math.abs(b - rawStep) < Math.abs(a - rawStep) ? b : a);

      const gridGroup = document.createElementNS(svgNS, "g");
      for (let gx = Math.ceil((minX - padX) / step) * step; gx <= maxX + padX; gx += step) {
        const line = document.createElementNS(svgNS, "line");
        line.setAttribute("x1", sx(gx)); line.setAttribute("x2", sx(gx));
        line.setAttribute("y1", 0); line.setAttribute("y2", H);
        line.setAttribute("stroke", "var(--grid)"); line.setAttribute("stroke-width", "1");
        gridGroup.appendChild(line);
      }
      for (let gy = Math.ceil((minY - padY) / step) * step; gy <= maxY + padY; gy += step) {
        const line = document.createElementNS(svgNS, "line");
        line.setAttribute("y1", sy(gy)); line.setAttribute("y2", sy(gy));
        line.setAttribute("x1", 0); line.setAttribute("x2", W);
        line.setAttribute("stroke", "var(--grid)"); line.setAttribute("stroke-width", "1");
        gridGroup.appendChild(line);
      }
      chart.appendChild(gridGroup);

      // color scale normalized over the FULL track so segment colors don't
      // shift as the trim slider moves
      const speeds = fullTrack.map(p => p[5]).filter(v => v !== null && v !== undefined);
      const minS = Math.min(...speeds), maxS = Math.max(...speeds);
      const N_BUCKET = 10;
      function bucketOf(v) {
        if (v === null || v === undefined) return -1;
        const t = maxS > minS ? (v - minS) / (maxS - minS) : 0;
        return Math.min(N_BUCKET - 1, Math.floor(t * N_BUCKET));
      }
      let curBucket = null, curPath = [];
      const trackGroup = document.createElementNS(svgNS, "g");
      trackGroup.setAttribute("fill", "none");
      trackGroup.setAttribute("stroke-linecap", "round");
      trackGroup.setAttribute("stroke-linejoin", "round");
      function flushPath() {
        if (curPath.length < 2 || curBucket === null) { curPath = []; return; }
        const d = curPath.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p[1]).toFixed(1)},${sy(p[2]).toFixed(1)}`).join(" ");
        const path = document.createElementNS(svgNS, "path");
        path.setAttribute("d", d);
        const midT = (curBucket + 0.5) / N_BUCKET;
        path.setAttribute("stroke", speedColor(midT, 0, 1));
        path.setAttribute("stroke-width", "2.25");
        trackGroup.appendChild(path);
        curPath = [];
      }
      track.forEach((p) => {
        const b = bucketOf(p[5]);
        if (b !== curBucket) {
          if (curPath.length) curPath.push(p);
          flushPath();
          curBucket = b;
          curPath = [p];
        } else { curPath.push(p); }
      });
      flushPath();
      chart.appendChild(trackGroup);

      const hoverGroup = document.createElementNS(svgNS, "g");
      const HOVER_STEP = Math.max(1, Math.floor(track.length / 600));
      for (let i = 0; i < track.length; i += HOVER_STEP) {
        const p = track[i];
        const c = document.createElementNS(svgNS, "circle");
        c.setAttribute("cx", sx(p[1])); c.setAttribute("cy", sy(p[2]));
        c.setAttribute("r", "7"); c.setAttribute("fill", "transparent");
        c.addEventListener("mouseenter", (ev) => showTooltip(ev, p));
        c.addEventListener("mouseleave", hideTooltip);
        hoverGroup.appendChild(c);
      }
      chart.appendChild(hoverGroup);

      COURSE.waypoints.forEach(wp => {
        const g = document.createElementNS(svgNS, "g");
        const cx = sx(wp.x), cy = sy(wp.y);
        const r = 10;
        const c = document.createElementNS(svgNS, "circle");
        c.setAttribute("cx", cx); c.setAttribute("cy", cy); c.setAttribute("r", r);
        c.setAttribute("fill", "var(--mark)");
        c.setAttribute("stroke", "var(--ink)"); c.setAttribute("stroke-width", "1.5");
        g.appendChild(c);
        const label = document.createElementNS(svgNS, "text");
        label.setAttribute("x", cx); label.setAttribute("y", cy);
        label.setAttribute("fill", "#201404"); label.setAttribute("font-size", wp.id.length > 1 ? "9.5" : "11");
        label.setAttribute("font-weight", "700"); label.setAttribute("text-anchor", "middle");
        label.setAttribute("dominant-baseline", "central");
        label.textContent = wp.id;
        g.appendChild(label);
        g.style.cursor = "pointer";
        g.addEventListener("mouseenter", (ev) => showTooltip(ev, null, `Mark ${wp.id}: ${wp.name}`));
        g.addEventListener("mouseleave", hideTooltip);
        chart.appendChild(g);
      });

      markerEls = [];
      visibleManeuvers().forEach((m) => {
        let el;
        const cx = sx(m.x), cy = sy(m.y);
        if (m.type === "tack") {
          el = document.createElementNS(svgNS, "rect");
          const size = 9;
          el.setAttribute("x", cx - size / 2); el.setAttribute("y", cy - size / 2);
          el.setAttribute("width", size); el.setAttribute("height", size);
          el.setAttribute("transform", `rotate(45 ${cx} ${cy})`);
          el.setAttribute("fill", isStarboardAfter(m) ? "var(--starboard)" : "var(--port)");
        } else if (m.type === "gybe") {
          el = document.createElementNS(svgNS, "polygon");
          const s2 = 7;
          el.setAttribute("points", `${cx},${cy - s2} ${cx - s2},${cy + s2} ${cx + s2},${cy + s2}`);
          el.setAttribute("fill", "var(--gybe)");
        } else {
          el = document.createElementNS(svgNS, "circle");
          el.setAttribute("cx", cx); el.setAttribute("cy", cy); el.setAttribute("r", "6");
          el.setAttribute("fill", "var(--mark)");
        }
        el.setAttribute("stroke", "var(--ink)"); el.setAttribute("stroke-width", "1");
        el.style.cursor = "pointer";
        el.addEventListener("mouseenter", (ev) => showTooltip(ev, null, maneuverTooltip(m)));
        el.addEventListener("mouseleave", hideTooltip);
        chart.appendChild(el);
        markerEls.push(el);
      });

      const scaleEl = document.getElementById("scaleBar");
      const barPx = step * scale;
      scaleEl.innerHTML = `<span class="bar" style="width:${barPx}px"></span><span>${step >= 1000 ? (step/1000)+" km" : step+" m"}</span>`;
    }

    function maneuverTooltip(m) {
      let s = `<div class="t-title">${typeLabel(m.type)}</div>`;
      if (m.heading_before !== null) s += `hdg ${m.heading_before}&deg; &rarr; ${m.heading_after}&deg;<br>`;
      if (m.twa_before !== null) s += `TWA ${m.twa_before}&deg; &rarr; ${m.twa_after}&deg;<br>`;
      if (m.speed_before !== null) s += `spd ${m.speed_before}`;
      if (m.speed_min !== null) s += ` &rarr; ${m.speed_min} kn`;
      if (m.speed_loss_pct !== null) s += ` (-${m.speed_loss_pct}%)`;
      if (m.distance_to_mark !== null) s += `<br>${m.distance_to_mark} m to mark`;
      return s;
    }
    function showTooltip(ev, trackPoint, html) {
      const wrapRect = chartWrap.getBoundingClientRect();
      let content = html;
      if (trackPoint) {
        const [elapsed, x, y, hdg, sog, stw, twa, tws, tack] = trackPoint;
        content = `<div class="t-title">${tack === "s" ? "Starboard" : "Port"} tack</div>` +
          `hdg ${hdg}&deg; &middot; STW ${stw} kn<br>TWA ${twa}&deg; &middot; TWS ${tws} kn`;
      }
      tooltip.innerHTML = content;
      tooltip.classList.add("show");
      tooltip.style.left = (ev.clientX - wrapRect.left + 14) + "px";
      tooltip.style.top = (ev.clientY - wrapRect.top + 14) + "px";
    }
    function hideTooltip() { tooltip.classList.remove("show"); }

    const trimSlider = document.getElementById("trimSlider");
    const trimLabel = document.getElementById("trimLabel");
    trimSlider.min = minElapsed;
    trimSlider.max = maxElapsed;
    trimSlider.step = 10;
    trimSlider.value = maxElapsed;
    function updateTrimLabel() {
      const vt = visibleTrack();
      trimLabel.textContent = vt.length ? fmtLocalTs(vt[vt.length - 1][9]) + " ADT" : "";
    }
    trimSlider.addEventListener("input", () => {
      cutoffElapsed = +trimSlider.value;
      updateTrimLabel();
      buildStats(); buildLog(); drawChart();
    });
    updateTrimLabel();

    // Save/clear the trim permanently: POSTs to the app, which stores the
    // cutoff in races.json and rebuilds this race's data (maneuvers + polar
    // recompute without the trimmed tail), then regenerates this page.
    // Only works when served by the app (not when opened as a bare file).
    const RACE_META = JSON.parse(document.getElementById("race-meta").textContent);
    const saveBtn = document.getElementById("saveTrimBtn");
    const clearBtn = document.getElementById("clearTrimBtn");
    const trimStatus = document.getElementById("trimStatus");
    if (RACE_META.trim_end_utc) {
      clearBtn.hidden = false;
      trimStatus.textContent = "trim saved";
    }
    async function postTrim(trimEndUtc, busyLabel) {
      saveBtn.disabled = true; clearBtn.disabled = true;
      trimStatus.classList.remove("err");
      trimStatus.textContent = busyLabel + " recomputing race…";
      try {
        const r = await fetch("/save-trim", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ race_id: RACE_META.id, trim_end_utc: trimEndUtc }),
        });
        if (!r.ok) throw new Error("server returned " + r.status);
        location.reload();
      } catch (e) {
        saveBtn.disabled = false; clearBtn.disabled = false;
        trimStatus.classList.add("err");
        trimStatus.textContent = "failed: " + e.message;
      }
    }
    saveBtn.addEventListener("click", () => {
      const vt = visibleTrack();
      if (!vt.length) return;
      postTrim(vt[vt.length - 1][9], "saving…");
    });
    clearBtn.addEventListener("click", () => postTrim(null, "clearing…"));

    buildLegend(); buildMarksLegend(); buildStats(); buildLog(); drawChart();
    window.addEventListener("resize", drawChart);
  })();

  /* ---------------- Polar performance (polar_visualization.html, single-race) ---------------- */
  (function () {
    const chart = document.getElementById("polarChart");
    const tooltip = document.getElementById("polarTooltip");
    const chartWrap = chart.parentElement;
    const CURVE_COLORS = { 8: "#5aa7e0", 12: "#f5b942", 16: "#ef5a4c" };

    function buildLegend() {
      document.getElementById("polarLegend").innerHTML = `
        <div class="row"><span class="sw" style="background:var(--starboard);border-radius:50%;width:7px;height:7px"></span>starboard tack</div>
        <div class="row"><span class="sw" style="background:var(--port);border-radius:50%;width:7px;height:7px"></span>port tack</div>
        <div class="row"><span class="ln" style="background:var(--dim)"></span>speed ring (kn)</div>
        <div class="row"><span class="ln" style="background:var(--mark);opacity:.6"></span>target curve</div>
      `;
    }
    function buildPosStats() {
      const el = document.getElementById("posStats");
      const order = ["beat", "reach", "run"];
      el.innerHTML = order.map(pos => {
        const st = POLAR.stats[pos];
        const pct = st.avg_pct !== null ? st.avg_pct : 0;
        return `<div class="pos-row"><div><div class="pos-name">${pos}</div><div class="pos-n">${st.n.toLocaleString()} samples</div></div>` +
          `<div style="text-align:right"><div class="pos-pct mono">${st.avg_pct !== null ? st.avg_pct.toFixed(0) : "&mdash;"}<span class="unit">%</span></div></div></div>` +
          `<div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, pct)}%"></div></div>`;
      }).join("");
    }
    function buildCurveKey() {
      document.getElementById("curveKey").innerHTML = POLAR.curves.map(c => `
        <div class="row"><span class="sw" style="background:${CURVE_COLORS[c.tws]}"></span>
          <div><div class="mono">${c.tws} kn TWS target</div>
          <div class="details">beat ${c.beat_angle}&deg; (${c.beat_vmg} kn VMG) &middot; run ${c.run_angle}&deg; (${c.run_vmg} kn VMG)</div></div>
        </div>`).join("");
    }
    function toXY(twa, radius, side, originX, originY, scale) {
      const rad = twa * Math.PI / 180;
      return [originX + side * radius * Math.sin(rad) * scale, originY - radius * Math.cos(rad) * scale];
    }
    function drawChart() {
      const rect = chartWrap.getBoundingClientRect();
      const W = Math.max(360, rect.width), H = Math.max(420, rect.height);
      const maxSpeed = Math.max(...POLAR.curves.flatMap(c => c.points.map(p => p[1])), ...POLAR.points.map(p => p[2])) * 1.08;
      const originX = W / 2, originY = H * 0.5;
      const usable = Math.min(W / 2, H * 0.46);
      const scale = usable / maxSpeed;
      chart.setAttribute("viewBox", `0 0 ${W} ${H}`);
      chart.innerHTML = "";

      const ringStep = maxSpeed > 10 ? 2 : 1;
      const ringGroup = document.createElementNS(svgNS, "g");
      for (let r = ringStep; r <= maxSpeed; r += ringStep) {
        const path = document.createElementNS(svgNS, "path");
        const [x0, y0] = toXY(0, r, -1, originX, originY, scale);
        const [x180, y180] = toXY(180, r, -1, originX, originY, scale);
        path.setAttribute("d", `M ${x0} ${y0} A ${r*scale} ${r*scale} 0 0 0 ${x180} ${y180} A ${r*scale} ${r*scale} 0 0 0 ${x0} ${y0}`);
        path.setAttribute("fill", "none"); path.setAttribute("stroke", "var(--grid)"); path.setAttribute("stroke-width", "1");
        ringGroup.appendChild(path);
        const label = document.createElementNS(svgNS, "text");
        label.setAttribute("x", originX + 4); label.setAttribute("y", originY - r * scale - 2);
        label.setAttribute("fill", "var(--dim)"); label.setAttribute("font-size", "9.5");
        label.textContent = r + "kn";
        ringGroup.appendChild(label);
      }
      chart.appendChild(ringGroup);

      const spokeGroup = document.createElementNS(svgNS, "g");
      for (let twa = 0; twa <= 180; twa += 30) {
        [-1, 1].forEach(side => {
          const [x, y] = toXY(twa, maxSpeed, side, originX, originY, scale);
          const line = document.createElementNS(svgNS, "line");
          line.setAttribute("x1", originX); line.setAttribute("y1", originY);
          line.setAttribute("x2", x); line.setAttribute("y2", y);
          line.setAttribute("stroke", "var(--grid)"); line.setAttribute("stroke-width", twa % 90 === 0 ? "1.4" : "1");
          spokeGroup.appendChild(line);
        });
        const [lx, ly] = toXY(twa, maxSpeed * 1.05, 1, originX, originY, scale);
        const lbl = document.createElementNS(svgNS, "text");
        lbl.setAttribute("x", lx); lbl.setAttribute("y", ly);
        lbl.setAttribute("fill", "var(--dim-2)"); lbl.setAttribute("font-size", "10"); lbl.setAttribute("text-anchor", "middle");
        lbl.textContent = twa + "°";
        spokeGroup.appendChild(lbl);
      }
      chart.appendChild(spokeGroup);

      POLAR.curves.forEach(c => {
        [-1, 1].forEach(side => {
          const d = c.points.map((p, i) => {
            const [x, y] = toXY(p[0], p[1], side, originX, originY, scale);
            return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
          }).join(" ");
          const path = document.createElementNS(svgNS, "path");
          path.setAttribute("d", d); path.setAttribute("fill", "none");
          path.setAttribute("stroke", CURVE_COLORS[c.tws]); path.setAttribute("stroke-width", "2"); path.setAttribute("opacity", "0.85");
          chart.appendChild(path);
        });
      });

      const ptGroup = document.createElementNS(svgNS, "g");
      POLAR.points.forEach(p => {
        const [twa, tws, stw, pct, tackSide] = p;
        const side = tackSide === "s" ? 1 : -1;
        const [x, y] = toXY(Math.abs(twa), stw, side, originX, originY, scale);
        const c = document.createElementNS(svgNS, "circle");
        c.setAttribute("cx", x); c.setAttribute("cy", y); c.setAttribute("r", "2");
        c.setAttribute("fill", side === 1 ? "var(--starboard)" : "var(--port)"); c.setAttribute("opacity", "0.45");
        c.addEventListener("mouseenter", (ev) => showTooltip(ev, p));
        c.addEventListener("mouseleave", hideTooltip);
        ptGroup.appendChild(c);
      });
      chart.appendChild(ptGroup);

      const originDot = document.createElementNS(svgNS, "circle");
      originDot.setAttribute("cx", originX); originDot.setAttribute("cy", originY);
      originDot.setAttribute("r", "2.5"); originDot.setAttribute("fill", "var(--paper)");
      chart.appendChild(originDot);
    }
    function showTooltip(ev, p) {
      const [twa, tws, stw, pct, tackSide, pointOfSail, oor] = p;
      const wrapRect = chartWrap.getBoundingClientRect();
      tooltip.innerHTML = `<div class="t-title">${tackSide === "s" ? "Starboard" : "Port"} tack</div>` +
        `TWA ${Math.abs(twa).toFixed(0)}&deg; &middot; TWS ${tws.toFixed(1)} kn<br>` +
        `STW ${stw.toFixed(2)} kn ${pct !== null ? `(${pct.toFixed(0)}% of target)` : ""}` +
        (oor ? `<br><span style="color:var(--mark)">outside tabulated polar range</span>` : "");
      tooltip.classList.add("show");
      tooltip.style.left = (ev.clientX - wrapRect.left + 14) + "px";
      tooltip.style.top = (ev.clientY - wrapRect.top + 14) + "px";
    }
    function hideTooltip() { tooltip.classList.remove("show"); }

    buildLegend(); buildPosStats(); buildCurveKey(); drawChart();
    window.addEventListener("resize", drawChart);
  })();

  buildMeta();
})();
</script>
"""


def _coach_markdown_to_html(text):
    """Minimal markdown -> HTML: headers, bullet/numbered lists, bold, paragraphs.
    Good enough for the coach report's fixed structure; not a general renderer."""
    lines = text.strip("\n").split("\n")
    out = []
    list_stack = []  # tags of currently-open <ul>/<ol>

    def close_lists():
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    def inline(s):
        s = html_mod.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", s)
        return s

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_lists()
            continue
        h = re.match(r"^(#{1,4})\s+(.*)$", line)
        if h:
            close_lists()
            level = {1: "h3", 2: "h3", 3: "h4", 4: "h4"}[len(h.group(1))]
            out.append(f"<{level}>{inline(h.group(2))}</{level}>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if not list_stack or list_stack[-1] != "ul":
                close_lists()
                list_stack.append("ul")
                out.append("<ul>")
            out.append(f"<li>{inline(m.group(1))}</li>")
            continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if m:
            if not list_stack or list_stack[-1] != "ol":
                close_lists()
                list_stack.append("ol")
                out.append("<ol>")
            out.append(f"<li>{inline(m.group(1))}</li>")
            continue
        close_lists()
        out.append(f"<p>{inline(line.strip())}</p>")

    close_lists()
    return "\n".join(out)


_DAY_PREFIX_RE = re.compile(r"^(-?)0:(\d+:\d+:\d+)$")


def _short_time(s):
    """'0:01:29:57' -> '1:29:57', '-0:00:01:15' -> '-0:01:15'; passes
    non-matching strings (e.g. 'DNC - 12') through unchanged."""
    m = _DAY_PREFIX_RE.match(s or "")
    return f"{m.group(1)}{m.group(2)}" if m else s


_US_CLASS = ' class="us"'


def _fleet_comparison_html(comparison):
    """Builds the Fleet Comparison section's inner HTML from
    fleet_comparison.compute()'s result, or '' if the race has no fleet
    data (the section is simply omitted for every other race)."""
    if comparison is None:
        return ""

    target = comparison["target_name"]

    rows = []
    for r in comparison["fleet_results"]:
        is_us = r.get("boat_name") == target
        rows.append(
            f"<tr{_US_CLASS if is_us else ''}>"
            f"<td class='mono'>{r.get('rank', '')}</td>"
            f"<td class='mono'>{html_mod.escape(r.get('sail_number') or '—')}</td>"
            f"<td>{html_mod.escape(r.get('boat_name') or '—')}</td>"
            f"<td>{html_mod.escape(r.get('boat_type') or '—')}</td>"
            f"<td>{html_mod.escape(r.get('skipper') or '—')}</td>"
            f"<td class='mono'>{r.get('handicap', '')}</td>"
            f"<td class='mono'>{html_mod.escape(_short_time(r.get('elapsed_time', '')))}</td>"
            f"<td class='mono'>{html_mod.escape(_short_time(r.get('corrected_time', '')))}</td>"
            f"<td class='mono'>{html_mod.escape(_short_time(r.get('delta', '')))}</td>"
            f"<td class='mono'>{html_mod.escape(r.get('finish_time') or '—')}</td>"
            f"</tr>"
        )
    fleet_table = (
        "<table class='fleet-table'><thead><tr>"
        "<th>Pos</th><th>Sail</th><th>Boat</th><th>Type</th><th>Skipper</th>"
        "<th>HCap</th><th class='mono'>Elapsed</th><th class='mono'>Corrected</th>"
        "<th class='mono'>Delta</th><th>Finish</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )

    loss_rows = []
    for typ in comparison["loss_order"]:
        b = comparison["losses"][typ]
        label = fleet_comparison.TYPE_LABELS.get(typ, typ)
        loss_rows.append(
            f"<tr><td>{label}</td><td class='mono'>{b['n']}</td>"
            f"<td class='mono'>{b['total_s']:.1f}s</td><td class='mono'>{b['avg_s']:.1f}s</td></tr>"
        )
    loss_table = (
        "<table class='fleet-table'><thead><tr><th>Mistake type</th><th>Count</th>"
        "<th class='mono'>Total lost</th><th class='mono'>Avg / event</th></tr></thead>"
        f"<tbody>{''.join(loss_rows)}"
        f"<tr><td><strong>Total</strong></td><td class='mono'></td>"
        f"<td class='mono'><strong>{comparison['total_lost_s']:.1f}s</strong></td><td class='mono'></td></tr>"
        "</tbody></table>"
    )

    tier_rows = []
    for t in comparison["tiers"]:
        gap = f"{t['gap_to_next_s']:.0f}s behind {t['next_boat']}" if t["gap_to_next_s"] is not None else "in the lead"
        tier_rows.append(
            f"<tr><td>{html_mod.escape(t['label'])}</td>"
            f"<td class='mono'>{fleet_comparison.format_hms(t['elapsed_s'])}</td>"
            f"<td class='mono'>{fleet_comparison.format_hms(t['corrected_s'])}</td>"
            f"<td class='mono'>{t['rank']} / {comparison['n_finishers']}</td>"
            f"<td>{html_mod.escape(gap)}</td></tr>"
        )
    tier_table = (
        "<table class='fleet-table'><thead><tr><th>Scenario</th>"
        "<th class='mono'>Elapsed</th><th class='mono'>Corrected</th><th>Rank</th><th>Gap</th></tr></thead>"
        f"<tbody>{''.join(tier_rows)}</tbody></table>"
    )

    final_tier = comparison["tiers"][-1]
    if comparison["boats_beaten"]:
        beaten = ", ".join(comparison["boats_beaten"])
        summary = (
            f"<p>Sailing every tack, gybe, and rounding turn with zero loss (an estimated "
            f"{comparison['total_lost_s']:.0f}s of the {target}'s own detected losses) would have "
            f"moved {target} from {comparison['actual_rank']}th to {final_tier['rank']}th of "
            f"{comparison['n_finishers']}, ahead of {beaten}.</p>"
        )
    else:
        gap = final_tier["gap_to_next_s"]
        next_boat = final_tier["next_boat"]
        summary = (
            f"<p>Removing all {comparison['total_lost_s']:.0f}s of detected tack/gybe/rounding losses "
            f"still leaves {target} {final_tier['rank']}th of {comparison['n_finishers']} — the gap to "
            f"{next_boat} narrows from {comparison['tiers'][0]['gap_to_next_s']:.0f}s to {gap:.0f}s, but "
            f"no boat was actually within reach today. No fabricated placements here — the numbers just "
            f"don't stretch that far.</p>"
        )

    return f"""
<section id="fleet-section">
  <div class="section-head"><span class="section-title">Fleet Comparison</span></div>
  <div class="fleet-table-wrap">{fleet_table}</div>
  <div class="fleet-subhead">Mistakes by type</div>
  <div class="fleet-table-wrap">{loss_table}</div>
  <div class="fleet-subhead">Progression if mistakes had not been made</div>
  <div class="fleet-table-wrap">{tier_table}</div>
  <div class="fleet-summary">{summary}</div>
</section>
"""


def render_race_page(conn, polar, race_meta):
    sid = race_meta["id"]
    course = export_course(conn, sid)
    polar_data = export_polar(conn, polar, sid)
    if course is None:
        return None

    if polar_data is None:
        polar_data = {"session_id": sid, "race_date": race_meta["race_date"],
                      "local_start_time": race_meta["local_start_time"],
                      "points": [], "curves": [],
                      "stats": {"beat": {"n": 0, "avg_pct": None},
                                "reach": {"n": 0, "avg_pct": None},
                                "run": {"n": 0, "avg_pct": None}}}

    title = f"{race_meta['race_date']} {race_meta['series']}"
    meta = {"id": race_meta["id"], "trim_end_utc": race_meta.get("trim_end_utc")}

    fleet_section_html = _fleet_comparison_html(fleet_comparison.compute(conn, race_meta))

    html = (PAGE_TEMPLATE
            .replace("__TITLE__", title)
            .replace("__SERIES__", race_meta["series"])
            .replace("__BOAT__", race_meta.get("boat", "Critical Mass"))
            .replace("__RACE_META__", json.dumps(meta))
            .replace("__COURSE_DATA__", json.dumps(course, separators=(",", ":")))
            .replace("__POLAR_DATA__", json.dumps(polar_data, separators=(",", ":")))
            .replace("__FLEET_COMPARISON_SECTION__", fleet_section_html))
    return html


def render_all():
    from race_registry import load_registry
    polar = PolarTable(POLAR_PATH)
    conn = sqlite3.connect(DB_PATH)
    registry = load_registry()

    RACES_DIR.mkdir(exist_ok=True)
    written = []
    for race in registry["races"]:
        html = render_race_page(conn, polar, race)
        if html is None:
            print(f"# WARNING: race {race['id']} ({race['race_date']}) has no data yet, skipping page")
            continue
        out_path = RACES_DIR / f"{race['id']}.html"
        out_path.write_text(html)
        written.append(race["id"])
        print(f"# Wrote {out_path} ({out_path.stat().st_size/1024:.0f} KB)")

    conn.close()
    return written


def render_one(race_id):
    """Regenerates a single race's page (used by the save-trim flow)."""
    from race_registry import load_registry
    matches = [r for r in load_registry()["races"] if r["id"] == race_id]
    if not matches:
        raise ValueError(f"race {race_id} not in registry")
    polar = PolarTable(POLAR_PATH)
    conn = sqlite3.connect(DB_PATH)
    html = render_race_page(conn, polar, matches[0])
    conn.close()
    if html is None:
        raise ValueError(f"race {race_id} has no data")
    out_path = RACES_DIR / f"{race_id}.html"
    out_path.write_text(html)
    print(f"# Wrote {out_path} ({out_path.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    render_all()
