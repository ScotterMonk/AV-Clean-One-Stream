# core/pipeline.py

import inspect
import time

from .interfaces import EditManifest
from io_ import audio_extractor
from io_ import video_renderer
from utils.path_helpers import make_processed_output_path
from utils.logger import get_logger, format_duration, format_time_cut
from utils.time_helpers import seconds_to_hms

from pathlib import Path

logger = get_logger(__name__)


# Modified by gpt-5.4 | 2026-03-15
def _log_filler_word_line(detail: dict) -> str:
    """Format a single filler-word detail into a consistent log line.

    Returns a string like:  00:01:05 "uh" (confidence: 0.9500) muted
    Used by both host and guest logging so the format is identical.
    """
    timestamp = seconds_to_hms(float(detail["start_sec"])).split(".", 1)[0]
    word = str(detail.get("text") or "").strip()
    confidence = float(detail.get("confidence", 0.0) or 0.0)
    action = str(detail.get("action") or "mute").strip().lower()
    if action == "mute":
        action = "muted"
    return f'{timestamp} "{word}" (confidence: {confidence:.4f}) {action}'


def _log_filler_word_details(word_mute_details: list) -> None:
    """Log per-word detail lines as a single combined block.

    Emits one [DETAIL] header followed by one line per word across all tracks.
    """
    if not word_mute_details:
        logger.info("[DETAIL] No filler words detected.")
        return

    muted = sum(1 for d in word_mute_details if d.get("action") == "mute")
    skipped = sum(1 for d in word_mute_details if d.get("action") == "skipped")
    logger.info(
        "[DETAIL] Filler words — %d found, %d muted, %d skipped:",
        len(word_mute_details), muted, skipped,
    )
    for detail in word_mute_details:
        logger.info("[DETAIL]   %s", _log_filler_word_line(detail))


def _log_filler_word_summary(manifest) -> None:
    """Log a single end-of-run filler word summary (after ALL processing completes).

    Emits one [RUN SUMMARY] line combining all details.
    Only emits when WordMuter ran and at least one word was found.
    """
    if not getattr(manifest, "word_mute_applied", False):
        return  # WordMuter didn't run — nothing to summarise

    details = getattr(manifest, "word_mute_details", []) or []
    found = len(details)
    muted = sum(1 for d in details if d.get("action") == "mute")
    skipped = sum(1 for d in details if d.get("action") == "skipped")
    logger.info(
        "[RUN SUMMARY] Filler words — found: %d, muted: %d, skipped: %d",
        found, muted, skipped,
    )


class ProcessingPipeline:
    def __init__(self, config):
        self.config = config
        self.detectors = []
        self.processors = []

    def add_detector(self, detector):
        self.detectors.append(detector)
        return self

    def add_processor(self, processor):
        self.processors.append(processor)
        return self

    def execute(self, video_path: str, *, render: bool = True) -> "str | None":
        """Run the full detection → manifest → render pipeline for a single input.

        Args:
            video_path: Path to the input video file.
            render:     When False the manifest is built but no output file is written.

        Returns:
            Path to the rendered output file, or None when render=False.
        """
        logger.info("Phase 1: Extraction & Analysis")
        phase1_start = time.time()

        # 1. Extract Audio to RAM/Temp (Fast pydub loading)
        logger.info("[DETAIL] Extracting audio...")
        audio = audio_extractor.extract_audio(video_path)

        # 2. Run Detectors (Generate Detection Results)
        detection_results = {
            # Detectors can depend on the input path (ex: SpikeFixerDetector FFmpeg pass).
            "video_path": video_path,
        }

        detector_names = [d.get_name() for d in self.detectors]
        logger.info("[DETECTOR] Execution order: %s", " -> ".join(detector_names) if detector_names else "(none)")

        for idx, detector in enumerate(self.detectors):
            detector_name = detector.get_name()
            logger.info("[DETAIL] Detector %s/%s: %s", idx + 1, len(self.detectors), detector_name)

            # Dependency/ordering logging: what is available to this detector right now.
            available_keys = sorted(detection_results.keys())
            logger.debug(
                "[DETECTOR] %s starting; available prior results: %s",
                detector_name,
                ", ".join(available_keys) if available_keys else "(none)",
            )

            # Pass accumulated detection_results when the detector supports it.
            supports_detection_results = False
            try:
                sig = inspect.signature(detector.detect)
                params = list(sig.parameters.values())
                supports_detection_results = any(
                    (p.kind == inspect.Parameter.VAR_KEYWORD) or (p.name == "detection_results")
                    for p in params
                )
            except Exception:
                # If introspection fails, stay conservative and call the legacy 2-arg signature.
                supports_detection_results = False

            if supports_detection_results:
                logger.debug("[DETECTOR] %s will receive accumulated detection_results", detector_name)
                result = detector.detect(audio, detection_results)
            else:
                logger.debug("[DETECTOR] %s does not accept detection_results (legacy signature)", detector_name)
                result = detector.detect(audio)

            detection_results[detector_name] = result

        phase1_duration = time.time() - phase1_start
        logger.info(f"Phase 1 complete - Duration: {format_duration(phase1_duration)}")

        # 3. Run Processors (Build the Manifest)
        logger.info("Phase 2: Building Edit Manifest")
        phase2_start = time.time()
        manifest = EditManifest()
         
        for processor in self.processors:
            processor_name = str(processor.get_name())
            logger.info(f"Running {processor_name}...")

            # Mirror user-facing function start/end markers.
            # These are used by the GUI PROGRESS pane to show an action-style timeline.
            friendly = None
            completion_details = None
            subfunction_start = None

            if processor_name == "AudioNormalizer":
                friendly = "Normalize Audio"
            elif processor_name == "SegmentRemover":
                friendly = "Remove pauses"
            elif processor_name == "WordMuter":
                friendly = "Mute filler words"
            elif processor_name == "SpikeFixer":
                # Keep user-facing title stable; report spike count after completion.
                friendly = "Remove audio spikes"

            if friendly:
                logger.info(f"[FUNCTION START] {friendly}")
                subfunction_start = time.time()

            manifest = processor.process(manifest, audio, detection_results)

            # Capture elapsed time immediately after processor runs (before detail logging)
            elapsed = time.time() - (subfunction_start or 0.0) if friendly else None

            # Log [DETAIL] lines BEFORE [FUNCTION COMPLETE] so order is:
            #   [FUNCTION START] -> [DETAIL] -> [FUNCTION COMPLETE]
            if processor_name == "SegmentRemover":
                removals = getattr(manifest, "pause_removals", []) or []
                total_removed_seconds = sum(end - start for start, end in removals)
                logger.info(
                    f"[DETAIL] Removed {len(removals)} pause(s) | "
                    f"Total time removed: {format_time_cut(total_removed_seconds)}"
                )
            elif processor_name == "WordMuter":
                word_mute_details = getattr(manifest, "word_mute_details", []) or []
                _log_filler_word_details(word_mute_details)
            elif processor_name == "AudioNormalizer":
                gain_est_db = getattr(manifest, "audio_gain_db_estimate", None)
                if gain_est_db is not None:
                    logger.info(f"[DETAIL] Audio adjusted (estimated): {gain_est_db:+.1f} dB")
            elif processor_name == "SpikeFixer":
                spike_regions = detection_results.get("spike_fixer_detector", []) or []
                logger.info(f"[DETAIL] Fixed {len(spike_regions)} audio spike(s)")

            # Log [FUNCTION COMPLETE] AFTER all [DETAIL] lines
            if friendly and elapsed is not None:
                logger.info(f"[FUNCTION COMPLETE] {friendly} - Took {format_duration(elapsed)}")

        phase2_duration = time.time() - phase2_start
        logger.info(f"Phase 2 complete - Duration: {format_duration(phase2_duration)}")

        # 4. Render (FFmpeg Execution)
        logger.info("Phase 3: Rendering (This may take time)")
        phase3_start = time.time()
        # Output container is MP4 regardless of input container.
        out = make_processed_output_path(video_path) if render else None

        logger.info("[FUNCTION START] Render videos")
        video_renderer.render_project(video_path, manifest, out, self.config)

        phase3_duration = time.time() - phase3_start
        logger.info(f"[FUNCTION COMPLETE] Render videos - Took {format_duration(phase3_duration)}")
        logger.info(f"Phase 3 complete - Duration: {format_duration(phase3_duration)}")

        # ── End-of-run filler word summary ────────────────────────────────
        _log_filler_word_summary(manifest)

        return out
