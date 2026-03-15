from __future__ import annotations

import tkinter as tk
from typing import Any

from ui.gui_helpers import FileRowState
from ui.gui_tooltip import GuiTooltip


# Created by gpt-5.4 | 2026-03-08
def _file_grid_padding_get(row_index: int, column_index: int) -> tuple[tuple[int, int], tuple[int, int]]:
    pad_x = (1 if column_index == 0 else 0, 1)
    pad_y = (1 if row_index == 0 else 0, 1)
    return pad_x, pad_y


# Created by gpt-5.4 | 2026-03-08
def _hex_color_blend(color_a: str, color_b: str, weight_a: float) -> str:
    if len(color_a) != 7 or len(color_b) != 7 or not color_a.startswith("#") or not color_b.startswith("#"):
        return color_a

    weight_a = max(0.0, min(1.0, weight_a))
    weight_b = 1.0 - weight_a

    try:
        channels_a = [int(color_a[idx : idx + 2], 16) for idx in (1, 3, 5)]
        channels_b = [int(color_b[idx : idx + 2], 16) for idx in (1, 3, 5)]
    except ValueError:
        return color_a

    blended = [round((channel_a * weight_a) + (channel_b * weight_b)) for channel_a, channel_b in zip(channels_a, channels_b)]
    return f"#{blended[0]:02X}{blended[1]:02X}{blended[2]:02X}"


# Created by gpt-5.4 | 2026-03-08
def file_grid_line_color_get(app: Any) -> str:
    """Return a FILES-grid accent line that is subtler than the main pane outline."""

    accent_line = str(app._ui_colors["accent_line"])
    panel_outline_thickness = int(getattr(app, "_panel_outline_thickness", 1))
    if panel_outline_thickness > 1:
        return accent_line
    return _hex_color_blend(accent_line, str(app._palette["panel"]), 0.72)


# Created by gpt-5.4 | 2026-03-08
def file_grid_cell_create(app, parent: tk.Widget, row_index: int, column_index: int, *, sticky: str = "nsew") -> tk.Frame:
    """Create one FILES-area grid cell with the shared accent-line treatment."""

    pad_x, pad_y = _file_grid_padding_get(row_index, column_index)
    cell = tk.Frame(parent, bg=app._palette["panel"], bd=0, highlightthickness=0)
    cell.grid(row=row_index, column=column_index, padx=pad_x, pady=pad_y, sticky=sticky)
    return cell


# Created by gpt-5.4 | 2026-03-07
def output_row_create(
    app,
    parent: tk.Widget,
    row_index: int,
    role: str,
    *,
    label_text: str,
    grid_style: bool = False,
) -> FileRowState:
    """Build one MODDED FILES output row and return its state container."""

    role_parent = parent
    file_parent = parent
    size_parent = parent
    length_parent = parent

    if grid_style:
        role_parent = file_grid_cell_create(app, parent, row_index, 0, sticky="nsew")
        file_parent = file_grid_cell_create(app, parent, row_index, 1, sticky="nsew")
        size_parent = file_grid_cell_create(app, parent, row_index, 2, sticky="nsew")
        length_parent = file_grid_cell_create(app, parent, row_index, 3, sticky="nsew")

    tk.Label(
        role_parent,
        text=label_text,
        anchor="w",
        font=app._mono(weight="bold"),
        bg=app._palette["panel"],
        fg=app._palette["muted"],
    ).pack(anchor="w", padx=8, pady=6)

    file_var = tk.StringVar(value="")
    size_var = tk.StringVar(value="")
    length_var = tk.StringVar(value="")

    file_cell = tk.Frame(file_parent, bg=app._palette["panel"])
    file_cell.pack(fill="both", expand=True, padx=8, pady=6)
    file_cell.columnconfigure(1, weight=1)

    play_btn = tk.Button(
        file_cell,
        text="▶",
        command=lambda r=role: app._play_modded_row(r),
        font=app._f(app._fonts["body"], "bold"),
        bg=app._palette["panel"],
        fg=app._ui_colors["accent_line"],
        activebackground=app._palette["panel2"],
        activeforeground=app._ui_colors["accent_font"],
        relief="flat",
        bd=0,
        padx=2,
        pady=0,
        highlightthickness=0,
    )
    play_btn.grid(row=0, column=0, padx=(0, 8), sticky="w")
    play_btn.grid_remove()
    try:
        play_btn.configure(cursor="hand2")
    except tk.TclError:
        pass

    play_btn.bind("<Enter>", lambda _evt: play_btn.configure(bg=app._palette["panel2"]))
    play_btn.bind("<Leave>", lambda _evt: play_btn.configure(bg=app._palette["panel"]))
    play_btn._gui_tooltip = GuiTooltip(  # type: ignore[attr-defined]
        play_btn,
        "Play",
        bg=app._palette["panel2"],
        fg=app._ui_colors["accent_font"],
        border=app._ui_colors["accent_line"],
    )

    tk.Label(
        file_cell,
        textvariable=file_var,
        anchor="w",
        font=app._mono(),
        bg=app._palette["panel"],
        fg=app._palette["text"],
    ).grid(row=0, column=1, sticky="ew")
    tk.Label(
        size_parent,
        textvariable=size_var,
        anchor="w",
        font=app._mono(),
        bg=app._palette["panel"],
        fg=app._palette["muted"],
    ).pack(anchor="w", padx=8, pady=6)
    tk.Label(
        length_parent,
        textvariable=length_var,
        anchor="w",
        font=app._mono(),
        bg=app._palette["panel"],
        fg=app._palette["muted"],
    ).pack(anchor="w", padx=8, pady=6)

    return FileRowState(
        path=None,
        file_var=file_var,
        size_var=size_var,
        length_var=length_var,
        play_btn=play_btn,
    )
