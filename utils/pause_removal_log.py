"""utils/pause_removal_log.py

Pause-removal logging helpers.

The app prints pause removals to the console during processing, and (optionally)
writes a text log into the same folder as the input videos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence, Tuple

from utils.time_helpers import seconds_to_hms


def seconds_to_hms_no_ms(seconds: float) -> str:
    """Format seconds into HH:MM:SS (drops milliseconds)."""

    # seconds_to_hms returns HH:MM:SS.mmm
    return seconds_to_hms(seconds).split(".", 1)[0]


def pause_removal_log_line(start_s: float, end_s: float) -> str:
    """Return the canonical pause-removal log line."""

    start = seconds_to_hms_no_ms(start_s)
    end = seconds_to_hms_no_ms(end_s)
    return f"pause rem-{start}-to-{end}"


def pause_removal_log_write(
    project_dir: str | Path,
    removals: Sequence[Tuple[float, float]],
    *,
    now: datetime | None = None,
) -> str | None:
    """Write a pause-removal log file.

    Returns:
        The created log path as a string, or None when no removals.
    """

    if not removals:
        return None

    dt = now or datetime.now()
    filename = f"{dt.date().isoformat()}-pauses-rem-log.txt"
    out_path = Path(project_dir) / filename

    lines = [pause_removal_log_line(s, e) for s, e in removals]
    lines.append(f"{len(removals)} pauses removed")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out_path)

