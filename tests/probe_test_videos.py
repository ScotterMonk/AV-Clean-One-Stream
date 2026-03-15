"""Simple script to probe test video durations for logging verification testing."""

from io_.media_probe import get_video_duration_seconds

print("\n=== Test Video Duration Probe ===\n")

host_path = "test_videos/host.mp4"
guest_path = "test_videos/guest.mp4"

try:
    host_duration = get_video_duration_seconds(host_path)
    print(f"Host video:  {host_path}")
    print(f"  Duration:  {host_duration:.6f} seconds ({host_duration/60:.2f} minutes)\n")
except Exception as e:
    print(f"ERROR probing {host_path}: {e}\n")
    host_duration = None

try:
    guest_duration = get_video_duration_seconds(guest_path)
    print(f"Guest video: {guest_path}")
    print(f"  Duration:  {guest_duration:.6f} seconds ({guest_duration/60:.2f} minutes)\n")
except Exception as e:
    print(f"ERROR probing {guest_path}: {e}\n")
    guest_duration = None

if host_duration is not None and guest_duration is not None:
    diff = abs(host_duration - guest_duration)
    print(f"Duration difference: {diff:.6f} seconds ({diff/60:.4f} minutes)")
    
    if diff < 0.1:
        print("✓ Durations MATCH (difference < 0.1s)")
        print("  → Preflight logging will NOT trigger with these videos")
    else:
        print(f"✓ Durations MISMATCH (difference = {diff:.2f}s)")
        print("  → Preflight logging WILL trigger with these videos")
