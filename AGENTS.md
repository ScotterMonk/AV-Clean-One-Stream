# AGENTS.md

## Environment & Shell
**Context**: Windows 11, VS Code, PowerShell Core (`pwsh`).
- **Base folder**: `d:/Dropbox/Projects/AV-clean-one-stream./app/`.
    - **Rule**: Always use forward slashes `/` in paths to avoid escaping errors.
- **Terminal**: **STRICTLY PowerShell**. Do not use `cmd.exe`, `bash`, or `wsl`.
- **Syntax Rules**:
  - **Never use Linux commands in terminal**.
  - **Chaining**: Use `;` (sequential) or `&&` (conditional).
  - **Variables**: Use `$env:VAR = 'val'` (not `export` or `set`).
  - **Replacements**: Use `Select-String` (not `grep`), `Get-Content` (not `cat`), `New-Item` (not `touch`), `Remove-Item` (not `rm`).
- **Prohibited**: `tail`, `sed`, `awk`, `sudo`, and `cmd.exe` flags (like `/d`).

## Run Commands
- Start app: `python app.py` # launches the GUI. Do not test to see if it worked.
- **ONLY if venv not activated**: Activate venv with `.\activate.ps1`
- Run processing: `python main.py process --host <path> --guest <path>`
- Override normalization: `python main.py process --host ... --guest ... --norm-mode MATCH_HOST|STANDARD_LUFS`
- Run tests: `pytest` (from project root)
- Run single test: `pytest tests/test_filename.py`

## Critical Non-Obvious Gotchas
- **`io_/` trailing underscore is intentional** — do NOT write `io/`; that shadows Python's built-in `io` namespace.
- **`config.py` is the behavioral control surface** — `PIPELINE_CONFIG` and `QUALITY_PRESETS` control which processors run, thresholds, and codec settings. Start there for any behavioral change.
- **`--action ALL` is deprecated** — the CLI still accepts it for backwards-compat but raises on any other value. Never generate `--action ALL` in new scripts or tests.
- **Top-level CLI form is legacy** — `python main.py --host ... --guest ...` still routes via `cli()` but always prefer the `process` subcommand.
- **Sync**
    - **Keep guest's video in sync with guest's audio**.
    - **Keep host's video in sync with host's audio**.
    - **Keep guest and host in sync with each other**: any removal of a pause in either video means you must modify both videos so they stay in sync.
- **Audio extraction loads entire video into RAM** as stereo 44.1kHz WAV via pydub; long videos require hundreds of MB (`io_/audio_extractor.py`)
- **All outputs are MP4** even when input is `.avi`, `.mkv`, etc. (`utils/path_helpers.py`)
- **`make_processed_output_path()` prevents `_processed_processed` chains**; if input already ends in `_processed`, it strips that suffix and returns `{stem}_processed_rerun.mp4` (unless `output_ext` overridden) (`utils/path_helpers.py`, `tests/test_output_paths.py`)
- **Detectors are NEVER user-configurable**; they're auto-added based on enabled processors (`main.py`)
- **Pipeline always renders BOTH outputs** (host + guest) even for guest-only workflows to maintain paired alignment (`main.py`)
- **Host + Guest renders run in parallel** via `ThreadPoolExecutor(max_workers=2)` inside `render_project()`; each is an independent FFmpeg subprocess so there is zero sync risk. Falls back to sequential when only one output is requested (`io_/video_renderer.py`)
- **`normalize_video_lengths()` writes BOTH processed files** when duration mismatch detected, even if only one needs padding (`io_/media_preflight.py`)
- **Rendering with output==input uses temp file + atomic replace**; otherwise FFmpeg would read/write same path (`io_/video_renderer.py`)
- **GUI subprocess stdout/stderr are merged** (`io_/video_renderer.py`); FFmpeg progress throttled to 0.25s for GUI smoothness (`io_/video_renderer.py`)
- **Frame-accurate cutting requires H.264/AAC**; changing codecs breaks non-keyframe cuts (`config.py`, `io_/video_renderer.py`)
- **LUFS uses `pyloudnorm` if installed**; missing triggers RMS fallback with warning (`analyzers/audio_level_analyzer.py`)

## Architecture (Edit Flow)
- Detectors → results keyed by `detector.get_name()` → processors consume and build `EditManifest` (no media mutation) (`core/pipeline.py`, `processors/base_processor.py`)
- Pipeline passes accumulated `detection_results` to detectors that accept it; SpikeFixerDetector can run an extra FFmpeg analysis pass post-normalization for accuracy and depends on `AudioLevelDetector` results
- AudioNormalizer consumes `detection_results['audio_level_detector']` (it no longer computes LUFS internally)
- WordMuter is the sole owner of per-track audio mute filters. SegmentRemover is the sole owner of removal_segments / keep_segments.
- **`processors/word_remover.py` was removed**; replaced by `processors/word_muter.py`. Do not recreate or reference `word_remover.py`.
- Rendering applies `host_filters`/`guest_filters`, then trims video AND audio using SAME `keep_segments` to preserve sync (`io_/video_renderer.py`, `core/interfaces.py`)
