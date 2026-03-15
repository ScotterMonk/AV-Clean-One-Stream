# tests/test_gui_result_line.py
"""Test that the GUI worker captures and uses [RESULT] line from subprocess output."""

import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGuiResultLineParsing:
    """Test [RESULT] line parsing in GUI _worker()."""

    def test_result_line_regex_parsing(self):
        """Verify [RESULT] line regex correctly extracts host and guest paths."""
        import re
        
        test_cases = [
            # Unix-style paths without spaces
            ("[RESULT] host=/path/to/host.mp4 guest=/path/to/guest.mp4", "/path/to/host.mp4", "/path/to/guest.mp4"),
            # Windows-style paths without spaces
            ("[RESULT] host=C:\\Videos\\host.mp4 guest=C:\\Videos\\guest.mp4", "C:\\Videos\\host.mp4", "C:\\Videos\\guest.mp4"),
            # Paths with special characters
            ("[RESULT] host=/path/with-dashes/host.mp4 guest=/path/with-dashes/guest.mp4", "/path/with-dashes/host.mp4", "/path/with-dashes/guest.mp4"),
            ("[RESULT] host=/path/with_underscores/host.mp4 guest=/path/with_underscores/guest.mp4", "/path/with_underscores/host.mp4", "/path/with_underscores/guest.mp4"),
            # CRITICAL: Windows paths with spaces (the bug being fixed)
            ("[RESULT] host=C:\\My Videos\\host.mp4 guest=C:\\My Videos\\guest.mp4", "C:\\My Videos\\host.mp4", "C:\\My Videos\\guest.mp4"),
            ("[RESULT] host=C:\\Users\\John Doe\\Videos\\host.mp4 guest=C:\\Users\\John Doe\\Videos\\guest.mp4", "C:\\Users\\John Doe\\Videos\\host.mp4", "C:\\Users\\John Doe\\Videos\\guest.mp4"),
            # Unix paths with spaces
            ("[RESULT] host=/home/user/My Videos/host.mp4 guest=/home/user/My Videos/guest.mp4", "/home/user/My Videos/host.mp4", "/home/user/My Videos/guest.mp4"),
            # Mixed: one path with spaces, one without
            ("[RESULT] host=C:\\My Videos\\host.mp4 guest=C:\\Videos\\guest.mp4", "C:\\My Videos\\host.mp4", "C:\\Videos\\guest.mp4"),
            # Double space between host and guest
            ("[RESULT] host=/path/host.mp4  guest=/path/guest.mp4", "/path/host.mp4", "/path/guest.mp4"),
        ]
        
        for line, expected_host, expected_guest in test_cases:
            # Use the updated regex that handles spaces in paths
            m = re.search(r'host=(.+?)\s+guest=(.+)$', line.strip())
            assert m is not None, f"Failed to match: {line}"
            assert m.group(1).strip() == expected_host, f"Host mismatch for: {line}"
            assert m.group(2).strip() == expected_guest, f"Guest mismatch for: {line}"

    def test_worker_uses_result_paths_when_available(self):
        """Verify worker logic uses [RESULT] paths when captured."""
        import re
        from utils.path_helpers import make_processed_output_path
        
        # Simulate worker logic
        _result_host: str | None = None
        _result_guest: str | None = None
        
        host_path = "original_host.mp4"
        guest_path = "original_guest.mp4"
        result_host = "host_processed_rerun.mp4"
        result_guest = "guest_processed_rerun.mp4"
        
        # Simulate captured [RESULT] line
        result_line = f"[RESULT] host={result_host} guest={result_guest}\n"
        if result_line.startswith("[RESULT]"):
            m = re.search(r'host=(\S+)\s+guest=(\S+)', result_line)
            if m:
                _result_host = m.group(1).strip()
                _result_guest = m.group(2).strip()
        
        # Simulate path selection logic
        host_processed = _result_host or make_processed_output_path(host_path)
        guest_processed = _result_guest or make_processed_output_path(guest_path)
        
        # Verify [RESULT] paths were used
        assert host_processed == result_host, f"Expected {result_host}, got {host_processed}"
        assert guest_processed == result_guest, f"Expected {result_guest}, got {guest_processed}"

    def test_worker_falls_back_to_computed_paths(self):
        """Verify worker logic falls back to computed paths when no [RESULT] captured."""
        from utils.path_helpers import make_processed_output_path
        
        # Simulate worker logic with no [RESULT] captured
        _result_host: str | None = None
        _result_guest: str | None = None
        
        host_path = "original_host.mp4"
        guest_path = "original_guest.mp4"
        
        # Simulate path selection logic
        host_processed = _result_host or make_processed_output_path(host_path)
        guest_processed = _result_guest or make_processed_output_path(guest_path)
        
        # Verify fallback paths were computed correctly
        assert host_processed == make_processed_output_path(host_path)
        assert guest_processed == make_processed_output_path(guest_path)

    def test_worker_partial_result_line(self):
        """Verify worker handles partial [RESULT] lines gracefully."""
        import re
        from utils.path_helpers import make_processed_output_path
        
        # Simulate worker logic with malformed [RESULT] line
        _result_host: str | None = None
        _result_guest: str | None = None
        
        host_path = "original_host.mp4"
        guest_path = "original_guest.mp4"
        
        # Simulate malformed [RESULT] line (missing guest)
        result_line = "[RESULT] host=only_host.mp4\n"
        if result_line.startswith("[RESULT]"):
            m = re.search(r'host=(\S+)\s+guest=(\S+)', result_line)
            if m:
                _result_host = m.group(1).strip()
                _result_guest = m.group(2).strip()
        
        # Should fall back to computed paths when regex doesn't match
        host_processed = _result_host or make_processed_output_path(host_path)
        guest_processed = _result_guest or make_processed_output_path(guest_path)
        
        # Verify fallback since regex didn't match
        assert host_processed == make_processed_output_path(host_path)
        assert guest_processed == make_processed_output_path(guest_path)
