# Contributing to JobPilot

Thanks for considering a contribution. A few guidelines to keep this
useful and safe for everyone running it against their own accounts.

## Setup

```bash
pip install -e ".[dev]"
pytest
```

## Adding a job connector

Implement `jobpilot/connectors/base.py`'s `JobConnector` interface - just
`search(keywords, country, limit)`. Prefer official APIs or public,
robots.txt-permitted pages (like the Bayt connector) over anything that
requires logging into a site whose Terms of Service restrict automation -
see "What we won't merge" below.

## Adding an AI provider

`jobpilot/core/llm.py` dispatches on `RuntimeSettings.llm_provider`. To add
one: write a `_yourprovider_generate(settings, system, user, max_tokens,
json_mode) -> str` function, register it in the `_PROVIDERS` dict, and add
the matching fields (`yourprovider_api_key`, `yourprovider_model`) to
`RuntimeSettings` in `jobpilot/core/settings_store.py` plus a radio option
in `jobpilot/web/templates/settings.html`.

## What we won't merge

- CAPTCHA-solving or anti-bot-detection evasion of any kind.
- Automating a login-gated flow (LinkedIn/Indeed-style "Easy Apply", etc.)
  on a site whose Terms of Service prohibit it. JobPilot's apply step is
  intentionally email-only for this reason.
- Anything that scrapes or applies at a volume/speed clearly meant to
  evade a platform's own rate limits, rather than working within the
  `BatchRateLimiter` pattern already in `core/rate_limiter.py`.
- Real personal data (resumes, emails, API keys) committed anywhere in the
  repo, including in tests or examples. All of that belongs in the local,
  gitignored database via the Settings page - never in source.

## Tests

New agents/connectors should ship with unit tests that don't hit the
network - see `tests/test_bayt_connector.py` for the pattern of testing
the parser against a saved HTML fixture instead of a live request.
