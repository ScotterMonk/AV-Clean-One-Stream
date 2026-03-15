# detectors/filler_word_detector.py
#
# Detects specific words/phrases (e.g. "uh", "uhm", "you know") in a single
# audio track via the AssemblyAI transcription API.
# Returns a list of (start_sec, end_sec) tuples for every match found.
#
# Required env vars:  AAI_SETTINGS_API_KEY, AAI_SETTINGS_BASE_URL
# Config key:         WORDS_TO_REMOVE['words_to_remove']  (list of str)

import os
import tempfile
import time
from typing import Any, Dict, List, Tuple

import requests

from .base_detector import BaseDetector
from config import WORDS_TO_REMOVE
from utils.logger import get_logger

logger = get_logger(__name__)

# How long to wait between status-polling retries (seconds).
_POLL_INTERVAL_SEC = 3


# Modified by gpt-5.4 | 2026-03-08
class FillerWordDetector(BaseDetector):
    """
    Transcribes a single audio track via AssemblyAI and returns the time ranges
    of every configured word/phrase that should be removed.

    Multi-word phrases (e.g. "you know") are matched by comparing consecutive
    word windows against the phrase token sequence.

    If the API key is absent, or if any API call fails, an empty list is
    returned so the pipeline degrades gracefully.
    """

    # ── Public interface ───────────────────────────────────────────────────

    # Modified by gpt-5.4 | 2026-03-08
    def detect(self, audio, detection_results=None) -> List[Dict[str, Any]]:
        """
        Transcribe the audio track and return word-removal ranges.

        Args:
            audio:             pydub AudioSegment for the track.
            detection_results: accumulated pipeline results dict; used to
                               resolve the video path for transcript file output.

        Returns:
            List of segment dicts with start_sec/end_sec for matched words.
            Caller (WordMuter) is responsible for sorting/merging.
            High-confidence filtering is applied here.
        """
        api_key = os.getenv("AAI_SETTINGS_API_KEY", "").strip()
        base_url = os.getenv("AAI_SETTINGS_BASE_URL", "").strip().rstrip("/")

        if not api_key or not base_url:
            logger.warning(
                "[FillerWordDetector] AAI_SETTINGS_API_KEY or AAI_SETTINGS_BASE_URL "
                "not set -- skipping word detection."
            )
            return []

        target_words: List[str] = WORDS_TO_REMOVE.get("words_to_remove", [])
        if not target_words:
            logger.info("[FillerWordDetector] WORDS_TO_REMOVE is empty -- nothing to detect.")
            return []

        logger.info(
            "[FillerWordDetector] Detecting word(s): %s",
            ", ".join(repr(w) for w in target_words),
        )

        # Resolve video path so _process_track can place transcript files
        # beside the processed output (same parent directory as input video).
        dr = detection_results or {}
        video_path = dr.get("video_path")

        headers = {"authorization": api_key}

        segments = self._process_track("audio", audio, target_words, base_url, headers, video_path)
        muted = [s for s in segments if s.get("action") == "mute"]
        skipped = [s for s in segments if s.get("action") == "skipped"]
        logger.info(
            "[DETAIL] Filler words: %d found, %d muted, %d skipped",
            len(segments), len(muted), len(skipped),
        )

        return segments

    def get_name(self) -> str:
        return "filler_word_detector"

    def validate_config(self) -> bool:
        """Returns True only when the API key env var is populated."""
        return bool(os.getenv("AAI_SETTINGS_API_KEY", "").strip())

    # ── Private helpers ────────────────────────────────────────────────────

    # Modified by gpt-5.4 | 2026-03-08
    def _process_track(
        self,
        label: str,
        audio,
        target_words: List[str],
        base_url: str,
        headers: dict,
        video_path: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Export one pydub AudioSegment, upload it, transcribe, return matches.

        Saves ``transcript_{label}.txt`` beside the input video after a
        successful transcription (overwrites any file from a prior run).
        """
        temp_path = None
        try:
            temp_path = self._export_to_temp_mp3(audio, label)
            audio_url = self._upload_audio(temp_path, base_url, headers, label)
            transcript_words = self._transcribe(audio_url, base_url, headers, label)
            matches = self._find_matches_detailed(transcript_words, target_words, label)
            filtered = self._filter_by_confidence(matches, label)
            # Persist filler word results beside the video output directory.
            if video_path is not None:
                self._save_filler_words(filtered, label, video_path)
            return filtered
        except Exception as exc:
            logger.error("[FillerWordDetector] %s track failed: %s", label, exc)
            return []
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass  # Non-critical; temp dir will clean up eventually

    def _export_to_temp_mp3(self, audio, label: str) -> str:
        """Write pydub AudioSegment to a named temp .mp3 file; return its path."""
        fd, temp_path = tempfile.mkstemp(suffix=f"_{label}.mp3", prefix="aai_")
        os.close(fd)  # Close OS handle so pydub can open the file for writing
        audio.export(temp_path, format="mp3")
        logger.debug("[FillerWordDetector] Exported %s audio -> %s", label, temp_path)
        return temp_path

    def _upload_audio(self, file_path: str, base_url: str, headers: dict, label: str) -> str:
        """Upload audio file to AssemblyAI; return the hosted audio URL."""
        logger.info("[DETAIL] Uploading %s audio to AssemblyAI...", label)
        with open(file_path, "rb") as f:
            response = requests.post(f"{base_url}/v2/upload", headers=headers, data=f)

        if response.status_code != 200:
            raise RuntimeError(
                f"Upload failed ({response.status_code}): {response.text}"
            )

        audio_url = response.json()["upload_url"]
        logger.debug("[FillerWordDetector] %s upload URL: %s", label, audio_url)
        return audio_url

    def _transcribe(
        self, audio_url: str, base_url: str, headers: dict, label: str
    ) -> List[dict]:
        """
        Submit a transcript request and poll until completion.
        Returns the raw word-level list from the API response.
        """
        payload = {
            "audio_url": audio_url,
            "speech_models": ["universal-3-pro", "universal-2"],
            "language_detection": True,
            "speaker_labels": False,
            # Must be True so disfluencies ("uh", "uhm", etc.) are preserved
            # in the word-level results instead of being silently stripped.
            "disfluencies": True,
        }
        response = requests.post(f"{base_url}/v2/transcript", headers=headers, json=payload)
        if response.status_code != 200:
            raise RuntimeError(
                f"Transcript request failed ({response.status_code}): {response.text}"
            )

        transcript_id = response.json()["id"]
        poll_url = f"{base_url}/v2/transcript/{transcript_id}"
        logger.info("[FillerWordDetector] Polling transcript %s for %s track...", transcript_id, label)

        while True:
            poll_response = requests.get(poll_url, headers=headers)
            transcript = poll_response.json()
            status = transcript.get("status")

            if status == "completed":
                words = transcript.get("words") or []
                logger.info(
                    "[DETAIL] %s transcript complete — %d word(s) received",
                    label,
                    len(words),
                )
                return words

            if status == "error":
                raise RuntimeError(
                    f"AssemblyAI transcription error for {label}: {transcript.get('error')}"
                )

            # Still processing -- wait and retry
            logger.debug("[FillerWordDetector] %s status=%s, retrying in %ds...", label, status, _POLL_INTERVAL_SEC)
            time.sleep(_POLL_INTERVAL_SEC)

    def _save_filler_words(
        self, matches: List[Dict[str, Any]], label: str, video_path: str
    ) -> None:
        """Write detected filler words to ``filler_words.txt`` beside
        the input video.  Overwrites any file from a prior run.

        Each line format:
            hh:mm:ss:ms - "{word}" - confidence: 0.9500 - muted
        """
        out_dir = os.path.dirname(os.path.abspath(video_path))
        out_path = os.path.join(out_dir, "filler_words.txt")
        lines = []
        for m in matches:
            start_sec = float(m.get("start_sec", 0.0))
            hh = int(start_sec // 3600)
            mm = int((start_sec % 3600) // 60)
            ss = int(start_sec % 60)
            ms = int(round((start_sec * 1000) % 1000))
            timestamp = f"{hh:02d}:{mm:02d}:{ss:02d}:{ms:03d}"
            word = str(m.get("text") or "").strip()
            conf = float(m.get("confidence", 0.0) or 0.0)
            action = str(m.get("action") or "mute")
            lines.append(f'{timestamp} - "{word}" - confidence: {conf:.4f} - {action}')
        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
                if lines:
                    fh.write("\n")
            logger.info(
                "[FillerWordDetector] Saved %s filler words (%d) -> %s",
                label, len(lines), out_path,
            )
        except OSError as exc:
            logger.warning("[FillerWordDetector] Could not save filler words file: %s", exc)

    # Modified by gpt-5.4 | 2026-03-08
    def _find_matches(
        self, words: List[dict], target_phrases: List[str]
    ) -> List[Tuple[float, float]]:
        """Return phrase matches as (start_sec, end_sec) tuples."""

        detailed_matches = self._find_matches_detailed(words, target_phrases, track=None)
        return [
            (match["start_sec"], match["end_sec"])
            for match in detailed_matches
        ]

    # Created by gpt-5.4 | 2026-03-08
    def _find_matches_detailed(
        self,
        words: List[dict],
        target_phrases: List[str],
        track: str | None,
    ) -> List[Dict[str, Any]]:
        """
        Scan the word list for any phrase in target_phrases.

        Single-token phrases:  matched against each word individually.
        Multi-token phrases:   matched against consecutive word windows.

        All timestamps from the API are in milliseconds; the returned tuples
        are in seconds.
        """
        matches: List[Dict[str, Any]] = []

        for phrase in target_phrases:
            tokens = phrase.lower().split()
            phrase_len = len(tokens)

            for i in range(len(words) - phrase_len + 1):
                window = words[i : i + phrase_len]
                window_texts = [w["text"].strip(".,!?;:").lower() for w in window]

                if window_texts == tokens:
                    # Timestamps are in milliseconds — convert to seconds
                    start_sec = window[0]["start"] / 1000.0
                    end_sec = window[-1]["end"] / 1000.0
                    confidence_values = [float(w.get("confidence", 0.0) or 0.0) for w in window]

                    # Gap (ms) to the preceding word; None if filler is first word.
                    # Used by WordMuter for pause-aware mute inset (slurred speech).
                    prev_gap_ms = (
                        words[i]["start"] - words[i - 1]["end"]
                        if i > 0 else None
                    )
                    # Gap (ms) to the following word; None if filler is last word.
                    next_gap_ms = (
                        words[i + phrase_len]["start"] - window[-1]["end"]
                        if (i + phrase_len) < len(words) else None
                    )

                    matches.append(
                        {
                            "track": track,
                            "text": phrase,
                            "start_sec": start_sec,
                            "end_sec": end_sec,
                            "confidence": min(confidence_values) if confidence_values else 0.0,
                            "prev_gap_ms": prev_gap_ms,
                            "next_gap_ms": next_gap_ms,
                        }
                    )
                    logger.info(
                        "[FillerWordDetector] Matched word %r at %.3f-%.3fs",
                        phrase,
                        start_sec,
                        end_sec,
                    )

        return matches

    def _filter_by_confidence(self, matches: List[Dict[str, Any]], track: str) -> List[Dict[str, Any]]:
        """
        Annotate each match with ``action = "mute"`` (meets threshold) or
        ``action = "skipped"`` (below threshold).  All matches are returned
        so downstream logging can report both kept and skipped words.

        The effective threshold is:
            effective_required = base_required - (word_count * confidence_bonus_per_word)
        So every word in the phrase lowers the bar equally — a 1-word phrase
        gets a -0.05 bonus, 2-word gets -0.10, 3-word gets -0.15, etc.
        """
        required = float(WORDS_TO_REMOVE.get("confidence_required", 0.0) or 0.0)

        bonus_per_word = float(
            WORDS_TO_REMOVE.get("confidence_bonus_per_word", 0.0) or 0.0
        )

        for match in matches:
            conf = float(match.get("confidence", 0.0) or 0.0)
            phrase = match.get("text", "")
            word_count = len(phrase.split())
            # Every word in the phrase earns a bonus that lowers the threshold.
            effective_required = required - (word_count * bonus_per_word)
            logger.debug(
                "[FillerWordDetector] %s | %r: %d word(s), threshold %.2f → %.2f (conf=%.2f)",
                track, phrase, word_count, required, effective_required, conf,
            )
            if conf >= effective_required:
                match["action"] = "mute"
            else:
                match["action"] = "skipped"

        return matches
