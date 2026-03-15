import tkinter as tk
from pathlib import Path

from ui.gui_settings_page import SettingsPage


class _PanelStub:
    def __init__(self, master: tk.Widget, bg: str) -> None:
        self.frame = tk.Frame(master, bg=bg)
        self.body = tk.Frame(self.frame, bg=bg)
        self.body.pack(fill="both", expand=True)

    def grid(self, *args, **kwargs) -> None:
        self.frame.grid(*args, **kwargs)


class _AppStub:
    def __init__(self, root: tk.Tk, project_dir: Path) -> None:
        self._project_dir = project_dir
        self._palette = {
            "bg": "#101010",
            "panel": "#202020",
            "panel2": "#303030",
            "text": "#ffffff",
            "muted": "#aaaaaa",
            "edge2": "#404040",
        }
        self._ui_colors = {"accent_line": "#39FF14"}
        self.statuses: list[str] = []
        self.root = root

    def _mono(self, weight: str | None = None):
        return ("Cascadia Mono", 9, weight or "normal")

    def _make_btn(self, parent: tk.Widget, text: str, command, kind: str = "secondary") -> tk.Button:
        return tk.Button(parent, text=text, command=command)

    def _make_panel(self, parent: tk.Widget, title: str) -> _PanelStub:
        return _PanelStub(parent, self._palette["panel"])

    def set_status(self, text: str) -> None:
        self.statuses.append(text)


def test_settings_page_reload_loads_filler_word_mute_fields(monkeypatch, tmp_path):
    config_data = (
        {},
        {"processors": []},
        {"PODCAST_HIGH_QUALITY": {}},
        {
            "words_to_remove": ["uh", "um"],
            "confidence_required_host": 1.0,
            "confidence_required_guest": 0.92,
            "filler_mute_inset_ms": 35,
            "filler_mute_gap_threshold_ms": 75,
        },
    )
    monkeypatch.setattr(
        "ui.gui_settings_page.ConfigEditor.load_gui_pipeline_quality_words",
        lambda _path: config_data,
    )

    root = tk.Tk()
    root.withdraw()
    try:
        page = SettingsPage(root, _AppStub(root, tmp_path))

        assert page._word_vars["filler_mute_inset_ms"].get() == "35"
        assert page._word_vars["filler_mute_gap_threshold_ms"].get() == "75"
    finally:
        root.destroy()


def test_settings_page_save_writes_filler_word_mute_fields(monkeypatch, tmp_path):
    writes: list[dict] = []
    config_data = (
        {
            "gui_width": 1000,
            "gui_height": 700,
            "font_family": "Segoe UI",
            "font_title_size": 18,
            "font_section_size": 11,
            "font_body_size": 10,
            "font_mono_family": "Cascadia Mono",
            "font_mono_size": 9,
            "button_height": 10,
            "default_video_player": "",
            "ui_button_caption_color": "#39FF14",
            "ui_accent_font_color": "#39FF14",
            "ui_accent_line_color": "#39FF14",
        },
        {"processors": []},
        {"PODCAST_HIGH_QUALITY": {"nvenc": {}, "normalization": {}}},
        {
            "words_to_remove": ["uh"],
            "confidence_required_host": 1.0,
            "confidence_required_guest": 0.92,
            "filler_mute_inset_ms": 30,
            "filler_mute_gap_threshold_ms": 60,
        },
    )
    monkeypatch.setattr(
        "ui.gui_settings_page.ConfigEditor.load_gui_pipeline_quality_words",
        lambda _path: config_data,
    )
    monkeypatch.setattr("ui.gui_settings_page.messagebox.showinfo", lambda *args: None)
    monkeypatch.setattr("ui.gui_settings_page.messagebox.showerror", lambda *args: None)

    def _capture_write(_config_path, _gui_update, _pipe_cfg, _qual_presets, words_cfg):
        writes.append(words_cfg.copy())

    monkeypatch.setattr("ui.gui_settings_page.ConfigEditor.write_gui_and_pipeline", _capture_write)

    root = tk.Tk()
    root.withdraw()
    try:
        page = SettingsPage(root, _AppStub(root, tmp_path))
        page._word_vars["filler_mute_inset_ms"].set("45")
        page._word_vars["filler_mute_gap_threshold_ms"].set("95")

        page._save()

        assert writes[-1]["filler_mute_inset_ms"] == 45
        assert writes[-1]["filler_mute_gap_threshold_ms"] == 95
    finally:
        root.destroy()
