# utils/audio_helpers.py
#
# Shared audio manipulation utilities used across detectors and processors.

from typing import List, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


def audio_apply_mutes(audio, mute_ranges: List[Tuple[float, float]]):
    """
    Return a copy of `audio` with all time ranges in `mute_ranges` replaced
    by silence of equal duration.

    Uses an O(N) single-pass approach:
      1. Sort mute ranges by start time.
      2. Walk through ranges, collecting kept chunks and silent chunks.
      3. Concatenate all chunks into a new AudioSegment.

    The original `audio` object is NOT modified (local copy only).

    Args:
        audio:       pydub AudioSegment to process.
        mute_ranges: List of (start_sec, end_sec) tuples to silence.

    Returns:
        New AudioSegment with muted ranges replaced by silence.
        Returns `audio` unchanged if `mute_ranges` is empty.
    """
    if not mute_ranges:
        return audio

    from pydub import AudioSegment

    sorted_mutes = sorted(mute_ranges, key=lambda r: r[0])
    chunks = []
    pos_ms = 0
    total_ms = len(audio)

    for start_s, end_s in sorted_mutes:
        start_ms = int(start_s * 1000)
        end_ms = int(end_s * 1000)

        # Clamp to audio bounds and skip zero-length or backwards ranges.
        start_ms = max(pos_ms, min(start_ms, total_ms))
        end_ms = max(start_ms, min(end_ms, total_ms))

        # Keep the chunk before this mute range.
        if start_ms > pos_ms:
            chunks.append(audio[pos_ms:start_ms])

        # Replace muted range with silence of equal duration.
        duration_ms = end_ms - start_ms
        if duration_ms > 0:
            silence = AudioSegment.silent(
                duration=duration_ms,
                frame_rate=audio.frame_rate,
            )
            silence = silence.set_channels(audio.channels)
            silence = silence.set_sample_width(audio.sample_width)
            chunks.append(silence)

        pos_ms = end_ms

    # Append the remainder after the last mute range.
    if pos_ms < total_ms:
        chunks.append(audio[pos_ms:])

    if not chunks:
        return audio

    result = chunks[0]
    for chunk in chunks[1:]:
        result = result + chunk

    logger.debug(
        "[audio_apply_mutes] Applied %d mute range(s) to audio (%.1fs total)",
        len(sorted_mutes),
        total_ms / 1000.0,
    )
    return result
