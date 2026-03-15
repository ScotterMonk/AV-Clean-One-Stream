import subprocess


def test_probe_ffmpeg_capabilities_missing_ffmpeg(monkeypatch):
    # Created by gpt-5.2 | 2026-01-09_01
    from io_ import video_renderer

    def _raise(_args, capture_output, text):
        raise FileNotFoundError("ffmpeg not found")

    monkeypatch.setattr(video_renderer.subprocess, "run", _raise)
    video_renderer.probe_ffmpeg_capabilities.cache_clear()

    caps = video_renderer.probe_ffmpeg_capabilities()
    assert caps["ffmpeg_ok"] is False
    assert caps["encoders"] == frozenset()
    assert caps["hwaccels"] == frozenset()


def test_probe_ffmpeg_capabilities_detects_nvenc_and_cuda(monkeypatch):
    # Created by gpt-5.2 | 2026-01-09_01
    from io_ import video_renderer

    def _fake_run(args, capture_output, text):
        if args[-1] == "-encoders":
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="V..... h264_nvenc NVIDIA NVENC H.264 encoder\nV..... hevc_nvenc NVIDIA NVENC hevc encoder\n",
                stderr="",
            )
        if args[-1] == "-hwaccels":
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="Hardware acceleration methods:\n  cuda\n  dxva2\n",
                stderr="",
            )
        raise AssertionError(f"Unexpected ffmpeg args: {args}")

    monkeypatch.setattr(video_renderer.subprocess, "run", _fake_run)
    video_renderer.probe_ffmpeg_capabilities.cache_clear()

    caps = video_renderer.probe_ffmpeg_capabilities()
    assert caps["ffmpeg_ok"] is True
    assert caps["encoders"] == frozenset({"h264_nvenc", "hevc_nvenc"})
    assert caps["hwaccels"] == frozenset({"cuda"})


def test_select_enc_opts_cuda_disabled_uses_cpu(monkeypatch):
    # Created by gpt-5.2 | 2026-01-09_02
    from io_ import video_renderer

    enc_opts = video_renderer.select_enc_opts(
        {"cuda_encode_enabled": False, "video_codec": "libx264", "crf": 21},
        {"encoders": frozenset({"h264_nvenc"})},
    )
    assert enc_opts["vcodec"] == "libx264"
    assert enc_opts["crf"] == 21


def test_select_enc_opts_nvenc_available_uses_nvenc(monkeypatch):
    # Created by gpt-5.2 | 2026-01-09_02
    from io_ import video_renderer

    enc_opts = video_renderer.select_enc_opts(
        {"cuda_encode_enabled": True, "nvenc": {"codec": "h264_nvenc", "preset": "p5"}},
        {"encoders": frozenset({"h264_nvenc"})},
    )
    assert enc_opts["vcodec"] == "h264_nvenc"
    assert enc_opts["preset"] == "p5"
    assert "crf" not in enc_opts


def test_select_enc_opts_nvenc_missing_require_support_raises(monkeypatch):
    # Created by gpt-5.2 | 2026-01-09_02
    from io_ import video_renderer

    try:
        video_renderer.select_enc_opts(
            {"cuda_encode_enabled": True, "cuda_require_support": True},
            {"encoders": frozenset()},
        )
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as e:
        assert "h264_nvenc" in str(e)


def test_select_enc_opts_nvenc_missing_falls_back_and_warns(monkeypatch):
    # Created by gpt-5.2 | 2026-01-09_02
    from io_ import video_renderer

    warnings = []

    def _warn(msg, *args, **kwargs):
        warnings.append(msg)

    monkeypatch.setattr(video_renderer.logger, "warning", _warn)

    enc_opts = video_renderer.select_enc_opts(
        {"cuda_encode_enabled": True, "cuda_require_support": False, "video_codec": "libx264"},
        {"encoders": frozenset()},
    )
    assert enc_opts["vcodec"] == "libx264"
    assert warnings == ["CUDA/NVENC REQUESTED BUT NOT AVAILABLE; FALLING BACK TO CPU ENCODE"]


def test_build_input_kwargs_cuda_decode_enabled_and_cuda_supported_returns_hwaccel_cuda():
    from io_ import video_renderer

    input_kwargs = video_renderer.build_input_kwargs(
        {"cuda_decode_enabled": True},
        {"hwaccels": ("cuda", "dxva2")},
    )

    assert input_kwargs == {"hwaccel": "cuda"}


def test_build_input_kwargs_otherwise_returns_empty_dict():
    from io_ import video_renderer

    assert (
        video_renderer.build_input_kwargs(
            {"cuda_decode_enabled": True},
            {"hwaccels": ("dxva2",)},
        )
        == {}
    )
    assert (
        video_renderer.build_input_kwargs(
            {"cuda_decode_enabled": False},
            {"hwaccels": ("cuda",)},
        )
        == {}
    )

