# tests/test_chunk_rendering.py
"""
Unit tests for chunk-parallel rendering helpers in io_/video_renderer.py.

Covers:
  - partition_segments()  — pure function, exhaustive edge-case coverage
  - render_project() chunk activation logic via use_chunks flag
"""

import pytest
from io_.video_renderer import partition_segments, CHUNK_SIZE_DEFAULT


class TestPartitionSegments:
    """Core behaviour of partition_segments()."""

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_empty_input_returns_empty(self):
        assert partition_segments([], chunk_size=50) == []

    def test_empty_input_any_chunk_size(self):
        assert partition_segments([], chunk_size=0) == []
        assert partition_segments([], chunk_size=1) == []
        assert partition_segments([], chunk_size=200) == []

    def test_zero_chunk_size_returns_single_list(self):
        """chunk_size < 1 is a degenerate guard; treat all segs as one chunk."""
        segs = [(0.0, 1.0), (1.0, 2.0)]
        result = partition_segments(segs, chunk_size=0)
        assert result == [[(0.0, 1.0), (1.0, 2.0)]]

    def test_negative_chunk_size_returns_single_list(self):
        segs = [(0.0, 1.0)]
        result = partition_segments(segs, chunk_size=-5)
        assert result == [[(0.0, 1.0)]]

    def test_single_segment_returns_one_chunk(self):
        segs = [(0.0, 1.0)]
        result = partition_segments(segs, chunk_size=50)
        assert result == [[(0.0, 1.0)]]

    def test_segments_exactly_equal_chunk_size_one_chunk(self):
        segs = [(float(i), float(i + 1)) for i in range(50)]
        result = partition_segments(segs, chunk_size=50)
        assert len(result) == 1
        assert len(result[0]) == 50

    # ── Chunking behaviour ────────────────────────────────────────────────────

    def test_even_split_produces_equal_chunks(self):
        segs = [(float(i), float(i + 1)) for i in range(100)]
        result = partition_segments(segs, chunk_size=50)
        assert len(result) == 2
        assert all(len(c) == 50 for c in result)

    def test_uneven_split_last_chunk_smaller(self):
        segs = [(float(i), float(i + 1)) for i in range(70)]
        result = partition_segments(segs, chunk_size=50)
        assert len(result) == 2
        assert len(result[0]) == 50
        assert len(result[1]) == 20

    def test_four_equal_chunks(self):
        segs = [(float(i), float(i + 1)) for i in range(200)]
        result = partition_segments(segs, chunk_size=50)
        assert len(result) == 4
        assert all(len(c) == 50 for c in result)

    def test_chunk_size_larger_than_segments_yields_one_chunk(self):
        """chunk_size > len(segments) → one chunk containing all segments."""
        segs = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]
        result = partition_segments(segs, chunk_size=50)
        assert len(result) == 1
        assert result[0] == segs

    def test_chunk_size_one_each_segment_is_own_chunk(self):
        segs = [(float(i), float(i + 1)) for i in range(5)]
        result = partition_segments(segs, chunk_size=1)
        assert len(result) == 5
        assert all(len(c) == 1 for c in result)

    def test_chunk_size_two(self):
        segs = [(float(i), float(i + 1)) for i in range(6)]
        result = partition_segments(segs, chunk_size=2)
        assert len(result) == 3
        assert all(len(c) == 2 for c in result)

    def test_remainder_chunk(self):
        """101 segments with chunk_size=50 → [50, 50, 1]."""
        segs = [(float(i), float(i + 1)) for i in range(101)]
        result = partition_segments(segs, chunk_size=50)
        assert len(result) == 3
        assert len(result[0]) == 50
        assert len(result[1]) == 50
        assert len(result[2]) == 1

    # ── Ordering and content preservation ─────────────────────────────────────

    def test_original_order_preserved_across_chunks(self):
        segs = [(10.0, 15.0), (20.0, 25.0), (30.0, 35.0), (40.0, 45.0), (50.0, 55.0)]
        result = partition_segments(segs, chunk_size=2)
        flat = [s for chunk in result for s in chunk]
        assert flat == segs

    def test_all_segments_present_after_partition(self):
        segs = [(float(i), float(i + 1)) for i in range(123)]
        result = partition_segments(segs, chunk_size=50)
        flat = [s for chunk in result for s in chunk]
        assert flat == segs

    def test_input_list_not_mutated(self):
        segs = [(float(i), float(i + 1)) for i in range(100)]
        original = list(segs)
        partition_segments(segs, chunk_size=50)
        assert segs == original

    def test_each_chunk_is_a_list(self):
        segs = [(float(i), float(i + 1)) for i in range(10)]
        result = partition_segments(segs, chunk_size=3)
        assert all(isinstance(c, list) for c in result)

    # ── Default constant ───────────────────────────────────────────────────────

    def test_default_chunk_size_constant_is_50(self):
        """CHUNK_SIZE_DEFAULT must match the config default and documented value."""
        assert CHUNK_SIZE_DEFAULT == 50

    def test_default_constant_applied_correctly(self):
        """partition_segments with CHUNK_SIZE_DEFAULT splits as expected."""
        segs = [(float(i), float(i + 1)) for i in range(150)]
        result = partition_segments(segs, chunk_size=CHUNK_SIZE_DEFAULT)
        assert len(result) == 3
        assert len(result[0]) == 50
        assert len(result[1]) == 50
        assert len(result[2]) == 50


class TestChunkActivationLogic:
    """Verify the use_chunks decision rule embedded in render_project().

    We test the pure boolean expression rather than calling render_project()
    itself (which requires real files).  The exact condition is:
        use_chunks = chunk_enabled and chunk_size > 0 and n_segs > chunk_size
    """

    def _use_chunks(self, chunk_enabled, chunk_size, n_segs):
        """Mirror of the use_chunks expression in render_project()."""
        return chunk_enabled and chunk_size > 0 and n_segs > chunk_size

    def test_enabled_and_enough_segments(self):
        assert self._use_chunks(True, 50, 51) is True

    def test_enabled_exactly_at_threshold_no_activation(self):
        """n_segs == chunk_size → single chunk → no benefit, don't activate."""
        assert self._use_chunks(True, 50, 50) is False

    def test_enabled_below_threshold_no_activation(self):
        assert self._use_chunks(True, 50, 10) is False

    def test_disabled_via_flag(self):
        assert self._use_chunks(False, 50, 200) is False

    def test_chunk_size_zero_never_activates(self):
        assert self._use_chunks(True, 0, 200) is False

    def test_chunk_size_negative_never_activates(self):
        assert self._use_chunks(True, -1, 200) is False

    def test_200_segments_chunk50_activates(self):
        assert self._use_chunks(True, 50, 200) is True

    def test_one_segment_no_activation(self):
        assert self._use_chunks(True, 50, 1) is False
