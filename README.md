# JobPilot

A small multi-agent system that finds jobs matching your resume, applies to
the ones worth applying to, and manages the email back-and-forth that
follows - throttled so it doesn't behave like a spam bot.

## How it works

```
resume.pdf ──▶ Profile Agent ──▶ candidate profile (skills, experience, languages)
                                        │
                 ┌──────────────────────┘
                 ▼
          Search Agent  ──▶ job connectors (Bayt, optionally LinkedIn/Indeed)
                 │            searched across your target countries
                 ▼
         Matching Agent  ──▶ Claude scores every job 0-100 against your profile
                 │
                 ▼
       Application Agent ──▶ writes a tailored cover letter, submits the
                              application, N at a time with a cooldown in
                              between (see "Rate limiting" below)
                 │
                 ▼
          Email Agent    ──▶ watches your inbox, classifies replies
                              (interview / rejection / info request),
                              and drafts + sends a reply
```

Each stage is a separate agent module under `jobpilot/agents/`, coordinated
by `jobpilot/orchestrator.py`. You can also run any single stage from the
CLI (see below) instead of the full pipeline.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium   # only needed if you enable LinkedIn/Indeed
cp .env.example .env          # then fill in your API key, email creds, etc.
```

```bash
jobpilot parse-profile --resume ./data/resume.pdf
jobpilot search
jobpilot match
jobpilot apply
jobpilot check-email
# or, the whole pipeline in one go:
jobpilot run
```

## Rate limiting

`APPLICATION_BATCH_SIZE` and `APPLICATION_BATCH_INTERVAL_MINUTES` in `.env`
control the pace of outbound applications - by default, 10 applications,
then a 10 minute pause, repeated until the queue (jobs above
`MATCH_THRESHOLD` that haven't been applied to yet) is empty. This is
implemented in `jobpilot/core/rate_limiter.py` and is deliberately simple:
it's a cooldown between fixed-size batches, not a sliding window.

## Job sources, and their real status

| Connector | Discovery | Auto-apply | Notes |
|---|---|---|---|
| Bayt | ✅ works today | ❌ not implemented | Public search pages, allowed by `robots.txt`, no login needed. Applying requires a logged-in session - contributions welcome. |
| LinkedIn | ⚠️ best-effort, off by default | ❌ intentionally not implemented | See "Risks" below. |
| Indeed | ⚠️ best-effort, off by default | ❌ intentionally not implemented | See "Risks" below. |

**In plain terms: out of the box, JobPilot discovers and scores real jobs
on Bayt across Syria/Turkey/Saudi Arabia (or any countries you configure),
and fully automates the email side of applying and replying. Automatic
form-submission on LinkedIn/Indeed/Bayt itself is not implemented** - those
flows need a logged-in, authenticated session per site, which is exactly
the part with the most ToS/account-risk (see below), so it was left as an
explicit extension point rather than shipped by default.

The most promising path to real end-to-end auto-apply without that risk is
adding connectors for ATS systems that expose public application forms or
APIs (Greenhouse, Lever, SmartRecruiters, Workday) - PRs welcome.

## Risks - read before enabling LinkedIn/Indeed

- LinkedIn's and Indeed's Terms of Service prohibit automated
  scraping/applying. Running `linkedin.py` / `indeed.py` (both **off by
  default**) can get your personal account rate-limited or banned. This
  project will never add CAPTCHA-solving or bot-detection evasion - if a
  site blocks the plain, visible browser session these connectors drive,
  that's the site telling you to stop.
- Auto-sending emails on your behalf (applications and replies) is
  powerful but not infallible - the email agent classifies and drafts with
  an LLM. Set `EMAIL_AUTO_SEND=false` in `.env` to have it draft without
  sending if you'd rather review first.
- Your resume and any parsed profile data stay local (SQLite under
  `data/`, gitignored). Don't commit real personal data into this repo if
  you fork it publicly - use `examples/sample_profile.json` as a
  reference shape instead.

## Project layout

```
jobpilot/
  agents/        profile, search, matching, application, email agents
  connectors/    one module per job source, all implementing connectors/base.py
  core/          config, database, pydantic models, LLM helper, rate limiter
  orchestrator.py
  cli.py
tests/
examples/sample_profile.json
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues: a Greenhouse/Lever
connector, more job-board connectors for a specific country, or improving
the email classifier's prompt.

## License

MIT - see [LICENSE](LICENSE).
