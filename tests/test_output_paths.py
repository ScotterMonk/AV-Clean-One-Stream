from __future__ import annotations

from pathlib import Path

from utils.path_helpers import make_fixed_output_path, make_processed_output_path


def test_make_processed_output_path_uses_mp4_even_for_non_mp4_input() -> None:
    cases = [
        "video.mp4",
        "video.avi",
        "video.wmv",
        "my.video.mkv",
        "no_ext",
        str(Path("nested") / "clip.avi"),
    ]

    for inp in cases:
        outp = make_processed_output_path(inp)
        out_path = Path(outp)
        assert out_path.suffix.lower() == ".mp4"
        assert out_path.stem.endswith("_processed")
        assert out_path.parent == Path(inp).parent


def test_make_processed_output_path_does_not_double_append_processed_suffix() -> None:
    inp = str(Path("nested") / "video_processed.mp4")
    outp = make_processed_output_path(inp)
    assert outp != inp
    assert Path(outp).name == "video_processed_rerun.mp4"


def test_make_processed_output_path_stability_comprehensive() -> None:
    """Inputs already ending with _processed should not be overwritten.

    Instead of returning the same path, we force a new output name so the user's
    selected input is never the render target.
    """
    cases = [
        # Simple case
        "x_processed.mp4",
        # Different extensions - preserved, not converted to .mp4
        "video_processed.avi",
        "clip_processed.mkv",
        "recording_processed.wmv",
        # No extension
        "video_processed",
        # Nested paths
        str(Path("output") / "guest_processed.mp4"),
        str(Path("deep") / "nested" / "host_processed.avi"),
        # Edge cases with multiple underscores
        "my_video_file_processed.mp4",
        "test_clip_processed.mp4",
    ]

    for inp in cases:
        result = make_processed_output_path(inp)
        assert result != inp, f"Expected {inp} to produce a new output path, got input"


def test_make_fixed_output_path_preserves_extension() -> None:
    inp = "video_processed.mp4"
    assert make_fixed_output_path(inp) == "video_processed_fixed.mp4"

