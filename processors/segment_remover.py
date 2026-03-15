# processors/segment_remover.py

from .base_processor import BaseProcessor
from core.interfaces import EditManifest
from typing import List, Tuple

from utils.logger import get_logger
from utils.logger import format_time_cut
from utils.pause_removal_log import pause_removal_log_line


logger = get_logger(__name__)

class SegmentRemover(BaseProcessor):
    """
    Translates cross-talk / mutual-silence detections into removal ranges
    on the EditManifest.

    Uses the manifest's shared accumulator (add_removal + compute_keep_segments)
    so that any subsequent processor (e.g. WordMuter) can safely add its own
    removals and recompute keep_segments without clobbering these cuts.
    """

    def process(self, manifest: EditManifest, host_audio, guest_audio, detection_results) -> EditManifest:
        # 1. Get the list of "bad" segments (pauses / cross-talk) to remove.
        pauses = detection_results.get('cross_talk_detector', [])

        # Mark that pause-removal ran for this pipeline execution.
        manifest.pause_removal_applied = True

        # If no pauses detected, leave the manifest unchanged.
        if not pauses:
            return manifest

        sorted_pauses = sorted(pauses, key=lambda x: x[0])

        # Keep a copy for end-of-run summary + optional file log.
        manifest.pause_removals = list(sorted_pauses)

        # Log each removal against the original timeline.
        for start_s, end_s in sorted_pauses:
            logger.info(pause_removal_log_line(start_s, end_s))

        # 2. Accumulate removals into the shared manifest accumulator,
        #    then (re)derive keep_segments from the full removal list.
        for start_s, end_s in sorted_pauses:
            manifest.add_removal(start_s, end_s)

        total_duration = host_audio.duration_seconds
        manifest.compute_keep_segments(total_duration)

        total_removed = sum(end - start for start, end in sorted_pauses)
        logger.info(
            f"[PROCESSOR COMPLETE] Cut {len(sorted_pauses)} pauses from both videos (sync-safe)"
            f" - Total time cut: {format_time_cut(total_removed)}"
        )

        return manifest

    def get_name(self) -> str:
        return "SegmentRemover"
