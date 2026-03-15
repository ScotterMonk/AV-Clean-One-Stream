"""FFmpeg progress line formatter for GUI console alignment."""

from __future__ import annotations

import re


def _format_cell(value: str, width: int) -> str:
    """Center-align a value inside a fixed-width column.

    Tkinter `Text` widgets preserve spaces, so monospaced + fixed width keeps
    header + data columns aligned.

    Note: Truncates if the value exceeds the column width.
    """

    s = str(value or "")
    if len(s) > width:
        return s[:width]
    return s.center(width)


def get_header_line() -> str:
    """Generate header line with same formatting as data lines.
    
    Returns:
        Formatted header string matching data column layout
    """
    return (
        f"{_format_cell('Frame', 12)}"  # Frame
        f"{_format_cell('FPS', 7)}"  # FPS
        f"{_format_cell('Qual', 8)}"  # Qual (Q)
        f"{_format_cell('Size', 10)}"  # Size
        f"{_format_cell('Progress', 10)}"  # Time
        f" "
        f"{_format_cell('Bitrate', 18)}"  # Bitrate
        f"{_format_cell('Speed', 8)}"  # Speed
        f" "
        f"{_format_cell('Elapsed', 10)}"  # Elapsed
    )


# Modified by gpt-5.2 | 2026-01-12_01
def _normalize_elapsed_value(raw_elapsed: str) -> str:
    """Normalize various elapsed representations into a compact time string.

    FFmpeg progress lines sometimes include a non-standard `elapsed=` field.
    When present, it may be either:
    - a timecode (e.g., "00:01:23.4")
    - seconds (e.g., "83.4")

    We normalize numeric seconds into "HH:MM:SS.S" (10 chars) to fit the GUI
    fixed-width column.
    """

    s = (raw_elapsed or "").strip()
    if not s:
        return ""
    if ":" in s:
        return s

    try:
        seconds = float(s)
    except ValueError:
        return s

    if seconds < 0:
        return ""

    total_seconds_int = int(seconds)
    hours = total_seconds_int // 3600
    minutes = (total_seconds_int % 3600) // 60
    sec_with_fraction = seconds % 60

    # Keep one decimal so the result remains 10 characters: HH:MM:SS.S
    sec_str = f"{sec_with_fraction:04.1f}"
    return f"{hours:02d}:{minutes:02d}:{sec_str}"


# Modified by gpt-5.2 | 2026-01-12_01
def format_ffmpeg_progress_line(line: str, show_every_nth: int = 2) -> tuple[str | None, bool]:
    """Parse and reformat FFmpeg progress line to align with header columns.
    
    Args:
        line: Raw FFmpeg output line
        show_every_nth: Only show every Nth progress line (1 = all, 2 = every other, etc.)
    
    Returns:
        Tuple of (formatted_line, is_progress_line)
        - formatted_line: Reformatted line if it's a progress line and should be shown, else original
        - is_progress_line: True if this was detected as an FFmpeg progress line
    
    FFmpeg progress typically looks like:
    frame= 2756 fps=444.94 q=14.0 size=79104kB time=00:01:54 bitrate=5649.3kbits/s speed=18.5x
    """
    # Check if this is an FFmpeg progress line (contains frame= and fps= keywords)
    if not ("frame=" in line and "fps=" in line):
        return line, False
    
    # Parse the line using regex to extract each field
    patterns = {
        "frame": r"frame=\s*(\d+)",
        "fps": r"fps=\s*([\d.]+)",
        "q": r"q=([\d.-]+)",  # Can be negative or have decimal
        "size": r"size=\s*(\d+\w+)",
        "time": r"time=\s*([\d:]+\.?\d*)",
        "bitrate": r"bitrate=\s*([\d.]+\w+/s)",
        "speed": r"speed=\s*([\d.]+x)",
        # Some pipelines append an explicit elapsed time; prefer it when present.
        "elapsed": r"elapsed=\s*([\d:]+\.?\d*|[\d.]+)",
    }
    
    values = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, line)
        if match:
            values[key] = match.group(1)
        else:
            values[key] = ""

    # Prefer explicit elapsed time when present; otherwise fall back to the timecode.
    elapsed_raw = values.get("elapsed") or values.get("time") or ""
    elapsed = _normalize_elapsed_value(elapsed_raw)
    
    # Format each field to match column widths from gui_pages.py headers:
    # OLD: Frame(9 left), FPS(8 right), Qual(8 right), Size(12 right),
    # Time(12 right), Bitrate(14 right), Speed(8 right), Elapsed(12 right)
    # NEW: all are centered
    # Add spacing between columns for better visual alignment
    
    formatted = (
        f"{_format_cell(values.get('frame', ''), 12)}"  # Frame
        f"{_format_cell(values.get('fps', ''), 10)}"  # FPS
        f"{_format_cell(values.get('q', ''), 10)}"  # Qual (Q)
        f"{_format_cell(values.get('size', ''), 10)}"  # Size
        f" "
        f"{_format_cell(values.get('time', ''), 10)}"  # Time
        f"{_format_cell(values.get('bitrate', ''), 18)}"  # Bitrate
        f"  "
        f"  "
        f"{_format_cell(values.get('speed', ''), 10)}"  # Speed
        f"{_format_cell(elapsed, 10)}"  # Elapsed
    )
    
    return formatted + '\n', True


# Track progress line counter for filtering
_progress_line_count = 0


def should_show_progress_line(show_every_nth: int = 2) -> bool:
    """Determine if current progress line should be shown based on counter.
    
    Args:
        show_every_nth: Show every Nth line (1=all, 2=every other)
    
    Returns:
        True if this line should be displayed
    """
    global _progress_line_count
    _progress_line_count += 1
    return (_progress_line_count % show_every_nth) == 0


def reset_progress_counter() -> None:
    """Reset the progress line counter (call when starting new process)."""
    global _progress_line_count
    _progress_line_count = 0
