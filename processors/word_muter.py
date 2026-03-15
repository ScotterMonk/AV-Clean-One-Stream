# processors/word_muter.py
#
# Translates FillerWordDetector results into per-track audio mute filters
# on the EditManifest.  Words are ALWAYS muted (never cut from the timeline).
#
# Confidence gating is performed upstream in FillerWordDetector before
# results reach this processor, so every segment received here is acted on.
#
# This processor does NOT touch removal_segments or compute_keep_segments.
# SegmentRemover is the sole owner of timeline cuts.

from .base_processor import BaseProcessor
from config import WORDS_TO_REMOVE
from core.interfaces import EditManifest
from utils.logger import get_logger, format_time_cut

logger = get_logger(__name__)


class WordMuter(BaseProcessor):
    """
    Reads filler_word_detector results and adds per-track FFmpeg volume=0
    filters to the EditManifest for every detected filler word.

    Words are always muted — never cut from the timeline. If a muted word
    is adjacent to natural silence, CrossTalkDetector may absorb it into a
    pause cut (self-healing). If not, the word remains as a silent gap.

    This processor does not sample cross-track audio; it only reads
    detection_results["filler_word_detector"] and writes audio filters.
    """

    def process(
        self, manifest: EditManifest, audio, detection_results
    ) -> EditManifest:
        # Mark that word-muting ran for this pipeline execution.
        manifest.word_mute_applied = True

        word_segments = detection_results.get("filler_word_detector", [])

        if not word_segments:
            logger.info("[WordMuter] No filler words detected -- nothing to mute.")
            return manifest

        mute_entries = []
        word_details = []

        for segment in word_segments:
            if isinstance(segment, dict):
                start_s = float(segment["start_sec"])
                end_s = float(segment["end_sec"])
                # Preserve action from detector (mute/skipped); default to "mute"
                # for pre-filtered data or legacy callers.
                action = str(segment.get("action") or "mute")
                detail = {
                    "track": str(segment.get("track") or ""),
                    "text": str(segment.get("text") or ""),
                    "start_sec": start_s,
                    "end_sec": end_s,
                    "confidence": float(segment.get("confidence", 0.0) or 0.0),
                    "action": action,
                    # Gap data from FillerWordDetector; None = no neighbour on that side.
                    # WordMuter uses these for pause-aware mute inset.
                    "prev_gap_ms": segment.get("prev_gap_ms"),
                    "next_gap_ms": segment.get("next_gap_ms"),
                }
                word_details.append(detail)

                # Only apply mute filter for words that passed confidence gating.
                if action == "mute":
                    self._word_mute_add(manifest, detail)
                    mute_entries.append((start_s, end_s))
            else:
                # Legacy tuple format — cannot determine track, log and skip filter.
                start_s, end_s = float(segment[0]), float(segment[1])
                logger.warning(
                    "[WordMuter] Received tuple-format segment %.3f-%.3fs with no track info; "
                    "skipping mute filter (use dict format from FillerWordDetector).",
                    start_s,
                    end_s,
                )

        sorted_mutes = sorted(mute_entries, key=lambda x: x[0])
        sorted_details = sorted(word_details, key=lambda x: x["start_sec"])

        # Store for logging in pipeline.py (includes both muted and skipped).
        manifest.word_mutes = list(sorted_mutes)
        manifest.word_mute_details = list(sorted_details)

        total_muted = sum(end - start for start, end in sorted_mutes)
        skipped_count = sum(1 for d in sorted_details if d["action"] == "skipped")
        logger.info(
            "[PROCESSOR COMPLETE] Muted %d filler word(s), skipped %d -- Total time muted: %s",
            len(sorted_mutes),
            skipped_count,
            format_time_cut(total_muted),
        )

        return manifest

    def _word_mute_add(self, manifest: EditManifest, detail: dict) -> None:
        """Add a single-track FFmpeg volume=0 filter for one filler-word span.

        Applies a pause-aware inset: if the gap between the filler word and an
        adjacent word is below filler_mute_gap_threshold_ms, the mute window is
        shrunk inward on that side by filler_mute_inset_ms to avoid silencing the
        edge phonemes of the neighbouring word (slurred/mushed speech).
        """
        start_s = float(detail["start_sec"])
        end_s = float(detail["end_sec"])

        # Read inset config (ms → seconds).
        inset_ms = float(WORDS_TO_REMOVE.get("filler_mute_inset_ms", 30))
        threshold_ms = float(WORDS_TO_REMOVE.get("filler_mute_gap_threshold_ms", 60))
        inset_s = inset_ms / 1000.0

        prev_gap_ms = detail.get("prev_gap_ms")
        next_gap_ms = detail.get("next_gap_ms")

        # Inset start when preceding word is slurred into the filler.
        if prev_gap_ms is not None and prev_gap_ms < threshold_ms:
            start_s += inset_s
            logger.debug(
                "[WordMuter] Slurred start: prev_gap=%.0fms < %.0fms → inset start +%.0fms",
                prev_gap_ms, threshold_ms, inset_ms,
            )

        # Inset end when following word is slurred out of the filler.
        if next_gap_ms is not None and next_gap_ms < threshold_ms:
            end_s -= inset_s
            logger.debug(
                "[WordMuter] Slurred end: next_gap=%.0fms < %.0fms → inset end -%.0fms",
                next_gap_ms, threshold_ms, inset_ms,
            )

        # Guard: if inset collapsed or inverted the window, revert to full extent.
        if start_s >= end_s:
            logger.warning(
                "[WordMuter] Inset collapsed mute window for %r at %.3f-%.3fs; "
                "reverting to full extent.",
                detail.get("text", ""), float(detail["start_sec"]), float(detail["end_sec"]),
            )
            start_s = float(detail["start_sec"])
            end_s = float(detail["end_sec"])

        enable_expr = f"between(t,{start_s:.3f},{end_s:.3f})"
        manifest.add_filter("volume", volume=0, enable=enable_expr)

    def get_name(self) -> str:
        return "WordMuter"
