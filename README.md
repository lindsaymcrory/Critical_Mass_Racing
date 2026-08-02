# Critical Mass Race Analysis

A self-hosted race-analysis site for a J/80 (or similar) sailboat instrumented
with an Actisense W2K-1 NMEA2000 logger. Decodes the logger's raw `.ebl`
files, reconstructs each race, and publishes a static results page per race
with a course plot, maneuver analysis, and polar-performance comparison
against a target polar table.

No cloud services, no external APIs at runtime -- everything runs locally
against your own logged data.

## What it does

- **Course plot** -- GPS track color-coded by boat speed, overlaid with the
  club's racing marks (labeled by number, with a name legend) and every
  detected tack/gybe/mark-rounding.
- **Maneuver analysis** -- tacks and gybes detected from apparent-wind-side
  changes (with noise/dock-time filtering), each with duration, heading
  change, and speed loss.
- **Polar performance** -- actual boat speed vs. a target polar table
  (`j80_Polars.csv`), plotted as a classic symmetric polar diagram with
  port/starboard tacks in the standard nautical red/green convention.
- **Race management** -- upload new `.ebl` files (deduplicated by content
  hash, not filename), register new races from already-imported files, and
  regenerate every static page from current data on demand.

## Quick start

### Docker (recommended)

```bash
docker compose up
```

Then open **http://localhost:8000**. The whole project directory is
bind-mounted into the container, so the database, imported `.ebl` files, and
generated race pages persist on your host and survive rebuilds.

### Local Python

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Then open **http://localhost:8000**.

Either way, this is Flask's development server -- fine for local/personal
use on your own machine, not meant to be exposed to the internet.

## Using the site

The left nav has three actions:

| Button | What it does |
|---|---|
| **Coach Says..** | Season-level summary and prioritized improvement list. |
| **Boat Check** | Season-wide analysis: port/starboard tack symmetry by wind range, a hull-drag (bottom fouling) trend chart, and the Boat Setup Log (tuning/maintenance history). |
| **About** | Project background, license, and instrument-mounting notes. |

Race pages are grouped by year on the homepage, most recent year first.

Adding races, uploading `.ebl` files, and rebuilding the site are no longer
done through the web UI -- they're run directly (typically in a Claude Code
session): drop new `.ebl` files in `ebl_staging/`, then run the pipeline
scripts below (`ebl_store.py` to ingest, `build_race_db.py` /
`detect_maneuvers.py` / `polar_analysis.py` to decode and analyze,
`render_race_page.py` / `render_homepage.py` to regenerate the static
pages). The `/add-race` form still exists and works, but isn't linked from
the nav.

## Deploying to Digital Ocean

`docker compose build` targets whatever architecture you're building *on*.
If you're on an Apple Silicon Mac, that's arm64 -- but a standard Digital
Ocean droplet is amd64/x86_64, so a plain `docker compose build` there
won't run. Build for amd64 explicitly with `docker build` instead:

```bash
docker build --platform linux/amd64 -t critical-mass-race-app:amd64 .
```

**Push to Digital Ocean's container registry** (adjust `<registry>` to your
registry name from `doctl registry get`):

```bash
docker tag critical-mass-race-app:amd64 registry.digitalocean.com/<registry>/critical-mass-race-app:latest
doctl registry login
docker push registry.digitalocean.com/<registry>/critical-mass-race-app:latest
```

**On the droplet**, pull and run it with a persistent data directory (copy
your `ebl_data/`, `race_sessions.db`, `races.json`, and `races/` there first,
or start empty and add races from scratch via `/add-race` or the pipeline scripts):

```bash
mkdir -p ~/critical-mass-data && cd ~/critical-mass-data
docker pull registry.digitalocean.com/<registry>/critical-mass-race-app:latest
docker run -d --name critical-mass -p 8000:8000 \
  -e HOST=0.0.0.0 -e PORT=8000 \
  -v ~/critical-mass-data:/app \
  registry.digitalocean.com/<registry>/critical-mass-race-app:latest
```

The bind-mount means the image only supplies the Python runtime and code;
none of your sailing data ever needs to go through the registry.

Simpler alternative if you don't need a registry at all: clone this repo
directly onto the droplet and run `docker compose up --build -d` there --
since the droplet itself is amd64, that builds natively with no cross-platform
flags needed.

## How it works

**EBL decoding** (`ebl2csv/`) is a pure-Python port of the NMEA2000 frame
parsing, fast-packet reassembly, and Canboat PGN field decoding used by
[go-nmea-client](https://github.com/aldas/go-nmea-client) -- see the
docstrings in each module for which part of that Go source it mirrors.
Field definitions come from `canboat.json`, the same public PGN database
[go-nmea-client](https://github.com/aldas/go-nmea-client) and
[canboat](https://github.com/canboat/canboat) itself use.

**The pipeline**, run in order (by `/add-race`, or directly in a Claude Code session):

1. `build_race_db.py` -- decodes the `.ebl` files assigned to each race
   (`races.json`) into `race_sessions.db`: per-PGN tables (position,
   heading, wind, speed, ...) plus a derived `nav_1hz` table resampled onto
   a 1Hz grid, with computed true wind (TWA/TWS) and tack side.
2. `detect_maneuvers.py` -- scans `nav_1hz` for tack/gybe/rounding events.
3. `polar_analysis.py` -- compares `nav_1hz` against `j80_Polars.csv`.
4. `export_course_data.py` / `export_polar_data.py` -- project lat/lon to
   local metres and package everything into compact JSON per race.
5. `render_race_page.py` / `render_homepage.py` -- embed that JSON into the
   static HTML pages actually served.

**Data files:**

- `races.json` -- the race registry (date, start time, series, assigned
  `.ebl` files). Edited through the Add Race form, not by hand.
- `ebl_data/` + `ebl_manifest.json` -- canonical store of every imported
  `.ebl` file, deduplicated by SHA-256 content hash.
- `race_sessions.db` -- SQLite, fully reproducible from the two above.
- `dyc_marks.py` -- the club's racing marks (number, name, lat/lon), shown
  on every course plot. Edit this list directly for a different venue.

## Project structure

```
app.py                  Flask app: homepage + race pages + nav actions
ebl_store.py             .ebl file ingest/dedup (ebl_data/, ebl_manifest.json)
race_registry.py         races.json read/write
build_race_db.py         EBL -> race_sessions.db
detect_maneuvers.py       tack/gybe/rounding detection
polar.py, polar_analysis.py   target-polar interpolation + comparison
export_course_data.py     race_sessions.db -> course_data.json (per race)
export_polar_data.py      race_sessions.db -> polar_data.json (per race)
render_race_page.py       course_data.json + polar_data.json -> races/<id>.html
render_homepage.py        races.json -> index.html
dyc_marks.py              racing mark reference data
j80_Polars.csv            target polar table
canboat.json              Canboat PGN definitions (field decoding schema)
ebl2csv/                  NMEA2000 decoder (frame parsing, fast-packet
                          reassembly, PGN field decoding)
```

## Known limitations

- A few manufacturer-proprietary PGNs aren't in the public `canboat.json`
  and are read but not decoded into named fields.
- The target polar (`j80_Polars.csv`) is a standard crewed polar; a gap
  between actual and target speed may partly reflect actual crew count
  rather than technique.
- Mark rounding detection needs the boat's plotter to have been actively
  navigating to a waypoint (PGN 129284) that day -- races without that data
  only get tack/gybe detection, not rounding detection.

## Credits

- [go-nmea-client](https://github.com/aldas/go-nmea-client) (Aldas
  Kirvaitis) -- the NMEA2000/Actisense decoding logic this project's
  `ebl2csv/` package is a Python port of.
- [canboat](https://github.com/canboat/canboat) -- the PGN definitions
  database (`canboat.json`).
