# utils/logger.py

import io
import logging
import sys
from typing import Optional

# Default log format: Time - Level - Message
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%H:%M:%S"


class _StrictStreamHandler(logging.StreamHandler):
    """StreamHandler that re-raises errors from emit() instead of swallowing them.

    Python's default StreamHandler.handleError() only prints a traceback
    to stderr and then continues, which can allow silent failures that are
    very hard to notice. This subclass re-raises so any logging infrastructure
    failure stops the process immediately.

    Unicode/encoding errors are pre-empted by _make_utf8_stdout(), which
    wraps the stream in UTF-8 + errors='replace'. Unrenderable characters
    become replacement markers ('?') rather than raising UnicodeEncodeError.
    """

    def handleError(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        _, exc_value, _ = sys.exc_info()
        if exc_value is not None:
            raise exc_value
        super().handleError(record)


def _make_utf8_stdout():
    """Return a UTF-8 text stream suitable for logging to stdout.

    On Windows where sys.stdout defaults to cp1252, this prevents
    UnicodeEncodeError when log messages contain non-cp1252 characters.
    Uses errors='replace' so unrenderable characters become '?' instead
    of crashing the logger.

    Falls back to the original sys.stdout if the buffer is not accessible
    (e.g., in some test harnesses that replace sys.stdout with a capture
    object that has no .buffer attribute).
    """
    # sys.stdout.buffer is available on real TTYs and subprocess pipes.
    if hasattr(sys.stdout, "buffer"):
        return io.TextIOWrapper(
            sys.stdout.buffer,
            encoding="utf-8",
            errors="replace",
            line_buffering=True,
        )
    # Fallback: try in-place reconfigure (Python 3.7+).
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # best-effort; original stdout stays
    return sys.stdout


def setup_logger(name: str = "video_trimmer", level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """
    Configures the root logger for the application.
    Should be called once at the start of main.py.

    Uses _StrictStreamHandler so any emit() failure stops the process,
    and _make_utf8_stdout() so Windows cp1252 encoding errors are
    pre-empted before they can reach the handler.
    
    Args:
        name: Name of the logger
        level: Logging level (logging.INFO, logging.DEBUG)
        log_file: Optional path to write logs to a file
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent adding handlers multiple times if setup is called twice
    if logger.hasHandlers():
        return logger

    # 1. Console Handler (Standard Output)
    # Wraps stdout in UTF-8 to prevent cp1252 UnicodeEncodeError on Windows.
    # _StrictStreamHandler re-raises any remaining emit() errors (no silent failures).
    console_handler = _StrictStreamHandler(_make_utf8_stdout())
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    logger.addHandler(console_handler)

    # 2. File Handler (Optional)
    if log_file:
        # Always write log files in UTF-8 regardless of system encoding.
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(file_handler)

    # Prevent propagation to root logger if using a named logger
    # (prevents logs appearing twice if other libraries use logging)
    logger.propagate = False

    return logger

def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger for a specific module.
    
    Usage in other files:
        from utils.logger import get_logger
        logger = get_logger(__name__)
    """
    # If the module name is 'core.pipeline', this creates 'video_trimmer.core.pipeline'
    # ensuring it inherits settings from the main 'video_trimmer' logger.
    parent_name = "video_trimmer"
    
    if name.startswith(parent_name):
        return logging.getLogger(name)
    
    return logging.getLogger(f"{parent_name}.{name}")


def format_duration(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.ms (milliseconds trimmed)."""
    sign = "-" if seconds < 0 else ""
    total_ms = int(round(abs(seconds) * 1000))

    total_seconds, ms = divmod(total_ms, 1000)
    hours, rem = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)

    ms_str = f"{ms:03d}".rstrip("0")
    if not ms_str:
        ms_str = "0"

    return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}.{ms_str}"


def format_time_cut(seconds: float) -> str:
    """Convert seconds to MM:SS or HH:MM:SS (rounded to nearest second)."""
    sign = "-" if seconds < 0 else ""
    total_seconds = int(round(abs(seconds)))

    hours, rem = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)

    if hours:
        return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{sign}{minutes:02d}:{secs:02d}"
