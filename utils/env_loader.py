from __future__ import annotations

import logging
import os
from pathlib import Path


_LOGGER = logging.getLogger("video_trimmer")
_ENV_FILE_NAME = ".env"


# Created by gpt-5.4 | 2026-03-07
def env_value_clean(value: str) -> str:
    """Normalize a .env value by removing matching outer quotes."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        return value[1:-1]
    return value


# Created by gpt-5.4 | 2026-03-07
def env_file_load(env_path: Path | None = None) -> Path | None:
    """Load root .env values into os.environ without overriding existing variables."""
    file_path = env_path or Path(__file__).resolve().parents[1] / _ENV_FILE_NAME
    if not file_path.exists():
        return None

    try:
        for raw_line in file_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                _LOGGER.warning(f"[ENV] Skipping invalid line in {file_path}: {raw_line}")
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                _LOGGER.warning(f"[ENV] Skipping empty key in {file_path}: {raw_line}")
                continue

            os.environ.setdefault(key, env_value_clean(value.strip()))
    except OSError as exc:
        _LOGGER.error(f"[ENV] Failed to load {file_path}: {exc}")
        raise

    return file_path
