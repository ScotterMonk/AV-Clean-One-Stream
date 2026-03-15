from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path

"""Small helpers for end-of-processing user alerts.

The chime WAV lives at ``assets/alert_chime.wav`` (relative to project root).
It is auto-generated on first use if missing.  Users can replace the file with
any standard WAV to customise the completion sound.
"""

# Persistent chime file path — resolved relative to project root
# (this file lives at utils/processing_alert.py → parent.parent = project root).
_CHIME_PATH = Path(__file__).resolve().parent.parent / "assets" / "alert_chime.wav"


def _build_chime_wav() -> bytes:
    """Generate a 3-tone ascending chime as in-memory WAV bytes.

    Uses only stdlib (wave, struct, math) — no external packages required.
    Tones mirror the original winsound.Beep sequence: A5 → C6 → E6.
    """
    sample_rate = 44100
    num_channels = 1
    sample_width = 2  # 16-bit signed PCM
    volume = 0.15

    # (frequency_hz, duration_seconds)
    tones = [
        (880, 0.18),   # A5
        (1046, 0.18),  # C6
        (1318, 0.24),  # E6
    ]

    all_samples: list[int] = []
    for freq, duration in tones:
        n_samples = int(sample_rate * duration)
        # 10 ms linear fade-in / fade-out to avoid clicks
        fade = int(sample_rate * 0.01)

        for i in range(n_samples):
            val = math.sin(2 * math.pi * freq * (i / sample_rate))

            # Amplitude envelope
            if i < fade:
                val *= i / fade
            elif i > n_samples - fade:
                val *= (n_samples - i) / fade

            # Scale to 16-bit range at 70 % volume to avoid clipping
            all_samples.append(int(val * 32767 * volume))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(all_samples)}h", *all_samples))

    return buf.getvalue()


def _chime_wav_ensure() -> str:
    """Return the path to the chime WAV, creating it on first use.

    The file lives at ``assets/alert_chime.wav``.  If the user has replaced
    it with their own WAV, the existing file is left untouched.
    """
    if _CHIME_PATH.exists():
        return str(_CHIME_PATH)

    # Create the assets/ directory if needed and write the default chime.
    _CHIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CHIME_PATH.write_bytes(_build_chime_wav())
    return str(_CHIME_PATH)


def processing_complete_alert_play() -> None:
    """Play a short completion chime without raising if audio is unavailable.

    Uses SND_FILENAME with ``assets/alert_chime.wav`` instead of SND_MEMORY.

    **Why not SND_MEMORY?**  Windows' multimedia subsystem retains a reference
    to the in-memory WAV buffer after PlaySound returns.  During process-exit
    cleanup (audio endpoint release, session disconnect, COM teardown) these
    stale references cause the sound to replay — producing phantom beeps
    minutes after the app has closed.

    **Why SND_FILENAME?**  Windows reads the file, plays it, and releases the
    handle.  No memory reference persists across process exit.

    **PlaySound(None, 0)** after playback explicitly clears the "last played
    sound" state in the multimedia subsystem, removing the final vector for
    phantom replays.

    SND_NODEFAULT prevents Windows from substituting its own default system
    sound if the WAV is rejected by the audio driver.

    winsound.Beep() is intentionally NOT used because Windows kernel-queues
    Beep() calls and they outlive the process.

    **Custom sounds**: Replace ``assets/alert_chime.wav`` with any standard WAV
    file.  Delete the file to regenerate the default chime on next run.
    """

    try:
        import winsound  # Windows only; ImportError silently skipped on other platforms

        chime_path = _chime_wav_ensure()

        flags = winsound.SND_FILENAME | winsound.SND_NODEFAULT
        winsound.PlaySound(chime_path, flags)

        # Explicitly clear the "last played sound" state so nothing lingers
        # in the multimedia subsystem after our process exits.
        winsound.PlaySound(None, 0)
    except Exception:
        # Audio alerts are best-effort only; never let this break processing.
        pass
