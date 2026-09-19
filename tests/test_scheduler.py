from unittest.mock import patch

from jobpilot.core.settings_store import RuntimeSettings
from jobpilot.web import app as web_app


def test_auto_run_defaults_to_disabled():
    settings = RuntimeSettings()
    assert settings.auto_run_enabled is False
    assert settings.auto_run_interval_hours == 24


def test_trigger_stage_starts_a_known_stage():
    web_app._last_run.clear()
    web_app._running.clear()
    with patch.object(web_app, "_stage_functions", return_value={"search": lambda progress=None: 0}):
        with patch("threading.Thread") as mock_thread:
            started = web_app._trigger_stage("search")

    assert started is True
    assert "search" in web_app._running
    mock_thread.assert_called_once()


def test_trigger_stage_refuses_unknown_stage():
    web_app._last_run.clear()
    web_app._running.clear()
    with patch.object(web_app, "_stage_functions", return_value={"search": lambda progress=None: 0}):
        started = web_app._trigger_stage("not-a-real-stage")

    assert started is False
    assert web_app._running == set()


def test_trigger_stage_refuses_when_already_running():
    web_app._last_run.clear()
    web_app._running.clear()
    web_app._running.add("search")
    with patch.object(web_app, "_stage_functions", return_value={"search": lambda progress=None: 0}):
        with patch("threading.Thread") as mock_thread:
            started = web_app._trigger_stage("search")

    assert started is False
    mock_thread.assert_not_called()
    web_app._running.clear()
