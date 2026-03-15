# analyzers/normalization_calculator.py

import logging
from typing import Any, Dict

from utils.logger import get_logger

# NOTE: normalization_gain_match_host() removed — single-stream workflow.
def normalization_params_standard_lufs(target_lufs: float, true_peak: float, lra: float) -> Dict[str, Any]:
    # Created by gpt-5.2 | 2026-01-20_01
    """Build the FFmpeg `loudnorm` parameter dict for STANDARD_LUFS mode.

    Notes
    -----
    This function returns a dict with the keys expected by FFmpeg's `loudnorm` filter
    (I, TP, LRA).

    Args:
        target_lufs: Target integrated loudness (LUFS) for `loudnorm` (I).
        true_peak: True-peak limit in dBTP for `loudnorm` (TP).
        lra: Loudness range for `loudnorm` (LRA).

    Returns:
        Dict with keys {"I", "TP", "LRA"} suitable for `manifest.add_filter("loudnorm", **params)`.
    """

    logger = get_logger(__name__)

    params: Dict[str, Any] = {
        "I": float(target_lufs),
        "TP": float(true_peak),
        "LRA": float(lra),
    }

    logger.info(
        "[NORMALIZATION] STANDARD_LUFS params - I=%.3f TP=%.3f LRA=%.3f",
        params["I"],
        params["TP"],
        params["LRA"],
    )
    return params

