import json
from typing import Any

from anthropic import Anthropic

from jobpilot.config import settings

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def ask_json(system: str, user: str, max_tokens: int = 1500) -> dict[str, Any]:
    """Send a prompt that must return a single JSON object, and parse it.

    Instructs the model to respond with JSON only, and raises a clear error
    if it doesn't - callers should treat this as retryable.
    """
    client = get_client()
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=system + "\n\nRespond with a single valid JSON object and nothing else.",
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {text[:500]}") from exc


def ask_text(system: str, user: str, max_tokens: int = 1500) -> str:
    client = get_client()
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()
