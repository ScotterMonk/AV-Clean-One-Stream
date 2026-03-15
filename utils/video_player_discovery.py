from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows fallback
    winreg = None


# Created by gpt-5.4 | 2026-03-07
@dataclass(frozen=True)
class VideoPlayerCandidate:
    """Represents one discovered media-player executable."""

    label: str
    path: str
    platform_name: str
    source: str


# Created by gpt-5.4 | 2026-03-07
def video_player_platform_name() -> str:
    """Return the normalized operating-system name for player discovery."""

    raw_name = platform.system().lower().strip()
    if raw_name == "darwin":
        return "macos"
    if raw_name == "windows":
        return "windows"
    if raw_name == "linux":
        return "linux"
    return raw_name or "unknown"


# Created by gpt-5.4 | 2026-03-07
def video_player_platform_label() -> str:
    """Return a display label for the current discovery platform."""

    platform_name = video_player_platform_name()
    if platform_name == "macos":
        return "macOS"
    if platform_name == "windows":
        return "Windows"
    if platform_name == "linux":
        return "Linux"
    return platform_name.title()


# Created by gpt-5.4 | 2026-03-07
def video_player_discover() -> list[VideoPlayerCandidate]:
    """Discover media players for the current operating system."""

    platform_name = video_player_platform_name()
    if platform_name == "windows":
        candidates = _discover_windows()
    elif platform_name == "macos":
        candidates = _discover_macos()
    elif platform_name == "linux":
        candidates = _discover_linux()
    else:
        candidates = []
    return sorted(candidates, key=lambda item: (item.label.lower(), item.path.lower()))


# Created by gpt-5.4 | 2026-03-07
def _candidate_add(
    found: dict[str, VideoPlayerCandidate],
    *,
    label: str,
    path: Path,
    platform_name: str,
    source: str,
) -> None:
    normalized = str(path).strip().lower()
    if not normalized:
        return
    if not path.exists() or normalized in found:
        return
    found[normalized] = VideoPlayerCandidate(
        label=label,
        path=str(path),
        platform_name=platform_name,
        source=source,
    )


# Created by gpt-5.4 | 2026-03-07
def _discover_from_path(
    found: dict[str, VideoPlayerCandidate],
    *,
    platform_name: str,
    targets: list[tuple[str, str]],
) -> None:
    for label, executable_name in targets:
        on_path = shutil.which(executable_name)
        if on_path:
            _candidate_add(
                found,
                label=label,
                path=Path(on_path),
                platform_name=platform_name,
                source="PATH",
            )


# Created by gpt-5.4 | 2026-03-07
def _windows_targets() -> list[tuple[str, str, list[str]]]:
    return [
        ("VLC media player", "vlc.exe", ["VideoLAN/VLC/vlc.exe"]),
        ("Windows Media Player", "wmplayer.exe", ["Windows Media Player/wmplayer.exe"]),
        ("Media Player Classic - HC", "mpc-hc64.exe", ["MPC-HC/mpc-hc64.exe"]),
        ("Media Player Classic - HC", "mpc-hc.exe", ["MPC-HC/mpc-hc.exe"]),
        ("Media Player Classic - HC", "mplayerc.exe", ["MPC-HC/mplayerc.exe"]),
        ("Media Player Classic - BE", "mpc-be64.exe", ["MPC-BE/mpc-be64.exe", "MPC-BE x64/mpc-be64.exe"]),
        ("Media Player Classic - BE", "mpc-be.exe", ["MPC-BE/mpc-be.exe", "MPC-BE x64/mpc-be.exe"]),
        ("mpv", "mpv.exe", ["mpv/mpv.exe"]),
        ("PotPlayer", "PotPlayerMini64.exe", ["DAUM/PotPlayer/PotPlayerMini64.exe"]),
        ("PotPlayer", "PotPlayerMini.exe", ["DAUM/PotPlayer/PotPlayerMini.exe"]),
        ("KMPlayer", "KMPlayer64.exe", ["KMPlayer/KMPlayer64.exe"]),
        ("KMPlayer", "KMPlayer.exe", ["KMPlayer/KMPlayer.exe"]),
    ]


# Created by gpt-5.4 | 2026-03-07
def _windows_candidate_roots() -> list[Path]:
    roots: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        raw_path = os.environ.get(env_name, "").strip()
        if not raw_path:
            continue
        root = Path(raw_path)
        if root.exists() and root not in roots:
            roots.append(root)
    return roots


# Created by gpt-5.4 | 2026-03-07
def _discover_windows() -> list[VideoPlayerCandidate]:
    found: dict[str, VideoPlayerCandidate] = {}
    platform_name = "windows"

    _discover_from_path(
        found,
        platform_name=platform_name,
        targets=[(label, executable_name) for label, executable_name, _ in _windows_targets()],
    )

    for label, _executable_name, relative_paths in _windows_targets():
        for root in _windows_candidate_roots():
            for relative_path in relative_paths:
                _candidate_add(
                    found,
                    label=label,
                    path=root / relative_path,
                    platform_name=platform_name,
                    source="Install Directory",
                )

    if winreg is not None:
        key_roots = [
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        ]
        for label, executable_name, _relative_paths in _windows_targets():
            for hive, base_key in key_roots:
                try:
                    with winreg.OpenKey(hive, f"{base_key}\\{executable_name}") as key:
                        raw_path, _ = winreg.QueryValueEx(key, None)
                except OSError:
                    continue
                _candidate_add(
                    found,
                    label=label,
                    path=Path(str(raw_path).strip()),
                    platform_name=platform_name,
                    source="Registry",
                )

    return list(found.values())


# Created by gpt-5.4 | 2026-03-07
def _macos_bundle_targets() -> list[tuple[str, str]]:
    return [
        ("VLC media player", "VLC.app"),
        ("IINA", "IINA.app"),
        ("mpv", "mpv.app"),
        ("QuickTime Player", "QuickTime Player.app"),
        ("Elmedia Player", "Elmedia Player.app"),
    ]


# Created by gpt-5.4 | 2026-03-07
def _macos_bundle_executable(app_bundle: Path) -> Path | None:
    macos_dir = app_bundle / "Contents" / "MacOS"
    if not macos_dir.exists() or not macos_dir.is_dir():
        return None
    executables = sorted(child for child in macos_dir.iterdir() if child.is_file())
    if not executables:
        return None
    return executables[0]


# Created by gpt-5.4 | 2026-03-07
def _discover_macos() -> list[VideoPlayerCandidate]:
    found: dict[str, VideoPlayerCandidate] = {}
    platform_name = "macos"

    _discover_from_path(
        found,
        platform_name=platform_name,
        targets=[("VLC media player", "vlc"), ("mpv", "mpv")],
    )

    app_dirs = [Path("/Applications"), Path("/System/Applications"), Path.home() / "Applications"]
    for label, bundle_name in _macos_bundle_targets():
        for app_dir in app_dirs:
            app_bundle = app_dir / bundle_name
            executable = _macos_bundle_executable(app_bundle)
            if executable is None:
                continue
            _candidate_add(
                found,
                label=label,
                path=executable,
                platform_name=platform_name,
                source="Application Bundle",
            )

    return list(found.values())


# Created by gpt-5.4 | 2026-03-07
def _linux_targets() -> list[tuple[str, str]]:
    return [
        ("VLC media player", "vlc"),
        ("mpv", "mpv"),
        ("Celluloid", "celluloid"),
        ("SMPlayer", "smplayer"),
        ("MPlayer", "mplayer"),
        ("GNOME Videos", "totem"),
    ]


# Created by gpt-5.4 | 2026-03-07
def _discover_linux() -> list[VideoPlayerCandidate]:
    found: dict[str, VideoPlayerCandidate] = {}
    platform_name = "linux"

    _discover_from_path(found, platform_name=platform_name, targets=_linux_targets())

    common_dirs = [Path("/usr/bin"), Path("/usr/local/bin"), Path("/snap/bin")]
    for label, executable_name in _linux_targets():
        for directory in common_dirs:
            _candidate_add(
                found,
                label=label,
                path=directory / executable_name,
                platform_name=platform_name,
                source="Common Binary Directory",
            )

    return list(found.values())
