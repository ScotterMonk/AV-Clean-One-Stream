# detectors/audio_level_detector.py

from typing import Any, Dict

from analyzers.audio_level_analyzer import calculate_lufs
from analyzers.normalization_calculator import (
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
    def detect(self, audio) -> Dict[str, Any]:
        # Created by gpt-5.2 | 2026-01-20_01
        logger = get_logger(__name__)

        lufs = float(calculate_lufs(audio))

        logger.info(
            "[DETECTOR] AudioLevelDetector LUFS: %.1f LUFS",
            lufs,
        )

        # NOTE: MATCH_HOST mode removed — single-stream workflow. Do not re-add.
        config = (self.config or {}).get("normalization", {})
        target_lufs = float(config.get("target_lufs", config.get("standard_target", -16.0)))
        loudnorm_params = normalization_params_standard_lufs(target_lufs, -1.5, 11)

        return {
            "lufs": lufs,
            "target_lufs": target_lufs,
            "loudnorm_params": loudnorm_params,
        }

    def get_name(self) -> str:
        # Created by gpt-5.2 | 2026-01-20_01
        return "audio_level_detector"

