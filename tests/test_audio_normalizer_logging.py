import logging


# Modified by gpt-5.2 | 2026-01-20_01
def test_audio_normalizer_logs_match_host(monkeypatch, caplog):
    from core.interfaces import EditManifest
    from processors.audio_normalizer import AudioNormalizer

    processor = AudioNormalizer(
        {
            "normalization": {
                "mode": "MATCH_HOST",
                "max_gain_db": 15.0,
            }
        }
    )

    caplog.set_level(logging.INFO)
    processor.process(
        EditManifest(),
        object(),
        object(),
        {
            "audio_level_detector": {
                "mode": "MATCH_HOST",
                "host_lufs": -16.2,
                "guest_lufs": -22.5,
                "guest_gain_db": 6.3,
            }
        },
    )

    assert "[PROCESSOR] Audio analysis - Host: -16.2 LUFS, Guest: -22.5 LUFS" in caplog.text
    assert "[PROCESSOR] Normalized guest audio - Applied +6.3 dB gain to match host" in caplog.text


# Modified by gpt-5.2 | 2026-01-20_01
def test_audio_normalizer_logs_standard_lufs(monkeypatch, caplog):
    from core.interfaces import EditManifest
    from processors.audio_normalizer import AudioNormalizer

    processor = AudioNormalizer(
        {
            "normalization": {
                "mode": "STANDARD_LUFS",
                "standard_target": -16.0,
            }
        }
    )

    caplog.set_level(logging.INFO)
    processor.process(
        EditManifest(),
        object(),
        object(),
        {
            "audio_level_detector": {
                "mode": "STANDARD_LUFS",
                "host_lufs": -18.0,
                "guest_lufs": -24.0,
                "target_lufs": -16.0,
                "loudnorm_params": {"I": -16.0, "TP": -1.5, "LRA": 11},
            }
        },
    )

    assert "[PROCESSOR] Audio analysis - Host: -18.0 LUFS, Guest: -24.0 LUFS" in caplog.text
    assert "[PROCESSOR] Normalized both tracks - Target: -16.0 LUFS (STANDARD_LUFS mode)" in caplog.text
