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

"""Loads the Canboat PGN-definitions database (canboat.json) used by
github.com/aldas/go-nmea-client's canboat package, and provides PGN/field
lookups needed by the decoder."""
import json
from dataclasses import dataclass, field
from typing import Optional

from . import rawdata


@dataclass
class Field:
    id: str
    order: int
    name: str
    unit: str
    match: int
    bit_length: int
    bit_offset: int
    bit_length_variable: bool
    signed: bool
    offset: int
    resolution: float
    field_type: str
    lookup_enumeration: str
    lookup_bit_enumeration: str
    lookup_indirect_enumeration: str
    lookup_indirect_enumeration_field_order: int

    def is_match(self, data: bytes) -> bool:
        try:
            value = rawdata.decode_variable_uint(data, self.bit_offset, self.bit_length)
        except Exception:
            return False
        return value == self.match


@dataclass
class PGN:
    pgn: int
    id: str
    description: str
    packet_type: str
    fields: list = field(default_factory=list)
    repeating_set1_size: int = 0
    repeating_set1_start: int = 0
    repeating_set1_count: int = 0
    repeating_set2_size: int = 0
    repeating_set2_start: int = 0
    repeating_set2_count: int = 0
    is_matchable: bool = False

    def is_match(self, data: bytes) -> bool:
        if not self.is_matchable:
            return False
        for f in self.fields:
            if f.match and not f.is_match(data):
                return False
        return True


def _field_from_json(fj: dict) -> Field:
    return Field(
        id=fj.get("Id", ""),
        order=fj.get("Order", 0),
        name=fj.get("Name", ""),
        unit=fj.get("Unit", "") or "",
        match=fj.get("Match", 0) or 0,
        bit_length=fj.get("BitLength", 0) or 0,
        bit_offset=fj.get("BitOffset", 0) or 0,
        bit_length_variable=bool(fj.get("BitLengthVariable", False)),
        signed=bool(fj.get("Signed", False)),
        offset=fj.get("Offset", 0) or 0,
        resolution=fj.get("Resolution", 1) or 1,
        field_type=fj.get("FieldType", ""),
        lookup_enumeration=fj.get("LookupEnumeration", "") or "",
        lookup_bit_enumeration=fj.get("LookupBitEnumeration", "") or "",
        lookup_indirect_enumeration=fj.get("LookupIndirectEnumeration", "") or "",
        lookup_indirect_enumeration_field_order=fj.get("LookupIndirectEnumerationFieldOrder", 0) or 0,
    )


def _pgn_from_json(pj: dict) -> PGN:
    fields = [_field_from_json(fj) for fj in pj.get("Fields", [])]
    p = PGN(
        pgn=pj["PGN"],
        id=pj.get("Id", ""),
        description=pj.get("Description", ""),
        packet_type=pj.get("Type", ""),
        fields=fields,
        repeating_set1_size=pj.get("RepeatingFieldSet1Size", 0) or 0,
        repeating_set1_start=pj.get("RepeatingFieldSet1StartField", 0) or 0,
        repeating_set1_count=pj.get("RepeatingFieldSet1CountField", 0) or 0,
        repeating_set2_size=pj.get("RepeatingFieldSet2Size", 0) or 0,
        repeating_set2_start=pj.get("RepeatingFieldSet2StartField", 0) or 0,
        repeating_set2_count=pj.get("RepeatingFieldSet2CountField", 0) or 0,
    )
    p.is_matchable = any(f.match for f in fields)
    return p


class CanboatSchema:
    def __init__(self, path: str):
        with open(path, "r") as f:
            raw = json.load(f)

        self.version = raw.get("Version", "")
        self.pgns = [_pgn_from_json(p) for p in raw.get("PGNs", [])]

        self.enums = {e["Name"]: {v["Value"]: v["Name"] for v in e["EnumValues"]}
                      for e in raw.get("LookupEnumerations", [])}
        self.bit_enums = {e["Name"]: {v["Bit"]: v["Name"] for v in e["EnumBitValues"]}
                           for e in raw.get("LookupBitEnumerations", [])}
        self.indirect_enums = {}
        for e in raw.get("LookupIndirectEnumerations", []):
            table = {}
            for v in e["EnumValues"]:
                table[(v["Value1"], v["Value2"])] = v["Name"]
            self.indirect_enums[e["Name"]] = table

        self._unique = {}
        self._non_unique = {}
        for p in self.pgns:
            if p.pgn in self._non_unique:
                self._non_unique[p.pgn].append(p)
            elif p.pgn in self._unique:
                self._non_unique[p.pgn] = [self._unique.pop(p.pgn), p]
            else:
                self._unique[p.pgn] = p

    def fast_packet_pgns(self):
        return {p.pgn for p in self.pgns if p.packet_type == "Fast"}

    def find_pgn(self, pgn_number: int, data: bytes) -> Optional[PGN]:
        p = self._unique.get(pgn_number)
        if p is not None:
            return p
        candidates = self._non_unique.get(pgn_number)
        if not candidates:
            return None
        for p in candidates:
            if p.is_match(data):
                return p
        return None
