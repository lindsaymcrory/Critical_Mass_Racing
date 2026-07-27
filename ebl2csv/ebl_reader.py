"""Reader for Actisense EBL log files (W2K-1 "CAN-Raw BST-95" format).

Ported from actisense.EBLFormatDevice in github.com/aldas/go-nmea-client
(actisense/eblreader.go).

Frame is escaped with ESC(0x1b): a frame starts at ESC+SOH(0x01) and ends at
ESC+NL(0x0a); any literal ESC byte inside the frame is doubled (ESC+ESC).
Two frame types are used by the W2K-1:

  type 0x03: 8-byte little-endian Windows FILETIME (100ns ticks since
             1601-01-01 UTC) giving the absolute time "now", emitted roughly
             once a second as a clock heartbeat. The go-nmea-client SDK does
             not use these at all for EBL files (see comments in
             eblreader.go) -- this reader uses them to reconstruct real
             timestamps, since the per-frame counter below is otherwise only
             a free-running millisecond counter with no absolute reference.
  type 0x07,0x95: a single CAN frame: [len][ts_lo][ts_hi][canid x4][data...]
             where ts is a 16 bit free-running millisecond counter (wraps at
             65536ms) with no absolute meaning on its own.
"""
import struct
from datetime import datetime, timedelta

from .canid import parse_can_id

SOH = 0x01
NL = 0x0A
ESC = 0x1B

_FILETIME_EPOCH = datetime(1601, 1, 1)


def _filetime_to_datetime(ticks_100ns: int) -> datetime:
    return _FILETIME_EPOCH + timedelta(microseconds=ticks_100ns / 10)


def iter_raw_frames(data: bytes):
    """Yields dicts: {header: CanBusHeader, payload: bytes (<=8),
    elapsed_ms: int, utc: datetime|None, frame_index: int}."""

    frame_index = 0
    last_raw_counter = None
    wrap_count = 0
    base_time = None  # best-effort UTC corresponding to running_ms_total == 0
    start_ms = None  # raw running_ms_total of the first frame, so elapsed_ms starts at 0

    i = 0
    n = len(data)
    while i < n:
        # find ESC+SOH start-of-frame
        while i + 1 < n and not (data[i] == ESC and data[i + 1] == SOH):
            i += 1
        if i + 1 >= n:
            break
        i += 2  # consumed ESC SOH

        msg = bytearray()
        while i < n:
            b = data[i]
            if b == ESC:
                if i + 1 >= n:
                    i = n
                    break
                nxt = data[i + 1]
                if nxt == ESC:
                    msg.append(ESC)
                    i += 2
                    continue
                elif nxt == NL:
                    i += 2
                    break
                else:
                    # unknown escape sequence -> discard frame, resume search
                    i += 2
                    msg = None
                    break
            else:
                msg.append(b)
                i += 1

        if not msg or len(msg) < 3:
            continue

        if msg[0] == 0x03 and len(msg) >= 9:
            ticks = struct.unpack("<Q", bytes(msg[1:9]))[0]
            anchor_time = _filetime_to_datetime(ticks)
            running_ms_total = wrap_count * 65536 + (last_raw_counter or 0)
            base_time = anchor_time - timedelta(milliseconds=running_ms_total)
            continue

        if msg[0] == 0x07 and msg[1] == 0x95:
            raw = bytes(msg[2:])
            if len(raw) < 8 or raw[0] != len(raw) - 1:
                continue
            can_id = raw[3] | (raw[4] << 8) | (raw[5] << 16) | (raw[6] << 24)
            header = parse_can_id(can_id)
            payload = raw[7:]

            raw_counter = raw[1] | (raw[2] << 8)
            if last_raw_counter is not None and raw_counter < last_raw_counter:
                wrap_count += 1
            last_raw_counter = raw_counter
            running_ms_total = wrap_count * 65536 + raw_counter
            if start_ms is None:
                start_ms = running_ms_total

            utc = (base_time + timedelta(milliseconds=running_ms_total)) if base_time else None

            frame_index += 1
            yield {
                "header": header,
                "payload": payload,
                "elapsed_ms": running_ms_total - start_ms,
                "utc": utc,
                "frame_index": frame_index,
            }
            continue
        # any other frame type is ignored (unknown/unhandled by this format)
