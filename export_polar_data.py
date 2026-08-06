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

"""Exports polar_performance + target curves to compact JSON for the polar
diagram artifact. Actual points keep signed TWA (port/starboard) so they can
be mirrored onto a classic full polar "bat-wing" plot; target curves are
drawn at a few representative TWS bands spanning what was actually sailed.
"""
import json
import sqlite3
from pathlib import Path

from polar import PolarTable

DB_PATH = Path(__file__).parent / "race_sessions.db"
POLAR_PATH = Path(__file__).parent / "j80_Polars.csv"
OUT_PATH = Path(__file__).parent / "polar_data.json"

REFERENCE_TWS = [8, 12, 16]
POINT_STEP = 2  # keep 1-of-every-N seconds of points (still dense enough for a scatter)


def export_for_race(conn, polar, sid):
    """Returns the polar-data dict for one race, or None if it has no
    polar_performance rows."""
    meta = conn.execute(
        "SELECT race_date, local_start_time FROM sessions WHERE session_id=?", (sid,)
    ).fetchone()
    if meta is None:
        return None
    race_date, local_start = meta

    cur = conn.execute(
        "SELECT p.twa_deg, p.tws_kn, p.stw_kn, p.pct_of_target, p.point_of_sail, p.out_of_polar_range, n.tack "
        "FROM polar_performance p JOIN nav_1hz n "
        "ON n.session_id = p.session_id AND n.utc_timestamp = p.utc_timestamp "
        "WHERE p.session_id=? ORDER BY p.utc_timestamp", (sid,)
    )
    all_rows = cur.fetchall()
    if not all_rows:
        return None

    points = []
    for i, (twa, tws, stw, pct, pos, oor, tack) in enumerate(all_rows):
        if i % POINT_STEP != 0:
            continue
        points.append([round(twa, 1), round(tws, 1), round(stw, 2),
                       round(pct, 0) if pct is not None else None,
                       tack[0] if tack else None, pos[0], oor])

    curves = []
    for tws in REFERENCE_TWS:
        curves.append({
            "tws": tws,
            "points": [[twa, round(spd, 2)] for twa, spd in polar.curve_points(tws)],
            "beat_angle": round(polar.beat_angle(tws), 1),
            "beat_vmg": round(polar.beat_vmg_target(tws), 2),
            "run_angle": round(polar.run_angle(tws), 1),
            "run_vmg": round(polar.run_vmg_target(tws), 2),
        })

    def stats_for(pos):
        # computed from the full (non-decimated) row set for accuracy
        vals = [pct for (_twa, _tws, _stw, pct, _pos, _oor, _tack) in all_rows
                if _pos == pos and pct is not None]
        return {"n": len(vals), "avg_pct": round(sum(vals) / len(vals), 1) if vals else None}

    return {
        "session_id": sid, "race_date": race_date, "local_start_time": local_start,
        "points": points,
        "curves": curves,
        "stats": {"beat": stats_for("beat"), "reach": stats_for("reach"), "run": stats_for("run")},
    }


def main():
    polar = PolarTable(POLAR_PATH)
    conn = sqlite3.connect(DB_PATH)
    sids = [row[0] for row in conn.execute("SELECT session_id FROM sessions ORDER BY session_id").fetchall()]

    sessions = []
    for sid in sids:
        s = export_for_race(conn, polar, sid)
        if s:
            sessions.append(s)
            print(f"# session {sid}: {len(s['points'])} points, curves at {REFERENCE_TWS} kt")

    OUT_PATH.write_text(json.dumps(sessions, separators=(",", ":")))
    print(f"# Wrote {OUT_PATH} ({OUT_PATH.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
