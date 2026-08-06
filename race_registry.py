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

"""Race registry: races.json is the editable source of truth for which
races exist and which .ebl files (in ebl_data/) belong to each -- this
replaces the hardcoded SESSIONS list in build_race_db.py so races can be
added through the web app instead of by editing source."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
REGISTRY_PATH = ROOT / "races.json"


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {"next_id": 1, "races": []}


def save_registry(registry: dict):
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


def add_race(race_date, local_start_time, series, files, boat="Critical Mass",
             crew_count=2, timezone="America/Halifax (ADT, UTC-3)", notes=""):
    registry = load_registry()
    race_id = registry["next_id"]
    race = {
        "id": race_id,
        "race_date": race_date,
        "local_start_time": local_start_time,
        "series": series,
        "boat": boat,
        "crew_count": crew_count,
        "timezone": timezone,
        "files": files,
        "notes": notes,
        "html_path": f"races/{race_id}.html",
    }
    registry["races"].append(race)
    registry["next_id"] = race_id + 1
    save_registry(registry)
    return race


def seed_known_races():
    registry = load_registry()
    if registry["races"]:
        return registry  # already seeded

    add_race(
        race_date="2026-07-13", local_start_time="18:15", series="WoW",
        files=[f"000009_{i:03d}.ebl" for i in range(3, 13)],
    )
    add_race(
        race_date="2026-07-20", local_start_time="18:15", series="WoW",
        files=[f"000009_{i:03d}.ebl" for i in range(20, 30)],
        notes="~90 min dropout 19:00-20:29 UTC: dead battery",
    )
    return load_registry()


if __name__ == "__main__":
    registry = seed_known_races()
    print(f"# Registry has {len(registry['races'])} race(s)")
    for r in registry["races"]:
        print(f"#   id={r['id']} {r['race_date']} {r['local_start_time']} {r['series']} "
              f"({len(r['files'])} files)")
