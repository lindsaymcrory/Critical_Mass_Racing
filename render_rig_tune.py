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

"""Renders the Rig Tune page: the Boat Setup Log table (rig tune settings,
mast rake/pre-bend, sail changes, bottom cleaning -- anything that may
affect boat speed). Reads boat_setup_log.json (hand-edited directly, like
season_summary.md), so this page never needs a live database connection --
consistent with the app's READ_ONLY view-only deployment mode. Split out
from what is now the Hull Analysis page (formerly Boat Check), which keeps
the season-wide performance charts."""
import html as html_mod
import json
from pathlib import Path

ROOT = Path(__file__).parent
LOG_PATH = ROOT / "boat_setup_log.json"

PAGE_TEMPLATE = """<title>Rig Tune — Critical Mass Racing</title>
<style>
  :root {
    --ink: #0a1a20; --panel: #122a32; --panel-2: #0e222a;
    --grid: #1f3e48; --grid-strong: #2a4e59; --paper: #e7ede9;
    --dim: #7fa3ab; --dim-2: #547881;
    --mark: #f5b942;
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

  section { border-bottom: none; padding-bottom: 8px; }
  .section-head { padding: 20px 24px 4px; }
  .section-title { font-size: 14.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }
  .section-sub { font-size: 14px; color: var(--dim); margin-top: 4px; }

  .log-table-wrap { margin: 4px 24px 24px; border: 1px solid var(--hair); border-radius: var(--radius); overflow: hidden; }
  table.log-table { width: 100%; border-collapse: collapse; font-size: 14px; }
  table.log-table th, table.log-table td { padding: 9px 14px; text-align: left; border-top: 1px solid var(--hair); }
  table.log-table th { text-transform: uppercase; letter-spacing: 0.06em; font-size: 12px; color: var(--dim); background: var(--panel-2); border-top: none; }
  table.log-table tr:first-child td { border-top: none; }
  table.log-table td.values { font-family: ui-monospace, "SF Mono", "Cascadia Mono", monospace; }

  footer { padding: 12px 24px; background: var(--panel-2); font-size: 12px; color: var(--dim-2); }
  ::-webkit-scrollbar { width: 9px; height: 9px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--hair); border-radius: 5px; }
</style>

<header>
  <a class="back" href="/">&larr; All races</a>
  <div class="brand">
    <div class="title">Rig Tune</div>
    <div class="sub">Tuning &amp; Maintenance Log</div>
  </div>
</header>

<p class="intro">Rig tune settings, mast rake/pre-bend, sail changes, and bottom cleaning &mdash; hand-logged events that may affect boat speed.</p>

<section id="log-section">
  <div class="section-head">
    <span class="section-title">Boat Setup Log</span>
    <div class="section-sub">Tuning and maintenance events that may affect boat speed.</div>
  </div>
  <div class="log-table-wrap">
    <table class="log-table">
      <thead><tr><th>Date</th><th>Label</th><th>Values</th></tr></thead>
      <tbody>__LOG_ROWS__</tbody>
    </table>
  </div>
</section>
"""


def _log_rows_html(entries):
    rows = []
    for e in sorted(entries, key=lambda e: e["date"], reverse=True):
        values = ", ".join(str(v) for v in e["values"])
        rows.append(
            f"<tr><td class='mono'>{html_mod.escape(e['date'])}</td>"
            f"<td>{html_mod.escape(e['label'])}</td>"
            f"<td class='values'>{html_mod.escape(values)}</td></tr>"
        )
    return "\n".join(rows) if rows else "<tr><td colspan='3'>No entries yet.</td></tr>"


def render_page():
    log = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else {"entries": []}
    return PAGE_TEMPLATE.replace("__LOG_ROWS__", _log_rows_html(log["entries"]))


if __name__ == "__main__":
    print(render_page()[:2000])
