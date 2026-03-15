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
    """Log per-word detail lines for each track using the shared formatter.

    Groups details by track (Host / Guest) and emits one [DETAIL] header
    followed by one line per word.  Identical format for both tracks.
    """
    if not word_mute_details:
        logger.info("[DETAIL] No filler words detected in either track.")
        return

    for label in ("Host", "Guest"):
        track_details = [
            d for d in word_mute_details
            if str(d.get("track") or "").lower() == label.lower()
        ]
        if not track_details:
            continue

        muted = sum(1 for d in track_details if d.get("action") == "mute")
        skipped = sum(1 for d in track_details if d.get("action") == "skipped")
        logger.info(
            "[DETAIL] %s filler words — %d found, %d muted, %d skipped:",
            label, len(track_details), muted, skipped,
        )
        for detail in track_details:
            logger.info("[DETAIL]   %s", _log_filler_word_line(detail))


def _log_filler_word_summary(manifest) -> None:
    """Log a per-track end-of-run filler word summary (after ALL processing completes).

    Emits one [RUN SUMMARY] line each for Host and Guest.
    Only emits when WordMuter ran and at least one track had words.
    """
    if not getattr(manifest, "word_mute_applied", False):
        return  # WordMuter didn't run — nothing to summarise

    details = getattr(manifest, "word_mute_details", []) or []

    for label in ("Host", "Guest"):
        track_details = [
            d for d in details
            if str(d.get("track") or "").lower() == label.lower()
        ]
        found = len(track_details)
        muted = sum(1 for d in track_details if d.get("action") == "mute")
        skipped = sum(1 for d in track_details if d.get("action") == "skipped")
        logger.info(
            "[RUN SUMMARY] %s filler words — found: %d, muted: %d, skipped: %d",
            label, found, muted, skipped,
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

    # Modified by gpt-5.4 | 2026-03-08
    def execute(
        self,
        host_video_path: str,
        guest_video_path: str,
        *,
        render_host: bool = True,
        render_guest: bool = True,
    ):
        logger.info("Phase 1: Extraction & Analysis")
        phase1_start = time.time()
         
        # 1. Extract Audio to RAM/Temp (Fast pydub loading)
        logger.info("[DETAIL] Extracting audio (host + guest)...")
        host_audio = audio_extractor.extract_audio(host_video_path)
        guest_audio = audio_extractor.extract_audio(guest_video_path)
         
        # 2. Run Detectors (Generate Detection Results)
        detection_results = {
            # Detectors can depend on input paths (ex: SpikeFixerDetector FFmpeg analysis).
            "host_video_path": host_video_path,
            "guest_video_path": guest_video_path,
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
                result = detector.detect(host_audio, guest_audio, detection_results)
            else:
                logger.debug("[DETECTOR] %s does not accept detection_results (legacy signature)", detector_name)
                result = detector.detect(host_audio, guest_audio)

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
                friendly = "Normalize Guest Audio"
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

            manifest = processor.process(manifest, host_audio, guest_audio, detection_results)

            # Capture elapsed time immediately after processor runs (before detail logging)
            elapsed = time.time() - (subfunction_start or 0.0) if friendly else None

            # Log [DETAIL] lines BEFORE [FUNCTION COMPLETE] so order is:
            #   [FUNCTION START] -> [DETAIL] -> [FUNCTION COMPLETE]
            if processor_name == "SegmentRemover":
                removals = getattr(manifest, "pause_removals", []) or []
                total_removed_seconds = sum(end - start for start, end in removals)
                logger.info(
                    f"[DETAIL] Removed {len(removals)} pause(s) from both Guest and Host videos | "
                    f"Total time removed: {format_time_cut(total_removed_seconds)}"
                )
            elif processor_name == "WordMuter":
                word_mute_details = getattr(manifest, "word_mute_details", []) or []
                _log_filler_word_details(word_mute_details)
            elif processor_name == "AudioNormalizer":
                gain_db = getattr(manifest, "guest_audio_gain_db_applied", None)
                gain_est_db = getattr(manifest, "guest_audio_gain_db_estimate", None)
                if gain_db is not None:
                    logger.info(f"[DETAIL] Guest audio adjusted: {gain_db:+.1f} dB")
                elif gain_est_db is not None:
                    logger.info(f"[DETAIL] Guest audio adjusted (estimated): {gain_est_db:+.1f} dB")
            elif processor_name == "SpikeFixer":
                spike_regions = detection_results.get("spike_fixer_detector", []) or []
                logger.info(f"[DETAIL] Fixed {len(spike_regions)} audio spike(s) in guest video")

            # Log [FUNCTION COMPLETE] AFTER all [DETAIL] lines
            if friendly and elapsed is not None:
                logger.info(f"[FUNCTION COMPLETE] {friendly} - Took {format_duration(elapsed)}")

        phase2_duration = time.time() - phase2_start
        logger.info(f"Phase 2 complete - Duration: {format_duration(phase2_duration)}")

        # 4. Render (FFmpeg Execution)
        logger.info("Phase 3: Rendering (This may take time)")
        phase3_start = time.time()
        # Output container is MP4 regardless of input container.
        host_out = make_processed_output_path(host_video_path) if render_host else None
        guest_out = make_processed_output_path(guest_video_path) if render_guest else None

        logger.info("[FUNCTION START] Render videos")
        video_renderer.render_project(
            host_video_path, guest_video_path,
            manifest,
            host_out, guest_out,
            self.config
        )

        phase3_duration = time.time() - phase3_start
        logger.info(f"[FUNCTION COMPLETE] Render videos - Took {format_duration(phase3_duration)}")
        logger.info(f"Phase 3 complete - Duration: {format_duration(phase3_duration)}")

        # ── End-of-run filler word summary ────────────────────────────────
        _log_filler_word_summary(manifest)

        return host_out, guest_out
