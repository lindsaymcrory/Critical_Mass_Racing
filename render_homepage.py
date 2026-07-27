#!/usr/bin/env python3
"""Generates the static homepage (index.html): a narrow left nav column
(Update EBL / Benchmark / Update HTML / Add Race) and a main content area
listing every processed race, grouped by year (newest year first), each
link showing its date + series and pointing at races/<id>.html."""
from pathlib import Path

from race_registry import load_registry

ROOT = Path(__file__).parent
OUT_PATH = ROOT / "index.html"

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

  main { background-color: var(--ink); }
  .content { padding: 32px 40px 60px; max-width: 980px; margin: 0 auto; }

  /* the jacket graphic is a wide banner (2666x644) -- show it at its natural
     proportions as a header, rather than smearing it across the page bg */
  .banner {
    border: 1px solid var(--hair); border-radius: var(--radius); overflow: hidden;
    margin: 0 auto 28px; background: #10182b; width: 70%;
  }
  .banner img { display: block; width: 100%; height: auto; }

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
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    padding: 13px 18px; border-top: 1px solid var(--hair); transition: background .1s;
  }
  .race-row:first-of-type { border-top: none; }
  .race-row:hover { background: rgba(245, 185, 66, 0.08); }
  .race-date { font-size: 14px; font-weight: 700; }
  .race-series { font-size: 11.5px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.06em; }
  .race-go { font-size: 11px; color: var(--mark); font-weight: 700; }

  .empty { padding: 40px 18px; text-align: center; color: var(--dim); font-size: 13px; }
</style>

<div class="layout">
  <nav>
    <div class="nav-brand">Critical Mass<span class="sub">Race Analysis</span></div>
    <a class="nav-btn" href="/add-race">Add Race<span class="hint">New race from logged data</span></a>
    <a class="nav-btn" href="/update-ebl">Update EBL<span class="hint">Upload new .ebl files</span></a>
    <form class="nav-form" method="post" action="/update-html">
      <button type="submit" class="nav-btn">Update HTML<span class="hint">Rebuild all race pages</span></button>
    </form>
    <a class="nav-btn" href="/benchmark">Benchmark<span class="hint">Coming soon</span></a>
  </nav>
  <main>
    <div class="content">
      __FLASH__
      <div class="banner"><img src="Jacket_Front.png" alt="Critical Mass Racing"></div>
      <div class="page-title">Race Results</div>
      <div class="page-sub">__RACE_COUNT__ processed race__PLURAL__</div>
      __YEARS__
    </div>
  </main>
</div>
"""


def _year_box(year, races):
    rows = "".join(
        f'<a class="race-row" href="{r["html_path"]}">'
        f'<div><div class="race-date mono">{r["race_date"]}</div>'
        f'<div class="race-series">{r["series"]}</div></div>'
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
            .replace("__YEARS__", years_html))
    return html


def main():
    html = render_homepage()
    OUT_PATH.write_text(html)
    print(f"# Wrote {OUT_PATH} ({OUT_PATH.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
