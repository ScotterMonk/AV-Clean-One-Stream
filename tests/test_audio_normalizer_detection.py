import os
import sys

import pytest


# Ensure project root is importable when running from /tests.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_audio_normalizer_match_host_uses_detection_results_and_adds_guest_volume_filter() -> None:
    from core.interfaces import EditManifest
    from processors.audio_normalizer import AudioNormalizer

    processor = AudioNormalizer({"normalization": {"mode": "MATCH_HOST", "max_gain_db": 15.0}})

    manifest = processor.process(
        EditManifest(),
        None,
        None,
        {
            "audio_level_detector": {
                "mode": "MATCH_HOST",
                "host_lufs": -16.0,
                "guest_lufs": -22.0,
                "guest_gain_db": 6.0,
            }
        },
    )

    assert manifest.host_filters == []
    assert len(manifest.guest_filters) == 1
    assert manifest.guest_filters[0].filter_name == "volume"
    assert manifest.guest_filters[0].params == {"volume": "6.0dB"}

    assert manifest.guest_audio_gain_db_applied == pytest.approx(6.0)
    assert not hasattr(manifest, "guest_audio_gain_db_estimate")


def test_audio_normalizer_standard_lufs_uses_detection_results_and_adds_loudnorm_to_both_tracks() -> None:
    from core.interfaces import EditManifest
    from processors.audio_normalizer import AudioNormalizer

    processor = AudioNormalizer({"normalization": {"mode": "STANDARD_LUFS", "standard_target": -16.0}})

    loudnorm_params = {"I": -16.0, "TP": -1.5, "LRA": 11}
    manifest = processor.process(
        EditManifest(),
        None,
        None,
        {
            "audio_level_detector": {
                "mode": "STANDARD_LUFS",
                "host_lufs": -18.0,
                "guest_lufs": -24.0,
                "target_lufs": -16.0,
                "loudnorm_params": loudnorm_params,
            }
        },
    )

    assert len(manifest.host_filters) == 1
    assert manifest.host_filters[0].filter_name == "loudnorm"
    assert manifest.host_filters[0].params == loudnorm_params

    assert len(manifest.guest_filters) == 1
    assert manifest.guest_filters[0].filter_name == "loudnorm"
    assert manifest.guest_filters[0].params == loudnorm_params

    assert manifest.guest_audio_gain_db_estimate == pytest.approx(8.0)
    assert not hasattr(manifest, "guest_audio_gain_db_applied")


def test_audio_normalizer_errors_when_detection_results_missing() -> None:
    from core.interfaces import EditManifest
    from processors.audio_normalizer import AudioNormalizer

    processor = AudioNormalizer({"normalization": {"mode": "MATCH_HOST"}})

    with pytest.raises(ValueError, match=r"requires detection_results"):
        processor.process(EditManifest(), None, None, None)


def test_audio_normalizer_errors_when_audio_level_detector_results_missing() -> None:
    from core.interfaces import EditManifest
    from processors.audio_normalizer import AudioNormalizer

    processor = AudioNormalizer({"normalization": {"mode": "MATCH_HOST"}})

    with pytest.raises(ValueError, match=r"detection_results\['audio_level_detector'\]"):
        processor.process(EditManifest(), None, None, {})

