from __future__ import annotations

import os
import shutil
from pathlib import Path
from tkinter import messagebox

from utils.path_helpers import make_fixed_output_path, make_processed_output_path


def save_fixed_outputs(host: str, guest: str, *, project_dir: Path) -> list[str] | None:
    """Save fixed copies (_fixed) of any processed outputs (_processed).

    Returns:
        List of saved fixed output paths, or None when nothing was saved.
    """

    # Match the pipeline naming behavior (_processed.mp4) so we can locate outputs.
    # Note: "NORMALIZE GUEST AUDIO" intentionally does NOT generate a new host file.
    host_processed = make_processed_output_path(host)
    guest_processed = make_processed_output_path(guest)

    host_exists = os.path.exists(host_processed)
    guest_exists = os.path.exists(guest_processed)

    if not host_exists and not guest_exists:
        messagebox.showwarning(
            "Nothing to save",
            "Expected processed files not found. Run an action first.\n\nMissing:\n"
            + "\n".join([host_processed, guest_processed]),
        )
        return None

    project_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    if host_exists:
        host_fixed = make_fixed_output_path(host_processed)
        shutil.copy2(host_processed, host_fixed)
        saved.append(host_fixed)

    if guest_exists:
        guest_fixed = make_fixed_output_path(guest_processed)
        shutil.copy2(guest_processed, guest_fixed)
        saved.append(guest_fixed)

    return saved

