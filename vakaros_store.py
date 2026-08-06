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

"""Ingests Vakaros track exports from Vakaros_staging/ into the permanent
vakaros_data/ store, matching each file to a race in races.json by the date
encoded in its filename (e.g. "Critical Mass 8-3-2026.csv" -> 2026-08-03,
month-day-year per the Vakaros export naming convention) -- mirrors
ebl_store.py's role for .ebl files, but keyed by filename date instead of
content hash since each Vakaros export is one whole-race file, not a set of
raw frames to dedup. A file whose date matches no known race is left alone
and reported, not guessed at (see the 2026-08-05 Vakaros CSV that turned out
to be an unrelated recording).

Two file formats are supported: the original .csv track export, and .vkx
(Vakaros' binary telemetry format, see vkx_parser.py -- all Vakaros exports
going forward are expected to be .vkx). When both exist for the same race,
.vkx wins (it's the higher-fidelity, forward-compatible source)."""
import re
import shutil
from pathlib import Path

from race_registry import load_registry as load_races
from vakaros_registry import load_registry, save_registry

ROOT = Path(__file__).parent
STAGING_DIR = ROOT / "Vakaros_staging"
DATA_DIR = ROOT / "vakaros_data"

_DATE_RE = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4})")


def parse_filename_date(name: str):
    """'Critical Mass 8-3-2026.csv' -> '2026-08-03', or None if no
    month-day-year pattern is found in the filename."""
    m = _DATE_RE.search(name)
    if not m:
        return None
    month, day, year = m.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def ingest_staging():
    """Copies every *.csv/*.vkx in Vakaros_staging/ whose filename date
    matches a known race into vakaros_data/ and registers it (replacing any
    prior file registered for that race; .vkx wins over .csv for the same
    race if both are present in this staging pass). Returns
    (added: list[(filename, race_id)], unmatched: list[str])."""
    races_by_date = {r["race_date"]: r["id"] for r in load_races()["races"]}
    registry = load_registry()

    added, unmatched = [], []
    if not STAGING_DIR.exists():
        return added, unmatched

    DATA_DIR.mkdir(exist_ok=True)
    candidates = {}  # race_id -> src Path, preferring .vkx over .csv
    for src in sorted(STAGING_DIR.glob("*.csv")) + sorted(STAGING_DIR.glob("*.vkx")):
        race_date = parse_filename_date(src.name)
        race_id = races_by_date.get(race_date) if race_date else None
        if race_id is None:
            unmatched.append(src.name)
            continue
        existing = candidates.get(race_id)
        if existing is None or src.suffix == ".vkx":
            candidates[race_id] = src

    for race_id, src in candidates.items():
        race_date = parse_filename_date(src.name)
        dest = DATA_DIR / src.name
        shutil.copyfile(src, dest)
        registry["races"] = [r for r in registry["races"] if r["race_id"] != race_id]
        registry["races"].append({"race_id": race_id, "filename": src.name, "race_date": race_date})
        added.append((src.name, race_id))

    registry["races"].sort(key=lambda r: r["race_id"])
    save_registry(registry)
    return added, unmatched


if __name__ == "__main__":
    added, unmatched = ingest_staging()
    for name, rid in added:
        print(f"# Ingested {name} -> race {rid}")
    for name in unmatched:
        print(f"# WARNING: no matching race for {name} (check filename date vs races.json)")
    if not added and not unmatched:
        print("# No CSV files found in Vakaros_staging/")
