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

"""Boat-performance analysis for the Hull Analysis page: computes the
per-race port-vs-starboard performance heatmap (see hull_performance.py for
the pure aggregation/placement logic) and the season-wide hull drag
(average reaching speed by wind band across the season) directly from
nav_1hz/polar_performance -- cached into boat_setup_analysis.json so the
published site never needs a live database connection, the same way
build_race_db.update_speed_stats() caches tws_range/bsp_range into
races.json."""
import json
import sqlite3
from pathlib import Path

from race_registry import load_registry
from boat_setup_log import load_log
import hull_performance as hp

ROOT = Path(__file__).parent
DB_PATH = ROOT / "race_sessions.db"
ANALYSIS_PATH = ROOT / "boat_setup_analysis.json"

HULL_BANDS = [(0, 8), (8, 12), (12, 20), (20, None)]


def _band_label(lo, hi):
    return f"{lo}-{hi}" if hi is not None else f"{lo}+"


def _in_band(tws, lo, hi):
    return tws >= lo and (hi is None or tws < hi)


def _compute_hull_drag(conn, race_dates):
    """Average beam-reaching (80-100 deg TWA) speed per race, by wind
    band -- a season-long drag/fouling trend independent of the tack
    heatmap above."""
    rows = conn.execute(
        "SELECT session_id, tws_kn, twa_deg, stw_kn FROM nav_1hz "
        "WHERE stw_kn >= 1.5 AND tws_kn IS NOT NULL AND twa_deg IS NOT NULL"
    ).fetchall()

    hull_acc = {_band_label(lo, hi): {} for lo, hi in HULL_BANDS}
    for session_id, tws, twa, stw in rows:
        twa_abs = abs(twa)
        if not (80 <= twa_abs <= 100):
            continue
        for lo, hi in HULL_BANDS:
            if _in_band(tws, lo, hi):
                acc = hull_acc[_band_label(lo, hi)].setdefault(session_id, [0.0, 0])
                acc[0] += stw
                acc[1] += 1
                break

    hull_drag = {}
    for band, sessions in hull_acc.items():
        entries = [
            {"race_id": sid, "race_date": race_dates[sid], "avg_stw": round(s / n, 2), "n": n}
            for sid, (s, n) in sessions.items() if sid in race_dates
        ]
        entries.sort(key=lambda e: e["race_date"])
        hull_drag[band] = entries
    return hull_drag


def compute_and_cache():
    """Queries race_sessions.db and writes boat_setup_analysis.json: the
    port-vs-starboard performance heatmap's observations/sessions/events,
    plus the hull drag trend. No-op if the database doesn't exist (e.g. a
    view-only deployment calling this by mistake)."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)

    races = load_registry()["races"]
    sessions_by_id = {r["id"]: {"date": r["race_date"], "name": f"{r['race_date']} {r['series']}"} for r in races}
    race_dates = {r["id"]: r["race_date"] for r in races}

    perf_rows = conn.execute(
        "SELECT p.session_id, p.tws_kn, p.stw_kn, p.target_stw_kn, p.point_of_sail, n.tack "
        "FROM polar_performance p "
        "JOIN nav_1hz n ON n.session_id = p.session_id AND n.utc_timestamp = p.utc_timestamp "
        "WHERE p.point_of_sail IS NOT NULL"
    ).fetchall()
    hull_drag = _compute_hull_drag(conn, race_dates)
    conn.close()

    observations = hp.aggregate_observations(perf_rows, sessions_by_id)
    sessions_present = {o["sessionId"] for o in observations}
    sessions = hp.sort_sessions_reverse_chronological([
        {"id": rid, "date": info["date"], "name": info["name"]}
        for rid, info in sessions_by_id.items() if str(rid) in sessions_present
    ])
    events = hp.build_events_from_log(load_log()["entries"])

    data = {
        "sessions": [{"id": str(s["id"]), "date": s["date"], "name": s["name"]} for s in sessions],
        "performance_observations": observations,
        "events": events,
        "wind_bands_hull": [[lo, hi] for lo, hi in HULL_BANDS],
        "hull_drag": hull_drag,
    }
    ANALYSIS_PATH.write_text(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    data = compute_and_cache()
    if data is None:
        print("# race_sessions.db not found -- nothing to compute")
    else:
        print(f"# wrote {ANALYSIS_PATH.name}")
        print(f"#   {len(data['sessions'])} session(s), {len(data['performance_observations'])} observation(s), "
              f"{len(data['events'])} event(s)")
        for band, entries in data["hull_drag"].items():
            print(f"#   hull {band} kn: {len(entries)} race(s)")
