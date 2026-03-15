# Modified by gpt-5.2 | 2026-01-19_01

import numpy as np


# Modified by gpt-5.2 | 2026-01-19_01
def test_cross_talk_detector_removes_beyond_new_pause_duration(monkeypatch):
    from detectors.cross_talk_detector import CrossTalkDetector

    # 5.0s of full silence in both tracks at 100ms windows.
    silent_db = np.full((50,), -100.0)

    def fake_envelope(_audio, window_ms: int):
        assert window_ms == 100
        return silent_db

    monkeypatch.setattr("detectors.cross_talk_detector.calculate_db_envelope", fake_envelope)
    monkeypatch.setattr(CrossTalkDetector, "_verify_mutual_silence", lambda *a, **k: True)

    detector = CrossTalkDetector(
        config={
            "silence_threshold_db": -20,
            "max_pause_duration": 1.2,
            "new_pause_duration": 0.5,
            "silence_window_ms": 100,
        }
    )

    host_audio = type("A", (), {"frame_rate": 44100})()
    guest_audio = type("A", (), {"frame_rate": 44100})()

    regions = detector.detect(host_audio, guest_audio)
    assert regions == [(0.5, 5.0)]


# Modified by gpt-5.2 | 2026-01-19_01
def test_cross_talk_detector_removes_nothing_when_new_pause_longer_than_detected_pause(monkeypatch):
    from detectors.cross_talk_detector import CrossTalkDetector

    # 1.3s of full silence in both tracks at 100ms windows.
    silent_db = np.full((13,), -100.0)

    def fake_envelope(_audio, window_ms: int):
        assert window_ms == 100
        return silent_db

    monkeypatch.setattr("detectors.cross_talk_detector.calculate_db_envelope", fake_envelope)
    monkeypatch.setattr(CrossTalkDetector, "_verify_mutual_silence", lambda *a, **k: True)

    detector = CrossTalkDetector(
        config={
            "silence_threshold_db": -20,
            "max_pause_duration": 1.0,
            "new_pause_duration": 2.0,
            "silence_window_ms": 100,
        }
    )

    host_audio = type("A", (), {"frame_rate": 44100})()
    guest_audio = type("A", (), {"frame_rate": 44100})()

    regions = detector.detect(host_audio, guest_audio)
    assert regions == []
