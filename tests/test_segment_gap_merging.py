# tests/test_segment_gap_merging.py
"""
Unit tests for merge_close_segments() and merge_close_segments_adaptive()
in io_/video_renderer.py.

Verifies that adjacent keep_segments whose inter-segment gap is below the
SEGMENT_GAP_MERGE_THRESHOLD_S constant are merged (reducing filter graph
complexity) and that the adaptive variant widens the threshold automatically
when segment count is too high.
"""

import pytest
from io_.video_renderer import (
    merge_close_segments,
    merge_close_segments_adaptive,
    SEGMENT_GAP_MERGE_THRESHOLD_S,
    ADAPTIVE_SEGMENT_COUNT_HIGH,
    ADAPTIVE_SEGMENT_COUNT_TARGET,
    ADAPTIVE_SEGMENT_GAP_MAX_S,
)


class TestMergeCloseSegments:
    """Core behaviour of the merge_close_segments() helper."""

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_empty_input_returns_empty(self):
        assert merge_close_segments([]) == []

    def test_single_segment_returned_unchanged(self):
        segs = [(1.0, 3.0)]
        assert merge_close_segments(segs) == [(1.0, 3.0)]

    def test_input_list_is_not_mutated(self):
        segs = [(0.0, 1.0), (1.05, 2.0)]
        original = list(segs)
        merge_close_segments(segs)
        assert segs == original

    # ── Merge behaviour ───────────────────────────────────────────────────────

    def test_gap_below_threshold_is_merged(self):
        """60 ms gap < 80 ms threshold → single merged segment."""
        segs = [(10.0, 12.5), (12.56, 15.0)]  # 60 ms gap
        result = merge_close_segments(segs, gap_threshold_s=0.080)
        assert result == [(10.0, 15.0)]

    def test_gap_exactly_at_threshold_is_not_merged(self):
        """Gap == threshold is NOT strictly below → keep as two segments."""
        segs = [(0.0, 1.0), (1.080, 2.0)]  # gap == 80 ms
        result = merge_close_segments(segs, gap_threshold_s=0.080)
        assert result == [(0.0, 1.0), (1.080, 2.0)]

    def test_gap_above_threshold_is_not_merged(self):
        """200 ms gap > 80 ms threshold → kept as separate segments."""
        segs = [(0.0, 1.0), (1.2, 2.0)]  # 200 ms gap
        result = merge_close_segments(segs, gap_threshold_s=0.080)
        assert result == [(0.0, 1.0), (1.2, 2.0)]

    def test_gap_just_below_threshold_is_merged(self):
        """79 ms gap is strictly below 80 ms → merged."""
        segs = [(0.0, 1.0), (1.079, 2.0)]  # 79 ms gap
        result = merge_close_segments(segs, gap_threshold_s=0.080)
        assert result == [(0.0, 2.0)]

    # ── Multi-segment chains ──────────────────────────────────────────────────

    def test_chain_of_three_all_micro_gaps_merged_into_one(self):
        """Three segments with sub-threshold gaps → one merged segment."""
        segs = [(0.0, 1.0), (1.05, 2.0), (2.06, 3.0)]  # 50 ms, 60 ms gaps
        result = merge_close_segments(segs, gap_threshold_s=0.080)
        assert result == [(0.0, 3.0)]

    def test_alternating_micro_and_macro_gaps(self):
        """Only sub-threshold gaps merged; large gaps preserved."""
        segs = [
            (0.0, 1.0),   # ← 60 ms gap (merge) →
            (1.06, 2.0),  # ← 500 ms gap (keep) →
            (2.5, 3.5),   # ← 70 ms gap (merge) →
            (3.57, 4.5),
        ]
        result = merge_close_segments(segs, gap_threshold_s=0.080)
        assert result == [(0.0, 2.0), (2.5, 4.5)]

    def test_five_segments_two_micro_gaps(self):
        """Realistic scenario: 5 segments, 2 micro-gaps → 3 segments."""
        segs = [
            (0.0, 5.0),
            (5.05, 10.0),   # 50 ms → merge
            (11.0, 15.0),   # 1 s → keep
            (16.0, 20.0),   # 1 s → keep
            (20.06, 25.0),  # 60 ms → merge
        ]
        result = merge_close_segments(segs, gap_threshold_s=0.080)
        assert result == [(0.0, 10.0), (11.0, 15.0), (16.0, 25.0)]

    def test_all_gaps_above_threshold_no_merges(self):
        """No micro-gaps → output identical to input."""
        segs = [(0.0, 1.0), (2.0, 3.0), (4.0, 5.0)]
        result = merge_close_segments(segs, gap_threshold_s=0.080)
        assert result == [(0.0, 1.0), (2.0, 3.0), (4.0, 5.0)]

    # ── Default threshold constant ────────────────────────────────────────────

    def test_default_threshold_is_150ms(self):
        """Base threshold raised to 150 ms for podcast content imperceptibility."""
        assert SEGMENT_GAP_MERGE_THRESHOLD_S == pytest.approx(0.150)

    def test_uses_default_threshold_when_omitted(self):
        """Calling without explicit gap_threshold_s uses the 150 ms default."""
        segs = [(0.0, 1.0), (1.079, 2.0)]  # 79 ms gap < 150 ms default → merged
        result = merge_close_segments(segs)
        assert result == [(0.0, 2.0)]

    def test_default_threshold_does_not_merge_151ms_gap(self):
        """Gap above 150 ms is NOT strictly below threshold → kept separate."""
        segs = [(0.0, 1.0), (1.151, 2.0)]  # 151 ms gap > 150 ms threshold → not merged
        result = merge_close_segments(segs)
        assert result == [(0.0, 1.0), (1.151, 2.0)]

    # ── Custom threshold override ─────────────────────────────────────────────

    def test_zero_threshold_never_merges(self):
        """gap_threshold_s=0 means no gap is below the threshold → no merges."""
        segs = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]  # touching segments
        result = merge_close_segments(segs, gap_threshold_s=0.0)
        assert result == [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]

    def test_large_threshold_merges_everything(self):
        """gap_threshold_s=10 should merge all segments with gaps < 10 s."""
        segs = [(0.0, 1.0), (3.0, 5.0), (8.0, 10.0)]  # gaps: 2s, 3s
        result = merge_close_segments(segs, gap_threshold_s=10.0)
        assert result == [(0.0, 10.0)]


class TestMergeCloseSegmentsAdaptive:
    """Tests for the adaptive merge wrapper that widens threshold on high segment counts."""

    # ── Adaptive constant values ──────────────────────────────────────────────

    def test_adaptive_constants_are_sane(self):
        """Verify the module-level adaptive constants have expected values."""
        assert ADAPTIVE_SEGMENT_COUNT_HIGH == 150
        assert ADAPTIVE_SEGMENT_COUNT_TARGET == 100
        assert ADAPTIVE_SEGMENT_GAP_MAX_S == pytest.approx(0.300)

    # ── Fast path (no adaptive widening needed) ───────────────────────────────

    def test_empty_input_returns_empty(self):
        assert merge_close_segments_adaptive([]) == []

    def test_single_segment_unchanged(self):
        assert merge_close_segments_adaptive([(1.0, 3.0)]) == [(1.0, 3.0)]

    def test_low_count_uses_base_threshold_only(self):
        """When merged count stays below high_count, no adaptive pass runs."""
        # 5 segments with 200 ms gaps — well above 150 ms base → not merged
        segs = [(float(i), float(i) + 0.5) for i in range(0, 10, 2)]  # 5 segments
        result = merge_close_segments_adaptive(
            segs,
            base_threshold_s=0.150,
            high_count=150,
            target_count=100,
        )
        # 200 ms gaps are above 150 ms base threshold → no merges
        assert result == segs

    def test_low_count_with_micro_gaps_merged_by_base(self):
        """Sub-threshold gaps merged in the base pass; adaptive not triggered."""
        # 3 segments with 100 ms gaps (< 150 ms base) → merged to 1
        segs = [(0.0, 1.0), (1.10, 2.0), (2.10, 3.0)]
        result = merge_close_segments_adaptive(
            segs,
            base_threshold_s=0.150,
            high_count=150,
        )
        assert result == [(0.0, 3.0)]

    # ── Adaptive path activated ───────────────────────────────────────────────

    def _make_segments(self, count: int, gap_s: float = 0.200) -> list:
        """Build *count* segments each 1 s long separated by *gap_s* gaps."""
        segs = []
        t = 0.0
        for _ in range(count):
            segs.append((t, t + 1.0))
            t += 1.0 + gap_s
        return segs

    def test_adaptive_widens_when_count_exceeds_high(self):
        """160 segments with 200 ms gaps: base (150 ms) doesn't merge; adaptive widens."""
        segs = self._make_segments(160, gap_s=0.200)  # 200 ms gaps
        result = merge_close_segments_adaptive(
            segs,
            base_threshold_s=0.150,
            high_count=150,     # trigger: count=160 > 150
            target_count=100,
            max_threshold_s=0.300,
            step_s=0.010,
        )
        # At 210 ms threshold the 200 ms gaps merge → all 160 collapse into 1
        assert len(result) < 150

    def test_adaptive_stops_at_target(self):
        """Adaptive widening stops as soon as count drops below target_count."""
        # 160 segments; 200 ms gaps.  At threshold ≥ 201 ms all merge into 1.
        segs = self._make_segments(160, gap_s=0.200)
        result = merge_close_segments_adaptive(
            segs,
            base_threshold_s=0.150,
            high_count=150,
            target_count=100,
            max_threshold_s=0.300,
            step_s=0.010,
        )
        assert len(result) < 100

    def test_adaptive_respects_max_threshold_ceiling(self):
        """If target can't be reached before max_threshold_s, stops at ceiling."""
        # 160 segments with 500 ms gaps — even 300 ms ceiling can't bridge them.
        segs = self._make_segments(160, gap_s=0.500)
        result = merge_close_segments_adaptive(
            segs,
            base_threshold_s=0.150,
            high_count=150,
            target_count=100,
            max_threshold_s=0.300,
            step_s=0.010,
        )
        # 500 ms gaps are > 300 ms ceiling → no merges occur; count unchanged
        assert len(result) == 160

    def test_adaptive_does_not_mutate_input(self):
        """Input list must not be modified by the adaptive function."""
        segs = self._make_segments(160, gap_s=0.200)
        original = list(segs)
        merge_close_segments_adaptive(segs)
        assert segs == original
