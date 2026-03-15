import sys
import os
import pytest

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_click_import():
    try:
        import click
    except ImportError:
        pytest.fail("Could not import click")

def test_main_import():
    try:
        import main
    except ImportError as e:
        pytest.fail(f"Could not import main: {e}")
