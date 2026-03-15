from __future__ import annotations


from click.testing import CliRunner


def test_main_preflights_normalize_lengths_for_guest_only_action(monkeypatch):
    import main as main_module

    calls: dict[str, object] = {}

    def fake_normalize_video_lengths(host: str, guest: str) -> tuple[str, str]:
        calls["normalized"] = (host, guest)
        return "H_norm.mp4", "G_norm.mp4"

    class _FakePipeline:
        def execute(self, host: str, guest: str, **kwargs):
            calls["execute"] = (host, guest, kwargs)
            return "host_out.mp4", "guest_out.mp4"

    def fake_build_pipeline(config: dict):
        calls["build_pipeline"] = True
        return _FakePipeline()

    monkeypatch.setattr(main_module, "normalize_video_lengths", fake_normalize_video_lengths)
    monkeypatch.setattr(main_module, "_build_pipeline", fake_build_pipeline)

    runner = CliRunner()
    result = runner.invoke(
        main_module.main,
        [
            "--host",
            "H.mp4",
            "--guest",
            "G.mp4",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls["normalized"] == ("H.mp4", "G.mp4")

    host, guest, kwargs = calls["execute"]
    assert (host, guest) == ("H_norm.mp4", "G_norm.mp4")
    assert kwargs == {}


def test_main_preflights_normalize_lengths_for_all_action(monkeypatch):
    import main as main_module

    calls: dict[str, object] = {}

    def fake_normalize_video_lengths(host: str, guest: str) -> tuple[str, str]:
        return "H_norm.mp4", "G_norm.mp4"

    class _FakePipeline:
        def execute(self, host: str, guest: str, **kwargs):
            calls["execute"] = (host, guest, kwargs)
            return "host_out.mp4", "guest_out.mp4"

    def fake_build_pipeline(config: dict):
        return _FakePipeline()

    monkeypatch.setattr(main_module, "normalize_video_lengths", fake_normalize_video_lengths)
    monkeypatch.setattr(main_module, "_build_pipeline", fake_build_pipeline)

    runner = CliRunner()
    result = runner.invoke(
        main_module.main,
        [
            "--host",
            "H.mp4",
            "--guest",
            "G.mp4",
        ],
    )
    assert result.exit_code == 0, result.output

    host, guest, kwargs = calls["execute"]
    assert (host, guest) == ("H_norm.mp4", "G_norm.mp4")
    assert kwargs == {}
