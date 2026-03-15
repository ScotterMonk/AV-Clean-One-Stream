# tests/test_word_removal.py
#
# Tests for the word-processing pipeline:
#   - EditManifest.add_removal() / compute_keep_segments()
#   - SegmentRemover refactor (accumulator pattern)
#   - WordMuter processor (always mutes, never cuts)
#   - FillerWordDetector confidence gating (_filter_by_confidence)
#   - CrossTalkDetector self-healing (detect() accepts detection_results)
#   - FillerWordDetector._find_matches() (pure logic, no API calls)

import types
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_audio(duration: float):
    """Return a minimal object with .duration_seconds."""
    audio = types.SimpleNamespace()
    audio.duration_seconds = duration
    return audio


# ── EditManifest.add_removal / compute_keep_segments ─────────────────────────

class TestEditManifestAccumulator:
    def test_single_removal_middle(self):
        from core.interfaces import EditManifest
        m = EditManifest()
        m.add_removal(2.0, 4.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 2.0), (4.0, 10.0)]
        assert m.keep_segments == result

    def test_removal_at_start(self):
        from core.interfaces import EditManifest
        m = EditManifest()
        m.add_removal(0.0, 3.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(3.0, 10.0)]

    def test_removal_at_end(self):
        from core.interfaces import EditManifest
        m = EditManifest()
        m.add_removal(8.0, 10.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 8.0)]

    def test_multiple_non_overlapping_removals(self):
        from core.interfaces import EditManifest
        m = EditManifest()
        m.add_removal(2.0, 4.0)
        m.add_removal(8.0, 9.0)
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 2.0), (4.0, 8.0), (9.0, 10.0)]

    def test_overlapping_removals_merged(self):
        from core.interfaces import EditManifest
        m = EditManifest()
        m.add_removal(1.0, 5.0)
        m.add_removal(3.0, 7.0)  # overlaps with first
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 1.0), (7.0, 10.0)]

    def test_adjacent_removals_merged(self):
        from core.interfaces import EditManifest
        m = EditManifest()
        m.add_removal(1.0, 3.0)
        m.add_removal(3.0, 5.0)  # butts up against first
        result = m.compute_keep_segments(10.0)
        assert result == [(0.0, 1.0), (5.0, 10.0)]

    def test_empty_removal_segments_leaves_keep_segments_unchanged(self):
        from core.interfaces import EditManifest
        m = EditManifest()
        result = m.compute_keep_segments(10.0)
        # Should not modify keep_segments when nothing queued
        assert result == []
        assert m.keep_segments == []

    def test_second_call_accumulates_both_sets(self):
        """Calling compute_keep_segments twice after adding more removals
        produces the union of all removals."""
        from core.interfaces import EditManifest
        m = EditManifest()

        # First processor adds a pause at 2–4s
        m.add_removal(2.0, 4.0)
        m.compute_keep_segments(10.0)
        assert m.keep_segments == [(0.0, 2.0), (4.0, 10.0)]

        # Second processor adds a word at 7–7.5s
        m.add_removal(7.0, 7.5)
        m.compute_keep_segments(10.0)
        assert m.keep_segments == [(0.0, 2.0), (4.0, 7.0), (7.5, 10.0)]


# ── SegmentRemover (refactored) ───────────────────────────────────────────────

class TestSegmentRemoverAccumulator:
    def test_sets_keep_segments_via_accumulator(self):
        from core.interfaces import EditManifest
        from processors.segment_remover import SegmentRemover

        processor = SegmentRemover({})
        manifest = processor.process(
            EditManifest(),
            _mock_audio(10.0),
            _mock_audio(10.0),
            {"cross_talk_detector": [(2.0, 4.0), (8.0, 9.0)]},
        )
        assert manifest.keep_segments == [(0.0, 2.0), (4.0, 8.0), (9.0, 10.0)]

    def test_no_pauses_leaves_keep_segments_empty(self):
        from core.interfaces import EditManifest
        from processors.segment_remover import SegmentRemover

        processor = SegmentRemover({})
        manifest = processor.process(
            EditManifest(),
            _mock_audio(10.0),
            _mock_audio(10.0),
            {"cross_talk_detector": []},
        )
        assert manifest.keep_segments == []  # empty = keep everything

    def test_removal_segments_populated(self):
        from core.interfaces import EditManifest
        from processors.segment_remover import SegmentRemover

        processor = SegmentRemover({})
        manifest = processor.process(
            EditManifest(),
            _mock_audio(10.0),
            _mock_audio(10.0),
            {"cross_talk_detector": [(3.0, 5.0)]},
        )
        assert (3.0, 5.0) in manifest.removal_segments


# ── WordMuter ─────────────────────────────────────────────────────────────────

class TestWordMuter:
    def test_removes_detected_words(self):
        """Dict-format words produce volume=0 filters; keep_segments NOT modified."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [
                {"track": "host", "text": "uh", "start_sec": 1.0, "end_sec": 1.5, "confidence": 1.0},
                {"track": "guest", "text": "um", "start_sec": 6.0, "end_sec": 6.4, "confidence": 0.95},
            ]},
        )
        assert manifest.keep_segments == []  # WordMuter never touches keep_segments
        assert len(manifest.host_filters) == 1
        assert manifest.host_filters[0].filter_name == "volume"
        assert manifest.host_filters[0].params == {"volume": 0, "enable": "between(t,1.000,1.500)"}
        assert len(manifest.guest_filters) == 1
        assert manifest.guest_filters[0].params == {"volume": 0, "enable": "between(t,6.000,6.400)"}

    def test_no_detections_leaves_manifest_unchanged(self):
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": []},
        )
        assert manifest.keep_segments == []

    def test_word_mute_applied_flag_set(self):
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": []},
        )
        assert manifest.word_mute_applied is True

    def test_word_mutes_bookkeeping(self):
        """word_mutes contains muted time ranges."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [
                {"track": "host", "text": "uh", "start_sec": 2.0, "end_sec": 2.3, "confidence": 1.0},
            ]},
        )
        assert manifest.word_mutes == [(2.0, 2.3)]

    def test_word_mute_details_bookkeeping(self):
        # Use above-threshold confidences (host=1.0 required, guest=0.92 required).
        # Filtering is now done in FillerWordDetector, but we unit-test WordMuter
        # in isolation so we supply pre-filtered (passing) results.
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [
                {"track": "host", "text": "uh", "start_sec": 2.0, "end_sec": 2.3, "confidence": 1.0},
                {"track": "guest", "text": "you know", "start_sec": 4.0, "end_sec": 4.4, "confidence": 0.95},
            ]},
        )
        assert manifest.word_mutes == [(2.0, 2.3), (4.0, 4.4)]
        assert all(d["action"] == "mute" for d in manifest.word_mute_details)
        assert "cut" not in [d["action"] for d in manifest.word_mute_details]

    def test_word_on_host_mutes(self):
        """No _AudioWithDb needed — just assert host volume=0 filter added."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [
                {"track": "host", "text": "um", "start_sec": 2.0, "end_sec": 2.3, "confidence": 1.0},
            ]},
        )
        assert [f.filter_name for f in manifest.host_filters] == ["volume"]
        assert manifest.host_filters[0].params == {"volume": 0, "enable": "between(t,2.000,2.300)"}
        assert manifest.word_mutes == [(2.0, 2.3)]

    def test_word_on_guest_mutes(self):
        """Guest word produces mute filter (NOT a cut); keep_segments unchanged."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [
                {"track": "guest", "text": "um", "start_sec": 2.0, "end_sec": 2.3, "confidence": 0.95},
            ]},
        )
        assert manifest.keep_segments == []  # no cut
        assert [f.filter_name for f in manifest.guest_filters] == ["volume"]
        assert manifest.word_mutes == [(2.0, 2.3)]

    def test_get_name(self):
        from processors.word_muter import WordMuter
        assert WordMuter({}).get_name() == "WordMuter"


# ── Combined: SegmentRemover + WordMuter ──────────────────────────────────────

class TestCombinedAccumulation:
    def test_wordmuter_does_not_modify_keep_segments(self):
        """WordMuter must not touch keep_segments — only SegmentRemover owns cuts."""
        from core.interfaces import EditManifest
        from processors.segment_remover import SegmentRemover
        from processors.word_muter import WordMuter
        host = _mock_audio(20.0)
        guest = _mock_audio(20.0)
        manifest = EditManifest()
        manifest = SegmentRemover({}).process(
            manifest, host, guest, {"cross_talk_detector": [(5.0, 7.0)]}
        )
        manifest = WordMuter({}).process(
            manifest, host, guest,
            {"filler_word_detector": [
                {"track": "host", "text": "uh", "start_sec": 12.0, "end_sec": 12.5, "confidence": 1.0},
            ]},
        )
        # keep_segments only reflects the pause cut; WordMuter does not modify it
        assert manifest.keep_segments == [(0.0, 5.0), (7.0, 20.0)]
        # But the mute filter was added for the filler word
        assert len(manifest.host_filters) == 1


# ── FillerWordDetector confidence gating ─────────────────────────────────────

class TestFillerWordDetectorConfidenceGating:
    """Verify confidence gating is applied by FillerWordDetector._filter_by_confidence()."""

    def _detector(self):
        from detectors.filler_word_detector import FillerWordDetector
        return FillerWordDetector({})

    def _match(self, track, confidence, start=1.0, end=1.3):
        return {"track": track, "text": "uh", "start_sec": start, "end_sec": end, "confidence": confidence}

    def test_host_word_above_threshold_muted(self):
        # config.py: confidence_required_host = 1.0
        det = self._detector()
        result = det._filter_by_confidence([self._match("host", 1.0)], "host")
        assert len(result) == 1
        assert result[0]["action"] == "mute"

    def test_host_word_below_threshold_skipped(self):
        # config: confidence_required_host=1.08, bonus_per_word=0.10
        # effective_required = 1.08 - (1 * 0.10) = 0.98; 0.97 < 0.98 → skipped
        det = self._detector()
        result = det._filter_by_confidence([self._match("host", 0.97)], "host")
        assert len(result) == 1
        assert result[0]["action"] == "skipped"

    def test_guest_word_at_threshold_muted(self):
        # config.py: confidence_required_guest = 0.92; 0.92 >= 0.92 → muted
        det = self._detector()
        result = det._filter_by_confidence([self._match("guest", 0.92)], "guest")
        assert len(result) == 1
        assert result[0]["action"] == "mute"

    def test_guest_word_below_threshold_skipped(self):
        # config: confidence_required_guest=0.95, bonus_per_word=0.10
        # effective_required = 0.95 - (1 * 0.10) = 0.85; 0.84 < 0.85 → skipped
        det = self._detector()
        result = det._filter_by_confidence([self._match("guest", 0.84)], "guest")
        assert len(result) == 1
        assert result[0]["action"] == "skipped"

    def test_unknown_track_passes_through_as_mute(self):
        det = self._detector()
        match = self._match("unknown", 0.0)
        result = det._filter_by_confidence([match], "unknown")
        assert len(result) == 1
        assert result[0]["action"] == "mute"

    def test_mixed_confidences_annotated(self):
        det = self._detector()
        matches = [self._match("guest", 0.95, 1.0, 1.3), self._match("guest", 0.80, 2.0, 2.3)]
        result = det._filter_by_confidence(matches, "guest")
        assert len(result) == 2
        muted = [r for r in result if r["action"] == "mute"]
        skipped = [r for r in result if r["action"] == "skipped"]
        assert len(muted) == 1
        assert muted[0]["start_sec"] == 1.0
        assert len(skipped) == 1
        assert skipped[0]["start_sec"] == 2.0


# ── WordMuter with skipped words ─────────────────────────────────────────────

class TestWordMuterSkippedWords:
    """Verify that skipped words pass through WordMuter without mute filters."""

    def test_skipped_word_no_filter(self):
        """A word with action='skipped' must NOT produce a volume=0 filter."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [
                {"track": "host", "text": "uh", "start_sec": 1.0, "end_sec": 1.5,
                 "confidence": 0.80, "action": "skipped"},
            ]},
        )
        assert manifest.host_filters == []  # no mute applied
        assert manifest.word_mutes == []    # no muted time ranges

    def test_skipped_word_in_details(self):
        """Skipped words still appear in word_mute_details for logging."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [
                {"track": "guest", "text": "um", "start_sec": 2.0, "end_sec": 2.4,
                 "confidence": 0.80, "action": "skipped"},
            ]},
        )
        assert len(manifest.word_mute_details) == 1
        assert manifest.word_mute_details[0]["action"] == "skipped"

    def test_mixed_muted_and_skipped(self):
        """Muted words get filters; skipped words appear in details only."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [
                {"track": "host", "text": "uh", "start_sec": 1.0, "end_sec": 1.5,
                 "confidence": 1.0, "action": "mute"},
                {"track": "guest", "text": "um", "start_sec": 3.0, "end_sec": 3.3,
                 "confidence": 0.80, "action": "skipped"},
            ]},
        )
        # Only the muted word gets a filter
        assert len(manifest.host_filters) == 1
        assert manifest.guest_filters == []
        # Both appear in details
        assert len(manifest.word_mute_details) == 2
        actions = {d["action"] for d in manifest.word_mute_details}
        assert actions == {"mute", "skipped"}
        # Only the muted word appears in word_mutes
        assert manifest.word_mutes == [(1.0, 1.5)]


# ── Pipeline filler word log helpers ─────────────────────────────────────────

class TestFillerWordLogHelpers:
    """Verify the shared formatting function produces expected output."""

    def test_log_filler_word_line_muted(self):
        from core.pipeline import _log_filler_word_line
        detail = {
            "track": "host", "text": "uh", "start_sec": 65.0, "end_sec": 65.5,
            "confidence": 0.9500, "action": "mute",
        }
        line = _log_filler_word_line(detail)
        assert line == '00:01:05 "uh" (confidence: 0.9500) muted'

    def test_log_filler_word_line_skipped(self):
        from core.pipeline import _log_filler_word_line
        detail = {
            "track": "guest", "text": "you know", "start_sec": 3661.0, "end_sec": 3662.0,
            "confidence": 0.4200, "action": "skipped",
        }
        line = _log_filler_word_line(detail)
        assert line == '01:01:01 "you know" (confidence: 0.4200) skipped'

    def test_log_filler_word_line_defaults_action_to_mute(self):
        from core.pipeline import _log_filler_word_line
        detail = {"track": "host", "text": "um", "start_sec": 0.0, "end_sec": 0.3}
        line = _log_filler_word_line(detail)
        assert line.endswith(" muted")


# ── CrossTalkDetector self-healing signature coverage ────────────────────────

class TestCrossTalkDetectorSelfHealing:
    """CrossTalkDetector.detect() must accept detection_results with filler mutes."""

    def test_detect_accepts_no_detection_results(self):
        """Legacy 2-arg signature still works (detection_results defaults to None)."""
        from detectors.cross_talk_detector import CrossTalkDetector
        det = CrossTalkDetector({"max_pause_duration": 1.0, "new_pause_duration": 0.5, "silence_threshold_db": -45})
        # Just confirm it doesn't raise with 2 args
        try:
            det.detect(_mock_audio(1.0), _mock_audio(1.0))
        except AttributeError:
            pass  # _mock_audio doesn't support pydub ops; that's OK — no crash from signature

    def test_detect_accepts_detection_results_kwarg(self):
        """detect() accepts detection_results as 3rd positional or keyword arg."""
        from detectors.cross_talk_detector import CrossTalkDetector
        import inspect
        det = CrossTalkDetector({})
        sig = inspect.signature(det.detect)
        params = list(sig.parameters.keys())
        assert "detection_results" in params

    def test_detect_detection_results_defaults_to_none(self):
        """detection_results parameter must be optional (has a default)."""
        from detectors.cross_talk_detector import CrossTalkDetector
        import inspect
        det = CrossTalkDetector({})
        sig = inspect.signature(det.detect)
        param = sig.parameters["detection_results"]
        assert param.default is None


# ── FillerWordDetector._find_matches (pure logic, no API) ────────────────────

class TestFillerWordDetectorFindMatches:
    def _detector(self):
        from detectors.filler_word_detector import FillerWordDetector
        return FillerWordDetector({})

    def _word(self, text, start_ms, end_ms):
        return {"text": text, "start": start_ms, "end": end_ms, "confidence": 0.9}

    def test_single_word_match(self):
        det = self._detector()
        words = [
            self._word("Hi,",   160,  480),
            self._word("uh,",   640,  920),
            self._word("I'm",   920, 1120),
            self._word("Bob.",  1120, 1520),
        ]
        matches = det._find_matches(words, ["uh"])
        assert matches == [(0.64, 0.92)]

    def test_multi_word_phrase_match(self):
        det = self._detector()
        words = [
            self._word("you",   1000, 1200),
            self._word("know",  1200, 1500),
            self._word("it",    1600, 1800),
        ]
        matches = det._find_matches(words, ["you know"])
        assert matches == [(1.0, 1.5)]

    def test_no_match_returns_empty(self):
        det = self._detector()
        words = [
            self._word("Hello",  0, 500),
            self._word("world.", 600, 1000),
        ]
        matches = det._find_matches(words, ["uh", "uhm"])
        assert matches == []

    def test_punctuation_stripped_from_word(self):
        det = self._detector()
        words = [self._word("uhm,", 200, 600)]
        matches = det._find_matches(words, ["uhm"])
        assert matches == [(0.2, 0.6)]

    def test_multiple_occurrences_all_returned(self):
        det = self._detector()
        words = [
            self._word("uh,",   0,    400),
            self._word("well",  500,  900),
            self._word("uh,",   1000, 1300),
        ]
        matches = det._find_matches(words, ["uh"])
        assert len(matches) == 2
        assert (0.0, 0.4) in matches
        assert (1.0, 1.3) in matches

    def test_detailed_matches_include_track_and_phrase(self):
        det = self._detector()
        words = [
            self._word("you", 1000, 1200),
            self._word("know", 1200, 1500),
        ]
        matches = det._find_matches_detailed(words, ["you know"], "guest")
        # Both gap fields are None because the phrase spans the entire word list
        # (no preceding or following word exists).
        assert matches == [
            {
                "track": "guest",
                "text": "you know",
                "start_sec": 1.0,
                "end_sec": 1.5,
                "confidence": 0.9,
                "prev_gap_ms": None,
                "next_gap_ms": None,
            }
        ]

    def test_find_matches_detailed_includes_gap_data(self):
        """Gap to neighbouring words is computed and stored in each match."""
        det = self._detector()
        words = [
            self._word("Hi,",   160,  480),   # preceding word
            self._word("uh,",   640,  920),   # filler: prev_gap=640-480=160ms
            self._word("I'm",   920, 1120),   # following: next_gap=920-920=0ms
            self._word("Bob.",  1120, 1520),
        ]
        matches = det._find_matches_detailed(words, ["uh"], "host")
        assert len(matches) == 1
        m = matches[0]
        assert m["prev_gap_ms"] == 160   # 640 - 480
        assert m["next_gap_ms"] == 0     # 920 - 920

    def test_find_matches_detailed_gap_none_at_boundaries(self):
        """prev_gap_ms is None when filler is the first word; next_gap_ms is None when last."""
        det = self._detector()
        # Filler is first word — no predecessor.
        words_first = [
            self._word("uh,", 0, 300),
            self._word("hi",  400, 700),
        ]
        m_first = det._find_matches_detailed(words_first, ["uh"], "host")[0]
        assert m_first["prev_gap_ms"] is None
        assert m_first["next_gap_ms"] == 100  # 400 - 300

        # Filler is last word — no successor.
        words_last = [
            self._word("hi",  0, 300),
            self._word("uh.", 400, 700),
        ]
        m_last = det._find_matches_detailed(words_last, ["uh"], "host")[0]
        assert m_last["prev_gap_ms"] == 100   # 400 - 300
        assert m_last["next_gap_ms"] is None


# ── WordMuter pause-aware mute inset ─────────────────────────────────────────

class TestWordMuterSlurInset:
    """Pause-aware mute inset: mute window shrinks inward on slurred edges."""

    def _segment(self, start, end, prev_gap=None, next_gap=None, track="host"):
        return {
            "track": track, "text": "uh",
            "start_sec": start, "end_sec": end,
            "confidence": 1.0, "action": "mute",
            "prev_gap_ms": prev_gap, "next_gap_ms": next_gap,
        }

    def test_no_inset_without_gap_data(self):
        """Segments with no gap keys use the exact detected timestamps (legacy path)."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [
                {"track": "host", "text": "uh", "start_sec": 2.0, "end_sec": 2.3,
                 "confidence": 1.0, "action": "mute"},
            ]},
        )
        assert manifest.host_filters[0].params["enable"] == "between(t,2.000,2.300)"

    def test_end_inset_when_next_gap_small(self):
        """next_gap_ms below threshold → end shrinks inward by inset_ms."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        from config import WORDS_TO_REMOVE
        inset_s = WORDS_TO_REMOVE.get("filler_mute_inset_ms", 30) / 1000.0
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [self._segment(2.0, 2.3, prev_gap=200, next_gap=0)]},
        )
        expected = f"between(t,2.000,{2.3 - inset_s:.3f})"
        assert manifest.host_filters[0].params["enable"] == expected

    def test_start_inset_when_prev_gap_small(self):
        """prev_gap_ms below threshold → start shrinks inward by inset_ms."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        from config import WORDS_TO_REMOVE
        inset_s = WORDS_TO_REMOVE.get("filler_mute_inset_ms", 30) / 1000.0
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [self._segment(2.0, 2.5, prev_gap=10, next_gap=200)]},
        )
        expected = f"between(t,{2.0 + inset_s:.3f},2.500)"
        assert manifest.host_filters[0].params["enable"] == expected

    def test_no_inset_when_gaps_large(self):
        """Gaps larger than threshold → no inset; timestamps unchanged."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [self._segment(2.0, 2.3, prev_gap=500, next_gap=500)]},
        )
        assert manifest.host_filters[0].params["enable"] == "between(t,2.000,2.300)"

    def test_both_sides_inset_when_both_gaps_small(self):
        """Both neighbours slurred → both start and end are inset."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        from config import WORDS_TO_REMOVE
        inset_s = WORDS_TO_REMOVE.get("filler_mute_inset_ms", 30) / 1000.0
        processor = WordMuter({})
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [self._segment(2.0, 2.5, prev_gap=10, next_gap=5)]},
        )
        expected = f"between(t,{2.0 + inset_s:.3f},{2.5 - inset_s:.3f})"
        assert manifest.host_filters[0].params["enable"] == expected

    def test_collapsed_window_reverts_to_full(self):
        """When inset collapses the window (start >= end), full original range is used."""
        from core.interfaces import EditManifest
        from processors.word_muter import WordMuter
        processor = WordMuter({})
        # Word is only 10ms long; two 30ms insets would invert the window.
        manifest = processor.process(
            EditManifest(), _mock_audio(10.0), _mock_audio(10.0),
            {"filler_word_detector": [self._segment(2.000, 2.010, prev_gap=5, next_gap=5)]},
        )
        assert manifest.host_filters[0].params["enable"] == "between(t,2.000,2.010)"
