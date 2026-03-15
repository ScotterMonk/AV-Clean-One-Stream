# processors/audio_normalizer.py

from .base_processor import BaseProcessor
from utils.logger import get_logger

# Modified by gpt-5.2 | 2026-01-20_01
class AudioNormalizer(BaseProcessor):
    def process(self, manifest, host_audio, guest_audio, detection_results):
        logger = get_logger(__name__)
        if not detection_results:
            raise ValueError(
                "AudioNormalizer requires detection_results, but none were provided. "
                "Expected detection_results['audio_level_detector'] from AudioLevelDetector."
            )

        audio_level_results = detection_results.get("audio_level_detector")
        if not audio_level_results:
            raise ValueError(
                "AudioNormalizer missing required detection results: detection_results['audio_level_detector']. "
                "Ensure AudioLevelDetector runs before AudioNormalizer."
            )

        # Note: host_audio/guest_audio are intentionally unused here.
        # Normalization params are precomputed in AudioLevelDetector.

        mode = audio_level_results.get("mode")
        host_lufs = audio_level_results.get("host_lufs")
        guest_lufs = audio_level_results.get("guest_lufs")
        if mode is None or host_lufs is None or guest_lufs is None:
            raise ValueError(
                "AudioNormalizer received incomplete audio_level_detector results. "
                "Expected keys: mode, host_lufs, guest_lufs."
            )

        logger.info(
            f"[PROCESSOR] Audio analysis - Host: {host_lufs:.1f} LUFS, Guest: {guest_lufs:.1f} LUFS"
        )

        if mode == "MATCH_HOST":
            guest_gain_db = audio_level_results.get("guest_gain_db")
            if guest_gain_db is None:
                raise ValueError(
                    "AudioNormalizer missing required key in audio_level_detector results: guest_gain_db "
                    "(required for MATCH_HOST)."
                )

            logger.info(
                f"[PROCESSOR] Normalized guest audio - Applied {guest_gain_db:+.1f} dB gain to match host"
            )

            # Used by the pipeline for end-of-subfunction summary logging.
            manifest.guest_audio_gain_db_applied = float(guest_gain_db)

            # Host gets NO filter (it is the reference)
            # Guest gets volume filter
            manifest.add_guest_filter("volume", volume=f"{guest_gain_db}dB")

        elif mode == "STANDARD_LUFS":
            target_lufs = audio_level_results.get("target_lufs")
            loudnorm_params = audio_level_results.get("loudnorm_params")
            if target_lufs is None or not loudnorm_params:
                raise ValueError(
                    "AudioNormalizer missing required keys in audio_level_detector results for STANDARD_LUFS: "
                    "target_lufs and loudnorm_params."
                )

            logger.info(
                f"[PROCESSOR] Normalized both tracks - Target: {target_lufs} LUFS (STANDARD_LUFS mode)"
            )

            # Loudnorm is dynamic; keep an estimate for summary logging.
            manifest.guest_audio_gain_db_estimate = float(target_lufs - guest_lufs)

            # Apply identical loudnorm to BOTH (params computed during detection)
            manifest.add_host_filter("loudnorm", **loudnorm_params)
            manifest.add_guest_filter("loudnorm", **loudnorm_params)

        else:
            raise ValueError(
                f"AudioNormalizer received unsupported normalization mode from audio_level_detector: {mode!r}"
            )

        return manifest
    
    def get_name(self): return "AudioNormalizer"
