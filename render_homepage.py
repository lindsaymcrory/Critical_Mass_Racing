#!/usr/bin/env python3
"""Generates the static homepage (index.html): a narrow left nav column
(Coach Says / Boat Check / About) and a main content area listing every
processed race, grouped by year (newest year first), each link showing its
date + series and pointing at races/<id>.html. Update EBL / Update HTML were
removed from the nav: race data is now added and rebuilt via Claude Code
sessions instead of the web UI."""
import html
from pathlib import Path

from race_registry import load_registry
from render_race_page import _coach_markdown_to_html

ROOT = Path(__file__).parent
OUT_PATH = ROOT / "index.html"
SEASON_SUMMARY_PATH = ROOT / "season_summary.md"

# True when this instance has no local working data (ebl_data/) -- e.g. a
# view-only deployment from the pushed Docker image, which ships the static
# race pages but not the raw EBL logs or database needed to add/rebuild races.
READ_ONLY = not (ROOT / "ebl_data").exists()

GITHUB_URL = "https://github.com/lindsaymcrory/Critical_Mass_Racing"
DOCKERHUB_URL = "https://hub.docker.com/r/lmcrory/critical_mass_racing"


def _coach_says_html(races):
    """Season-level summary + improvement priorities, written by hand (in a
    Claude session, from querying race_sessions.db across all races) and
    saved to season_summary.md -- re-run that analysis and update the file
    after adding new races, rather than computing it live, so this works the
    same in a view-only deployment with no database."""
    last_race_date = max((r["race_date"] for r in races), default=None)
    heading = (
        f"<h2>Summary as of the last race: {last_race_date}</h2>" if last_race_date
        else "<h2>Summary</h2><p>No races processed yet.</p>"
    )
    body = ""
    if SEASON_SUMMARY_PATH.exists():
        body = _coach_markdown_to_html(SEASON_SUMMARY_PATH.read_text())
    return heading + body

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
<p>Technical details are contained in the <a href="{GITHUB_URL}/blob/main/README.md" target="_blank" rel="noopener">README.md</a> and <a href="{GITHUB_URL}/blob/main/ARCHITECTURE.md" target="_blank" rel="noopener">ARCHITECTURE.md</a> files.</p>

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

<h3>Fitting It All into the J/80</h3>
<p>All electronics are removed from Critical Mass at the end of each season, as we are constantly experimenting with new equipment.</p>
<p>We use custom 3D-printed mounts for the Vakaros instruments and Velocitek ProStart&mdash;thanks, Dwayne! These mounts are necessary because of the location of our Cunningham.</p>
<p>We have also developed several temporary companionway sliding-hatch mounting systems, allowing instruments to be added, removed, and repositioned easily.</p>
<p>The NMEA 2000 bus is zip-tied to the mast, keeping it accessible for maintenance and equipment changes.</p>
<p>The Actisense W2K-1 is mounted for quick removal. It comes home after every race, along with the Vakaros instruments and ProStart, because these devices contain our race data.</p>
<img class="about-instruments-img" src="how_it_fits.png" alt="How the instruments fit into the J/80">
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

  /* -- modal (shared by About and Coach Says) -- */
  .nav-btn.about-btn { font-size: 15px; color: var(--mark); }
  .modal-overlay {
    display: none; position: fixed; inset: 0; z-index: 100;
    background: rgba(6, 14, 18, 0.72); backdrop-filter: blur(1px);
    padding: 5vh 20px; overflow-y: auto;
  }
  .modal-overlay.open { display: flex; justify-content: center; align-items: flex-start; }
  .modal-panel {
    position: relative; width: 100%; max-width: 720px; max-height: 90vh;
    background: var(--panel); border: 1px solid var(--hair); border-radius: 6px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.4);
    display: flex; flex-direction: column; overflow: hidden;
  }
  .modal-close {
    position: absolute; top: 12px; right: 12px; z-index: 1;
    width: 32px; height: 32px; border-radius: 50%;
    border: 1px solid var(--hair); background: var(--panel-2); color: var(--paper);
    font-size: 16px; line-height: 1; cursor: pointer; appearance: none;
  }
  .modal-close:hover { border-color: var(--mark); color: var(--mark); }
  .modal-content {
    overflow-y: auto; padding: 44px 40px 40px;
  }
  .modal-content h2 { font-size: 22px; margin: 8px 0 14px; }
  .modal-content h3 { font-size: 17px; margin: 28px 0 10px; color: var(--mark); }
  .modal-content h4 { font-size: 14px; margin: 18px 0 6px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--dim); }
  .modal-content p { font-size: 14px; line-height: 1.65; margin: 0 0 12px; }
  .modal-content ul, .modal-content ol { margin: 0 0 14px; padding-left: 22px; }
  .modal-content li { font-size: 14px; line-height: 1.6; margin: 3px 0; }
  .modal-content a { color: var(--mark); text-decoration: underline; }
  .modal-content strong { color: var(--paper); }
  .about-meta { list-style: none; padding: 0; margin: 0 0 16px; }
  .about-meta li { font-size: 13.5px; }
  .about-instruments-img { display: block; width: 100%; height: auto; margin-top: 24px; border-radius: var(--radius); border: 1px solid var(--hair); }
</style>

<div class="layout">
  <nav>
    <div class="nav-brand">Critical Mass<span class="sub">Race Analysis</span></div>
    <button type="button" class="nav-btn about-btn" id="coachSaysBtn">Coach Says..<span class="hint">Season summary &amp; priorities</span></button>
    <a class="nav-btn about-btn" href="/boat-check">Boat Check<span class="hint">Speed, Rig &amp; Bottom</span></a>
    <button type="button" class="nav-btn about-btn" id="aboutBtn">About<span class="hint">Project, boat &amp; instruments</span></button>
  </nav>
  <main>
    <div class="content">
      __FLASH__
      <div class="banner"><img src="CM_Logo.png" alt="Critical Mass Racing"></div>
      <div class="tagline">We may not always place well, but we always know why.</div>
      <div class="page-title">Race Results</div>
      <div class="page-sub">__RACE_COUNT__ processed race__PLURAL__ &nbsp;&middot;&nbsp; __VIEW_COUNT__ Views</div>
      __YEARS__
    </div>
  </main>
</div>

<div class="modal-overlay" id="coachSaysOverlay">
  <div class="modal-panel">
    <button type="button" class="modal-close" id="coachSaysClose" aria-label="Close">&times;</button>
    <div class="modal-content">__COACH_SAYS_HTML__</div>
  </div>
</div>

<div class="modal-overlay" id="aboutOverlay">
  <div class="modal-panel">
    <button type="button" class="modal-close" id="aboutClose" aria-label="Close">&times;</button>
    <div class="modal-content">__ABOUT_HTML__</div>
  </div>
</div>

<script>
(function () {
  function wireModal(btnId, overlayId, closeId) {
    const btn = document.getElementById(btnId);
    const overlay = document.getElementById(overlayId);
    const closeBtn = document.getElementById(closeId);

    function open() { overlay.classList.add("open"); }
    function close() { overlay.classList.remove("open"); }

    btn.addEventListener("click", open);
    closeBtn.addEventListener("click", close);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && overlay.classList.contains("open")) close();
    });
  }

  wireModal("coachSaysBtn", "coachSaysOverlay", "coachSaysClose");
  wireModal("aboutBtn", "aboutOverlay", "aboutClose");
})();
</script>
"""


def _conditions_cell(r):
    tws, bsp = r.get("tws_range"), r.get("bsp_range")
    lines = []
    if tws and bsp:
        lines.append(f'TWS: <span class="mono">{tws[0]}&ndash;{tws[1]} kn</span>')
        lines.append(f'BSP: <span class="mono">{bsp[0]}&ndash;{bsp[1]} kn</span>')
    crew_count = r.get("crew_count")
    if crew_count is not None:
        lines.append(f'#Crew: <span class="mono">{crew_count}</span>')
    if not lines:
        return '<div class="race-conditions">&mdash;</div>'
    return f'<div class="race-conditions">{"<br>".join(lines)}</div>'


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


def render_homepage(flash_message=None, flash_kind="success", view_count=0):
    registry = load_registry()
    races = sorted(registry["races"], key=lambda r: r["race_date"], reverse=True)

    by_year = {}
    for r in races:
        year = r["race_date"][:4]
        by_year.setdefault(year, []).append(r)

    years_html = "".join(
        _year_box(year, by_year[year]) for year in sorted(by_year, reverse=True)
    ) if by_year else '<div class="empty">No races processed yet.</div>'

    flash_html = ""
    if flash_message:
        flash_html = f'<div class="flash {flash_kind}">{flash_message}</div>'

    html = (PAGE_TEMPLATE
            .replace("__FLASH__", flash_html)
            .replace("__RACE_COUNT__", str(len(races)))
            .replace("__PLURAL__", "" if len(races) == 1 else "s")
            .replace("__VIEW_COUNT__", str(view_count))
            .replace("__YEARS__", years_html)
            .replace("__ABOUT_HTML__", ABOUT_HTML)
            .replace("__COACH_SAYS_HTML__", _coach_says_html(races)))
    return html


def main():
    html = render_homepage()
    OUT_PATH.write_text(html)
    print(f"# Wrote {OUT_PATH} ({OUT_PATH.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
