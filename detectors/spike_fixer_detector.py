"""SpikeFixerDetector.

Detects whether the audio track contains peaks above `spike_threshold_db`.

Performance note (normalize-before-spike-detect / P3-T15):
 - This detector may run an FFmpeg *analysis pass* (audio-only) to evaluate peak levels
   *after* normalization. That extra pass adds time, but improves accuracy because the
   limiter decision is based on the same post-normalization signal that will be rendered.
 - Pydub extraction is still performed for other detectors/processors, so this does not
   remove the cost of extracting audio from the input media.
 - The FFmpeg filter parameters used for analysis MUST exactly match the render-time
   normalization filters; otherwise, the analyzed peak levels may not match what is
   actually rendered.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from utils.logger import get_logger

from .base_detector import BaseDetector

class SpikeFixerDetector(BaseDetector):
    """
    Detects audio spikes (peaks) above threshold.
    Used to identify segments that need limiting/compression.

    FFmpeg analysis tradeoff:
        We may run an additional FFmpeg pass to analyze peaks *post-normalization*.
        This makes spike detection slower, but more accurate than pre-normalization
        peak detection when normalization can increase peak levels.

        Keep analysis and render filter params in lockstep. Any divergence between the
        analysis filter chain and the render-time filter chain will produce misleading
        results.
    """

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_02
    _FFMPEG_ANALYSIS_CACHE_MAX_ITEMS = 8

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_02
    _FFMPEG_ANALYSIS_CACHE_TTL_SECONDS = 60.0

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_02
    _ffmpeg_analysis_cache: Dict[Tuple[str, str, int, int], Tuple[float, List[float]]] = {}
    
    # [Modified] by gpt-5.2 | 2026-01-20_01
    def detect(self, audio, detection_results: Dict[str, Any] | None = None) -> List[Tuple[float, float]]:
        """Detect audio spikes in audio track.

        Args:
            audio: Pydub AudioSegment for the track being analyzed.
            detection_results: Optional accumulated detector results. When
                `detection_results["audio_level_detector"]` is present, we attempt an
                FFmpeg post-normalization analysis pass.

        Notes:
            - The FFmpeg analysis pass adds time, but improves accuracy because it
              mirrors render-time normalization.
            - Pydub extraction is still needed elsewhere in the pipeline.
            - Analysis filter params MUST exactly match render filter params.
        """

        logger = get_logger(__name__)
        threshold_db = float((self.config or {}).get("spike_threshold_db", -6))

        audio_level = (detection_results or {}).get("audio_level_detector")
        if not audio_level:
            logger.warning(
                "[DETECTOR] SpikeFixerDetector: audio_level_detector results missing; "
                "falling back to pre-normalization spike detection"
            )
            return self._detect_pre_normalization(audio)

        video_path = self._video_path_from_detection_results(detection_results or {})
        if not video_path:
            logger.warning(
                "[DETECTOR] SpikeFixerDetector: video path missing in detection_results; "
                "falling back to pre-normalization spike detection"
            )
            return self._detect_pre_normalization(audio)

        try:
            peak_series_db = self._detect_post_normalization_peak_series_db(video_path, audio_level)
        except Exception as e:
            logger.warning(
                "[DETECTOR] SpikeFixerDetector: FFmpeg post-normalization analysis failed; "
                "falling back to pre-normalization spike detection (%s)",
                e,
            )
            logger.debug("SpikeFixerDetector FFmpeg analysis exception", exc_info=True)
            return self._detect_pre_normalization(audio)

        duration_seconds = float(getattr(audio, "duration_seconds", 0.0) or 0.0)
        spike_regions = self._spike_regions_from_peak_series(
            peak_series_db,
            reset_seconds=1.0,
            duration_seconds=duration_seconds,
            threshold_db=threshold_db,
        )

        if spike_regions:
            logger.info(
                "[DETECTOR] SpikeFixerDetector post-normalization analysis: found %s spike region(s)",
                len(spike_regions),
            )
        else:
            max_peak_db = max(peak_series_db) if peak_series_db else float("-inf")
            logger.info(
                "[DETECTOR] SpikeFixerDetector post-normalization analysis: no spikes (max_peak_db=%.2f threshold_db=%.2f)",
                max_peak_db,
                threshold_db,
            )

        return spike_regions

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_01
    def _detect_pre_normalization(self, audio) -> List[Tuple[float, float]]:
        """Original pydub/numpy spike detector (pre-normalization)."""

        logger = get_logger(__name__)

        threshold_db = float((self.config or {}).get("spike_threshold_db", -6))
        window_ms = float((self.config or {}).get("spike_window_ms", 50))

        # IMPORTANT: frame-accurate windowing for mono/stereo.
        # - Convert window_ms -> window_frames using frame_rate.
        # - Window over frames (not samples).
        # - Peak across ALL channels.
        sample_rate = int(audio.frame_rate)
        window_frames = int(sample_rate * window_ms / 1000)
        window_frames = max(1, window_frames)

        samples = np.asarray(audio.get_array_of_samples())
        peaks_db, _num_frames = self._window_peaks_db(
            samples,
            channels=int(audio.channels),
            window_frames=window_frames,
            sample_width=int(audio.sample_width),
        )

        duration_seconds = float(audio.duration_seconds)
        spike_window_idxs = np.nonzero(peaks_db > threshold_db)[0]
        spike_regions = [
            (
                (int(window_idx) * window_frames) / sample_rate,
                min(((int(window_idx) + 1) * window_frames) / sample_rate, duration_seconds),
            )
            for window_idx in spike_window_idxs
        ]

        merged = self._merge_adjacent_regions(spike_regions, gap_threshold=0.1)
        logger.info("[DETECTOR] Found %s audio spike regions in video", len(merged))
        return merged

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_01
    @staticmethod
    def _video_path_from_detection_results(detection_results: Dict[str, Any]) -> str | None:
        """Best-effort lookup for the input video path.

        Checks the canonical `video_path` key first, then backward-compatible
        guest-specific keys for callers that have not yet migrated.
        """

        # Direct keys — canonical first, then backward-compatible
        for k in ("video_path", "guest_video_path", "guest_path", "_guest_video_path"):
            v = detection_results.get(k)
            if isinstance(v, str) and v.strip():
                return v

        # Nested shapes — canonical first, then backward-compatible
        for k in ("media", "_media", "paths", "_paths"):
            block = detection_results.get(k)
            if isinstance(block, dict):
                for kk in ("video_path", "guest", "guest_video_path", "guest_path"):
                    v = block.get(kk)
                    if isinstance(v, str) and v.strip():
                        return v

        return None

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_01
    def _detect_post_normalization_peak_series_db(self, video_path: str, audio_level: Dict[str, Any]) -> List[float]:
        """Run FFmpeg analysis pass and return per-reset peak dBFS series (post-normalization)."""

        logger = get_logger(__name__)

        # Build loudnorm filter using STANDARD_LUFS parameters from audio_level_detector.
        # IMPORTANT:
        # This analysis filter chain MUST match the render-time normalization chain.
        # Any mismatch means analyzed peaks will not reflect the rendered output.
        target = float(audio_level.get("target_lufs"))
        params = audio_level.get("loudnorm_params") or {}
        tp = float(params.get("TP"))
        lra = float(params.get("LRA"))
        af = f"loudnorm=I={target}:TP={tp}:LRA={lra},astats=metadata=1:reset=1"

        cache_key = self._ffmpeg_analysis_cache_key(video_path, af)
        cached = self._ffmpeg_analysis_cache_get(cache_key)
        if cached is not None:
            logger.debug(
                "SpikeFixerDetector FFmpeg analysis cache hit: path=%s",
                video_path,
            )
            return list(cached)

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "info",
            "-i",
            str(video_path),
            "-vn",
            "-af",
            af,
            "-f",
            "null",
            "-",
        ]
        logger.debug("SpikeFixerDetector FFmpeg cmd: %s", " ".join(cmd))

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stderr = proc.stderr or ""

        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg analysis failed (code={proc.returncode}): {stderr.strip()}")

        peak_series = self._parse_astats_peak_series_db(stderr)
        self._ffmpeg_analysis_cache_set(cache_key, list(peak_series))
        if peak_series:
            logger.debug(
                "SpikeFixerDetector astats peak series: n=%s max=%.2f",
                len(peak_series),
                max(peak_series),
            )
        return list(peak_series)

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_02
    @classmethod
    def _ffmpeg_analysis_cache_key(cls, video_path: str, af: str) -> Tuple[str, str, int, int]:
        """Build a cache key for FFmpeg analysis results.

        Cache safety goals:
            - No cross-run stale cache: this cache is in-memory only.
            - Invalidation within a run: incorporate file mtime/size.
            - Keep it small: bounded by `_FFMPEG_ANALYSIS_CACHE_MAX_ITEMS`.
        """

        p = Path(video_path)
        try:
            st = p.stat()
            mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
            size = int(st.st_size)
        except Exception:
            # If we can't stat (missing/permission), still allow execution without caching.
            mtime_ns = -1
            size = -1

        return (str(p), str(af), mtime_ns, size)

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_02
    @classmethod
    def _ffmpeg_analysis_cache_get(cls, key: Tuple[str, str, int, int]) -> List[float] | None:
        v = cls._ffmpeg_analysis_cache.get(key)
        if not v:
            return None

        created_at, series = v
        if (time.time() - float(created_at)) > float(cls._FFMPEG_ANALYSIS_CACHE_TTL_SECONDS):
            cls._ffmpeg_analysis_cache.pop(key, None)
            return None

        return list(series)

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_02
    @classmethod
    def _ffmpeg_analysis_cache_set(cls, key: Tuple[str, str, int, int], series: List[float]) -> None:
        # Basic TTL + small-size eviction. This intentionally does NOT persist to disk.
        now = time.time()
        cls._ffmpeg_analysis_cache[key] = (now, list(series))

        # Opportunistic cleanup.
        if len(cls._ffmpeg_analysis_cache) <= int(cls._FFMPEG_ANALYSIS_CACHE_MAX_ITEMS):
            return

        # Remove oldest entries until under limit.
        items = sorted(cls._ffmpeg_analysis_cache.items(), key=lambda kv: float(kv[1][0]))
        while len(items) > int(cls._FFMPEG_ANALYSIS_CACHE_MAX_ITEMS):
            k, _v = items.pop(0)
            cls._ffmpeg_analysis_cache.pop(k, None)

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_01
    def _spike_regions_from_peak_series(
        self,
        peak_series_db: List[float],
        *,
        reset_seconds: float,
        duration_seconds: float,
        threshold_db: float,
    ) -> List[Tuple[float, float]]:
        """Convert an astats per-reset peak series into spike regions."""

        if not peak_series_db:
            return []

        reset_seconds = float(reset_seconds)
        if reset_seconds <= 0:
            raise ValueError("reset_seconds must be > 0")

        duration_seconds = max(0.0, float(duration_seconds))

        spike_regions: List[Tuple[float, float]] = []
        for idx, peak_db in enumerate(peak_series_db):
            if float(peak_db) <= float(threshold_db):
                continue

            start = float(idx) * reset_seconds
            end = min(float(idx + 1) * reset_seconds, duration_seconds)
            if end > start:
                spike_regions.append((start, end))

        # Merge adjacent/overlapping windows into coarser regions.
        return self._merge_adjacent_regions(spike_regions, gap_threshold=0.1)

    # [Created-or-Modified] by gpt-5.2 | 2026-01-20_01
    @staticmethod
    def _parse_astats_peak_series_db(stderr: str) -> List[float]:
        """Extract a per-reset peak series from FFmpeg astats stderr output.

        With `astats=...:reset=1`, FFmpeg prints repeated "Overall" blocks.
        We treat each Overall block as one time window.
        """

        series: List[float] = []
        current: float | None = None

        for raw_line in (stderr or "").splitlines():
            line = raw_line.strip()

            # Start of a new window.
            if re.search(r"\] Overall\b", line):
                if current is not None:
                    series.append(float(current))
                current = None
                continue

            m = re.search(r"\b(?:Peak level dB|Max level dB):\s*(-?\d+(?:\.\d+)?)", line)
            if not m:
                continue

            try:
                v = float(m.group(1))
            except Exception:
                continue

            if current is None:
                current = v
            else:
                current = max(current, v)

        if current is not None:
            series.append(float(current))

        if series:
            return series

        # Fallback: accept a single Overall metric.
        values: List[float] = []
        for m in re.finditer(r"\b(?:Peak level dB|Max level dB):\s*(-?\d+(?:\.\d+)?)", stderr or ""):
            try:
                values.append(float(m.group(1)))
            except Exception:
                continue
        if not values:
            raise ValueError("No astats peak/max dB values found in FFmpeg stderr")
        return [float(max(values))]

    # Created-or-Modified by gpt-5.2 | 2026-01-09_01
    @staticmethod
    def _window_peaks_db(
        samples: np.ndarray,
        *,
        channels: int,
        window_frames: int,
        sample_width: int,
        min_ratio: float = 1e-10,
    ) -> Tuple[np.ndarray, int]:
        """Compute peak dBFS per frame-window (vectorized).

        Important: `samples` must be interleaved PCM samples as returned by
        `audio.get_array_of_samples()`.

        Returns:
            (peaks_db, num_frames)
        Where:
            peaks_db is shape (num_windows,) and computed across ALL channels.
            num_frames is the number of source frames (before padding).
        """

        if channels <= 0:
            raise ValueError("channels must be >= 1")

        # Clamp to at least 1 to avoid divide-by-zero and reshape issues.
        window_frames = max(1, int(window_frames))

        if sample_width <= 0:
            raise ValueError("sample_width must be >= 1")

        # NOTE: The project usually operates on extracted WAV audio; common PCM
        # widths are 1/2/3/4 bytes. We keep this generic, but sanity-check
        # absurd widths so shifts don't explode.
        if sample_width > 8:
            raise ValueError("sample_width must be <= 8")

        # Ensure integer type before abs() to avoid int16 overflow at -32768.
        # (np.abs(np.int16(-32768)) == -32768)
        samples_i32 = np.asarray(samples)
        if not np.issubdtype(samples_i32.dtype, np.signedinteger):
            samples_i32 = samples_i32.astype(np.int32, copy=False)
        else:
            samples_i32 = samples_i32.astype(np.int32, copy=False)

        # Frame-accurate windowing for mono/stereo: reshape interleaved samples
        # into (num_frames, channels) and window over frames.
        num_frames = int(samples_i32.size // channels)
        if num_frames <= 0:
            return np.asarray([], dtype=np.float64), 0

        usable = samples_i32[: num_frames * channels]
        frames = usable.reshape((num_frames, channels))

        # Pad trailing frames to a multiple of window_frames so we can reshape
        # into (num_windows, window_frames, channels) in one go.
        pad_frames = (-num_frames) % window_frames
        if pad_frames:
            frames = np.pad(frames, ((0, pad_frames), (0, 0)), mode="constant")

        num_windows = frames.shape[0] // window_frames
        windows = frames.reshape((num_windows, window_frames, channels))

        # Peak across all samples in the window across channels.
        peaks = np.max(np.abs(windows), axis=(1, 2)).astype(np.float64, copy=False)

        # Convert to dBFS where 0 dBFS == full scale. Derive full scale from
        # sample_width (bytes) rather than hardcoding 32768.
        full_scale = float(1 << ((8 * sample_width) - 1))
        ratio = peaks / full_scale
        peaks_db = 20.0 * np.log10(np.maximum(ratio, min_ratio))

        return peaks_db, num_frames
    
    def _merge_adjacent_regions(self, regions, gap_threshold=0.1):
        """Merge regions that are close together"""
        if not regions:
            return []
        
        merged = [regions[0]]
        
        for start, end in regions[1:]:
            last_start, last_end = merged[-1]
            
            if start - last_end <= gap_threshold:
                # Merge with previous region
                merged[-1] = (last_start, end)
            else:
                merged.append((start, end))
        
        return merged
    
    def get_name(self) -> str:
        return "spike_fixer_detector"
