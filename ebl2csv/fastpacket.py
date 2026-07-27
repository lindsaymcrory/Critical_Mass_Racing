"""NMEA2000 Fast-Packet multi-frame reassembly.

Ported from FastPacketAssembler in github.com/aldas/go-nmea-client
(fastpacket.go). Fast-Packet PGNs split payloads over multiple 8-byte CAN
frames: frame 0 carries a (sequence-counter<<5 | 0) byte plus a total-length
byte plus 6 payload bytes; subsequent frames carry (sequence-counter<<5 |
frame-nr) plus up to 7 payload bytes.
"""

STALE_MS = 750


def _is_always_fast_packet_range(pgn: int) -> bool:
    """Manufacturer-proprietary fast-packet PGN ranges per the NMEA2000 PGN
    group table (see canboat: 126720 and 130816-131071). canboat.json does
    not enumerate every proprietary PGN a device might use, but any PGN in
    these ranges is structurally fast-packet regardless of whether we know
    how to decode its fields."""
    return pgn == 126720 or 130816 <= pgn <= 131071


class _Sequence:
    __slots__ = ("header", "sequence", "length", "complete_mask", "received_mask",
                 "data", "last_ms")

    def __init__(self):
        self.reset()

    def reset(self):
        self.header = None
        self.sequence = 0
        self.length = 0
        self.complete_mask = 0
        self.received_mask = 0
        self.data = bytearray(223)
        self.last_ms = None

    def append(self, header, payload: bytes, now_ms: int) -> bool:
        if len(payload) < 2:
            return False
        sequence = payload[0] >> 5
        frame_nr = payload[0] & 0x1F
        frame_mask = 1 << frame_nr
        if self.received_mask & frame_mask:
            return self.complete_mask == self.received_mask
        if self.received_mask == 0:
            self.header = header
            self.sequence = sequence

        self.received_mask |= frame_mask
        self.last_ms = now_ms

        if frame_nr == 0:
            self.length = payload[1]
            frame_count = 1
            if self.length > 6:
                # ceil((length - 6) / 7): go-nmea-client's Go source uses
                # `(length - 6 + 7) / 7` here, which is off by one whenever
                # (length - 6) is an exact multiple of 7 (e.g. length=34),
                # causing it to wait forever for a frame that is never sent.
                frame_count += -(-(self.length - 6) // 7)
            self.complete_mask = (1 << frame_count) - 1
            self.data[0:6] = payload[2:8].ljust(6, b"\x00")[:6]
        else:
            start = 6 + (frame_nr - 1) * 7
            chunk = payload[1:8]
            self.data[start:start + len(chunk)] = chunk

        return self.complete_mask == self.received_mask

    def result(self):
        return self.header, bytes(self.data[:self.length])


class FastPacketAssembler:
    def __init__(self, fast_packet_pgns):
        self.fast_pgns = set(fast_packet_pgns)
        self.in_transfer = {}  # (source, pgn, sequence) -> _Sequence

    def assemble(self, header, payload: bytes, now_ms: int):
        """header: object with .pgn/.source attrs. payload: raw CAN frame bytes
        (<=8). Returns (header, full_data_bytes) when a message completes, else None."""
        if header.pgn not in self.fast_pgns and not _is_always_fast_packet_range(header.pgn):
            return header, bytes(payload)

        if len(payload) < 1:
            return None
        sequence = payload[0] >> 5
        key = (header.source, header.pgn, sequence)

        seq = self.in_transfer.get(key)
        if seq is not None and seq.last_ms is not None and now_ms - seq.last_ms > STALE_MS:
            seq.reset()
        if seq is None:
            seq = _Sequence()
            self.in_transfer[key] = seq

        is_complete = seq.append(header, payload, now_ms)
        if is_complete:
            del self.in_transfer[key]
            return seq.result()
        return None
