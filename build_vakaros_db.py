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

"""Builds course/maneuver data for a race's Vakaros track file, entirely
independent of the EBL/N2K pipeline (build_race_db.py, race_sessions.db):
this reads straight from the file in vakaros_data/ each time, the same way
render_race_page.py reads straight from race_sessions.db. Supports both the
original .csv track export and the newer .vkx binary format (vkx_parser.py)
-- see read_track() for the dispatch.

The Vakaros export carries GPS position, heading, speed over ground, heel,
and pitch -- but no wind instrument data (no TWA/AWA), so unlike the EBL
pipeline's detect_maneuvers.py, tack/gybe events here cannot be classified
by wind side. Heading-change episodes are detected and logged the same way
(turn angle, duration, speed loss) but labeled generically as "maneuver".
Mark roundings ARE reliable from GPS alone (proximity to a known club mark)
and are detected the same way as the EBL pipeline's fallback: a local
minimum in distance-to-mark below a radius threshold.
"""
import csv
import math
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from pathlib import Path

import vkx_parser
from dyc_marks import DYC_MARKS
from export_course_data import project

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "vakaros_data"

TRACK_STEP_S = 3           # keep 1-of-every-N seconds of the resampled track for plotting
ROT_THRESHOLD_DEG_S = 6.0  # |rate of turn| considered "actively maneuvering"
SETTLE_S = 2               # consecutive quiet seconds to call a maneuver over
PRE_POST_WINDOW_S = 8      # window for before/after heading & speed averages
MIN_HEADING_CHANGE_DEG = 45.0
MIN_UNDERWAY_SPEED_KN = 1.5
ROUNDING_RADIUS_M = 150.0  # local minimum in distance-to-nearest-mark closer than this = a rounding
ROUNDING_CLEAR_FACTOR = 3  # must move this many radii away before another rounding can trigger


def circ_diff(a, b):
    """Shortest signed angular difference a-b in degrees, wrapped to [-180,180]."""
    return (a - b + 180) % 360 - 180


def avg(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _read_csv(path):
    """Returns rows as dicts with a parsed true-UTC `utc` datetime plus the
    raw numeric fields, sorted by time -- the original Vakaros .csv export."""
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            utc = datetime.fromisoformat(r["timestamp"]).astimezone(timezone.utc).replace(tzinfo=None)
            rows.append({
                "utc": utc,
                "lat": float(r["latitude"]), "lon": float(r["longitude"]),
                "sog": float(r["sog_kts"]), "hdg": float(r["hdg_true"]),
                "heel": float(r["heel"]), "trim": float(r["trim"]),
            })
    rows.sort(key=lambda r: r["utc"])
    return rows


def read_track(path):
    """Dispatches to the right parser by file extension -- .vkx (the
    current/future Vakaros export format) or .csv (the original format,
    kept for any already-ingested races)."""
    path = Path(path)
    if path.suffix.lower() == ".vkx":
        return vkx_parser.read_track(path)
    return _read_csv(path)


def resample_1hz(rows, start_utc, end_utc):
    """Snaps the ~2Hz raw log onto an exact 1Hz grid (nearest-sample), the
    same cadence build_race_db.py resamples EBL data to -- this lets the
    maneuver-episode state machine below treat "1 row" as "1 second"."""
    if not rows:
        return []
    utcs = [r["utc"] for r in rows]
    out = []
    t = start_utc
    while t <= end_utc:
        idx = bisect_left(utcs, t)
        candidates = [i for i in (idx - 1, idx) if 0 <= i < len(rows)]
        if not candidates:
            t += timedelta(seconds=1)
            continue
        best = min(candidates, key=lambda i: abs((utcs[i] - t).total_seconds()))
        if abs((utcs[best] - t).total_seconds()) <= 2.0:
            out.append({**rows[best], "t": t})
        t += timedelta(seconds=1)
    return out


MERGE_GAP_S = 6  # episodes closer together than this are one messy maneuver, not several


def _raw_episodes(rot, n):
    """First pass: contiguous (start_idx, end_idx) spans where the boat is
    actively turning. A single messy moment (e.g. a broach recovery) often
    oscillates back below ROT_THRESHOLD_DEG_S for a moment without the turn
    really being over, so these are merged in a second pass rather than
    trusted as separate events."""
    episodes = []
    i = 1
    while i < n:
        if rot[i] is not None and abs(rot[i]) > ROT_THRESHOLD_DEG_S:
            start_idx = i
            while start_idx > 0 and rot[start_idx - 1] is not None and abs(rot[start_idx - 1]) > ROT_THRESHOLD_DEG_S:
                start_idx -= 1

            end_idx = i
            below = 0
            k = i
            while k < n - 1:
                k += 1
                if rot[k] is not None and abs(rot[k]) < ROT_THRESHOLD_DEG_S:
                    below += 1
                    if below >= SETTLE_S:
                        end_idx = k
                        break
                else:
                    below = 0
            else:
                end_idx = n - 1

            episodes.append((start_idx, end_idx))
            i = k + 1
        else:
            i += 1
    return episodes


def _merge_episodes(episodes):
    merged = []
    for start_idx, end_idx in episodes:
        if merged and start_idx - merged[-1][1] <= MERGE_GAP_S:
            merged[-1] = (merged[-1][0], end_idx)
        else:
            merged.append((start_idx, end_idx))
    return merged


def detect_maneuvers(track):
    """track: 1Hz list of dicts with 't' and 'hdg'/'sog'. Returns generic
    heading-change events -- see module docstring for why these aren't
    classified as tack/gybe."""
    n = len(track)
    rot = [None] * n
    for i in range(1, n):
        dt = (track[i]["t"] - track[i - 1]["t"]).total_seconds()
        rot[i] = circ_diff(track[i]["hdg"], track[i - 1]["hdg"]) / dt if dt > 0 else 0.0

    episodes = _merge_episodes(_raw_episodes(rot, n))

    events = []
    for start_idx, end_idx in episodes:
        pre_start = max(0, start_idx - PRE_POST_WINDOW_S)
        post_end = min(n - 1, end_idx + PRE_POST_WINDOW_S)
        heading_before = avg([track[j]["hdg"] for j in range(pre_start, start_idx)])
        heading_after = avg([track[j]["hdg"] for j in range(end_idx, post_end)])
        speed_before = avg([track[j]["sog"] for j in range(pre_start, start_idx)])
        speed_min = min((track[j]["sog"] for j in range(start_idx, end_idx + 1)), default=None)
        heading_change = circ_diff(heading_after, heading_before) if heading_before is not None and heading_after is not None else None

        if (heading_change is not None and abs(heading_change) >= MIN_HEADING_CHANGE_DEG
                and speed_before is not None and speed_before >= MIN_UNDERWAY_SPEED_KN):
            speed_loss_pct = ((speed_before - speed_min) / speed_before * 100.0) if speed_min is not None and speed_before > 0 else None
            events.append({
                "type": "maneuver",
                "start_utc": track[start_idx]["t"], "end_utc": track[end_idx]["t"],
                "duration_s": (track[end_idx]["t"] - track[start_idx]["t"]).total_seconds(),
                "heading_before": heading_before, "heading_after": heading_after,
                "heading_change": heading_change,
                "speed_before": speed_before, "speed_min": speed_min,
                "speed_loss_pct": speed_loss_pct,
                "idx": start_idx,
            })
    return events


def detect_roundings(track, marks_xy):
    """Local minima in distance-to-nearest-mark below ROUNDING_RADIUS_M --
    the GPS-only analog of detect_maneuvers.py's waypoint-distance rounding
    detection, generalized across every known club mark instead of one
    logged destination waypoint."""
    n = len(track)
    dist, nearest = [], []
    for row in track:
        best_d, best_mark = None, None
        for mid, mname, mx, my in marks_xy:
            d = math.hypot(row["x"] - mx, row["y"] - my)
            if best_d is None or d < best_d:
                best_d, best_mark = d, (mid, mname)
        dist.append(best_d)
        nearest.append(best_mark)

    roundings = []
    i = 1
    while i < n - 1:
        if dist[i] <= ROUNDING_RADIUS_M and dist[i] <= dist[i - 1]:
            j = i
            while j + 1 < n and dist[j + 1] <= dist[j]:
                j += 1
            min_idx = j
            k = min_idx
            while k + 1 < n and dist[k + 1] < ROUNDING_RADIUS_M * ROUNDING_CLEAR_FACTOR:
                k += 1
            speed_at_mark = track[min_idx]["sog"]
            if speed_at_mark is not None and speed_at_mark >= MIN_UNDERWAY_SPEED_KN:
                mark_id, mark_name = nearest[min_idx]
                roundings.append({
                    "type": "rounding",
                    "start_utc": track[max(0, min_idx - 5)]["t"], "end_utc": track[min(n - 1, min_idx + 5)]["t"],
                    "duration_s": 10.0,
                    "mark_id": mark_id, "mark_name": mark_name,
                    "distance_to_mark": dist[min_idx],
                    "idx": min_idx,
                })
            i = k + 1
        else:
            i += 1
    return roundings


def build_race(race_id, track_path, trim_start_utc, trim_end_utc):
    """Returns the course-data dict for one race's Vakaros track (same
    consumer shape as export_course_data.export_for_race), or None if the
    trim window has no data in this file."""
    raw = read_track(track_path)
    track = resample_1hz(raw, trim_start_utc, trim_end_utc)
    if not track:
        return None

    lats = [r["lat"] for r in track]
    lons = [r["lon"] for r in track]
    lat0, lon0 = sum(lats) / len(lats), sum(lons) / len(lons)
    for r in track:
        r["x"], r["y"] = project(r["lat"], r["lon"], lat0, lon0)

    waypoints = [{"id": mid, "name": mname, "x": x, "y": y}
                 for mid, mname, lat, lon in DYC_MARKS
                 for x, y in [project(lat, lon, lat0, lon0)]]
    marks_xy = [(mid, mname, wp["x"], wp["y"]) for (mid, mname, _, _), wp in zip(DYC_MARKS, waypoints)]

    maneuvers = detect_maneuvers(track)
    roundings = detect_roundings(track, marks_xy)
    all_events = sorted(maneuvers + roundings, key=lambda e: e["start_utc"])

    out_track = []
    for i, r in enumerate(track):
        if i % TRACK_STEP_S != 0 and i != len(track) - 1:
            continue
        elapsed = (r["t"] - trim_start_utc).total_seconds()
        out_track.append([
            round(elapsed, 0), r["x"], r["y"],
            round(r["hdg"], 0), round(r["sog"], 2), round(r["heel"], 1), round(r["trim"], 1),
            r["t"].isoformat(sep=" ", timespec="seconds"),
        ])

    out_maneuvers = []
    for e in all_events:
        row = track[e["idx"]]
        out_maneuvers.append({
            "type": e["type"],
            "start_utc": e["start_utc"].isoformat(sep=" ", timespec="seconds"),
            "end_utc": e["end_utc"].isoformat(sep=" ", timespec="seconds"),
            "duration_s": round(e["duration_s"], 1),
            "heading_before": round(e["heading_before"], 0) if e.get("heading_before") is not None else None,
            "heading_after": round(e["heading_after"], 0) if e.get("heading_after") is not None else None,
            "heading_change": round(e["heading_change"], 0) if e.get("heading_change") is not None else None,
            "speed_before": round(e["speed_before"], 2) if e.get("speed_before") is not None else None,
            "speed_min": round(e["speed_min"], 2) if e.get("speed_min") is not None else None,
            "speed_loss_pct": round(e["speed_loss_pct"], 0) if e.get("speed_loss_pct") is not None else None,
            "mark_id": e.get("mark_id"), "mark_name": e.get("mark_name"),
            "distance_to_mark": round(e["distance_to_mark"], 0) if e.get("distance_to_mark") is not None else None,
            "x": row["x"], "y": row["y"],
        })

    return {
        "race_id": race_id,
        "track": out_track,
        "waypoints": waypoints,
        "maneuvers": out_maneuvers,
        "utc_start": trim_start_utc.isoformat(sep=" ", timespec="seconds"),
        "utc_end": trim_end_utc.isoformat(sep=" ", timespec="seconds"),
    }


def build_for_race(race_meta):
    """race_meta: an entry from races.json. Looks up this race's Vakaros
    track file (if any) via vakaros_registry and builds its course data,
    trimmed to the same gun-to-finish window already established for the
    EBL analysis of this race. Returns None if there's no Vakaros file
    registered for this race, or it has no trim window yet."""
    import vakaros_registry
    entry = vakaros_registry.by_race_id().get(race_meta["id"])
    if entry is None:
        return None
    track_path = DATA_DIR / entry["filename"]
    if not track_path.exists():
        return None
    trim_start = race_meta.get("trim_start_utc")
    trim_end = race_meta.get("trim_end_utc")
    if not trim_start or not trim_end:
        return None
    return build_race(
        race_meta["id"], track_path,
        datetime.fromisoformat(trim_start), datetime.fromisoformat(trim_end),
    )


if __name__ == "__main__":
    from race_registry import load_registry
    import vakaros_registry

    registered_ids = {r["race_id"] for r in vakaros_registry.load_registry()["races"]}
    for race in load_registry()["races"]:
        if race["id"] not in registered_ids:
            continue
        data = build_for_race(race)
        if data is None:
            print(f"# race {race['id']}: no usable Vakaros data (missing trim window or file)")
            continue
        print(f"# race {race['id']}: {len(data['track'])} track points, {len(data['maneuvers'])} maneuvers")
