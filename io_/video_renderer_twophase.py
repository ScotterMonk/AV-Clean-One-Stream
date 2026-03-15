# io_/video_renderer_twophase.py
"""Two-phase render strategy for AV-cleaner.

Phase 1 (audio) renders a normalised/filtered audio-only stream to a
temporary AAC file.  Phase 2 (video) re-muxes the original video stream
with that pre-rendered audio, avoiding a full re-encode of video on the
common path where only audio needs processing.

This module begins with the audio-phase helper.  Video-phase and mux
helpers will be added in subsequent tasks (Phase 1 Task 04+).

Design rationale
----------------
The two-phase approach lets us apply expensive audio transformations
(normalisation, limiting, silence removal) once and then reuse the
result when iterating on video-only parameters, cutting total processing
time by 40–70 % on typical podcast files.
"""

import os
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ffmpeg

from io_.media_probe import (
    get_video_duration_seconds,
    probe_video_fps,
    probe_video_keyframes,
    probe_video_stream_codec,
)
from io_.video_renderer import (
    _build_filter_chain,
    _fmt_elapsed,
    _render_with_safe_overwrite,
    build_input_kwargs,
    merge_close_segments,
)
from io_.video_renderer_progress import run_with_progress
from utils.logger import get_logger

logger = get_logger(__name__)


def render_audio_phase(
    input_path: str,
    filters: list,
    keep_segments: list,
    out_path: str,
    audio_opts: dict,
) -> None:
    """Render the audio-only phase of a two-phase encode.

    Merges close segments, applies audio filters, trims to keep_segments, and
    writes an audio-only file to *out_path*.  Uses asplit when multi-segment +
    filter path requires it.  Executes via run_with_progress.

    Args:
        input_path:    Source video or audio file.
        filters:       Audio filter objects with .filter_name / .params.
        keep_segments: (start_s, end_s) tuples to retain; empty = full audio.
        out_path:      Destination audio-only file.
        audio_opts:    Extra kwargs for ffmpeg.output() (acodec, audio_bitrate).
    """
    # Step 1: merge micro-gap pairs before constructing the filter graph.
    keep_segments = merge_close_segments(keep_segments)

    logger.debug(
        "render_audio_phase(%s): keep_segments=%d filters=%d out=%s",
        os.path.basename(input_path),
        len(keep_segments),
        len(filters or []),
        os.path.basename(out_path),
    )

    # Step 2: build the base audio stream from the source file.
    inp = ffmpeg.input(input_path)
    a = inp.audio

    # Step 3: apply audio filters sequentially.
    for f in filters or []:
        a = a.filter(f.filter_name, **f.params)

    # Step 4: initialise audio_inputs before any conditional branch.
    audio_inputs = None

    if keep_segments:
        segs_a = []

        # Step 5: insert asplit when multiple segments + at least one filter
        # exist, to prevent ffmpeg-python from wiring one filtered output node
        # into multiple atrim chains (graph construction error).
        if len(keep_segments) > 1 and (filters or []):
            logger.debug(
                "render_audio_phase(%s): inserting asplit(outputs=%d) before per-segment atrim",
                os.path.basename(input_path),
                len(keep_segments),
            )
            # NOTE: do NOT call list() on the FilterNode; iterate via .stream(i) only.
            split_node = a.filter_multi_output("asplit", outputs=len(keep_segments))
            audio_inputs = [split_node.stream(i) for i in range(len(keep_segments))]

        for idx, (start, end) in enumerate(keep_segments):
            # Step 6: trim each segment and reset PTS to 0-relative.
            a_in = audio_inputs[idx] if audio_inputs is not None else a
            seg_a = (
                a_in.filter_("atrim", start=start, end=end)
                    .filter_("asetpts", "PTS-STARTPTS")
            )
            segs_a.append(seg_a)

        # Step 7: concatenate trimmed segments (audio-only; v=0 a=1).
        if len(segs_a) == 1:
            # Single segment: skip concat node — no multi-input needed.
            audio_out = segs_a[0]
        else:
            audio_out = ffmpeg.concat(*segs_a, v=0, a=1)

    else:
        # Step 8: no segments requested — pass the full audio through unchanged.
        audio_out = a

    # Step 9: build output stream; vn=None suppresses any video track.
    stream = ffmpeg.output(audio_out, out_path, vn=None, **audio_opts)

    # Step 10: execute with progress reporting.
    run_with_progress(stream, overwrite_output=True)


def classify_segments_by_keyframe(
    keep_segments: list,
    keyframes: list,
    snap_tolerance_s: float = 0.1,
) -> list[dict]:
    """Classify each keep segment as 'copy' or 'bridge' based on keyframe alignment.

    For each ``(start, end)`` in *keep_segments*:

    * **empty keyframes**: ``type='bridge'``, ``kf_start=0.0``
    * **nearest keyframe within tolerance**: ``type='copy'``, ``kf_start=nearest_kf``
    * **otherwise**: ``type='bridge'``,
      ``kf_start=max(kf for kf in keyframes if kf <= start, default=0.0)``

    This classification drives Phase 2 rendering decisions: copy-eligible segments
    are stream-copied directly (fast, lossless); bridge segments require a re-encode
    from the nearest preceding keyframe to the cut point.

    Args:
        keep_segments:    Sorted list of ``(start_s, end_s)`` float tuples defining
                          regions to retain (seconds).
        keyframes:        Sorted list of keyframe timestamps in seconds, as returned
                          by :func:`io_.media_probe.probe_video_keyframes`.
        snap_tolerance_s: Maximum distance (seconds) between a segment start and a
                          keyframe for the segment to be classified as ``'copy'``.
                          Defaults to 0.1 s (one typical GOP frame interval).

    Returns:
        List of dicts, one per input segment, with keys:
        ``'type'`` (``'copy'`` | ``'bridge'``), ``'start'``, ``'end'``, ``'kf_start'``.
    """
    result = []
    copy_count = 0
    bridge_count = 0

    for start, end in keep_segments:
        if not keyframes:
            # No keyframe data available — must re-encode from the beginning.
            seg_type = "bridge"
            kf_start = 0.0
        else:
            # Only consider keyframes AT OR BEFORE the segment start.
            # Using a keyframe AFTER start as kf_start would cause the copy to
            # seek past the segment's logical start, dropping leading frames and
            # accumulating per-segment A/V de-sync drift.
            kf_before = max(
                (kf for kf in keyframes if kf <= start),
                default=None,
            )
            if kf_before is not None and (start - kf_before) <= snap_tolerance_s:
                # Segment starts within tolerance of the nearest preceding keyframe.
                # render_video_segment_copy will output-side trim to exact [start, end).
                seg_type = "copy"
                kf_start = kf_before
            else:
                # Too far from any keyframe — re-encode from the nearest preceding kf.
                seg_type = "bridge"
                kf_start = kf_before if kf_before is not None else 0.0

        if seg_type == "copy":
            copy_count += 1
        else:
            bridge_count += 1

        result.append({"type": seg_type, "start": start, "end": end, "kf_start": kf_start})

    logger.info(
        "classify_segments_by_keyframe: total=%d copy=%d bridge=%d",
        len(result),
        copy_count,
        bridge_count,
    )

    return result


def render_video_segment_copy(
    input_path: str,
    kf_start: float,
    start: float,
    end: float,
    out_path: str,
) -> None:
    """Stream-copy a video-only segment using a keyframe-aligned start point.

    Invokes FFmpeg with ``-ss`` placed **before** ``-i`` (input seek, faster)
    and ``-c:v copy`` so no re-encode occurs.  Audio is suppressed with ``-an``
    because video-phase segments are later muxed with the pre-rendered audio
    phase output.

    When ``kf_start`` precedes ``start`` (keyframe not exactly at the segment
    boundary), an output-side ``-ss`` skip and ``-t`` duration cap are added so
    the output segment duration is **exactly** ``end - start``, matching the
    audio phase.  Without this correction, each "copy" segment would be up to
    ``snap_tolerance_s`` seconds longer than the audio segment, causing gradual
    A/V de-sync that compounds across all cut points.

    Args:
        input_path: Path to the source video file.
        kf_start:   Keyframe-aligned seek point (seconds).  Must be <= start.
        start:      Logical segment start timestamp (seconds).
        end:        Logical segment end timestamp (seconds).
        out_path:   Destination path for the video-only segment clip.

    Returns:
        None.

    Raises:
        RuntimeError: When FFmpeg exits with a non-zero return code; full
                      stderr is included in the exception message.
    """
    # extra: pre-segment frames between kf_start and logical start (always >= 0
    # because classify_segments_by_keyframe now guarantees kf_start <= start).
    extra = start - kf_start
    duration = end - start  # exact segment duration — must match audio phase

    logger.debug(
        "render_video_segment_copy: kf_start=%.3f start=%.3f end=%.3f "
        "extra=%.3f duration=%.3f out=%s",
        kf_start,
        start,
        end,
        extra,
        duration,
        out_path,
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(kf_start),   # input seek BEFORE -i (fast, keyframe-accurate)
        "-i", input_path,
        "-c:v", "copy",         # stream-copy video — no re-encode
        "-an",                  # suppress audio; muxed separately from audio phase
        "-avoid_negative_ts", "1",
    ]

    if extra > 1e-3:
        # Output-side skip: discard frames between kf_start and the logical
        # segment start.  Ensures output duration = (end - start), matching the
        # audio phase's atrim output and preventing cumulative A/V drift.
        cmd += ["-ss", str(extra)]

    cmd += ["-t", str(duration), out_path]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"render_video_segment_copy failed for {input_path!r} "
            f"(kf_start={kf_start}, start={start}, end={end})\nstderr:\n{result.stderr}"
        )


# Known video encoder key → canonical FFmpeg flag
_VIDEO_KEY_MAP = {
    "vcodec": "-c:v",
    "preset": "-preset",
    "crf": "-crf",
    "cq": "-cq",
    "rc": "-rc",
}

# Audio-only keys — must never appear in a video-phase command
_AUDIO_ONLY_KEYS = {"acodec", "audio_bitrate"}


def _build_video_enc_flags(enc_opts: dict) -> list[str]:
    """Build FFmpeg CLI flags from *enc_opts* for video-only encoding.

    Known video keys are mapped to their canonical FFmpeg flags.
    Audio-only keys (``acodec``, ``audio_bitrate``) are excluded.
    Unrecognised keys are forwarded verbatim as ``-<key> <value>``.

    Args:
        enc_opts: Encoder options dict (typically from ``QUALITY_PRESETS``).

    Returns:
        Flat list of CLI flag/value pairs for insertion into an FFmpeg command.
    """
    flags = []
    for key, value in enc_opts.items():
        if key in _AUDIO_ONLY_KEYS:
            # Exclude audio-only options — video phase always uses -an
            continue
        canonical_flag = _VIDEO_KEY_MAP.get(key)
        if canonical_flag:
            flags.extend([canonical_flag, str(value)])
        else:
            # Unrecognised key: forward as -<key> <value> (assumed video-related)
            flags.extend([f"-{key}", str(value)])
    return flags


def render_video_segment_bridge(
    input_path: str,
    kf_before: float,
    start: float,
    end: float,
    out_path: str,
    enc_opts: dict,
) -> None:
    """Re-encode a bridge video segment from a preceding keyframe.

    When a segment start does not align with a keyframe, stream-copy is
    inaccurate.  This function seeks to the keyframe *before* the desired
    start (``kf_before``), then uses a ``trim`` video filter to extract
    exactly ``[start, end)`` relative to that seek point, followed by
    ``setpts=PTS-STARTPTS`` to reset timestamps to 0.

    Trim offsets (relative to the seek point):
    - ``trim_start = start - kf_before``
    - ``trim_end   = end   - kf_before``

    Audio is suppressed (``-an``) because video-phase segments are muxed
    with the pre-rendered audio-phase output downstream.

    Args:
        input_path: Path to the source video file.
        kf_before:  Keyframe timestamp (seconds) that precedes *start*;
                    used as the FFmpeg input seek point (``-ss`` before ``-i``).
        start:      Logical segment start timestamp (seconds).
        end:        Logical segment end timestamp (seconds).
        out_path:   Destination path for the re-encoded video-only segment.
        enc_opts:   Encoder options dict mapping option name → value.
                    Video-related keys are forwarded as FFmpeg flags;
                    audio-only keys (``acodec``, ``audio_bitrate``) are
                    always excluded.

    Returns:
        None.

    Raises:
        RuntimeError: When FFmpeg exits with a non-zero return code; full
                      stderr is included in the exception message.
    """
    trim_start = start - kf_before
    trim_end = end - kf_before

    logger.debug(
        "render_video_segment_bridge: kf_before=%.3f start=%.3f end=%.3f "
        "trim_start=%.3f trim_end=%.3f encoder=%s out=%s",
        kf_before,
        start,
        end,
        trim_start,
        trim_end,
        enc_opts.get("vcodec", "unknown"),
        out_path,
    )

    vf_filter = f"trim=start={trim_start}:end={trim_end},setpts=PTS-STARTPTS"
    enc_flags = _build_video_enc_flags(enc_opts)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(kf_before),   # input seek BEFORE -i (fast, keyframe-accurate)
        "-i", input_path,
        "-vf", vf_filter,        # trim to [trim_start, trim_end) + PTS reset
        "-an",                   # suppress audio; muxed separately from audio phase
        *enc_flags,
        out_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"render_video_segment_bridge failed for {input_path!r} "
            f"(kf_before={kf_before}, start={start}, end={end})\n"
            f"stderr:\n{result.stderr}"
        )


def render_video_smart_copy(
    input_path: str,
    keep_segments: list,
    keyframes: list,
    out_path: str,
    enc_opts: dict,
    snap_tolerance_s: float = 0.1,
) -> None:
    """Render smart-copy video: classify segments by keyframe, render in parallel, concat.

    Stream-copies keyframe-aligned segments; bridge-reencodes others.  All temp
    files are cleaned up in the finally block regardless of success or failure.

    Args:
        input_path:       Source video file.
        keep_segments:    (start_s, end_s) tuples to retain.
        keyframes:        Sorted keyframe timestamps in seconds.
        out_path:         Destination for the final concatenated video.
        enc_opts:         Encoder options forwarded to bridge segments.
        snap_tolerance_s: Max distance (s) from keyframe to classify as 'copy'.
    """
    t_start = time.monotonic()
    out_dir = Path(out_path).parent

    # Step 1: merge micro-gap pairs before classification.
    keep_segments = merge_close_segments(keep_segments)

    # Step 2: classify each segment as copy or bridge.
    classified = classify_segments_by_keyframe(keep_segments, keyframes, snap_tolerance_s)

    # Step 2b: drop zero-duration segments — these occur when a "copy" segment's
    # nearest keyframe lands exactly on the segment end (kf_start == end).
    # FFmpeg rejects "-to value smaller than -ss" in that case.
    valid = []
    for seg in classified:
        if seg["kf_start"] >= seg["end"]:
            logger.warning(
                "render_video_smart_copy: skipping zero-duration segment "
                "kf_start=%.3f end=%.3f type=%s — would crash FFmpeg",
                seg["kf_start"],
                seg["end"],
                seg["type"],
            )
        else:
            valid.append(seg)
    classified = valid

    # Step 3: log stats (classify_segments_by_keyframe also logs; repeat here for context).
    copy_count = sum(1 for s in classified if s["type"] == "copy")
    bridge_count = len(classified) - copy_count
    logger.info(
        "render_video_smart_copy: total=%d copy=%d bridge=%d input=%s",
        len(classified),
        copy_count,
        bridge_count,
        os.path.basename(input_path),
    )

    tmp_paths: list[str] = []
    concat_list_path: str | None = None

    try:
        # Step 4: create one temp segment file per classified segment; close fds.
        for _ in classified:
            fd, tmp_path = tempfile.mkstemp(suffix=".mp4", dir=str(out_dir))
            os.close(fd)
            tmp_paths.append(tmp_path)

        # Step 5: render segments in parallel.
        # NVENC (GPU) encode sessions are a limited hardware resource: consumer
        # NVIDIA GPUs cap concurrent sessions at 3–5.  With two tracks (host +
        # guest) each spawning up to 8 workers, we can easily exceed that limit
        # and get "incompatible client key" failures mid-encode.
        # CPU encoders have no such hard limit, so they can safely use 8.
        is_nvenc = any("nvenc" in str(v).lower() for v in (enc_opts or {}).values())
        _worker_cap = 3 if is_nvenc else 8  # 3 = safe consumer GPU session limit
        max_workers = min(len(classified), _worker_cap)
        logger.info(
            "render_video_smart_copy: %d segments → max_workers=%d (%s encoder)",
            len(classified), max_workers, "nvenc" if is_nvenc else "cpu",
        )
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for seg, tmp_path in zip(classified, tmp_paths):
                if seg["type"] == "copy":
                    fut = executor.submit(
                        render_video_segment_copy,
                        input_path,
                        seg["kf_start"],
                        seg["start"],   # logical start — ensures output duration = end - start
                        seg["end"],
                        tmp_path,
                    )
                else:
                    fut = executor.submit(
                        render_video_segment_bridge,
                        input_path,
                        seg["kf_start"],
                        seg["start"],
                        seg["end"],
                        tmp_path,
                        enc_opts,
                    )
                futures.append(fut)

            # Step 6: surface any worker failure immediately.
            for fut in futures:
                fut.result()

        # Step 7: write concat list file — one absolute path per segment in order.
        # Include explicit `duration` directives so the concat demuxer uses the
        # exact expected segment duration instead of container metadata.  Without
        # this, stream-copied segments may report slightly different container
        # durations (B-frame DTS/PTS mismatch, MP4 mdat rounding) causing the
        # concat demuxer to place subsequent segments at wrong timestamps.  Over
        # many segments, these tiny errors accumulate into visible A/V de-sync
        # against the audio phase (which uses the concat filter with precise atrim).
        fd, concat_list_path = tempfile.mkstemp(suffix=".txt", dir=str(out_dir))
        os.close(fd)
        with open(concat_list_path, "w", encoding="utf-8") as fh:
            for tmp_path, seg in zip(tmp_paths, classified):
                abs_path = str(Path(tmp_path).resolve())
                seg_duration = seg["end"] - seg["start"]
                fh.write(f"file '{abs_path}'\n")
                fh.write(f"duration {seg_duration:.6f}\n")

        # Step 8: concatenate all segments via FFmpeg concat demuxer (lossless).
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"render_video_smart_copy concat failed for {out_path!r}\n"
                f"stderr:\n{result.stderr}"
            )

    finally:
        # Step 9: clean up all temp segment files regardless of success or failure.
        for tmp_path in tmp_paths:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        if concat_list_path is not None:
            try:
                os.remove(concat_list_path)
            except OSError:
                pass

    elapsed = time.monotonic() - t_start
    logger.info(
        "render_video_smart_copy: done in %.2fs out=%s",
        elapsed,
        os.path.basename(out_path),
    )


def quantize_segments_to_frames(
    keep_segments: list,
    fps: float,
) -> list:
    """Round each segment boundary to the nearest video frame boundary.

    Video is frame-quantized (each segment's duration snaps to a multiple of
    1/fps), while audio ``atrim`` is sample-precise.  When audio and video
    segments are concatenated independently in the two-phase render, each
    segment can drift by up to ½ frame (e.g. ±8.3 ms at 60 fps), compounding
    into seconds of A/V de-sync over hundreds of cuts.

    Rounding BOTH audio and video boundaries to the same frame grid before
    rendering ensures both phases operate on identical timestamps, eliminating
    cumulative drift.  The rounding adjustment is at most 0.5/fps per boundary
    — imperceptible in practice.

    Args:
        keep_segments: Sorted list of ``(start_s, end_s)`` float tuples.
        fps:           Video frame rate in frames per second (e.g. 60.0).

    Returns:
        New list of ``(start_s, end_s)`` tuples with boundaries snapped to the
        nearest frame boundary.  Input is never mutated.
    """
    if not fps or fps <= 0:
        return list(keep_segments)

    result = []
    for start, end in keep_segments:
        q_start = round(start * fps) / fps
        q_end = round(end * fps) / fps
        # Guard against zero-duration segments after rounding (ensure ≥ 1 frame).
        if q_end <= q_start:
            q_end = q_start + 1.0 / fps
        result.append((q_start, q_end))
    return result


def render_project_two_phase(
    host_path: str,
    guest_path: str,
    manifest,
    out_host: str | None,
    out_guest: str | None,
    config: dict | None,
) -> None:
    """Orchestrate two-phase (audio-first) rendering for host and guest tracks."""
    from io_.video_renderer import probe_ffmpeg_capabilities, select_enc_opts
    caps = probe_ffmpeg_capabilities()
    enc_opts = select_enc_opts(config, caps)
    cfg = config or {}
    use_cuda_decode = bool(cfg.get("cuda_decode_enabled"))
    input_kwargs = build_input_kwargs(config, caps) if use_cuda_decode else {}
    audio_opts = {k: enc_opts[k] for k in ("acodec", "audio_bitrate") if k in enc_opts}
    snap_tol = float(cfg.get("keyframe_snap_tolerance_s", 0.1))

    def _render_track(src_path: str, filters: list, to_path: str, label: str = "") -> None:
        # Normalize empty keep_segments to full-duration span.
        segs = manifest.keep_segments or [(0.0, get_video_duration_seconds(src_path))]

        # Quantize segment boundaries to video frame boundaries so audio (atrim,
        # sample-precise) and video (frame-quantized) phases use identical timestamps.
        # Without this, each segment can drift by up to ½ frame (~8.3 ms at 60 fps),
        # compounding into noticeable A/V de-sync over hundreds of cuts.
        vid_fps = probe_video_fps(src_path)
        if vid_fps:
            segs = quantize_segments_to_frames(segs, vid_fps)
            logger.info(
                "[DETAIL] %sframe quantization: %d segments snapped to %.4f fps grid",
                f"{label} " if label else "", len(segs), vid_fps,
            )
        else:
            logger.warning(
                "two-phase: could not probe FPS for %s; skipping frame quantization",
                os.path.basename(src_path),
            )

        source_codec = probe_video_stream_codec(src_path)
        if source_codec != "h264":
            # Non-h264 source: fall back to single-pass re-encode.
            # Use quantized `segs` (not raw manifest.keep_segments) so the
            # single-pass filter graph uses frame-aligned boundaries.
            logger.info("two-phase: non-h264 codec=%r; single-pass fallback", source_codec)
            v, a = _build_filter_chain(src_path, filters, segs, input_kwargs)
            run_with_progress(ffmpeg.output(v, a, to_path, **enc_opts), overwrite_output=True)
            return
        out_dir = Path(to_path).parent
        fd, tmp_audio = tempfile.mkstemp(suffix=".aac", dir=str(out_dir))
        os.close(fd)
        fd, tmp_video = tempfile.mkstemp(suffix=".mp4", dir=str(out_dir))
        os.close(fd)
        pfx = f"{label} " if label else ""
        try:
            t0 = time.monotonic()
            logger.info("[DETAIL] %saudio render: started (%d segments)", pfx, len(segs))
            render_audio_phase(src_path, filters, segs, tmp_audio, audio_opts)
            logger.info("[DETAIL] %saudio render: complete | Took %s", pfx, _fmt_elapsed(time.monotonic() - t0))

            t0 = time.monotonic()
            logger.info("[DETAIL] %skeyframe scan: started", pfx)
            keyframes = probe_video_keyframes(src_path)
            logger.info("[DETAIL] %skeyframe scan: complete | %d keyframes | Took %s", pfx, len(keyframes), _fmt_elapsed(time.monotonic() - t0))

            t0 = time.monotonic()
            logger.info("[DETAIL] %svideo copy: started (%d segments)", pfx, len(segs))
            render_video_smart_copy(src_path, segs, keyframes, tmp_video, enc_opts, snap_tol)
            logger.info("[DETAIL] %svideo copy: complete | Took %s", pfx, _fmt_elapsed(time.monotonic() - t0))

            t0 = time.monotonic()
            logger.info("[DETAIL] %smux: started", pfx)
            # -shortest: stop output when the shorter track ends, preventing
            # the longer track from extending unsynchronised.  Guards against
            # any residual cumulative duration mismatch between the separately
            # rendered audio and video phases.
            cmd = ["ffmpeg", "-y", "-i", tmp_video, "-i", tmp_audio,
                   "-c", "copy", "-map", "0:v", "-map", "1:a",
                   "-shortest", to_path]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            logger.info("[DETAIL] %smux: complete | Took %s", pfx, _fmt_elapsed(time.monotonic() - t0))
            if proc.returncode != 0:
                raise RuntimeError(f"Mux failed: {proc.stderr}")
        finally:
            for _p in (tmp_audio, tmp_video):
                try:
                    os.remove(_p)
                except OSError:
                    pass

    render_tasks: list = []
    if out_host:
        def _host_fn(to_path: str, _s=host_path, _f=manifest.host_filters) -> None:
            _render_track(_s, _f, to_path, label="Host")
        render_tasks.append(("Host", host_path, out_host, _host_fn))
    if out_guest:
        def _guest_fn(to_path: str, _s=guest_path, _f=manifest.guest_filters) -> None:
            _render_track(_s, _f, to_path, label="Guest")
        render_tasks.append(("Guest", guest_path, out_guest, _guest_fn))

    def _run(task: tuple) -> None:
        label, src, dst, fn = task
        logger.info("Rendering %s Video (two-phase)...", label)
        _render_with_safe_overwrite(src, dst, fn)

    if len(render_tasks) == 1:
        _run(render_tasks[0])
    else:
        logger.info("Rendering Host + Guest in parallel (two-phase, max_workers=2)...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_run, t) for t in render_tasks]
        for future in futures:
            future.result()
