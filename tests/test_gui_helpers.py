# tests/test_gui_helpers.py
# Created by coder-sr | 2026-03-15
"""Tests for ui/gui_process_helpers.py — single-stream result-line parsing.

What is tested:
- result_line_paths_parse() extracts the path from [RESULT] output=<path>
- Returns None for lines that do not start with [RESULT]
- Returns None for [RESULT] lines that contain no output= key
- Returns None for the old dual-stream host=/... guest=/... format
- No real files, network, or GUI required.
"""

import pytest
from ui.gui_process_helpers import result_line_paths_parse


# ---------------------------------------------------------------------------
# result_line_paths_parse() — happy paths
# ---------------------------------------------------------------------------

class TestResultLinePathsParseValid:
    def test_standard_unix_path_returned(self):
        line = "[RESULT] output=/some/path.mp4"
        assert result_line_paths_parse(line) == "/some/path.mp4"

    def test_windows_path_returned(self):
        line = r"[RESULT] output=C:\Users\scott\Videos\output_processed.mp4"
        result = result_line_paths_parse(line)
        assert result == r"C:\Users\scott\Videos\output_processed.mp4"

    def test_path_with_spaces_returned_intact(self):
        line = "[RESULT] output=/some/path with spaces/video processed.mp4"
        result = result_line_paths_parse(line)
        assert result == "/some/path with spaces/video processed.mp4"

    def test_trailing_whitespace_stripped(self):
        line = "[RESULT] output=/clean/video.mp4   "
        result = result_line_paths_parse(line)
        assert result == "/clean/video.mp4"

    def test_nested_path_returned(self):
        line = "[RESULT] output=/project/recordings/2026-03/ep01_processed.mp4"
        result = result_line_paths_parse(line)
        assert result == "/project/recordings/2026-03/ep01_processed.mp4"

    def test_none_string_pipeline_log_returned_as_string(self):
        """Pipeline logs output=None when render=False; parser returns the string 'None'."""
        line = "[RESULT] output=None"
        result = result_line_paths_parse(line)
        assert result == "None"


# ---------------------------------------------------------------------------
# result_line_paths_parse() — rejection cases
# ---------------------------------------------------------------------------

class TestResultLinePathsParseReturnsNone:
    def test_non_result_prefix_returns_none(self):
        assert result_line_paths_parse("[RUN SUMMARY] something") is None

    def test_empty_string_returns_none(self):
        assert result_line_paths_parse("") is None

    def test_plain_text_returns_none(self):
        assert result_line_paths_parse("Processing complete.") is None

    def test_result_without_output_key_returns_none(self):
        """[RESULT] line with no output= key must return None."""
        assert result_line_paths_parse("[RESULT] something_else=/path.mp4") is None

    def test_old_dual_stream_host_guest_format_returns_none(self):
        """Old format [RESULT] host=... guest=... must be rejected (no output= key)."""
        line = "[RESULT] host=/host.mp4 guest=/guest.mp4"
        assert result_line_paths_parse(line) is None

    def test_old_dual_stream_host_only_returns_none(self):
        line = "[RESULT] host=/host_processed.mp4"
        assert result_line_paths_parse(line) is None

    def test_old_dual_stream_guest_only_returns_none(self):
        line = "[RESULT] guest=/guest_processed.mp4"
        assert result_line_paths_parse(line) is None

    def test_detail_line_returns_none(self):
        assert result_line_paths_parse('[DETAIL] 00:01:05 "uh" (confidence: 0.9500) muted') is None

    def test_run_complete_returns_none(self):
        assert result_line_paths_parse("[RUN COMPLETE] FULL_PIPELINE - Took 2m 3s") is None

    def test_function_start_returns_none(self):
        assert result_line_paths_parse("[FUNCTION START] Normalize Audio") is None


# ---------------------------------------------------------------------------
# result_line_paths_parse() — boundary / edge cases
# ---------------------------------------------------------------------------

class TestResultLinePathsParseEdgeCases:
    def test_result_prefix_case_sensitive(self):
        """[result] lowercase must not match — prefix check is case-sensitive."""
        assert result_line_paths_parse("[result] output=/path.mp4") is None

    def test_result_with_extra_leading_space_returns_none(self):
        """Line with leading space before [RESULT] must not match."""
        assert result_line_paths_parse(" [RESULT] output=/path.mp4") is None

    def test_result_with_tab_padding_returns_none(self):
        assert result_line_paths_parse("\t[RESULT] output=/path.mp4") is None
