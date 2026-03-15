# detectors/cross_talk_detector.py
#
# NOTE: This file keeps its historical name "cross_talk_detector" for registry
# compatibility. The detector key returned by get_name() ("cross_talk_detector")
# is referenced by the pipeline and processors. Do NOT rename this file, class,
# or registry key without coordinated updates to: core/pipeline.py, config.py,
# and any processor that reads detection_results["cross_talk_detector"].

from .base_detector import BaseDetector
from analyzers.audio_envelope import calculate_db_envelope
from typing import List, Tuple


class CrossTalkDetector(BaseDetector):
    """
    Detects pauses in a single audio stream that exceed `max_pause_duration`.

    Formerly used dual-track mutual-silence logic; now operates on a single
    audio input. Pauses longer than `max_pause_duration` are trimmed so only
    `new_pause_duration` seconds remain.

    Self-healing: filler-word mute ranges from detection_results are applied
    to a local copy of the audio before analysis, so that a muted word
    adjacent to natural silence is correctly absorbed into the pause region.
    The shared audio object passed by the pipeline is NOT modified.
    """

    def detect(self, audio, detection_results=None) -> List[Tuple[float, float]]:
        """
        Detect silence regions that exceed `max_pause_duration`.

        For each detected pause region (start..end), we *replace the entire pause*
        with a fixed-length pause of `new_pause_duration` by removing only the
        *excess* beyond `new_pause_duration`.

        Example: 5-second pause with max_pause_duration=1.2s and new_pause_duration=0.5s
          - Detected: 0.0 to 5.0 (5s total)
          - Returned: 0.5 to 5.0 (4.5s to remove, keeps 0.5s replacement pause)
        """
        from utils.logger import format_time_cut, get_logger
        logger = get_logger(__name__)

        # Self-healing: apply in-memory filler-word mutes so that a muted word
        # adjacent to natural silence expands the silence zone during analysis.
        # The shared audio object passed by the pipeline is NOT modified.
        filler_results = (detection_results or {}).get("filler_word_detector", [])
        if filler_results:
            from utils.audio_helpers import audio_apply_mutes

            mute_ranges = [
                (seg["start_sec"], seg["end_sec"])
                for seg in filler_results
                if isinstance(seg, dict)
            ]
            if mute_ranges:
                audio = audio_apply_mutes(audio, mute_ranges)
                logger.debug(
                    "[CrossTalkDetector] Applied %d filler-word mute(s) to local copy for analysis",
                    len(mute_ranges),
                )

        threshold_db = self.config.get("silence_threshold_db", -45)
        max_pause_duration = self.config.get("max_pause_duration", 2.5)
        new_pause_duration = self.config.get("new_pause_duration", 0.5)
        window_ms = self.config.get("silence_window_ms", 100)

        # Safety clamps:
        # - new_pause_duration cannot be negative.
        # - If new_pause_duration is longer than the detected pause, we remove nothing.
        try:
            new_pause_duration = max(0.0, float(new_pause_duration))
        except (TypeError, ValueError):
            new_pause_duration = 0.5

        logger.info(
            "CrossTalkDetector config: threshold=%sdB, max_pause_duration=%ss, new_pause_duration=%ss, window=%sms",
            threshold_db,
            max_pause_duration,
            new_pause_duration,
            window_ms,
        )

        # Step 1: Calculate dB envelope for the single audio track
        db_levels = calculate_db_envelope(audio, window_ms)

        # Step 2: Identify silent frames
        is_silent = db_levels < threshold_db

        # Step 3: Find continuous silence regions exceeding max_pause_duration
        silence_regions = self._find_continuous_regions(
            is_silent,
            max_pause_duration,
            audio.frame_rate,
            window_ms,
        )

        # Step 4: Verify each region and remove only the portion beyond new_pause_duration
        verified_regions = []
        for start, end in silence_regions:
            if self._verify_silence(audio, start, end, threshold_db):
                # Replace the entire pause with `new_pause_duration`.
                # Keep the first `new_pause_duration` seconds; remove the remainder.
                keep_len = min(new_pause_duration, max(0.0, end - start))
                trimmed_start = start + keep_len
                if trimmed_start < end:
                    verified_regions.append((trimmed_start, end))
                    logger.debug(
                        "Detected pause %.2fs to %.2fs (duration=%.2fs) -> removing %.2fs to %.2fs (excess=%.2fs)",
                        start,
                        end,
                        (end - start),
                        trimmed_start,
                        end,
                        (end - trimmed_start),
                    )

        total_seconds = sum(end - start for start, end in verified_regions)
        logger.info(
            "[DETECTOR] Found %s pauses (total duration: %s to remove)",
            len(verified_regions),
            format_time_cut(total_seconds),
        )
        return verified_regions

    def _find_continuous_regions(self, mask, min_duration, sample_rate, window_ms):
        """Find continuous True regions in boolean mask that meet min_duration."""
        regions = []
        start = None

        for i, is_silent in enumerate(mask):
            if is_silent and start is None:
                start = i
            elif not is_silent and start is not None:
                duration = (i - start) * window_ms / 1000
                if duration >= min_duration:
                    start_time = start * window_ms / 1000
                    end_time = i * window_ms / 1000
                    regions.append((start_time, end_time))
                start = None

        # Handle case where silence extends to end of audio
        if start is not None:
            duration = (len(mask) - start) * window_ms / 1000
            if duration >= min_duration:
                start_time = start * window_ms / 1000
                end_time = len(mask) * window_ms / 1000
                regions.append((start_time, end_time))

        return regions

    def _verify_silence(self, audio, start, end, threshold_db):
        """
        Quality gate: confirm a detected region is genuinely silent.

        Uses RMS-based dBFS (pydub AudioSegment.dBFS) — NOT max_dBFS (peak).
        Reason: the envelope detector uses windowed RMS via calculate_db_envelope(),
        so we stay consistent here. RMS averages energy across the whole segment,
        preventing false rejections from brief noise clicks in otherwise silent pauses.
        """
        segment = audio[int(start * 1000):int(end * 1000)]
        rms = segment.dBFS if len(segment) > 0 else -100
        return rms < threshold_db

    def get_name(self) -> str:
        return "cross_talk_detector"
