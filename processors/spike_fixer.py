"""SpikeFixer processor.

This processor MUST NOT mutate any pydub AudioSegment inputs.
It only updates the EditManifest with FFmpeg filter instructions.
"""

from __future__ import annotations

from core.interfaces import EditManifest
from utils.logger import get_logger

from .base_processor import BaseProcessor


class SpikeFixer(BaseProcessor):
    """Adds an audio limiter when spikes are detected."""

    def process(self, manifest: EditManifest, audio, detection_results) -> EditManifest:
        spike_regions = detection_results.get("spike_fixer_detector", [])
        if not spike_regions:
            return manifest

        # FFmpeg: alimiter (hard limiter). We apply it to the full track when spikes exist.
        # Limit is linear amplitude (0..1). Convert from dBFS peak target.
        max_peak_db = float(self.config.get("max_peak_db", -3.0))
        limit = 10 ** (max_peak_db / 20.0)

        # Clamp to alimiter's expected range.
        limit = max(0.0001, min(limit, 1.0))

        attack_ms = float(self.config.get("limiter_attack_ms", 5.0))
        release_ms = float(self.config.get("limiter_release_ms", 50.0))

        manifest.add_filter(
            "alimiter",
            limit=limit,
            attack=attack_ms,
            release=release_ms,
        )

        logger = get_logger(__name__)
        logger.info(
            f"Applied limiter to {len(spike_regions)} spike regions"
        )
        return manifest

    def get_name(self) -> str:
        return "SpikeFixer"
