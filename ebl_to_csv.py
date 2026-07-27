#!/usr/bin/env python3
"""Converts Actisense W2K-1 EBL log files to CSV.

Two-step workflow:

  1. generate-config: scans an .ebl file and writes a JSON file listing every
     PGN and field that actually occurs in it, each with an "enabled" flag
     you can flip to choose which columns end up in the CSV.

  2. convert: reads the .ebl file again and writes a single CSV file, one
     row per decoded NMEA2000 message, with one column per enabled field
     (blank where a row's PGN doesn't have that field).

NMEA2000 frame decoding (fast-packet reassembly + Canboat PGN field
decoding) is a Python port of github.com/aldas/go-nmea-client -- see
ebl2csv/*.py docstrings for the specific source files each module mirrors.
Field definitions come from canboat.json (the same PGN database
go-nmea-client's own CLI downloads from the canboat project).
"""
import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

from ebl2csv import ebl_reader
from ebl2csv.decoder import decode_message
from ebl2csv.fastpacket import FastPacketAssembler
from ebl2csv.schema import CanboatSchema

DEFAULT_PGNS_PATH = Path(__file__).with_name("canboat.json")


def _iter_decoded_messages(ebl_path: Path, schema: CanboatSchema, convert_units: bool = True):
    """Yields (elapsed_ms, utc_or_None, header, pgn_def_or_None, decoded_fields_or_None)."""
    assembler = FastPacketAssembler(schema.fast_packet_pgns())
    data = ebl_path.read_bytes()

    for frame in ebl_reader.iter_raw_frames(data):
        header = frame["header"]
        assembled = assembler.assemble(header, frame["payload"], frame["elapsed_ms"])
        if assembled is None:
            continue
        full_header, full_data = assembled

        pgn_def = schema.find_pgn(full_header.pgn, full_data)
        if pgn_def is None:
            yield frame["elapsed_ms"], frame["utc"], full_header, None, None
            continue
        try:
            fields = decode_message(pgn_def, full_data, schema, convert_units)
        except Exception:
            yield frame["elapsed_ms"], frame["utc"], full_header, pgn_def, None
            continue
        yield frame["elapsed_ms"], frame["utc"], full_header, pgn_def, fields


def cmd_generate_config(args):
    schema = CanboatSchema(args.pgns)
    ebl_path = Path(args.input)

    pgns = OrderedDict()  # pgn_number(str) -> {"description":..., "fields": OrderedDict(key->name)}
    total = 0
    undecoded = 0

    for _elapsed_ms, _utc, header, pgn_def, fields in _iter_decoded_messages(ebl_path, schema, not args.raw_units):
        total += 1
        if pgn_def is None or fields is None:
            undecoded += 1
            continue
        entry = pgns.setdefault(str(header.pgn), {
            "description": pgn_def.description,
            "fields": OrderedDict(),
        })
        for f in fields:
            entry["fields"].setdefault(f.key, f.name)

    config = {
        "source_file": ebl_path.name,
        "pgns_database": str(Path(args.pgns).resolve()),
        "pgns": {
            pgn_number: {
                "enabled": True,
                "description": info["description"],
                "fields": [
                    {"key": key, "name": name, "enabled": True}
                    for key, name in info["fields"].items()
                ],
            }
            for pgn_number, info in sorted(pgns.items(), key=lambda kv: int(kv[0]))
        },
    }

    Path(args.output).write_text(json.dumps(config, indent=2))
    print(f"# Scanned {total} messages ({undecoded} not decodable with current PGN database)")
    print(f"# Found {len(pgns)} distinct PGNs, wrote config: {args.output}")
    print("# Edit the config's \"enabled\" flags to choose which PGNs/fields go into the CSV, "
          "then run the 'convert' command.")


def _load_config(path):
    config = json.loads(Path(path).read_text())
    enabled_pgns = OrderedDict()
    for pgn_number, info in config["pgns"].items():
        if not info.get("enabled", True):
            continue
        fields = [f for f in info["fields"] if f.get("enabled", True)]
        if not fields:
            continue
        enabled_pgns[int(pgn_number)] = {
            "description": info.get("description", ""),
            "fields": fields,
        }
    return enabled_pgns


def _format_elapsed(elapsed_ms: int) -> str:
    return f"{elapsed_ms / 1000.0:06.3f}"


def cmd_convert(args):
    schema = CanboatSchema(args.pgns)
    ebl_path = Path(args.input)
    enabled_pgns = _load_config(args.config)

    if not enabled_pgns:
        print("# No enabled PGNs/fields found in config, nothing to do", file=sys.stderr)
        sys.exit(1)

    columns = ["elapsed_seconds", "utc_timestamp", "pgn", "pgn_name", "source", "destination", "priority"]
    column_index = {}
    for pgn_number, info in enabled_pgns.items():
        for f in info["fields"]:
            col_name = f"{pgn_number}:{f['name']}"
            column_index[(pgn_number, f["key"])] = col_name
            columns.append(col_name)

    import csv
    written = 0
    skipped_pgns = set()
    with open(args.output, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(columns)

        for elapsed_ms, utc, header, pgn_def, fields in _iter_decoded_messages(ebl_path, schema, not args.raw_units):
            if header.pgn not in enabled_pgns or fields is None:
                continue
            row = {c: "" for c in columns}
            row["elapsed_seconds"] = _format_elapsed(elapsed_ms)
            row["utc_timestamp"] = utc.isoformat() if utc else ""
            row["pgn"] = header.pgn
            row["pgn_name"] = pgn_def.description if pgn_def else ""
            row["source"] = header.source
            row["destination"] = header.destination
            row["priority"] = header.priority

            for f in fields:
                key = (header.pgn, f.key)
                col_name = column_index.get(key)
                if col_name is None:
                    continue
                value = f.value
                if isinstance(value, bytes):
                    value = value.hex()
                elif isinstance(value, str):
                    value = value.replace("\x00", "").strip()
                elif isinstance(value, float):
                    value = f"{value:.8g}"
                row[col_name] = value
            writer.writerow(row[c] for c in columns)
            written += 1

    print(f"# Wrote {written} rows, {len(columns)} columns to {args.output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    gc = sub.add_parser("generate-config", help="scan an .ebl file and write a JSON parameter config")
    gc.add_argument("--input", required=True, help="path to .ebl file")
    gc.add_argument("--output", required=True, help="path to write JSON config")
    gc.add_argument("--pgns", default=str(DEFAULT_PGNS_PATH), help="path to canboat.json PGN database")
    gc.add_argument("--raw-units", action="store_true",
                    help="keep raw SI units (radians, m/s, Kelvin) instead of converting to "
                         "deg/knots/Celsius for display")
    gc.set_defaults(func=cmd_generate_config)

    cv = sub.add_parser("convert", help="convert an .ebl file to CSV using a JSON parameter config")
    cv.add_argument("--input", required=True, help="path to .ebl file")
    cv.add_argument("--config", required=True, help="path to JSON config (see generate-config)")
    cv.add_argument("--output", required=True, help="path to write CSV file")
    cv.add_argument("--pgns", default=str(DEFAULT_PGNS_PATH), help="path to canboat.json PGN database")
    cv.add_argument("--raw-units", action="store_true",
                    help="keep raw SI units (radians, m/s, Kelvin) instead of converting to "
                         "deg/knots/Celsius for display -- must match what generate-config used")
    cv.set_defaults(func=cmd_convert)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
