# tests/test_pipeline.py
# Created by coder-sr | 2026-03-15
"""Integration-level tests for ProcessingPipeline.execute() single-stream contract.

All external I/O (audio extraction, video rendering) is mocked.
No real media files, FFmpeg, or external services required.

What is tested:
- Audio is extracted exactly once from the video path.
- The same audio object is passed to every detector and processor.
- Each detector result is stored in detection_results under its name.
- Each processor receives (manifest, audio, detection_results).
- The video_path is seeded into detection_results before detectors run.
- execute() returns the output path when render=True.
- execute() returns None when render=False.
"""

import pytest
from unittest.mock import patch, MagicMock

from core.pipeline import ProcessingPipeline
from core.interfaces import EditManifest


# ---------------------------------------------------------------------------
# Minimal real-class stubs (avoids MagicMock signature-inspection conflicts)
# ---------------------------------------------------------------------------

class _MockDetector:
    """Minimal detector stub — real detect() signature so inspect works correctly."""

    def __init__(self, name: str, result=None):
        self._name = name
        self._result = result if result is not None else {name: "detected"}
        # Track calls for assertions
        self.calls: list = []

    def get_name(self) -> str:
        return self._name

    def detect(self, audio, detection_results):
        # Confirms pipeline passes both audio and accumulated detection_results
        self.calls.append((audio, dict(detection_results)))
        return self._result


class _MockProcessor:
    """Minimal processor stub — real process() signature."""

    def __init__(self, name: str):
        self._name = name
        self.calls: list = []

    def get_name(self) -> str:
        return self._name

    def process(self, manifest: EditManifest, audio, detection_results: dict) -> EditManifest:
        self.calls.append((manifest, audio, dict(detection_results)))
        return manifest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_AUDIO = MagicMock(name="pydub_audio_segment")
MOCK_OUTPUT_PATH = "/tmp/fake_video_processed.mp4"


@pytest.fixture
def pipeline():
    """Fresh ProcessingPipeline with an empty config dict."""
    return ProcessingPipeline({})


# ---------------------------------------------------------------------------
# Tests — patching pipeline-level imports
# ---------------------------------------------------------------------------

@patch("core.pipeline.make_processed_output_path", return_value=MOCK_OUTPUT_PATH)
@patch("core.pipeline.video_renderer.render_project")
@patch("core.pipeline.audio_extractor.extract_audio", return_value=MOCK_AUDIO)
class TestPipelineExecuteContract:

    # ── Audio extraction ────────────────────────────────────────────────────

    def test_audio_extracted_exactly_once(self, mock_extract, mock_render, mock_out_path, pipeline):
        """extract_audio() must be called exactly once per pipeline.execute() call."""
        pipeline.execute("/fake/video.mp4")
        mock_extract.assert_called_once_with("/fake/video.mp4")

    def test_audio_extracted_from_given_path(self, mock_extract, mock_render, mock_out_path, pipeline):
        pipeline.execute("/some/other/clip.mp4")
        mock_extract.assert_called_once_with("/some/other/clip.mp4")

    # ── Return values ───────────────────────────────────────────────────────

    def test_returns_output_path_when_render_true(self, mock_extract, mock_render, mock_out_path, pipeline):
        result = pipeline.execute("/fake/video.mp4")
        assert result == MOCK_OUTPUT_PATH

    def test_returns_none_when_render_false(self, mock_extract, mock_render, mock_out_path, pipeline):
        result = pipeline.execute("/fake/video.mp4", render=False)
        assert result is None

    # ── Detector contract ───────────────────────────────────────────────────

    def test_single_detector_receives_extracted_audio(self, mock_extract, mock_render, mock_out_path, pipeline):
        """The audio object returned by extract_audio must reach detector.detect()."""
        det = _MockDetector("my_detector")
        pipeline.add_detector(det)
        pipeline.execute("/fake/video.mp4")
        assert len(det.calls) == 1
        audio_arg = det.calls[0][0]
        assert audio_arg is MOCK_AUDIO

    def test_multiple_detectors_all_receive_audio(self, mock_extract, mock_render, mock_out_path, pipeline):
        det1 = _MockDetector("det_a")
        det2 = _MockDetector("det_b")
        pipeline.add_detector(det1)
        pipeline.add_detector(det2)
        pipeline.execute("/fake/video.mp4")
        assert det1.calls[0][0] is MOCK_AUDIO
        assert det2.calls[0][0] is MOCK_AUDIO

    def test_detector_result_keyed_by_detector_name(self, mock_extract, mock_render, mock_out_path, pipeline):
        """detection_results must include an entry keyed by detector.get_name()."""
        det = _MockDetector("audio_level_detector", result={"lufs": -18.0})
        proc = _MockProcessor("noop_processor")
        pipeline.add_detector(det)
        pipeline.add_processor(proc)
        pipeline.execute("/fake/video.mp4")
        _, _, dr = proc.calls[0]
        assert "audio_level_detector" in dr
        assert dr["audio_level_detector"] == {"lufs": -18.0}

    def test_video_path_seeded_into_detection_results(self, mock_extract, mock_render, mock_out_path, pipeline):
        """video_path must be available in detection_results from the start."""
        proc = _MockProcessor("noop")
        pipeline.add_processor(proc)
        pipeline.execute("/fake/video.mp4")
        _, _, dr = proc.calls[0]
        assert dr["video_path"] == "/fake/video.mp4"

    def test_later_detector_sees_earlier_detector_results(self, mock_extract, mock_render, mock_out_path, pipeline):
        """detection_results accumulate: second detector receives first detector's output."""
        det1 = _MockDetector("first_det", result={"first": True})
        det2 = _MockDetector("second_det")
        pipeline.add_detector(det1)
        pipeline.add_detector(det2)
        pipeline.execute("/fake/video.mp4")
        # detection_results passed to det2 should already contain det1's result
        _, dr_at_det2 = det2.calls[0]
        assert "first_det" in dr_at_det2
        assert dr_at_det2["first_det"] == {"first": True}

    # ── Processor contract ──────────────────────────────────────────────────

    def test_single_processor_receives_extracted_audio(self, mock_extract, mock_render, mock_out_path, pipeline):
        """processor.process() second positional arg must be the extracted audio."""
        proc = _MockProcessor("my_proc")
        pipeline.add_processor(proc)
        pipeline.execute("/fake/video.mp4")
        assert len(proc.calls) == 1
        _, audio_arg, _ = proc.calls[0]
        assert audio_arg is MOCK_AUDIO

    def test_processor_receives_edit_manifest(self, mock_extract, mock_render, mock_out_path, pipeline):
        """processor.process() first positional arg must be an EditManifest."""
        proc = _MockProcessor("my_proc")
        pipeline.add_processor(proc)
        pipeline.execute("/fake/video.mp4")
        manifest_arg, _, _ = proc.calls[0]
        assert isinstance(manifest_arg, EditManifest)

    def test_multiple_processors_all_called(self, mock_extract, mock_render, mock_out_path, pipeline):
        proc1 = _MockProcessor("proc_a")
        proc2 = _MockProcessor("proc_b")
        pipeline.add_processor(proc1)
        pipeline.add_processor(proc2)
        pipeline.execute("/fake/video.mp4")
        assert len(proc1.calls) == 1
        assert len(proc2.calls) == 1

    def test_no_detectors_no_processors_completes(self, mock_extract, mock_render, mock_out_path, pipeline):
        """Pipeline with empty detector/processor lists must complete without error."""
        result = pipeline.execute("/fake/video.mp4")
        assert result == MOCK_OUTPUT_PATH

    # ── Rendering contract ──────────────────────────────────────────────────

    def test_render_true_calls_make_output_path(self, mock_extract, mock_render, mock_out_path, pipeline):
        pipeline.execute("/fake/video.mp4", render=True)
        mock_out_path.assert_called_once_with("/fake/video.mp4")

    def test_render_project_called_with_video_path(self, mock_extract, mock_render, mock_out_path, pipeline):
        pipeline.execute("/fake/video.mp4")
        call_args = mock_render.call_args
        assert call_args[0][0] == "/fake/video.mp4"

    def test_render_project_called_with_manifest(self, mock_extract, mock_render, mock_out_path, pipeline):
        pipeline.execute("/fake/video.mp4")
        call_args = mock_render.call_args
        assert isinstance(call_args[0][1], EditManifest)
