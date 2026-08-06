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

"""Fleet Comparison for a single race: compares Critical Mass's actual
result against the fleet's official handicap results (hand-entered into
that race's races.json entry as "fleet_results"), and estimates how the
standings would have looked with our own tacks/gybes/roundings sailed
perfectly.

Time lost per maneuver is computed from real nav_1hz telemetry, not a rough
percentage: for the window [start_utc, end_utc + RECOVERY_WINDOW_S] (the
same 20s constant detect_maneuvers.py uses for its own recovery window),
compare the distance actually sailed against the distance that would have
been sailed at the pre-maneuver speed, then convert that distance deficit
back into seconds at the pre-maneuver speed.

The corrected-time model assumes a fixed time allowance (corrected minus
elapsed, as recorded in the actual result) carries forward unchanged as
elapsed time improves -- standard for PHRF/distance-race scoring, where the
allowance depends on rating and course distance, not on how fast the boat
actually sailed that day."""
import re

RECOVERY_WINDOW_S = 20  # matches detect_maneuvers.RECOVERY_WINDOW_S

_DHMS_RE = re.compile(r"^(\d+):(\d+):(\d+):(\d+)$")

TYPE_LABELS = {"tack": "Tacks", "gybe": "Gybes", "rounding-turn": "Roundings"}


def _parse_dhms(s):
    """'0:01:29:57' (D:HH:MM:SS) -> seconds. Non-finish strings (DNC, etc)
    return None."""
    if not s:
        return None
    m = _DHMS_RE.match(s.strip())
    if not m:
        return None
    d, h, mi, sec = (int(x) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + sec


def format_hms(seconds):
    """Rounds to the nearest whole second -- sub-second precision isn't
    meaningful for race times, and the estimated tiers are approximate
    anyway."""
    if seconds is None:
        return "—"
    sign = "-" if seconds < 0 else ""
    seconds = round(abs(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{sign}{h}:{m:02d}:{s:02d}"


def _maneuver_losses(conn, session_id):
    """Groups maneuvers by type and computes total/avg time lost (seconds)
    per type using real nav_1hz samples, per the module docstring's method."""
    from datetime import datetime, timedelta

    rows = conn.execute(
        "SELECT type, start_utc, end_utc, speed_before_kn FROM maneuvers "
        "WHERE session_id=? AND type IN ('tack','gybe','rounding-turn')",
        (session_id,),
    ).fetchall()

    losses = {}
    for typ, start_utc, end_utc, speed_before in rows:
        if speed_before is None or speed_before <= 0:
            continue
        window_end = (datetime.fromisoformat(end_utc) + timedelta(seconds=RECOVERY_WINDOW_S)).isoformat(sep=" ")
        samples = conn.execute(
            "SELECT stw_kn FROM nav_1hz WHERE session_id=? AND utc_timestamp>=? AND utc_timestamp<=? "
            "ORDER BY utc_timestamp",
            (session_id, start_utc, window_end),
        ).fetchall()
        speeds = [r[0] for r in samples if r[0] is not None]
        if not speeds:
            continue
        window_s = len(speeds)
        actual_nm = sum(speeds) / 3600.0
        reference_nm = speed_before * window_s / 3600.0
        time_lost_s = max(0.0, (reference_nm - actual_nm) / speed_before * 3600.0)

        bucket = losses.setdefault(typ, {"n": 0, "total_s": 0.0})
        bucket["n"] += 1
        bucket["total_s"] += time_lost_s

    for bucket in losses.values():
        bucket["avg_s"] = bucket["total_s"] / bucket["n"] if bucket["n"] else 0.0
    return losses


def _rank_and_gap(new_corrected_s, others):
    """others: [(boat_name, corrected_s), ...] for every other finisher.
    Returns (rank, gap_to_next_up_s, next_boat_name)."""
    ahead = sorted((c, name) for name, c in others if c is not None and c < new_corrected_s)
    rank = 1 + sum(1 for c, _ in ahead)
    if ahead:
        gap_c, gap_name = ahead[-1]
        return rank, new_corrected_s - gap_c, gap_name
    return rank, None, None


def compute(conn, race_meta):
    """Returns None if this race has no fleet_results, otherwise a dict with
    the raw fleet table, per-type mistake costs, a tiered what-if
    progression, and any boats that would actually have been beaten."""
    fleet = race_meta.get("fleet_results")
    if not fleet:
        return None

    target_name = race_meta.get("boat", "Critical Mass")
    our_row = next((r for r in fleet if r.get("boat_name") == target_name), None)
    our_elapsed = _parse_dhms(our_row["elapsed_time"]) if our_row else None
    our_corrected = _parse_dhms(our_row["corrected_time"]) if our_row else None
    if our_row is None or our_elapsed is None or our_corrected is None:
        return None

    others = [
        (r.get("boat_name"), _parse_dhms(r.get("corrected_time")))
        for r in fleet
        if r.get("boat_name") != target_name
    ]
    finishers = [c for _, c in others if c is not None] + [our_corrected]
    our_actual_rank = 1 + sum(1 for c in finishers if c < our_corrected)

    losses = _maneuver_losses(conn, race_meta["id"])
    total_lost_s = sum(b["total_s"] for b in losses.values())

    order = sorted(losses.keys(), key=lambda t: -losses[t]["total_s"])
    allowance = our_corrected - our_elapsed

    tiers = []
    actual_rank, actual_gap, actual_next = _rank_and_gap(our_corrected, others)
    tiers.append({
        "label": "Actual result", "elapsed_s": our_elapsed, "corrected_s": our_corrected,
        "rank": actual_rank, "gap_to_next_s": actual_gap, "next_boat": actual_next,
    })

    cum_saved = 0.0
    for typ in order:
        cum_saved += losses[typ]["total_s"]
        new_corrected = our_corrected - cum_saved
        new_elapsed = our_elapsed - cum_saved
        rank, gap, next_boat = _rank_and_gap(new_corrected, others)
        tiers.append({
            "label": f"+ fix {TYPE_LABELS.get(typ, typ).lower()}",
            "elapsed_s": new_elapsed, "corrected_s": new_corrected,
            "rank": rank, "gap_to_next_s": gap, "next_boat": next_boat,
        })

    final_corrected = tiers[-1]["corrected_s"] if tiers else our_corrected
    boats_beaten = [
        name for name, c in others
        if c is not None and c < our_corrected and c > final_corrected
    ]

    return {
        "fleet_results": fleet,
        "target_name": target_name,
        "actual_rank": our_actual_rank,
        "n_finishers": len(finishers),
        "losses": losses,
        "loss_order": order,
        "total_lost_s": total_lost_s,
        "allowance_s": allowance,
        "tiers": tiers,
        "boats_beaten": boats_beaten,
    }
