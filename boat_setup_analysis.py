#!/usr/bin/env python3
"""Season-wide boat-performance analysis for the Boat Check page: computes
port-vs-starboard tack symmetry by wind band and angle, and hull drag
(average reaching speed by wind band across the season) directly from
nav_1hz -- cached into boat_setup_analysis.json so the published site never
needs a live database connection, the same way
build_race_db.update_speed_stats() caches tws_range/bsp_range into
races.json."""
import json
import sqlite3
from pathlib import Path

from race_registry import load_registry

ROOT = Path(__file__).parent
DB_PATH = ROOT / "race_sessions.db"
ANALYSIS_PATH = ROOT / "boat_setup_analysis.json"

TACK_BANDS = [(0, 6), (6, 12), (12, 20), (20, None)]
HULL_BANDS = [(0, 8), (8, 12), (12, 20), (20, None)]
ANGLE_BUCKETS = list(range(20, 181, 10))


def _band_label(lo, hi):
    return f"{lo}-{hi}" if hi is not None else f"{lo}+"


def _in_band(tws, lo, hi):
    return tws >= lo and (hi is None or tws < hi)


def _nearest_angle_bucket(twa_abs):
    if twa_abs < 15:
        return None
    return min(ANGLE_BUCKETS, key=lambda a: abs(a - twa_abs))


def compute_and_cache():
    """Runs the two grouped queries against race_sessions.db across every
    race and writes boat_setup_analysis.json. No-op if the database doesn't
    exist (e.g. a view-only deployment calling this by mistake)."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT session_id, tws_kn, twa_deg, stw_kn, tack FROM nav_1hz "
        "WHERE stw_kn >= 1.5 AND tws_kn IS NOT NULL AND twa_deg IS NOT NULL"
    ).fetchall()
    conn.close()

    tack_acc = {
        _band_label(lo, hi): {
            "port": {a: [0.0, 0] for a in ANGLE_BUCKETS},
            "starboard": {a: [0.0, 0] for a in ANGLE_BUCKETS},
        }
        for lo, hi in TACK_BANDS
    }
    hull_acc = {_band_label(lo, hi): {} for lo, hi in HULL_BANDS}

    for session_id, tws, twa, stw, tack in rows:
        if tack not in ("port", "starboard"):
            continue
        twa_abs = abs(twa)

        for lo, hi in TACK_BANDS:
            if _in_band(tws, lo, hi):
                bucket = _nearest_angle_bucket(twa_abs)
                if bucket is not None:
                    acc = tack_acc[_band_label(lo, hi)][tack][bucket]
                    acc[0] += stw
                    acc[1] += 1
                break

        if 80 <= twa_abs <= 100:
            for lo, hi in HULL_BANDS:
                if _in_band(tws, lo, hi):
                    acc = hull_acc[_band_label(lo, hi)].setdefault(session_id, [0.0, 0])
                    acc[0] += stw
                    acc[1] += 1
                    break

    tack_performance = {
        band: {
            side: [
                {"angle": a, "avg_stw": round(s / n, 2), "n": n}
                for a, (s, n) in buckets.items() if n > 0
            ]
            for side, buckets in sides.items()
        }
        for band, sides in tack_acc.items()
    }

    race_dates = {r["id"]: r["race_date"] for r in load_registry()["races"]}
    hull_drag = {}
    for band, sessions in hull_acc.items():
        entries = [
            {"race_id": sid, "race_date": race_dates[sid], "avg_stw": round(s / n, 2), "n": n}
            for sid, (s, n) in sessions.items() if sid in race_dates
        ]
        entries.sort(key=lambda e: e["race_date"])
        hull_drag[band] = entries

    data = {
        "wind_bands_tack": [[lo, hi] for lo, hi in TACK_BANDS],
        "wind_bands_hull": [[lo, hi] for lo, hi in HULL_BANDS],
        "angle_buckets": ANGLE_BUCKETS,
        "tack_performance": tack_performance,
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
        for band, sides in data["tack_performance"].items():
            n_port = sum(p["n"] for p in sides["port"])
            n_stbd = sum(p["n"] for p in sides["starboard"])
            print(f"#   tack {band} kn: port n={n_port}, starboard n={n_stbd}")
        for band, entries in data["hull_drag"].items():
            print(f"#   hull {band} kn: {len(entries)} race(s)")
