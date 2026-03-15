# core/interfaces.py

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Any

@dataclass
# Modified by gpt-5.4 | 2026-03-08
class AudioFilter:
    filter_name: str
    params: Dict[str, Any]

@dataclass
# Modified by gpt-5.4 | 2026-03-08
class EditManifest:
    """
    The recipe for the final video.

    Segment-removal pattern:
      1. Processors call add_removal(start, end) for each range to cut.
      2. Any processor that adds at least one removal then calls
         compute_keep_segments(total_duration) to (re)derive keep_segments
         from the full accumulated removal_segments list.
      3. Because every call to compute_keep_segments operates on the
         complete accumulator, processors may run in any order and each
         one's removals are automatically merged with prior removals.
    """
    # Time ranges (start, end) from the ORIGINAL file to keep.
    # If empty, the whole file is kept.
    # Derived by compute_keep_segments(); do NOT write directly.
    keep_segments: List[Tuple[float, float]] = field(default_factory=list)

    # ── Removal accumulator ────────────────────────────────────────────────
    # Raw "cut these spans" ranges — ALL processors append here.
    # keep_segments is always derived from this list via compute_keep_segments.
    removal_segments: List[Tuple[float, float]] = field(default_factory=list)

    # ── Pause-removal bookkeeping ──────────────────────────────────────────
    # Original-timeline segments removed by SegmentRemover (for logging).
    # Render logic MUST continue to rely on keep_segments only.
    pause_removals: List[Tuple[float, float]] = field(default_factory=list)

    # True when the pause-removal processor ran (even if zero pauses detected).
    pause_removal_applied: bool = False

    # ── Word-mute bookkeeping ──────────────────────────────────────────────
    # Original-timeline word spans muted by WordMuter (for duration logging).
    word_mutes: List[Tuple[float, float]] = field(default_factory=list)

    # Structured per-track word-mute details for GUI/console reporting.
    word_mute_details: List[Dict[str, Any]] = field(default_factory=list)

    # True when the word-mute processor ran (even if zero words detected).
    word_mute_applied: bool = False

    # ── Audio filters ──────────────────────────────────────────────────────
    # FFmpeg filters to apply to the Host Track
    host_filters: List[AudioFilter] = field(default_factory=list)

    # FFmpeg filters to apply to the Guest Track
    guest_filters: List[AudioFilter] = field(default_factory=list)

    # ── Helpers ────────────────────────────────────────────────────────────
    def add_host_filter(self, name, **kwargs):
        self.host_filters.append(AudioFilter(name, kwargs))

    def add_guest_filter(self, name, **kwargs):
        self.guest_filters.append(AudioFilter(name, kwargs))

    def add_removal(self, start: float, end: float) -> None:
        """Append a time range (seconds) to the shared removal accumulator."""
        self.removal_segments.append((start, end))

    def compute_keep_segments(self, total_duration: float) -> List[Tuple[float, float]]:
        """
        Derive keep_segments from the full accumulated removal_segments list.

        Handles overlapping/adjacent removals correctly via a sorted sweep.
        Stores the result in self.keep_segments and returns it.

        If removal_segments is empty, keep_segments is left unchanged
        (callers should guard with 'if removals' before invoking this).
        """
        if not self.removal_segments:
            return self.keep_segments

        keep: List[Tuple[float, float]] = []
        current = 0.0

        for start, end in sorted(self.removal_segments, key=lambda s: s[0]):
            if start > current:
                keep.append((current, start))
            # Advance past this removal, handling overlaps via max()
            current = max(current, end)

        # Capture anything after the last removal
        if current < total_duration:
            keep.append((current, total_duration))

        self.keep_segments = keep
        return keep
