from __future__ import annotations

import os
import shutil
from pathlib import Path
from tkinter import messagebox

from utils.path_helpers import make_fixed_output_path, make_processed_output_path


def save_fixed_outputs(output_path: str, *, project_dir: Path) -> list[str] | None:
    """Save fixed copies (_fixed) of any processed outputs (_processed).

    Returns:
        List of saved fixed output paths, or None when nothing was saved.
    """

    processed = make_processed_output_path(output_path)
    if not os.path.exists(processed):
        messagebox.showwarning("Nothing to save", f"Expected processed file not found: {processed}")
        return None
    project_dir.mkdir(parents=True, exist_ok=True)
    fixed = make_fixed_output_path(processed)
    shutil.copy2(processed, fixed)
    return [fixed]

