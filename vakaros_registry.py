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

"""Registry of which race each ingested Vakaros CSV belongs to
(vakaros_races.json): {"races": [{"race_id", "csv_filename", "race_date"}]}.
Mirrors race_registry.py's role for races.json, but for the separate,
independently-sourced Vakaros GPS-track data (see vakaros_store.py for how
files land here)."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
REGISTRY_PATH = ROOT / "vakaros_races.json"


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {"races": []}


def save_registry(registry: dict):
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


def by_race_id() -> dict:
    """{race_id: entry} for quick homepage / renderer lookups."""
    return {r["race_id"]: r for r in load_registry()["races"]}
