# tests/test_cli.py
# Created by coder-sr | 2026-03-15
"""Tests for the CLI contract defined in main.py.

Uses click.testing.CliRunner — no real processing, FFmpeg, or file I/O.

What is tested:
- cli --input <path>           routes to _run_process(input_path=<path>)
- cli (no args)                exits non-zero with a helpful usage message
- cli process --input <path>   routes to _run_process(input_path=<path>)
- cli process (no args)        exits non-zero (--input is required)
- --host / --guest flags       are rejected (removed in single-stream refactor)
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from main import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _invoke(args, *, run_process_mock=None):
    """Invoke the CLI with CliRunner; returns (result, mock)."""
    runner = CliRunner()
    if run_process_mock is None:
        run_process_mock = MagicMock()
    with patch("main._run_process", run_process_mock):
        result = runner.invoke(cli, args, catch_exceptions=False)
    return result, run_process_mock


# ---------------------------------------------------------------------------
# cli group — top-level --input flag
# ---------------------------------------------------------------------------

class TestCliGroupInput:
    def test_input_flag_calls_run_process_with_correct_path(self):
        _, mock_run = _invoke(["--input", "/some/video.mp4"])
        mock_run.assert_called_once_with(input_path="/some/video.mp4")

    def test_input_flag_exits_zero(self):
        result, _ = _invoke(["--input", "/some/video.mp4"])
        assert result.exit_code == 0

    def test_no_args_exits_nonzero(self):
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code != 0

    def test_no_args_mentions_input_in_output(self):
        runner = CliRunner()
        result = runner.invoke(cli, [])
        # Click should surface "--input" in the error text
        assert "--input" in result.output or "Missing" in result.output

    def test_host_flag_rejected(self):
        """--host must not exist; Click should exit non-zero."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--host", "/host.mp4"])
        assert result.exit_code != 0

    def test_guest_flag_rejected(self):
        """--guest must not exist; Click should exit non-zero."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--guest", "/guest.mp4"])
        assert result.exit_code != 0

    def test_host_error_message_indicates_unknown_option(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--host", "/host.mp4"])
        # Click surfaces "No such option" for unrecognised flags
        assert "no such option" in result.output.lower() or result.exit_code != 0

    def test_guest_error_message_indicates_unknown_option(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--guest", "/guest.mp4"])
        assert "no such option" in result.output.lower() or result.exit_code != 0


# ---------------------------------------------------------------------------
# process subcommand — dedicated --input flag
# ---------------------------------------------------------------------------

class TestProcessSubcommand:
    def test_process_input_calls_run_process_with_path(self):
        _, mock_run = _invoke(["process", "--input", "/some/video.mp4"])
        mock_run.assert_called_once_with(input_path="/some/video.mp4")

    def test_process_input_exits_zero(self):
        result, _ = _invoke(["process", "--input", "/some/video.mp4"])
        assert result.exit_code == 0

    def test_process_missing_input_exits_nonzero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["process"])
        assert result.exit_code != 0

    def test_process_host_flag_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["process", "--host", "/host.mp4"])
        assert result.exit_code != 0

    def test_process_guest_flag_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["process", "--guest", "/guest.mp4"])
        assert result.exit_code != 0

    def test_process_does_not_call_run_process_without_input(self):
        """When --input is missing, _run_process must never be called."""
        mock_run = MagicMock()
        runner = CliRunner()
        with patch("main._run_process", mock_run):
            runner.invoke(cli, ["process"])
        mock_run.assert_not_called()
