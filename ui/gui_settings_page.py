from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from ui.gui_config_editor import ConfigEditor
from ui.video_player_picker import video_player_pick
from utils.video_player_discovery import video_player_discover, video_player_platform_label


# Settings page layout tuning
# - Increase this value to make both panes shorter and lift footer buttons up.
SETTINGS_PANES_HEIGHT_REDUCTION_PX = 120
# - Vertical gap between GUI-pane input rows.
SETTINGS_GUI_FIELD_ROW_GAP_PX = 4


class SettingsPage(tk.Frame):
    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent, bg=app._palette["bg"])
        self._app = app
        self._config_path = app._project_dir / "config.py"

        # Footer (packed first to reserve space at bottom)
        footer = tk.Frame(self, bg=app._palette["bg"])
        # Bottom padding reserves space so the footer buttons sit higher, and both panes
        # lose the same amount of vertical space.
        footer.pack(side="bottom", fill="x", pady=(14, SETTINGS_PANES_HEIGHT_REDUCTION_PX))
        app._make_btn(footer, "SAVE TO config.py", self._save, kind="primary").pack(side="right")
        app._make_btn(footer, "RELOAD", self._reload, kind="secondary").pack(side="right", padx=(0, 12))

        # Grid (panes) takes remaining space
        grid = tk.Frame(self, bg=app._palette["bg"])
        grid.pack(side="top", fill="both", expand=True)
        grid.grid_rowconfigure(0, weight=1)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)

        gui_panel = app._make_panel(grid, "GUI")
        gui_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self._build_gui_form(gui_panel.body)

        pipeline_panel = app._make_panel(grid, "Pipeline")
        pipeline_panel.grid(row=0, column=1, sticky="nsew")
        self._build_pipeline_form(pipeline_panel.body)

        self._reload()

    # Modified by gpt-5.4 | 2026-03-07
    def _build_gui_form(self, parent: tk.Frame) -> None:
        app = self._app
        self._vars: dict[str, tk.StringVar] = {
            "gui_width": tk.StringVar(),
            "gui_height": tk.StringVar(),
            "font_family": tk.StringVar(),
            "font_title_size": tk.StringVar(),
            "font_section_size": tk.StringVar(),
            "font_body_size": tk.StringVar(),
            "font_mono_family": tk.StringVar(),
            "font_mono_size": tk.StringVar(),
            "button_height": tk.StringVar(),
            "default_video_player": tk.StringVar(),
            # Accent colors (split for easy theming)
            "ui_button_caption_color": tk.StringVar(),
            "ui_accent_font_color": tk.StringVar(),
            "ui_accent_line_color": tk.StringVar(),
            # Console / Filler Words Found pane width split (column weights)
            "pane_console_width_pct": tk.StringVar(),
            "pane_filler_words_found_pct": tk.StringVar(),
        }

        def add_row(label: str, key: str) -> None:
            row = tk.Frame(parent, bg=app._palette["panel"])
            row.pack(fill="x", pady=SETTINGS_GUI_FIELD_ROW_GAP_PX)
            tk.Label(
                row,
                text=label,
                font=app._mono(weight="bold"),
                bg=app._palette["panel"],
                fg=app._palette["muted"],
            ).pack(side="left")
            ent = tk.Entry(
                row,
                textvariable=self._vars[key],
                font=app._mono(),
                bg=app._palette["panel2"],
                fg=app._palette["text"],
                insertbackground=app._ui_colors["accent_line"],
                relief="flat",
                highlightthickness=2,
                highlightbackground=app._palette["edge2"],
                highlightcolor=app._ui_colors["accent_line"],
            )
            ent.pack(side="right", fill="x", expand=True)

        add_row("Window width", "gui_width")
        add_row("Window height", "gui_height")
        add_row("Font family", "font_family")
        add_row("Title size", "font_title_size")
        add_row("Section size", "font_section_size")
        add_row("Body size", "font_body_size")
        add_row("Mono family", "font_mono_family")
        add_row("Mono size", "font_mono_size")
        add_row("Button height", "button_height")

        player_row = tk.Frame(parent, bg=app._palette["panel"])
        player_row.pack(fill="x", pady=SETTINGS_GUI_FIELD_ROW_GAP_PX)
        tk.Label(
            player_row,
            text="Default Video Player",
            font=app._mono(weight="bold"),
            bg=app._palette["panel"],
            fg=app._palette["muted"],
        ).pack(side="left")
        app._make_btn(player_row, "SCAN", self._scan_default_video_player, kind="secondary").pack(side="right")
        player_ent = tk.Entry(
            player_row,
            textvariable=self._vars["default_video_player"],
            font=app._mono(),
            bg=app._palette["panel2"],
            fg=app._palette["text"],
            insertbackground=app._ui_colors["accent_line"],
            relief="flat",
            highlightthickness=2,
            highlightbackground=app._palette["edge2"],
            highlightcolor=app._ui_colors["accent_line"],
        )
        player_ent.pack(side="right", fill="x", expand=True, padx=(12, 8))

        add_row("Button caption color", "ui_button_caption_color")
        add_row("Accent font color", "ui_accent_font_color")
        add_row("Accent line color", "ui_accent_line_color")
        add_row("Console pane width %", "pane_console_width_pct")
        add_row("Filler Words pane width %", "pane_filler_words_found_pct")

        note = tk.Label(
            parent,
            text=(
                "These values are written into the GUI dict in config.py.\n"
                "SCAN detects media players for the current operating system.\n"
                "Choose one, then use SAVE TO config.py to persist it.\n"
                "Restart GUI to fully apply typography/layout/color changes.\n"
                "Colors accept #RRGGBB."
            ),
            font=app._mono(),
            bg=app._palette["panel"],
            fg=app._palette["muted"],
            justify="left",
        )
        note.pack(anchor="w", pady=(14, 0))

    # Created by gpt-5.4 | 2026-03-07
    def _scan_default_video_player(self) -> None:
        options = video_player_discover()
        if not options:
            platform_label = video_player_platform_label()
            messagebox.showinfo(
                "No media players found",
                f"No supported media players were found for {platform_label}.",
            )
            return

        selected_path = video_player_pick(self, self._app, options)
        if not selected_path:
            return

        self._vars["default_video_player"].set(selected_path)

        player_name = Path(selected_path).name
        self._app.set_status(f"Default video player selected: {player_name}. Click SAVE TO config.py.")

    # Modified by gpt-5.4 | 2026-03-15
    def _build_pipeline_form(self, parent: tk.Frame) -> None:
        app = self._app
        self._pipe_vars: dict[str, tk.BooleanVar] = {}

        self._word_vars: dict[str, tk.StringVar] = {
            "words_to_remove": tk.StringVar(),
            "confidence_required": tk.StringVar(value="0.95"),
            "confidence_bonus_per_word": tk.StringVar(value="0.05"),
            "filler_mute_inset_ms": tk.StringVar(value="30"),
            "filler_mute_gap_threshold_ms": tk.StringVar(value="60"),
        }

        # Quality preset vars (PODCAST_HIGH_QUALITY)
        self._qual_vars: dict[str, tk.StringVar] = {
            "silence_threshold_db": tk.StringVar(value="-45"),
            "max_pause_duration": tk.StringVar(value="2"),
            "new_pause_duration": tk.StringVar(value="0.5"),
            "silence_window_ms": tk.StringVar(value="100"),
            "spike_threshold_db": tk.StringVar(value="-5"),
            "normalization_standard_target": tk.StringVar(value="-16.0"),
            "normalization_max_gain_db": tk.StringVar(value="15.0"),
        }
        # Encoder vars
        self._enc_mode = tk.StringVar(value="cpu")
        self._enc_quality = tk.StringVar(value="18")

        # Extended encoder and rendering vars (all QUALITY_PRESETS fields not covered above)
        self._enc_str_vars: dict[str, tk.StringVar] = {
            "video_codec": tk.StringVar(value="libx264"),
            "video_preset": tk.StringVar(value="fast"),
            "audio_codec": tk.StringVar(value="aac"),
            "audio_bitrate": tk.StringVar(value="320k"),
            "nvenc_codec": tk.StringVar(value="h264_nvenc"),
            "nvenc_preset": tk.StringVar(value="p4"),
            "nvenc_rc": tk.StringVar(value="vbr"),
            "chunk_size": tk.StringVar(value="50"),
            "keyframe_snap_tolerance_s": tk.StringVar(value="0.1"),
            "cut_fade_ms": tk.StringVar(value="16"),
        }
        self._enc_bool_vars: dict[str, tk.BooleanVar] = {
            "cuda_decode_enabled": tk.BooleanVar(value=True),
            "cuda_require_support": tk.BooleanVar(value=True),
            "chunk_parallel_enabled": tk.BooleanVar(value=True),
            "two_phase_render_enabled": tk.BooleanVar(value=False),
        }

        # Scrollable container for pipeline pane
        outer = tk.Frame(parent, bg=app._palette["panel"])
        outer.pack(fill="both", expand=True)

        self._pipe_canvas = tk.Canvas(
            outer,
            bg=app._palette["panel"],
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self._pipe_scroll = tk.Scrollbar(outer, orient="vertical", command=self._pipe_canvas.yview)
        self._pipe_canvas.configure(yscrollcommand=self._pipe_scroll.set)

        self._pipe_scroll.pack(side="right", fill="y")
        self._pipe_canvas.pack(side="left", fill="both", expand=True)

        self._pipe_container = tk.Frame(self._pipe_canvas, bg=app._palette["panel"])
        self._pipe_window = self._pipe_canvas.create_window((0, 0), window=self._pipe_container, anchor="nw")

        def _on_container_configure(_evt=None):
            self._pipe_canvas.configure(scrollregion=self._pipe_canvas.bbox("all"))

        def _on_canvas_configure(_evt=None):
            # Keep inner frame width in sync with canvas width.
            self._pipe_canvas.itemconfigure(self._pipe_window, width=self._pipe_canvas.winfo_width())

        self._pipe_container.bind("<Configure>", _on_container_configure)
        self._pipe_canvas.bind("<Configure>", _on_canvas_configure)

        # Mousewheel scrolling (Windows/macOS)
        def _on_mousewheel(evt):
            # On Windows, evt.delta is typically multiples of 120
            delta = int(-1 * (evt.delta / 120)) if getattr(evt, "delta", 0) else 0
            if delta:
                self._pipe_canvas.yview_scroll(delta, "units")

        def _bind_mousewheel(_evt=None):
            self._pipe_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(_evt=None):
            self._pipe_canvas.unbind_all("<MouseWheel>")

        self._pipe_canvas.bind("<Enter>", _bind_mousewheel)
        self._pipe_canvas.bind("<Leave>", _unbind_mousewheel)

    # Modified by gpt-5.4 | 2026-03-15
    def _render_pipeline_toggles(self, pipe_cfg: dict, qual_presets: dict, words_cfg: dict) -> None:
        app = self._app
        for c in self._pipe_container.winfo_children():
            c.destroy()

        self._pipe_vars.clear()

        # Load encoding settings (assuming generic 'PODCAST_HIGH_QUALITY' preset)
        preset = qual_presets.get("PODCAST_HIGH_QUALITY", {})

        # Load quality-preset settings
        self._qual_vars["silence_threshold_db"].set(str(preset.get("silence_threshold_db", -45)))
        self._qual_vars["max_pause_duration"].set(str(preset.get("max_pause_duration", 2)))
        self._qual_vars["new_pause_duration"].set(str(preset.get("new_pause_duration", 0.5)))
        self._qual_vars["silence_window_ms"].set(str(preset.get("silence_window_ms", 100)))
        self._qual_vars["spike_threshold_db"].set(str(preset.get("spike_threshold_db", -5)))

        norm = preset.get("normalization")
        if not isinstance(norm, dict):
            norm = {}
        self._qual_vars["normalization_standard_target"].set(
            str(norm.get("target_lufs", norm.get("standard_target", -16.0)))
        )
        self._qual_vars["normalization_max_gain_db"].set(str(norm.get("max_gain_db", 15.0)))

        cuda_enabled = bool(preset.get("cuda_encode_enabled", False))
        self._enc_mode.set("gpu" if cuda_enabled else "cpu")

        # Default quality display (CRF as master, or fallback to NVENC CQ)
        start_q = preset.get("crf", 23)
        self._enc_quality.set(str(start_q))

        # Load extended encoder / rendering settings
        self._enc_str_vars["video_codec"].set(str(preset.get("video_codec", "libx264")))
        self._enc_str_vars["video_preset"].set(str(preset.get("video_preset", "fast")))
        self._enc_str_vars["audio_codec"].set(str(preset.get("audio_codec", "aac")))
        self._enc_str_vars["audio_bitrate"].set(str(preset.get("audio_bitrate", "320k")))
        nvenc_blk = preset.get("nvenc", {})
        if not isinstance(nvenc_blk, dict):
            nvenc_blk = {}
        self._enc_str_vars["nvenc_codec"].set(str(nvenc_blk.get("codec", "h264_nvenc")))
        self._enc_str_vars["nvenc_preset"].set(str(nvenc_blk.get("preset", "p4")))
        self._enc_str_vars["nvenc_rc"].set(str(nvenc_blk.get("rc", "vbr")))
        self._enc_str_vars["chunk_size"].set(str(preset.get("chunk_size", 50)))
        self._enc_str_vars["keyframe_snap_tolerance_s"].set(str(preset.get("keyframe_snap_tolerance_s", 0.1)))
        self._enc_str_vars["cut_fade_ms"].set(str(preset.get("cut_fade_ms", 16)))
        self._enc_bool_vars["cuda_decode_enabled"].set(bool(preset.get("cuda_decode_enabled", True)))
        self._enc_bool_vars["cuda_require_support"].set(bool(preset.get("cuda_require_support", True)))
        self._enc_bool_vars["chunk_parallel_enabled"].set(bool(preset.get("chunk_parallel_enabled", True)))
        self._enc_bool_vars["two_phase_render_enabled"].set(bool(preset.get("two_phase_render_enabled", False)))

        words_to_remove = words_cfg.get("words_to_remove", [])
        if not isinstance(words_to_remove, list):
            words_to_remove = []
        self._word_vars["words_to_remove"].set(", ".join(str(word).strip() for word in words_to_remove if str(word).strip()))
        self._word_vars["confidence_required"].set(str(words_cfg.get("confidence_required", 0.95)))
        self._word_vars["confidence_bonus_per_word"].set(str(words_cfg.get("confidence_bonus_per_word", 0.05)))
        self._word_vars["filler_mute_inset_ms"].set(str(words_cfg.get("filler_mute_inset_ms", 30)))
        self._word_vars["filler_mute_gap_threshold_ms"].set(str(words_cfg.get("filler_mute_gap_threshold_ms", 60)))

        def mk_section(title: str) -> tk.Frame:
            tk.Label(
                self._pipe_container,
                text=title,
                font=app._mono(weight="bold"),
                bg=app._palette["panel"],
                fg=app._palette["muted"],
            ).pack(anchor="w")
            sec = tk.Frame(self._pipe_container, bg=app._palette["panel"])
            sec.pack(fill="x", pady=(8, 14))
            return sec

        def mk_toggle(sec: tk.Frame, key: str, label: str, initial: bool) -> None:
            var = tk.BooleanVar(value=initial)
            self._pipe_vars[key] = var
            row = tk.Frame(sec, bg=app._palette["panel"])
            row.pack(fill="x", pady=4)
            chk = tk.Checkbutton(
                row,
                text=label,
                variable=var,
                font=app._mono(),
                bg=app._palette["panel"],
                fg=app._palette["text"],
                activebackground=app._palette["panel"],
                activeforeground=app._palette["text"],
                selectcolor=app._palette["panel2"],
                highlightthickness=0,
                bd=0,
            )
            chk.pack(side="left")

        def mk_kv_row(sec: tk.Frame, label: str, var: tk.StringVar, width: int = 10) -> None:
            row = tk.Frame(sec, bg=app._palette["panel"])
            row.pack(fill="x", pady=4)
            tk.Label(
                row,
                text=label,
                font=app._mono(weight="bold"),
                bg=app._palette["panel"],
                fg=app._palette["text"],
            ).pack(side="left")
            ent = tk.Entry(
                row,
                textvariable=var,
                font=app._mono(),
                bg=app._palette["panel2"],
                fg=app._palette["text"],
                insertbackground=app._ui_colors["accent_line"],
                relief="flat",
                highlightthickness=2,
                highlightbackground=app._palette["edge2"],
                highlightcolor=app._ui_colors["accent_line"],
                width=width,
            )
            # Add a small right padding so inputs don't visually touch the scrollbar.
            ent.pack(side="right", padx=(0, 5))

        # --- Quality Presets Section ---
        qual_sec = mk_section("QUALITY PRESETS")
        mk_kv_row(qual_sec, "Silence threshold (dB)", self._qual_vars["silence_threshold_db"], width=10)
        mk_kv_row(qual_sec, "Max pause duration (sec)", self._qual_vars["max_pause_duration"], width=10)
        mk_kv_row(qual_sec, "New pause duration (sec)", self._qual_vars["new_pause_duration"], width=10)
        mk_kv_row(qual_sec, "Silence window (ms)", self._qual_vars["silence_window_ms"], width=10)
        mk_kv_row(qual_sec, "Spike threshold (dB)", self._qual_vars["spike_threshold_db"], width=10)

        tk.Label(
            qual_sec,
            text="Normalization: Standard LUFS (fixed)",
            font=app._mono(weight="bold"),
            bg=app._palette["panel"],
            fg=app._palette["text"],
        ).pack(anchor="w", pady=(6, 8))

        mk_kv_row(qual_sec, "Standard target (LUFS)", self._qual_vars["normalization_standard_target"], width=10)
        mk_kv_row(qual_sec, "Max gain (dB)", self._qual_vars["normalization_max_gain_db"], width=10)

        proc_sec = mk_section("PROCESSORS")
        for i, p in enumerate(pipe_cfg.get("processors", [])):
            t = str(p.get("type"))
            mk_toggle(proc_sec, f"processors:{i}", t, bool(p.get("enabled")))

        words_sec = mk_section("FILLER WORD DETECTION")
        mk_kv_row(words_sec, "Words to remove (comma-separated)", self._word_vars["words_to_remove"], width=28)
        mk_kv_row(words_sec, "Confidence required", self._word_vars["confidence_required"], width=10)
        mk_kv_row(words_sec, "Confidence bonus per word", self._word_vars["confidence_bonus_per_word"], width=10)
        mk_kv_row(words_sec, "Mute inset (ms)", self._word_vars["filler_mute_inset_ms"], width=10)
        mk_kv_row(
            words_sec,
            "Mute gap threshold (ms)",
            self._word_vars["filler_mute_gap_threshold_ms"],
            width=10,
        )

        # --- Encoding Section ---
        enc_sec = mk_section("VIDEO ENCODING")

        # Encoder Selection
        lbl_enc = tk.Label(
            enc_sec,
            text="Encoder",
            font=app._mono(weight="bold"),
            bg=app._palette["panel"],
            fg=app._palette["text"],
        )
        lbl_enc.pack(anchor="w")

        row_enc = tk.Frame(enc_sec, bg=app._palette["panel"])
        row_enc.pack(fill="x", pady=(2, 8))

        def mk_radio(val: str, label: str):
            r = tk.Radiobutton(
                row_enc,
                text=label,
                variable=self._enc_mode,
                value=val,
                font=app._mono(),
                bg=app._palette["panel"],
                fg=app._palette["text"],
                selectcolor=app._palette["panel2"],
                activebackground=app._palette["panel"],
                activeforeground=app._palette["text"],
                highlightthickness=0,
                bd=0,
            )
            r.pack(side="left", padx=(0, 10))

        mk_radio("cpu", "CPU (libx264)")
        mk_radio("gpu", "NVIDIA GPU (NVENC)")

        # Quality
        lbl_qual = tk.Label(
            enc_sec,
            text="Quality (0-51, Lower is Better)",
            font=app._mono(weight="bold"),
            bg=app._palette["panel"],
            fg=app._palette["text"],
        )
        lbl_qual.pack(anchor="w")

        row_qual = tk.Frame(enc_sec, bg=app._palette["panel"])
        row_qual.pack(fill="x", pady=(2, 0))

        ent_qual = tk.Entry(
            row_qual,
            textvariable=self._enc_quality,
            font=app._mono(),
            bg=app._palette["panel2"],
            fg=app._palette["text"],
            insertbackground=app._ui_colors["accent_line"],
            relief="flat",
            highlightthickness=2,
            highlightbackground=app._palette["edge2"],
            highlightcolor=app._ui_colors["accent_line"],
            width=6,
        )
        ent_qual.pack(side="left")

        tk.Label(
            row_qual,
            text="Rec: 16-18 (High), 0 (Lossless)",
            font=app._mono(),
            bg=app._palette["panel"],
            fg=app._palette["muted"],
        ).pack(side="left", padx=10)

        # Helper: checkbox row bound to an existing BooleanVar
        def mk_chk_row(sec: tk.Frame, label: str, var: tk.BooleanVar) -> None:
            row = tk.Frame(sec, bg=app._palette["panel"])
            row.pack(fill="x", pady=4)
            tk.Checkbutton(
                row,
                text=label,
                variable=var,
                font=app._mono(),
                bg=app._palette["panel"],
                fg=app._palette["text"],
                activebackground=app._palette["panel"],
                activeforeground=app._palette["text"],
                selectcolor=app._palette["panel2"],
                highlightthickness=0,
                bd=0,
            ).pack(side="left")

        # CPU encoder settings
        mk_kv_row(enc_sec, "CPU codec", self._enc_str_vars["video_codec"], width=14)
        mk_kv_row(enc_sec, "CPU preset", self._enc_str_vars["video_preset"], width=14)

        # NVENC (GPU) settings
        mk_kv_row(enc_sec, "NVENC codec", self._enc_str_vars["nvenc_codec"], width=14)
        mk_kv_row(enc_sec, "NVENC preset", self._enc_str_vars["nvenc_preset"], width=14)
        mk_kv_row(enc_sec, "NVENC rate-control", self._enc_str_vars["nvenc_rc"], width=14)
        mk_chk_row(enc_sec, "CUDA decode enabled", self._enc_bool_vars["cuda_decode_enabled"])
        mk_chk_row(enc_sec, "Require CUDA support", self._enc_bool_vars["cuda_require_support"])

        # Audio
        mk_kv_row(enc_sec, "Audio codec", self._enc_str_vars["audio_codec"], width=14)
        mk_kv_row(enc_sec, "Audio bitrate", self._enc_str_vars["audio_bitrate"], width=14)

        # Rendering / chunking
        mk_chk_row(enc_sec, "Chunk parallel enabled", self._enc_bool_vars["chunk_parallel_enabled"])
        mk_kv_row(enc_sec, "Chunk size (frames)", self._enc_str_vars["chunk_size"], width=10)
        mk_chk_row(enc_sec, "Two-phase render", self._enc_bool_vars["two_phase_render_enabled"])
        mk_kv_row(enc_sec, "Keyframe snap tolerance (s)", self._enc_str_vars["keyframe_snap_tolerance_s"], width=10)
        mk_kv_row(enc_sec, "Cut fade (ms)", self._enc_str_vars["cut_fade_ms"], width=10)

        note = tk.Label(
            self._pipe_container,
            text=(
                "Settings save to QUALITY_PRESETS, PIPELINE_CONFIG, and WORDS_TO_REMOVE in config.py.\n"
                "Words to remove should be comma-separated. Restart GUI to apply full pipeline changes."
            ),
            font=app._mono(),
            bg=app._palette["panel"],
            fg=app._palette["muted"],
            justify="left",
        )
        note.pack(anchor="w", pady=(14, 0))

    # Modified by gpt-5.4 | 2026-03-15
    def _reload(self) -> None:
        try:
            gui_dict, pipe_cfg, qual_presets, words_cfg = ConfigEditor.load_gui_pipeline_quality_words(self._config_path)
        except Exception as e:
            messagebox.showerror("Config load failed", str(e))
            return

        for k, v in self._vars.items():
            v.set(str(gui_dict.get(k, "")))
        self._render_pipeline_toggles(pipe_cfg, qual_presets, words_cfg)
        self._app.set_status("Settings loaded")

    # Modified by gpt-5.4 | 2026-03-15
    def _save(self) -> None:
        def to_int(key: str) -> int:
            raw = self._vars[key].get().strip()
            if raw == "":
                raise ValueError(f"{key} is required")
            try:
                return int(raw)
            except ValueError:
                raise ValueError(f"{key} must be an integer")

        def to_color(key: str) -> str:
            raw = self._vars[key].get().strip()
            if raw == "":
                raise ValueError(f"{key} is required")
            return raw

        def to_float_word(key: str, label: str) -> float:
            raw = self._word_vars[key].get().strip()
            if raw == "":
                raise ValueError(f"{label} is required")
            try:
                return float(raw)
            except ValueError:
                raise ValueError(f"{label} must be a number")

        def to_int_word(key: str, label: str) -> int:
            raw = self._word_vars[key].get().strip()
            if raw == "":
                raise ValueError(f"{label} is required")
            try:
                return int(raw)
            except ValueError:
                raise ValueError(f"{label} must be an integer")

        try:
            gui_update = {
                "gui_width": to_int("gui_width"),
                "gui_height": to_int("gui_height"),
                "font_family": self._vars["font_family"].get().strip() or "Segoe UI",
                "font_title_size": to_int("font_title_size"),
                "font_section_size": to_int("font_section_size"),
                "font_body_size": to_int("font_body_size"),
                "font_mono_family": self._vars["font_mono_family"].get().strip() or "Cascadia Mono",
                "font_mono_size": to_int("font_mono_size"),
                "button_height": to_int("button_height"),
                "default_video_player": self._vars["default_video_player"].get().strip(),
                "ui_button_caption_color": to_color("ui_button_caption_color"),
                "ui_accent_font_color": to_color("ui_accent_font_color"),
                "ui_accent_line_color": to_color("ui_accent_line_color"),
                # Pane split weights (integers; don't need to sum to 100)
                "pane_console_width_pct": to_int("pane_console_width_pct"),
                "pane_filler_words_found_pct": to_int("pane_filler_words_found_pct"),
            }

            _, pipe_cfg, qual_presets, words_cfg = ConfigEditor.load_gui_pipeline_quality_words(self._config_path)

            # Update Pipeline Config
            for k, var in self._pipe_vars.items():
                group, idx_s = k.split(":", 1)
                idx = int(idx_s)
                pipe_cfg[group][idx]["enabled"] = bool(var.get())
            pipe_cfg.pop("detectors", None)

            # Update Quality Presets (Encode Settings)
            preset = qual_presets.get("PODCAST_HIGH_QUALITY")
            if not preset:
                # Should not happen typically
                raise ValueError("PODCAST_HIGH_QUALITY preset missing in config.py")

            def to_int_s(var: tk.StringVar, label: str) -> int:
                raw = var.get().strip()
                if raw == "":
                    raise ValueError(f"{label} is required")
                try:
                    return int(raw)
                except ValueError:
                    raise ValueError(f"{label} must be an integer")

            def to_float_s(var: tk.StringVar, label: str) -> float:
                raw = var.get().strip()
                if raw == "":
                    raise ValueError(f"{label} is required")
                try:
                    return float(raw)
                except ValueError:
                    raise ValueError(f"{label} must be a number")

            # Update Quality Preset (analysis + normalization)
            preset["silence_threshold_db"] = to_int_s(
                self._qual_vars["silence_threshold_db"], "Silence threshold (dB)"
            )
            preset["max_pause_duration"] = to_float_s(
                self._qual_vars["max_pause_duration"], "Max pause duration (sec)"
            )
            preset["new_pause_duration"] = to_float_s(
                self._qual_vars["new_pause_duration"], "New pause duration (sec)"
            )
            preset["silence_window_ms"] = to_int_s(self._qual_vars["silence_window_ms"], "Silence window (ms)")
            preset["spike_threshold_db"] = to_int_s(self._qual_vars["spike_threshold_db"], "Spike threshold (dB)")

            preset["normalization"] = {
                "target_lufs": to_float_s(self._qual_vars["normalization_standard_target"], "Standard target (LUFS)"),
                "max_gain_db": to_float_s(self._qual_vars["normalization_max_gain_db"], "Max gain (dB)"),
            }

            is_gpu = self._enc_mode.get() == "gpu"
            qual_val = int(self._enc_quality.get().strip())

            preset["cuda_encode_enabled"] = is_gpu
            preset["crf"] = qual_val

            # Ensure nvenc block exists
            if "nvenc" not in preset or not isinstance(preset["nvenc"], dict):
                preset["nvenc"] = {"codec": "h264_nvenc", "preset": "p4", "rc": "vbr"}

            preset["nvenc"]["cq"] = qual_val

            # Extended encoder / rendering fields
            preset["cuda_decode_enabled"] = self._enc_bool_vars["cuda_decode_enabled"].get()
            preset["cuda_require_support"] = self._enc_bool_vars["cuda_require_support"].get()
            preset["video_codec"] = self._enc_str_vars["video_codec"].get().strip()
            preset["video_preset"] = self._enc_str_vars["video_preset"].get().strip()
            preset["audio_codec"] = self._enc_str_vars["audio_codec"].get().strip()
            preset["audio_bitrate"] = self._enc_str_vars["audio_bitrate"].get().strip()
            preset["nvenc"]["codec"] = self._enc_str_vars["nvenc_codec"].get().strip()
            preset["nvenc"]["preset"] = self._enc_str_vars["nvenc_preset"].get().strip()
            preset["nvenc"]["rc"] = self._enc_str_vars["nvenc_rc"].get().strip()
            preset["chunk_parallel_enabled"] = self._enc_bool_vars["chunk_parallel_enabled"].get()
            try:
                preset["chunk_size"] = int(self._enc_str_vars["chunk_size"].get().strip())
            except ValueError:
                raise ValueError("Chunk size must be an integer")
            preset["two_phase_render_enabled"] = self._enc_bool_vars["two_phase_render_enabled"].get()
            try:
                preset["keyframe_snap_tolerance_s"] = float(
                    self._enc_str_vars["keyframe_snap_tolerance_s"].get().strip()
                )
            except ValueError:
                raise ValueError("Keyframe snap tolerance must be a number")
            try:
                preset["cut_fade_ms"] = int(self._enc_str_vars["cut_fade_ms"].get().strip())
            except ValueError:
                raise ValueError("Cut fade (ms) must be an integer")

            words_raw = self._word_vars["words_to_remove"].get().strip()
            words_cfg["words_to_remove"] = [
                word.strip() for word in words_raw.split(",") if word.strip()
            ]
            words_cfg["confidence_required"] = to_float_word("confidence_required", "Confidence required")
            words_cfg["confidence_bonus_per_word"] = to_float_word(
                "confidence_bonus_per_word", "Confidence bonus per word"
            )
            words_cfg["filler_mute_inset_ms"] = to_int_word(
                "filler_mute_inset_ms", "Mute inset (ms)"
            )
            words_cfg["filler_mute_gap_threshold_ms"] = to_int_word(
                "filler_mute_gap_threshold_ms", "Mute gap threshold (ms)"
            )

            ConfigEditor.write_gui_and_pipeline(
                self._config_path,
                gui_update,
                pipe_cfg,
                qual_presets,
                words_cfg,
            )
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            return

        self._app.set_status("Saved to config.py")
        messagebox.showinfo("Saved", "config.py updated. Restart GUI to apply all typography/layout/color changes.")

