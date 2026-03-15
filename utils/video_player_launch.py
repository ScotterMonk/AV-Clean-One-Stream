from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# Created by gpt-5.4 | 2026-03-07
def video_player_open(video_path: str, *, player_path: str | None = None) -> None:
    """Open a video in the configured player or the operating-system default."""

    target_path = Path(video_path)
    if not target_path.exists():
        raise FileNotFoundError(f"Video file not found: {target_path}")

    configured_player = str(player_path or "").strip().strip('"')
    if configured_player:
        player = Path(configured_player)
        if not player.exists():
            raise FileNotFoundError(f"Configured video player not found: {player}")

        subprocess.Popen([str(player), str(target_path)], close_fds=not sys.platform.startswith("win"))
        return

    _video_open_default(str(target_path))


# Created by gpt-5.4 | 2026-03-07
def _video_open_default(video_path: str) -> None:
    """Open a video using the current platform default application."""

    if sys.platform.startswith("win"):
        os.startfile(video_path)
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", video_path], close_fds=True)
        return

    subprocess.Popen(["xdg-open", video_path], close_fds=True)
