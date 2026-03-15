# io_/video_renderer.py

import ffmpeg
import functools
import os
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from io_.video_renderer_progress import run_with_progress  # noqa: F401 — re-exported for callers
from utils.logger import get_logger

logger = get_logger(__name__)

# Maximum gap between two adjacent keep_segments (seconds) that is considered
# imperceptible by viewers. Segments separated by less than this threshold are
# merged before filter-graph construction, reducing node count by ~20–40%.
# 150 ms is comfortably below the ~200 ms perception floor for podcast cuts
# that land adjacent to an inserted pause (new_pause_duration = 0.8 s).
SEGMENT_GAP_MERGE_THRESHOLD_S = 0.150

# Adaptive merging: when segment count after the base-threshold pass still
# exceeds ADAPTIVE_SEGMENT_COUNT_HIGH, the merge window is widened in 10 ms
# steps until the count falls below ADAPTIVE_SEGMENT_COUNT_TARGET or the
# ceiling ADAPTIVE_SEGMENT_GAP_MAX_S is reached.
ADAPTIVE_SEGMENT_COUNT_HIGH = 150    # trigger adaptive widening above this
ADAPTIVE_SEGMENT_COUNT_TARGET = 100  # desired segment count after widening
ADAPTIVE_SEGMENT_GAP_MAX_S = 0.300   # never widen past 300 ms

# Target number of segments per FFmpeg chunk when chunk-parallel rendering is active.
# When the total segment count exceeds this value, rendering is split into N parallel
# FFmpeg processes (one per chunk) followed by a fast concat-demuxer join pass.
# Override via config key "chunk_size".
CHUNK_SIZE_DEFAULT = 50


def _path_norm_for_compare(p: str) -> str:
    """Normalize a path for equality comparisons (works even if path doesn't exist)."""
    return os.path.normcase(os.path.abspath(p))


def _render_with_safe_overwrite(input_path: str, output_path: str, render: Callable[[str], None]) -> None:
    """Render to `output_path`, safely handling the case where output==input.

    If `output_path` resolves to the same location as `input_path`, we render to a
    temp file *in the output directory* and then atomically replace the original.

    This avoids reading and writing the same path in one FFmpeg invocation.
    """
    if _path_norm_for_compare(input_path) != _path_norm_for_compare(output_path):
        render(output_path)
        return

    out_p = Path(output_path)
    out_dir = out_p.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{out_p.stem}.tmp-",
        suffix=out_p.suffix,
        dir=str(out_dir),
    )
    os.close(fd)

    try:
        logger.info("Output path equals input path; rendering to temp then replacing: %s", tmp_path)
        render(tmp_path)
        os.replace(tmp_path, output_path)
    except Exception:
        # Ensure we don't leave a temp file behind on failure.
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        finally:
            raise


def build_cpu_enc_opts(config):
    """Pure helper to build CPU encoder options for ffmpeg.output()."""
    config = config or {}
    return {
        "vcodec": config.get("video_codec", "libx264"),
        "preset": config.get("video_preset", "fast"),
        "crf": config.get("crf", 23),
        "acodec": config.get("audio_codec", "aac"),
        "audio_bitrate": config.get("audio_bitrate", "192k"),
    }


def build_nvenc_enc_opts(config):
    """
    Pure helper to build NVENC encoder options for ffmpeg.output().
    - NVENC does not support x264/libx264's CRF, so this intentionally omits "crf".
    """
    config = config or {}
    nvenc = config.get("nvenc") or {}

    opts = {
        "vcodec": nvenc.get("codec", "h264_nvenc"),
        "preset": nvenc.get("preset", "p4"),
        "rc": nvenc.get("rc", "vbr"),
        "acodec": config.get("audio_codec", "aac"),
        "audio_bitrate": config.get("audio_bitrate", "192k"),
    }

    cq = nvenc.get("cq", 23)
    if cq is not None:
        opts["cq"] = cq

    return opts


def build_input_kwargs(config, caps):
    """Pure helper returning kwargs for ffmpeg.input()."""
    config = config or {}
    caps = caps or {}
    hwaccels = caps.get("hwaccels") or ()

    cuda_supported = "cuda" in hwaccels
    if config.get("cuda_decode_enabled") and cuda_supported:
        return {"hwaccel": "cuda"}
    return {}


# Modified by gpt-5.2 | 2026-01-09_02
def select_enc_opts(config, caps):
    """
    Select encoder options for ffmpeg.output() based on config + probed FFmpeg caps.
    Rules:
    - If cuda_encode_enabled is False: always CPU encode.
    - If cuda_encode_enabled is True:
        - If NVENC is supported (desired codec present OR at least h264_nvenc):
            Use NVENC opts.
        - Else:
            - If cuda_require_support is True:
                Raise with a clear message.
            - Else:
                Warn (ALL CAPS) and fall back to CPU opts.
    """
    config = config or {}
    caps = caps or {}

    use_cuda_encode = bool(config.get("cuda_encode_enabled"))
    require_support = bool(config.get("cuda_require_support"))

    if not use_cuda_encode:
        return build_cpu_enc_opts(config)

    encoders = set(caps.get("encoders") or ())
    desired_codec = (config.get("nvenc") or {}).get("codec", "h264_nvenc")
    nvenc_supported = desired_codec in encoders or "h264_nvenc" in encoders

    if nvenc_supported:
        enc_opts = build_nvenc_enc_opts(config)

        # If the configured codec isn't present but h264_nvenc is, force a safe default.
        if enc_opts.get("vcodec") not in encoders and "h264_nvenc" in encoders:
            logger.info(
                "NVENC codec not detected (wanted=%s, available=%s); using h264_nvenc",
                enc_opts.get("vcodec"),
                sorted(encoders),
            )
            enc_opts["vcodec"] = "h264_nvenc"

        return enc_opts

    if require_support:
        raise RuntimeError(
            "CUDA/NVENC ENCODE REQUESTED (cuda_encode_enabled=True) BUT NVENC IS NOT AVAILABLE: "
            "FFmpeg encoder h264_nvenc was not found. "
            "Install an FFmpeg build with NVENC support or set cuda_require_support=False."
        )

    logger.warning("CUDA/NVENC REQUESTED BUT NOT AVAILABLE; FALLING BACK TO CPU ENCODE")
    return build_cpu_enc_opts(config)


def _build_filter_chain(
    input_path: str,
    filters: list,
    keep_segments: list,
    input_kwargs: dict,
) -> tuple:
    """Build ffmpeg-python video + audio streams for one input file.

    Extracted from the `build_chain` closure in `render_project` so it can be
    reused by both the single-pass and chunk-parallel rendering paths.

    Returns:
        (v, a) — ffmpeg-python stream specs ready for ffmpeg.output().
    """
    inp = ffmpeg.input(input_path, **input_kwargs)
    v = inp.video
    a = inp.audio

    # Merge adjacent segments separated by an imperceptibly small gap to reduce
    # filter graph complexity (saves ~20-40% of trim/atrim node pairs).
    # Uses adaptive widening automatically when segment count is very high.
    if keep_segments and len(keep_segments) > 1:
        original_count = len(keep_segments)
        keep_segments = merge_close_segments_adaptive(keep_segments)
        merged_away = original_count - len(keep_segments)
        if merged_away:
            logger.info(
                "_build_filter_chain(%s): merged %d micro-gap pair(s); segments %d → %d",
                os.path.basename(str(input_path)),
                merged_away,
                original_count,
                len(keep_segments),
            )

    try:
        filter_names = [getattr(f, "filter_name", str(f)) for f in (filters or [])]
    except Exception:
        filter_names = ["<unprintable>"]
    logger.debug(
        "_build_filter_chain(%s): keep_segments=%s audio_filters=%s",
        os.path.basename(str(input_path)),
        len(keep_segments or []),
        filter_names,
    )

    # 1. Apply Audio Filters (Normalization, etc.)
    for f in filters:
        a = a.filter(f.filter_name, **f.params)

    # 2. Apply Cutting (Trimming)
    if keep_segments:
        segments_v = []
        segments_a = []

        # IMPORTANT:
        # If there are multiple segments, we will create multiple atrim chains.
        # When `a` is the output of an audio filter (e.g., alimiter), ffmpeg-python
        # will throw a graph error unless we insert an `asplit`.
        audio_inputs = None
        if len(keep_segments) > 1 and (filters or []):
            logger.debug(
                "_build_filter_chain(%s): inserting asplit(outputs=%s) before per-segment atrim",
                os.path.basename(str(input_path)),
                len(keep_segments),
            )
            # NOTE: don't call list() on the FilterNode; that can behave like an unbounded iterator.
            split_node = a.filter_multi_output("asplit", outputs=len(keep_segments))
            audio_inputs = [split_node.stream(i) for i in range(len(keep_segments))]

        for idx, (start, end) in enumerate(keep_segments):
            # Video Trim (Reset PTS to start at 0 relative to segment)
            seg_v = v.trim(start=start, end=end).setpts("PTS-STARTPTS")
            segments_v.append(seg_v)

            # Audio Trim (Must match exactly)
            a_in = audio_inputs[idx] if audio_inputs is not None else a
            seg_a = a_in.filter_("atrim", start=start, end=end).filter_("asetpts", "PTS-STARTPTS")
            segments_a.append(seg_a)

        # Concatenate all segments using a single combined concat to guarantee A/V sync.
        # Two separate concat filters (one for video, one for audio) accumulate PTS drift
        # independently across segments: even sub-frame timing differences between a video
        # trim boundary (frame-aligned) and an audio atrim boundary (sample-exact) compound
        # over multiple cuts and produce sped-up or slowed-down playback.
        # A combined concat=n=N:v=1:a=1 with interleaved [v, a] pairs locks video and audio
        # together per-segment inside a single filter, preventing any drift from building up.
        interleaved = []
        for seg_v, seg_a in zip(segments_v, segments_a):
            interleaved.append(seg_v)
            interleaved.append(seg_a)
        concat_out = ffmpeg.concat(*interleaved, v=1, a=1)
        v = concat_out.node[0]  # video output (stream 0)
        a = concat_out.node[1]  # audio output (stream 1)

    return v, a


@functools.lru_cache(maxsize=1)
def probe_ffmpeg_capabilities():
    # Created by gpt-5.2 | 2026-01-09_01
    """Best-effort probe for local FFmpeg capabilities.

    Returns a small dict suitable for unit tests and memoization.

    Shape:
        {
            "ffmpeg_ok": bool,
            "encoders": frozenset[str],   # subset of {"h264_nvenc", "hevc_nvenc"}
            "hwaccels": frozenset[str],   # subset of {"cuda"}
        }
    """
    desired_encoders = {"h264_nvenc", "hevc_nvenc"}
    desired_hwaccels = {"cuda"}

    def _run_ffmpeg_cmd(args):
        return subprocess.run(args, capture_output=True, text=True)

    def _combined_output(proc):
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        return f"{stdout}\n{stderr}".strip()

    def _contains_token(haystack, token):
        return re.search(rf"\b{re.escape(token)}\b", haystack) is not None

    ffmpeg_ok = False
    found_encoders = set()
    found_hwaccels = set()

    try:
        enc_proc = _run_ffmpeg_cmd(["ffmpeg", "-hide_banner", "-encoders"])
        ffmpeg_ok = True
        enc_output = _combined_output(enc_proc)
        for enc in desired_encoders:
            if _contains_token(enc_output, enc):
                found_encoders.add(enc)

        hw_proc = _run_ffmpeg_cmd(["ffmpeg", "-hide_banner", "-hwaccels"])
        hw_output = _combined_output(hw_proc)
        for accel in desired_hwaccels:
            if _contains_token(hw_output, accel):
                found_hwaccels.add(accel)
    except (FileNotFoundError, OSError) as e:
        logger.info("FFmpeg not available for probing (%s); treating GPU capabilities as absent", e)
        return {"ffmpeg_ok": False, "encoders": frozenset(), "hwaccels": frozenset()}

    logger.debug(
        "FFmpeg probe result: ffmpeg_ok=%s encoders=%s hwaccels=%s",
        ffmpeg_ok,
        sorted(found_encoders),
        sorted(found_hwaccels),
    )

    if "cuda" in found_hwaccels or found_encoders:
        logger.info(
            "Detected FFmpeg GPU capabilities: encoders=%s hwaccels=%s",
            sorted(found_encoders),
            sorted(found_hwaccels),
        )
    else:
        logger.info("No FFmpeg CUDA/NVENC capabilities detected")

    return {
        "ffmpeg_ok": ffmpeg_ok,
        "encoders": frozenset(found_encoders),
        "hwaccels": frozenset(found_hwaccels),
    }


def merge_close_segments(
    keep_segments: list,
    gap_threshold_s: float = SEGMENT_GAP_MERGE_THRESHOLD_S,
) -> list:
    """Merge adjacent keep_segments whose inter-segment gap is below *gap_threshold_s*.

    A gap smaller than 80 ms is imperceptible to viewers.  Merging across those
    micro-gaps eliminates the corresponding trim/atrim pairs from the FFmpeg filter
    graph, reducing node count by roughly 20–40 % on typical podcast recordings
    with zero perceptible quality impact.

    Example
    -------
    >>> merge_close_segments([(10.0, 12.5), (12.56, 15.0)], gap_threshold_s=0.080)
    [(10.0, 15.0)]   # 60 ms gap → merged

    Args:
        keep_segments:   Sorted list of (start, end) float tuples (seconds).
        gap_threshold_s: Gaps strictly below this value (in seconds) are bridged.
                         Default is SEGMENT_GAP_MERGE_THRESHOLD_S (80 ms).

    Returns:
        New list of (start, end) tuples; input is never mutated.
    """
    if not keep_segments or len(keep_segments) < 2:
        return list(keep_segments) if keep_segments else []

    merged = []
    current_start, current_end = keep_segments[0]

    for next_start, next_end in keep_segments[1:]:
        gap = next_start - current_end
        if gap < gap_threshold_s:
            # Bridge the micro-gap: extend current segment rightward.
            current_end = max(current_end, next_end)
        else:
            merged.append((current_start, current_end))
            current_start, current_end = next_start, next_end

    merged.append((current_start, current_end))
    return merged


def merge_close_segments_adaptive(
    keep_segments: list,
    base_threshold_s: float = SEGMENT_GAP_MERGE_THRESHOLD_S,
    high_count: int = ADAPTIVE_SEGMENT_COUNT_HIGH,
    target_count: int = ADAPTIVE_SEGMENT_COUNT_TARGET,
    max_threshold_s: float = ADAPTIVE_SEGMENT_GAP_MAX_S,
    step_s: float = 0.010,
) -> list:
    """Merge close segments with optional adaptive threshold widening.

    First pass uses *base_threshold_s* (150 ms).  If the merged segment count
    still exceeds *high_count* (150), the threshold is incremented by *step_s*
    (10 ms) each iteration until the count falls below *target_count* (100) or
    *max_threshold_s* (300 ms) is reached — whichever comes first.

    The adaptive path trades a tiny amount of extra audio continuity for a
    significantly simpler FFmpeg filter graph, which reduces render time and
    avoids the "Too many filters" error on very long recordings.

    Args:
        keep_segments:    Sorted (start, end) tuples in seconds.
        base_threshold_s: Starting merge threshold (default 150 ms).
        high_count:       Segment count that triggers adaptive widening.
        target_count:     Desired segment count after adaptive passes.
        max_threshold_s:  Hard ceiling on the merge window (default 300 ms).
        step_s:           Threshold increment per adaptive step (10 ms).

    Returns:
        Merged segment list; may be shorter than input.  Input is never mutated.
    """
    if not keep_segments or len(keep_segments) < 2:
        return list(keep_segments) if keep_segments else []

    result = merge_close_segments(keep_segments, gap_threshold_s=base_threshold_s)

    # Fast path: base threshold reduced the count to an acceptable level.
    if len(result) < high_count:
        return result

    # Adaptive widening: widen the threshold in small steps until target is met.
    threshold = base_threshold_s + step_s
    while len(result) >= target_count and threshold <= max_threshold_s:
        result = merge_close_segments(keep_segments, gap_threshold_s=threshold)
        threshold += step_s

    final_threshold_ms = (threshold - step_s) * 1000
    logger.info(
        "merge_close_segments_adaptive: high segment count triggered adaptive widening; "
        "final threshold=%.0f ms, segments %d → %d",
        final_threshold_ms,
        len(keep_segments),
        len(result),
    )
    return result


def partition_segments(segments: list, chunk_size: int) -> list:
    """Split a flat segment list into sub-lists of at most *chunk_size* each.

    Used by _render_as_chunks() to divide work across parallel FFmpeg processes.
    Each sub-list preserves the original segment ordering and absolute timestamps.

    Args:
        segments:   Sorted list of (start, end) tuples.
        chunk_size: Maximum number of segments per chunk.  Values < 1 are treated
                    as "no chunking" and the entire list is returned as one chunk.

    Returns:
        List of sub-lists.  Always returns at least one sub-list when segments is
        non-empty.  Returns [] when segments is empty.

    Examples:
        >>> partition_segments([(0, 1), (1, 2), (2, 3)], chunk_size=2)
        [[(0, 1), (1, 2)], [(2, 3)]]
        >>> partition_segments([], chunk_size=50)
        []
    """
    if not segments:
        return []
    if chunk_size < 1:
        # Degenerate guard: treat all as one chunk.
        return [list(segments)]
    return [segments[i:i + chunk_size] for i in range(0, len(segments), chunk_size)]


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed seconds as HH:MM:SS for progress display."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _render_as_chunks(
    input_path: str,
    filters: list,
    keep_segments: list,
    out_path: str,
    enc_opts: dict,
    input_kwargs: dict,
    chunk_size: int,
    label: str = "",
) -> None:
    """Render by splitting keep_segments into N parallel FFmpeg chunk processes.

    Strategy
    --------
    1. Partition keep_segments into N groups of ≤ chunk_size each.
    2. Spawn one FFmpeg process per chunk in parallel (ThreadPoolExecutor).
       Each chunk opens the same source file and renders its subset of segments
       using a combined concat=v=1:a=1 filter for guaranteed A/V sync within chunk.
    3. Join chunk files with the concat demuxer (-f concat -c copy) — stream
       copy, no re-encode, essentially free wall-clock time.

    Temp chunk files are cleaned up unconditionally (success or failure).
    """
    chunks = partition_segments(keep_segments, chunk_size)
    n = len(chunks)
    logger.info(
        "Chunked parallel render: %d segments → %d chunks of ≤%d segs  [%s]",
        len(keep_segments), n, chunk_size, os.path.basename(input_path),
    )

    out_p = Path(out_path)
    chunk_paths: list[str] = []
    for i in range(n):
        fd, cp = tempfile.mkstemp(
            prefix=f".chunk{i:02d}.",
            suffix=out_p.suffix,
            dir=str(out_p.parent),
        )
        os.close(fd)
        chunk_paths.append(cp)

    concat_list_path: str | None = None
    try:
        def _render_chunk(args: tuple) -> None:
            """Render one chunk to its temp file (runs in a thread)."""
            idx, chunk_segs = args
            chunk_out = chunk_paths[idx]
            pfx = f"{label} " if label else ""
            print(f"\n=== {pfx}Chunk {idx + 1}/{n}: {len(chunk_segs)} segments ===", flush=True)
            logger.info("[DETAIL] %sChunk %d of %d start", pfx, idx + 1, n)
            chunk_start = time.time()
            v, a = _build_filter_chain(input_path, filters, chunk_segs, input_kwargs)
            stream = ffmpeg.output(v, a, chunk_out, **enc_opts)
            logger.info("Chunk %d/%d: rendering %d segs → %s", idx + 1, n, len(chunk_segs), chunk_out)
            run_with_progress(stream, overwrite_output=True)
            elapsed = _fmt_elapsed(time.time() - chunk_start)
            logger.info("[DETAIL] %sChunk %d of %d complete - Took %s", pfx, idx + 1, n, elapsed)

        logger.info("Running %d chunk FFmpeg processes in parallel...", n)
        with ThreadPoolExecutor(max_workers=n) as executor:
            futures = [executor.submit(_render_chunk, (i, chunks[i])) for i in range(n)]
        # Surface any exception from a chunk worker
        for future in futures:
            future.result()

        # Write concat list (absolute forward-slash paths; -safe 0 allows absolute paths)
        fd2, concat_list_path = tempfile.mkstemp(
            suffix=".txt", prefix="concat_list_", dir=str(out_p.parent)
        )
        os.close(fd2)
        with open(concat_list_path, "w", encoding="utf-8") as fh:
            for cp in chunk_paths:
                safe_path = str(Path(cp).absolute()).replace("\\", "/")
                fh.write(f"file '{safe_path}'\n")

        # Final concat pass: stream copy (no re-encode, fast)
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            out_path,
        ]
        pfx = f"{label} " if label else ""
        logger.info("[DETAIL] %sChunk concat: joining %d chunks", pfx, n)
        logger.info("Chunk concat pass: joining %d chunks → %s", n, out_path)
        concat_start = time.time()
        proc = subprocess.run(concat_cmd, capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0:
            raise RuntimeError(
                f"Chunk concat demuxer failed (rc={proc.returncode}):\n{proc.stderr}"
            )
        elapsed = _fmt_elapsed(time.time() - concat_start)
        logger.info("Chunk concat complete → %s", out_path)
        logger.info("[DETAIL] %sChunk concat complete - Took %s", pfx, elapsed)

    finally:
        # Clean up all chunk temp files unconditionally
        for cp in chunk_paths:
            try:
                if os.path.exists(cp):
                    os.remove(cp)
            except OSError:
                pass
        if concat_list_path:
            try:
                os.remove(concat_list_path)
            except OSError:
                pass


# [Modified] by gpt-5.2 | 2026-01-09_03
def render_project(host_path, guest_path, manifest, out_host, out_guest, config):
    """
    Constructs and executes the FFmpeg graph.
    Cuts video and audio simultaneously to guarantee sync.

    When the segment count exceeds `chunk_size` (from config, default 50), chunk-parallel
    rendering splits the work across N FFmpeg processes then joins results with a concat-demuxer
    pass for significant wall-clock speedup on videos with many cuts.
    """
    caps = probe_ffmpeg_capabilities()

    # [Modified] by gpt-5.2 | 2026-01-09_03
    # Best-effort CUDA decode is applied ONLY at ffmpeg.input(...) time.
    # NOTE: The rest of the filter graph remains CPU-side.
    use_cuda_decode = bool((config or {}).get("cuda_decode_enabled"))
    input_kwargs = build_input_kwargs(config, caps) if use_cuda_decode else {}
    if use_cuda_decode and input_kwargs:
        logger.warning(
            "CUDA HWACCEL DECODE ENABLED; FILTER GRAPH IS CPU-SIDE SO DECODE SPEEDUPS MAY BE LIMITED"
        )

    if not out_host and not out_guest:
        raise ValueError("render_project() requires at least one output (out_host or out_guest)")

    # Common Output Settings
    enc_opts = select_enc_opts(config, caps)

    logger.info(
        "Selected encoder options: vcodec=%s preset=%s crf=%s cq=%s rc=%s acodec=%s audio_bitrate=%s",
        enc_opts.get("vcodec"),
        enc_opts.get("preset"),
        enc_opts.get("crf"),
        enc_opts.get("cq"),
        enc_opts.get("rc"),
        enc_opts.get("acodec"),
        enc_opts.get("audio_bitrate"),
    )

    cfg = config or {}

    # Two-phase render dispatch (audio-first + smart video copy).
    # NOTE: probe_ffmpeg_capabilities() is LRU-cached; select_enc_opts() above is
    # redundant when two-phase is active, but cost is negligible.
    if cfg.get("two_phase_render_enabled"):
        from io_.video_renderer_twophase import render_project_two_phase

        logger.info("Two-phase render ACTIVE (audio-first + smart video copy)")
        out_count = sum(1 for o in (out_host, out_guest) if o)
        logger.info(
            "[DETAIL] Encoding strategy: two-phase (audio-first + smart copy) × %d video(s)",
            out_count,
        )
        return render_project_two_phase(
            host_path, guest_path, manifest, out_host, out_guest, config
        )

    # Determine if chunk-parallel rendering should be used.
    # Activates when segment count exceeds chunk_size (guarantees ≥ 2 chunks).
    chunk_enabled = bool(cfg.get("chunk_parallel_enabled", True))
    chunk_size = int(cfg.get("chunk_size", CHUNK_SIZE_DEFAULT))
    n_segs = len(manifest.keep_segments or [])
    use_chunks = chunk_enabled and chunk_size > 0 and n_segs > chunk_size

    out_count = sum(1 for o in (out_host, out_guest) if o)
    if use_chunks:
        n_chunks = (n_segs + chunk_size - 1) // chunk_size
        logger.info(
            "Chunk-parallel rendering ACTIVE: %d segments, chunk_size=%d → %d chunks",
            n_segs, chunk_size, n_chunks,
        )
        logger.info(
            "[DETAIL] Encoding strategy: chunk-parallel | %d segments → %d chunks × %d video(s)",
            n_segs, n_chunks, out_count,
        )
    else:
        logger.info(
            "[DETAIL] Encoding strategy: single-pass | %d segments × %d video(s)",
            n_segs, out_count,
        )

    # Collect render tasks so we can run host+guest in parallel (existing behaviour).
    # Each task is a completely independent FFmpeg subprocess writing to a different
    # file, so there is zero sync risk.
    render_tasks: list[tuple[str, str, str, Callable[[str], None]]] = []

    if out_host:
        def _render_host(to_path: str) -> None:
            if use_chunks:
                _render_as_chunks(
                    host_path, manifest.host_filters, manifest.keep_segments,
                    to_path, enc_opts, input_kwargs, chunk_size, label="Host",
                )
            else:
                h_v, h_a = _build_filter_chain(
                    host_path, manifest.host_filters, manifest.keep_segments, input_kwargs
                )
                stream = ffmpeg.output(h_v, h_a, to_path, **enc_opts)
                run_with_progress(stream, overwrite_output=True)
        render_tasks.append(("Host", host_path, out_host, _render_host))

    if out_guest:
        def _render_guest(to_path: str) -> None:
            if use_chunks:
                _render_as_chunks(
                    guest_path, manifest.guest_filters, manifest.keep_segments,
                    to_path, enc_opts, input_kwargs, chunk_size, label="Guest",
                )
            else:
                g_v, g_a = _build_filter_chain(
                    guest_path, manifest.guest_filters, manifest.keep_segments, input_kwargs
                )
                stream = ffmpeg.output(g_v, g_a, to_path, **enc_opts)
                run_with_progress(stream, overwrite_output=True)
        render_tasks.append(("Guest", guest_path, out_guest, _render_guest))

    def _run_render_task(task: tuple[str, str, str, Callable[[str], None]]) -> None:
        """Execute a single (label, src, dst, render_fn) render task."""
        label, src, dst, fn = task
        logger.info("Rendering %s Video...", label)
        logger.info("[DETAIL] %s video: encoding started", label)
        task_start = time.time()
        _render_with_safe_overwrite(src, dst, fn)
        elapsed = _fmt_elapsed(time.time() - task_start)
        logger.info("[DETAIL] %s video: encoding complete | Took %s", label, elapsed)

    if len(render_tasks) == 1:
        # Only one output requested — skip threading overhead.
        _run_render_task(render_tasks[0])
    else:
        # Both outputs requested — run in parallel for ~2× wall-clock speedup.
        logger.info("Rendering Host + Guest Videos in parallel (ThreadPoolExecutor max_workers=2)...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_run_render_task, t) for t in render_tasks]
        # executor.__exit__ blocks until both threads finish; now surface any exceptions.
        for future in futures:
            future.result()
