import pytest


def test_select_enc_opts_cpu_path_includes_crf_libx264_and_audio_keys():
    from io_ import video_renderer

    enc_opts = video_renderer.select_enc_opts(
        {
            "cuda_encode_enabled": False,
            "crf": 20,
            "audio_codec": "aac",
            "audio_bitrate": "128k",
        },
        {"encoders": frozenset({"h264_nvenc"})},
    )

    assert enc_opts["vcodec"] == "libx264"  # default CPU codec
    assert enc_opts["crf"] == 20
    assert enc_opts["acodec"] == "aac"
    assert enc_opts["audio_bitrate"] == "128k"


def test_select_enc_opts_nvenc_path_uses_h264_nvenc_omits_crf_and_includes_audio_keys():
    from io_ import video_renderer

    enc_opts = video_renderer.select_enc_opts(
        {
            "cuda_encode_enabled": True,
            "nvenc": {"codec": "h264_nvenc", "preset": "p5"},
            "audio_codec": "aac",
            "audio_bitrate": "160k",
        },
        {"encoders": frozenset({"h264_nvenc"})},
    )

    assert enc_opts["vcodec"] == "h264_nvenc"
    assert "crf" not in enc_opts
    assert enc_opts["acodec"] == "aac"
    assert enc_opts["audio_bitrate"] == "160k"


def test_select_enc_opts_nvenc_missing_falls_back_to_cpu_when_not_required(monkeypatch):
    from io_ import video_renderer

    warnings = []

    def _warn(msg, *args, **kwargs):
        warnings.append(msg)

    monkeypatch.setattr(video_renderer.logger, "warning", _warn)

    enc_opts = video_renderer.select_enc_opts(
        {
            "cuda_encode_enabled": True,
            "cuda_require_support": False,
            "video_codec": "libx264",
            "crf": 22,
            "audio_codec": "aac",
            "audio_bitrate": "192k",
        },
        {"encoders": frozenset()},
    )

    assert enc_opts["vcodec"] == "libx264"
    assert enc_opts["crf"] == 22
    assert enc_opts["acodec"] == "aac"
    assert enc_opts["audio_bitrate"] == "192k"
    assert warnings == ["CUDA/NVENC REQUESTED BUT NOT AVAILABLE; FALLING BACK TO CPU ENCODE"]


def test_select_enc_opts_nvenc_missing_fail_fast_when_required():
    from io_ import video_renderer

    with pytest.raises(RuntimeError) as e:
        video_renderer.select_enc_opts(
            {"cuda_encode_enabled": True, "cuda_require_support": True},
            {"encoders": frozenset()},
        )

    assert "h264_nvenc" in str(e.value)

