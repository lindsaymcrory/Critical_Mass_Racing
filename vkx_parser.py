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

"""Parses Vakaros .vkx telemetry log files (the binary format Vakaros
switched to going forward, replacing the .csv track export). Implements the
VKX 1.4 row format documented at github.com/vakaros/vkx: a flat sequence of
[U1 key][fixed-size payload] rows, little-endian, with 0xFF page-header and
0xFE page-terminator rows sprinkled in roughly every 2kB.

Only the row types this app actually uses are decoded (0x02 position/
orientation, 0x04 race timer events); every other known row key is skipped
by its documented fixed size so the byte stream stays in sync. All payload
sizes below come straight from the spec's row tables (including the
"internal use" keys listed there) -- an unrecognized key means either file
corruption or a newer VKX revision this parser doesn't know about yet, and
is treated as an error rather than silently guessed at.

Decoded heading/heel/pitch come from the 0x02 row's orientation quaternion
(true NED frame) via a standard yaw-pitch-roll Euler conversion -- verified
byte-for-byte against Vakaros' own CSV export (hdg_true/heel/trim columns)
for the one race where both exports exist."""
import math
import struct
from datetime import datetime, timezone
from pathlib import Path

# key -> total payload size in bytes (excludes the 1-byte key itself)
PAYLOAD_SIZES = {
    0xFF: 7,   # page header
    0xFE: 2,   # page terminator
    0x02: 44,  # position/velocity/orientation
    0x03: 20,  # declination
    0x04: 13,  # race timer event
    0x05: 17,  # line position
    0x06: 18,  # shift angle
    0x08: 13,  # device configuration
    0x0A: 16,  # wind
    0x0B: 16,  # speed through water
    0x0C: 12,  # depth
    0x0F: 16,  # load
    0x10: 12,  # temperature
    # internal/reserved, per spec's "Vakaros Internal Messages" table
    0x01: 32, 0x07: 12, 0x0E: 16, 0x20: 13, 0x21: 52,
}

RACE_TIMER_EVENTS = {0: "RESET", 1: "START", 2: "SYNC", 3: "RACE_START", 4: "RACE_END"}

_POS_STRUCT = struct.Struct("<Qiifffffff")  # ts, lat_e7, lon_e7, sog, cog, alt, qw, qx, qy, qz
_TIMER_STRUCT = struct.Struct("<QBi")       # ts, event_type, timer_s
_LINE_STRUCT = struct.Struct("<QBff")       # ts, end_type (0=pin, 1=boat), lat, lon

LINE_END_NAMES = {0: "pin", 1: "boat"}


def _quat_to_euler_deg(w, x, y, z):
    """NED-frame quaternion -> (roll, pitch, yaw) in degrees, standard
    yaw-pitch-roll (ZYX) Euler decomposition."""
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def iter_rows(path):
    """Yields (key, payload_bytes) for every row in a .vkx file. Raises
    ValueError on an unrecognized key (parsing can't safely continue without
    knowing every row's size)."""
    data = Path(path).read_bytes()
    i = 0
    n = len(data)
    while i < n:
        key = data[i]
        size = PAYLOAD_SIZES.get(key)
        if size is None:
            raise ValueError(f"{path}: unknown VKX row key 0x{key:02x} at offset {i}")
        yield key, data[i + 1:i + 1 + size]
        i += 1 + size


def read_track(path):
    """Returns position/orientation rows as a list of dicts shaped like
    build_vakaros_db.read_csv()'s output: utc (datetime), lat, lon,
    sog (kn), hdg (deg true), heel (deg), trim (deg) -- sorted by time."""
    rows = []
    for key, payload in iter_rows(path):
        if key != 0x02:
            continue
        ts_ms, lat_e7, lon_e7, sog_ms, cog_rad, alt, qw, qx, qy, qz = _POS_STRUCT.unpack(payload)
        roll, pitch, yaw = _quat_to_euler_deg(qw, qx, qy, qz)
        rows.append({
            "utc": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).replace(tzinfo=None),
            "lat": lat_e7 * 1e-7, "lon": lon_e7 * 1e-7,
            "sog": sog_ms * 1.9438445, "hdg": yaw % 360.0,
            "heel": roll, "trim": pitch,
        })
    rows.sort(key=lambda r: r["utc"])
    return rows


def read_race_timer_events(path):
    """Returns [{"utc", "event", "timer_s"}] for every 0x04 row -- useful as
    an independent check against the registered gun time in races.json, but
    not authoritative on its own (it's whatever the sailor pressed on the
    device, which may lead or lag the actual starting-line gun)."""
    events = []
    for key, payload in iter_rows(path):
        if key != 0x04:
            continue
        ts_ms, event_type, timer_s = _TIMER_STRUCT.unpack(payload)
        events.append({
            "utc": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).replace(tzinfo=None),
            "event": RACE_TIMER_EVENTS.get(event_type, event_type),
            "timer_s": timer_s,
        })
    return events


def read_line_positions(path):
    """Returns {"pin": (lat, lon), "boat": (lat, lon)} from 0x05 rows -- only
    present if the sailor actually set both ends of the start line on the
    device before the sequence. Later rows win (a line reset before the
    start supersedes an earlier one); a key is simply absent if that end
    was never set."""
    positions = {}
    for key, payload in iter_rows(path):
        if key != 0x05:
            continue
        ts_ms, end_type, lat, lon = _LINE_STRUCT.unpack(payload)
        name = LINE_END_NAMES.get(end_type)
        if name:
            positions[name] = (lat, lon)
    return positions


if __name__ == "__main__":
    import sys
    track = read_track(sys.argv[1])
    print(f"# {len(track)} position rows, {track[0]['utc']} -> {track[-1]['utc']}")
    for e in read_race_timer_events(sys.argv[1]):
        print(f"#   timer event: {e['utc']} {e['event']} ({e['timer_s']}s)")
    print(f"#   line positions: {read_line_positions(sys.argv[1])}")
