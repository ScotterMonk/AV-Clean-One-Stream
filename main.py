# main.py

import copy
import logging
import os
import sys
import time

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
from io_.media_preflight import normalize_video_lengths
from io_.media_probe import get_video_duration_seconds
from processors.spike_fixer import SpikeFixer
from processors.audio_normalizer import AudioNormalizer
from processors.segment_remover import SegmentRemover
from processors.word_muter import WordMuter
from config import QUALITY_PRESETS, PIPELINE_CONFIG
from utils.logger import format_duration, format_time_cut, setup_logger


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


def _run_process(host: str, guest: str, norm_mode: str | None, action: str | None) -> None:
    """
    Video Automation Tool: Sync-safe cleaning and normalization.
    """
    from pathlib import Path
    from utils.progress_log import ProgressLogHandler, progress_log_path
    
    # Initialize logger with progress log handler
    logger = setup_logger()
    
    # Add progress log handler to capture all PROGRESS pane lines
    project_dir = Path(host).resolve().parent
    log_path = progress_log_path(project_dir)
    progress_handler = ProgressLogHandler(log_path)
    progress_handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger("video_trimmer").addHandler(progress_handler)
    
    run_start_time = time.time()
    logger.info("[RUN START] FULL_PIPELINE")

    # Preserve user-selected inputs for reporting, even if preflight normalizes to new paths.
    original_host = host
    original_guest = guest

    # Backwards-compat CLI flag: older docs/scripts used --action ALL.
    if action not in (None, 'ALL'):
        raise click.ClickException(
            "Only --action ALL is supported (the action concept has been removed)."
        )

    # Preflight: ensure host+guest durations are aligned for all actions (even guest-only).
    host, guest = normalize_video_lengths(host, guest)
     
    # Load Config
    config = copy.deepcopy(QUALITY_PRESETS['PODCAST_HIGH_QUALITY'])
    if norm_mode:
        config['normalization']['mode'] = norm_mode

    # Init Pipeline
    pipeline = _build_pipeline(config)
 
    # Run
    try:
        # Always render both host+guest outputs so the GUI/CLI can reliably switch to
        # a stable processed pair after any action (even guest-only workflows).
        h_out, g_out = pipeline.execute(host, guest)

        created = [p for p in [h_out, g_out] if p]

        def _probe_duration_label(path: str | None) -> str:
            if not path:
                return "N/A"
            try:
                return format_time_cut(get_video_duration_seconds(path))
            except Exception:
                return "N/A"

        logger.info(
            "[RUN SUMMARY] ORIGINAL FILES - Host length: %s, Guest length: %s",
            _probe_duration_label(original_host),
            _probe_duration_label(original_guest),
        )
        logger.info(
            "[RUN SUMMARY] PROCESSED FILES - Host length: %s, Guest length: %s",
            _probe_duration_label(h_out),
            _probe_duration_label(g_out),
        )

        action_duration = time.time() - run_start_time
        logger.info(f"[RUN COMPLETE] FULL_PIPELINE - Took {format_duration(action_duration)}")

        logger.info("Success! Files created:\n" + "\n".join(created))
        logger.info(f"[RESULT] host={h_out} guest={g_out}")
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}")
        raise


@click.group(invoke_without_command=True)
@click.option('--host', required=False, help='Host video path')
@click.option('--guest', required=False, help='Guest video path')
@click.option(
    '--action',
    type=click.Choice(['ALL']),
    default=None,
    help='(Deprecated) Old interface. Only ALL is supported.',
)
@click.option(
    '--norm-mode',
    type=click.Choice(['MATCH_HOST', 'STANDARD_LUFS']),
    help='Override normalization mode',
)
@click.pass_context
def cli(ctx: click.Context, host: str | None, guest: str | None, action: str | None, norm_mode: str | None):
    """Video Automation Tool: Sync-safe cleaning and normalization."""
    if ctx.invoked_subcommand is not None:
        return

    if not host or not guest:
        raise click.UsageError(
            "Missing required options: --host and --guest. Try: main.py process --help"
        )

    _run_process(host=host, guest=guest, norm_mode=norm_mode, action=action)


# Backwards-compatible entry point used by older tests/scripts.
# (Click commands are regular callables; `CliRunner.invoke()` can target this.)
main = cli


@cli.command(name='process')
@click.option('--host', required=True, help='Host video path')
@click.option('--guest', required=True, help='Guest video path')
@click.option(
    '--action',
    type=click.Choice(['ALL']),
    default=None,
    help='(Deprecated) Old interface. Only ALL is supported.',
)
@click.option(
    '--norm-mode',
    type=click.Choice(['MATCH_HOST', 'STANDARD_LUFS']),
    help='Override normalization mode',
)
def process(host: str, guest: str, action: str | None, norm_mode: str | None):
    """Run the full processing pipeline."""
    _run_process(host=host, guest=guest, norm_mode=norm_mode, action=action)

if __name__ == '__main__':
    cli()
