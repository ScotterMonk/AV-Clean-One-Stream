"""io_/media_preflight.py

Media preflight utilities.

Currently includes duration alignment for host/guest videos by padding the shorter
to match the longer -- using a fast stream-copy+tail strategy for large files.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time

from dataclasses import dataclass
from pathlib import Path

import ffmpeg

from io_.media_probe import get_video_duration_seconds
from io_.video_renderer import run_with_progress
from utils.logger import get_logger
from utils.path_helpers import add_suffix_to_filename


logger = get_logger(__name__)


@dataclass(frozen=True)
class _NormalizePlan:
    input_path: str
    output_path: str
    input_duration_s: float
    target_duration_s: float
    pad_seconds: float


def _run_ffmpeg(cmd: list[str], label: str = "") -> None:
    """Run an FFmpeg subprocess command, raising RuntimeError on failure."""
    if label:
        logger.info("[FFmpeg] %s: %s", label, " ".join(str(c) for c in cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed [{label}] (returncode={result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )


def _fmt_concat_path(p: str) -> str:
    """Format a filesystem path for an FFmpeg concat demuxer list file.

    FFmpeg's concat demuxer wraps paths in single quotes.
    Forward-slash normalization is applied for Windows compatibility.
    Single quotes inside the path are backslash-escaped.
    """
    p = p.replace("\\", "/")   # Windows path -> forward slashes (FFmpeg handles both)
    p = p.replace("'", "\\'")  # Escape any literal single quotes in the path
    return f"'{p}'"


def _video_pad_efficient(plan: _NormalizePlan) -> None:
    """Pad a video by appending a tiny frozen-frame tail -- fast path for large files.

    Strategy (avoids re-encoding the full main body):
      1. Probe the original for video fps, audio sample rate, and channel count.
      2. Fast-seek to near the end of the input; extract exactly 1 frame as a PNG.
      3. Loop that PNG frame + generate silence to create a short tail segment.
         Only `pad_seconds` of video are encoded -- typically seconds, not minutes.
      4. Concatenate original + tail using the FFmpeg concat demuxer with -c copy
         so the main body is muxed at the container level (no decode/encode).

    For a 2 GB / 2-hour file with a 3-second tail difference, total encode work
    drops from ~O(2 hours) to O(3 seconds).
    """
    if plan.pad_seconds <= 0:
        raise ValueError(f"_video_pad_efficient requires pad_seconds > 0 (got {plan.pad_seconds})")

    out_dir = Path(plan.output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # All temp files land next to the output so there are no cross-device moves.
    fd_frame, frame_path = tempfile.mkstemp(prefix=".pf_frame_", suffix=".png", dir=str(out_dir))
    os.close(fd_frame)

    fd_tail, tail_path = tempfile.mkstemp(prefix=".pf_tail_", suffix=".mp4", dir=str(out_dir))
    os.close(fd_tail)

    fd_list, concat_list_path = tempfile.mkstemp(prefix=".pf_concat_", suffix=".txt", dir=str(out_dir))
    os.close(fd_list)

    try:
        # -- Step 0: Probe original for fps and audio parameters --
        try:
            probe = ffmpeg.probe(plan.input_path)
        except Exception as exc:
            raise RuntimeError(f"ffmpeg.probe failed on {plan.input_path}: {exc}") from exc

        video_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
        audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]

        fps = 30.0  # safe default
        if video_streams:
            fps_str = video_streams[0].get("r_frame_rate", "30/1")
            try:
                fps_n, fps_d = (int(x) for x in fps_str.split("/"))
                fps = fps_n / fps_d if fps_d else 30.0
            except (ValueError, ZeroDivisionError):
                pass  # keep default

        sample_rate = 44100  # safe default
        channels = 2         # safe default
        if audio_streams:
            try:
                sample_rate = int(audio_streams[0].get("sample_rate", 44100))
            except (ValueError, TypeError):
                pass
            try:
                channels = int(audio_streams[0].get("channels", 2))
            except (ValueError, TypeError):
                pass

        # Map channel count to FFmpeg layout name understood by anullsrc.
        channel_layout = "mono" if channels == 1 else "stereo"

        logger.info(
            "Tail params: fps=%.2f sample_rate=%d channels=%d layout=%s pad_seconds=%.3f",
            fps, sample_rate, channels, channel_layout, plan.pad_seconds,
        )

        # -- Step 1: Extract last frame (fast input seek; near-instant) --
        # Use a positive absolute timestamp (-ss before -i) rather than -sseof.
        # -sseof can return exit 0 while writing no frames when seeking hits EOF
        # in certain containers; a positive seek to (duration - 1.0) is reliable.
        seek_ts = max(0.0, plan.input_duration_s - 1.0)
        _run_ffmpeg(
            [
                "ffmpeg", "-y",
                "-ss", str(seek_ts),  # fast input seek to ~1 s before end
                "-i", plan.input_path,
                "-frames:v", "1",
                "-q:v", "1",           # highest quality PNG
                frame_path,
            ],
            label="Extract last frame",
        )

        # Guard: confirm the frame was actually written (non-empty file).
        if not os.path.exists(frame_path) or os.path.getsize(frame_path) == 0:
            raise RuntimeError(
                f"Frame extraction produced no output for '{plan.input_path}'. "
                f"The PNG at '{frame_path}' is missing or empty after Step 1."
            )

        # -- Step 2: Encode tiny tail (looped still image + silence) --
        # -loop 1 makes the PNG repeat for the given -t duration.
        # anullsrc generates silence with matching sample rate / channel layout.
        # -vf format=yuv420p ensures H.264-compatible pixel format regardless of PNG depth.
        _run_ffmpeg(
            [
                "ffmpeg", "-y",
                "-loop", "1", "-framerate", str(fps), "-i", frame_path,
                "-f", "lavfi",
                "-i", f"anullsrc=sample_rate={sample_rate}:channel_layout={channel_layout}",
                "-t", str(plan.pad_seconds),
                "-vf", "format=yuv420p",
                "-vcodec", "libx264", "-preset", "ultrafast", "-crf", "18",
                "-acodec", "aac", "-b:a", "192k",
                "-shortest",        # stop when the shorter stream (video) ends
                tail_path,
            ],
            label=f"Encode tail segment ({plan.pad_seconds:.3f}s)",
        )

        # -- Step 3: Concat original + tail via concat demuxer (-c copy, no re-encode) --
        with open(concat_list_path, "w", encoding="utf-8") as f:
            f.write(f"file {_fmt_concat_path(plan.input_path)}\n")
            f.write(f"file {_fmt_concat_path(tail_path)}\n")

        _run_ffmpeg(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list_path,
                "-c", "copy",
                plan.output_path,
            ],
            label=f"Concat {os.path.basename(plan.input_path)} + tail -> {os.path.basename(plan.output_path)}",
        )

    finally:
        # Always clean up temp files, even on failure.
        for tmp in (frame_path, tail_path, concat_list_path):
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass  # best-effort cleanup


def normalize_video_lengths(host_path: str, guest_path: str) -> tuple[str, str]:
    """Normalize host+guest video container durations.

    - If durations are equal (within 10 ms): returns inputs unchanged.
    - Otherwise: pads only the shorter video to match the longer using
      the efficient stream-copy + tiny-tail strategy.  The longer video is
      returned as-is (no re-encode, no intermediate file).

    Notes:
    - Only one preflight output file is written (for the shorter video).
    - The returned path for the longer video is its original input path.
    - Preflight outputs use `_preflight` suffix to reserve `_processed` for final outputs.
    """
    host_d = get_video_duration_seconds(host_path)
    guest_d = get_video_duration_seconds(guest_path)

    # Treat sub-frame probe jitter as aligned so tiny FFmpeg/container rounding differences
    # do not trigger an unnecessary preflight re-encode.
    if abs(host_d - guest_d) < 0.01:
        return host_path, guest_path

    target = max(host_d, guest_d)
    shorter_is_guest = guest_d < host_d
    which_padded = "guest" if shorter_is_guest else "host"

    logger.info(
        f"[FUNCTION START] Pad end of shorter video ({which_padded}) to fit longer video length"
    )
    logger.info(
        "Duration mismatch detected; normalizing lengths: host=%.3fs guest=%.3fs target=%.3fs",
        host_d,
        guest_d,
        target,
    )

    # The longer video needs no changes -- return its original path directly.
    if shorter_is_guest:
        shorter_path = guest_path
        shorter_d = guest_d
        out_shorter = add_suffix_to_filename(guest_path, "_preflight", output_ext=".mp4")
        out_host = host_path    # already the longer; no processing needed
        out_guest = out_shorter
    else:
        shorter_path = host_path
        shorter_d = host_d
        out_shorter = add_suffix_to_filename(host_path, "_preflight", output_ext=".mp4")
        out_host = out_shorter
        out_guest = guest_path  # already the longer; no processing needed

    plan = _NormalizePlan(
        input_path=shorter_path,
        output_path=out_shorter,
        input_duration_s=shorter_d,
        target_duration_s=target,
        pad_seconds=target - shorter_d,
    )

    preflight_start = time.time()
    logger.info(
        "Padding shorter video: in=%s out=%s pad=%.3fs target=%.3fs",
        plan.input_path,
        plan.output_path,
        plan.pad_seconds,
        plan.target_duration_s,
    )

    _video_pad_efficient(plan)

    preflight_duration = time.time() - preflight_start
    from utils.logger import format_duration, format_time_cut

    logger.info(
        f"[PREFLIGHT COMPLETE] Padded shorter video ({which_padded}) to fit longer video - "
        f"Preflight pair written to {format_time_cut(target)} duration - "
        f"Took {format_duration(preflight_duration)}"
    )
    logger.info(
        f"[FUNCTION COMPLETE] Pad end of shorter video ({which_padded}) to fit longer video length"
        f" - Took {format_duration(preflight_duration)}"
    )

    return out_host, out_guest
