"""Diagnostic: extract guest audio and print every word AssemblyAI returns.

Usage:
    python tests/diag_transcribe_words.py
"""
import os, sys, tempfile, time, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.env_loader import env_file_load
env_file_load()

from io_ import audio_extractor

GUEST_VIDEO = "test_videos/guest.mp4"

api_key = os.getenv("AAI_SETTINGS_API_KEY", "").strip()
base_url = os.getenv("AAI_SETTINGS_BASE_URL", "").strip().rstrip("/")
headers = {"authorization": api_key}

print("Extracting audio…")
audio = audio_extractor.extract_audio(GUEST_VIDEO)

fd, tmp = tempfile.mkstemp(suffix="_diag.mp3")
os.close(fd)
audio.export(tmp, format="mp3")
print(f"Exported → {tmp}")

print("Uploading…")
with open(tmp, "rb") as f:
    r = requests.post(f"{base_url}/v2/upload", headers=headers, data=f)
r.raise_for_status()
audio_url = r.json()["upload_url"]

print("Submitting transcript (disfluencies=True)…")
r = requests.post(f"{base_url}/v2/transcript", headers=headers, json={
    "audio_url": audio_url,
    "speech_models": ["universal-3-pro", "universal-2"],
    "language_detection": True,
    "speaker_labels": False,
    "disfluencies": True,
})
r.raise_for_status()
tid = r.json()["id"]
poll = f"{base_url}/v2/transcript/{tid}"

print(f"Polling {tid}…")
while True:
    t = requests.get(poll, headers=headers).json()
    if t["status"] == "completed":
        break
    if t["status"] == "error":
        print("ERROR:", t.get("error"))
        sys.exit(1)
    time.sleep(3)

os.unlink(tmp)

print("\n── Full transcript ──────────────────────────────────")
print(t["text"])
print("\n── Word-level results ───────────────────────────────")
for w in t.get("words") or []:
    print(f"  {w['start']:>6}ms – {w['end']:>6}ms  |  {w['text']!r}")
