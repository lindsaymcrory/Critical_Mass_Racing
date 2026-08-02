"""Boat Setup Log: boat_setup_log.json is the editable source of truth for
tuning and maintenance events (rig tune settings, bottom cleaning, mast rake
and pre-bend) that may affect boat speed. Entries are added by hand -- there
is no add/edit form, the same way races.json notes are edited directly."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
LOG_PATH = ROOT / "boat_setup_log.json"


def load_log() -> dict:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text())
    return {"next_id": 1, "entries": []}


def save_log(log: dict):
    LOG_PATH.write_text(json.dumps(log, indent=2))


def add_entry(date, label, values):
    log = load_log()
    entry_id = log["next_id"]
    entry = {"id": entry_id, "date": date, "label": label, "values": values}
    log["entries"].append(entry)
    log["next_id"] = entry_id + 1
    save_log(log)
    return entry


if __name__ == "__main__":
    log = load_log()
    print(f"# Boat Setup Log has {len(log['entries'])} entrie(s)")
    for e in log["entries"]:
        print(f"#   id={e['id']} {e['date']} {e['label']}: {', '.join(str(v) for v in e['values'])}")
