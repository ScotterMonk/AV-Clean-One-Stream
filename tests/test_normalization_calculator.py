import os
import sys

import pytest


# Add the project root to sys.path (consistent with existing tests like tests/test_imports.py)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from analyzers.normalization_calculator import (
    normalization_gain_match_host,
    normalization_params_standard_lufs,
)


def test_normalization_gain_match_host_basic() -> None:
    gain = normalization_gain_match_host(host_lufs=-18.0, guest_lufs=-23.0, max_gain_db=15.0)
    assert gain == pytest.approx(5.0)


def test_normalization_gain_match_host_clamp() -> None:
    gain = normalization_gain_match_host(host_lufs=-10.0, guest_lufs=-30.0, max_gain_db=15.0)
    assert gain == pytest.approx(15.0)


def test_normalization_gain_match_host_negative() -> None:
    gain = normalization_gain_match_host(host_lufs=-25.0, guest_lufs=-20.0, max_gain_db=15.0)
    assert gain == pytest.approx(-5.0)


def test_normalization_gain_match_host_identical() -> None:
    gain = normalization_gain_match_host(host_lufs=-18.0, guest_lufs=-18.0, max_gain_db=15.0)
    assert gain == pytest.approx(0.0)


def test_normalization_params_standard_lufs_structure_and_values() -> None:
    params = normalization_params_standard_lufs(target_lufs=-16.0, true_peak=-1.5, lra=11.0)

    assert set(params.keys()) == {"I", "TP", "LRA"}
    assert params["I"] == pytest.approx(-16.0)
    assert params["TP"] == pytest.approx(-1.5)
    assert params["LRA"] == pytest.approx(11.0)
