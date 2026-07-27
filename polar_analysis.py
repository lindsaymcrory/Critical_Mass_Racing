#!/usr/bin/env python3
"""Compares logged performance (nav_1hz) against the J/80 target polar
(j80_Polars.csv), writing a `polar_performance` table to race_sessions.db:
for every second with valid TWA/TWS/STW, the target boat speed for that
TWA/TWS, % of target achieved, point of sail (beat/reach/run), and -- for
beat/run only, where an "optimal angle" concept actually applies -- the
angle delta from the target beat/run angle at that wind speed.

Caveat surfaced in the summary, not hidden: Critical Mass is logged with a
2-person crew; J/80 polars are commonly generated/certified for a fuller
racing crew, so a gap from target speed may partly reflect that rather than
technique.
"""
import sqlite3
from pathlib import Path

from polar import PolarTable

DB_PATH = Path(__file__).parent / "race_sessions.db"
POLAR_PATH = Path(__file__).parent / "j80_Polars.csv"

BEAT_MAX_TWA = 75.0   # |TWA| at/below this -> beating (matches polar's beat-zone rows)
RUN_MIN_TWA = 120.0   # |TWA| at/above this -> running (matches polar's run-zone rows)
MIN_UNDERWAY_KN = 1.5

SCHEMA_SQL = """
DROP TABLE IF EXISTS polar_performance;
CREATE TABLE polar_performance (
    session_id INTEGER, utc_timestamp TEXT,
    twa_deg REAL, tws_kn REAL, stw_kn REAL,
    target_stw_kn REAL, pct_of_target REAL,
    point_of_sail TEXT,
    target_angle_deg REAL, angle_delta_deg REAL,
    out_of_polar_range INTEGER
);
CREATE INDEX idx_polar_perf ON polar_performance(session_id, utc_timestamp);
"""


def point_of_sail(twa_abs):
    if twa_abs <= BEAT_MAX_TWA:
        return "beat"
    if twa_abs >= RUN_MIN_TWA:
        return "run"
    return "reach"


def main():
    polar = PolarTable(POLAR_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)

    for (sid,) in conn.execute("SELECT session_id FROM sessions ORDER BY session_id").fetchall():
        cur = conn.execute(
            "SELECT utc_timestamp, twa_deg, tws_kn, stw_kn FROM nav_1hz "
            "WHERE session_id=? AND twa_deg IS NOT NULL AND tws_kn IS NOT NULL AND stw_kn IS NOT NULL "
            "AND stw_kn >= ? ORDER BY utc_timestamp",
            (sid, MIN_UNDERWAY_KN),
        )
        rows = []
        for ts, twa, tws, stw in cur.fetchall():
            twa_abs = abs(twa)
            target, out_of_range = polar.target_speed(twa_abs, tws)
            pct = (stw / target * 100.0) if target > 0 else None
            pos = point_of_sail(twa_abs)

            target_angle = None
            angle_delta = None
            if pos == "beat":
                target_angle = polar.beat_angle(tws)
                angle_delta = twa_abs - target_angle
            elif pos == "run":
                target_angle = polar.run_angle(tws)
                angle_delta = twa_abs - target_angle

            rows.append((sid, ts, twa, tws, stw, round(target, 3), round(pct, 1) if pct is not None else None,
                         pos, round(target_angle, 1) if target_angle is not None else None,
                         round(angle_delta, 1) if angle_delta is not None else None,
                         1 if out_of_range else 0))

        conn.executemany(f"INSERT INTO polar_performance VALUES ({','.join('?'*11)})", rows)
        conn.commit()

        n = len(rows)
        beat_pct = [r[6] for r in rows if r[7] == "beat" and r[6] is not None]
        run_pct = [r[6] for r in rows if r[7] == "run" and r[6] is not None]
        reach_pct = [r[6] for r in rows if r[7] == "reach" and r[6] is not None]
        beat_delta = [r[9] for r in rows if r[7] == "beat" and r[9] is not None]
        run_delta = [r[9] for r in rows if r[7] == "run" and r[9] is not None]

        def avg(v):
            return f"{sum(v) / len(v):.1f}" if v else "  -- "

        print(f"# Session {sid}: {n} rows underway")
        print(f"#   beat : n={len(beat_pct):5d}  avg %target={avg(beat_pct):>6}  avg angle delta={avg(beat_delta):>6} deg")
        print(f"#   reach: n={len(reach_pct):5d}  avg %target={avg(reach_pct):>6}")
        print(f"#   run  : n={len(run_pct):5d}  avg %target={avg(run_pct):>6}  avg angle delta={avg(run_delta):>6} deg")

    conn.close()
    print(f"# Updated {DB_PATH} with polar_performance table")


if __name__ == "__main__":
    main()
