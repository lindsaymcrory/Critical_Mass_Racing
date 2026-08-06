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
