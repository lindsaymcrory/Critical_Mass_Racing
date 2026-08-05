"""Video Log: video_log.json is the editable source of truth for race
video links (YouTube, etc.) and their notes. Entries are added by hand --
there is no upload form, the same way boat_setup_log.json entries are
added directly."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
LOG_PATH = ROOT / "video_log.json"


def load_log() -> dict:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text())
    return {"next_id": 1, "entries": []}


def save_log(log: dict):
    LOG_PATH.write_text(json.dumps(log, indent=2))


def add_entry(date, url, note):
    log = load_log()
    entry_id = log["next_id"]
    entry = {"id": entry_id, "date": date, "url": url, "note": note}
    log["entries"].append(entry)
    log["next_id"] = entry_id + 1
    save_log(log)
    return entry


if __name__ == "__main__":
    log = load_log()
    print(f"# Video Log has {len(log['entries'])} entrie(s)")
    for e in sorted(log["entries"], key=lambda e: e["date"], reverse=True):
        print(f"#   id={e['id']} {e['date']} {e['url']}: {e['note']}")
