#!/usr/bin/env python3
"""Generates the static homepage (index.html): a narrow left nav column
(Update EBL / Benchmark / Update HTML / Add Race) and a main content area
listing every processed race, grouped by year (newest year first), each
link showing its date + series and pointing at races/<id>.html."""
import html
from pathlib import Path

from race_registry import load_registry

ROOT = Path(__file__).parent
OUT_PATH = ROOT / "index.html"

# True when this instance has no local working data (ebl_data/) -- e.g. a
# view-only deployment from the pushed Docker image, which ships the static
# race pages but not the raw EBL logs or database needed to add/rebuild races.
READ_ONLY = not (ROOT / "ebl_data").exists()

_NAV_LIVE = (
    '<a class="nav-btn" href="/add-race">Add Race<span class="hint">New race from logged data</span></a>'
    '<a class="nav-btn" href="/update-ebl">Update EBL<span class="hint">Upload new .ebl files</span></a>'
    '<form class="nav-form" method="post" action="/update-html">'
    '<button type="submit" class="nav-btn">Update HTML<span class="hint">Rebuild all race pages</span></button>'
    '</form>'
)
_NAV_READ_ONLY = (
    '<span class="nav-btn disabled">Add Race<span class="hint">View-only deployment &mdash; edit locally</span></span>'
    '<span class="nav-btn disabled">Update EBL<span class="hint">View-only deployment &mdash; edit locally</span></span>'
    '<span class="nav-btn disabled">Update HTML<span class="hint">View-only deployment &mdash; edit locally</span></span>'
)

GITHUB_URL = "https://github.com/lindsaymcrory/Critical_Mass_Racing"
DOCKERHUB_URL = "https://hub.docker.com/r/lmcrory/critical_mass_racing"

ABOUT_HTML = f"""
<h2>About Critical Mass Racing</h2>
<p>Critical Mass Racing is an open-source, AI-assisted race-analysis platform developed for our J/80 sailing program.</p>
<ul class="about-meta">
  <li><strong>Author</strong> &mdash; Lindsay McRory</li>
  <li><strong>Contact</strong> &mdash; <a href="mailto:Lindsay.McRory@gmail.com">Lindsay.McRory@gmail.com</a></li>
  <li><strong>Licence</strong> &mdash; Apache License 2.0</li>
  <li><strong>Source code</strong> &mdash; <a href="{GITHUB_URL}" target="_blank" rel="noopener">{GITHUB_URL}</a></li>
  <li><strong>Docker image</strong> &mdash; <a href="{DOCKERHUB_URL}" target="_blank" rel="noopener">{DOCKERHUB_URL}</a></li>
</ul>
<p>The software may be used, modified, and distributed under the terms of the Apache License 2.0. See the LICENSE file in the GitHub repository for the complete licence terms.</p>

<h3>About Critical Mass</h3>
<p>Critical Mass is a J/80 raced in one-design configuration. We are weeknight &ldquo;beer can&rdquo; racers who want to better understand where we make gains, where we lose time, and where the biggest performance gaps lie.</p>
<p>This project turns our onboard instrument data into practical post-race coaching. It is designed specifically for a J/80 and tailored to the instruments installed on Critical Mass. It is not intended to replace crew judgment, tactical discussion, or time on the water. Its purpose is to give those conversations a reliable baseline.</p>

<h3>Onboard instruments</h3>
<p>Our data-logging system includes:</p>
<ul>
  <li><strong>Speed and depth</strong> &mdash; B&amp;G DST810</li>
  <li><strong>Wind</strong> &mdash; B&amp;G WS310</li>
  <li><strong>GPS and compass</strong> &mdash; B&amp;G ZG100</li>
  <li><strong>Data recorder and gateway</strong> &mdash; Actisense W2K-1</li>
  <li><strong>Additional race data</strong> &mdash; Velocitek ProStart and Vakaros instruments</li>
</ul>
<p>The system records available instrument data throughout each race, creating a second-by-second account of the boat&rsquo;s speed, heading, wind conditions, position, heel, and other measurements.</p>

<h3>What the analysis does</h3>
<p>Post-race analysis turns a gut feeling about &ldquo;how we sailed&rdquo; into evidence. Each race is divided into three main areas: maneuvers, boat performance, and strategy.</p>

<h4>Maneuvers</h4>
<p>Every tack and gybe is measured for speed loss, duration, consistency, and recovery time.</p>
<p>Instead of remembering that &ldquo;one tack felt slow,&rdquo; we can see that it lost 45% of the boat&rsquo;s speed and took 18 seconds to recover, while the best tack that evening lost only 9% and recovered in six seconds.</p>
<p>Patterns emerge quickly:</p>
<ul>
  <li>Which maneuvers cost the most time</li>
  <li>Whether entry and exit angles are consistent</li>
  <li>How quickly the boat accelerates after each maneuver</li>
  <li>Whether performance changes as the race progresses</li>
  <li>Which techniques appear in our best maneuvers</li>
  <li>Which specific skills are worth practising</li>
</ul>
<p>Mark roundings can also be reviewed to understand approach angles, speed through the rounding, distance from the mark, and acceleration onto the next leg.</p>

<h4>Boat performance and polars</h4>
<p>Actual boat speed, sailing angle, and velocity made good are compared with the J/80&rsquo;s predicted performance for the wind conditions.</p>
<p>This helps answer questions such as:</p>
<ul>
  <li>Were we sailing close to the boat&rsquo;s target speed?</li>
  <li>Were we pointing too high and sacrificing speed?</li>
  <li>Were we sailing too low and giving away height?</li>
  <li>Was the performance gap caused by speed, angle, or both?</li>
  <li>Did excessive heel, steering activity, or inconsistent trim contribute?</li>
  <li>Were we overpowered or underpowered for the conditions?</li>
</ul>
<p>The comparison helps separate equipment, trim, steering, and execution issues from changes caused by wind strength or direction.</p>
<p>Polar predictions are a reference, not an unquestionable standard. Their usefulness depends on the quality of the polar data, instrument calibration, sea state, crew weight, current, and local conditions.</p>

<h4>Strategy</h4>
<p>The boat&rsquo;s actual track is plotted against the recorded course marks, showing the course we sailed rather than the course we remember sailing.</p>
<p>The analysis can examine:</p>
<ul>
  <li>Which side of each leg we selected</li>
  <li>Whether that side gained or lost distance</li>
  <li>How wind shifts affected each tack or gybe</li>
  <li>Distance sailed compared with the most direct course</li>
  <li>Layline positioning and overstanding</li>
  <li>Approaches to and exits from mark roundings</li>
  <li>Where gains and losses occurred during each leg</li>
</ul>
<p>Instrument data cannot always explain why a tactical decision was made. Other boats, bad air, traffic, waves, and visual observations may not appear in the data. The analysis therefore identifies outcomes and likely explanations without pretending to know everything that happened on the water.</p>

<h3>Comparing races</h3>
<p>The value of the system increases as more races are recorded.</p>
<p>Individual maneuvers and sailing segments can be compared with previous races in similar wind conditions. This gives us a team-specific baseline based on how Critical Mass has actually performed &mdash; not only on a theoretical target.</p>
<p>Cross-race analysis can show:</p>
<ul>
  <li>Whether our tacks and gybes are becoming faster and more consistent</li>
  <li>Which wind ranges create the largest performance gaps</li>
  <li>Whether we are improving against our polar targets</li>
  <li>Which recurring trim or handling patterns are associated with better speed</li>
  <li>Whether certain tactical choices repeatedly produce gains or losses</li>
  <li>Which areas offer the greatest opportunity for improvement</li>
</ul>
<p>Over time, every tack, gybe, rounding, and leg becomes part of the team&rsquo;s performance history.</p>

<h3>AI-assisted coaching</h3>
<p>The system uses specialized AI agents for two types of analysis:</p>
<ul>
  <li><strong>Race analysis</strong> &mdash; reviews one race and produces a concise post-race coaching report.</li>
  <li><strong>Comparative analysis</strong> &mdash; compares the race with previous races and maneuvers sailed in similar conditions.</li>
</ul>
<p>The AI is instructed to support conclusions with data, distinguish observations from likely explanations, and clearly identify when the available information is insufficient.</p>
<p>Its recommendations are starting points for crew discussion, not absolute conclusions. Sensor errors, calibration problems, incomplete course information, current, sea state, traffic, and tactical context can all affect the results.</p>

<h3>The goal</h3>
<p>The goal is to establish a useful baseline for what went well and where we can improve at three levels:</p>
<ul>
  <li>How well we executed our tacks, gybes, and roundings</li>
  <li>Whether we sailed to our target polars</li>
  <li>Whether we chose the right or wrong side of the course</li>
</ul>
<p>Put together, these views turn each race into a data point instead of just a memory. With enough races, we can begin to distinguish between nights that were fast because of favourable conditions and nights that were fast because of better technique.</p>
<p>That distinction is what makes the information coachable &mdash; and gives us something specific to work on the next time we leave the dock.</p>

<img class="about-instruments-img" src="CM_Instruments.png" alt="Critical Mass instrument diagram">
"""

PAGE_TEMPLATE = """<title>Critical Mass Racing</title>
<style>
  :root {
    --ink: #0a1a20; --panel: #122a32; --panel-2: #0e222a;
    --grid: #1f3e48; --hair: #24444f; --paper: #e7ede9;
    --dim: #7fa3ab; --dim-2: #547881;
    --starboard: #3fbf7f; --port: #ef5a4c; --mark: #f5b942;
    --radius: 4px;
  }
  :root[data-theme="light"] {
    --ink: #eef3f1; --panel: #ffffff; --panel-2: #f4f8f7;
    --grid: #d7e2df; --hair: #d2ddda; --paper: #10262c;
    --dim: #4c6b71; --dim-2: #7d9ba1;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; background: var(--ink); color: var(--paper); min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .mono { font-family: ui-monospace, "SF Mono", "Cascadia Mono", "Roboto Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
  .label { text-transform: uppercase; letter-spacing: 0.09em; font-size: 11px; color: var(--dim); font-weight: 600; }
  a { color: inherit; text-decoration: none; }

  .layout { display: grid; grid-template-columns: 210px 1fr; min-height: 100vh; }
  @media (max-width: 720px) { .layout { grid-template-columns: 1fr; } }

  nav {
    background: var(--panel-2); border-right: 1px solid var(--hair);
    display: flex; flex-direction: column; padding: 22px 16px; gap: 8px;
    position: sticky; top: 0; height: 100vh; overflow-y: auto;
  }
  .nav-brand { font-size: 14px; font-weight: 700; letter-spacing: 0.02em; margin-bottom: 6px; padding: 0 4px; }
  .nav-brand .sub { display: block; font-size: 10.5px; font-weight: 500; color: var(--dim); margin-top: 2px; text-transform: none; letter-spacing: normal; }
  .nav-form { margin: 0; }
  .nav-btn {
    display: flex; flex-direction: column; gap: 2px; width: 100%;
    padding: 10px 12px; border-radius: var(--radius); border: 1px solid var(--hair);
    background: var(--panel); color: var(--paper); font: inherit; font-size: 12.5px;
    font-weight: 700; letter-spacing: 0.02em; text-align: left;
    cursor: pointer; transition: border-color .12s, background .12s;
  }
  .nav-btn:hover { border-color: var(--mark); }
  .nav-btn .hint { font-size: 10px; font-weight: 500; color: var(--dim); text-transform: none; letter-spacing: normal; }
  .nav-btn.primary { background: var(--mark); color: #201404; border-color: var(--mark); }
  .nav-btn.primary .hint { color: #4a3410; }
  .nav-btn.primary:hover { filter: brightness(1.05); }
  .nav-btn.disabled { cursor: default; opacity: 0.5; }
  .nav-btn.disabled:hover { border-color: var(--hair); }

  main { background-color: var(--ink); }
  .content { padding: 32px 40px 60px; max-width: 980px; margin: 0 auto; }

  /* the jacket graphic is a wide banner (2666x644) -- show it at its natural
     proportions as a header, rather than smearing it across the page bg */
  .banner {
    border: 1px solid var(--hair); border-radius: var(--radius); overflow: hidden;
    margin: 0 auto 28px; background: #10182b; width: 70%;
  }
  .banner img { display: block; width: 100%; height: auto; }

  .tagline {
    text-align: center; font-size: 14px; font-style: italic; color: var(--dim);
    margin: 0 0 28px;
  }

  .flash {
    padding: 12px 16px; border-radius: var(--radius); margin-bottom: 22px;
    font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 10px;
  }
  .flash.success { background: rgba(63, 191, 127, 0.14); border: 1px solid var(--starboard); color: var(--starboard); }
  .flash.error { background: rgba(239, 90, 76, 0.14); border: 1px solid var(--port); color: var(--port); }

  .page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; }
  .page-sub { font-size: 12.5px; color: var(--dim); margin: 0 0 28px; }

  .year-box {
    border: 1px solid var(--hair); border-radius: var(--radius); background: rgba(18, 42, 50, 0.55);
    backdrop-filter: blur(2px); margin-bottom: 18px; overflow: hidden;
  }
  :root[data-theme="light"] .year-box { background: rgba(255,255,255,0.72); }
  .year-head {
    padding: 14px 18px; font-size: 22px; font-weight: 700; letter-spacing: 0.01em;
    border-bottom: 1px solid var(--hair);
    background: rgba(14, 34, 42, 0.5);
  }
  :root[data-theme="light"] .year-head { background: rgba(244,248,247,0.7); }
  .race-row {
    display: grid; grid-template-columns: 130px 1fr 130px auto;
    align-items: center; gap: 16px;
    padding: 13px 18px; border-top: 1px solid var(--hair); transition: background .1s;
  }
  .race-row:first-of-type { border-top: none; }
  .race-row:hover { background: rgba(245, 185, 66, 0.08); }
  .race-date { font-size: 14px; font-weight: 700; }
  .race-series { font-size: 11.5px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.06em; }
  .race-notes { font-size: 12px; font-style: italic; color: var(--dim); line-height: 1.4; }
  .race-conditions { font-size: 11.5px; line-height: 1.5; color: var(--dim); white-space: nowrap; }
  .race-conditions .mono { color: var(--paper); }
  .race-go { font-size: 15px; color: var(--mark); font-weight: 700; }

  .empty { padding: 40px 18px; text-align: center; color: var(--dim); font-size: 13px; }

  /* -- About -- */
  .nav-btn.about-btn { font-size: 15px; color: var(--mark); }
  .about-overlay {
    display: none; position: fixed; inset: 0; z-index: 100;
    background: rgba(6, 14, 18, 0.72); backdrop-filter: blur(1px);
    padding: 5vh 20px; overflow-y: auto;
  }
  .about-overlay.open { display: flex; justify-content: center; align-items: flex-start; }
  .about-panel {
    position: relative; width: 100%; max-width: 720px; max-height: 90vh;
    background: var(--panel); border: 1px solid var(--hair); border-radius: 6px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.4);
    display: flex; flex-direction: column; overflow: hidden;
  }
  .about-close {
    position: absolute; top: 12px; right: 12px; z-index: 1;
    width: 32px; height: 32px; border-radius: 50%;
    border: 1px solid var(--hair); background: var(--panel-2); color: var(--paper);
    font-size: 16px; line-height: 1; cursor: pointer; appearance: none;
  }
  .about-close:hover { border-color: var(--mark); color: var(--mark); }
  .about-content {
    overflow-y: auto; padding: 44px 40px 40px;
  }
  .about-content h2 { font-size: 22px; margin: 8px 0 14px; }
  .about-content h3 { font-size: 17px; margin: 28px 0 10px; color: var(--mark); }
  .about-content h4 { font-size: 14px; margin: 18px 0 6px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--dim); }
  .about-content p { font-size: 14px; line-height: 1.65; margin: 0 0 12px; }
  .about-content ul { margin: 0 0 14px; padding-left: 22px; }
  .about-content li { font-size: 14px; line-height: 1.6; margin: 3px 0; }
  .about-content a { color: var(--mark); text-decoration: underline; }
  .about-content strong { color: var(--paper); }
  .about-meta { list-style: none; padding: 0; margin: 0 0 16px; }
  .about-meta li { font-size: 13.5px; }
  .about-instruments-img { display: block; width: 100%; height: auto; margin-top: 24px; border-radius: var(--radius); border: 1px solid var(--hair); }
</style>

<div class="layout">
  <nav>
    <div class="nav-brand">Critical Mass<span class="sub">Race Analysis</span></div>
    __NAV_ITEMS__
    <a class="nav-btn" href="/benchmark">Benchmark<span class="hint">Coming soon</span></a>
    <button type="button" class="nav-btn about-btn" id="aboutBtn">About<span class="hint">Project, boat &amp; instruments</span></button>
  </nav>
  <main>
    <div class="content">
      __FLASH__
      <div class="banner"><img src="Jacket_Front.png" alt="Critical Mass Racing"></div>
      <div class="tagline">Turning every race into data &mdash; maneuvers, strategy, and polar performance measured, not remembered.</div>
      <div class="page-title">Race Results</div>
      <div class="page-sub">__RACE_COUNT__ processed race__PLURAL__</div>
      __YEARS__
    </div>
  </main>
</div>

<div class="about-overlay" id="aboutOverlay">
  <div class="about-panel">
    <button type="button" class="about-close" id="aboutClose" aria-label="Close">&times;</button>
    <div class="about-content">__ABOUT_HTML__</div>
  </div>
</div>

<script>
(function () {
  const btn = document.getElementById("aboutBtn");
  const overlay = document.getElementById("aboutOverlay");
  const closeBtn = document.getElementById("aboutClose");

  function open() { overlay.classList.add("open"); }
  function close() { overlay.classList.remove("open"); }

  btn.addEventListener("click", open);
  closeBtn.addEventListener("click", close);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && overlay.classList.contains("open")) close();
  });
})();
</script>
"""


def _conditions_cell(r):
    tws, bsp = r.get("tws_range"), r.get("bsp_range")
    if not tws or not bsp:
        return '<div class="race-conditions">&mdash;</div>'
    return (
        '<div class="race-conditions">'
        f'TWS: <span class="mono">{tws[0]}&ndash;{tws[1]} kn</span><br>'
        f'BSP: <span class="mono">{bsp[0]}&ndash;{bsp[1]} kn</span>'
        '</div>'
    )


def _year_box(year, races):
    rows = "".join(
        f'<a class="race-row" href="{r["html_path"]}">'
        f'<div><div class="race-date mono">{r["race_date"]}</div>'
        f'<div class="race-series">{r["series"]}</div></div>'
        f'<div class="race-notes">{html.escape(r.get("notes") or "")}</div>'
        f'{_conditions_cell(r)}'
        f'<div class="race-go">Results &rarr;</div></a>'
        for r in races
    )
    return f'<div class="year-box"><div class="year-head">{year} Racing Season</div>{rows}</div>'


def render_homepage(flash_message=None, flash_kind="success"):
    registry = load_registry()
    races = sorted(registry["races"], key=lambda r: r["race_date"], reverse=True)

    by_year = {}
    for r in races:
        year = r["race_date"][:4]
        by_year.setdefault(year, []).append(r)

    years_html = "".join(
        _year_box(year, by_year[year]) for year in sorted(by_year, reverse=True)
    ) if by_year else '<div class="empty">No races processed yet -- use Add Race to get started.</div>'

    flash_html = ""
    if flash_message:
        flash_html = f'<div class="flash {flash_kind}">{flash_message}</div>'

    html = (PAGE_TEMPLATE
            .replace("__FLASH__", flash_html)
            .replace("__RACE_COUNT__", str(len(races)))
            .replace("__PLURAL__", "" if len(races) == 1 else "s")
            .replace("__YEARS__", years_html)
            .replace("__NAV_ITEMS__", _NAV_READ_ONLY if READ_ONLY else _NAV_LIVE)
            .replace("__ABOUT_HTML__", ABOUT_HTML))
    return html


def main():
    html = render_homepage()
    OUT_PATH.write_text(html)
    print(f"# Wrote {OUT_PATH} ({OUT_PATH.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
