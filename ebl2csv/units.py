"""Optional physical-unit conversions for CSV readability.

canboat.json field values are decoded in their raw SI-ish unit (radians,
metres/second, Kelvin, Pascal, ...). Marine display conventions differ
(degrees, knots, Celsius, hectopascals), which is what tools like the
Actisense NMEA Reader show. These conversions are applied by default in
`convert` and can be turned off with --raw-units.
"""
import math

# source_unit -> (display_unit, convert_fn)
CONVERSIONS = {
    "rad": ("deg", math.degrees),
    "rad/s": ("deg/s", math.degrees),
    "semi-circle": ("deg", lambda v: v * 180.0),
    "semi-circle/s": ("deg/s", lambda v: v * 180.0),
    "m/s": ("kn", lambda v: v * 1.9438444924406046),
    "K": ("C", lambda v: v - 273.15),
    "Pa": ("hPa", lambda v: v / 100.0),
}
