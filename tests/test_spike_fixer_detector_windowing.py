import os
import sys

import numpy as np
import pytest


# Add the project root to sys.path (mirrors tests/test_imports.py)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from detectors.spike_fixer_detector import SpikeFixerDetector


def _dbfs_from_peak(peak: float, *, sample_width: int, min_ratio: float = 1e-10) -> float:
    full_scale = float(1 << ((8 * sample_width) - 1))
    ratio = float(peak) / full_scale
    return float(20.0 * np.log10(max(ratio, min_ratio)))


def test_window_peaks_db_mono_vs_stereo_peak_is_max_across_channels():
    # Mono: 4 frames, window_frames=2 -> 2 windows
    mono_samples = np.asarray([0, 1000, -2000, 3000], dtype=np.int16)
    mono_peaks_db, mono_num_frames = SpikeFixerDetector._window_peaks_db(
        mono_samples,
        channels=1,
        window_frames=2,
        sample_width=2,
    )
    assert mono_num_frames == 4
    assert mono_peaks_db.shape == (2,)

    assert mono_peaks_db[0] == pytest.approx(_dbfs_from_peak(1000, sample_width=2), abs=1e-9)
    assert mono_peaks_db[1] == pytest.approx(_dbfs_from_peak(3000, sample_width=2), abs=1e-9)

    # Stereo: interleaved (L0,R0,L1,R1,L2,R2), 3 frames, window_frames=2 -> 2 windows (last padded)
    # Window 0 (frames 0-1): L peaks at 1000, R peaks at 2000 -> overall peak 2000
    # Window 1 (frame 2 + padding): L=3000, R=10 -> overall peak 3000
    stereo_samples = np.asarray([1000, -2000, 5, 0, 3000, 10], dtype=np.int16)
    stereo_peaks_db, stereo_num_frames = SpikeFixerDetector._window_peaks_db(
        stereo_samples,
        channels=2,
        window_frames=2,
        sample_width=2,
    )
    assert stereo_num_frames == 3
    assert stereo_peaks_db.shape == (2,)

    assert stereo_peaks_db[0] == pytest.approx(_dbfs_from_peak(2000, sample_width=2), abs=1e-9)
    assert stereo_peaks_db[1] == pytest.approx(_dbfs_from_peak(3000, sample_width=2), abs=1e-9)


def test_timestamp_mapping_sanity_matches_detect_window_index_math():
    # Sanity-check the math used by detect() without depending on pydub.
    sample_rate = 10
    window_frames = 4
    channels = 1
    sample_width = 2
    num_frames = 9  # duration_seconds = 0.9

    # Make windows 0 and 2 exceed a hypothetical threshold.
    # frames 0-3: peak=20000
    # frames 4-7: peak=0
    # frames 8 + pad: peak=25000
    frames = np.asarray(
        [20000, 0, 0, 0, 0, 0, 0, 0, 25000],
        dtype=np.int16,
    )
    peaks_db, got_num_frames = SpikeFixerDetector._window_peaks_db(
        frames,
        channels=channels,
        window_frames=window_frames,
        sample_width=sample_width,
    )
    assert got_num_frames == num_frames
    assert peaks_db.shape == (3,)

    threshold_db = -20.0
    spike_window_idxs = np.nonzero(peaks_db > threshold_db)[0]
    assert spike_window_idxs.tolist() == [0, 2]

    duration_seconds = num_frames / sample_rate
    spike_regions = [
        (
            (int(window_idx) * window_frames) / sample_rate,
            min(((int(window_idx) + 1) * window_frames) / sample_rate, duration_seconds),
        )
        for window_idx in spike_window_idxs
    ]

    assert spike_regions == [(0.0, 0.4), (0.8, 0.9)]


def test_padding_behavior_last_partial_window_uses_actual_samples_and_zero_pad():
    # 6 frames, window_frames=4 -> 2 windows (second window has 2 actual frames + 2 zero-pad frames)
    samples = np.asarray([1, 2, 3, 4, 10000, 0], dtype=np.int16)
    peaks_db, num_frames = SpikeFixerDetector._window_peaks_db(
        samples,
        channels=1,
        window_frames=4,
        sample_width=2,
    )
    assert num_frames == 6
    assert peaks_db.shape == (2,)
    assert peaks_db[0] == pytest.approx(_dbfs_from_peak(4, sample_width=2), abs=1e-9)
    assert peaks_db[1] == pytest.approx(_dbfs_from_peak(10000, sample_width=2), abs=1e-9)

    # If the trailing actual samples are all zeros, peak should remain 0 even with padding.
    samples_zeros_tail = np.asarray([1, 2, 3, 4, 0, 0], dtype=np.int16)
    peaks_db2, _ = SpikeFixerDetector._window_peaks_db(
        samples_zeros_tail,
        channels=1,
        window_frames=4,
        sample_width=2,
    )
    assert peaks_db2.shape == (2,)
    assert peaks_db2[1] == pytest.approx(_dbfs_from_peak(0, sample_width=2), abs=1e-9)


def test_int16_negative_full_scale_handling_abs_overflow_avoided_for_minus_32768():
    # np.abs(np.int16(-32768)) would overflow to -32768; implementation must upcast before abs.
    samples = np.asarray([-32768], dtype=np.int16)
    peaks_db, num_frames = SpikeFixerDetector._window_peaks_db(
        samples,
        channels=1,
        window_frames=1,
        sample_width=2,
    )
    assert num_frames == 1
    assert peaks_db.shape == (1,)
    assert peaks_db[0] == pytest.approx(0.0, abs=1e-12)


def test_merge_adjacent_regions_gap_threshold_behavior_unchanged():
    d = SpikeFixerDetector(config={})

    regions = [(0.0, 1.0), (1.05, 2.0), (2.3, 2.5), (2.55, 3.0)]
    merged = d._merge_adjacent_regions(regions, gap_threshold=0.1)
    assert merged == [(0.0, 2.0), (2.3, 3.0)]

    # Ensure no merge when gap is above threshold
    regions2 = [(0.0, 1.0), (1.11, 2.0)]
    merged2 = d._merge_adjacent_regions(regions2, gap_threshold=0.1)
    assert merged2 == regions2

