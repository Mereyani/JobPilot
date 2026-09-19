from unittest.mock import MagicMock, patch

import pytest

from jobpilot.core import llm
from jobpilot.core.settings_store import RuntimeSettings


def _settings(**overrides) -> RuntimeSettings:
    return RuntimeSettings(llm_provider="google", google_api_key="fake", ollama_model="llama3.2").model_copy(
        update=overrides
    )


def test_falls_back_to_ollama_when_primary_provider_fails():
    # The primary provider is looked up through _PROVIDERS (patch.dict), but
    # the fallback path calls _ollama_generate by name directly - it needs
    # its own patch target.
    fake_google = MagicMock(side_effect=RuntimeError("quota exceeded"))

    with patch("jobpilot.core.llm.get_settings", return_value=_settings()):
        with patch.dict(llm._PROVIDERS, {"google": fake_google}):
            with patch("jobpilot.core.llm._ollama_generate", return_value="fallback result") as fake_ollama:
                result = llm.ask_text("system", "user")

    assert result == "fallback result"
    fake_ollama.assert_called_once()


def test_no_fallback_when_ollama_not_configured():
    fake_google = MagicMock(side_effect=RuntimeError("quota exceeded"))

    with patch("jobpilot.core.llm.get_settings", return_value=_settings(ollama_model="")):
        with patch.dict(llm._PROVIDERS, {"google": fake_google}):
            with pytest.raises(RuntimeError, match="quota exceeded"):
                llm.ask_text("system", "user")


def test_ollama_as_primary_does_not_fall_back_to_itself():
    fake_ollama = MagicMock(side_effect=RuntimeError("ollama down"))

    with patch("jobpilot.core.llm.get_settings", return_value=_settings(llm_provider="ollama")):
        with patch.dict(llm._PROVIDERS, {"ollama": fake_ollama}):
            with pytest.raises(RuntimeError, match="ollama down"):
                llm.ask_text("system", "user")

    assert fake_ollama.call_count == 1


def test_non_rate_limit_error_is_not_retried_before_falling_back():
    fake_google = MagicMock(side_effect=RuntimeError("totally unrelated failure"))

    with patch("jobpilot.core.llm.get_settings", return_value=_settings()):
        with patch("jobpilot.core.llm.time.sleep") as mock_sleep:
            with patch.dict(llm._PROVIDERS, {"google": fake_google}):
                with patch("jobpilot.core.llm._ollama_generate", return_value="fallback result") as fake_ollama:
                    result = llm.ask_text("system", "user")

    assert result == "fallback result"
    fake_google.assert_called_once()  # no retries for a non-rate-limit error
    fake_ollama.assert_called_once()
    mock_sleep.assert_not_called()
