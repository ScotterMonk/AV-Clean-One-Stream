# tests/test_renderer.py
# Created by coder-sr | 2026-03-15
"""Unit tests for io_/video_renderer.py — single-stream render contract.

Covers:
- render_project() accepts (input_path, manifest, output_path, config)
- render_project() raises ValueError when output_path is missing / empty
- render_project() dispatches to two-phase when config flag set
- merge_close_segments() — segment gap merging (pure, no FFmpeg)
- merge_close_segments_adaptive() — adaptive threshold widening
- partition_segments() — chunk splitting for parallel render

All FFmpeg / subprocess calls are mocked; no real media files required.
"""

import inspect

import pytest
from unittest.mock import MagicMock, patch, call

from io_.video_renderer import (
    ADAPTIVE_SEGMENT_GAP_MAX_S,
    ADAPTIVE_SEGMENT_COUNT_HIGH,
    ADAPTIVE_SEGMENT_COUNT_TARGET,
    SEGMENT_GAP_MERGE_THRESHOLD_S,
    _apply_cut_fades,
    merge_close_segments,
    merge_close_segments_adaptive,
    partition_segments,
    render_project,
)
from core.interfaces import EditManifest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _manifest(keep_segments=None, filters=None) -> EditManifest:
    m = EditManifest()
    if keep_segments:
        m.keep_segments = list(keep_segments)
    return m


def _base_config(overrides=None) -> dict:
    cfg = {
        "video_codec": "libx264",
        "audio_codec": "aac",
        "chunk_parallel_enabled": False,
        "two_phase_render_enabled": False,
        "cuda_decode_enabled": False,
        "cuda_encode_enabled": False,
    }
    if overrides:
        cfg.update(overrides)
    return cfg


def _fake_caps() -> dict:
    return {"hwaccels": [], "encoders": {"libx264", "aac"}}


def _fake_enc_opts() -> dict:
    return {
        "vcodec": "libx264",
        "preset": "fast",
        "crf": 23,
        "acodec": "aac",
        "audio_bitrate": "192k",
    }


# ---------------------------------------------------------------------------
# render_project() — signature and guard rail tests
# ---------------------------------------------------------------------------

class TestRenderProjectSignature:
    """render_project() has a defined single-stream 4-argument signature."""

    def test_signature_has_exactly_four_params(self):
        sig = inspect.signature(render_project)
        assert list(sig.parameters.keys()) == ["input_path", "manifest", "output_path", "config"]

    def test_raises_value_error_when_output_path_is_none(self):
        with pytest.raises(ValueError, match="output path"):
            render_project("input.mp4", _manifest(), None, _base_config())

    def test_raises_value_error_when_output_path_is_empty_string(self):
        with pytest.raises(ValueError, match="output path"):
            render_project("input.mp4", _manifest(), "", _base_config())


# ---------------------------------------------------------------------------
# render_project() — dispatch tests (FFmpeg fully mocked)
# ---------------------------------------------------------------------------

class TestRenderProjectDispatch:
    """Verify render_project() routes to the right render path."""

    @patch("io_.video_renderer.probe_ffmpeg_capabilities")
    @patch("io_.video_renderer.select_enc_opts")
    @patch("io_.video_renderer._render_with_safe_overwrite")
    def test_calls_render_with_safe_overwrite_for_standard_path(
        self, mock_safe_overwrite, mock_enc, mock_probe
    ):
        """Standard (non-two-phase) single-pass render reaches _render_with_safe_overwrite."""
        mock_probe.return_value = _fake_caps()
        mock_enc.return_value = _fake_enc_opts()

        render_project("input.mp4", _manifest(), "output.mp4", _base_config())

        mock_safe_overwrite.assert_called_once()
        # First two args must be input and output paths
        args = mock_safe_overwrite.call_args[0]
        assert args[0] == "input.mp4"
        assert args[1] == "output.mp4"

    @patch("io_.video_renderer.probe_ffmpeg_capabilities")
    @patch("io_.video_renderer.select_enc_opts")
    @patch("io_.video_renderer._render_with_safe_overwrite")
    def test_does_not_raise_with_empty_manifest(
        self, mock_safe_overwrite, mock_enc, mock_probe
    ):
        """render_project() must not raise with an empty manifest (no cuts, no filters)."""
        mock_probe.return_value = _fake_caps()
        mock_enc.return_value = _fake_enc_opts()
        render_project("input.mp4", EditManifest(), "output.mp4", _base_config())

    @patch("io_.video_renderer.probe_ffmpeg_capabilities")
    def test_delegates_to_two_phase_when_flag_set(self, mock_probe):
        """two_phase_render_enabled=True → render_project_two_phase is called.

        The import of render_project_two_phase is lazy (inside the if-branch),
        so we patch the function on its source module.
        """
        mock_probe.return_value = _fake_caps()
        cfg = _base_config({"two_phase_render_enabled": True})
        m = _manifest()
        with patch("io_.video_renderer_twophase.render_project_two_phase",
                   return_value="output.mp4") as mock_two_phase:
            render_project("input.mp4", m, "output.mp4", cfg)
        mock_two_phase.assert_called_once_with("input.mp4", m, "output.mp4", cfg)

    @patch("io_.video_renderer.probe_ffmpeg_capabilities")
    @patch("io_.video_renderer.select_enc_opts")
    @patch("io_.video_renderer._render_with_safe_overwrite")
    def test_two_phase_not_called_when_flag_is_false(
        self, mock_safe, mock_enc, mock_probe
    ):
        mock_probe.return_value = _fake_caps()
        mock_enc.return_value = _fake_enc_opts()
        with patch("io_.video_renderer_twophase.render_project_two_phase") as mock_two_phase:
            render_project("input.mp4", _manifest(), "output.mp4", _base_config())
        mock_two_phase.assert_not_called()

    @patch("io_.video_renderer.probe_ffmpeg_capabilities")
    @patch("io_.video_renderer.select_enc_opts")
    @patch("io_.video_renderer._render_with_safe_overwrite")
    def test_none_config_treated_as_empty_dict(
        self, mock_safe_overwrite, mock_enc, mock_probe
    ):
        """config=None must not raise — treated as {}."""
        mock_probe.return_value = _fake_caps()
        mock_enc.return_value = _fake_enc_opts()
        # Should not raise a TypeError on cfg.get(...)
        render_project("input.mp4", _manifest(), "output.mp4", None)


# ---------------------------------------------------------------------------
# merge_close_segments() — pure function; no FFmpeg
# ---------------------------------------------------------------------------

class TestMergeCloseSegments:
    """merge_close_segments() merges keep_segments whose inter-segment gap is tiny."""

    # ── edge cases ────────────────────────────────────────────────────────

    def test_empty_input_returns_empty_list(self):
        assert merge_close_segments([]) == []

    def test_single_segment_returned_as_is(self):
        assert merge_close_segments([(0.0, 5.0)]) == [(0.0, 5.0)]

    # ── merging behaviour ─────────────────────────────────────────────────

    def test_merges_when_gap_is_below_threshold(self):
        # 50 ms gap < 100 ms threshold → merged
        segs = [(0.0, 10.0), (10.05, 20.0)]
        result = merge_close_segments(segs, gap_threshold_s=0.100)
        assert result == [(0.0, 20.0)]

    def test_does_not_merge_when_gap_clearly_exceeds_threshold(self):
        # Gap (0.5 s) is well above threshold (0.1 s) → no merge.
        # Avoids floating-point subtraction hazards at the exact boundary.
        segs = [(0.0, 10.0), (10.5, 20.0)]
        result = merge_close_segments(segs, gap_threshold_s=0.1)
        assert len(result) == 2

    def test_does_not_merge_when_gap_exceeds_threshold(self):
        segs = [(0.0, 5.0), (10.0, 20.0)]
        result = merge_close_segments(segs)
        assert result == [(0.0, 5.0), (10.0, 20.0)]

    def test_merges_multiple_consecutive_micro_gaps(self):
        # Three segments all separated by 50 ms (< default 150 ms) → one merged segment
        segs = [(0.0, 5.0), (5.05, 10.0), (10.08, 15.0)]
        result = merge_close_segments(segs)
        assert result == [(0.0, 15.0)]

    def test_partial_merge_preserves_distant_segments(self):
        # First two merge; third is far away
        segs = [(0.0, 5.0), (5.05, 10.0), (20.0, 30.0)]
        result = merge_close_segments(segs)
        assert (0.0, 10.0) in result
        assert (20.0, 30.0) in result
        assert len(result) == 2

    def test_default_threshold_is_segment_gap_merge_threshold_s(self):
        """Explicit default matches the module constant."""
        gap = SEGMENT_GAP_MERGE_THRESHOLD_S
        segs = [(0.0, 10.0), (10.0 + gap - 0.001, 20.0)]  # just inside threshold
        result = merge_close_segments(segs)
        assert len(result) == 1  # merged

    # ── immutability ──────────────────────────────────────────────────────

    def test_does_not_mutate_input_list(self):
        segs = [(0.0, 5.0), (5.05, 10.0)]
        original = list(segs)
        merge_close_segments(segs)
        assert segs == original

    def test_returns_new_list_object(self):
        segs = [(0.0, 5.0)]
        result = merge_close_segments(segs)
        assert result is not segs

    # ── output type ───────────────────────────────────────────────────────

    def test_returns_list_of_tuples(self):
        segs = [(0.0, 5.0), (6.0, 10.0)]
        result = merge_close_segments(segs)
        for item in result:
            assert isinstance(item, tuple)


# ---------------------------------------------------------------------------
# merge_close_segments_adaptive() — adaptive threshold widening
# ---------------------------------------------------------------------------

class TestMergeCloseSegmentsAdaptive:
    """merge_close_segments_adaptive() widens threshold when segment count is very high."""

    def test_empty_input_returns_empty_list(self):
        assert merge_close_segments_adaptive([]) == []

    def test_single_segment_returned_unchanged(self):
        assert merge_close_segments_adaptive([(0.0, 5.0)]) == [(0.0, 5.0)]

    def test_result_is_never_longer_than_input(self):
        segs = [(float(i), float(i) + 0.5) for i in range(0, 30, 1)]
        result = merge_close_segments_adaptive(segs)
        assert len(result) <= len(segs)

    def test_does_not_mutate_input(self):
        segs = [(0.0, 5.0), (5.05, 10.0)]
        original = list(segs)
        merge_close_segments_adaptive(segs)
        assert segs == original

    def test_returns_list(self):
        segs = [(float(i), float(i) + 0.9) for i in range(20)]
        assert isinstance(merge_close_segments_adaptive(segs), list)

    def test_applies_adaptive_widening_for_high_segment_count(self):
        """When input exceeds ADAPTIVE_SEGMENT_COUNT_HIGH, widening reduces count."""
        # Build a segment list that is above the high-count trigger.
        # Each segment is 0.5 s long; gaps are 0.2 s (just above default 150 ms threshold).
        # Without adaptive widening, none should merge.
        # With widening (up to 300 ms), many consecutive 200 ms gaps should merge.
        n = ADAPTIVE_SEGMENT_COUNT_HIGH + 20
        segs = [(i * 0.7, i * 0.7 + 0.5) for i in range(n)]  # 200 ms gaps
        result = merge_close_segments_adaptive(segs)
        # Adaptive widening should have merged most pairs
        assert len(result) < len(segs)


# ---------------------------------------------------------------------------
# partition_segments() — chunk splitting for parallel render
# ---------------------------------------------------------------------------

class TestPartitionSegments:
    """partition_segments() splits keep_segments into sub-lists for parallel FFmpeg."""

    # ── edge cases ────────────────────────────────────────────────────────

    def test_empty_input_returns_empty(self):
        assert partition_segments([], chunk_size=50) == []

    def test_single_segment_wraps_in_one_chunk(self):
        result = partition_segments([(0.0, 1.0)], chunk_size=50)
        assert result == [[(0.0, 1.0)]]

    def test_chunk_size_less_than_one_returns_single_chunk(self):
        segs = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]
        result = partition_segments(segs, chunk_size=0)
        assert len(result) == 1
        assert result[0] == segs

    def test_chunk_size_negative_returns_single_chunk(self):
        segs = [(0.0, 1.0), (1.0, 2.0)]
        result = partition_segments(segs, chunk_size=-5)
        assert len(result) == 1

    # ── splitting ─────────────────────────────────────────────────────────

    def test_splits_into_correct_number_of_chunks(self):
        segs = [(float(i), float(i) + 1) for i in range(100)]
        result = partition_segments(segs, chunk_size=50)
        assert len(result) == 2

    def test_each_chunk_has_at_most_chunk_size_segments(self):
        segs = [(float(i), float(i) + 1) for i in range(110)]
        for chunk in partition_segments(segs, chunk_size=50):
            assert len(chunk) <= 50

    def test_all_segments_preserved_across_chunks(self):
        segs = [(float(i), float(i) + 1) for i in range(75)]
        result = partition_segments(segs, chunk_size=30)
        flat = [seg for chunk in result for seg in chunk]
        assert flat == segs

    def test_exact_multiple_of_chunk_size(self):
        segs = [(float(i), float(i) + 1) for i in range(60)]
        result = partition_segments(segs, chunk_size=20)
        assert len(result) == 3

    def test_non_multiple_of_chunk_size_has_smaller_last_chunk(self):
        segs = [(float(i), float(i) + 1) for i in range(55)]
        result = partition_segments(segs, chunk_size=20)
        # 3 chunks: 20 + 20 + 15
        assert len(result) == 3
        assert len(result[-1]) == 15

    def test_segment_ordering_preserved_within_chunks(self):
        segs = [(float(i), float(i) + 1) for i in range(10)]
        result = partition_segments(segs, chunk_size=4)
        assert result[0] == segs[0:4]
        assert result[1] == segs[4:8]
        assert result[2] == segs[8:10]

    # ── output type ───────────────────────────────────────────────────────

    def test_returns_list_of_lists(self):
        segs = [(float(i), float(i) + 1) for i in range(5)]
        result = partition_segments(segs, chunk_size=2)
        for chunk in result:
            assert isinstance(chunk, list)


# ---------------------------------------------------------------------------
# _apply_cut_fades() — audio fade helper for cut-edge click/pop elimination
# ---------------------------------------------------------------------------

class TestApplyCutFades:
    """_apply_cut_fades() inserts afade in/out filters at cut splice boundaries."""

    def test_returns_original_when_cut_fade_s_is_zero(self):
        """cut_fade_s=0 → nothing applied; original stream returned unchanged."""
        seg = MagicMock()
        result = _apply_cut_fades(seg, idx=1, n_segs=3, seg_dur=5.0, cut_fade_s=0.0)
        assert result is seg
        seg.filter_.assert_not_called()

    def test_single_segment_no_fades(self):
        """idx=0, n_segs=1 → no preceding or following cut; no fades applied."""
        seg = MagicMock()
        result = _apply_cut_fades(seg, idx=0, n_segs=1, seg_dur=5.0, cut_fade_s=0.015)
        assert result is seg
        seg.filter_.assert_not_called()

    def test_first_segment_gets_only_fade_out(self):
        """First of multiple segments: no preceding cut → no fade-in; has trailing cut → fade-out."""
        seg = MagicMock()
        _apply_cut_fades(seg, idx=0, n_segs=3, seg_dur=5.0, cut_fade_s=0.015)
        calls = seg.filter_.call_args_list
        assert len(calls) == 1
        assert calls[0].args[0] == "afade"
        assert calls[0].kwargs["t"] == "out"

    def test_last_segment_gets_only_fade_in(self):
        """Last of multiple segments: has preceding cut → fade-in; no trailing cut → no fade-out."""
        seg = MagicMock()
        _apply_cut_fades(seg, idx=2, n_segs=3, seg_dur=5.0, cut_fade_s=0.015)
        calls = seg.filter_.call_args_list
        assert len(calls) == 1
        assert calls[0].args[0] == "afade"
        assert calls[0].kwargs["t"] == "in"

    def test_middle_segment_gets_both_fades(self):
        """Inner segment (not first, not last): gets fade-in then fade-out in that order."""
        seg = MagicMock()
        # MagicMock chaining: seg.filter_() → m1, m1.filter_() → m2
        m1 = seg.filter_.return_value
        m2 = m1.filter_.return_value

        result = _apply_cut_fades(seg, idx=1, n_segs=3, seg_dur=5.0, cut_fade_s=0.015)

        # Fade-in applied first on the raw segment
        seg.filter_.assert_called_once_with("afade", t="in", st=0, d=0.015)
        # Fade-out applied second on the result of fade-in (m1)
        m1.filter_.assert_called_once_with("afade", t="out", st=pytest.approx(5.0 - 0.015), d=0.015)
        assert result is m2

    def test_segment_too_short_for_both_fades_returns_original(self):
        """Middle segment shorter than 2 × cut_fade_s → skip both fades."""
        seg = MagicMock()
        # Needs 2 × 0.015 = 0.030 s but only 0.025 s available
        result = _apply_cut_fades(seg, idx=1, n_segs=3, seg_dur=0.025, cut_fade_s=0.015)
        assert result is seg
        seg.filter_.assert_not_called()

    def test_segment_too_short_for_single_fade_returns_original(self):
        """Single-fade segment (first/last) shorter than cut_fade_s → skip."""
        seg = MagicMock()
        # First segment needs only 1 × 0.015 = 0.015 s; provide exactly 0.015 (not strictly greater)
        result = _apply_cut_fades(seg, idx=0, n_segs=2, seg_dur=0.015, cut_fade_s=0.015)
        assert result is seg
        seg.filter_.assert_not_called()

    def test_fade_out_start_time_equals_seg_dur_minus_fade_dur(self):
        """fade-out must start at (seg_dur - cut_fade_s) so it finishes exactly at segment end."""
        seg = MagicMock()
        fade_dur = 0.020
        seg_dur = 3.0
        # First segment of 2: only fade-out
        _apply_cut_fades(seg, idx=0, n_segs=2, seg_dur=seg_dur, cut_fade_s=fade_dur)
        call = seg.filter_.call_args_list[0]
        assert call.kwargs["st"] == pytest.approx(seg_dur - fade_dur)
        assert call.kwargs["d"] == pytest.approx(fade_dur)

    def test_fade_in_start_time_is_zero(self):
        """fade-in must always start at st=0 (immediately after atrim resets PTS)."""
        seg = MagicMock()
        # Last segment of 2: only fade-in
        _apply_cut_fades(seg, idx=1, n_segs=2, seg_dur=3.0, cut_fade_s=0.015)
        call = seg.filter_.call_args_list[0]
        assert call.kwargs["t"] == "in"
        assert call.kwargs["st"] == 0
