#!/usr/bin/env python3

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

"""Unit tests for hull_performance.py's pure data-transformation
functions -- the heatmap's reverse-chronological sort, weighted
aggregation, performance-percent math, missing-data handling, and event
placement. Run with: python -m unittest tests.test_hull_performance"""
import unittest

import hull_performance as hp


class TestWindRangeFor(unittest.TestCase):
    def test_bands_match_boundaries(self):
        self.assertEqual(hp.wind_range_for(0), "0-6")
        self.assertEqual(hp.wind_range_for(5.9), "0-6")
        self.assertEqual(hp.wind_range_for(6), "6-12")
        self.assertEqual(hp.wind_range_for(11.9), "6-12")
        self.assertEqual(hp.wind_range_for(12), "12-20")
        self.assertEqual(hp.wind_range_for(19.9), "12-20")
        self.assertEqual(hp.wind_range_for(20), "20+")
        self.assertEqual(hp.wind_range_for(35), "20+")

    def test_missing_input_returns_none(self):
        self.assertIsNone(hp.wind_range_for(None))
        self.assertIsNone(hp.wind_range_for(-1))


class TestPerformancePercent(unittest.TestCase):
    def test_at_target_is_zero(self):
        self.assertAlmostEqual(hp.performance_percent(5.0, 5.0), 0.0)

    def test_below_target_is_negative(self):
        self.assertAlmostEqual(hp.performance_percent(4.0, 5.0), -20.0)

    def test_above_target_is_positive(self):
        self.assertAlmostEqual(hp.performance_percent(6.0, 5.0), 20.0)

    def test_missing_target_returns_none_not_zero_division(self):
        self.assertIsNone(hp.performance_percent(4.0, None))
        self.assertIsNone(hp.performance_percent(4.0, 0))

    def test_missing_actual_returns_none(self):
        self.assertIsNone(hp.performance_percent(None, 5.0))


class TestWeightedMean(unittest.TestCase):
    def test_simple_average_when_weights_equal(self):
        self.assertAlmostEqual(hp.weighted_mean([(4.0, 1), (6.0, 1)]), 5.0)

    def test_weights_bias_the_mean(self):
        # 9 samples at 4.0, 1 sample at 14.0 -> mean pulled toward 4.0
        self.assertAlmostEqual(hp.weighted_mean([(4.0, 9), (14.0, 1)]), 5.0)

    def test_empty_input_returns_none(self):
        self.assertIsNone(hp.weighted_mean([]))

    def test_all_zero_weight_returns_none(self):
        self.assertIsNone(hp.weighted_mean([(4.0, 0), (6.0, 0)]))

    def test_skips_none_values(self):
        self.assertAlmostEqual(hp.weighted_mean([(None, 5), (4.0, 1)]), 4.0)


class TestAggregateObservationsMissingData(unittest.TestCase):
    """The heatmap must distinguish 'no data logged' from 'measured
    zero' -- these tests pin down that aggregate_observations never
    fabricates a cell that had zero underlying samples."""

    def setUp(self):
        self.sessions_by_id = {1: {"date": "2026-08-31", "name": "2026-08-31 Monday Nights"}}

    def test_only_emits_cells_with_data(self):
        rows = [
            (1, 10.0, 5.0, 6.0, "beat", "starboard"),
            (1, 10.0, 5.2, 6.0, "beat", "starboard"),
        ]
        observations = hp.aggregate_observations(rows, self.sessions_by_id)
        self.assertEqual(len(observations), 1)
        obs = observations[0]
        self.assertEqual(obs["windRange"], "6-12")
        self.assertEqual(obs["tack"], "starboard")
        self.assertEqual(obs["angleBand"], "upwind")
        self.assertEqual(obs["sampleCount"], 2)
        self.assertAlmostEqual(obs["actualSpeedKnots"], 5.1, places=2)

    def test_no_fabricated_cell_for_untouched_combo(self):
        rows = [(1, 10.0, 5.0, 6.0, "beat", "starboard")]
        observations = hp.aggregate_observations(rows, self.sessions_by_id)
        keys = {(o["windRange"], o["tack"], o["angleBand"]) for o in observations}
        self.assertNotIn(("6-12", "port", "upwind"), keys)
        self.assertEqual(len(observations), 1)

    def test_unknown_tack_is_skipped(self):
        rows = [(1, 10.0, 5.0, 6.0, "beat", None)]
        self.assertEqual(hp.aggregate_observations(rows, self.sessions_by_id), [])

    def test_unknown_session_is_skipped(self):
        rows = [(999, 10.0, 5.0, 6.0, "beat", "starboard")]
        self.assertEqual(hp.aggregate_observations(rows, self.sessions_by_id), [])

    def test_out_of_band_point_of_sail_is_skipped(self):
        rows = [(1, 10.0, 5.0, 6.0, "unknown-angle", "starboard")]
        self.assertEqual(hp.aggregate_observations(rows, self.sessions_by_id), [])


class TestSortSessionsReverseChronological(unittest.TestCase):
    def test_most_recent_first(self):
        sessions = [
            {"id": 1, "date": "2026-07-13"},
            {"id": 3, "date": "2026-08-31"},
            {"id": 2, "date": "2026-08-05"},
        ]
        ordered = hp.sort_sessions_reverse_chronological(sessions)
        self.assertEqual([s["id"] for s in ordered], [3, 2, 1])

    def test_ties_break_on_id_descending(self):
        sessions = [
            {"id": 5, "date": "2026-08-31"},
            {"id": 7, "date": "2026-08-31"},
        ]
        ordered = hp.sort_sessions_reverse_chronological(sessions)
        self.assertEqual([s["id"] for s in ordered], [7, 5])

    def test_does_not_mutate_input(self):
        sessions = [{"id": 1, "date": "2026-07-13"}, {"id": 2, "date": "2026-08-05"}]
        original_order = [s["id"] for s in sessions]
        hp.sort_sessions_reverse_chronological(sessions)
        self.assertEqual([s["id"] for s in sessions], original_order)


class TestEventTypeForLabel(unittest.TestCase):
    def test_recognizes_known_labels_case_insensitively(self):
        self.assertEqual(hp.event_type_for_label("rig tune - (6~10)"), "rig-tune")
        self.assertEqual(hp.event_type_for_label("Rig Tune -(2-12)"), "rig-tune")
        self.assertEqual(hp.event_type_for_label("Sail Change"), "sail-change")
        self.assertEqual(hp.event_type_for_label("sailchange"), "sail-change")
        self.assertEqual(hp.event_type_for_label("Bottom clean"), "hull-cleaning")

    def test_unrecognized_label_is_other(self):
        self.assertEqual(hp.event_type_for_label("Mast Rake set"), "other")
        self.assertEqual(hp.event_type_for_label(""), "other")


class TestBuildEventsFromLog(unittest.TestCase):
    def test_joins_values_into_description(self):
        entries = [{"id": 20, "date": "2026-08-31", "label": "rig tune",
                    "values": ["30", "15", "15", "Tuned for higher wind."]}]
        events = hp.build_events_from_log(entries)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["id"], "20")
        self.assertEqual(event["type"], "rig-tune")
        self.assertEqual(event["description"], "30, 15, 15, Tuned for higher wind.")


class TestPlaceEventsRelativeToSessions(unittest.TestCase):
    def setUp(self):
        # newest-first, matching the heatmap's column order
        self.sessions_desc = [
            {"id": 3, "date": "2026-08-31"},
            {"id": 2, "date": "2026-08-10"},
            {"id": 1, "date": "2026-07-13"},
        ]

    def test_event_between_two_races_lands_at_that_boundary(self):
        events = [{"id": "e1", "date": "2026-08-20"}]
        placements = hp.place_events_relative_to_sessions(events, self.sessions_desc)
        # only session 3 (2026-08-31) is >= 2026-08-20
        self.assertEqual(placements[0]["boundary_index"], 1)

    def test_event_on_same_date_as_a_race_lands_to_its_right(self):
        events = [{"id": "e1", "date": "2026-08-10"}]
        placements = hp.place_events_relative_to_sessions(events, self.sessions_desc)
        # sessions 3 and 2 are both >= 2026-08-10
        self.assertEqual(placements[0]["boundary_index"], 2)

    def test_event_newer_than_every_session_lands_at_left_edge(self):
        events = [{"id": "e1", "date": "2026-09-15"}]
        placements = hp.place_events_relative_to_sessions(events, self.sessions_desc)
        self.assertEqual(placements[0]["boundary_index"], 0)

    def test_event_older_than_every_session_lands_at_right_edge(self):
        events = [{"id": "e1", "date": "2026-01-01"}]
        placements = hp.place_events_relative_to_sessions(events, self.sessions_desc)
        self.assertEqual(placements[0]["boundary_index"], len(self.sessions_desc))


if __name__ == "__main__":
    unittest.main()
