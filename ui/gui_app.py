from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from queue import Empty, Queue

import tkinter as tk
from tkinter import filedialog, messagebox

from config import GUI
from ui.gui_config_editor import ConfigEditor
from ui.gui_helpers import FileRowState, format_duration_display, format_size_mb, get_video_duration_seconds
from ui.gui_output_rows import file_grid_cell_create, output_row_create
from ui.gui_pages import MainPage
from ui.gui_process_helpers import progress_line_mirror_should, result_line_paths_parse
from ui.gui_settings_page import SettingsPage
from ui.gui_ffmpeg_formatter import format_ffmpeg_progress_line, reset_progress_counter
from ui.gui_outputs import save_fixed_outputs as gui_save_fixed_outputs
from utils.processing_alert import processing_complete_alert_play
from utils.path_helpers import make_processed_output_path
from utils.video_player_launch import video_player_open


class AVCleanerGUI(tk.Tk):
    # Created by gpt-5.2 | 2026-01-08_01
    def __init__(self, *, project_dir: Path | None = None) -> None:
        # Modified by gpt-5.4 | 2026-03-07
        super().__init__()

        self._project_dir = project_dir or Path(__file__).resolve().parents[1]

        self.title("AV Cleaner")

        # Accent colors are intentionally split so users can theme captions vs accent-fonts vs lines.
        neon_green = "#39FF14"
        self._ui_colors = {
            "button_caption": str(GUI.get("ui_button_caption_color", neon_green)),
            "accent_font": str(GUI.get("ui_accent_font_color", neon_green)),
            "accent_line": str(GUI.get("ui_accent_line_color", neon_green)),
        }
        self._panel_outline_thickness = 1

        self._palette = {
            "bg": "#0B0D10",
            "panel": "#12161B",
            "panel2": "#0F1318",
            "text": "#E9EEF5",
            "muted": "#A3ABB8",
            "edge": "#E9EEF5",
            "edge2": "#2C3440",
            "danger": "#FF3B30",
            "good": "#00E676",
        }

        self._fonts = {
            "family": str(GUI.get("font_family", "Segoe UI")),
            "mono_family": str(GUI.get("font_mono_family", "Cascadia Mono")),
            "title": int(GUI.get("font_title_size", 18)),
            "section": int(GUI.get("font_section_size", 11)),
            "body": int(GUI.get("font_body_size", 10)),
            "mono": int(GUI.get("font_mono_size", 9)),
        }

        self._button_height = int(GUI.get("button_height", 12))

        # Pane width proportions — used as Tkinter grid column weights.
        # Values should sum to 100; ratio drives the split.
        self._pane_console_width_pct = int(GUI.get("pane_console_width_pct", 50))
        self._pane_filler_words_found_pct = int(GUI.get("pane_filler_words_found_pct", 50))

        width = int(GUI.get("gui_width", 1100))
        height = int(GUI.get("gui_height", 720))
        self.geometry(f"{width}x{height}")
        self.minsize(940, 620)

        self.configure(bg=self._palette["bg"])

        self._rows: dict[str, FileRowState] = {}
        self._modded_rows: dict[str, FileRowState] = {}
        self._status_var = tk.StringVar(value="Ready")

        self._log_queue: Queue[str] = Queue()
        self._progress_queue: Queue[str] = Queue()
        self._proc: subprocess.Popen | None = None

        # Processing control state
        self._proc_paused: bool = False
        self._proc_stop_requested: bool = False

        # Button references registered by MainPage after build
        self._proc_process_btn: tk.Button | None = None
        self._proc_pause_btn: tk.Button | None = None
        self._proc_stop_btn: tk.Button | None = None

        self._build_shell()
        self._poll_log_queue()

    def _f(self, size: int, weight: str = "normal", family: str | None = None) -> tuple[str, int, str]:
        return (family or self._fonts["family"], size, weight)

    def _mono(self, size: int | None = None, weight: str = "normal") -> tuple[str, int, str]:
        return (self._fonts["mono_family"], int(size or self._fonts["mono"]), weight)

    def _style_label(self, w: tk.Label, *, fg: str | None = None, bg: str | None = None) -> None:
        w.configure(
            bg=bg or self._palette["panel"],
            fg=fg or self._palette["text"],
        )

    def _make_panel(self, parent: tk.Widget, title: str) -> tk.Frame:
        # Modified by Claude-4.5-Sonnet | 2026-01-08_03
        outer = tk.Frame(
            parent,
            bg=self._palette["panel"],
            highlightthickness=self._panel_outline_thickness,
            highlightbackground=self._ui_colors["accent_line"],
            highlightcolor=self._ui_colors["accent_line"],
            relief="flat",
            bd=0,
        )

        # Bold header with accent stripe
        hdr = tk.Frame(outer, bg=self._palette["panel2"], highlightthickness=0, bd=0)
        hdr.pack(fill="x")

        # Accent stripe on left edge
        stripe = tk.Frame(hdr, bg=self._ui_colors["accent_line"], width=6)
        stripe.pack(side="left", fill="y")

        lbl = tk.Label(hdr, text=title.upper(), font=self._f(self._fonts["section"], "bold"))
        lbl.configure(bg=self._palette["panel2"], fg=self._ui_colors["accent_font"])
        lbl.pack(side="left", padx=16, pady=3)

        body = tk.Frame(outer, bg=self._palette["panel"])
        body.pack(fill="both", expand=True, padx=16, pady=12)
        outer.body = body  # type: ignore[attr-defined]
        return outer

    def _make_btn(self, parent: tk.Widget, text: str, command, *, kind: str = "primary") -> tk.Button:
        # Modified by Claude-4.5-Sonnet | 2026-01-08_04
        # Flat buttons with caption color controlled via config.

        # Metallic gradient simulation: dark gunmetal with highlights
        bg_metal_dark = "#2A2D32"
        bg_metal_light = "#3A3F47"
        bg_metal = bg_metal_light if kind == "primary" else bg_metal_dark

        fg_caption = self._ui_colors["button_caption"]

        # Edge color: matches background when inactive (invisible outline)
        edge_invisible = bg_metal
        edge_glow = self._ui_colors["accent_line"]

        # Calculate height in text lines (approximation for visual consistency)
        # Tkinter button height is in text lines, not pixels
        btn_height_lines = max(1, self._button_height // 10)

        btn = tk.Button(
            parent,
            text=text,
            command=command,
            font=self._f(self._fonts["body"], "bold"),
            bg=bg_metal,
            fg=fg_caption,
            activebackground=bg_metal,
            activeforeground=fg_caption,
            relief="flat",
            bd=0,
            highlightthickness=3,
            highlightbackground=edge_invisible,
            highlightcolor=edge_invisible,
            height=btn_height_lines,
            padx=16,
            pady=0,
        )

        # Cursor
        try:
            btn.configure(cursor="hand2")
        except tk.TclError:
            pass

        # Hover effects: light up edges
        def _enter(_evt=None) -> None:
            btn.configure(
                highlightbackground=edge_glow,
                highlightcolor=edge_glow,
                bg="#454C57",
                relief="flat",
            )

        def _leave(_evt=None) -> None:
            btn.configure(
                highlightbackground=edge_invisible,
                highlightcolor=edge_invisible,
                bg=bg_metal,
                relief="flat",
            )

        btn.bind("<Enter>", _enter)
        btn.bind("<Leave>", _leave)
        return btn

    def _build_shell(self) -> None:
        # Top bar
        top = tk.Frame(self, bg=self._palette["bg"])
        top.pack(fill="x", padx=18, pady=(18, 8))

        title = tk.Label(
            top,
            text="AV CLEANER",
            font=self._f(self._fonts["title"], "bold"),
            bg=self._palette["bg"],
            fg=self._palette["text"],
        )
        title.pack(side="left")

        nav = tk.Frame(top, bg=self._palette["bg"])
        nav.pack(side="right")

        self._page_container = tk.Frame(self, bg=self._palette["bg"])
        self._page_container.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self._page_container.grid_rowconfigure(0, weight=1)
        self._page_container.grid_columnconfigure(0, weight=1)

        self._pages: dict[str, tk.Frame] = {}
        self._pages["main"] = MainPage(self._page_container, app=self)
        self._pages["settings"] = SettingsPage(self._page_container, app=self)
        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        # Action buttons: PROCESS (always visible) | PAUSE/STOP (visible during processing).
        # Nested in a grid sub-frame so grid_remove() works for show/hide without
        # disturbing the surrounding pack layout.
        action_frame = tk.Frame(nav, bg=self._palette["bg"])
        action_frame.pack(side="left", padx=(0, 10))

        process_btn = self._make_btn(action_frame, "PROCESS", self._run_clicked, kind="primary")
        process_btn.grid(row=0, column=0, padx=(0, 6), sticky="w")

        pause_btn = self._make_btn(action_frame, "PAUSE", self.pause_processing, kind="secondary")
        pause_btn.grid(row=0, column=1, padx=(0, 6), sticky="w")
        pause_btn.grid_remove()  # hidden until processing starts

        stop_btn = self._make_btn(action_frame, "STOP", self.stop_processing, kind="secondary")
        stop_btn.grid(row=0, column=2, padx=(0, 6), sticky="w")
        stop_btn.grid_remove()  # hidden until processing starts

        # Register early so _proc_ui_update works from the moment pages are built.
        self.register_action_buttons(process_btn, pause_btn, stop_btn)

        self._nav_main_btn = self._make_btn(nav, "MAIN", lambda: self.show_page("main"), kind="secondary")
        self._nav_main_btn.pack(side="left", padx=(0, 10))
        self._nav_settings_btn = self._make_btn(nav, "SETTINGS", lambda: self.show_page("settings"), kind="secondary")
        self._nav_settings_btn.pack(side="left", padx=(0, 10))
        self._nav_restart_btn = self._make_btn(nav, "RESTART APP", self._restart_app, kind="secondary")
        self._nav_restart_btn.pack(side="left")

        # Status bar
        status = tk.Frame(self, bg=self._palette["panel2"], highlightthickness=2, highlightbackground=self._palette["edge2"])
        status.pack(fill="x", padx=18, pady=(0, 18))
        tk.Label(
            status,
            text="STATUS",
            font=self._mono(self._fonts["mono"], "bold"),
            bg=self._palette["panel2"],
            fg=self._palette["muted"],
        ).pack(side="left", padx=12, pady=10)
        tk.Label(
            status,
            textvariable=self._status_var,
            font=self._mono(self._fonts["mono"]),
            bg=self._palette["panel2"],
            fg=self._palette["text"],
        ).pack(side="left", padx=10, pady=10)

        self.show_page("main")

    def show_page(self, name: str) -> None:
        page = self._pages[name]
        page.tkraise()

    def set_status(self, text: str) -> None:
        self._status_var.set(text)

    # Created by gpt-5.4 | 2026-03-08
    def _restart_app(self) -> None:
        """Launch a fresh GUI process, then close the current window.

        This mirrors the user's manual workflow of closing the app and running
        `python app.py` again from the project root.
        """

        restart_cmd = [sys.executable, "app.py"]

        try:
            self.append_log("[GUI] Restarting app...\n")
        except Exception:
            pass

        try:
            subprocess.Popen(restart_cmd, cwd=str(self._project_dir))
        except Exception as exc:
            self.set_status("Restart failed")
            messagebox.showerror("Restart failed", f"Could not restart app.\n\n{exc}")
            return

        self.destroy()

    def _run_clicked(self) -> None:
        # Created by coder-sr | 2026-03-14 — moved from MainPage._run_clicked
        # "PROCESS" requires both files because it performs sync-preserving edits
        # that must be applied to host + guest together.
        host_row = self._rows.get("host")
        guest_row = self._rows.get("guest")
        host = host_row.path if host_row else None
        guest = guest_row.path if guest_row else None
        if not host or not guest:
            messagebox.showwarning("Missing files", "Select both HOST and GUEST files first.")
            return
        self.run_processing(host, guest)

    def clear_logs(self) -> None:
        self._log_queue.put("__CLEAR__")

    # Modified by gpt-5.4 | 2026-03-15
    def _gui_line_sanitize(self, text: str) -> str:
        """Remove redundant logging level text from GUI-only display lines."""

        sanitized = text.replace(" - INFO - ", " ")
        sanitized = sanitized.replace("â€”", " ")
        sanitized = sanitized.replace("—", " ")
        return sanitized

    def append_log(self, text: str) -> None:
        self._log_queue.put(self._gui_line_sanitize(text))

    def clear_progress(self) -> None:
        self._progress_queue.put("__CLEAR__")

    def append_progress(self, text: str) -> None:
        self._progress_queue.put(self._gui_line_sanitize(text))

    # Created by gpt-5.4 | 2026-03-08
    def _reload_runtime_settings(self) -> bool:
        """Refresh config-backed GUI settings from `config.py` before a run starts."""

        config_path = self._project_dir / "config.py"
        try:
            gui_dict, _pipe_cfg, _qual_presets = ConfigEditor.load_gui_and_pipeline(config_path)
        except Exception as exc:
            self.append_log(f"[GUI] Failed to reload config.py: {exc}\n")
            self.set_status("Config reload failed")
            messagebox.showerror("Config load failed", str(exc))
            return False

        # Keep the imported GUI dict object current so later runtime lookups use the
        # latest values without requiring a full GUI restart.
        GUI.clear()
        GUI.update(gui_dict)

        settings_page = self._pages.get("settings")
        if settings_page is not None and hasattr(settings_page, "_reload"):
            settings_page._reload()

        return True

    def _poll_log_queue(self) -> None:
        try:
            while True:
                line = self._log_queue.get_nowait()
                if line == "__CLEAR__":
                    main: MainPage = self._pages["main"]  # type: ignore[assignment]
                    main.clear_log_view()
                else:
                    main = self._pages["main"]  # type: ignore[assignment]
                    main.append_log_view(line)
        except Empty:
            pass

        try:
            while True:
                line = self._progress_queue.get_nowait()
                if line == "__CLEAR__":
                    main: MainPage = self._pages["main"]  # type: ignore[assignment]
                    main.clear_progress_view()
                else:
                    main = self._pages["main"]  # type: ignore[assignment]
                    main.append_progress_view(line)
        except Empty:
            pass
        self.after(60, self._poll_log_queue)

    # Created by Claude-Sonnet-4.6 | 2026-03-11
    def register_action_buttons(
        self,
        process_btn: tk.Button,
        pause_btn: tk.Button,
        stop_btn: tk.Button,
    ) -> None:
        """Called by MainPage after building buttons so the app can update them."""
        self._proc_process_btn = process_btn
        self._proc_pause_btn = pause_btn
        self._proc_stop_btn = stop_btn

    # Created by Claude-Sonnet-4.6 | 2026-03-11
    def _proc_ui_update(self, running: bool) -> None:
        """Show/hide Pause+Stop and enable/disable Process to reflect state."""
        if self._proc_process_btn:
            self._proc_process_btn.configure(state="disabled" if running else "normal")
        if self._proc_pause_btn:
            if running:
                label = "RESUME" if self._proc_paused else "PAUSE"
                self._proc_pause_btn.configure(text=label)
                self._proc_pause_btn.grid()
            else:
                self._proc_pause_btn.grid_remove()
                self._proc_paused = False
        if self._proc_stop_btn:
            if running:
                self._proc_stop_btn.grid()
            else:
                self._proc_stop_btn.grid_remove()

    # Created by Claude-Sonnet-4.6 | 2026-03-11
    def _proc_tree_suspend(self) -> None:
        """Suspend the entire subprocess tree (pause all child processes too)."""
        if not self._proc:
            return
        try:
            import psutil
            parent = psutil.Process(self._proc.pid)
            # Suspend children first, then parent
            for child in parent.children(recursive=True):
                child.suspend()
            parent.suspend()
        except Exception as exc:
            self.append_log(f"[GUI] Pause failed: {exc}\n")

    # Created by Claude-Sonnet-4.6 | 2026-03-11
    def _proc_tree_resume(self) -> None:
        """Resume the entire suspended subprocess tree."""
        if not self._proc:
            return
        try:
            import psutil
            parent = psutil.Process(self._proc.pid)
            # Resume parent first, then children
            parent.resume()
            for child in parent.children(recursive=True):
                child.resume()
        except Exception as exc:
            self.append_log(f"[GUI] Resume failed: {exc}\n")

    # Modified by Claude-Sonnet-4.6 | 2026-03-12
    def _proc_tree_kill(self) -> None:
        """Kill the entire subprocess tree, including all child processes.

        On Windows, child processes (e.g. FFmpeg) are NOT automatically killed
        when their parent Python process dies.  We therefore use the Windows-native
        `taskkill /F /T /PID` command as the primary path, which atomically
        terminates the entire process tree with no snapshot race-condition.
        psutil is kept as a fallback for non-Windows platforms.
        """
        if not self._proc:
            return

        pid = self._proc.pid

        # Primary path on Windows: taskkill /F (force) /T (tree) kills the
        # parent AND all descendants in one OS call.  This is more reliable
        # than psutil on Windows because it has no snapshot timing gap.
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                )
                return
            except Exception as exc:
                self.append_log(f"[GUI] taskkill failed ({exc}); falling back to psutil\n")

        # Non-Windows (or taskkill fallback): walk the tree with psutil.
        try:
            import psutil
            parent = psutil.Process(pid)
            # Snapshot children BEFORE killing parent so the list is complete.
            children = parent.children(recursive=True)
            for child in children:
                child.kill()
            parent.kill()
        except Exception:
            # Last resort: kills only the direct parent process.
            try:
                self._proc.kill()
            except Exception:
                pass

    # Created by Claude-Sonnet-4.6 | 2026-03-11
    def pause_processing(self) -> None:
        """Toggle pause/resume on the running process tree."""
        if not self._proc or self._proc.poll() is not None:
            return

        if self._proc_paused:
            # Currently paused — resume it
            self._proc_tree_resume()
            self._proc_paused = False
            self.set_status("Running…")
            if self._proc_pause_btn:
                self._proc_pause_btn.configure(text="PAUSE")
            self.append_log("[GUI] Processing resumed.\n")
        else:
            # Currently running — pause it
            self._proc_tree_suspend()
            self._proc_paused = True
            self.set_status("Paused")
            if self._proc_pause_btn:
                self._proc_pause_btn.configure(text="RESUME")
            self.append_log("[GUI] Processing paused.\n")

    # Created by Claude-Sonnet-4.6 | 2026-03-11
    def stop_processing(self) -> None:
        """Kill the running process tree and reset UI to idle."""
        if not self._proc or self._proc.poll() is not None:
            return

        self._proc_stop_requested = True

        # If paused, resume first so the kill signal propagates cleanly
        if self._proc_paused:
            self._proc_tree_resume()
            self._proc_paused = False

        self._proc_tree_kill()
        self.append_log("[GUI] Processing stopped by user.\n")
        self.set_status("Stopped")

    # Modified by gpt-5.2 | 2026-01-13_01
    def run_processing(self, host_path: str, guest_path: str) -> None:
        # Modified by gpt-5.4 | 2026-03-07
        if self._proc and self._proc.poll() is None:
            messagebox.showwarning("Already running", "A job is already running.")
            return

        self.clear_logs()
        self.clear_progress()
        self._clear_modded_rows()

        # Reset FFmpeg progress line counter + stop-request flag for new run
        reset_progress_counter()
        self._proc_stop_requested = False
        self._proc_paused = False

        if not self._reload_runtime_settings():
            return

        self.set_status("Running…")
        self.after(0, self._proc_ui_update, True)

        cmd = [
            sys.executable,
            "main.py",
            "process",
            "--host",
            host_path,
            "--guest",
            guest_path,
        ]
        self.append_log("$ " + " ".join(cmd) + "\n")

        # Modified by gpt-5.4 | 2026-03-07
        def _worker() -> None:
            _result_host: str | None = None
            _result_guest: str | None = None
            # Flag: play the completion chime only when processing actually finished
            # (not when the user manually stopped it). Set exactly once per run so
            # the alert never fires more than once regardless of code path taken.
            _play_alert = False

            try:
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(self._project_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert self._proc.stdout is not None
                for line in self._proc.stdout:
                    # Classify each line: FFmpeg render stats vs. regular output.
                    _formatted, is_progress = format_ffmpeg_progress_line(line)

                    if is_progress:
                        # FFmpeg render-progress lines are dropped from display;
                        # the right pane is now FILLER WORDS FOUND and only shows
                        # filler-word output, not render stats.
                        pass
                    else:
                        # Pass through all non-FFmpeg lines to the CONSOLE.
                        self.append_log(line)
                        if progress_line_mirror_should(line):
                            # Mirror filler-word lines to the FILLER WORDS FOUND pane.
                            # Routing to HOST/GUEST sub-pane is handled inside
                            # MainPage.append_progress_view().
                            self.append_progress(line)

                    result_host, result_guest = result_line_paths_parse(line)
                    if result_host and result_guest:
                        _result_host = result_host
                        _result_guest = result_guest

                code = self._proc.wait()

                if self._proc_stop_requested:
                    # User-initiated stop; status already set by stop_processing()
                    pass
                elif code == 0:
                    # Use paths emitted by the pipeline, fall back to computed paths.
                    host_processed = _result_host or make_processed_output_path(host_path)
                    guest_processed = _result_guest or make_processed_output_path(guest_path)

                    if os.path.exists(host_processed):
                        self.after(0, self._set_modded_row_for_path, "host", host_processed)
                    if os.path.exists(guest_processed):
                        self.after(0, self._set_modded_row_for_path, "guest", guest_processed)

                    self.set_status("Done")
                    _play_alert = True
                else:
                    self.set_status(f"Failed (exit {code})")
                    _play_alert = True
            except Exception as e:
                self.append_log(f"\n[GUI] Failed to run: {e}\n")
                self.set_status("Failed")
                _play_alert = True
            finally:
                # Always restore buttons to idle state when the worker exits.
                self.after(0, self._proc_ui_update, False)
                # Play the completion chime exactly once, directly from the
                # worker thread.  Calling from here (not via self.after) avoids
                # coupling the sound to the Tkinter event loop — if the user
                # closes the window mid-run the chime still plays cleanly and
                # winsound never queues into a partially-destroyed Tk instance.
                if _play_alert:
                    processing_complete_alert_play()

        threading.Thread(target=_worker, daemon=True).start()

    def _create_file_row(self, parent: tk.Widget, row_index: int, role: str, *, button_text: str | None = None) -> None:
        # Modified by gpt-5.4 | 2026-03-08
        # Modified by gpt-5.4 | 2026-03-07
        role_parent = parent
        file_parent = parent
        size_parent = parent
        length_parent = parent

        if getattr(parent, "_files_grid_enabled", False):
            role_parent = file_grid_cell_create(self, parent, row_index, 0, sticky="nsew")
            file_parent = file_grid_cell_create(self, parent, row_index, 1, sticky="nsew")
            size_parent = file_grid_cell_create(self, parent, row_index, 2, sticky="nsew")
            length_parent = file_grid_cell_create(self, parent, row_index, 3, sticky="nsew")

        browse_btn = self._make_btn(
            role_parent,
            button_text or "BROWSE",
            command=lambda r=role: self._select_file(r),
            kind="secondary",
        )
        browse_btn.pack(anchor="w", padx=8, pady=6)

        file_var = tk.StringVar(value="")
        size_var = tk.StringVar(value="")
        length_var = tk.StringVar(value="")

        file_cell = tk.Frame(file_parent, bg=self._palette["panel"])
        file_cell.pack(fill="both", expand=True, padx=8, pady=6)
        file_cell.columnconfigure(1, weight=1)

        play_btn = tk.Button(
            file_cell,
            text="▶",
            command=lambda r=role: self._play_source_row(r),
            font=self._f(self._fonts["body"], "bold"),
            bg=self._palette["panel"],
            fg=self._ui_colors["accent_line"],
            activebackground=self._palette["panel2"],
            activeforeground=self._ui_colors["accent_font"],
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
        play_btn.bind("<Enter>", lambda _evt: play_btn.configure(bg=self._palette["panel2"]))
        play_btn.bind("<Leave>", lambda _evt: play_btn.configure(bg=self._palette["panel"]))

        tk.Label(
            file_cell,
            textvariable=file_var,
            anchor="w",
            font=self._mono(),
            bg=self._palette["panel"],
            fg=self._palette["text"],
        ).grid(row=0, column=1, sticky="ew")
        tk.Label(
            size_parent,
            textvariable=size_var,
            anchor="w",
            font=self._mono(),
            bg=self._palette["panel"],
            fg=self._palette["muted"],
        ).pack(anchor="w", padx=8, pady=6)
        tk.Label(
            length_parent,
            textvariable=length_var,
            anchor="w",
            font=self._mono(),
            bg=self._palette["panel"],
            fg=self._palette["muted"],
        ).pack(anchor="w", padx=8, pady=6)

        self._rows[role] = FileRowState(
            path=None,
            file_var=file_var,
            size_var=size_var,
            length_var=length_var,
            play_btn=play_btn,
        )

    # Created by gpt-5.4 | 2026-03-07
    def _create_output_row(self, parent: tk.Widget, row_index: int, role: str, *, label_text: str) -> None:
        self._modded_rows[role] = output_row_create(
            self,
            parent,
            row_index,
            role,
            label_text=label_text,
            grid_style=bool(getattr(parent, "_files_grid_enabled", False)),
        )

    # Created by gpt-5.4 | 2026-03-07
    def _play_modded_row(self, role: str) -> None:
        """Open a processed host/guest output in the configured video player."""

        row = self._modded_rows[role]
        if not row.path:
            messagebox.showinfo("Play", "No processed video is available yet.")
            return

        try:
            video_player_open(row.path, player_path=str(GUI.get("default_video_player", "")))
            self.set_status(f"Opened {os.path.basename(row.path)}")
        except (FileNotFoundError, OSError) as exc:
            messagebox.showerror("Play failed", str(exc))

    # Created by gpt-5.4 | 2026-03-07
    def _play_source_row(self, role: str) -> None:
        """Open a selected source host/guest video in the configured video player."""

        row = self._rows[role]
        if not row.path:
            messagebox.showinfo("Play", "No source video is selected yet.")
            return

        try:
            video_player_open(row.path, player_path=str(GUI.get("default_video_player", "")))
            self.set_status(f"Opened {os.path.basename(row.path)}")
        except (FileNotFoundError, OSError) as exc:
            messagebox.showerror("Play failed", str(exc))

    def _select_file(self, role: str) -> None:
        # Modified by gpt-5.4 | 2026-03-07
        title = "Select Host Video" if role == "host" else "Select Guest Video"
        video_path = filedialog.askopenfilename(
            title=title,
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.avi *.m4v"),
                ("All files", "*.*"),
            ],
        )
        if not video_path:
            return

        self._clear_modded_rows()
        self._set_row_for_path(role=role, video_path=video_path)

    def _set_row_for_path(self, role: str, video_path: str) -> None:
        # Modified by gpt-5.4 | 2026-03-07
        row = self._rows[role]
        self._populate_file_row(row, video_path)

    # Created by gpt-5.4 | 2026-03-07
    def _set_modded_row_for_path(self, role: str, video_path: str) -> None:
        self._populate_file_row(self._modded_rows[role], video_path)

    # Created by gpt-5.4 | 2026-03-07
    def _populate_file_row(self, row: FileRowState, video_path: str) -> None:
        # Modified by gpt-5.4 | 2026-03-07
        row.path = video_path
        row.file_var.set(os.path.basename(video_path))
        if row.play_btn is not None:
            row.play_btn.grid()

        try:
            size_bytes = os.path.getsize(video_path)
            row.size_var.set(format_size_mb(size_bytes))
        except OSError:
            row.size_var.set("")

        try:
            duration_s = get_video_duration_seconds(video_path)
            row.length_var.set(format_duration_display(duration_s))
        except Exception:
            row.length_var.set("")

    # Created by gpt-5.4 | 2026-03-07
    def _clear_modded_rows(self) -> None:
        # Modified by gpt-5.4 | 2026-03-07
        for row in self._modded_rows.values():
            row.path = None
            row.file_var.set("")
            row.size_var.set("")
            row.length_var.set("")
            if row.play_btn is not None:
                row.play_btn.grid_remove()

    def save_fixed_outputs(self, host: str, guest: str) -> None:
        try:
            saved = gui_save_fixed_outputs(host, guest, project_dir=self._project_dir)
            if not saved:
                return
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            return

        self.append_log("[GUI] Saved fixed copies:\n" + "\n".join(f"  {p}" for p in saved) + "\n")
        self.set_status("Saved _fixed files")


def main() -> None:
    app = AVCleanerGUI()
    app.mainloop()

