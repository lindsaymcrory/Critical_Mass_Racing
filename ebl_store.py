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

"""Canonical store of known .ebl files (ebl_data/) with a content-hash
manifest (ebl_manifest.json) to prevent re-importing the same recording
twice under a different name -- dedup is by content, not filename, since a
re-uploaded or re-copied file may not keep the original name."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
EBL_DATA_DIR = ROOT / "ebl_data"
MANIFEST_PATH = ROOT / "ebl_manifest.json"


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _time_range(path: Path):
    """(first_utc, last_utc) ISO strings, reconstructed from the EBL's own
    FILETIME anchors -- computed once at ingest time and cached in the
    manifest, since scanning a whole file just for its time span is too
    slow (~0.5s each) to redo on every Add Race page load."""
    from ebl2csv import ebl_reader

    data = path.read_bytes()
    first_utc = last_utc = None
    for frame in ebl_reader.iter_raw_frames(data):
        u = frame["utc"]
        if u and u.year > 2000:
            if first_utc is None:
                first_utc = u
            last_utc = u
    return (
        first_utc.isoformat(sep=" ", timespec="seconds") if first_utc else None,
        last_utc.isoformat(sep=" ", timespec="seconds") if last_utc else None,
    )


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def save_manifest(manifest: dict):
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def known_hashes(manifest: dict) -> set:
    return set(manifest.keys())


def _unique_dest_name(name: str) -> str:
    dest = EBL_DATA_DIR / name
    if not dest.exists():
        return name
    stem, suffix = Path(name).stem, Path(name).suffix
    i = 1
    while (EBL_DATA_DIR / f"{stem}_{i}{suffix}").exists():
        i += 1
    return f"{stem}_{i}{suffix}"


def ingest_files(paths, manifest=None):
    """Copies each path into ebl_data/ unless its content hash is already
    known. Returns (added: list[str], duplicates: list[str], errors: list[(str,str)])."""
    EBL_DATA_DIR.mkdir(exist_ok=True)
    manifest = load_manifest() if manifest is None else manifest
    added, duplicates, errors = [], [], []

    for src in paths:
        src = Path(src)
        try:
            digest = _hash_file(src)
        except Exception as e:
            errors.append((src.name, str(e)))
            continue

        if digest in manifest:
            duplicates.append(src.name)
            continue

        dest_name = _unique_dest_name(src.name)
        dest = EBL_DATA_DIR / dest_name
        shutil.copyfile(src, dest)
        first_utc, last_utc = _time_range(dest)
        manifest[digest] = {"filename": dest_name, "original_name": src.name, "size": dest.stat().st_size,
                            "first_utc": first_utc, "last_utc": last_utc}
        added.append(dest_name)

    save_manifest(manifest)
    return added, duplicates, errors


def list_files_with_ranges():
    """Returns [{filename, size, first_utc, last_utc}] for every file in
    ebl_data/, reading cached time ranges from the manifest (fast). Any
    file missing from the manifest -- shouldn't normally happen -- is
    scanned on the spot and the manifest is backfilled."""
    manifest = load_manifest()
    by_filename = {entry["filename"]: entry for entry in manifest.values()}

    out = []
    dirty = False
    for p in sorted(EBL_DATA_DIR.glob("*.ebl")):
        entry = by_filename.get(p.name)
        if entry is None or "first_utc" not in entry:
            first_utc, last_utc = _time_range(p)
            digest = _hash_file(p)
            manifest[digest] = {"filename": p.name, "original_name": p.name, "size": p.stat().st_size,
                                "first_utc": first_utc, "last_utc": last_utc}
            dirty = True
        else:
            first_utc, last_utc = entry["first_utc"], entry["last_utc"]
        out.append({"filename": p.name, "size": p.stat().st_size, "first_utc": first_utc, "last_utc": last_utc})

    if dirty:
        save_manifest(manifest)
    return out


def seed_manifest_from_existing():
    """One-time bootstrap: hash the files already copied into ebl_data/
    (from W2K_Dump) so future uploads correctly dedup against them."""
    manifest = load_manifest()
    added = 0
    for p in sorted(EBL_DATA_DIR.glob("*.ebl")):
        digest = _hash_file(p)
        if digest not in manifest:
            manifest[digest] = {"filename": p.name, "original_name": p.name, "size": p.stat().st_size}
            added += 1
    save_manifest(manifest)
    return added


if __name__ == "__main__":
    n = seed_manifest_from_existing()
    print(f"# Seeded manifest with {n} new entries ({len(load_manifest())} total)")
