# io_/video_renderer_progress.py
"""FFmpeg progress reporting and filter_complex script offloading.

Extracted from io_/video_renderer.py to keep that module under the 600-line limit.

Public API (also re-exported from video_renderer for backward compatibility):
  - run_with_progress()
  - _maybe_offload_filter_complex()
"""

import ffmpeg
import os
import subprocess
import tempfile
import time

from utils.logger import get_logger

logger = get_logger(__name__)


def _maybe_offload_filter_complex(cmd_args: list) -> tuple[list, str | None]:
    """If cmd_args contains -filter_complex, write its value to a temp file and
    replace it with -filter_complex_script <tmpfile>.

    This avoids WinError 206 (command line too long) when many segments produce a
    very large filter graph string.  Returns (new_cmd_args, tmp_path).  If no
    -filter_complex arg is present, returns (cmd_args, None) unchanged.
    """
    try:
        fc_idx = cmd_args.index("-filter_complex")
    except ValueError:
        return cmd_args, None

    fc_content = cmd_args[fc_idx + 1]
    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="ffmpeg_fc_")
    try:
        os.close(fd)
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(fc_content)
    except Exception:
        # If we can't write the file, fall back to the original command.
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return cmd_args, None

    new_cmd = cmd_args[:fc_idx] + ["-filter_complex_script", tmp_path] + cmd_args[fc_idx + 2:]
    logger.info(
        "Offloaded filter_complex (%d chars, %d lines) to temp file: %s",
        len(fc_content),
        fc_content.count(";") + 1,
        tmp_path,
    )
    return new_cmd, tmp_path


# Modified by gpt-5.2 | 2026-01-12_01
def run_with_progress(stream_spec, **kwargs):
    """
    Runs ffmpeg with a custom progress parser that displays a table.
    Columns: Frame, FPS, Q, Size, Progress (time), Bitrate, Speed, Elapsed.

    Uses -progress pipe:1 for machine-readable output with proper newlines,
    and flush=True on all prints for immediate GUI display.
    """
    cmd_args = ffmpeg.compile(stream_spec, **kwargs)
    # Add -progress for machine-readable newline-delimited output
    # Add -nostats to suppress the normal stderr progress line
    cmd_args = cmd_args + ["-progress", "pipe:1", "-nostats"]

    # Offload -filter_complex to a temp file to avoid WinError 206 (Windows
    # command-line length limit) when many segments produce a huge filter graph.
    cmd_args, _fc_tmp = _maybe_offload_filter_complex(cmd_args)

    logger.info(f"Running FFmpeg: {' '.join(cmd_args)}")

    start_time = time.time()

    # Table Header - pinned at top
    headers = ["Frame", "FPS", "Q", "Size", "Progress", "Bitrate", "Speed", "Elapsed"]
    row_fmt = "{:<8} {:<8} {:<6} {:<10} {:<12} {:<12} {:<8} {:<10}"

    print("-" * 80, flush=True)
    print(row_fmt.format(*headers), flush=True)
    print("-" * 80, flush=True)

    # NOTE:
    # - We merge stderr into stdout to avoid deadlocks if FFmpeg writes enough to fill the stderr pipe.
    # - This also matches how the GUI reads output (stdout only) in [`AVCleanerGUI.run_processing()`](ui/gui_app.py:262).
    try:
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1  # Line-buffered
        )

        assert process.stdout is not None

        # -progress outputs key=value pairs, one per line.
        # We collect them and print a row when we see "progress=continue" or "progress=end".
        stats = {}
        last_print_time = 0.0
        UPDATE_INTERVAL = 0.25  # Throttle to ~4 updates/sec for GUI smoothness

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            if "=" in line:
                key, _, value = line.partition("=")
                stats[key] = value

                # When we see progress=continue or progress=end, we have a full update
                if key == "progress":
                    current_time = time.time()
                    # Throttle output for GUI performance
                    if current_time - last_print_time >= UPDATE_INTERVAL or value == "end":
                        elapsed = current_time - start_time
                        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))

                        # Format size from bytes to kB
                        try:
                            size_bytes = int(stats.get("total_size", 0))
                            size_str = f"{size_bytes // 1024}kB"
                        except (ValueError, TypeError):
                            size_str = stats.get("total_size", "N/A")

                        # Find Q value (stream_0_0_q or similar)
                        q_val = "-"
                        for k, v in stats.items():
                            if k.endswith("_q"):
                                q_val = v
                                break

                        # out_time is in format HH:MM:SS.microseconds
                        progress_time = stats.get("out_time", "00:00:00")
                        # Truncate microseconds for cleaner display
                        if "." in progress_time:
                            progress_time = progress_time.split(".")[0]

                        print(row_fmt.format(
                            stats.get("frame", "0"),
                            stats.get("fps", "0"),
                            q_val,
                            size_str,
                            progress_time,
                            stats.get("bitrate", "N/A"),
                            stats.get("speed", "N/A"),
                            elapsed_str
                        ), flush=True)
                        last_print_time = current_time
            else:
                # Non key=value line - likely FFmpeg banner/warnings.
                # Keep the table clean; only print likely-fatal messages.
                lowered = line.lower()
                if "error" in lowered or "invalid" in lowered or "failed" in lowered:
                    print(line, flush=True)

        returncode = process.wait()
        if returncode != 0:
            logger.error(f"FFmpeg failed with return code {returncode}")
            raise ffmpeg.Error("ffmpeg", returncode, cmd=cmd_args)

        # Provide an explicit end/summary message (the old FFmpeg stderr stats line effectively did this).
        total_elapsed = time.time() - start_time
        total_elapsed_str = time.strftime("%H:%M:%S", time.gmtime(total_elapsed))

        # Created by gpt-5.2 | 2026-01-12_01
        def _format_bytes(n: int) -> str:
            if n < 0:
                return "N/A"
            if n < 1024:
                return f"{n}B"
            if n < 1024 * 1024:
                return f"{n / 1024:.1f}kB"
            if n < 1024 * 1024 * 1024:
                return f"{n / (1024 * 1024):.1f}MB"
            return f"{n / (1024 * 1024 * 1024):.2f}GB"

        try:
            final_size_bytes = int(stats.get("total_size", 0))
            final_size_str = _format_bytes(final_size_bytes)
        except (ValueError, TypeError):
            final_size_str = "N/A"

        print("-" * 80, flush=True)
        print(
            f"FFmpeg complete | elapsed={total_elapsed_str} | final_size={final_size_str} | avg_bitrate={stats.get('bitrate', 'N/A')}",
            flush=True,
        )
    finally:
        # Clean up the temp filter_complex_script file if one was created.
        if _fc_tmp:
            try:
                os.remove(_fc_tmp)
            except OSError:
                pass
