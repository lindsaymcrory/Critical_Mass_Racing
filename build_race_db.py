#!/usr/bin/env python3
"""Builds a SQLite database of decoded NMEA2000 data for every race in the
registry (races.json, managed by race_registry.py / the web app's Add Race
flow), for maneuver, strategy/course, and polar analysis. Always does a full
rebuild from races.json + ebl_data/ -- simple and fast enough (~1min for
~90MB of EBL data) that incremental updates aren't worth the complexity.

Tables:
  sessions            -- one row per race, with its file range and UTC span
  position             -- 129025 Position, Rapid Update (high-rate lat/lon)
  gnss                  -- 129029 GNSS Position Data (fix quality, altitude)
  heading               -- 127250 Vessel Heading
  rate_of_turn          -- 127251 Rate of Turn
  cog_sog               -- 129026 COG & SOG, Rapid Update
  boat_speed            -- 128259 Speed (through water / over ground)
  wind                  -- 130306 Wind Data (apparent, as transmitted)
  attitude              -- 127257 Attitude (yaw/pitch/roll -- roll = heel)
  depth                 -- 128267 Water Depth
  cross_track_error     -- 129283 Cross Track Error
  navigation_data       -- 129284 Navigation Data (bearing/distance to mark)
  route_wp_info         -- 129285 Navigation - Route/WP Information (raw)
  waypoints             -- derived: distinct named marks from route_wp_info
  nav_1hz               -- derived: all of the above merged onto a 1Hz grid,
                           with computed true wind (TWA/TWS) and tack

All angles are in degrees, speeds in knots (canboat's native rad/m/s
converted via ebl2csv.units, same as ebl_to_csv.py's default behavior).
"""
import math
import sqlite3
import sys
from bisect import bisect_right
from datetime import datetime, timedelta
from pathlib import Path

import boat_setup_analysis
from ebl2csv import ebl_reader
from ebl2csv.decoder import decode_message
from ebl2csv.fastpacket import FastPacketAssembler
from ebl2csv.schema import CanboatSchema
from ebl_store import EBL_DATA_DIR
from race_registry import load_registry, save_registry

ROOT = Path(__file__).parent
EBL_DIR = EBL_DATA_DIR
PGNS_PATH = ROOT / "canboat.json"
DB_PATH = ROOT / "race_sessions.db"

# Forward-fill on the 1Hz grid is cut off if the last real reading is older
# than this -- otherwise a multi-minute dropout (e.g. the dead battery gap
# on 20-Jul) would silently smear one stale reading across the whole gap.
MAX_STALENESS_S = 10.0


def load_sessions():
    """Race registry entries, reshaped into the session_cfg dict this
    module's functions expect (session_id <- race id)."""
    registry = load_registry()
    return [
        {
            "session_id": r["id"],
            "race_date": r["race_date"],
            "local_start_time": r["local_start_time"],
            "series": r["series"],
            "boat": r.get("boat", "Critical Mass"),
            "crew_count": r.get("crew_count", 2),
            "timezone": r.get("timezone", "America/Halifax (ADT, UTC-3)"),
            "files": r["files"],
            "notes": r.get("notes", ""),
            "trim_end_utc": r.get("trim_end_utc"),
            "trim_start_utc": r.get("trim_start_utc"),
        }
        for r in registry["races"]
    ]

SCHEMA_SQL = """
CREATE TABLE sessions (
    session_id INTEGER PRIMARY KEY,
    race_date TEXT, local_start_time TEXT, series TEXT, boat TEXT, crew_count INTEGER,
    timezone TEXT, utc_start TEXT, utc_end TEXT, file_start TEXT, file_end TEXT, notes TEXT
);
CREATE TABLE position (
    session_id INTEGER, utc_timestamp TEXT, latitude REAL, longitude REAL
);
CREATE TABLE gnss (
    session_id INTEGER, utc_timestamp TEXT, latitude REAL, longitude REAL,
    altitude_m REAL, gnss_type TEXT, method TEXT, integrity TEXT,
    number_of_svs INTEGER, hdop REAL, pdop REAL, geoidal_separation_m REAL
);
CREATE TABLE heading (
    session_id INTEGER, utc_timestamp TEXT, heading_deg REAL,
    deviation_deg REAL, variation_deg REAL, reference TEXT
);
CREATE TABLE rate_of_turn (
    session_id INTEGER, utc_timestamp TEXT, rot_deg_s REAL
);
CREATE TABLE cog_sog (
    session_id INTEGER, utc_timestamp TEXT, cog_deg REAL, cog_reference TEXT, sog_kn REAL
);
CREATE TABLE boat_speed (
    session_id INTEGER, utc_timestamp TEXT, speed_water_kn REAL,
    speed_ground_kn REAL, speed_water_type TEXT
);
CREATE TABLE wind (
    session_id INTEGER, utc_timestamp TEXT, wind_speed_kn REAL,
    wind_angle_deg REAL, reference TEXT
);
CREATE TABLE attitude (
    session_id INTEGER, utc_timestamp TEXT, yaw_deg REAL, pitch_deg REAL, roll_deg REAL
);
CREATE TABLE depth (
    session_id INTEGER, utc_timestamp TEXT, depth_m REAL, offset_m REAL
);
CREATE TABLE cross_track_error (
    session_id INTEGER, utc_timestamp TEXT, xte_m REAL, xte_mode TEXT, navigation_terminated TEXT
);
CREATE TABLE navigation_data (
    session_id INTEGER, utc_timestamp TEXT,
    distance_to_waypoint_m REAL,
    bearing_origin_to_dest_deg REAL, bearing_position_to_dest_deg REAL,
    origin_waypoint_number INTEGER, destination_waypoint_number INTEGER,
    destination_latitude REAL, destination_longitude REAL,
    waypoint_closing_velocity_kn REAL,
    perpendicular_crossed TEXT, arrival_circle_entered TEXT, calculation_type TEXT
);
CREATE TABLE route_wp_info (
    session_id INTEGER, utc_timestamp TEXT, route_name TEXT,
    wp_id INTEGER, wp_name TEXT, wp_latitude REAL, wp_longitude REAL,
    nitems INTEGER, database_id INTEGER, route_id INTEGER, nav_direction TEXT
);
CREATE TABLE waypoints (
    session_id INTEGER, wp_id INTEGER, wp_name TEXT,
    latitude REAL, longitude REAL, first_seen_utc TEXT, last_seen_utc TEXT
);
CREATE TABLE nav_1hz (
    session_id INTEGER, utc_timestamp TEXT, elapsed_s REAL,
    latitude REAL, longitude REAL,
    heading_deg REAL, rot_deg_s REAL,
    cog_deg REAL, sog_kn REAL, stw_kn REAL,
    awa_deg REAL, aws_kn REAL, twa_deg REAL, tws_kn REAL, tack TEXT,
    heel_deg REAL, pitch_deg REAL,
    depth_m REAL, xte_m REAL,
    distance_to_wp_m REAL, destination_wp_number INTEGER
);
"""

INDEX_SQL = """
CREATE INDEX idx_position ON position(session_id, utc_timestamp);
CREATE INDEX idx_gnss ON gnss(session_id, utc_timestamp);
CREATE INDEX idx_heading ON heading(session_id, utc_timestamp);
CREATE INDEX idx_rot ON rate_of_turn(session_id, utc_timestamp);
CREATE INDEX idx_cogsog ON cog_sog(session_id, utc_timestamp);
CREATE INDEX idx_speed ON boat_speed(session_id, utc_timestamp);
CREATE INDEX idx_wind ON wind(session_id, utc_timestamp);
CREATE INDEX idx_attitude ON attitude(session_id, utc_timestamp);
CREATE INDEX idx_depth ON depth(session_id, utc_timestamp);
CREATE INDEX idx_xte ON cross_track_error(session_id, utc_timestamp);
CREATE INDEX idx_navdata ON navigation_data(session_id, utc_timestamp);
CREATE INDEX idx_routewp ON route_wp_info(session_id, utc_timestamp);
CREATE INDEX idx_waypoints ON waypoints(session_id, wp_id);
CREATE INDEX idx_nav1hz ON nav_1hz(session_id, utc_timestamp);
"""


def iso(dt: datetime) -> str:
    return dt.isoformat(sep=" ", timespec="milliseconds")


def decode_session_messages(schema, files, trim_end=None, trim_start=None):
    """Yields (utc_datetime, header, fields_dict) for every decodable message
    across all files in a session, in file order (files must already be
    chronologically ordered). Messages after trim_end (a datetime, from the
    race's saved trim -- excludes the post-race trip to the dock) are
    dropped, as are messages before trim_start (excludes time at the dock/
    mooring, or transiting to the start area, before the race itself)."""
    assembler = FastPacketAssembler(schema.fast_packet_pgns())
    for fname in files:
        path = EBL_DIR / fname
        data = path.read_bytes()
        for frame in ebl_reader.iter_raw_frames(data):
            header = frame["header"]
            assembled = assembler.assemble(header, frame["payload"], frame["elapsed_ms"])
            if assembled is None:
                continue
            full_header, full_data = assembled
            utc = frame["utc"]
            if utc is None or utc.year < 2000:
                continue
            if trim_end is not None and utc > trim_end:
                continue
            if trim_start is not None and utc < trim_start:
                continue
            pgn_def = schema.find_pgn(full_header.pgn, full_data)
            if pgn_def is None:
                continue
            try:
                fields = decode_message(pgn_def, full_data, schema, convert_units=True)
            except Exception:
                continue
            fields_by_key = {f.key: f.value for f in fields}
            yield utc, full_header, fields_by_key


def build_session(conn, schema, session_cfg):
    sid = session_cfg["session_id"]
    trim_end = None
    if session_cfg.get("trim_end_utc"):
        trim_end = datetime.fromisoformat(session_cfg["trim_end_utc"])
    trim_start = None
    if session_cfg.get("trim_start_utc"):
        trim_start = datetime.fromisoformat(session_cfg["trim_start_utc"])
    trim_note = ""
    if trim_start and trim_end:
        trim_note = f" (trimmed to {session_cfg['trim_start_utc']} -> {session_cfg['trim_end_utc']})"
    elif trim_end:
        trim_note = f" (trimmed at {session_cfg['trim_end_utc']})"
    elif trim_start:
        trim_note = f" (trimmed from {session_cfg['trim_start_utc']})"
    print(f"# Session {sid} ({session_cfg['race_date']}): decoding {len(session_cfg['files'])} files{trim_note}...")

    rows = {
        "position": [], "gnss": [], "heading": [], "rate_of_turn": [], "cog_sog": [],
        "boat_speed": [], "wind": [], "attitude": [], "depth": [],
        "cross_track_error": [], "navigation_data": [], "route_wp_info": [],
    }
    utc_min = None
    utc_max = None
    n = 0

    for utc, header, fv in decode_session_messages(schema, session_cfg["files"], trim_end, trim_start):
        n += 1
        if utc_min is None or utc < utc_min:
            utc_min = utc
        if utc_max is None or utc > utc_max:
            utc_max = utc
        ts = iso(utc)
        pgn = header.pgn

        if pgn == 129025:
            rows["position"].append((sid, ts, fv.get("latitude"), fv.get("longitude")))
        elif pgn == 129029:
            rows["gnss"].append((sid, ts, fv.get("latitude"), fv.get("longitude"), fv.get("altitude"),
                                  fv.get("gnssType"), fv.get("method"), fv.get("integrity"),
                                  fv.get("numberOfSvs"), fv.get("hdop"), fv.get("pdop"),
                                  fv.get("geoidalSeparation")))
        elif pgn == 127250:
            rows["heading"].append((sid, ts, fv.get("heading"), fv.get("deviation"),
                                     fv.get("variation"), fv.get("reference")))
        elif pgn == 127251:
            rows["rate_of_turn"].append((sid, ts, fv.get("rate")))
        elif pgn == 129026:
            rows["cog_sog"].append((sid, ts, fv.get("cog"), fv.get("cogReference"), fv.get("sog")))
        elif pgn == 128259:
            rows["boat_speed"].append((sid, ts, fv.get("speedWaterReferenced"),
                                        fv.get("speedGroundReferenced"), fv.get("speedWaterReferencedType")))
        elif pgn == 130306:
            rows["wind"].append((sid, ts, fv.get("windSpeed"), fv.get("windAngle"), fv.get("reference")))
        elif pgn == 127257:
            rows["attitude"].append((sid, ts, fv.get("yaw"), fv.get("pitch"), fv.get("roll")))
        elif pgn == 128267:
            rows["depth"].append((sid, ts, fv.get("depth"), fv.get("offset")))
        elif pgn == 129283:
            rows["cross_track_error"].append((sid, ts, fv.get("xte"), fv.get("xteMode"),
                                               fv.get("navigationTerminated")))
        elif pgn == 129284:
            rows["navigation_data"].append((
                sid, ts, fv.get("distanceToWaypoint"),
                fv.get("bearingOriginToDestinationWaypoint"), fv.get("bearingPositionToDestinationWaypoint"),
                fv.get("originWaypointNumber"), fv.get("destinationWaypointNumber"),
                fv.get("destinationLatitude"), fv.get("destinationLongitude"),
                fv.get("waypointClosingVelocity"),
                fv.get("perpendicularCrossed"), fv.get("arrivalCircleEntered"), fv.get("calculationType"),
            ))
        elif pgn == 129285:
            # repeating WP group -> keys "wpId #1"/"wpName #1"/... "wpId #2"/... one row per WP entry
            n_items = fv.get("nitems")
            i = 1
            while f"wpId #{i}" in fv or f"wpName #{i}" in fv or f"wpLatitude #{i}" in fv:
                rows["route_wp_info"].append((
                    sid, ts, fv.get("routeName"),
                    fv.get(f"wpId #{i}"), fv.get(f"wpName #{i}"),
                    fv.get(f"wpLatitude #{i}"), fv.get(f"wpLongitude #{i}"),
                    n_items, fv.get("databaseId"), fv.get("routeId"),
                    fv.get("navigationDirectionInRoute"),
                ))
                i += 1
                if i > 8:  # safety valve
                    break

    if utc_min is None:
        raise ValueError(f"race {sid}: no decodable messages left "
                         f"(is the saved trim earlier than the recording start?)")
    print(f"#   {n:,} decodable messages, {iso(utc_min)} -> {iso(utc_max)}")

    for table, values in rows.items():
        if values:
            placeholders = ",".join("?" * len(values[0]))
            conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", values)
    conn.commit()

    conn.execute(
        "UPDATE sessions SET utc_start=?, utc_end=? WHERE session_id=?",
        (iso(utc_min), iso(utc_max), sid),
    )
    conn.commit()
    return utc_min, utc_max


def build_waypoints(conn, sid):
    cur = conn.execute(
        "SELECT wp_id, wp_name, AVG(wp_latitude), AVG(wp_longitude), MIN(utc_timestamp), MAX(utc_timestamp) "
        "FROM route_wp_info WHERE session_id=? AND wp_latitude IS NOT NULL "
        "GROUP BY wp_id, wp_name ORDER BY MIN(utc_timestamp)",
        (sid,),
    )
    rows = [(sid,) + tuple(r) for r in cur.fetchall()]
    if rows:
        conn.executemany("INSERT INTO waypoints VALUES (?,?,?,?,?,?,?)", rows)
        conn.commit()
    return len(rows)


def _asof_series(conn, table, cols, sid):
    """Returns (timestamps: list[datetime], values: list[tuple], width: int) sorted by time."""
    col_list = ", ".join(cols)
    cur = conn.execute(f"SELECT utc_timestamp, {col_list} FROM {table} WHERE session_id=? ORDER BY utc_timestamp", (sid,))
    ts, vals = [], []
    for row in cur.fetchall():
        ts.append(datetime.fromisoformat(row[0]))
        vals.append(row[1:])
    return ts, vals, len(cols)


def _lookup(ts_list, val_list, width, t, max_staleness):
    """Latest value at or before time t, or all-None if none / too stale."""
    idx = bisect_right(ts_list, t) - 1
    if idx < 0:
        return (None,) * width
    if (t - ts_list[idx]).total_seconds() > max_staleness:
        return (None,) * width
    return val_list[idx]


def true_wind(awa_deg, aws_kn, stw_kn):
    """awa_deg is canboat's native unsigned 0-360 (0=dead ahead, clockwise).
    twa_deg is returned SIGNED in (-180, 180] (positive = wind from starboard),
    the conventional representation for polar/maneuver analysis -- unlike
    awa_deg, it must NOT be compared with plain abs()<90 for "upwind" without
    accounting for wrap-around, since -170 and 170 are both near dead-astern."""
    if awa_deg is None or aws_kn is None or stw_kn is None:
        return None, None, None
    awa_rad = math.radians(awa_deg)
    ax = aws_kn * math.cos(awa_rad)
    ay = aws_kn * math.sin(awa_rad)
    tx = ax - stw_kn  # subtract boat's own motion (boat-relative frame: heading axis)
    ty = ay
    tws = math.hypot(tx, ty)
    twa = ((math.degrees(math.atan2(ty, tx)) + 180) % 360) - 180
    tack = "starboard" if awa_deg < 180 else "port"
    return twa, tws, tack


def build_nav_1hz(conn, sid, utc_min, utc_max):
    channels = {
        "position": ("position", ["latitude", "longitude"]),
        "heading": ("heading", ["heading_deg"]),
        "rot": ("rate_of_turn", ["rot_deg_s"]),
        "cogsog": ("cog_sog", ["cog_deg", "sog_kn"]),
        "speed": ("boat_speed", ["speed_water_kn"]),
        "wind": ("wind", ["wind_speed_kn", "wind_angle_deg"]),
        "attitude": ("attitude", ["roll_deg", "pitch_deg"]),
        "depth": ("depth", ["depth_m"]),
        "xte": ("cross_track_error", ["xte_m"]),
        "navdata": ("navigation_data", ["distance_to_waypoint_m", "destination_waypoint_number"]),
    }
    series = {name: _asof_series(conn, table, cols, sid) for name, (table, cols) in channels.items()}

    t0 = utc_min.replace(microsecond=0)
    t1 = utc_max.replace(microsecond=0)
    rows = []
    t = t0
    while t <= t1:
        lat, lon = _lookup(*series["position"], t, MAX_STALENESS_S)
        heading, = _lookup(*series["heading"], t, MAX_STALENESS_S)
        rot, = _lookup(*series["rot"], t, MAX_STALENESS_S)
        cog, sog = _lookup(*series["cogsog"], t, MAX_STALENESS_S)
        stw, = _lookup(*series["speed"], t, MAX_STALENESS_S)
        aws, awa = _lookup(*series["wind"], t, MAX_STALENESS_S)
        heel, pitch = _lookup(*series["attitude"], t, MAX_STALENESS_S)
        depth, = _lookup(*series["depth"], t, MAX_STALENESS_S)
        xte, = _lookup(*series["xte"], t, MAX_STALENESS_S)
        dist_wp, dest_wp_num = _lookup(*series["navdata"], t, MAX_STALENESS_S)

        twa, tws, tack = true_wind(awa, aws, stw)

        rows.append((
            sid, iso(t), (t - t0).total_seconds(),
            lat, lon, heading, rot, cog, sog, stw,
            awa, aws, twa, tws, tack,
            heel, pitch, depth, xte, dist_wp, dest_wp_num,
        ))
        t += timedelta(seconds=1)

    conn.executemany(f"INSERT INTO nav_1hz VALUES ({','.join('?'*21)})", rows)
    conn.commit()
    return len(rows)


def update_speed_stats(conn, race_id):
    """Caches this race's TWS/boat-speed ranges (underway samples only) into
    races.json, so the homepage can show them without needing a database
    connection -- it's a static, view-only summary shipped with the site."""
    tws_min, tws_max, stw_min, stw_max = conn.execute(
        "SELECT MIN(tws_kn), MAX(tws_kn), MIN(stw_kn), MAX(stw_kn) FROM nav_1hz "
        "WHERE session_id=? AND stw_kn >= 1.5 AND tws_kn IS NOT NULL", (race_id,)
    ).fetchone()

    registry = load_registry()
    race = next((r for r in registry["races"] if r["id"] == race_id), None)
    if race is None:
        return
    if tws_min is None:
        race.pop("tws_range", None)
        race.pop("bsp_range", None)
    else:
        race["tws_range"] = [round(tws_min, 1), round(tws_max, 1)]
        race["bsp_range"] = [round(stw_min, 1), round(stw_max, 1)]
    save_registry(registry)


# every table keyed by session_id; used by rebuild_race to surgically remove
# one race before re-inserting it (maneuvers/polar_performance are excluded:
# their scripts DROP and rebuild the whole table from nav_1hz afterwards)
SESSION_TABLES = [
    "sessions", "position", "gnss", "heading", "rate_of_turn", "cog_sog",
    "boat_speed", "wind", "attitude", "depth", "cross_track_error",
    "navigation_data", "route_wp_info", "waypoints", "nav_1hz",
]


def rebuild_race(race_id):
    """Deletes and re-decodes a single race in the existing database --
    much faster than main() when only one race changed (e.g. a saved trim),
    since it doesn't re-decode every other race's EBL files."""
    matches = [s for s in load_sessions() if s["session_id"] == race_id]
    if not matches:
        raise ValueError(f"race {race_id} not in registry")
    cfg = matches[0]

    if not DB_PATH.exists():
        main()
        return

    conn = sqlite3.connect(DB_PATH)
    for table in SESSION_TABLES:
        conn.execute(f"DELETE FROM {table} WHERE session_id=?", (race_id,))
    conn.commit()

    conn.execute(
        "INSERT INTO sessions (session_id, race_date, local_start_time, series, boat, crew_count, "
        "timezone, file_start, file_end, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cfg["session_id"], cfg["race_date"], cfg["local_start_time"], cfg["series"], cfg["boat"],
         cfg["crew_count"], cfg["timezone"], cfg["files"][0], cfg["files"][-1], cfg["notes"]),
    )
    conn.commit()

    schema = CanboatSchema(str(PGNS_PATH))
    utc_min, utc_max = build_session(conn, schema, cfg)
    n_wp = build_waypoints(conn, race_id)
    n_1hz = build_nav_1hz(conn, race_id, utc_min, utc_max)
    update_speed_stats(conn, race_id)
    print(f"#   {n_wp} distinct waypoints, {n_1hz:,} rows in nav_1hz")
    conn.close()
    boat_setup_analysis.compute_and_cache()


def main(race_ids=None):
    """Full rebuild of race_sessions.db from the current registry -- this
    always deletes and recreates the whole database, so race_ids is for
    isolated/test runs only (e.g. rebuilding just one race to inspect it
    quickly); passing it from the app would drop every OTHER race from the
    db. The app must always call main() with no arguments."""
    sessions = load_sessions()
    if race_ids is not None:
        sessions = [s for s in sessions if s["session_id"] in race_ids]

    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)

    for cfg in sessions:
        conn.execute(
            "INSERT INTO sessions (session_id, race_date, local_start_time, series, boat, crew_count, "
            "timezone, file_start, file_end, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cfg["session_id"], cfg["race_date"], cfg["local_start_time"], cfg["series"], cfg["boat"],
             cfg["crew_count"], cfg["timezone"], cfg["files"][0], cfg["files"][-1], cfg["notes"]),
        )
    conn.commit()

    schema = CanboatSchema(str(PGNS_PATH))

    for cfg in sessions:
        utc_min, utc_max = build_session(conn, schema, cfg)
        n_wp = build_waypoints(conn, cfg["session_id"])
        n_1hz = build_nav_1hz(conn, cfg["session_id"], utc_min, utc_max)
        update_speed_stats(conn, cfg["session_id"])
        print(f"#   {n_wp} distinct waypoints, {n_1hz:,} rows in nav_1hz\n")

    conn.executescript(INDEX_SQL)
    conn.commit()

    print("# Row counts:")
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        print(f"    {table:<20} {count:>10,}")

    conn.close()
    print(f"\n# Wrote {DB_PATH}")

    boat_setup_analysis.compute_and_cache()
    print(f"# Wrote {boat_setup_analysis.ANALYSIS_PATH.name}")


if __name__ == "__main__":
    main()
