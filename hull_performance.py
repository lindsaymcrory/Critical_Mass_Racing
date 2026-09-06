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

"""Pure data-transformation utilities for the Hull Analysis page's
port-vs-starboard performance heatmap. Kept free of any database or
rendering concerns so every function here is a plain, unit-testable
transform: raw per-second rows and boat_setup_log entries in, plain
dicts/lists out. boat_setup_analysis.py wires these to the database and
race registry; render_hull_analysis.py wires the resulting JSON to the
page's SVG/JS."""

WIND_RANGE_BANDS = [(0, 6, "0-6"), (6, 12, "6-12"), (12, 20, "12-20"), (20, None, "20+")]

ANGLE_BAND_BY_POINT_OF_SAIL = {"beat": "upwind", "reach": "reach", "run": "downwind"}

EVENT_TYPE_KEYWORDS = [
    ("rig tune", "rig-tune"),
    ("rig-tune", "rig-tune"),
    ("sail change", "sail-change"),
    ("sailchange", "sail-change"),
    ("bottom clean", "hull-cleaning"),
    ("hull clean", "hull-cleaning"),
    ("crew", "crew-change"),
    ("repair", "repair"),
]


def wind_range_for(tws_kn):
    """Buckets a true-wind-speed sample into one of the four season-wide
    wind ranges. Returns None for missing/negative input rather than
    guessing a band."""
    if tws_kn is None or tws_kn < 0:
        return None
    for lo, hi, label in WIND_RANGE_BANDS:
        if tws_kn >= lo and (hi is None or tws_kn < hi):
            return label
    return None


def angle_band_for(point_of_sail):
    """Maps the polar_performance point-of-sail label to the heatmap's
    three sailing-angle bands. Unknown/missing input returns None so
    callers can skip the sample rather than mis-bucket it."""
    return ANGLE_BAND_BY_POINT_OF_SAIL.get(point_of_sail)


def performance_percent(actual_speed_kn, target_speed_kn):
    """((actual / target) - 1) * 100. Returns None when there's no usable
    target (missing or non-positive) instead of dividing by zero or
    reporting a misleading 0%."""
    if actual_speed_kn is None or not target_speed_kn:
        return None
    return ((actual_speed_kn / target_speed_kn) - 1) * 100


def weighted_mean(value_count_pairs):
    """Sample-weighted mean of (value, count) pairs. Returns None for an
    empty input or when every count is zero -- distinct from a real 0.0
    result, so callers can tell 'no data' from 'measured zero'."""
    total_weight = 0
    total = 0.0
    for value, count in value_count_pairs:
        if value is None or not count:
            continue
        total += value * count
        total_weight += count
    if total_weight == 0:
        return None
    return total / total_weight


def aggregate_observations(rows, sessions_by_id):
    """Groups raw 1Hz (session_id, tws_kn, stw_kn, target_stw_kn,
    point_of_sail, tack) rows into PerformanceObservation dicts, one per
    (session, wind range, tack, angle band) cell that actually has data.
    Cells with zero samples are simply absent from the result -- the
    caller must not backfill them as zero, since a missing observation
    and a measured-zero one mean different things on the heatmap.

    sessions_by_id: {session_id: {"date": ..., "name": ...}} -- rows for
    an unknown session_id are skipped (e.g. a session pruned from the
    registry after the DB was populated)."""
    buckets = {}
    for session_id, tws_kn, stw_kn, target_stw_kn, point_of_sail, tack in rows:
        if tack not in ("port", "starboard"):
            continue
        session = sessions_by_id.get(session_id)
        if session is None:
            continue
        wind_range = wind_range_for(tws_kn)
        angle_band = angle_band_for(point_of_sail)
        if wind_range is None or angle_band is None:
            continue

        key = (session_id, wind_range, tack, angle_band)
        acc = buckets.setdefault(key, {"actual": [], "target": []})
        if stw_kn is not None:
            acc["actual"].append((stw_kn, 1))
        if target_stw_kn is not None:
            acc["target"].append((target_stw_kn, 1))

    observations = []
    for (session_id, wind_range, tack, angle_band), acc in buckets.items():
        sample_count = len(acc["actual"])
        if sample_count == 0:
            continue
        actual_mean = weighted_mean(acc["actual"])
        target_mean = weighted_mean(acc["target"])
        session = sessions_by_id[session_id]
        observations.append({
            "sessionId": str(session_id),
            "sessionName": session["name"],
            "date": session["date"],
            "windRange": wind_range,
            "tack": tack,
            "angleBand": angle_band,
            "actualSpeedKnots": round(actual_mean, 3) if actual_mean is not None else None,
            "targetSpeedKnots": round(target_mean, 3) if target_mean is not None else None,
            "sampleCount": sample_count,
            "validDurationSeconds": sample_count,
        })
    return observations


def sort_sessions_reverse_chronological(sessions):
    """Sorts session dicts (each with 'id' and 'date') most-recent-first.
    Ties (e.g. two sessions logged the same date) break on id descending,
    so ordering is stable and deterministic rather than relying on
    whatever order the caller happened to build the list in."""
    return sorted(sessions, key=lambda s: (s["date"], int(s["id"])), reverse=True)


def event_type_for_label(label):
    """Maps a free-text boat_setup_log label to one of the fixed
    BoatEvent types by keyword match; anything unrecognized is 'other'
    rather than raising, since the log is hand-typed and labels vary
    (e.g. 'Rig Tune -(2-12)', 'rig tune - (6~10)')."""
    lowered = (label or "").lower()
    for keyword, event_type in EVENT_TYPE_KEYWORDS:
        if keyword in lowered:
            return event_type
    return "other"


def build_events_from_log(log_entries):
    """Turns boat_setup_log.json entries into BoatEvent dicts. The log's
    free-form 'values' list becomes the description (joined with ', '),
    since that's the only place the actual rig numbers/notes live."""
    events = []
    for entry in log_entries:
        values = entry.get("values") or []
        events.append({
            "id": str(entry["id"]),
            "date": entry["date"],
            "type": event_type_for_label(entry.get("label", "")),
            "label": entry.get("label", "").strip() or "Event",
            "description": ", ".join(str(v) for v in values),
        })
    return events


def place_events_relative_to_sessions(events, sessions_desc):
    """For each event, computes the column boundary index it should be
    drawn at within a reverse-chronological (newest-first) session list.

    boundary_index counts how many sessions are on/after the event's
    date -- i.e. the number of newer-or-same-date columns to the event's
    left. An event on the same date as a race is treated as having
    happened by that race (boundary drawn to that race's right, toward
    older races), matching how the rig log records a change made before
    that day's sailing. Returns [{"event": ..., "boundary_index": int}],
    where 0 means the far left edge (newer than every session shown) and
    len(sessions_desc) means the far right edge (older than all of
    them)."""
    placements = []
    for event in events:
        boundary_index = sum(1 for s in sessions_desc if s["date"] >= event["date"])
        placements.append({"event": event, "boundary_index": boundary_index})
    return placements
