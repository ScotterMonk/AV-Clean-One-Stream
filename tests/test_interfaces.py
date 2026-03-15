# tests/test_interfaces.py
# Created by coder-sr | 2026-03-15
"""Tests for core/interfaces.py — EditManifest single-stream contract.

Covers:
- Default field values
- add_filter() appends AudioFilter to filters list
- compute_keep_segments() derivation from removal_segments
"""

import pytest
from core.interfaces import AudioFilter, EditManifest


# ---------------------------------------------------------------------------
# Default state
# ---------------------------------------------------------------------------

class TestEditManifestDefaults:
    def test_filters_starts_empty(self):
        m = EditManifest()
        assert m.filters == []

    def test_removal_segments_starts_empty(self):
        m = EditManifest()
        assert m.removal_segments == []

    def test_keep_segments_starts_empty(self):
        m = EditManifest()
        assert m.keep_segments == []

    def test_no_host_or_guest_filters_attribute(self):
        """Single-stream: host_filters / guest_filters must not exist."""
        m = EditManifest()
        assert not hasattr(m, "host_filters")
        assert not hasattr(m, "guest_filters")


# ---------------------------------------------------------------------------
# add_filter()
# ---------------------------------------------------------------------------

class TestAddFilter:
    def test_add_filter_appends_audio_filter_instance(self):
        m = EditManifest()
        m.add_filter("volume", volume=1.5)
        assert len(m.filters) == 1
        assert isinstance(m.filters[0], AudioFilter)

    def test_add_filter_stores_name(self):
        m = EditManifest()
        m.add_filter("highpass", frequency=80)
        assert m.filters[0].filter_name == "highpass"

    def test_add_filter_stores_kwargs_as_params(self):
        m = EditManifest()
        m.add_filter("volume", volume=1.5)
        assert m.filters[0].params == {"volume": 1.5}

    def test_add_filter_multiple_appends_in_order(self):
        m = EditManifest()
        m.add_filter("highpass", frequency=80)
        m.add_filter("lowpass", frequency=8000)
        assert len(m.filters) == 2
        assert m.filters[0].filter_name == "highpass"
        assert m.filters[1].filter_name == "lowpass"

    def test_add_filter_no_kwargs_stores_empty_params(self):
        m = EditManifest()
        m.add_filter("anull")
        assert m.filters[0].filter_name == "anull"
        assert m.filters[0].params == {}

    def test_add_filter_multiple_kwargs(self):
        m = EditManifest()
        m.add_filter("equalizer", frequency=1000, width=200, gain=3.0)
        assert m.filters[0].params == {"frequency": 1000, "width": 200, "gain": 3.0}


# ---------------------------------------------------------------------------
# compute_keep_segments()
# ---------------------------------------------------------------------------

class TestComputeKeepSegments:
    def test_no_removals_returns_existing_keep_segments_unchanged(self):
        """When removal_segments is empty, the existing keep_segments is returned as-is."""
        m = EditManifest()
        m.keep_segments = [(0.0, 10.0)]
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 10.0)]

    def test_single_removal_middle_yields_two_keeps(self):
        m = EditManifest()
        m.add_removal(3.0, 7.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 3.0), (7.0, 10.0)]

    def test_removal_at_start_omits_leading_segment(self):
        m = EditManifest()
        m.add_removal(0.0, 5.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(5.0, 10.0)]

    def test_removal_at_end_omits_trailing_segment(self):
        m = EditManifest()
        m.add_removal(8.0, 10.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 8.0)]

    def test_full_removal_yields_empty_list(self):
        m = EditManifest()
        m.add_removal(0.0, 10.0)
        result = m.compute_keep_segments(10.0)
        assert result == []

    def test_overlapping_removals_are_merged(self):
        m = EditManifest()
        m.add_removal(2.0, 6.0)
        m.add_removal(4.0, 8.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 2.0), (8.0, 10.0)]

    def test_adjacent_removals_are_merged(self):
        m = EditManifest()
        m.add_removal(2.0, 5.0)
        m.add_removal(5.0, 8.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 2.0), (8.0, 10.0)]

    def test_multiple_disjoint_removals_produce_multiple_keeps(self):
        m = EditManifest()
        m.add_removal(1.0, 2.0)
        m.add_removal(4.0, 5.0)
        m.add_removal(7.0, 8.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 1.0), (2.0, 4.0), (5.0, 7.0), (8.0, 10.0)]

    def test_out_of_order_removals_are_sorted(self):
        """Removals added in reverse order must still produce correct keep segments."""
        m = EditManifest()
        m.add_removal(7.0, 9.0)
        m.add_removal(1.0, 3.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 1.0), (3.0, 7.0), (9.0, 10.0)]

    def test_result_is_stored_in_keep_segments(self):
        """Computed result is written to self.keep_segments."""
        m = EditManifest()
        m.add_removal(3.0, 6.0)
        result = m.compute_keep_segments(10.0)
        assert m.keep_segments == result

    def test_multiple_calls_accumulate_all_removals(self):
        """Each call to add_removal grows removal_segments; compute uses the full list."""
        m = EditManifest()
        m.add_removal(1.0, 2.0)
        m.compute_keep_segments(10.0)  # first call
        m.add_removal(5.0, 6.0)
        result = m.compute_keep_segments(10.0)  # second call sees both removals
        assert result == [(0.0, 1.0), (2.0, 5.0), (6.0, 10.0)]
