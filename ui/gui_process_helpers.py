from __future__ import annotations

import re


# Modified by coder-sr | 2026-03-14 — retasked to filter only filler-word lines
def progress_line_mirror_should(line: str) -> bool:
    """Return True when a log line should appear in the FILLER WORDS FOUND pane.

    Only filler-word-related lines are mirrored; all other progress/action
    lines (FFmpeg, [ACTION START], [FUNCTION START], etc.) are excluded.
    """
    return filler_line_is_filler(line)


# coder-sr | 2026-03-12 — retained for backwards-compat; now a no-op
def progress_line_transform(line: str) -> str:
    """Formerly truncated per-word detail tails for the PROGRESS pane.

    Now a no-op: the FILLER WORDS FOUND pane displays full lines.
    Retained so any callers don't break on import.
    """
    return line


# Created by coder-sr | 2026-03-14
def filler_line_is_filler(line: str) -> bool:
    """Return True when a log line is filler-word related.

    Matches:
      - Summary/header lines that contain "filler word(s)" (pipeline + detector)
      - Upload status lines that contain "assemblyai"
      - Transcript completion lines that contain "transcript complete"
      - Per-word detail lines that contain "confidence:"
    """
    low = line.lower()
    return any(
        kw in low
        for kw in (
            "filler word",        # covers: "filler words", "filler word", "[RUN SUMMARY] Host filler words"
            "assemblyai",         # covers: "Uploading host/guest audio to AssemblyAI..."
            "transcript complete",# covers: "host/guest transcript complete — N word(s) received"
            "confidence:",        # covers: per-word lines "[DETAIL]   00:01:05 "uh" (confidence: 0.9500) — muted"
        )
    )


# Created by coder-sr | 2026-03-14
def filler_line_track_hint(line: str) -> str:
    """Return routing hint for a filler-word line.

    Returns:
        "host"    — line belongs to HOST sub-pane
        "guest"   — line belongs to GUEST sub-pane
        "both"    — line belongs in both sub-panes
        "context" — no explicit track; caller should use last-seen track state
                    (e.g. indented per-word lines like "  00:01:05 'uh' (confidence:...)")
    """
    low = line.lower()

    # "either track" lines go into both sub-panes
    if "either track" in low:
        return "both"

    has_host = "host" in low
    has_guest = "guest" in low

    if has_host and not has_guest:
        return "host"
    if has_guest and not has_host:
        return "guest"
    if has_host and has_guest:
        # Rare edge case — route to both sub-panes to be safe
        return "both"

    # No explicit track indicator (indented per-word detail lines)
    return "context"


# Created by gpt-5.4 | 2026-03-07
def result_line_paths_parse(line: str) -> tuple[str | None, str | None]:
    """Extract host and guest output paths from a [RESULT] line."""

    if not line.startswith("[RESULT]"):
        return None, None

    match = re.search(r"host=(.+?)\s+guest=(.+)$", line.strip())
    if match is None:
        return None, None

    return match.group(1).strip(), match.group(2).strip()
