"""Test GUI subprocess command construction for processing runs."""

import sys
from pathlib import Path
from types import SimpleNamespace

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.gui_app import AVCleanerGUI


class _FakeStdout:
    # Modified by gpt-5.4 | 2026-03-07
    def __init__(self, lines=None):
        self._lines = lines or ()

    # Modified by gpt-5.4 | 2026-03-07
    def __iter__(self):
        return iter(self._lines)


class _FakeProcess:
    # Modified by gpt-5.4 | 2026-03-07
    def __init__(self, cmd, *, lines=None):
        self.cmd = cmd
        self.stdout = _FakeStdout(lines)

    def poll(self):
        return 0

    def wait(self):
        return 0


class _FakeThread:
    def __init__(self, *, target, daemon):
        self._target = target
        self.daemon = daemon

    def start(self):
        self._target()


def _make_app(tmp_path):
    app = object.__new__(AVCleanerGUI)
    app._proc = None
    app._project_dir = tmp_path
    app._pages = {}
    app.after = lambda _delay, callback, *args: callback(*args)
    app._set_row_for_path = lambda *_args: None
    app._set_modded_row_for_path = lambda *_args: None
    app._clear_modded_rows = lambda: None
    # Processing-control state added by 2026-03-11 pause/stop feature
    app._proc_paused = False
    app._proc_stop_requested = False
    app._proc_process_btn = None
    app._proc_pause_btn = None
    app._proc_stop_btn = None
    return app


# Modified by gpt-5.4 | 2026-03-07
def test_run_processing_uses_process_subcommand(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        return _FakeProcess(cmd)

    monkeypatch.setattr("ui.gui_app.subprocess.Popen", _fake_popen)
    monkeypatch.setattr("ui.gui_app.threading.Thread", _FakeThread)
    monkeypatch.setattr("ui.gui_app.ConfigEditor.load_gui_and_pipeline", lambda _path: ({}, {}, {}))

    app = _make_app(tmp_path)
    app.clear_logs = lambda: None
    app.clear_progress = lambda: None
    app.set_status = lambda _status: None
    app.append_log = lambda _line: None
    app.append_progress = lambda _line: None

    app.run_processing("host.mp4", "guest.mp4")

    cmd = captured["cmd"]
    assert cmd[0] == sys.executable
    assert cmd[1] == "main.py"
    assert cmd[2] == "process"
    assert "--host" in cmd
    assert "host.mp4" in cmd
    assert "--guest" in cmd
    assert "guest.mp4" in cmd
    assert "--action" not in cmd
    assert captured["cwd"] == str(tmp_path)


# Created by gpt-5.4 | 2026-03-07
def test_run_processing_updates_modded_rows_from_result_line(monkeypatch, tmp_path):
    captured_updates: list[tuple[str, str]] = []

    result_lines = [
        "[RESULT] host=C:\\Videos\\host_processed.mp4 guest=C:\\Videos\\guest_processed.mp4\n",
    ]

    def _fake_popen(cmd, **kwargs):
        return _FakeProcess(cmd, lines=result_lines)

    monkeypatch.setattr("ui.gui_app.subprocess.Popen", _fake_popen)
    monkeypatch.setattr("ui.gui_app.threading.Thread", _FakeThread)
    monkeypatch.setattr("ui.gui_app.os.path.exists", lambda _path: True)
    monkeypatch.setattr("ui.gui_app.ConfigEditor.load_gui_and_pipeline", lambda _path: ({}, {}, {}))

    app = _make_app(tmp_path)
    app.clear_logs = lambda: None
    app.clear_progress = lambda: None
    app.set_status = lambda _status: None
    app.append_log = lambda _line: None
    app.append_progress = lambda _line: None
    app._set_modded_row_for_path = lambda role, path: captured_updates.append((role, path))

    app.run_processing("host.mp4", "guest.mp4")

    assert captured_updates == [
        ("host", "C:\\Videos\\host_processed.mp4"),
        ("guest", "C:\\Videos\\guest_processed.mp4"),
    ]


def test_run_processing_reloads_config_before_start(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProcess(cmd)

    reloaded_gui = {"default_video_player": "D:/Apps/VLC/vlc.exe"}

    monkeypatch.setattr("ui.gui_app.subprocess.Popen", _fake_popen)
    monkeypatch.setattr("ui.gui_app.threading.Thread", _FakeThread)
    monkeypatch.setattr("ui.gui_app.ConfigEditor.load_gui_and_pipeline", lambda _path: (reloaded_gui, {}, {}))

    app = _make_app(tmp_path)
    app.clear_logs = lambda: None
    app.clear_progress = lambda: None
    app.set_status = lambda _status: None
    app.append_log = lambda _line: None
    app.append_progress = lambda _line: None

    original_player = AVCleanerGUI.__module__
    # Use the imported GUI dict object from ui.gui_app directly.
    from ui.gui_app import GUI

    old_gui = dict(GUI)
    try:
        GUI.clear()
        GUI.update({"default_video_player": "C:/Old/player.exe"})

        app.run_processing("host.mp4", "guest.mp4")

        assert captured["cmd"][2] == "process"
        assert GUI["default_video_player"] == reloaded_gui["default_video_player"]
    finally:
        GUI.clear()
        GUI.update(old_gui)


def test_run_processing_stops_when_config_reload_fails(monkeypatch, tmp_path):
    statuses: list[str] = []
    log_lines: list[str] = []
    popen_called = {"value": False}

    def _fake_popen(cmd, **kwargs):
        popen_called["value"] = True
        return _FakeProcess(cmd)

    monkeypatch.setattr("ui.gui_app.subprocess.Popen", _fake_popen)
    monkeypatch.setattr("ui.gui_app.threading.Thread", _FakeThread)
    monkeypatch.setattr(
        "ui.gui_app.ConfigEditor.load_gui_and_pipeline",
        lambda _path: (_ for _ in ()).throw(ValueError("bad config")),
    )
    messagebox_calls: list[tuple[str, str]] = []
    monkeypatch.setattr("ui.gui_app.messagebox.showerror", lambda title, msg: messagebox_calls.append((title, msg)))

    app = _make_app(tmp_path)
    app.clear_logs = lambda: None
    app.clear_progress = lambda: None
    app.set_status = lambda status: statuses.append(status)
    app.append_log = lambda line: log_lines.append(line)
    app.append_progress = lambda _line: None

    app.run_processing("host.mp4", "guest.mp4")

    assert popen_called["value"] is False
    assert statuses[-1] == "Config reload failed"
    assert any("Failed to reload config.py" in line for line in log_lines)
    assert messagebox_calls == [("Config load failed", "bad config")]


# Created by gpt-5.4 | 2026-03-08
def test_restart_app_relaunches_gui_and_closes_current_window(monkeypatch, tmp_path):
    captured: dict[str, object] = {}
    log_lines: list[str] = []
    destroyed = {"value": False}

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        return _FakeProcess(cmd)

    monkeypatch.setattr("ui.gui_app.subprocess.Popen", _fake_popen)

    app = _make_app(tmp_path)
    app.append_log = lambda line: log_lines.append(line)
    app.set_status = lambda _status: None
    app.destroy = lambda: destroyed.__setitem__("value", True)

    app._restart_app()

    assert captured["cmd"] == [sys.executable, "app.py"]
    assert captured["cwd"] == str(tmp_path)
    assert destroyed["value"] is True
    assert log_lines == ["[GUI] Restarting app...\n"]


# Created by gpt-5.4 | 2026-03-08
def test_restart_app_shows_error_when_relaunch_fails(monkeypatch, tmp_path):
    statuses: list[str] = []
    messagebox_calls: list[tuple[str, str]] = []
    destroyed = {"value": False}

    def _fake_popen(cmd, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr("ui.gui_app.subprocess.Popen", _fake_popen)
    monkeypatch.setattr("ui.gui_app.messagebox.showerror", lambda title, msg: messagebox_calls.append((title, msg)))

    app = _make_app(tmp_path)
    app.append_log = lambda _line: None
    app.set_status = lambda status: statuses.append(status)
    app.destroy = lambda: destroyed.__setitem__("value", True)

    app._restart_app()

    assert statuses == ["Restart failed"]
    assert destroyed["value"] is False
    assert messagebox_calls == [("Restart failed", "Could not restart app.\n\nboom")]
