# analyzers/normalization_calculator.py

import logging
from typing import Any, Dict

from utils.logger import get_logger


def normalization_gain_match_host(host_lufs: float, guest_lufs: float, max_gain_db: float) -> float:
    # Created by gpt-5.2 | 2026-01-20_01
    """Calculate the gain (in dB) to apply to the guest track in MATCH_HOST mode.

    MATCH_HOST vs STANDARD_LUFS
    ---------------------------
    - MATCH_HOST: Make the *guest* track match the host's integrated loudness (LUFS).
      This is useful when the host is considered the reference (e.g., primary mic), and
      the guest should be raised/lowered to sit at the same overall loudness.

    - STANDARD_LUFS: Normalize to a fixed LUFS target for both tracks (handled by
      `normalization_params_standard_lufs()`), typically using FFmpeg's `loudnorm`
      parameters.

    Safety
    ------
    A positive diff (host louder than guest) will boost the guest; this boost is clamped
    to `max_gain_db` to avoid excessively amplifying noise.

    Args:
        host_lufs: Integrated loudness of the host track (LUFS).
        guest_lufs: Integrated loudness of the guest track (LUFS).
        max_gain_db: Maximum positive gain allowed (dB).

    Returns:
        Gain in dB to apply to the guest track.
    """

    logger = get_logger(__name__)

    # Gain difference to align guest to host.
    gain_db = float(host_lufs - guest_lufs)
    max_gain_db = float(max_gain_db)

    # Clamp only upward gain (per plan: min(diff, max_gain_db)).
    gain_db_clamped = float(min(gain_db, max_gain_db))

    logger.info(
        "[NORMALIZATION] MATCH_HOST gain calc - host_lufs=%.3f guest_lufs=%.3f diff_db=%+.3f clamped_db=%+.3f max_gain_db=%.3f",
        host_lufs,
        guest_lufs,
        gain_db,
        gain_db_clamped,
        max_gain_db,
    )
    return gain_db_clamped


def normalization_params_standard_lufs(target_lufs: float, true_peak: float, lra: float) -> Dict[str, Any]:
    # Created by gpt-5.2 | 2026-01-20_01
    """Build the FFmpeg `loudnorm` parameter dict for STANDARD_LUFS mode.

    MATCH_HOST vs STANDARD_LUFS
    ---------------------------
    - MATCH_HOST: Compute a *single* static `volume` gain for the guest so it matches the
      host track's integrated LUFS.

    - STANDARD_LUFS: Compute *configuration* for FFmpeg's `loudnorm` filter so both host
      and guest can be normalized to the same standard loudness target.

    Notes
    -----
    This function returns a dict with the keys expected by FFmpeg's `loudnorm` filter
    (I, TP, LRA).

    Args:
        target_lufs: Target integrated loudness (LUFS) for `loudnorm` (I).
        true_peak: True-peak limit in dBTP for `loudnorm` (TP).
        lra: Loudness range for `loudnorm` (LRA).

    Returns:
        Dict with keys {"I", "TP", "LRA"} suitable for `manifest.add_*_filter("loudnorm", **params)`.
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

