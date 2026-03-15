# detectors/audio_level_detector.py

from typing import Any, Dict

from analyzers.audio_level_analyzer import calculate_lufs
from analyzers.normalization_calculator import (
    normalization_gain_match_host,
    normalization_params_standard_lufs,
)
from detectors.base_detector import BaseDetector
from utils.logger import get_logger


class AudioLevelDetector(BaseDetector):
    # Created by gpt-5.2 | 2026-01-20_01
    """Calculate LUFS and normalization parameters for downstream detectors/processors.

    This detector does not produce cut regions. Instead it returns a dict that will be
    stored in `detection_results["audio_level_detector"]`.
    """

    # Created by gpt-5.2 | 2026-01-20_01
    def detect(self, host_audio, guest_audio) -> Dict[str, Any]:
        # Created by gpt-5.2 | 2026-01-20_01
        logger = get_logger(__name__)

        host_lufs = float(calculate_lufs(host_audio))
        guest_lufs = float(calculate_lufs(guest_audio))

        logger.info(
            "[DETECTOR] AudioLevelDetector LUFS - Host: %.1f LUFS, Guest: %.1f LUFS",
            host_lufs,
            guest_lufs,
        )

        config = (self.config or {}).get("normalization", {})
        mode = str(config.get("mode", "MATCH_HOST"))

        if mode == "MATCH_HOST":
            max_gain_db = float(config.get("max_gain_db", 15.0))
            guest_gain_db = float(normalization_gain_match_host(host_lufs, guest_lufs, max_gain_db))

            return {
                "mode": mode,
                "host_lufs": host_lufs,
                "guest_lufs": guest_lufs,
                "guest_gain_db": guest_gain_db,
            }

        if mode == "STANDARD_LUFS":
            target_lufs = float(config.get("standard_target", -16.0))
            loudnorm_params = normalization_params_standard_lufs(target_lufs, -1.5, 11)

            return {
                "mode": mode,
                "host_lufs": host_lufs,
                "guest_lufs": guest_lufs,
                "target_lufs": target_lufs,
                "loudnorm_params": loudnorm_params,
            }

        raise ValueError(f"Unknown normalization mode: {mode}")

    def get_name(self) -> str:
        # Created by gpt-5.2 | 2026-01-20_01
        return "audio_level_detector"

