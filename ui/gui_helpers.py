from __future__ import annotations

from dataclasses import dataclass

import tkinter as tk

from io_.media_probe import get_video_duration_seconds as _get_video_duration_seconds


# Modified by gpt-5.4 | 2026-03-07
@dataclass
class FileRowState:
    path: str | None
    file_var: tk.StringVar
    size_var: tk.StringVar
    length_var: tk.StringVar
    play_btn: tk.Widget | None = None


# Created by gpt-5.4 | 2026-03-07
def format_size_mb(num_bytes: int) -> str:
    """Format bytes as megabytes with a fixed MB suffix."""

    if num_bytes < 0:
        return ""

    size_mb = num_bytes / (1024.0 * 1024.0)
    return f"{size_mb:.2f} MB"


def format_bytes(num_bytes: int) -> str:
    """Format bytes as a compact human-readable string."""

    if num_bytes < 0:
        return ""

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


# Created by gpt-5.4 | 2026-03-07
def format_duration_display(duration_seconds: float) -> str:
    """Format seconds as HH:MM:SS or MM:SS for the GUI."""

    if duration_seconds <= 0:
        return ""

    total_seconds = int(round(duration_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def get_video_duration_seconds(video_path: str) -> float:
    # Modified by gpt-5.2 | 2026-01-13_01
    """Return video duration in seconds using ffprobe via ffmpeg-python."""

    # Delegate to the shared, non-UI duration helper so CLI + GUI stay consistent.
    # Keep the GUI API stable (callers expect this function name) and preserve
    # the prior behavior of returning 0.0 on errors.
    try:
        return float(_get_video_duration_seconds(video_path))
    except Exception:
        return 0.0

