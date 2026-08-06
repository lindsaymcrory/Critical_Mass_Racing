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
