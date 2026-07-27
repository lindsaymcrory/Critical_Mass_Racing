"""Decodes NMEA2000 RawMessage payloads into named field values, using a
Canboat PGN schema. Ported from canboat.Decoder in go-nmea-client
(canboat/decoder.go), including repeating field-set handling and enum lookups.
"""
from dataclasses import dataclass
from typing import Any, List, Optional

from . import rawdata
from . import units as unit_conv
from .schema import CanboatSchema, Field, PGN

IGNORED_TYPES = {"RESERVED", "SPARE"}


class UnknownPGN(Exception):
    pass


@dataclass
class DecodedField:
    key: str          # stable, unique column key (repeats get a #n suffix)
    field_id: str      # canboat field Id (not unique across repeats)
    name: str          # human readable name (repeats get a #n suffix)
    value: Any


def _decode_field(f: Field, data: bytes, bit_offset: int):
    """Returns (value, bits_read) or raises rawdata.ValueNoData/OutOfRange/Reserved
    to signal the field should be skipped, matching decoder.go's decodeSingleField."""
    t = f.field_type
    if t == "NUMBER" or t in ("LOOKUP", "INDIRECT_LOOKUP", "BITLOOKUP"):
        if f.signed:
            raw_value = rawdata.decode_variable_int(data, bit_offset, f.bit_length)
        else:
            raw_value = rawdata.decode_variable_uint(data, bit_offset, f.bit_length)
        if f.resolution == 1:
            value = raw_value + f.offset
        else:
            value = (raw_value + f.offset) * f.resolution
        return value, f.bit_length
    elif t in ("RESERVED", "SPARE", "BINARY"):
        raw, bits = rawdata.decode_bytes(data, bit_offset, f.bit_length, f.bit_length_variable)
        return raw, bits
    elif t == "TIME":
        return rawdata.decode_time(data, bit_offset, f.bit_length, f.resolution), f.bit_length
    elif t == "MMSI":
        return rawdata.decode_variable_uint(data, bit_offset, f.bit_length), f.bit_length
    elif t == "STRING_FIX":
        return rawdata.decode_string_fix(data, bit_offset, f.bit_length), f.bit_length
    elif t == "STRING_LZ":
        return rawdata.decode_string_lz(data, bit_offset, f.bit_length)
    elif t == "STRING_LAU":
        return rawdata.decode_string_lau(data, bit_offset)
    elif t == "DATE":
        return rawdata.decode_date(data, bit_offset, f.bit_length), f.bit_length
    elif t == "DECIMAL":
        return rawdata.decode_decimal(data, bit_offset, f.bit_length), f.bit_length
    elif t == "FLOAT":
        return rawdata.decode_float(data, bit_offset, f.bit_length), f.bit_length
    else:
        raise ValueError(f"unsupported field type: {t}")


def _resolve_enum(f: Field, raw_int: int, schema: CanboatSchema, all_values: dict):
    if f.field_type == "LOOKUP":
        table = schema.enums.get(f.lookup_enumeration, {})
        name = table.get(raw_int)
        return name if name is not None else f"UNKNOWN ENUM VALUE ({raw_int})"
    elif f.field_type == "BITLOOKUP":
        table = schema.bit_enums.get(f.lookup_bit_enumeration, {})
        if raw_int == 0:
            return ""
        names = [name for bit, name in table.items() if raw_int & (1 << bit)]
        return "|".join(names) if names else f"UNKNOWN BIT ENUM VALUE ({raw_int})"
    elif f.field_type == "INDIRECT_LOOKUP":
        indirect_field = all_values.get(f.lookup_indirect_enumeration_field_order)
        if indirect_field is None:
            return raw_int
        table = schema.indirect_enums.get(f.lookup_indirect_enumeration, {})
        name = table.get((raw_int, int(indirect_field)))
        return name if name is not None else f"UNKNOWN INDIRECT ENUM VALUE ({raw_int})"
    return raw_int


def decode_message(pgn: PGN, data: bytes, schema: CanboatSchema, convert_units: bool = True) -> List[DecodedField]:
    if pgn.repeating_set1_start > 0 or pgn.repeating_set2_start > 0:
        return _decode_with_repeated_fields(pgn, data, schema, convert_units)
    return _decode_simple(pgn, data, schema, convert_units)


def _emit(f: Field, raw_value, schema: CanboatSchema, order_values: dict, convert_units: bool, suffix: str = ""):
    order_values[f.order] = raw_value if isinstance(raw_value, int) else None
    value = raw_value
    display_name = f.name
    if f.field_type == "NUMBER" and isinstance(raw_value, (int, float)) and f.unit:
        conv = unit_conv.CONVERSIONS.get(f.unit) if convert_units else None
        if conv:
            display_unit, fn = conv
            value = fn(raw_value)
            display_name = f"{f.name} ({display_unit})"
        else:
            display_name = f"{f.name} ({f.unit})"
    elif f.field_type in ("LOOKUP", "BITLOOKUP", "INDIRECT_LOOKUP"):
        value = _resolve_enum(f, raw_value, schema, order_values)
    key = f.id + suffix
    name = display_name + suffix
    return DecodedField(key=key, field_id=f.id, name=name, value=value)


def _decode_simple(pgn: PGN, data: bytes, schema: CanboatSchema, convert_units: bool) -> List[DecodedField]:
    result = []
    order_values = {}
    message_bits = len(data) * 8
    bit_offset = pgn.fields[0].bit_offset if pgn.fields else 0

    for f in pgn.fields:
        if bit_offset >= message_bits:
            break
        if f.field_type in IGNORED_TYPES:
            bit_offset += f.bit_length
            continue
        try:
            value, bits = _decode_field(f, data, bit_offset)
        except (rawdata.ValueNoData, rawdata.ValueOutOfRange, rawdata.ValueReserved):
            bit_offset += f.bit_length
            continue
        bit_offset += bits
        result.append(_emit(f, value, schema, order_values, convert_units))
    return result


def _decode_with_repeated_fields(pgn: PGN, data: bytes, schema: CanboatSchema, convert_units: bool) -> List[DecodedField]:
    result = []
    order_values = {}
    message_bits = len(data) * 8
    bit_offset = pgn.fields[0].bit_offset if pgn.fields else 0

    rep1_start = pgn.repeating_set1_start or (1 << 30)
    rep1_end = (1 << 30) if pgn.repeating_set1_count == 0 else 0
    rep2_start = pgn.repeating_set2_start or (1 << 30)
    rep2_end = (1 << 30) if pgn.repeating_set2_count == 0 else 0

    rep1_counts: dict = {}
    rep2_counts: dict = {}

    current_field_order = 1
    current_rep_field_order = 0

    while bit_offset < message_bits:
        if current_field_order > len(pgn.fields):
            break
        f = pgn.fields[current_field_order - 1]

        is_within_rep1 = rep1_start <= current_field_order <= rep1_end
        is_within_rep2 = (not is_within_rep1) and rep2_start <= current_field_order <= rep2_end

        if is_within_rep1:
            if current_field_order == rep1_start:
                current_rep_field_order = 1
            else:
                current_rep_field_order += 1
            offset_in_group = current_rep_field_order % pgn.repeating_set1_size
            current_field_order = rep1_start + offset_in_group
            rep_index = (current_rep_field_order - 1) // pgn.repeating_set1_size
        elif is_within_rep2:
            if current_field_order == rep2_start:
                current_rep_field_order = 1
            else:
                current_rep_field_order += 1
            offset_in_group = current_rep_field_order % pgn.repeating_set2_size
            current_field_order = rep2_start + offset_in_group
            rep_index = (current_rep_field_order - 1) // pgn.repeating_set2_size
        else:
            current_field_order += 1
            rep_index = None

        if f.field_type in IGNORED_TYPES:
            bit_offset += f.bit_length
            continue
        try:
            value, bits = _decode_field(f, data, bit_offset)
        except (rawdata.ValueNoData, rawdata.ValueOutOfRange, rawdata.ValueReserved):
            bit_offset += f.bit_length
            continue
        bit_offset += bits

        # detect count fields to bound the repeat range (mirrors decoder.go)
        if pgn.repeating_set1_count and current_field_order - 1 == pgn.repeating_set1_count and isinstance(value, int):
            rep1_end = value * pgn.repeating_set1_size + pgn.repeating_set1_start
        elif pgn.repeating_set2_count and current_field_order - 1 == pgn.repeating_set2_count and isinstance(value, int):
            rep2_end = value * pgn.repeating_set2_size + pgn.repeating_set2_start

        if is_within_rep1:
            suffix = f" #{rep_index + 1}"
            rep1_counts[f.id] = rep_index + 1
            result.append(_emit(f, value, schema, order_values, convert_units, suffix))
        elif is_within_rep2:
            suffix = f" #{rep_index + 1}"
            rep2_counts[f.id] = rep_index + 1
            result.append(_emit(f, value, schema, order_values, convert_units, suffix))
        else:
            result.append(_emit(f, value, schema, order_values, convert_units))

    return result
