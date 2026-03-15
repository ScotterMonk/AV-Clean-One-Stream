# processors/audio_normalizer.py

from .base_processor import BaseProcessor
from utils.logger import get_logger

# Modified by gpt-5.2 | 2026-01-20_01
class AudioNormalizer(BaseProcessor):
    def process(self, manifest, audio, detection_results):
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

        # Note: audio param is intentionally unused here.
        # Normalization params are precomputed in AudioLevelDetector.
        # NOTE: MATCH_HOST normalization mode removed — single-stream workflow.

        lufs = audio_level_results.get("lufs")
        target_lufs = audio_level_results.get("target_lufs")
        loudnorm_params = audio_level_results.get("loudnorm_params")
        if lufs is None or target_lufs is None or not loudnorm_params:
            raise ValueError(
                "AudioNormalizer received incomplete audio_level_detector results. "
                "Expected keys: lufs, target_lufs, loudnorm_params."
            )

        logger.info(
            f"[PROCESSOR] Audio analysis: {lufs:.1f} LUFS"
        )

        logger.info(f"[PROCESSOR] Normalized audio — Target: {target_lufs} LUFS")
        # Estimate for summary logging (loudnorm is dynamic, so this is approximate)
        manifest.audio_gain_db_estimate = float(target_lufs - lufs)
        manifest.add_filter("loudnorm", **loudnorm_params)

        return manifest
    
    def get_name(self): return "AudioNormalizer"
