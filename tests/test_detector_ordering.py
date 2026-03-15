import copy
import os
import sys

# Ensure project root is importable when running from /tests.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

from detectors.audio_level_detector import AudioLevelDetector
from detectors.cross_talk_detector import CrossTalkDetector
from detectors.filler_word_detector import FillerWordDetector
from detectors.spike_fixer_detector import SpikeFixerDetector


def _build_pipeline_with_processors(
    monkeypatch,
    *,
    audio_normalizer: bool,
    spike_fixer: bool,
    segment_remover: bool,
    word_muter: bool,
):
    pipeline_config = {
        "processors": [
            {"type": "SegmentRemover", "enabled": bool(segment_remover)},
            {"type": "AudioNormalizer", "enabled": bool(audio_normalizer)},
            {"type": "SpikeFixer", "enabled": bool(spike_fixer)},
            {"type": "WordMuter", "enabled": bool(word_muter)},
        ]
    }

    monkeypatch.setattr(main, "PIPELINE_CONFIG", pipeline_config)
    config = copy.deepcopy(main.QUALITY_PRESETS["PODCAST_HIGH_QUALITY"])
    return main._build_pipeline(config)


def test_detector_ordering_with_audio_normalizer_enabled(monkeypatch):
    pipeline = _build_pipeline_with_processors(
        monkeypatch,
        audio_normalizer=True,
        spike_fixer=True,
        segment_remover=True,
        word_muter=True,
    )

    assert pipeline.detectors, "Expected at least one detector to be registered"

    # Verify AudioLevelDetector first.
    assert isinstance(pipeline.detectors[0], AudioLevelDetector)

    # Verify SpikeFixerDetector after AudioLevelDetector.
    spike_idx = next(i for i, d in enumerate(pipeline.detectors) if isinstance(d, SpikeFixerDetector))
    audio_level_idx = next(i for i, d in enumerate(pipeline.detectors) if isinstance(d, AudioLevelDetector))
    assert spike_idx > audio_level_idx

    # Verify CrossTalkDetector positioning (after SpikeFixerDetector in the required detector sequence).
    cross_talk_idx = next(i for i, d in enumerate(pipeline.detectors) if isinstance(d, CrossTalkDetector))
    filler_word_idx = next(i for i, d in enumerate(pipeline.detectors) if isinstance(d, FillerWordDetector))
    assert filler_word_idx > spike_idx
    assert filler_word_idx < cross_talk_idx
    assert cross_talk_idx > spike_idx


def test_audio_level_detector_not_registered_when_audio_normalizer_disabled(monkeypatch):
    pipeline = _build_pipeline_with_processors(
        monkeypatch,
        audio_normalizer=False,
        spike_fixer=True,
        segment_remover=True,
        word_muter=False,
    )

    assert not any(isinstance(d, AudioLevelDetector) for d in pipeline.detectors)

