"""utils/path_helpers.py

Filename/path helpers.

Important: This project renders outputs as MP4 (see ffmpeg settings), so helpers default
to generating *.mp4 output paths even if the input was a different container.
"""

from __future__ import annotations

from pathlib import Path


def add_suffix_to_filename(input_path: str, suffix: str, *, output_ext: str | None = None) -> str:
    """Return a path in the same directory with `suffix` inserted before the extension.

    Examples:
      - input.mp4 + "_processed" -> input_processed.mp4
      - input.avi + "_processed" (output_ext=".mp4") -> input_processed.mp4
      - input (no extension) + "_processed" (output_ext=".mp4") -> input_processed.mp4
    """

    p = Path(input_path)
    ext = p.suffix if output_ext is None else str(output_ext)
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return str(p.with_name(f"{p.stem}{suffix}{ext}"))


def make_processed_output_path(input_video_path: str, *, output_ext: str = ".mp4") -> str:
    """Derive the default processed output path for an input video.

    Safety invariant: this must NEVER return a path equal to the input path.
    The application must not overwrite the user's selected input.
    """

    p = Path(input_video_path)

    # If the input already looks like a processed file, generate a *new* output path
    # rather than returning the input unchanged.
    stem = p.stem
    if stem.endswith("_processed"):
        stem = stem[: -len("_processed")]
        return str(p.with_name(f"{stem}_processed_rerun{output_ext}"))

    return add_suffix_to_filename(input_video_path, "_processed", output_ext=output_ext)


def make_fixed_output_path(input_video_path: str) -> str:
    """Derive the "fixed" output path by appending `_fixed` and preserving extension."""

    p = Path(input_video_path)
    return add_suffix_to_filename(input_video_path, "_fixed", output_ext=p.suffix)

