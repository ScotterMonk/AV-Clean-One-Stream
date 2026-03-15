# Pre-Plan: Simplify App to One Combined Video Stream
## Goal
Simplify the application from a dual-file, sync-preserving host/guest workflow to a single-file workflow:
- Input: one Zoom `.mp4` file.
- Audio: one stereo mixed track with no host/guest separation.
- Output: one processed `.mp4` file.

The simplified app should only care about:
- Filler words.
- Pauses.
- Audio spikes.
- Loudness normalization.
- Keeping the video's audio and video in sync.

## Core Assessment
This change makes the entire application simpler.

The old architecture assumes two separate concepts everywhere:
- Host.
- Guest.

That split exists in:
- CLI inputs.
- Pipeline signatures.
- Detector interfaces.
- Processor interfaces.
- Render logic.
- Edit manifest filter storage.
- GUI layout.
- Logging.
- Settings.
- Tests.

With one Zoom file and one mixed audio stream, all of that collapses to a single-stream model:
- One input path.
- One extracted audio object.
- One filter list.
- One output path.
- One filler-word pane in the UI.
- One set of settings for detection and normalization.

## What Disappears Entirely
The following concepts no longer apply and should be removed:
- Separate host and guest input files.
- Syncing two processed outputs together.
- Host-versus-guest confidence thresholds.
- Host-versus-guest filler-word reporting.
- `MATCH_HOST` normalization mode.
- Duration-alignment preflight between two videos.
- Dual-render output threading for host and guest.
- Mutual-silence comparison between two independent audio signals.

## Files and Functions Likely Needing Changes
## 1) Configuration
- `config.py`.
    - `WORDS_TO_REMOVE`.
        - Remove `confidence_required_host`.
        - Remove `confidence_required_guest`.
        - Replace both with a single `confidence_required` value.
    - `QUALITY_PRESETS`.
        - Remove `normalization.mode: MATCH_HOST`.
        - Keep only standard single-stream normalization behavior.
        - Simplify normalization settings to the minimum needed for one mixed track.

## 2) CLI and Entry Flow
- `main.py`.
    - `_run_process(host, guest, norm_mode, action)`.
        - Change to a single-input version such as `_run_process(input_path, norm_mode, action)` or simpler.
        - Remove the call to `normalize_video_lengths()`.
    - `cli()`.
        - Replace `--host` and `--guest` with one `--input` option.
    - `process()`.
        - Replace `--host` and `--guest` with one `--input` option.
    - Logging and result output.
        - Replace host/guest result reporting with a single output path.

## 3) Core Pipeline
- `core/pipeline.py`.
    - `ProcessingPipeline.execute(host_video_path, guest_video_path, ...)`.
        - Change to one input path.
        - Extract one audio object instead of two.
        - Pass one audio object to detectors and processors.
        - Produce one output path instead of two.
    - `_log_filler_word_details()`.
        - Remove host/guest grouping.
        - Log one stream of filler-word results.
    - `_log_filler_word_summary()`.
        - Remove host/guest summary split.
        - Summarize one stream only.

- `core/interfaces.py`.
    - `EditManifest`.
        - Replace `host_filters` and `guest_filters` with one `filters` list.
    - `add_host_filter()`.
        - Remove.
    - `add_guest_filter()`.
        - Remove.
    - Add a single `add_filter()` helper.

## 4) Rendering and Preflight
- `io_/video_renderer.py`.
    - `render_project(host_path, guest_path, manifest, out_host, out_guest, config)`.
        - Change to single input and single output.
        - Remove host/guest render task branching.
        - Remove host/guest parallel render threading.
        - Use one filter list from the manifest.

- `io_/video_renderer_twophase.py`.
    - `render_project_two_phase(host_path, guest_path, manifest, out_host, out_guest, config)`.
        - Same simplification as the main renderer.
        - Single input path.
        - Single output path.
        - Single audio filter path.

- `io_/media_preflight.py`.
    - `normalize_video_lengths(host_path, guest_path)`.
        - Remove entirely.
    - The whole file likely becomes unnecessary.

## 5) Detector Interfaces and Detector Logic
- `detectors/base_detector.py`.
    - `detect(host_audio, guest_audio)`.
        - Change to `detect(audio)`.

- `detectors/audio_level_detector.py`.
    - `AudioLevelDetector.detect(host_audio, guest_audio)`.
        - Change to single-audio detection.
        - Remove `host_lufs` and `guest_lufs` split.
        - Remove `guest_gain_db` logic tied to `MATCH_HOST`.
        - Return only what single-stream normalization needs.

- `detectors/filler_word_detector.py`.
    - `FillerWordDetector.detect(host_audio, guest_audio, detection_results)`.
        - Change to one audio input.
        - Remove the host/guest loop.
        - Remove per-track labels in results.
        - Use one confidence threshold.

- `detectors/spike_fixer_detector.py`.
    - `SpikeFixerDetector.detect(host_audio, guest_audio, detection_results)`.
        - Change to one audio input.
        - Keep the basic spike logic.
        - Rename guest-specific path lookups to generic video-path lookups.
    - `_detect_pre_normalization(host_audio, guest_audio)`.
        - Change to one-audio version.
    - `_guest_video_path_from_detection_results()`.
        - Rename to a generic path resolver.
    - `_detect_post_normalization_peak_series_db(guest_video_path, ...)`.
        - Rename parameters to generic single-video equivalents.

- `detectors/cross_talk_detector.py`.
    - `CrossTalkDetector.detect(host_audio, guest_audio, detection_results)`.
        - The current two-stream mutual-silence concept no longer applies.
        - This detector should either be removed or rewritten into a plain single-track silence detector.

- `detectors/silence_detector.py`.
    - `SilenceDetector.detect(host_audio, guest_audio)`.
        - Change to `detect(audio)`.
        - This file may become the primary pause detector instead of `cross_talk_detector.py`.

## 6) Processor Interfaces and Processor Logic
- `processors/base_processor.py`.
    - `process(manifest, host_audio, guest_audio, detection_results)`.
        - Change to `process(manifest, audio, detection_results)`.

- `processors/word_muter.py`.
    - `WordMuter.process(manifest, host_audio, guest_audio, detection_results)`.
        - Change to single-audio processing.
        - Replace per-track filter routing with one filter list.

- `processors/audio_normalizer.py`.
    - `AudioNormalizer.process(manifest, host_audio, guest_audio, detection_results)`.
        - Change to single-audio processing.
        - Remove the `MATCH_HOST` branch entirely.
        - Use a single normalization filter path.

- `processors/spike_fixer.py`.
    - `SpikeFixer.process(manifest, host_audio, guest_audio, detection_results)`.
        - Change to single-audio processing.
        - Replace guest-only filter application with generic single-track filter application.

- `processors/segment_remover.py`.
    - `SegmentRemover.process(manifest, host_audio, guest_audio, detection_results)`.
        - Change to single-audio processing.
        - Replace references to removing from both videos with single-video wording.
        - Use `audio.duration_seconds` instead of `host_audio.duration_seconds`.

## 7) GUI
- `ui/gui_app.py`.
    - `run_processing(host_path, guest_path)`.
        - Change to `run_processing(input_path)`.
        - Launch CLI with `--input`.
    - Process button validation.
        - Require one selected file instead of host plus guest.
    - Result handling.
        - Track one processed output instead of two.
    - Save-fixed output flow.
        - Save one file instead of two.

- `ui/gui_pages.py`.
    - File selection section.
        - Replace two source rows with one.
    - Output section.
        - Replace two output rows with one.
    - Filler-word pane.
        - Replace host/guest split pane with one pane.
    - Progress append and clear logic.
        - Remove host/guest routing behavior.

- `ui/gui_process_helpers.py`.
    - `filler_line_track_hint()`.
        - Remove entirely.
    - `result_line_paths_parse()`.
        - Change from parsing host/guest result lines to parsing one result path.

- `ui/gui_outputs.py`.
    - `save_fixed_outputs(host, guest, project_dir=...)`.
        - Change to one-path save behavior.

- `ui/gui_settings_page.py`.
    - Host and guest confidence fields.
        - Collapse to one field.
    - `MATCH_HOST` radio option.
        - Remove.

## 8) Tests Likely Needing Updates
Any test that assumes separate host and guest paths, separate audio objects, separate output files, or host/guest-specific logs will need updating.

Most likely impacted test groups include:
- `tests/test_audio_level_detector.py`.
- `tests/test_audio_normalizer_detection.py`.
- `tests/test_cross_talk_detector_pause_shortening.py`.
- `tests/test_spike_fixer_ffmpeg.py`.
- `tests/test_spike_fixer_logging.py`.
- `tests/test_pipeline_normalize_spike.py`.
- `tests/test_pause_removal_log.py`.
- `tests/test_gui_result_line.py`.
- `tests/test_video_renderer_twophase.py`.
- `tests/test_main_preflight_normalize_lengths.py`.
- `tests/test_media_preflight_normalize_video_lengths.py`.

## Simplification Summary
This refactor should reduce both code complexity and conceptual complexity.

The biggest simplifications are:
1) All host/guest method signatures collapse to single-audio signatures.
2) The edit manifest collapses from dual filter lists to one filter list.
3) Rendering collapses from two outputs to one output.
4) Preflight duration alignment disappears entirely.
5) The UI collapses from a two-role layout to a one-file layout.
6) Normalization becomes simpler because `MATCH_HOST` disappears.
7) Pause detection becomes simpler because it only needs to detect silence in one mixed stream.

## Biggest Architectural Pressure Points
Even though the overall system gets simpler, the most important files to address first in a later implementation plan are:
1) `core/interfaces.py`.
    - Because the filter model changes from dual-track to single-track.
2) `core/pipeline.py`.
    - Because all detector and processor wiring changes here.
3) `io_/video_renderer.py`.
    - Because the output model collapses from two renders to one render.
4) `main.py`.
    - Because the CLI contract changes from two paths to one path.
5) `config.py`.
    - Because old dual-speaker assumptions should be removed early.

## Bottom-Line Assessment
This should make all of the app simpler.

The application stops being a dual-stream synchronization tool and becomes a straightforward single-video cleanup pipeline.

That means less branching, fewer special cases, fewer UI elements, fewer config settings, fewer result paths, and fewer places where host and guest must be kept conceptually aligned.
