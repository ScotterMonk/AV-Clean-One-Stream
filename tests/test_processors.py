# tests/test_processors.py
# Created by coder-sr | 2026-03-15
"""Unit tests for processor single-audio signatures and manifest.filters behavior.

Covers:
- AudioNormalizer: consumes audio_level_detector results, adds loudnorm to manifest.filters
- WordMuter: reads filler_word_detector, adds volume filters to manifest.filters
- SpikeFixer: reads spike_fixer_detector, adds alimiter to manifest.filters
- SegmentRemover: reads cross_talk_detector, accumulates removal_segments / keep_segments

All tests verify manifest.filters (single list) — NOT host_filters / guest_filters.
No real FFmpeg, pydub, or external APIs required.
"""

import pytest
from unittest.mock import MagicMock

from core.interfaces import EditManifest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_audio(duration_seconds: float = 30.0) -> MagicMock:
    """Lightweight pydub AudioSegment stub."""
    audio = MagicMock()
    audio.duration_seconds = duration_seconds
    return audio


def _manifest() -> EditManifest:
    return EditManifest()


# Canonical audio_level_detector result — reused by AudioNormalizer tests.
_LOUDNORM_PARAMS = {"I": -16.0, "TP": -1.5, "LRA": 11}
_AUDIO_LEVEL_RESULTS = {
    "lufs": -20.0,
    "target_lufs": -16.0,
    "loudnorm_params": _LOUDNORM_PARAMS,
}


# ---------------------------------------------------------------------------
# AudioNormalizer
# ---------------------------------------------------------------------------

class TestAudioNormalizer:
    """AudioNormalizer reads audio_level_detector and writes to manifest.filters."""

    def _make(self, config=None):
        from processors.audio_normalizer import AudioNormalizer
        return AudioNormalizer(config=config or {})

    # ── name ────────────────────────────────────────────────────────────────

    def test_get_name(self):
        assert self._make().get_name() == "AudioNormalizer"

    # ── guard: missing detection_results ────────────────────────────────────

    def test_raises_value_error_when_detection_results_none(self):
        p = self._make()
        with pytest.raises(ValueError, match="detection_results"):
            p.process(_manifest(), _make_audio(), detection_results=None)

    def test_raises_value_error_when_audio_level_detector_absent(self):
        p = self._make()
        with pytest.raises(ValueError, match="audio_level_detector"):
            p.process(_manifest(), _make_audio(), detection_results={})

    def test_raises_value_error_when_lufs_missing(self):
        p = self._make()
        incomplete = {"target_lufs": -16.0, "loudnorm_params": _LOUDNORM_PARAMS}
        with pytest.raises(ValueError):
            p.process(_manifest(), _make_audio(),
                      detection_results={"audio_level_detector": incomplete})

    def test_raises_value_error_when_target_lufs_missing(self):
        p = self._make()
        incomplete = {"lufs": -20.0, "loudnorm_params": _LOUDNORM_PARAMS}
        with pytest.raises(ValueError):
            p.process(_manifest(), _make_audio(),
                      detection_results={"audio_level_detector": incomplete})

    def test_raises_value_error_when_loudnorm_params_missing(self):
        p = self._make()
        incomplete = {"lufs": -20.0, "target_lufs": -16.0}
        with pytest.raises(ValueError):
            p.process(_manifest(), _make_audio(),
                      detection_results={"audio_level_detector": incomplete})

    # ── filter output ────────────────────────────────────────────────────────

    def test_adds_loudnorm_filter_to_manifest_filters(self):
        p = self._make()
        m = _manifest()
        p.process(m, _make_audio(), detection_results={"audio_level_detector": _AUDIO_LEVEL_RESULTS})
        names = [f.filter_name for f in m.filters]
        assert "loudnorm" in names

    def test_loudnorm_filter_params_contain_i_tp_lra(self):
        """loudnorm filter carries the params from audio_level_detector."""
        p = self._make()
        m = _manifest()
        p.process(m, _make_audio(), detection_results={"audio_level_detector": _AUDIO_LEVEL_RESULTS})
        loudnorm_filter = next(f for f in m.filters if f.filter_name == "loudnorm")
        assert "I" in loudnorm_filter.params
        assert "TP" in loudnorm_filter.params
        assert "LRA" in loudnorm_filter.params

    # ── single-stream contract: no host/guest split ──────────────────────────

    def test_uses_single_filters_list_not_host_or_guest(self):
        """Single-stream: AudioNormalizer must write to manifest.filters only."""
        p = self._make()
        m = _manifest()
        p.process(m, _make_audio(), detection_results={"audio_level_detector": _AUDIO_LEVEL_RESULTS})
        assert len(m.filters) >= 1
        assert not hasattr(m, "host_filters")
        assert not hasattr(m, "guest_filters")

    # ── return value ──────────────────────────────────────────────────────────

    def test_returns_same_manifest_instance(self):
        p = self._make()
        m = _manifest()
        result = p.process(m, _make_audio(),
                           detection_results={"audio_level_detector": _AUDIO_LEVEL_RESULTS})
        assert result is m


# ---------------------------------------------------------------------------
# WordMuter
# ---------------------------------------------------------------------------

class TestWordMuter:
    """WordMuter writes volume=0 filters to manifest.filters for each filler word."""

    def _make(self, config=None):
        from processors.word_muter import WordMuter
        return WordMuter(config=config or {})

    def _word_seg(self, start: float, end: float, action: str = "mute") -> dict:
        """Build a realistic filler_word_detector segment dict."""
        return {
            "start_sec": start,
            "end_sec": end,
            "text": "uh",
            "confidence": 0.95,
            "action": action,
            "track": "main",
            "prev_gap_ms": None,
            "next_gap_ms": None,
        }

    # ── name ────────────────────────────────────────────────────────────────

    def test_get_name(self):
        assert self._make().get_name() == "WordMuter"

    # ── flag bookkeeping ─────────────────────────────────────────────────────

    def test_word_mute_applied_flag_set_regardless_of_words_found(self):
        m = _manifest()
        self._make().process(m, _make_audio(), detection_results={"filler_word_detector": []})
        assert m.word_mute_applied is True

    # ── no words detected ────────────────────────────────────────────────────

    def test_no_filters_added_when_filler_words_empty(self):
        m = _manifest()
        self._make().process(m, _make_audio(), detection_results={"filler_word_detector": []})
        assert m.filters == []

    # ── filter output ────────────────────────────────────────────────────────

    def test_adds_volume_filter_for_each_muted_word(self):
        m = _manifest()
        segs = [self._word_seg(1.0, 1.3), self._word_seg(5.0, 5.4)]
        self._make().process(m, _make_audio(),
                             detection_results={"filler_word_detector": segs})
        by_name = [f for f in m.filters if f.filter_name == "volume"]
        assert len(by_name) == 2

    def test_volume_filter_has_zero_volume(self):
        m = _manifest()
        self._make().process(m, _make_audio(),
                             detection_results={"filler_word_detector": [self._word_seg(1.0, 1.3)]})
        vol_filter = next(f for f in m.filters if f.filter_name == "volume")
        assert vol_filter.params.get("volume") == 0

    def test_volume_filter_has_enable_expression(self):
        """FFmpeg enable= expression gates the volume=0 to the word's time range."""
        m = _manifest()
        self._make().process(m, _make_audio(),
                             detection_results={"filler_word_detector": [self._word_seg(2.0, 2.5)]})
        vol_filter = next(f for f in m.filters if f.filter_name == "volume")
        assert "enable" in vol_filter.params
        assert "between" in vol_filter.params["enable"]

    # ── skipped words ──────────────────────────────────────────────────────

    def test_skipped_words_produce_no_volume_filter(self):
        """action='skipped' → confidence below threshold → must NOT add a filter."""
        m = _manifest()
        segs = [self._word_seg(1.0, 1.3, action="skipped")]
        self._make().process(m, _make_audio(), detection_results={"filler_word_detector": segs})
        assert m.filters == []

    def test_mix_of_muted_and_skipped_words(self):
        """Only 'mute' entries produce filters; 'skipped' produce none."""
        m = _manifest()
        segs = [
            self._word_seg(1.0, 1.3, action="mute"),
            self._word_seg(3.0, 3.4, action="skipped"),
        ]
        self._make().process(m, _make_audio(), detection_results={"filler_word_detector": segs})
        assert len(m.filters) == 1

    # ── single-stream contract: no host/guest split ──────────────────────────

    def test_uses_single_filters_list_not_host_or_guest(self):
        m = _manifest()
        segs = [self._word_seg(1.0, 1.3)]
        self._make().process(m, _make_audio(), detection_results={"filler_word_detector": segs})
        assert not hasattr(m, "host_filters")
        assert not hasattr(m, "guest_filters")

    # ── return value ──────────────────────────────────────────────────────────

    def test_returns_same_manifest_instance(self):
        m = _manifest()
        result = self._make().process(m, _make_audio(),
                                      detection_results={"filler_word_detector": []})
        assert result is m


# ---------------------------------------------------------------------------
# SpikeFixer
# ---------------------------------------------------------------------------

class TestSpikeFixer:
    """SpikeFixer adds alimiter filter to manifest.filters when spikes are detected."""

    def _make(self, config=None):
        from processors.spike_fixer import SpikeFixer
        return SpikeFixer(config=config or {"max_peak_db": -3.0})

    # ── name ────────────────────────────────────────────────────────────────

    def test_get_name(self):
        assert self._make().get_name() == "SpikeFixer"

    # ── no spikes ────────────────────────────────────────────────────────────

    def test_no_filter_added_when_no_spikes(self):
        m = _manifest()
        self._make().process(m, _make_audio(), detection_results={"spike_fixer_detector": []})
        assert m.filters == []

    def test_returns_manifest_unmodified_when_no_spikes(self):
        m = _manifest()
        result = self._make().process(m, _make_audio(),
                                      detection_results={"spike_fixer_detector": []})
        assert result is m

    # ── spikes present ───────────────────────────────────────────────────────

    def test_adds_alimiter_filter_when_spikes_detected(self):
        m = _manifest()
        self._make().process(m, _make_audio(),
                             detection_results={"spike_fixer_detector": [(1.0, 1.1), (5.0, 5.05)]})
        names = [f.filter_name for f in m.filters]
        assert "alimiter" in names

    def test_alimiter_limit_param_is_in_valid_range(self):
        """alimiter limit must be in (0.0, 1.0] — FFmpeg rejects values outside range."""
        m = _manifest()
        self._make(config={"max_peak_db": -3.0}).process(
            m, _make_audio(),
            detection_results={"spike_fixer_detector": [(1.0, 1.1)]},
        )
        lim = next(f for f in m.filters if f.filter_name == "alimiter").params["limit"]
        assert 0.0 < lim <= 1.0

    def test_alimiter_has_attack_param(self):
        m = _manifest()
        self._make().process(m, _make_audio(),
                             detection_results={"spike_fixer_detector": [(1.0, 1.1)]})
        al = next(f for f in m.filters if f.filter_name == "alimiter")
        assert "attack" in al.params

    def test_alimiter_has_release_param(self):
        m = _manifest()
        self._make().process(m, _make_audio(),
                             detection_results={"spike_fixer_detector": [(1.0, 1.1)]})
        al = next(f for f in m.filters if f.filter_name == "alimiter")
        assert "release" in al.params

    def test_exactly_one_alimiter_filter_even_for_multiple_spike_regions(self):
        """alimiter is applied globally — one filter regardless of spike count."""
        m = _manifest()
        spikes = [(1.0, 1.1), (3.0, 3.05), (7.0, 7.02)]
        self._make().process(m, _make_audio(),
                             detection_results={"spike_fixer_detector": spikes})
        count = sum(1 for f in m.filters if f.filter_name == "alimiter")
        assert count == 1

    # ── single-stream contract: no host/guest split ──────────────────────────

    def test_uses_single_filters_list_not_host_or_guest(self):
        m = _manifest()
        self._make().process(m, _make_audio(),
                             detection_results={"spike_fixer_detector": [(1.0, 1.1)]})
        assert not hasattr(m, "host_filters")
        assert not hasattr(m, "guest_filters")

    # ── return value ──────────────────────────────────────────────────────────

    def test_returns_same_manifest_instance(self):
        m = _manifest()
        result = self._make().process(
            m, _make_audio(),
            detection_results={"spike_fixer_detector": [(1.0, 1.1)]},
        )
        assert result is m


# ---------------------------------------------------------------------------
# SegmentRemover
# ---------------------------------------------------------------------------

class TestSegmentRemover:
    """SegmentRemover accumulates removal_segments and computes keep_segments."""

    def _make(self, config=None):
        from processors.segment_remover import SegmentRemover
        return SegmentRemover(config=config or {})

    # ── name ────────────────────────────────────────────────────────────────

    def test_get_name(self):
        assert self._make().get_name() == "SegmentRemover"

    # ── flag bookkeeping ─────────────────────────────────────────────────────

    def test_pause_removal_applied_flag_set_even_with_no_pauses(self):
        m = _manifest()
        self._make().process(m, _make_audio(30.0),
                             detection_results={"cross_talk_detector": []})
        assert m.pause_removal_applied is True

    # ── no pauses ──────────────────────────────────────────────────────────

    def test_removal_segments_empty_when_no_pauses(self):
        m = _manifest()
        self._make().process(m, _make_audio(30.0),
                             detection_results={"cross_talk_detector": []})
        assert m.removal_segments == []

    def test_keep_segments_unchanged_when_no_pauses(self):
        m = _manifest()
        self._make().process(m, _make_audio(30.0),
                             detection_results={"cross_talk_detector": []})
        assert m.keep_segments == []

    # ── pauses present ───────────────────────────────────────────────────────

    def test_pause_accumulated_into_removal_segments(self):
        m = _manifest()
        pauses = [(5.0, 8.0), (15.0, 17.0)]
        self._make().process(m, _make_audio(30.0),
                             detection_results={"cross_talk_detector": pauses})
        assert (5.0, 8.0) in m.removal_segments
        assert (15.0, 17.0) in m.removal_segments

    def test_keep_segments_derived_correctly_from_single_pause(self):
        """A single removal [5, 8] in a 30-s video → keep [(0, 5), (8, 30)]."""
        m = _manifest()
        self._make().process(m, _make_audio(30.0),
                             detection_results={"cross_talk_detector": [(5.0, 8.0)]})
        assert m.keep_segments[0] == (0.0, 5.0)
        assert m.keep_segments[1] == (8.0, 30.0)

    def test_keep_segments_derived_correctly_from_multiple_pauses(self):
        """Two removals produce three keep segments."""
        m = _manifest()
        pauses = [(5.0, 8.0), (15.0, 17.0)]
        self._make().process(m, _make_audio(30.0),
                             detection_results={"cross_talk_detector": pauses})
        assert len(m.keep_segments) == 3
        assert m.keep_segments[0] == (0.0, 5.0)
        assert m.keep_segments[1] == (8.0, 15.0)
        assert m.keep_segments[2] == (17.0, 30.0)

    def test_pause_removals_stores_sorted_copy_for_logging(self):
        m = _manifest()
        pauses = [(15.0, 17.0), (5.0, 8.0)]  # unsorted input
        self._make().process(m, _make_audio(30.0),
                             detection_results={"cross_talk_detector": pauses})
        # pause_removals is sorted
        assert m.pause_removals[0][0] < m.pause_removals[1][0]

    # ── does not add audio filters ────────────────────────────────────────

    def test_does_not_add_audio_filters(self):
        """SegmentRemover is solely responsible for timeline cuts — no audio filters."""
        m = _manifest()
        self._make().process(m, _make_audio(30.0),
                             detection_results={"cross_talk_detector": [(5.0, 8.0)]})
        assert m.filters == []

    # ── multiple processor calls (accumulation) ───────────────────────────

    def test_removal_segments_accumulate_across_multiple_process_calls(self):
        """Shared accumulator: two calls → all removals merged in removal_segments."""
        m = _manifest()
        p = self._make()
        audio = _make_audio(60.0)
        p.process(m, audio, detection_results={"cross_talk_detector": [(5.0, 8.0)]})
        p.process(m, audio, detection_results={"cross_talk_detector": [(20.0, 25.0)]})
        assert (5.0, 8.0) in m.removal_segments
        assert (20.0, 25.0) in m.removal_segments

    # ── return value ──────────────────────────────────────────────────────────

    def test_returns_same_manifest_instance(self):
        m = _manifest()
        result = self._make().process(m, _make_audio(30.0),
                                      detection_results={"cross_talk_detector": []})
        assert result is m
