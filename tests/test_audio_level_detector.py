import os
import sys

import pytest


# Add the project root to sys.path (consistent with existing tests like tests/test_imports.py)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from detectors.audio_level_detector import AudioLevelDetector


def test_audio_level_detector_match_host_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    # detectors.audio_level_detector imports calculate_lufs directly, so patch that symbol.
    values = iter([-18.0, -23.0])
    monkeypatch.setattr(
        "detectors.audio_level_detector.calculate_lufs",
        lambda _audio: next(values),
    )

    detector = AudioLevelDetector(
        config={
            "normalization": {
                "mode": "MATCH_HOST",
                "max_gain_db": 15.0,
            }
        }
    )

    result = detector.detect(object(), object())

    assert result["mode"] == "MATCH_HOST"
    assert result["host_lufs"] == pytest.approx(-18.0)
    assert result["guest_lufs"] == pytest.approx(-23.0)
    assert result["guest_gain_db"] == pytest.approx(5.0)


def test_audio_level_detector_match_host_clamp(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter([-10.0, -30.0])
    monkeypatch.setattr(
        "detectors.audio_level_detector.calculate_lufs",
        lambda _audio: next(values),
    )

    detector = AudioLevelDetector(
        config={
            "normalization": {
                "mode": "MATCH_HOST",
                "max_gain_db": 15.0,
            }
        }
    )

    result = detector.detect(object(), object())

    assert result["mode"] == "MATCH_HOST"
    assert result["host_lufs"] == pytest.approx(-10.0)
    assert result["guest_lufs"] == pytest.approx(-30.0)
    assert result["guest_gain_db"] == pytest.approx(15.0)


def test_audio_level_detector_standard_lufs(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter([-18.0, -23.0])
    monkeypatch.setattr(
        "detectors.audio_level_detector.calculate_lufs",
        lambda _audio: next(values),
    )

    detector = AudioLevelDetector(
        config={
            "normalization": {
                "mode": "STANDARD_LUFS",
                "standard_target": -16.0,
            }
        }
    )

    result = detector.detect(object(), object())

    assert result["mode"] == "STANDARD_LUFS"
    assert result["host_lufs"] == pytest.approx(-18.0)
    assert result["guest_lufs"] == pytest.approx(-23.0)
    assert result["target_lufs"] == pytest.approx(-16.0)

    assert set(result["loudnorm_params"].keys()) == {"I", "TP", "LRA"}
    assert result["loudnorm_params"]["I"] == pytest.approx(-16.0)
    assert result["loudnorm_params"]["TP"] == pytest.approx(-1.5)
    assert result["loudnorm_params"]["LRA"] == pytest.approx(11.0)

