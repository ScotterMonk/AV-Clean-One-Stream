# AV Cleaner
by Scott Howard Swain

## Application overview
Automates cleanup of a single recorded video while keeping that video's audio and video in sync.

Features:
- **Removes filler words**: Detects configured filler words from `config.py` and mutes them during processing. Depending on surrounding silence, those muted spans can also be shortened by pause removal.
- **Normalizes loudness**: Applies the configured single-track loudness workflow to the input video's audio.
- **Reduces volume spikes**: Detects and corrects sharp peaks in the audio track above the configured threshold.
- **Cuts pauses**: Shortens long silent sections to a configurable minimum duration.

Notes:
- The processing pipeline is detector/processor-based so behavior can be extended without rewriting the full flow.
- Most behavior is controlled via `config.py`, including enabled processors, render settings, and the filler words list.

## Requirements
1) Python >= 3.13
2) FFmpeg available on PATH

## Install
1) `pip install -r requirements.txt`

## Commands
1) Run GUI: `py app.py`
2) Run CLI: `python main.py process --input path/to/video.mp4`

## Configuration
Edit `config.py` to change thresholds, normalization behavior, rendering options, enabled processors, and the filler words to detect/mute.

## Secrets
- Keep non-secret app behavior in `config.py`.
- Keep credentials and other secret values in `.env` at the project root.
- The app loads `.env` automatically on startup for both `python app.py` and `python main.py process ...`.
- Read values in Python with `os.getenv("YOUR_SECRET_NAME")`.

## Workflow
1) Select one input video.
2) Run the GUI or `python main.py process --input path/to/video.mp4`.
3) The pipeline extracts one audio track, runs the enabled detectors and processors, then renders one processed video.
4) The default output path is created next to the input file with a `_processed.mp4` suffix.

## Output
- The tool renders one processed output file per run.
- Outputs are written as MP4 even if the source input used another container such as AVI or MKV.

## Limitations / performance
1) Audio extraction can load entire audio into RAM on long videos.
2) Frame-accurate cutting depends on codec/encoding settings; changing codecs can reduce cut accuracy.

## Development
1) Run tests: `pytest`

