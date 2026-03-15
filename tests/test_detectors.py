# tests/test_detectors.py
# Created by coder-sr | 2026-03-15
"""Unit tests for detector single-audio signatures.

Covers:
- AudioLevelDetector: returns lufs, target_lufs, loudnorm_params only
- SpikeFixerDetector: fallback paths, single-audio detect() signature
- FillerWordDetector: graceful degradation, single-audio detect() signature
- CrossTalkDetector: pause detection, self-healing with filler results

All tests are isolated: no real FFmpeg, pydub I/O, or external API calls.
"""

import inspect

import numpy as np
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_audio_mock(duration_seconds: float = 30.0) -> MagicMock:
    """Lightweight pydub AudioSegment stub."""
    audio = MagicMock()
    audio.duration_seconds = duration_seconds
    audio.frame_rate = 44100
    audio.channels = 1
    audio.sample_width = 2
    audio.__len__ = lambda self: int(duration_seconds * 1000)
    # Slicing returns another mock with a usable dBFS for _verify_silence
    sliced = MagicMock()
    sliced.dBFS = -60.0         # well below silence_threshold_db ~ -45
    sliced.__len__ = lambda self: 100
    audio.__getitem__ = lambda self, key: sliced
    return audio


# ---------------------------------------------------------------------------
# AudioLevelDetector
# ---------------------------------------------------------------------------

class TestAudioLevelDetector:
    """AudioLevelDetector returns a plain dict with exactly three keys."""

    def _make(self, config=None):
        from detectors.audio_level_detector import AudioLevelDetector
        return AudioLevelDetector(config=config or {})

    # ── name ────────────────────────────────────────────────────────────────

    def test_get_name_returns_audio_level_detector(self):
        assert self._make().get_name() == "audio_level_detector"

    # ── required result keys ────────────────────────────────────────────────

    @patch("detectors.audio_level_detector.normalization_params_standard_lufs",
           return_value={"I": -16.0, "TP": -1.5, "LRA": 11})
    @patch("detectors.audio_level_detector.calculate_lufs", return_value=-18.5)
    def test_returns_lufs_key(self, _mock_lufs, _mock_params):
        result = self._make().detect(_make_audio_mock())
        assert "lufs" in result

    @patch("detectors.audio_level_detector.normalization_params_standard_lufs",
           return_value={"I": -16.0, "TP": -1.5, "LRA": 11})
    @patch("detectors.audio_level_detector.calculate_lufs", return_value=-18.5)
    def test_returns_target_lufs_key(self, _mock_lufs, _mock_params):
        result = self._make().detect(_make_audio_mock())
        assert "target_lufs" in result

    @patch("detectors.audio_level_detector.normalization_params_standard_lufs",
           return_value={"I": -16.0, "TP": -1.5, "LRA": 11})
    @patch("detectors.audio_level_detector.calculate_lufs", return_value=-18.5)
    def test_returns_loudnorm_params_key(self, _mock_lufs, _mock_params):
        result = self._make().detect(_make_audio_mock())
        assert "loudnorm_params" in result

    # ── single-stream: no dual-track keys ──────────────────────────────────

    @patch("detectors.audio_level_detector.normalization_params_standard_lufs",
           return_value={})
    @patch("detectors.audio_level_detector.calculate_lufs", return_value=-18.5)
    def test_no_host_or_guest_keys_in_result(self, _mock_lufs, _mock_params):
        """Single-stream: host/guest split must not appear in result."""
        result = self._make().detect(_make_audio_mock())
        for key in result:
            assert "host" not in key.lower()
            assert "guest" not in key.lower()

    # ── value types ─────────────────────────────────────────────────────────

    @patch("detectors.audio_level_detector.normalization_params_standard_lufs",
           return_value={"I": -16.0})
    @patch("detectors.audio_level_detector.calculate_lufs", return_value=-18.5)
    def test_lufs_is_float(self, _mock_lufs, _mock_params):
        result = self._make().detect(_make_audio_mock())
        assert isinstance(result["lufs"], float)

    @patch("detectors.audio_level_detector.normalization_params_standard_lufs",
           return_value={"I": -16.0})
    @patch("detectors.audio_level_detector.calculate_lufs", return_value=-18.5)
    def test_target_lufs_is_float(self, _mock_lufs, _mock_params):
        result = self._make().detect(_make_audio_mock())
        assert isinstance(result["target_lufs"], float)

    # ── config-driven target_lufs ────────────────────────────────────────────

    @patch("detectors.audio_level_detector.normalization_params_standard_lufs",
           return_value={})
    @patch("detectors.audio_level_detector.calculate_lufs", return_value=-18.5)
    def test_default_target_lufs_is_minus_16(self, _mock_lufs, _mock_params):
        """Empty config → target_lufs defaults to -16.0."""
        result = self._make(config={}).detect(_make_audio_mock())
        assert result["target_lufs"] == -16.0

    @patch("detectors.audio_level_detector.normalization_params_standard_lufs",
           return_value={})
    @patch("detectors.audio_level_detector.calculate_lufs", return_value=-18.5)
    def test_custom_target_lufs_from_normalization_config(self, _mock_lufs, _mock_params):
        config = {"normalization": {"target_lufs": -14.0}}
        result = self._make(config=config).detect(_make_audio_mock())
        assert result["target_lufs"] == -14.0

    # ── loudnorm_params passthrough ──────────────────────────────────────────

    @patch(
        "detectors.audio_level_detector.normalization_params_standard_lufs",
        return_value={"I": -16.0, "TP": -1.5, "LRA": 11},
    )
    @patch("detectors.audio_level_detector.calculate_lufs", return_value=-18.5)
    def test_loudnorm_params_are_calculator_result(self, _mock_lufs, mock_params):
        """loudnorm_params value is the exact dict from normalization_params_standard_lufs."""
        audio = _make_audio_mock()
        result = self._make().detect(audio)
        assert result["loudnorm_params"] == {"I": -16.0, "TP": -1.5, "LRA": 11}


# ---------------------------------------------------------------------------
# SpikeFixerDetector
# ---------------------------------------------------------------------------

class TestSpikeFixerDetector:
    """SpikeFixerDetector — single-audio detect() with pre-normalization fallback."""

    def _make(self, config=None):
        from detectors.spike_fixer_detector import SpikeFixerDetector
        return SpikeFixerDetector(config=config or {})

    # ── name ────────────────────────────────────────────────────────────────

    def test_get_name_is_non_empty_string(self):
        name = self._make().get_name()
        assert isinstance(name, str) and len(name) > 0

    # ── detect() signature ──────────────────────────────────────────────────

    def test_detect_signature_has_audio_and_optional_detection_results(self):
        from detectors.spike_fixer_detector import SpikeFixerDetector
        sig = inspect.signature(SpikeFixerDetector.detect)
        params = list(sig.parameters.keys())
        assert "audio" in params
        assert "detection_results" in params

    # ── fallback: no audio_level results ───────────────────────────────────

    def test_falls_back_to_pre_normalization_when_no_audio_level_in_results(self):
        d = self._make(config={"spike_threshold_db": -6})
        audio = _make_audio_mock()
        with patch.object(d, "_detect_pre_normalization", return_value=[]) as mock_fb:
            result = d.detect(audio, detection_results={})
        mock_fb.assert_called_once_with(audio)
        assert result == []

    def test_falls_back_when_detection_results_is_none(self):
        d = self._make()
        audio = _make_audio_mock()
        with patch.object(d, "_detect_pre_normalization", return_value=[]) as mock_fb:
            result = d.detect(audio, detection_results=None)
        mock_fb.assert_called_once_with(audio)

    # ── fallback: video path missing ────────────────────────────────────────

    def test_falls_back_when_video_path_missing_in_detection_results(self):
        d = self._make()
        audio = _make_audio_mock()
        # audio_level_detector present, but no video_path key
        dr = {"audio_level_detector": {"lufs": -18.0, "target_lufs": -16.0, "loudnorm_params": {}}}
        with patch.object(d, "_detect_pre_normalization", return_value=[]) as mock_fb:
            result = d.detect(audio, detection_results=dr)
        mock_fb.assert_called_once_with(audio)

    # ── return type ───────────────────────────────────────────────────────

    def test_detect_always_returns_list(self):
        d = self._make()
        audio = _make_audio_mock()
        with patch.object(d, "_detect_pre_normalization", return_value=[]):
            result = d.detect(audio, detection_results={})
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# FillerWordDetector
# ---------------------------------------------------------------------------

class TestFillerWordDetector:
    """FillerWordDetector — single-audio signature and graceful degradation."""

    def _make(self, config=None):
        from detectors.filler_word_detector import FillerWordDetector
        return FillerWordDetector(config=config or {})

    # ── name ────────────────────────────────────────────────────────────────

    def test_get_name_is_non_empty_string(self):
        name = self._make().get_name()
        assert isinstance(name, str) and len(name) > 0

    # ── detect() signature ──────────────────────────────────────────────────

    def test_detect_signature_has_audio_and_detection_results(self):
        from detectors.filler_word_detector import FillerWordDetector
        sig = inspect.signature(FillerWordDetector.detect)
        params = list(sig.parameters.keys())
        assert "audio" in params
        assert "detection_results" in params

    # ── graceful degradation ────────────────────────────────────────────────

    def test_returns_empty_list_when_api_key_missing(self, monkeypatch):
        """Missing AAI_SETTINGS_API_KEY → returns [] without raising."""
        monkeypatch.delenv("AAI_SETTINGS_API_KEY", raising=False)
        monkeypatch.delenv("AAI_SETTINGS_BASE_URL", raising=False)
        result = self._make().detect(_make_audio_mock(), detection_results={})
        assert result == []

    def test_returns_empty_list_when_base_url_missing(self, monkeypatch):
        monkeypatch.setenv("AAI_SETTINGS_API_KEY", "test-key")
        monkeypatch.delenv("AAI_SETTINGS_BASE_URL", raising=False)
        result = self._make().detect(_make_audio_mock(), detection_results={})
        assert result == []

    def test_returns_empty_list_when_both_keys_missing(self, monkeypatch):
        monkeypatch.delenv("AAI_SETTINGS_API_KEY", raising=False)
        monkeypatch.delenv("AAI_SETTINGS_BASE_URL", raising=False)
        audio = _make_audio_mock()
        result = self._make().detect(audio)
        assert isinstance(result, list)

    def test_detect_does_not_raise_with_empty_env(self, monkeypatch):
        """detect() must never raise — it degrades gracefully."""
        monkeypatch.delenv("AAI_SETTINGS_API_KEY", raising=False)
        monkeypatch.delenv("AAI_SETTINGS_BASE_URL", raising=False)
        # Should not raise even when called with no detection_results
        self._make().detect(_make_audio_mock())


# ---------------------------------------------------------------------------
# CrossTalkDetector
# ---------------------------------------------------------------------------

class TestCrossTalkDetector:
    """CrossTalkDetector — single-audio pause detection and self-healing."""

    _DEFAULT_CONFIG = {
        "silence_threshold_db": -45,
        "max_pause_duration": 2.5,
        "new_pause_duration": 0.5,
        "silence_window_ms": 100,
    }

    def _make(self, config=None):
        from detectors.cross_talk_detector import CrossTalkDetector
        return CrossTalkDetector(config=config if config is not None else dict(self._DEFAULT_CONFIG))

    def _silent_envelope(self, n: int = 50) -> np.ndarray:
        """All frames below threshold — simulates a fully-silent track."""
        return np.full(n, -60.0)

    def _loud_envelope(self, n: int = 50) -> np.ndarray:
        """All frames above threshold — simulates no silence at all."""
        return np.full(n, -20.0)

    # ── name ────────────────────────────────────────────────────────────────

    def test_get_name_returns_cross_talk_detector(self):
        assert self._make().get_name() == "cross_talk_detector"

    # ── detect() signature ──────────────────────────────────────────────────

    def test_detect_signature_has_audio_and_optional_detection_results(self):
        from detectors.cross_talk_detector import CrossTalkDetector
        sig = inspect.signature(CrossTalkDetector.detect)
        params = list(sig.parameters.keys())
        assert "audio" in params
        assert "detection_results" in params

    # ── return type ───────────────────────────────────────────────────────

    def test_returns_list_when_no_silence_detected(self):
        audio = _make_audio_mock(duration_seconds=5.0)
        with patch(
            "detectors.cross_talk_detector.calculate_db_envelope",
            return_value=self._loud_envelope(),
        ):
            result = self._make().detect(audio, detection_results={})
        assert isinstance(result, list)
        # Loud-only track → no pauses found
        assert result == []

    def test_detect_returns_list_of_tuples(self):
        """Each detected pause is a (float, float) tuple."""
        audio = _make_audio_mock(duration_seconds=30.0)
        # 20 consecutive silent windows @ 100 ms each = 2 s > max_pause_duration 2.5 s? No.
        # Use 30 windows @ 100 ms = 3 s > 2.5 s → one detected pause
        n = 300  # 300 * 100 ms window = 30 s
        envelope = np.full(n, -60.0)   # all silent
        with patch(
            "detectors.cross_talk_detector.calculate_db_envelope",
            return_value=envelope,
        ):
            result = self._make().detect(audio, detection_results={})
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], float)
            assert isinstance(item[1], float)

    # ── self-healing ─────────────────────────────────────────────────────────

    def test_self_healing_calls_audio_apply_mutes_when_filler_results_present(self):
        """When filler_word_detector results exist, audio_apply_mutes is invoked."""
        audio = _make_audio_mock(duration_seconds=10.0)
        filler_results = [
            {"start_sec": 1.0, "end_sec": 1.5},
            {"start_sec": 3.0, "end_sec": 3.3},
        ]
        detection_results = {"filler_word_detector": filler_results}

        # audio_apply_mutes returns a new mock (the locally-modified copy)
        mutated_copy = _make_audio_mock(duration_seconds=10.0)

        with patch("utils.audio_helpers.audio_apply_mutes", return_value=mutated_copy) as mock_mute:
            with patch(
                "detectors.cross_talk_detector.calculate_db_envelope",
                return_value=self._loud_envelope(100),
            ):
                self._make().detect(audio, detection_results=detection_results)

        mock_mute.assert_called_once()
        # First arg is the shared audio object passed by the pipeline
        call_first_arg = mock_mute.call_args[0][0]
        assert call_first_arg is audio

    def test_self_healing_does_not_call_audio_apply_mutes_when_no_filler_results(self):
        """Without filler results, audio_apply_mutes must not be called."""
        audio = _make_audio_mock(duration_seconds=5.0)
        with patch("utils.audio_helpers.audio_apply_mutes") as mock_mute:
            with patch(
                "detectors.cross_talk_detector.calculate_db_envelope",
                return_value=self._loud_envelope(),
            ):
                self._make().detect(audio, detection_results={})
        mock_mute.assert_not_called()

    def test_self_healing_does_not_call_audio_apply_mutes_for_empty_filler_list(self):
        audio = _make_audio_mock(duration_seconds=5.0)
        detection_results = {"filler_word_detector": []}
        with patch("utils.audio_helpers.audio_apply_mutes") as mock_mute:
            with patch(
                "detectors.cross_talk_detector.calculate_db_envelope",
                return_value=self._loud_envelope(),
            ):
                self._make().detect(audio, detection_results=detection_results)
        mock_mute.assert_not_called()
