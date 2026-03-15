"""Tests for FILES-area grid spacing and color helpers."""

import sys
from pathlib import Path
from types import SimpleNamespace

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.gui_output_rows import _file_grid_padding_get, file_grid_line_color_get


# Created by gpt-5.4 | 2026-03-08
def test_file_grid_padding_adds_outer_left_and_top_border_once():
    assert _file_grid_padding_get(0, 0) == ((1, 1), (1, 1))


# Created by gpt-5.4 | 2026-03-08
def test_file_grid_padding_uses_single_pixel_internal_separators():
    assert _file_grid_padding_get(0, 2) == ((0, 1), (1, 1))
    assert _file_grid_padding_get(2, 1) == ((0, 1), (0, 1))


# Created by gpt-5.4 | 2026-03-08
def test_file_grid_line_color_is_softened_when_pane_outline_is_one_pixel():
    app = SimpleNamespace(
        _ui_colors={"accent_line": "#39FF14"},
        _palette={"panel": "#12161B"},
        _panel_outline_thickness=1,
    )

    assert file_grid_line_color_get(app) == "#2EBE16"


# Created by gpt-5.4 | 2026-03-08
def test_file_grid_line_color_stays_full_strength_when_pane_outline_is_thicker():
    app = SimpleNamespace(
        _ui_colors={"accent_line": "#39FF14"},
        _palette={"panel": "#12161B"},
        _panel_outline_thickness=2,
    )

    assert file_grid_line_color_get(app) == "#39FF14"
