from __future__ import annotations

import tkinter as tk


# Created by gpt-5.4 | 2026-03-07
class GuiTooltip:
    """Show a lightweight tooltip for a Tk widget."""

    # Created by gpt-5.4 | 2026-03-07
    def __init__(
        self,
        widget: tk.Widget,
        text: str,
        *,
        bg: str,
        fg: str,
        border: str,
        delay_ms: int = 250,
    ) -> None:
        self._widget = widget
        self._text = text
        self._bg = bg
        self._fg = fg
        self._border = border
        self._delay_ms = delay_ms
        self._after_id: str | None = None
        self._tooltip_window: tk.Toplevel | None = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    # Created by gpt-5.4 | 2026-03-07
    def _schedule(self, _event=None) -> None:
        self._cancel_pending()
        self._after_id = self._widget.after(self._delay_ms, self._show)

    # Created by gpt-5.4 | 2026-03-07
    def _cancel_pending(self) -> None:
        if self._after_id is None:
            return
        self._widget.after_cancel(self._after_id)
        self._after_id = None

    # Created by gpt-5.4 | 2026-03-07
    def _show(self) -> None:
        self._after_id = None
        if self._tooltip_window is not None:
            return

        x = self._widget.winfo_rootx() + 18
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 8

        tooltip = tk.Toplevel(self._widget)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{x}+{y}")
        tooltip.configure(bg=self._border)

        tk.Label(
            tooltip,
            text=self._text,
            bg=self._bg,
            fg=self._fg,
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
        ).pack(padx=1, pady=1)

        self._tooltip_window = tooltip

    # Created by gpt-5.4 | 2026-03-07
    def _hide(self, _event=None) -> None:
        self._cancel_pending()
        if self._tooltip_window is None:
            return
        self._tooltip_window.destroy()
        self._tooltip_window = None
