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

"""Local web app for the Critical Mass race-analysis site: serves the
homepage, static race pages, Rig Tune, Hull Analysis, and Videos, plus the
remaining server-side Add Race flow (unlinked but still functional).
Update EBL / Update HTML were removed: race data is now added and rebuilt
via Claude Code sessions instead of the web UI."""
import os
import traceback
from pathlib import Path

from flask import Flask, request, redirect, send_from_directory, abort

import build_race_db
import detect_maneuvers
import polar_analysis
import render_homepage
import render_hull_analysis
import render_race_page
import render_rig_tune
import render_videos
from ebl_store import list_files_with_ranges
from race_registry import add_race, load_registry, save_registry

ROOT = Path(__file__).parent
RACES_DIR = ROOT / "races"
VAKAROS_DIR = ROOT / "vakaros"
VIDEOS_DIR = ROOT / "Videos"

app = Flask(__name__)
app.secret_key = "critical-mass-local-dev"  # local personal tool, no auth/session sensitivity

_pending_flash = {"message": None, "kind": "success"}

# In-memory homepage view counter -- deliberately not persisted to disk, so
# it resets to 0 whenever the process restarts (a new release/deploy, or a
# local `docker compose up --force-recreate`), per the "resets each release"
# requirement -- no separate reset step needed.
_view_count = 0


def set_flash(message, kind="success"):
    _pending_flash["message"] = message
    _pending_flash["kind"] = kind


def pop_flash():
    m, k = _pending_flash["message"], _pending_flash["kind"]
    _pending_flash["message"] = None
    return m, k


def _blocked_if_read_only():
    """Returns a response if this instance has no local working data (a
    view-only deployment from the pushed Docker image), else None. Routes
    that add/rebuild race data call this first and return early on a hit --
    the nav already hides these actions, but this guards direct URL access
    from a raw 500 (missing race_sessions.db / ebl_data/)."""
    if not render_homepage.READ_ONLY:
        return None
    if request.method == "POST":
        set_flash("This is a view-only deployment -- race data is added and rebuilt locally.", "error")
        return redirect("/")
    body = (
        "<a class='back' href='/'>&larr; Back to races</a>"
        "<h1>View-only deployment</h1>"
        "<p class='sub'>This instance ships the built static site only. "
        "Race data is added and rebuilt locally, then republished.</p>"
    )
    return page("View-only", body)


PAGE_CHROME_CSS = """
<style>
  :root {
    --ink: #0a1a20; --panel: #122a32; --panel-2: #0e222a;
    --grid: #1f3e48; --hair: #24444f; --paper: #e7ede9;
    --dim: #7fa3ab; --dim-2: #547881;
    --starboard: #3fbf7f; --port: #ef5a4c; --mark: #f5b942; --radius: 4px;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; background: var(--ink); color: var(--paper); min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  }
  .mono { font-family: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace; }
  a { color: var(--mark); }
  .wrap { max-width: 640px; margin: 0 auto; padding: 40px 24px; }
  .back { display: inline-block; margin-bottom: 20px; color: var(--dim); text-decoration: none; font-size: 12.5px; }
  .back:hover { color: var(--paper); }
  h1 { font-size: 20px; margin: 0 0 6px; }
  .sub { color: var(--dim); font-size: 13px; margin: 0 0 28px; }
  label { display: block; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.07em; color: var(--dim); font-weight: 600; margin: 18px 0 6px; }
  input[type=text], input[type=date], input[type=time], input[type=file] {
    width: 100%; padding: 10px 12px; background: var(--panel); border: 1px solid var(--hair);
    border-radius: var(--radius); color: var(--paper); font-size: 13.5px; font-family: inherit;
  }
  input:focus { outline: 2px solid var(--mark); outline-offset: -1px; }
  .file-list { border: 1px solid var(--hair); border-radius: var(--radius); max-height: 320px; overflow-y: auto; margin-top: 6px; }
  .file-row { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-top: 1px solid var(--hair); font-size: 12.5px; }
  .file-row:first-child { border-top: none; }
  .file-row .name { font-weight: 600; }
  .file-row .range { color: var(--dim); font-size: 11px; }
  button, .btn {
    appearance: none; border: none; background: var(--mark); color: #201404; font-weight: 700;
    padding: 11px 20px; border-radius: var(--radius); font-size: 13px; cursor: pointer; margin-top: 24px;
  }
  button:hover { filter: brightness(1.05); }
  .empty { color: var(--dim); font-size: 13px; padding: 16px 0; }
  .placeholder { text-align: center; padding: 80px 20px; color: var(--dim); }
</style>
"""


def page(title, body):
    return f"<title>{title}</title>{PAGE_CHROME_CSS}<div class='wrap'>{body}</div>"


@app.route("/")
def home():
    global _view_count
    _view_count += 1
    message, kind = pop_flash()
    return render_homepage.render_homepage(flash_message=message, flash_kind=kind, view_count=_view_count)


@app.route("/index.html")
def home_index_html():
    # the static index.html on disk isn't served directly (it's a snapshot
    # for Update HTML's "recreate static pages" requirement) -- redirect any
    # link/bookmark to the live, flash-aware homepage route instead.
    return redirect("/")


@app.route("/races/<path:filename>")
def race_page(filename):
    if not filename.endswith(".html"):
        abort(404)
    return send_from_directory(RACES_DIR, filename)


@app.route("/vakaros/<path:filename>")
def vakaros_page(filename):
    if not filename.endswith(".html"):
        abort(404)
    return send_from_directory(VAKAROS_DIR, filename)


@app.route("/videos-media/<path:filename>")
def videos_media(filename):
    # Local-only: Videos/ is gitignored/dockerignored (raw + overlaid race
    # footage is too large to ship), so this route only serves anything on
    # a deployed/pushed instance, not the Docker image -- see render_videos.py.
    if not filename.endswith(".mp4"):
        abort(404)
    return send_from_directory(VIDEOS_DIR, filename, conditional=True)


@app.route("/CM_Logo.png")
def logo_image():
    return send_from_directory(ROOT, "CM_Logo.png")


@app.route("/CM_Instruments.png")
def instruments_image():
    return send_from_directory(ROOT, "CM_Instruments.png")


@app.route("/how_it_fits.png")
def how_it_fits_image():
    return send_from_directory(ROOT, "how_it_fits.png")


# ----------------------------------------------------------------- Rig Tune
@app.route("/rig-tune")
def rig_tune():
    return render_rig_tune.render_page()


# ------------------------------------------------------------- Hull Analysis
@app.route("/hull-analysis")
def hull_analysis():
    return render_hull_analysis.render_page()


# ------------------------------------------------------------------ Videos
@app.route("/videos")
def videos():
    return render_videos.render_page()


# ---------------------------------------------------------------- Add Race
@app.route("/add-race", methods=["GET"])
def add_race_form():
    blocked = _blocked_if_read_only()
    if blocked:
        return blocked
    registry = load_registry()
    assigned = {f for r in registry["races"] for f in r["files"]}
    files = [f for f in list_files_with_ranges() if f["filename"] not in assigned]

    if files:
        rows = "".join(
            f"<label class='file-row'><input type='checkbox' name='files' value='{f['filename']}'>"
            f"<span class='name mono'>{f['filename']}</span>"
            f"<span class='range mono'>{f['first_utc'] or '?'} &rarr; {f['last_utc'] or '?'}</span></label>"
            for f in files
        )
        file_picker = f"<div class='file-list'>{rows}</div>"
    else:
        file_picker = "<div class='empty'>No unassigned .ebl files available &mdash; use Update EBL to add some first.</div>"

    body = (
        "<a class='back' href='/'>&larr; Back to races</a>"
        "<h1>Add Race</h1><p class='sub'>Create a new race from already-imported EBL data.</p>"
        "<form method='post'>"
        "<label>Race start date</label><input type='date' name='race_date' required>"
        "<label>Race start time</label><input type='time' name='local_start_time' required value='18:15'>"
        "<label>Series / session name</label><input type='text' name='series' placeholder='WoW' required>"
        "<label>EBL files for this race</label>" + file_picker +
        "<button type='submit'>Create race</button>"
        "</form>"
    )
    return page("Add Race", body)


@app.route("/add-race", methods=["POST"])
def add_race_submit():
    blocked = _blocked_if_read_only()
    if blocked:
        return blocked
    race_date = request.form.get("race_date", "").strip()
    local_start_time = request.form.get("local_start_time", "").strip()
    series = request.form.get("series", "").strip()
    files = request.form.getlist("files")

    if not (race_date and local_start_time and series and files):
        set_flash("Add Race failed: date, time, series, and at least one file are required.", "error")
        return redirect("/add-race")

    try:
        race = add_race(race_date, local_start_time, series, files)
        build_race_db.main()
        detect_maneuvers.main()
        polar_analysis.main()
        render_race_page.render_all()
        render_homepage.main()
    except Exception:
        set_flash(f"Add Race failed: {traceback.format_exc(limit=1).splitlines()[-1]}", "error")
        return redirect("/")

    set_flash(f"Added race {race['race_date']} ({race['series']}).", "success")
    return redirect("/")


if __name__ == "__main__":
    # HOST defaults to 127.0.0.1 for local use; the Docker image sets it to
    # 0.0.0.0 via an env var so the port mapping actually works.
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    debug = os.environ.get("FLASK_DEBUG", "1") not in ("0", "false", "False")
    app.run(host=host, port=port, debug=debug)
