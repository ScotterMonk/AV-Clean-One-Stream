import os
import sys

import pytest


# Add the project root to sys.path (mirrors tests/test_imports.py)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from detectors.spike_fixer_detector import SpikeFixerDetector


class _DummyAudio:
    def __init__(self, duration_seconds: float = 3.0):
        self.duration_seconds = float(duration_seconds)


def test_builds_ffmpeg_filter_chain_match_host(monkeypatch):
    d = SpikeFixerDetector(config={"spike_threshold_db": -6})

    calls = {}

    def _fake_run(cmd, **kwargs):
        calls["cmd"] = cmd

        class _P:
            returncode = 0
            stderr = "[Parsed_astats_0 @ 0x0] Overall\n[Parsed_astats_0 @ 0x0] Peak level dB: -3.0\n"

        return _P()

    monkeypatch.setattr("subprocess.run", _fake_run)

    regions = d.detect(
        host_audio=_DummyAudio(),
        guest_audio=_DummyAudio(duration_seconds=2.5),
        detection_results={
            "guest_video_path": "C:/tmp/guest.mp4",
            "audio_level_detector": {"mode": "MATCH_HOST", "guest_gain_db": 5.5},
        },
    )

    assert "-af" in calls["cmd"]
    af = calls["cmd"][calls["cmd"].index("-af") + 1]
    assert af == "volume=5.5dB,astats=metadata=1:reset=1"
    assert regions == [(0.0, 1.0)]


def test_builds_ffmpeg_filter_chain_standard_lufs(monkeypatch):
    d = SpikeFixerDetector(config={"spike_threshold_db": -6})

    calls = {}

    def _fake_run(cmd, **kwargs):
        calls["cmd"] = cmd

        class _P:
            returncode = 0
            stderr = "[Parsed_astats_0 @ 0x0] Overall\n[Parsed_astats_0 @ 0x0] Max level dB: -2.0\n"

        return _P()

    monkeypatch.setattr("subprocess.run", _fake_run)

    regions = d.detect(
        host_audio=_DummyAudio(),
        guest_audio=_DummyAudio(duration_seconds=4.0),
        detection_results={
            "guest_video_path": "C:/tmp/guest.mp4",
            "audio_level_detector": {
                "mode": "STANDARD_LUFS",
                "target_lufs": -16.0,
                "loudnorm_params": {"I": -16.0, "TP": -1.5, "LRA": 11},
            },
        },
    )

    assert "-af" in calls["cmd"]
    af = calls["cmd"][calls["cmd"].index("-af") + 1]
    assert af == "loudnorm=I=-16.0:TP=-1.5:LRA=11.0,astats=metadata=1:reset=1"
    assert regions == [(0.0, 1.0)]


def test_parse_astats_series_multiple_overall_blocks_produces_windows():
    stderr = """
[Parsed_astats_0 @ 0x0] Overall
[Parsed_astats_0 @ 0x0] Peak level dB: -20.0
[Parsed_astats_0 @ 0x0] Overall
[Parsed_astats_0 @ 0x0] Peak level dB: -4.0
""".strip()

    series = SpikeFixerDetector._parse_astats_peak_series_db(stderr)
    assert series == [-20.0, -4.0]


def test_detect_falls_back_when_audio_level_missing(monkeypatch):
    d = SpikeFixerDetector(config={"spike_threshold_db": -6})
    monkeypatch.setattr(d, "_detect_pre_normalization", lambda *_args, **_kwargs: [(1.0, 2.0)])

    got = d.detect(host_audio=_DummyAudio(), guest_audio=_DummyAudio(), detection_results={"guest_video_path": "x"})
    assert got == [(1.0, 2.0)]


def test_detect_falls_back_when_ffmpeg_fails(monkeypatch):
    d = SpikeFixerDetector(config={"spike_threshold_db": -6})
    monkeypatch.setattr(d, "_detect_pre_normalization", lambda *_args, **_kwargs: [(1.0, 2.0)])

    def _fake_run(cmd, **kwargs):
        class _P:
            returncode = 1
            stderr = "ffmpeg error"

        return _P()

    monkeypatch.setattr("subprocess.run", _fake_run)

    got = d.detect(
        host_audio=_DummyAudio(),
        guest_audio=_DummyAudio(),
        detection_results={
            "guest_video_path": "C:/tmp/guest.mp4",
            "audio_level_detector": {"mode": "MATCH_HOST", "guest_gain_db": 1.0},
        },
    )
    assert got == [(1.0, 2.0)]


def test_detect_raises_on_bad_reset_seconds():
    d = SpikeFixerDetector(config={})
    with pytest.raises(ValueError):
        d._spike_regions_from_peak_series([-1.0], reset_seconds=0.0, duration_seconds=1.0, threshold_db=-6.0)

