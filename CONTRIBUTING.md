# Contributing to JobPilot

Thanks for considering a contribution. A few guidelines to keep this
useful and safe for everyone running it against their own accounts.

## Setup

```bash
pip install -e ".[dev]"
pytest
```

## Adding a job connector

Implement `jobpilot/connectors/base.py`'s `JobConnector` interface:

- `search(keywords, country, limit)` - required.
- `apply(job, application)` - optional; raise `NotImplementedError` if the
  source has no safe/legitimate auto-apply path yet.
- Set `tos_risk = True` if the connector automates a site whose Terms of
  Service restrict scripted access, and gate it behind an
  `ENABLE_<NAME>_CONNECTOR` setting in `jobpilot/config.py`, off by
  default - see `linkedin.py` / `indeed.py` for the pattern.

Prefer official APIs or public, robots.txt-permitted pages (like the Bayt
connector) over authenticated browser automation wherever the job source
offers one.

## What we won't merge

- CAPTCHA-solving or anti-bot-detection evasion of any kind.
- Anything that scrapes or applies at a volume/speed clearly meant to
  evade a platform's own rate limits, rather than working within the
  `BatchRateLimiter` pattern already in `core/rate_limiter.py`.
- Real personal data (resumes, emails, tokens) committed anywhere in the
  repo, including in tests or examples.

## Tests

New agents/connectors should ship with unit tests that don't hit the
network - see `tests/test_bayt_connector.py` for the pattern of testing
the parser against a saved HTML fixture instead of a live request.
