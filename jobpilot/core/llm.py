"""Talks to whichever AI provider the user picked on the Settings page.

Three providers are supported: Anthropic (Claude), Google (Gemini, via the
`google-genai` SDK - the current one as of the Gemini 3 generation; the
older `google-generativeai` package is deprecated), and Ollama (any model
running locally - no API key needed, useful as a fallback if neither
hosted provider is available). Adding another provider means adding one
`_x_generate()` function below, registering it in `_PROVIDERS`, and adding
its settings fields - the rest of the app only calls `ask_json` / `ask_text`.
"""

import json
import logging
import time
from typing import Any

from jobpilot.core.settings_store import RuntimeSettings, get_settings

logger = logging.getLogger(__name__)

# Free-tier API keys (Google's in particular, at 5 requests/minute) run out
# of quota fast once you're scoring dozens of jobs back to back. Rather than
# assume a fixed pace that would needlessly throttle a paid key, retry with
# backoff only when a call actually hits a rate limit.
_RATE_LIMIT_MARKERS = ("429", "RESOURCE_EXHAUSTED", "rate_limit", "overloaded")
_RETRY_DELAYS_SECONDS = (15, 30, 60)


def _anthropic_generate(settings: RuntimeSettings, system: str, user: str, max_tokens: int, json_mode: bool) -> str:
    from anthropic import Anthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("No Anthropic API key configured - set one on the Settings page.")

    client = Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = system
    if json_mode:
        system_prompt += "\n\nRespond with a single valid JSON object and nothing else."
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


def _google_generate(settings: RuntimeSettings, system: str, user: str, max_tokens: int, json_mode: bool) -> str:
    from google import genai
    from google.genai import types

    if not settings.google_api_key:
        raise RuntimeError("No Google API key configured - set one on the Settings page.")

    client = genai.Client(api_key=settings.google_api_key)
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    response = client.models.generate_content(model=settings.google_model, contents=user, config=config)
    return (response.text or "").strip()


def _ollama_generate(settings: RuntimeSettings, system: str, user: str, max_tokens: int, json_mode: bool) -> str:
    from ollama import Client

    if not settings.ollama_model:
        raise RuntimeError("No Ollama model configured - set one on the Settings page.")

    client = Client(host=settings.ollama_base_url)
    response = client.chat(
        model=settings.ollama_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        format="json" if json_mode else None,
        options={"num_predict": max_tokens},
    )
    return response["message"]["content"].strip()


_PROVIDERS = {
    "anthropic": _anthropic_generate,
    "google": _google_generate,
    "ollama": _ollama_generate,
}


def _call_with_retry(provider: str, settings: RuntimeSettings, system: str, user: str, max_tokens: int, json_mode: bool) -> str:
    generate_fn = _PROVIDERS.get(provider)
    if generate_fn is None:
        raise RuntimeError(f"Unknown llm_provider '{provider}' - expected one of {list(_PROVIDERS)}.")

    for attempt, delay in enumerate((0, *_RETRY_DELAYS_SECONDS)):
        if delay:
            logger.warning("Rate-limited by %s, retrying in %ds", provider, delay)
            time.sleep(delay)
        try:
            return generate_fn(settings, system, user, max_tokens, json_mode)
        except Exception as exc:
            is_rate_limit = any(marker in str(exc) for marker in _RATE_LIMIT_MARKERS)
            if not is_rate_limit or attempt == len(_RETRY_DELAYS_SECONDS):
                raise
    raise AssertionError("unreachable")  # pragma: no cover


def _generate(system: str, user: str, max_tokens: int, json_mode: bool) -> str:
    settings = get_settings()
    provider = settings.llm_provider
    try:
        return _call_with_retry(provider, settings, system, user, max_tokens, json_mode)
    except Exception as exc:
        # A local Ollama model, if the user has one configured, is a
        # reasonable fallback for a hosted provider that's out of quota or
        # unreachable - it has no rate limit and needs no network access.
        if provider != "ollama" and settings.ollama_model:
            logger.warning("%s failed (%s) - falling back to local Ollama (%s)", provider, exc, settings.ollama_model)
            try:
                return _ollama_generate(settings, system, user, max_tokens, json_mode)
            except Exception:
                logger.exception("Ollama fallback also failed")
        raise


def ask_json(system: str, user: str, max_tokens: int = 1500) -> dict[str, Any]:
    """Send a prompt that must return a single JSON object, and parse it."""
    text = _generate(system, user, max_tokens, json_mode=True)
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {text[:500]}") from exc


def ask_text(system: str, user: str, max_tokens: int = 1500) -> str:
    return _generate(system, user, max_tokens, json_mode=False)
