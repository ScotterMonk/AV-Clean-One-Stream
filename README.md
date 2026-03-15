# AV Cleaner
by Scott Howard Swain

## Application overview
Automates “cleaning” of a host/guest type video recording while keeping audio and video in sync.

Features:
- **Removes filler words**: Detects configured filler words from `config.py` and mutes them during processing. Depending on length of silence (including surrounding silence), the muted area may be cut in the `Cuts pauses` step.
- **Normalizes loudness** may be just a placeholder for now as it is legacy functionality for getting audio streams of two videos in sync.
- **Reduces volume spikes** in the audio track above a configured threshold.
- **Cuts pauses**: Shortens long silence pauses to a configurable minimum duration by removing the excess.

Notes:
- The processing pipeline is detector/processor-based so behavior can be extended without rewriting the full flow.
- Most behavior is controlled via `config.py`, including enabled processors and the filler words list.

```mermaid
flowchart LR
    A[Probe media] --> B[Detect events]
    B --> C[Mute filler words]
    C --> D[Cut pauses]
    D --> E[Normalize loudness]
    E --> F[Reduce volume spikes]
    F --> G[Render output]
```

## Requirements
1) Python >= 3.13
2) FFmpeg available on PATH

## Install
1) `pip install -r requirements.txt`

## Commands
1) Run GUI: `py app.py`
2) Run CLI: `python main.py process --host path/to/host.mp4 --guest path/to/guest.mp4`
3) Override normalization mode: `python main.py process --host ... --guest ... --norm-mode MATCH_HOST|STANDARD_LUFS`

## Configuration
Edit `config.py` to change thresholds (spikes/silence), normalization behavior, rendering options, enabled processors, and the filler words to detect/mute.

## Secrets
- Keep non-secret app behavior in `config.py`.
- Keep credentials and other secret values in `.env` at the project root.
- The app loads `.env` automatically on startup for both `python app.py` and `python main.py process ...`.
- Read values in Python with `os.getenv("YOUR_SECRET_NAME")`.

## Output
- The tool always renders a processed host + processed guest pair to preserve alignment.
- Outputs are written as MP4 (even if inputs are AVI/MKV/etc.).

## Limitations / performance
1) Audio extraction can load entire audio into RAM on long videos.
2) Frame-accurate cutting depends on codec/encoding settings; changing codecs can reduce cut accuracy.

## Development
1) Run tests: `pytest`

