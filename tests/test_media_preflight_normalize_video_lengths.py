from __future__ import annotations

import os
import sys

import pytest

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_normalize_video_lengths_equal_returns_inputs(monkeypatch):
    from io_ import media_preflight

    monkeypatch.setattr(media_preflight, "get_video_duration_seconds", lambda _p: 10.0)

    called = []

    def _nope(_plan):
        called.append(True)

    monkeypatch.setattr(media_preflight, "_video_pad_efficient", _nope)

    host_out, guest_out = media_preflight.normalize_video_lengths("host.mp4", "guest.mp4")
    assert (host_out, guest_out) == ("host.mp4", "guest.mp4")
    assert called == []


def test_normalize_video_lengths_returns_inputs_when_within_tolerance(monkeypatch):
    from io_ import media_preflight

    durations = {"host.mp4": 10.0, "guest.mp4": 10.005}
    monkeypatch.setattr(media_preflight, "get_video_duration_seconds", lambda p: durations[p])

    called = []

    def _nope(_plan):
        called.append(True)

    monkeypatch.setattr(media_preflight, "_video_pad_efficient", _nope)

    host_out, guest_out = media_preflight.normalize_video_lengths("host.mp4", "guest.mp4")
    assert (host_out, guest_out) == ("host.mp4", "guest.mp4")
    assert called == []


def test_normalize_video_lengths_normalizes_when_outside_tolerance(monkeypatch):
    """When guest is longer, only the host (shorter) video is padded.

    guest=10.02 > host=10.0 → host needs padding.
    Expected: host_out = _preflight path, guest_out = original guest path.
    Only one call to _video_pad_efficient (for the shorter video).
    """
    from io_ import media_preflight

    durations = {"host.mp4": 10.0, "guest.mp4": 10.02}
    monkeypatch.setattr(media_preflight, "get_video_duration_seconds", lambda p: durations[p])

    calls = []

    def _capture(plan):
        calls.append(plan)

    monkeypatch.setattr(media_preflight, "_video_pad_efficient", _capture)

    host_out, guest_out = media_preflight.normalize_video_lengths("host.mp4", "guest.mp4")

    # Only the shorter video gets a _preflight output; the longer is returned as-is.
    assert host_out.endswith("_preflight.mp4"), f"Expected host_out to be a preflight path, got: {host_out}"
    assert guest_out == "guest.mp4", f"Expected guest_out to be the original path, got: {guest_out}"

    # Exactly one pad call — only the shorter video.
    assert len(calls) == 1, f"Expected 1 call, got {len(calls)}"

    padded = calls[0]
    assert padded.input_path == "host.mp4"
    assert padded.target_duration_s == pytest.approx(10.02)
    assert padded.pad_seconds == pytest.approx(0.02)


def test_normalize_video_lengths_mismatch_pads_shorter_only(monkeypatch):
    """When host is longer, only the guest (shorter) video is padded.

    host=10.0 > guest=8.0 → guest needs padding.
    Expected: guest_out = _preflight path, host_out = original host path.
    Only one call to _video_pad_efficient (for the shorter video).
    Completion log messages are emitted.
    """
    from io_ import media_preflight

    logged: list[str] = []

    class _FakeLogger:
        def info(self, msg, *args, **kwargs):
            if args:
                msg = msg % args
            logged.append(str(msg))

        def warning(self, msg, *args, **kwargs):
            if args:
                msg = msg % args
            logged.append(str(msg))

    monkeypatch.setattr(media_preflight, "logger", _FakeLogger())

    durations = {"host.mp4": 10.0, "guest.mp4": 8.0}
    monkeypatch.setattr(media_preflight, "get_video_duration_seconds", lambda p: durations[p])

    calls = []

    def _capture(plan):
        calls.append(plan)

    monkeypatch.setattr(media_preflight, "_video_pad_efficient", _capture)

    host_out, guest_out = media_preflight.normalize_video_lengths("host.mp4", "guest.mp4")

    # Longer video (host) returned as-is; shorter (guest) gets the _preflight output.
    assert host_out == "host.mp4", f"Expected host_out to be the original path, got: {host_out}"
    assert guest_out.endswith("_preflight.mp4"), f"Expected guest_out to be a preflight path, got: {guest_out}"

    # Exactly one pad call — only the shorter video.
    assert len(calls) == 1, f"Expected 1 call, got {len(calls)}"

    padded = calls[0]
    assert padded.input_path == "guest.mp4"
    assert padded.target_duration_s == pytest.approx(10.0)
    assert padded.pad_seconds == pytest.approx(2.0)

    # Completion log messages should be present.
    assert any("[PREFLIGHT COMPLETE]" in m for m in logged), "Expected [PREFLIGHT COMPLETE] log"
    assert any("Preflight pair written" in m for m in logged), "Expected 'Preflight pair written' in log"
