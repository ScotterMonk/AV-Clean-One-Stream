import logging


def test_spike_fixer_logs_applied_limiter(caplog) -> None:
    from core.interfaces import EditManifest
    from processors.spike_fixer import SpikeFixer

    processor = SpikeFixer(
        {
            "max_peak_db": -6.0,
            "limiter_attack_ms": 5.0,
            "limiter_release_ms": 50.0,
        }
    )

    caplog.set_level(logging.INFO)
    processor.process(
        EditManifest(),
        host_audio=object(),
        guest_audio=object(),
        detection_results={"spike_fixer_detector": [(1.0, 2.0)]},
    )

    assert (
        "[PROCESSOR] Applied limiter to 1 spike regions in guest video - Settings: limit=0.501, attack=5.0ms, release=50.0ms"
        in caplog.text
    )

