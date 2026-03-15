"""Tests for GUI file metadata formatting helpers."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.gui_helpers import format_duration_display, format_size_mb


# Created by gpt-5.4 | 2026-03-07
def test_format_size_mb_uses_fixed_mb_units():
    assert format_size_mb(1572864) == "1.50 MB"


# Created by gpt-5.4 | 2026-03-07
def test_format_duration_display_formats_minutes_and_seconds():
    assert format_duration_display(125.4) == "02:05"


# Created by gpt-5.4 | 2026-03-07
def test_format_duration_display_formats_hours_when_needed():
    assert format_duration_display(3661) == "01:01:01"
