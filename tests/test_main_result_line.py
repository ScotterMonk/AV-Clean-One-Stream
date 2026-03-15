# tests/test_main_result_line.py
"""Test that _run_process emits [RESULT] line after successful completion."""

import logging
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMainResultLine:
    """Test [RESULT] line emission in _run_process()."""

    def test_result_line_emitted_on_success(self):
        """Verify [RESULT] host=<path> guest=<path> appears in log output."""
        from main import _run_process

        # Mock external dependencies
        mock_h_out = "h_out.mp4"
        mock_g_out = "g_out.mp4"

        # Create a proper mock handler
        mock_handler_class = MagicMock()
        mock_handler_instance = MagicMock(spec=logging.Handler)
        mock_handler_instance.level = logging.INFO
        mock_handler_class.return_value = mock_handler_instance

        with (
            patch("main.normalize_video_lengths", return_value=("host.mp4", "guest.mp4")),
            patch("main._build_pipeline") as mock_build_pipeline,
            patch("main.setup_logger", return_value=logging.getLogger("video_trimmer")),
            patch("utils.progress_log.ProgressLogHandler", mock_handler_class),
        ):
            # Setup mock pipeline
            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = (mock_h_out, mock_g_out)
            mock_build_pipeline.return_value = mock_pipeline

            # Capture log output
            log_capture = StringIO()
            handler = logging.StreamHandler(log_capture)
            handler.setLevel(logging.INFO)
            logger = logging.getLogger("video_trimmer")
            original_handlers = logger.handlers[:]
            logger.handlers = [handler]  # Replace with our handler only
            logger.setLevel(logging.INFO)

            try:
                _run_process(
                    host="host.mp4",
                    guest="guest.mp4",
                    norm_mode=None,
                    action=None,
                )
            finally:
                logger.handlers = original_handlers  # Restore original handlers

            log_output = log_capture.getvalue()

            # Assert [RESULT] line is present with correct format
            assert "[RESULT]" in log_output
            assert f"host={mock_h_out}" in log_output
            assert f"guest={mock_g_out}" in log_output
