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

"""Renders a performance-data overlay onto race video footage: a top-right
telemetry panel, a left-side position map (marks + live boat position, on a
real map basemap when available), and a bottom-center race clock -- synced
second-by-second to the boat's own logged telemetry.

Standalone script, not imported by app.py -- keeps the Flask app/Docker
image free of the video/imaging dependencies this needs (see
requirements-video.txt: pillow). Never touches race_sessions.db or
races.json; decodes telemetry directly from the race's .ebl files, so
overlay coverage isn't limited by that race's website-analysis trim (which
is set for scoring/coaching purposes and can end before the video does).

Usage:
    python render_video_overlay.py <race_id> <video_filename> <video_offset_seconds>
    python render_video_overlay.py --all
        (processes every Videos/video_config.json entry with no P_-prefixed
        output yet)

video_offset_seconds is the timestamp (in seconds into the video) at which
the race's actual start happens -- read straight off the footage.
"""
import bisect
import json
import math
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

from PIL import Image, ImageDraw, ImageFont

from build_race_db import (
    MAX_STALENESS_S, PGNS_PATH, EBL_DIR,
    _lookup, decode_session_messages, true_wind,
)
from dyc_marks import DYC_MARKS
from ebl2csv.schema import CanboatSchema
from race_registry import load_registry

ROOT = Path(__file__).parent
VIDEOS_DIR = ROOT / "Videos"
CONFIG_PATH = VIDEOS_DIR / "video_config.json"
TILE_CACHE_DIR = VIDEOS_DIR / ".tile_cache"

PGN_POSITION = 129025
PGN_SPEED = 128259
PGN_WIND = 130306
PGN_ATTITUDE = 127257

UNDERWAY_KN = 1.5
SUSTAIN_S = 30

TILE_SIZE = 256
TILE_ZOOM = 15
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_USER_AGENT = "CriticalMassRacing/1.0 (personal race-video overlay tool)"

PANEL_FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
PANEL_FONT_BOLD_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

# Title-safe margins: many players/devices overscan-crop roughly the outer
# 10% of the frame, which was clipping the top panels and hiding the
# bottom text entirely. Keep all overlay content inside this box. Expressed
# as fractions of the actual source video's dimensions (probed per-video --
# footage isn't always the same resolution) rather than fixed pixel counts.
MARGIN_X_FRAC = 0.10
MARGIN_TOP_FRAC = 0.15  # 10% safe margin + an extra 5% requested
MARGIN_BOTTOM_FRAC = 0.10

TRACK_STEP_S = 3  # breadcrumb sampling interval (matches export_course_data.py's own decimation)


# --------------------------------------------------------------- telemetry

def _decode_race_channels(race):
    """Decodes this race's assigned .ebl files with no trim, returning
    as-of series (ts_list, val_list, width) per channel -- the same shape
    build_race_db._lookup() expects, built independently of
    race_sessions.db so the trim used there doesn't limit this."""
    schema = CanboatSchema(str(PGNS_PATH))
    raw = {"position": [], "speed": [], "wind": [], "attitude": []}

    for utc, header, fv in decode_session_messages(schema, race["files"], trim_end=None):
        pgn = header.pgn
        if pgn == PGN_POSITION:
            raw["position"].append((utc, fv.get("latitude"), fv.get("longitude")))
        elif pgn == PGN_SPEED:
            raw["speed"].append((utc, fv.get("speedWaterReferenced")))
        elif pgn == PGN_WIND:
            raw["wind"].append((utc, fv.get("windSpeed"), fv.get("windAngle")))
        elif pgn == PGN_ATTITUDE:
            raw["attitude"].append((utc, fv.get("pitch"), fv.get("roll")))

    if not raw["position"]:
        raise ValueError(f"race {race['id']}: no position messages decoded from {race['files']}")

    series = {}
    for name, rows in raw.items():
        rows.sort(key=lambda r: r[0])
        series[name] = ([r[0] for r in rows], [r[1:] for r in rows], len(rows[0]) - 1 if rows else 0)
    return series


def _sample(series, t):
    lat, lon = _lookup(*series["position"], t, MAX_STALENESS_S)
    stw, = _lookup(*series["speed"], t, MAX_STALENESS_S)
    aws, awa = _lookup(*series["wind"], t, MAX_STALENESS_S)
    pitch, heel = _lookup(*series["attitude"], t, MAX_STALENESS_S)
    twa, tws, tack = true_wind(awa, aws, stw)
    return {"lat": lat, "lon": lon, "stw_kn": stw, "twa_deg": twa, "heel_deg": heel, "pitch_deg": pitch}


def _detect_sailing_start(series, t_min, t_max):
    """First timestamp where boat speed sustains >= UNDERWAY_KN for
    SUSTAIN_S seconds -- the same rule used to set this race's trim_end_utc,
    reapplied here so the video-sync anchor doesn't depend on remembering a
    separately-stored value."""
    ts_list, val_list, _ = series["speed"]
    t = t_min
    while t <= t_max:
        idx = bisect.bisect_right(ts_list, t) - 1
        if idx >= 0 and (t - ts_list[idx]).total_seconds() <= MAX_STALENESS_S:
            stw = val_list[idx][0]
            if stw is not None and stw >= UNDERWAY_KN:
                sustained = True
                tt = t
                for _ in range(SUSTAIN_S):
                    tt += timedelta(seconds=1)
                    idx2 = bisect.bisect_right(ts_list, tt) - 1
                    stw2 = val_list[idx2][0] if idx2 >= 0 else None
                    if stw2 is None or stw2 < UNDERWAY_KN:
                        sustained = False
                        break
                if sustained:
                    return t
        t += timedelta(seconds=1)
    raise ValueError("never found a sustained underway period in this race's telemetry")


# --------------------------------------------------------------------- map

def _lonlat_to_tile_xy(lon, lat, zoom):
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _fetch_tile(z, x, y):
    cache_path = TILE_CACHE_DIR / f"{z}_{x}_{y}.png"
    if cache_path.exists():
        return Image.open(cache_path).convert("RGB")
    TILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    req = Request(OSM_TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": OSM_USER_AGENT})
    with urlopen(req, timeout=10) as resp:
        data = resp.read()
    cache_path.write_bytes(data)
    return Image.open(cache_path).convert("RGB")


def build_basemap(lat_min, lat_max, lon_min, lon_max, out_w, out_h):
    """Fetches/stitches real OSM tiles covering the given bbox and returns
    (basemap_image, project_fn) where project_fn(lat, lon) -> (px, py) in
    the returned image. Raises on any network/tile failure -- caller falls
    back to the schematic map."""
    x0f, y0f = _lonlat_to_tile_xy(lon_min, lat_max, TILE_ZOOM)  # top-left
    x1f, y1f = _lonlat_to_tile_xy(lon_max, lat_min, TILE_ZOOM)  # bottom-right
    tx0, ty0 = int(math.floor(x0f)), int(math.floor(y0f))
    tx1, ty1 = int(math.floor(x1f)), int(math.floor(y1f))

    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * TILE_SIZE, (ty1 - ty0 + 1) * TILE_SIZE))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            tile = _fetch_tile(TILE_ZOOM, tx, ty)
            canvas.paste(tile, ((tx - tx0) * TILE_SIZE, (ty - ty0) * TILE_SIZE))

    def project(lat, lon):
        xf, yf = _lonlat_to_tile_xy(lon, lat, TILE_ZOOM)
        return (xf - tx0) * TILE_SIZE, (yf - ty0) * TILE_SIZE

    px0, py0 = project(lat_max, lon_min)
    px1, py1 = project(lat_min, lon_max)
    cropped = canvas.crop((int(px0), int(py0), int(px1), int(py1))).resize((out_w, out_h))

    def project_out(lat, lon):
        x, y = project(lat, lon)
        ox = (x - px0) / (px1 - px0) * out_w
        oy = (y - py0) / (py1 - py0) * out_h
        return ox, oy

    return cropped, project_out


def build_schematic_basemap(lat_min, lat_max, lon_min, lon_max, out_w, out_h):
    """Fallback used when the real basemap can't be fetched (offline, tile
    server unreachable, etc): flat equirectangular projection on a plain
    dark background, matching the site's own course-plot styling."""
    canvas = Image.new("RGB", (out_w, out_h), (14, 34, 42))
    draw = ImageDraw.Draw(canvas)
    for frac in (0.25, 0.5, 0.75):
        draw.line([(0, out_h * frac), (out_w, out_h * frac)], fill=(31, 62, 72), width=1)
        draw.line([(out_w * frac, 0), (out_w * frac, out_h)], fill=(31, 62, 72), width=1)

    lat0 = (lat_min + lat_max) / 2
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    x_min = (lon_min - lon_min) * m_per_deg_lon
    x_max = (lon_max - lon_min) * m_per_deg_lon
    y_min = (lat_min - lat_min) * m_per_deg_lat
    y_max = (lat_max - lat_min) * m_per_deg_lat

    def project(lat, lon):
        x = (lon - lon_min) * m_per_deg_lon
        y = (lat - lat_min) * m_per_deg_lat
        ox = (x - x_min) / (x_max - x_min) * out_w if x_max > x_min else out_w / 2
        oy = out_h - (y - y_min) / (y_max - y_min) * out_h if y_max > y_min else out_h / 2
        return ox, oy

    return canvas, project


# --------------------------------------------------------------- rendering

def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _fmt_clock(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def draw_performance_panel(draw, x, y, w, h, sample, font, font_bold):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=(10, 26, 32, 165))
    stw = sample["stw_kn"]
    twa = sample["twa_deg"]
    heel = sample["heel_deg"]
    pitch = sample["pitch_deg"]

    vmg = stw * math.cos(math.radians(twa)) if (stw is not None and twa is not None) else None
    up_vmg = f"{vmg:.1f} kn" if (vmg is not None and abs(twa) <= 90) else "--"
    down_vmg = f"{vmg:.1f} kn" if (vmg is not None and abs(twa) > 90) else "--"

    lines = [
        ("Boat Speed", f"{stw:.1f} kn" if stw is not None else "--"),
        ("Up VMG", up_vmg),
        ("Down VMG", down_vmg),
        ("Heel", f"{abs(heel):.0f}°" if heel is not None else "--"),
        ("Trim", f"{pitch:+.0f}°" if pitch is not None else "--"),
    ]
    line_h = h / len(lines)
    for i, (label, value) in enumerate(lines):
        ly = y + i * line_h + line_h / 2
        draw.text((x + 12, ly), f"{label}:", font=font, fill=(127, 163, 171, 255), anchor="lm")
        draw.text((x + w - 12, ly), value, font=font_bold, fill=(231, 237, 233, 255), anchor="rm")


def draw_map_panel(draw_target, x, y, w, h, basemap_img, project_fn, marks, trail, boat_latlon):
    draw_target.paste(basemap_img, (x, y))
    overlay = ImageDraw.Draw(draw_target)

    for mark_id, name, lat, lon in marks:
        mx, my = project_fn(lat, lon)
        overlay.ellipse([x + mx - 4, y + my - 4, x + mx + 4, y + my + 4], fill=(245, 185, 66, 230))
        overlay.text((x + mx + 6, y + my), mark_id, fill=(245, 185, 66, 255))

    if len(trail) > 1:
        pts = [(x + project_fn(lat, lon)[0], y + project_fn(lat, lon)[1]) for lat, lon in trail]
        overlay.line(pts, fill=(63, 191, 127, 200), width=2)

    if boat_latlon and boat_latlon[0] is not None:
        bx, by = project_fn(*boat_latlon)
        overlay.ellipse([x + bx - 6, y + by - 6, x + bx + 6, y + by + 6],
                         outline=(239, 90, 76, 255), width=3, fill=(239, 90, 76, 120))


def draw_bottom_text(draw, text, font, frame_w, frame_h, margin_bottom):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (frame_w - tw) / 2
    y = frame_h - margin_bottom - 26
    pad = 8
    draw.rounded_rectangle([x - pad, y - 4, x + tw + pad, y + 22], radius=6, fill=(10, 26, 32, 150))
    draw.text((x, y), text, font=font, fill=(231, 237, 233, 255))


def render_overlay_frames(race, series, video_start_utc, video_end_utc, sailing_start_utc, out_dir, frame_w, frame_h):
    margin_x = int(frame_w * MARGIN_X_FRAC)
    margin_top = int(frame_h * MARGIN_TOP_FRAC)
    margin_bottom = int(frame_h * MARGIN_BOTTOM_FRAC)

    lats = [v[0] for v in series["position"][1] if v[0] is not None]
    lons = [v[1] for v in series["position"][1] if v[1] is not None]
    lat_pad = (max(lats) - min(lats)) * 0.2 or 0.002
    lon_pad = (max(lons) - min(lons)) * 0.2 or 0.002
    lat_min, lat_max = min(lats) - lat_pad, max(lats) + lat_pad
    lon_min, lon_max = min(lons) - lon_pad, max(lons) + lon_pad

    map_w, map_h = 170, 170
    try:
        basemap_img, project_fn = build_basemap(lat_min, lat_max, lon_min, lon_max, map_w, map_h)
        print("# using real OSM basemap")
    except (URLError, OSError, TimeoutError) as e:
        print(f"# OSM basemap fetch failed ({e}); using schematic fallback")
        basemap_img, project_fn = build_schematic_basemap(lat_min, lat_max, lon_min, lon_max, map_w, map_h)

    marks = [m for m in DYC_MARKS if lat_min - lat_pad <= m[2] <= lat_max + lat_pad
             and lon_min - lon_pad <= m[3] <= lon_max + lon_pad]

    panel_font = _font(PANEL_FONT_PATH, 13)
    panel_font_bold = _font(PANEL_FONT_BOLD_PATH, 13)
    bottom_font = _font(PANEL_FONT_BOLD_PATH, 15)

    date_str = datetime.fromisoformat(race["race_date"]).strftime("%b %-d, %Y")
    label_prefix = f"Critical Mass: {race['series']} {date_str}"

    n_seconds = int((video_end_utc - video_start_utc).total_seconds()) + 1
    out_dir.mkdir(parents=True, exist_ok=True)

    # Precompute the full-race breadcrumb track once (from the actual start
    # of sailing through the end of the video), so each frame just slices
    # this list instead of re-sampling telemetry for every prior second --
    # O(n) total instead of O(n^2).
    track_ts, track_latlon = [], []
    tt = sailing_start_utc
    while tt <= video_end_utc:
        samp = _sample(series, tt)
        if samp["lat"] is not None:
            track_ts.append(tt)
            track_latlon.append((samp["lat"], samp["lon"]))
        tt += timedelta(seconds=TRACK_STEP_S)

    panel_x, panel_y, panel_w, panel_h = frame_w - margin_x - 176, margin_top, 176, 110
    map_x, map_y = margin_x, margin_top

    for i in range(n_seconds):
        t = video_start_utc + timedelta(seconds=i)
        frame = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        sample = _sample(series, t)
        draw_performance_panel(draw, panel_x, panel_y, panel_w, panel_h, sample, panel_font, panel_font_bold)

        trail_end = bisect.bisect_right(track_ts, t)
        trail = track_latlon[:trail_end]
        draw_map_panel(frame, map_x, map_y, map_w, map_h, basemap_img, project_fn, marks,
                        trail, (sample["lat"], sample["lon"]))

        if t < sailing_start_utc:
            clock_text = f"{label_prefix}  In sequence"
        else:
            clock_text = f"{label_prefix}  race time: {_fmt_clock((t - sailing_start_utc).total_seconds())}"
        draw_bottom_text(draw, clock_text, bottom_font, frame_w, frame_h, margin_bottom)

        frame.save(out_dir / f"frame_{i:06d}.png")


# --------------------------------------------------------------- ffmpeg io

def ffprobe_duration(video_path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def ffprobe_dimensions(video_path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=s=x:p=0", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    w, h = out.stdout.strip().split("x")
    return int(w), int(h)


def composite(video_path, overlay_dir, out_path):
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-framerate", "1", "-i", str(overlay_dir / "frame_%06d.png"),
        "-filter_complex", "[0:v][1:v]overlay=x=0:y=0:eof_action=pass[out]",
        "-map", "[out]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy", "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


# ----------------------------------------------------------------- driver

def process_video(race_id, video_filename, video_offset_seconds):
    race = next(r for r in load_registry()["races"] if r["id"] == race_id)
    video_path = VIDEOS_DIR / video_filename
    out_path = VIDEOS_DIR / f"P_{video_filename}"
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    print(f"# Decoding telemetry for race {race_id} ({race['race_date']} {race['series']})...")
    series = _decode_race_channels(race)

    # The race-clock anchor is the actual gun time: the race's saved
    # trim_start_utc when present (set from the known start time, e.g.
    # 18:20 ADT = 21:20 UTC -- the logger clock is true UTC, verified by
    # GPS cross-correlation against a Vakaros track). Falls back to
    # first-sustained-underway detection only for races without one, which
    # can land on the pre-race motor out rather than the gun.
    if race.get("trim_start_utc"):
        race_start_utc = datetime.fromisoformat(race["trim_start_utc"])
        print(f"#   race start (gun) from trim_start_utc: {race_start_utc} (video offset {video_offset_seconds}s)")
    else:
        t_min = min(series["position"][0])
        t_max = max(series["position"][0])
        race_start_utc = _detect_sailing_start(series, t_min, t_max)
        print(f"#   race start estimated from first sustained underway: {race_start_utc} (video offset {video_offset_seconds}s)")

    video_start_utc = race_start_utc - timedelta(seconds=video_offset_seconds)
    duration = ffprobe_duration(video_path)
    frame_w, frame_h = ffprobe_dimensions(video_path)
    video_end_utc = video_start_utc + timedelta(seconds=duration)
    print(f"#   video covers {video_start_utc} -> {video_end_utc} ({duration:.0f}s, {frame_w}x{frame_h})")

    with tempfile.TemporaryDirectory(prefix=f"overlay_{race_id}_") as tmp:
        overlay_dir = Path(tmp)
        print(f"# Rendering {int(duration)+1} overlay frames to {overlay_dir}...")
        render_overlay_frames(race, series, video_start_utc, video_end_utc, race_start_utc, overlay_dir, frame_w, frame_h)
        print(f"# Compositing onto video -> {out_path}...")
        composite(video_path, overlay_dir, out_path)

    print(f"# Wrote {out_path} ({out_path.stat().st_size/1e6:.0f} MB)")


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--all":
        entries = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else []
        for entry in entries:
            out_path = VIDEOS_DIR / f"P_{entry['video_filename']}"
            if out_path.exists():
                print(f"# skipping {entry['video_filename']} (P_ output already exists)")
                continue
            process_video(entry["race_id"], entry["video_filename"], entry["video_offset_seconds"])
        return

    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    race_id = int(sys.argv[1])
    video_filename = sys.argv[2]
    video_offset_seconds = float(sys.argv[3])
    process_video(race_id, video_filename, video_offset_seconds)


if __name__ == "__main__":
    main()
