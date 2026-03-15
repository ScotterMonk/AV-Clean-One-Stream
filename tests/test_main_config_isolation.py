"""Regression test for per-run config isolation in [`_run_process()`](main.py:93)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import QUALITY_PRESETS
from main import _run_process


def test_run_process_norm_mode_override_does_not_mutate_global_preset():
    """Verify [`QUALITY_PRESETS`](config.py) remains unchanged across runs."""
    original_mode = QUALITY_PRESETS["PODCAST_HIGH_QUALITY"]["normalization"]["mode"]

    assert original_mode == "MATCH_HOST"

    with (
        patch("main.normalize_video_lengths", side_effect=lambda h, g: (h, g)),
        patch("main._build_pipeline") as mock_build_pipeline,
        patch("main.setup_logger", return_value=MagicMock()),
        patch("utils.progress_log.ProgressLogHandler", return_value=MagicMock()),
        patch("main.get_video_duration_seconds", return_value=1.0),
        patch("logging.getLogger") as mock_get_logger,
    ):
        mock_pipeline = MagicMock()
        mock_pipeline.execute.return_value = ("h_out.mp4", "g_out.mp4")
        mock_build_pipeline.return_value = mock_pipeline

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        _run_process(
            host="host.mp4",
            guest="guest.mp4",
            norm_mode="STANDARD_LUFS",
            action=None,
        )

        _run_process(
            host="host.mp4",
            guest="guest.mp4",
            norm_mode=None,
            action=None,
        )

    assert QUALITY_PRESETS["PODCAST_HIGH_QUALITY"]["normalization"]["mode"] == "MATCH_HOST"
