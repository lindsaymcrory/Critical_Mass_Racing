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

"""Detects tacks, gybes, and mark roundings in nav_1hz and writes them to a
`maneuvers` table in race_sessions.db.

Tack/gybe detection: nav_1hz already carries a `tack` column (port/starboard,
from apparent wind angle sign). A hysteresis filter confirms a real
tack-side flip only once the new side has held for MIN_HOLD_S seconds
(filters noise right at head-to-wind/dead-downwind where AWA can bounce
across the boundary without a committed maneuver). Each confirmed flip is
classified using the average true wind angle just before/after:
  |TWA| < 90 on both sides  -> tack   (turn passed through head-to-wind)
  |TWA| >= 90 on both sides -> gybe   (turn passed through dead-downwind)
The maneuver's start/end are found by searching outward from the flip for
where rate-of-turn crosses ROT_THRESHOLD_DEG_S.

Mark rounding detection: only possible where navigation_data carries
distance-to-waypoint (session 1, "14 Rockingham"). A rounding is a local
minimum in distance-to-waypoint below ROUNDING_RADIUS_M.
"""
import math
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "race_sessions.db"

MIN_HOLD_S = 8            # seconds the new tack side must hold to confirm a real flip
ROT_THRESHOLD_DEG_S = 4.0  # |rate of turn| considered "actively maneuvering"
SETTLE_S = 2               # consecutive seconds below threshold to call the maneuver over
PRE_POST_WINDOW_S = 8      # window for before/after heading & TWA & speed averages
RECOVERY_WINDOW_S = 20     # window after maneuver end to measure recovered speed
ROUNDING_RADIUS_M = 300.0  # local minimum in distance-to-mark closer than this = a rounding
                           # (300m, not the more usual arrival-circle sizes, because the
                           # closest approach actually logged to "14 Rockingham" was 262m --
                           # the boat likely changed target waypoint before physically
                           # reaching this one, or logging stopped just before rounding)
MIN_HEADING_CHANGE_DEG = 45.0  # reject AWA-noise flips with no real turn (e.g. sitting at the dock)
MIN_UNDERWAY_SPEED_KN = 1.5    # reject events while not actually sailing

SCHEMA_SQL = """
DROP TABLE IF EXISTS maneuvers;
CREATE TABLE maneuvers (
    session_id INTEGER, type TEXT,
    start_utc TEXT, end_utc TEXT, duration_s REAL,
    heading_before_deg REAL, heading_after_deg REAL, heading_change_deg REAL,
    twa_before_deg REAL, twa_after_deg REAL,
    speed_before_kn REAL, speed_min_kn REAL, speed_recovered_kn REAL,
    speed_loss_pct REAL, recovery_time_s REAL,
    mark_wp_number INTEGER, distance_to_mark_m REAL
);
CREATE INDEX idx_maneuvers ON maneuvers(session_id, start_utc);
"""


def circ_diff_deg(a, b):
    """Shortest signed angular difference a-b in degrees, wrapped to [-180,180]."""
    d = (a - b + 180) % 360 - 180
    return d


def load_series(conn, sid):
    cur = conn.execute(
        "SELECT utc_timestamp, heading_deg, rot_deg_s, twa_deg, tack, stw_kn, distance_to_wp_m, "
        "destination_wp_number FROM nav_1hz WHERE session_id=? ORDER BY utc_timestamp",
        (sid,),
    )
    return cur.fetchall()


def avg(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def detect_tacks_gybes(rows, sid):
    """rows: list of (ts, heading, rot, twa, tack, stw, dist_wp, dest_wp_num)."""
    n = len(rows)
    events = []

    current_tack = None
    pending_tack = None
    pending_start_idx = None
    pending_count = 0

    for i, r in enumerate(rows):
        tack = r[4]
        if tack is None:
            continue
        if current_tack is None:
            current_tack = tack
            continue
        if tack == current_tack:
            pending_tack = None
            pending_count = 0
            continue
        if tack == pending_tack:
            pending_count += 1
        else:
            pending_tack = tack
            pending_count = 1
            pending_start_idx = i
        if pending_count >= MIN_HOLD_S:
            events.append((pending_start_idx, current_tack, pending_tack))
            current_tack = pending_tack
            pending_tack = None
            pending_count = 0

    maneuvers = []
    for flip_idx, old_tack, new_tack in events:
        # search backward from the flip for where the turn actually began
        # (rate-of-turn first exceeded the threshold)
        start_idx = flip_idx
        while start_idx > 0 and abs(rows[start_idx - 1][2] or 0) > ROT_THRESHOLD_DEG_S:
            start_idx -= 1

        # search forward from flip for turn to settle back down
        end_idx = flip_idx
        below_count = 0
        k = flip_idx
        while k < n - 1:
            k += 1
            if abs(rows[k][2] or 999) < ROT_THRESHOLD_DEG_S:
                below_count += 1
                if below_count >= SETTLE_S:
                    end_idx = k
                    break
            else:
                below_count = 0
        else:
            end_idx = n - 1

        if start_idx >= end_idx:
            continue

        pre_start = max(0, start_idx - PRE_POST_WINDOW_S)
        post_end = min(n - 1, end_idx + PRE_POST_WINDOW_S)
        recov_end = min(n - 1, end_idx + RECOVERY_WINDOW_S)

        heading_before = avg([r[1] for r in rows[pre_start:start_idx]])
        heading_after = avg([r[1] for r in rows[end_idx:post_end]])
        twa_before = avg([r[3] for r in rows[pre_start:start_idx]])
        twa_after = avg([r[3] for r in rows[end_idx:post_end]])
        speed_before = avg([r[5] for r in rows[pre_start:start_idx]])
        speed_min = min([r[5] for r in rows[start_idx:end_idx + 1] if r[5] is not None], default=None)
        speed_recovered = avg([r[5] for r in rows[end_idx:recov_end]])

        if twa_before is None or twa_after is None:
            man_type = "tack" if old_tack != new_tack else "unknown"
        else:
            man_type = "tack" if (abs(twa_before) < 90 and abs(twa_after) < 90) else \
                       "gybe" if (abs(twa_before) >= 90 and abs(twa_after) >= 90) else "rounding-turn"

        heading_change = circ_diff_deg(heading_after, heading_before) if heading_before is not None and heading_after is not None else None

        # Reject noise: a boat sitting at the dock/mooring can show the AWA
        # sign flip back and forth (wind vane jitter near head-to-wind) with
        # no actual turn or motion. Require a real heading change and that
        # the boat was actually underway.
        if heading_change is None or abs(heading_change) < MIN_HEADING_CHANGE_DEG:
            continue
        if speed_before is None or speed_before < MIN_UNDERWAY_SPEED_KN:
            continue

        speed_loss_pct = ((speed_before - speed_min) / speed_before * 100.0) if speed_before and speed_min is not None and speed_before > 0 else None

        recovery_time_s = None
        if speed_before is not None:
            target = speed_before * 0.9
            for r in rows[end_idx:recov_end + 1]:
                if r[5] is not None and r[5] >= target:
                    recovery_time_s = (parse_ts(r[0]) - parse_ts(rows[end_idx][0])).total_seconds()
                    break

        maneuvers.append({
            "session_id": sid, "type": man_type,
            "start_utc": rows[start_idx][0], "end_utc": rows[end_idx][0],
            "duration_s": (parse_ts(rows[end_idx][0]) - parse_ts(rows[start_idx][0])).total_seconds(),
            "heading_before_deg": heading_before, "heading_after_deg": heading_after,
            "heading_change_deg": heading_change,
            "twa_before_deg": twa_before, "twa_after_deg": twa_after,
            "speed_before_kn": speed_before, "speed_min_kn": speed_min, "speed_recovered_kn": speed_recovered,
            "speed_loss_pct": speed_loss_pct, "recovery_time_s": recovery_time_s,
            "mark_wp_number": None, "distance_to_mark_m": None,
        })
    return maneuvers


def parse_ts(s):
    return datetime.fromisoformat(s)


def detect_roundings(rows, sid):
    """Local minima in distance-to-waypoint below ROUNDING_RADIUS_M."""
    dist = [r[6] for r in rows]
    n = len(rows)
    roundings = []
    i = 1
    while i < n - 1:
        if dist[i] is None:
            i += 1
            continue
        # find a contiguous stretch of non-null distances forming one approach
        if dist[i] <= ROUNDING_RADIUS_M and (dist[i - 1] is None or dist[i] <= dist[i - 1]) :
            # walk to local minimum
            j = i
            while j + 1 < n and dist[j + 1] is not None and dist[j + 1] <= dist[j]:
                j += 1
            min_idx = j
            # skip forward past this approach (until distance grows well past radius again)
            k = min_idx
            while k + 1 < n and dist[k + 1] is not None and dist[k + 1] < ROUNDING_RADIUS_M * 3:
                k += 1
            speed_at_mark = rows[min_idx][5]
            if speed_at_mark is None or speed_at_mark < MIN_UNDERWAY_SPEED_KN:
                i = k + 1
                continue
            roundings.append({
                "session_id": sid, "type": "rounding",
                "start_utc": rows[max(0, min_idx - 5)][0], "end_utc": rows[min(n - 1, min_idx + 5)][0],
                "duration_s": 10.0,
                "heading_before_deg": None, "heading_after_deg": None, "heading_change_deg": None,
                "twa_before_deg": None, "twa_after_deg": None,
                "speed_before_kn": rows[max(0, min_idx - 5)][5], "speed_min_kn": rows[min_idx][5],
                "speed_recovered_kn": rows[min(n - 1, min_idx + 10)][5],
                "speed_loss_pct": None, "recovery_time_s": None,
                "mark_wp_number": rows[min_idx][7], "distance_to_mark_m": dist[min_idx],
            })
            i = k + 1
        else:
            i += 1
    return roundings


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)

    cols = ["session_id", "type", "start_utc", "end_utc", "duration_s",
            "heading_before_deg", "heading_after_deg", "heading_change_deg",
            "twa_before_deg", "twa_after_deg",
            "speed_before_kn", "speed_min_kn", "speed_recovered_kn",
            "speed_loss_pct", "recovery_time_s", "mark_wp_number", "distance_to_mark_m"]

    for (sid,) in conn.execute("SELECT session_id FROM sessions ORDER BY session_id").fetchall():
        rows = load_series(conn, sid)
        maneuvers = detect_tacks_gybes(rows, sid)
        roundings = detect_roundings(rows, sid)
        all_events = maneuvers + roundings
        all_events.sort(key=lambda e: e["start_utc"])

        values = [tuple(e[c] for c in cols) for e in all_events]
        if values:
            conn.executemany(f"INSERT INTO maneuvers VALUES ({','.join('?'*len(cols))})", values)
        conn.commit()

        by_type = {}
        for e in all_events:
            by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        print(f"# Session {sid}: {len(all_events)} events -> {by_type}")

    conn.close()
    print(f"# Updated {DB_PATH} with maneuvers table")


if __name__ == "__main__":
    main()
