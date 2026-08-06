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

"""Summarizes every .ebl file under W2K_Dump/ebl_data_logs, grouped by
directory, and lists the unique PGNs seen across the whole dataset.

This only does raw CAN-ID + fast-packet-reassembly scanning (no per-field
bit decoding), since that's ~an order of magnitude cheaper and all a PGN
inventory needs. Runs one process per CPU core since the dataset is large
(hundreds of files, multiple GB).
"""
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from ebl2csv import ebl_reader
from ebl2csv.fastpacket import FastPacketAssembler
from ebl2csv.schema import CanboatSchema

ROOT = Path(__file__).parent
DUMP_DIR = ROOT / "W2K_Dump" / "ebl_data_logs"
PGNS_PATH = ROOT / "canboat.json"

_schema = None


def _get_schema():
    global _schema
    if _schema is None:
        _schema = CanboatSchema(str(PGNS_PATH))
    return _schema


def scan_file(path_str: str):
    schema = _get_schema()
    fast_pgns = schema.fast_packet_pgns()
    assembler = FastPacketAssembler(fast_pgns)

    path = Path(path_str)
    data = path.read_bytes()

    pgn_counts = Counter()
    total = 0
    min_ms = None
    max_ms = 0
    unknown = 0

    for frame in ebl_reader.iter_raw_frames(data):
        header = frame["header"]
        assembled = assembler.assemble(header, frame["payload"], frame["elapsed_ms"])
        if assembled is None:
            continue
        full_header, _full_data = assembled
        pgn_counts[full_header.pgn] += 1
        total += 1
        ms = frame["elapsed_ms"]
        if min_ms is None or ms < min_ms:
            min_ms = ms
        if ms > max_ms:
            max_ms = ms
        if full_header.pgn not in schema._unique and full_header.pgn not in schema._non_unique:
            unknown += 1

    duration_s = ((max_ms - min_ms) / 1000.0) if min_ms is not None else 0.0
    return {
        "path": path_str,
        "size": path.stat().st_size,
        "messages": total,
        "duration_s": duration_s,
        "pgn_counts": pgn_counts,
    }


def pgn_name(schema, pgn: int) -> str:
    p = schema._unique.get(pgn)
    if p is not None:
        return p.description
    variants = schema._non_unique.get(pgn)
    if variants:
        descs = sorted({v.description for v in variants})
        return descs[0] if len(descs) == 1 else f"{descs[0]} (+{len(descs)-1} more variants)"
    return "(unknown / not in canboat.json)"


def main():
    if not DUMP_DIR.exists():
        print(f"Not found: {DUMP_DIR}", file=sys.stderr)
        sys.exit(1)

    schema = _get_schema()

    dirs = sorted(d for d in DUMP_DIR.iterdir() if d.is_dir())
    all_files = []
    files_by_dir = {}
    for d in dirs:
        files = sorted(d.glob("*.ebl"))
        files_by_dir[d.name] = files
        all_files.extend(str(f) for f in files)

    print(f"# {len(dirs)} directories, {len(all_files)} .ebl files total\n")

    t0 = time.time()
    results_by_path = {}
    with ProcessPoolExecutor() as pool:
        futures = {pool.submit(scan_file, p): p for p in all_files}
        done = 0
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                results_by_path[p] = fut.result()
            except Exception as e:
                results_by_path[p] = {"path": p, "size": Path(p).stat().st_size,
                                       "messages": 0, "duration_s": 0.0,
                                       "pgn_counts": Counter(), "error": str(e)}
            done += 1
            if done % 100 == 0 or done == len(all_files):
                print(f"# ... scanned {done}/{len(all_files)} files ({time.time()-t0:.0f}s elapsed)", file=sys.stderr)

    global_pgn_counts = Counter()
    global_pgn_dirs = {}  # pgn -> set of directory names

    print("=" * 78)
    for d in dirs:
        files = files_by_dir[d.name]
        dir_pgn_counts = Counter()
        dir_messages = 0
        dir_size = 0
        dir_duration = 0.0
        errors = []
        for f in files:
            r = results_by_path[str(f)]
            dir_pgn_counts.update(r["pgn_counts"])
            dir_messages += r["messages"]
            dir_size += r["size"]
            dir_duration += r["duration_s"]
            if "error" in r:
                errors.append((f.name, r["error"]))

        for pgn in dir_pgn_counts:
            global_pgn_dirs.setdefault(pgn, set()).add(d.name)
        global_pgn_counts.update(dir_pgn_counts)

        print(f"\n{d.name}  ({len(files)} files, {dir_size/1e6:.0f} MB, "
              f"{dir_messages:,} messages, ~{dir_duration/60:.1f} min logged)")
        if errors:
            print(f"  ! {len(errors)} file(s) failed to parse: {errors[:5]}")
        for pgn, cnt in sorted(dir_pgn_counts.items(), key=lambda kv: -kv[1]):
            print(f"    {pgn:>6}  {cnt:>8,}  {pgn_name(schema, pgn)}")

    print("\n" + "=" * 78)
    print(f"UNIQUE PGNs ACROSS ALL {len(dirs)} DIRECTORIES: {len(global_pgn_counts)}\n")
    for pgn, cnt in sorted(global_pgn_counts.items()):
        dirs_seen = len(global_pgn_dirs[pgn])
        print(f"  {pgn:>6}  total={cnt:>9,}  in {dirs_seen:>2}/{len(dirs)} dirs  {pgn_name(schema, pgn)}")

    print(f"\n# Total wall time: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
