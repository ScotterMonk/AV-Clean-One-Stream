import subprocess


def test_get_video_duration_seconds_missing_file_raises():
    from io_.media_probe import get_video_duration_seconds

    try:
        get_video_duration_seconds("this_file_does_not_exist.mp4")
        raise AssertionError("Expected FileNotFoundError")
    except FileNotFoundError:
        pass


def test_get_video_duration_seconds_missing_ffprobe_raises(monkeypatch, tmp_path):
    from io_ import media_probe

    p = tmp_path / "video.mp4"
    p.write_bytes(b"not a real mp4")

    def _raise(_cmd, capture_output, text):
        raise FileNotFoundError("ffprobe not found")

    monkeypatch.setattr(media_probe.subprocess, "run", _raise)

    try:
        media_probe.get_video_duration_seconds(str(p))
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as e:
        assert "ffprobe" in str(e).lower()


def test_get_video_duration_seconds_nonzero_returncode_raises(monkeypatch, tmp_path):
    from io_ import media_probe

    p = tmp_path / "video.mp4"
    p.write_bytes(b"not a real mp4")

    def _fake_run(_cmd, capture_output, text):
        return subprocess.CompletedProcess(args=_cmd, returncode=1, stdout="", stderr="bad")

    monkeypatch.setattr(media_probe.subprocess, "run", _fake_run)

    try:
        media_probe.get_video_duration_seconds(str(p))
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as e:
        assert "ffprobe failed" in str(e).lower()


def test_get_video_duration_seconds_parses_float(monkeypatch, tmp_path):
    from io_ import media_probe

    p = tmp_path / "video.mp4"
    p.write_bytes(b"not a real mp4")

    def _fake_run(_cmd, capture_output, text):
        return subprocess.CompletedProcess(args=_cmd, returncode=0, stdout="12.5\n", stderr="")

    monkeypatch.setattr(media_probe.subprocess, "run", _fake_run)

    assert media_probe.get_video_duration_seconds(str(p)) == 12.5

