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

"""Exports track/waypoint/maneuver data for both race sessions from
race_sessions.db to a compact JSON file for the course-visualization
artifact. Lat/lon is projected to local metres (equirectangular, per-session
origin at the track centroid) since the visualization draws a flat course
plot, not a slippy map.
"""
import json
import math
import sqlite3
from pathlib import Path

from dyc_marks import DYC_MARKS

DB_PATH = Path(__file__).parent / "race_sessions.db"
OUT_PATH = Path(__file__).parent / "course_data.json"

TRACK_STEP_S = 3  # keep 1-of-every-N seconds of nav_1hz for the plotted track


def project(lat, lon, lat0, lon0):
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    x = (lon - lon0) * m_per_deg_lon
    y = (lat - lat0) * m_per_deg_lat
    return round(x, 1), round(y, 1)


def build_session(conn, sid, meta):
    cur = conn.execute(
        "SELECT utc_timestamp, elapsed_s, latitude, longitude, heading_deg, sog_kn, stw_kn, "
        "twa_deg, tws_kn, tack, depth_m, awa_deg, aws_kn, heel_deg, pitch_deg "
        "FROM nav_1hz WHERE session_id=? AND latitude IS NOT NULL "
        "ORDER BY utc_timestamp", (sid,)
    )
    rows = cur.fetchall()
    if not rows:
        return None

    lats = [r[2] for r in rows]
    lons = [r[3] for r in rows]
    lat0 = sum(lats) / len(lats)
    lon0 = sum(lons) / len(lons)

    track = []
    for i, r in enumerate(rows):
        if i % TRACK_STEP_S != 0 and i != len(rows) - 1:
            continue
        ts, elapsed_s, lat, lon, hdg, sog, stw, twa, tws, tack, depth, awa, aws, heel, pitch = r
        x, y = project(lat, lon, lat0, lon0)
        track.append([
            round(elapsed_s, 0), x, y,
            round(hdg, 0) if hdg is not None else None,
            round(sog, 2) if sog is not None else None,
            round(stw, 2) if stw is not None else None,
            round(twa, 0) if twa is not None else None,
            round(tws, 1) if tws is not None else None,
            tack[0] if tack else None,  # 'p'/'s'
            ts,
            round(awa, 0) if awa is not None else None,
            round(aws, 1) if aws is not None else None,
            round(heel, 1) if heel is not None else None,
            round(pitch, 1) if pitch is not None else None,
        ])

    # known club racing marks, shown on every race regardless of which ones
    # were actually rounded that day -- projected with this race's own
    # track origin so they line up spatially with the plotted course
    waypoints = []
    for mark_id, mark_name, lat, lon in DYC_MARKS:
        x, y = project(lat, lon, lat0, lon0)
        waypoints.append({"id": mark_id, "name": mark_name, "x": x, "y": y})

    man_cur = conn.execute(
        "SELECT type, start_utc, end_utc, duration_s, heading_before_deg, heading_after_deg, "
        "heading_change_deg, twa_before_deg, twa_after_deg, speed_before_kn, speed_min_kn, "
        "speed_loss_pct, distance_to_mark_m FROM maneuvers WHERE session_id=? ORDER BY start_utc", (sid,)
    )
    maneuvers = []
    # look up nearest track x/y for each maneuver's start_utc for plotting
    ts_list = [r[0] for r in rows]
    xy_list = [(project(r[2], r[3], lat0, lon0)) for r in rows]

    from bisect import bisect_left
    for m in man_cur.fetchall():
        (mtype, start_utc, end_utc, dur, hb, ha, hchg, twab, twaa, spb, spmin, loss, dist) = m
        idx = bisect_left(ts_list, start_utc)
        idx = min(idx, len(ts_list) - 1)
        x, y = xy_list[idx]
        maneuvers.append({
            "type": mtype, "start_utc": start_utc, "end_utc": end_utc,
            "duration_s": round(dur, 1) if dur is not None else None,
            "heading_before": round(hb, 0) if hb is not None else None,
            "heading_after": round(ha, 0) if ha is not None else None,
            "heading_change": round(hchg, 0) if hchg is not None else None,
            "twa_before": round(twab, 0) if twab is not None else None,
            "twa_after": round(twaa, 0) if twaa is not None else None,
            "speed_before": round(spb, 2) if spb is not None else None,
            "speed_min": round(spmin, 2) if spmin is not None else None,
            "speed_loss_pct": round(loss, 0) if loss is not None else None,
            "distance_to_mark": round(dist, 0) if dist is not None else None,
            "x": x, "y": y,
        })

    return {
        "session_id": sid, **meta,
        "track": track,
        "waypoints": waypoints,
        "maneuvers": maneuvers,
    }


def _session_meta(conn, sid):
    row = conn.execute(
        "SELECT race_date, local_start_time, series, boat, timezone, utc_start, utc_end, notes "
        "FROM sessions WHERE session_id=?", (sid,)
    ).fetchone()
    if row is None:
        return None
    race_date, local_start, series, boat, tz, utc_start, utc_end, notes = row
    return {
        "race_date": race_date, "local_start_time": local_start, "series": series,
        "boat": boat, "timezone": tz, "utc_start": utc_start, "utc_end": utc_end,
        "notes": notes,
    }


def export_for_race(conn, sid):
    """Returns the course-data dict for one race (for embedding directly in
    that race's page), or None if the race/session has no track data."""
    meta = _session_meta(conn, sid)
    if meta is None:
        return None
    return build_session(conn, sid, meta)


def main():
    conn = sqlite3.connect(DB_PATH)
    sids = [row[0] for row in conn.execute("SELECT session_id FROM sessions").fetchall()]

    out = []
    for sid in sids:
        s = export_for_race(conn, sid)
        if s:
            out.append(s)
            print(f"# session {sid}: {len(s['track'])} track points, {len(s['waypoints'])} waypoints, "
                  f"{len(s['maneuvers'])} maneuvers")

    OUT_PATH.write_text(json.dumps(out, separators=(",", ":")))
    print(f"# Wrote {OUT_PATH} ({OUT_PATH.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
