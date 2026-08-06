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

"""Bit-level field decoding for NMEA2000/Canboat PGN payloads.

Ported from the field-decoding rules used by github.com/aldas/go-nmea-client
(nmea.RawData methods in fieldvalue.go). NMEA2000 fields are packed as
little-endian bit fields that do not need to be byte aligned.
"""
import struct
from datetime import date, timedelta, datetime


class ValueNoData(Exception):
    """Field uses the reserved 'no data available' sentinel value."""


class ValueOutOfRange(Exception):
    """Field uses the reserved 'out of range' sentinel value."""


class ValueReserved(Exception):
    """Field uses the reserved 'reserved/error' sentinel value."""


def _raw_window(data: bytes, bit_offset: int, bit_length: int):
    start_byte = bit_offset // 8
    end_byte = (bit_offset + bit_length + 7) // 8 - 1
    if end_byte >= len(data):
        raise ValueError("bitoffset is out of bounds of data")
    value = int.from_bytes(data[start_byte:end_byte + 1], "little")
    value >>= bit_offset % 8
    mask = (1 << bit_length) - 1
    return value & mask, mask


def decode_variable_uint(data: bytes, bit_offset: int, bit_length: int) -> int:
    if bit_length > 64:
        raise ValueError("bit length larger than can be decoded")
    result, mask = _raw_window(data, bit_offset, bit_length)
    if bit_length >= 8:
        if result == mask:
            raise ValueNoData()
        elif result == mask - 1:
            raise ValueOutOfRange()
        elif result == mask - 2:
            raise ValueReserved()
    return result


def decode_variable_int(data: bytes, bit_offset: int, bit_length: int) -> int:
    if bit_length > 64:
        raise ValueError("bit length larger than can be decoded")
    result, mask = _raw_window(data, bit_offset, bit_length)
    is_negative = (result & (1 << (bit_length - 1))) != 0
    smask = mask >> 1
    if bit_length >= 8:
        if result == smask:
            raise ValueNoData()
        elif result == smask - 1:
            raise ValueOutOfRange()
        elif result == smask - 2:
            raise ValueReserved()
    if is_negative:
        result -= (1 << bit_length)
    return result


def decode_bytes(data: bytes, bit_offset: int, bit_length: int, is_variable_size: bool):
    """Returns (bytes, bits_read). Mirrors RawData.DecodeBytes."""
    total_bits = len(data) * 8
    end_bit = bit_offset + bit_length
    if end_bit > total_bits:
        if is_variable_size:
            bit_length -= (end_bit - total_bits)
            if bit_length <= 0:
                return b"", 0
        else:
            raise ValueError("bitoffset is out of bounds of data")

    start_byte = bit_offset // 8
    end_byte = (bit_offset + bit_length + 7) // 8 - 1
    value = int.from_bytes(data[start_byte:end_byte + 1], "little")
    value >>= bit_offset % 8
    mask = (1 << bit_length) - 1
    value &= mask

    n_out_bytes = (bit_length + 7) // 8
    return value.to_bytes(n_out_bytes, "little"), bit_length


def decode_time(data: bytes, bit_offset: int, bit_length: int, resolution: float) -> timedelta:
    raw_seconds = decode_variable_uint(data, bit_offset, bit_length)
    return timedelta(seconds=raw_seconds * resolution)


def decode_date(data: bytes, bit_offset: int, bit_length: int) -> date:
    if bit_length != 16:
        raise ValueError("can only decode date with 16 bits")
    raw, _ = decode_bytes(data, bit_offset, bit_length, False)
    days_since_epoch = int.from_bytes(raw, "little")
    if days_since_epoch == 0xFFFF:
        raise ValueNoData()
    elif days_since_epoch == 0xFFFE:
        raise ValueOutOfRange()
    elif days_since_epoch == 0xFFFD:
        raise ValueReserved()
    return date(1970, 1, 1) + timedelta(days=days_since_epoch)


def decode_string_fix(data: bytes, bit_offset: int, bit_length: int) -> str:
    raw, _ = decode_bytes(data, bit_offset, bit_length, False)
    length = 0
    for b in raw:
        if b in (0xFF, 0x00, ord('@')):
            break
        length += 1
    return raw[:length].decode("latin1")


def decode_string_lz(data: bytes, bit_offset: int, bit_length: int):
    length_byte_index = bit_offset // 8
    actual_length = data[length_byte_index]
    field_length = (bit_length + 7) // 8
    if actual_length > field_length:
        actual_length = field_length
    elif actual_length == 0:
        return "", 8
    raw, read_bits = decode_bytes(data, bit_offset + 8, actual_length * 8, True)
    return raw.decode("latin1"), read_bits + 8


def decode_string_lau(data: bytes, bit_offset: int):
    header, _ = decode_bytes(data, bit_offset, 16, False)
    length = header[0]
    if length == 2:
        return "", 16
    elif length < 2:
        raise ValueError("string lau has invalid size below 2")
    length -= 2
    encoding = header[1]
    raw, read_bits = decode_bytes(data, bit_offset + 16, length * 8, True)
    read_bits += 16
    if encoding == 0:  # utf16
        if len(raw) >= 2 and raw[0] == 0xFF and raw[1] == 0xFE:
            s = raw[2:].decode("utf-16-le")
        elif len(raw) >= 2 and raw[0] == 0xFE and raw[1] == 0xFF:
            s = raw[2:].decode("utf-16-be")
        else:
            s = raw.decode("utf-16-le")
        return s, read_bits
    elif encoding == 1:  # ascii/utf8, trim trailing 0x00/0xFF ("no data")
        usable_len = 0
        for b in raw:
            if b in (0x00, 0xFF):
                break
            usable_len += 1
        return raw[:usable_len].decode("utf-8", errors="replace"), read_bits
    else:
        raise ValueError("invalid string lau encoding")


def decode_decimal(data: bytes, bit_offset: int, bit_length: int) -> int:
    raw, _ = decode_bytes(data, bit_offset, bit_length, False)
    result = 0
    digits = 1
    is_no_data = True
    for b in reversed(raw):
        if b == 0xFF:
            continue
        if b > 99:
            raise ValueError("decimal contains byte with value larger than 2 digits")
        is_no_data = False
        right = b % 10
        left = b // 10
        result += digits * right
        digits *= 10
        result += digits * left
        digits *= 10
    if is_no_data:
        raise ValueNoData()
    return result


def decode_float(data: bytes, bit_offset: int, bit_length: int) -> float:
    if bit_length != 32:
        raise ValueError("can only decode float with 32 bits")
    raw, _ = decode_bytes(data, bit_offset, bit_length, False)
    as_uint32 = int.from_bytes(raw, "little")
    if as_uint32 == 0xFFFFFFFF:
        raise ValueNoData()
    elif as_uint32 == 0xFFFFFFFE:
        raise ValueOutOfRange()
    elif as_uint32 == 0xFFFFFFFD:
        raise ValueReserved()
    return struct.unpack("<f", raw)[0]
