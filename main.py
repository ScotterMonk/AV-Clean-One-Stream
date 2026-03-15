# main.py

import copy
import logging
import os
import sys
import time
from pathlib import Path

# Ensure current directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import click

from utils.env_loader import env_file_load

env_file_load()

from core.pipeline import ProcessingPipeline
from detectors.audio_level_detector import AudioLevelDetector
from detectors.cross_talk_detector import CrossTalkDetector
from detectors.filler_word_detector import FillerWordDetector
from detectors.spike_fixer_detector import SpikeFixerDetector
from io_.media_probe import get_video_duration_seconds
from processors.spike_fixer import SpikeFixer
from processors.audio_normalizer import AudioNormalizer
from processors.segment_remover import SegmentRemover
from processors.word_muter import WordMuter
from config import QUALITY_PRESETS, PIPELINE_CONFIG
from utils.logger import format_duration, format_time_cut, setup_logger

# ---------------------------------------------------------------------------
# PERMANENTLY REMOVED OPTIONS — do NOT re-add these to the CLI or this module:
#   --host        (replaced by --input; dual-stream concept removed)
#   --guest       (replaced by --input; dual-stream concept removed)
#   --action      (deprecated compatibility shim; action concept removed)
#   --norm-mode   (runtime LUFS override removed; configure via config.py)
# ---------------------------------------------------------------------------


_PROCESSOR_REGISTRY = {
    "SegmentRemover": SegmentRemover,
    "WordMuter":      WordMuter,
    "AudioNormalizer": AudioNormalizer,
    "SpikeFixer":     SpikeFixer,
}


def _pipeline_component_enabled(group: str, type_name: str) -> bool:
    """Return True when PIPELINE_CONFIG[group] has an enabled entry for type_name."""
    for entry in PIPELINE_CONFIG.get(group, []):
        if str(entry.get("type")) == type_name:
            return bool(entry.get("enabled"))
    return False


def _register_enabled_processors(pipeline: ProcessingPipeline, config: dict) -> None:
    """Register enabled processors (user-facing). Required detectors are added automatically."""
    for entry in PIPELINE_CONFIG.get("processors", []):
        if not entry.get("enabled"):
            continue
        t = str(entry.get("type"))
        cls = _PROCESSOR_REGISTRY.get(t)
        if cls is None:
            raise click.ClickException(f"Unknown processor type in PIPELINE_CONFIG: {t!r}")
        pipeline.add_processor(cls(config))


def _register_required_detectors(pipeline: ProcessingPipeline) -> None:
    """Add detectors implied by enabled processors (not user-facing)."""
    logger = logging.getLogger("video_trimmer")
    detector_order: list[str] = []

    # Detector registration order matters for analysis/processing dependencies.
    # Required order (when enabled): AudioLevelDetector -> SpikeFixerDetector -> FillerWordDetector -> CrossTalkDetector

    # AudioNormalizer needs per-frame audio level analysis (for normalization decisions).
    if _pipeline_component_enabled("processors", "AudioNormalizer"):
        pipeline.add_detector(AudioLevelDetector(pipeline.config))
        detector_order.append("AudioLevelDetector")

    # SpikeFixer requires spike detection.
    if _pipeline_component_enabled("processors", "SpikeFixer"):
        pipeline.add_detector(SpikeFixerDetector(pipeline.config))
        detector_order.append("SpikeFixerDetector")

    # WordMuter requires word-level transcription detection.
    # Must run before CrossTalkDetector so filler_word_detector results
    # are available for self-healing mute analysis.
    if _pipeline_component_enabled("processors", "WordMuter"):
        pipeline.add_detector(FillerWordDetector(pipeline.config))
        detector_order.append("FillerWordDetector")

    # SegmentRemover requires mutual-silence detection.
    if _pipeline_component_enabled("processors", "SegmentRemover"):
        pipeline.add_detector(CrossTalkDetector(pipeline.config))
        detector_order.append("CrossTalkDetector")

    if detector_order:
        logger.info(
            "[PIPELINE] Required detectors registered (in order): %s",
            " -> ".join(detector_order),
        )
    else:
        logger.info("[PIPELINE] No required detectors registered.")


def _build_pipeline(config: dict) -> ProcessingPipeline:
    pipeline = ProcessingPipeline(config)
    _register_enabled_processors(pipeline, config)
    _register_required_detectors(pipeline)
    return pipeline


def _run_process(input_path: str) -> None:
    """
    Single-stream video cleaning and normalization pipeline.

    Accepts one input video file, runs all enabled processors (audio
    normalization, spike fixing, filler-word muting, segment removal),
    and writes a single cleaned output file.
    """
    from utils.progress_log import ProgressLogHandler, progress_log_path

    # Initialize logger with progress log handler
    logger = setup_logger()

    # Resolve project directory from the input file location
    project_dir = Path(input_path).resolve().parent
    log_path = progress_log_path(project_dir)
    progress_handler = ProgressLogHandler(log_path)
    progress_handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger("video_trimmer").addHandler(progress_handler)

    run_start_time = time.time()
    logger.info("[RUN START] FULL_PIPELINE")

    # Load config
    config = copy.deepcopy(QUALITY_PRESETS['PODCAST_HIGH_QUALITY'])

    # Init pipeline
    pipeline = _build_pipeline(config)

    # Run
    try:
        output_path = pipeline.execute(input_path)

        def _probe_duration_label(path: str | None) -> str:
            if not path:
                return "N/A"
            try:
                return format_time_cut(get_video_duration_seconds(path))
            except Exception:
                return "N/A"

        logger.info(
            "[RUN SUMMARY] ORIGINAL FILE - Length: %s",
            _probe_duration_label(input_path),
        )
        logger.info(
            "[RUN SUMMARY] PROCESSED FILE - Length: %s",
            _probe_duration_label(output_path),
        )

        action_duration = time.time() - run_start_time
        logger.info(f"[RUN COMPLETE] FULL_PIPELINE - Took {format_duration(action_duration)}")

        if output_path:
            logger.info("Success! File created: %s", output_path)
        logger.info(f"[RESULT] output={output_path}")
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}")
        raise


@click.group(invoke_without_command=True)
@click.option('--input', 'input_path', required=False, help='Input video path to clean and normalize')
@click.pass_context
def cli(ctx: click.Context, input_path: str | None):
    """Single-stream video cleaning and normalization tool."""
    if ctx.invoked_subcommand is not None:
        return

    if not input_path:
        raise click.UsageError(
            "Missing required option: --input. Try: main.py process --help"
        )

    _run_process(input_path=input_path)


# Entry point alias (Click commands are regular callables; CliRunner.invoke() can target this).
main = cli


@cli.command(name='process')
@click.option('--input', 'input_path', required=True, help='Input video path to clean and normalize')
def process(input_path: str):
    """Run the full single-stream cleaning and normalization pipeline."""
    _run_process(input_path=input_path)


if __name__ == '__main__':
    cli()
