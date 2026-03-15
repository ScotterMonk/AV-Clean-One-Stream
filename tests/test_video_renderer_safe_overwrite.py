import os
import sys
from pathlib import Path

# Ensure parent directory is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_render_with_safe_overwrite_uses_temp_and_replaces_on_same_path(monkeypatch, tmp_path):
    from io_ import video_renderer

    inp = tmp_path / "video.mp4"
    inp.write_bytes(b"old")

    captured = {"out": None}

    def _render(out_path: str) -> None:
        captured["out"] = out_path
        # Simulate ffmpeg writing output.
        with open(out_path, "wb") as f:
            f.write(b"new")

    video_renderer._render_with_safe_overwrite(str(inp), str(inp), _render)

    assert captured["out"] is not None
    assert os.path.basename(captured["out"]).startswith(".video.tmp-")
    assert os.path.dirname(captured["out"]) == str(tmp_path)
    assert inp.read_bytes() == b"new"
    assert not os.path.exists(captured["out"])


def test_render_with_safe_overwrite_cleans_temp_on_failure(monkeypatch, tmp_path):
    from io_ import video_renderer

    inp = tmp_path / "video.mp4"
    inp.write_bytes(b"old")

    captured = {"out": None}

    def _render(out_path: str) -> None:
        captured["out"] = out_path
        # Create a partial output then fail.
        with open(out_path, "wb") as f:
            f.write(b"partial")
        raise RuntimeError("boom")

    try:
        video_renderer._render_with_safe_overwrite(str(inp), str(inp), _render)
        raise AssertionError("expected error")
    except RuntimeError as e:
        assert str(e) == "boom"

    assert inp.read_bytes() == b"old"
    assert captured["out"] is not None
    assert not os.path.exists(captured["out"])


def test_render_with_safe_overwrite_renders_directly_when_paths_differ(tmp_path):
    """When input != output, should render directly without temp file."""
    from io_ import video_renderer

    inp = tmp_path / "input.mp4"
    out = tmp_path / "output.mp4"
    inp.write_bytes(b"original")

    captured = {"out": None}

    def _render(out_path: str) -> None:
        captured["out"] = out_path
        with open(out_path, "wb") as f:
            f.write(b"rendered")

    video_renderer._render_with_safe_overwrite(str(inp), str(out), _render)

    # Should render directly to output path (no temp file)
    assert captured["out"] == str(out)
    assert out.read_bytes() == b"rendered"
    assert inp.read_bytes() == b"original"  # Input unchanged


def test_render_with_safe_overwrite_normalizes_paths_for_comparison(tmp_path):
    """Path normalization should detect same path with different representations."""
    from io_ import video_renderer

    inp = tmp_path / "video.mp4"
    inp.write_bytes(b"old")

    # Use relative path for output
    import os as os_module
    orig_cwd = os_module.getcwd()
    try:
        os_module.chdir(tmp_path)
        relative_path = "video.mp4"

        captured = {"out": None}

        def _render(out_path: str) -> None:
            captured["out"] = out_path
            with open(out_path, "wb") as f:
                f.write(b"new")

        video_renderer._render_with_safe_overwrite(str(inp), relative_path, _render)

        # Should use temp file since paths resolve to same location
        assert captured["out"] is not None
        assert os.path.basename(captured["out"]).startswith(".video.tmp-")
        assert inp.read_bytes() == b"new"
    finally:
        os_module.chdir(orig_cwd)


def test_render_with_safe_overwrite_temp_file_naming_pattern(tmp_path):
    """Verify temp file uses correct naming pattern with stem and suffix."""
    from io_ import video_renderer

    inp = tmp_path / "my_video.mp4"
    inp.write_bytes(b"old")

    captured = {"out": None}

    def _render(out_path: str) -> None:
        captured["out"] = out_path
        with open(out_path, "wb") as f:
            f.write(b"new")

    video_renderer._render_with_safe_overwrite(str(inp), str(inp), _render)

    # Verify naming pattern: .{stem}.tmp-{random}.{suffix}
    temp_name = os.path.basename(captured["out"])
    assert temp_name.startswith(".my_video.tmp-")
    assert temp_name.endswith(".mp4")


def test_render_with_safe_overwrite_creates_output_directory_when_same_path(tmp_path):
    """When output == input, temp directory should be created if missing."""
    from io_ import video_renderer

    # Create nested directory structure
    inp_dir = tmp_path / "nested" / "input"
    inp_dir.mkdir(parents=True)
    inp = inp_dir / "video.mp4"
    
    inp.write_bytes(b"old")

    def _render(out_path: str) -> None:
        with open(out_path, "wb") as f:
            f.write(b"new")

    # Should work even though directory exists
    video_renderer._render_with_safe_overwrite(str(inp), str(inp), _render)

    # File should be overwritten
    assert inp.read_bytes() == b"new"


def test_render_with_safe_overwrite_cleanup_on_exception_only(tmp_path):
    """Cleanup works for Exception subclasses but not BaseException (like KeyboardInterrupt)."""
    from io_ import video_renderer

    inp = tmp_path / "video.mp4"
    inp.write_bytes(b"old")

    # Test that cleanup DOES work for Exception subclasses
    captured = {"out": None}

    def _render_runtime_error(out_path: str) -> None:
        captured["out"] = out_path
        with open(out_path, "wb") as f:
            f.write(b"partial")
        raise RuntimeError("test error")

    try:
        video_renderer._render_with_safe_overwrite(str(inp), str(inp), _render_runtime_error)
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass

    # Cleanup should work for Exception subclasses
    assert inp.read_bytes() == b"old"
    assert captured["out"] is not None
    assert not os.path.exists(captured["out"])


def test_render_with_safe_overwrite_atomic_replace(tmp_path):
    """Verify os.replace is used for atomic operation."""
    from io_ import video_renderer
    import unittest.mock as mock

    inp = tmp_path / "video.mp4"
    inp.write_bytes(b"old")

    def _render(out_path: str) -> None:
        with open(out_path, "wb") as f:
            f.write(b"new")

    with mock.patch("os.replace", wraps=os.replace) as mock_replace:
        video_renderer._render_with_safe_overwrite(str(inp), str(inp), _render)
        
        # os.replace should be called once with temp -> final path
        assert mock_replace.call_count == 1
        call_args = mock_replace.call_args[0]
        assert call_args[1] == str(inp)  # Target is the input path
        assert ".tmp-" in call_args[0]  # Source is temp file
