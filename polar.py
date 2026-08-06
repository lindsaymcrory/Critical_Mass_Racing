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

"""Loads a J/80-style polar table (Beat Angles/VMG row, TWA x TWS boat-speed
grid, Run VMG/Gybe Angles row) and provides interpolated lookups:
target boat speed for any (TWA, TWS), and optimal beat/run angle for any TWS.
"""
import csv


class PolarTable:
    def __init__(self, path):
        rows = list(csv.reader(open(path)))
        header = rows[0]
        self.tws_values = [float(c.strip().split()[0]) for c in header[1:]]

        self.beat_angles = [float(v) for v in rows[1][1:]]
        self.beat_vmg = [float(v) for v in rows[2][1:]]

        self.twa_values = []
        self.speed_table = []  # speed_table[i][j] = speed at twa_values[i], tws_values[j]
        for r in rows[3:-2]:
            self.twa_values.append(float(r[0]))
            self.speed_table.append([float(v) for v in r[1:]])

        self.run_vmg = [float(v) for v in rows[-2][1:]]
        self.gybe_angles = [float(v) for v in rows[-1][1:]]

        self.min_twa = min(self.twa_values)
        self.max_twa = max(self.twa_values)
        self.min_tws = min(self.tws_values)
        self.max_tws = max(self.tws_values)

    @staticmethod
    def _interp1(x, xs, ys):
        x = max(xs[0], min(xs[-1], x))
        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                t = (x - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + t * (ys[i + 1] - ys[i])
        return ys[-1]

    def beat_angle(self, tws_kn):
        return self._interp1(tws_kn, self.tws_values, self.beat_angles)

    def beat_vmg_target(self, tws_kn):
        return self._interp1(tws_kn, self.tws_values, self.beat_vmg)

    def run_angle(self, tws_kn):
        return self._interp1(tws_kn, self.tws_values, self.gybe_angles)

    def run_vmg_target(self, tws_kn):
        return self._interp1(tws_kn, self.tws_values, self.run_vmg)

    def target_speed(self, twa_deg, tws_kn, clamp=True):
        """Bilinear interpolation of target boat speed. twa_deg should be
        the absolute (0-180) true wind angle. Returns (speed, out_of_range)
        where out_of_range flags TWA outside the tabulated 52-150 deg band
        (no-go zone above beat angle, or deep run below gybe angle) -- the
        returned speed in that case is the nearest-edge value, clamped, and
        should be treated as a rough floor/ceiling rather than a real target."""
        twa = abs(twa_deg)
        out_of_range = twa < self.min_twa or twa > self.max_twa or \
            tws_kn < self.min_tws or tws_kn > self.max_tws
        if clamp:
            twa = max(self.min_twa, min(self.max_twa, twa))
            tws = max(self.min_tws, min(self.max_tws, tws_kn))
        else:
            tws = tws_kn

        # find twa bracket
        ti = 0
        for i in range(len(self.twa_values) - 1):
            if self.twa_values[i] <= twa <= self.twa_values[i + 1]:
                ti = i
                break
        else:
            ti = len(self.twa_values) - 2

        # find tws bracket
        wi = 0
        for j in range(len(self.tws_values) - 1):
            if self.tws_values[j] <= tws <= self.tws_values[j + 1]:
                wi = j
                break
        else:
            wi = len(self.tws_values) - 2

        twa0, twa1 = self.twa_values[ti], self.twa_values[ti + 1]
        tws0, tws1 = self.tws_values[wi], self.tws_values[wi + 1]
        tt = (twa - twa0) / (twa1 - twa0) if twa1 != twa0 else 0.0
        wt = (tws - tws0) / (tws1 - tws0) if tws1 != tws0 else 0.0

        s00 = self.speed_table[ti][wi]
        s01 = self.speed_table[ti][wi + 1]
        s10 = self.speed_table[ti + 1][wi]
        s11 = self.speed_table[ti + 1][wi + 1]
        s0 = s00 + wt * (s01 - s00)
        s1 = s10 + wt * (s11 - s10)
        speed = s0 + tt * (s1 - s0)
        return speed, out_of_range

    def curve_points(self, tws_kn, n=60):
        """Full target-speed curve at a given TWS across the tabulated TWA
        range, for plotting."""
        pts = []
        for i in range(n + 1):
            twa = self.min_twa + (self.max_twa - self.min_twa) * i / n
            speed, _ = self.target_speed(twa, tws_kn)
            pts.append((twa, speed))
        return pts
