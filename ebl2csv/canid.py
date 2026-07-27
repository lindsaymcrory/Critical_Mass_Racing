"""CAN bus 29-bit extended ID <-> NMEA2000 header parsing (J1939 PGN rules)."""
from dataclasses import dataclass


@dataclass
class CanBusHeader:
    pgn: int
    priority: int
    source: int
    destination: int


ADDRESS_GLOBAL = 0xFF


def parse_can_id(can_id: int) -> CanBusHeader:
    priority = (can_id >> 26) & 0x7
    source = can_id & 0xFF
    ps = (can_id >> 8) & 0xFF
    pdu_format = (can_id >> 16) & 0xFF
    r_and_dp = (can_id >> 24) & 0x3
    pgn = (r_and_dp << 16) + (pdu_format << 8)

    if pdu_format < 240:
        destination = ps
    else:
        destination = ADDRESS_GLOBAL
        pgn += ps

    return CanBusHeader(pgn=pgn, priority=priority, source=source, destination=destination)
