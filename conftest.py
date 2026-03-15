# conftest.py
# Ensure the project root is always on sys.path when pytest runs.
# Without this, packages like io_, core, processors, utils, etc. cannot be
# resolved by test modules — pytest does not auto-insert the rootdir for
# projects without a setup.py / pyproject.toml installed in editable mode.

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))


# Silence the processing-complete chime for every test automatically.
# The alert is a GUI side effect; tests that exercise run_processing() should
# not trigger audio any more than they trigger real subprocesses or real file I/O.
# This is the same pattern as monkeypatching subprocess.Popen etc. in those tests —
# but done session-wide so no individual test has to remember to do it.
@pytest.fixture(autouse=True)
def _silence_processing_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    # Created by anthropic/claude-sonnet-4.6 | 2026-03-14
    monkeypatch.setattr(
        "utils.processing_alert.processing_complete_alert_play",
        lambda: None,
    )
