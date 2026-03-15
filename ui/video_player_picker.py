from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from utils.video_player_discovery import VideoPlayerCandidate


# Created by gpt-5.4 | 2026-03-07
class VideoPlayerPickerDialog:
    """Modal picker dialog for selecting one discovered media player."""

    # Created by gpt-5.4 | 2026-03-07
    def __init__(self, parent: tk.Widget, app, options: list[VideoPlayerCandidate]) -> None:
        self._parent = parent
        self._app = app
        self._options = options
        self._selected_path: str | None = None

        self._dialog = tk.Toplevel(parent)
        self._dialog.title("Select Default Video Player")
        self._dialog.configure(bg=app._palette["panel"])
        self._dialog.transient(parent.winfo_toplevel())
        self._dialog.grab_set()
        self._dialog.resizable(True, True)

        self._build()

    # Created by gpt-5.4 | 2026-03-07
    def _build(self) -> None:
        panel = tk.Frame(self._dialog, bg=self._app._palette["panel"])
        panel.pack(fill="both", expand=True, padx=16, pady=16)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        tk.Label(
            panel,
            text="Detected media players",
            font=self._app._mono(weight="bold"),
            bg=self._app._palette["panel"],
            fg=self._app._ui_colors["accent_font"],
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        list_frame = tk.Frame(panel, bg=self._app._palette["panel"])
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            list_frame,
            font=self._app._mono(),
            bg=self._app._palette["panel2"],
            fg=self._app._palette["text"],
            selectbackground=self._app._ui_colors["accent_line"],
            selectforeground=self._app._palette["panel2"],
            highlightthickness=2,
            highlightbackground=self._app._palette["edge2"],
            highlightcolor=self._app._ui_colors["accent_line"],
            relief="flat",
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self._listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=scrollbar.set)

        for option in self._options:
            self._listbox.insert(tk.END, f"{option.label}  |  {option.source}  |  {option.path}")

        if self._options:
            self._listbox.selection_set(0)
            self._listbox.activate(0)

        self._listbox.bind("<Double-Button-1>", self._accept)

        button_row = tk.Frame(panel, bg=self._app._palette["panel"])
        button_row.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        self._app._make_btn(button_row, "SELECT", self._accept, kind="primary").pack(side="right")
        self._app._make_btn(button_row, "CANCEL", self._cancel, kind="secondary").pack(side="right", padx=(0, 10))

        self._dialog.geometry("1080x360")
        self._dialog.minsize(820, 280)

    # Created by gpt-5.4 | 2026-03-07
    def _accept(self, _event=None) -> None:
        selection = self._listbox.curselection()
        if not selection:
            messagebox.showinfo("Select a player", "Pick a video player from the list.", parent=self._dialog)
            return
        self._selected_path = self._options[int(selection[0])].path
        self._dialog.destroy()

    # Created by gpt-5.4 | 2026-03-07
    def _cancel(self, _event=None) -> None:
        self._dialog.destroy()

    # Created by gpt-5.4 | 2026-03-07
    def show(self) -> str | None:
        self._parent.wait_window(self._dialog)
        return self._selected_path


# Created by gpt-5.4 | 2026-03-07
def video_player_pick(parent: tk.Widget, app, options: list[VideoPlayerCandidate]) -> str | None:
    """Open a picker dialog for already-discovered media-player options."""

    if not options:
        return None
    return VideoPlayerPickerDialog(parent, app, options).show()
