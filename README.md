# JobPilot

A small multi-agent system with one job: search well, find a real contact
email for each matching posting, send a tailored application, and handle
the replies that come back - all from a local dashboard, throttled so it
doesn't behave like a spam bot.

Deliberately not in scope: logging into LinkedIn/Indeed/etc. and
driving their application forms. That requires automating a site whose
Terms of Service restrict it, which risks your account and adds a lot of
fragile complexity for a personal tool. The whole "apply" step here is
just: find an email, write a good letter, send it.

## How it works

```
resume.pdf ──▶ Profile Agent ──▶ candidate profile (skills, experience, languages)
                                        │
                 ┌──────────────────────┘
                 ▼
          Search Agent  ──▶ your AI first turns the profile into 4-8 search
                              keywords per country (in the language local
                              postings are usually written in - e.g. Arabic
                              phrasings for Syria/Saudi Arabia), then Bayt
                              (public search pages, robots.txt-permitted) is
                              searched with them
                 ▼
         Matching Agent  ──▶ your chosen AI scores every job 0-100 against your profile
                              (seniority is a hard gate - a "Senior/Staff/Lead"
                              posting scores low even with matching skills if
                              it's above your actual experience level)
                 │
                 ▼
       Application Agent ──▶ finds a contact email on the listing page, writes
                              a tailored cover letter, sends it with your resume
                              attached - N at a time with a cooldown in between
                 │
                 ▼
          Email Agent    ──▶ watches your inbox, classifies replies
                              (interview / rejection / info request),
                              and drafts + sends a reply
```

Each stage is a separate module under `jobpilot/agents/`, coordinated by
`jobpilot/orchestrator.py`. The dashboard (`jobpilot/web/`) lets you trigger
any stage by hand and see what it did.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium   # needed once - see "Job sources" below
jobpilot serve
```

Open `http://127.0.0.1:8000/settings` and fill in:

- **AI provider** - Anthropic (Claude), Google (Gemini), or Ollama (any
  model running locally - no API key, useful if you'd rather not use a
  hosted provider or don't have a key for one). Nothing is pre-filled;
  every user of this repo brings their own key (or their own local model).
- **Email** - the address JobPilot sends from and reads replies on, plus
  an app password (for Gmail: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)).
  Quick-fill buttons set the right IMAP/SMTP host for Gmail/Outlook/Yahoo.
- **Job search** - target countries, a fallback role keyword (used only if
  AI keyword generation fails or no profile is parsed yet), path to your
  resume PDF, and the match threshold.
- **Application pacing** - applications per batch and minutes between batches.

Then from the dashboard (`/`), click through **Run search → Run matching →
Send applications → Check email**, or run the same steps from the CLI:

```bash
jobpilot parse-profile --resume ./data/resume.pdf
jobpilot search
jobpilot match
jobpilot apply
jobpilot check-email
jobpilot run          # the whole pipeline, once
```

## Rate limiting

`application_batch_size` / `application_batch_interval_minutes` in
Settings control the pace of outbound applications - by default, 10
applications, then a 10 minute pause, repeated until the queue (jobs above
the match threshold that haven't been applied to yet) is empty. Implemented
in `jobpilot/core/rate_limiter.py`: a cooldown between fixed-size batches,
not a sliding window.

## Job sources

Currently just **Bayt** (`jobpilot/connectors/bayt.py`): its search-results
pages are public and allowed by `robots.txt`, no login involved - but the
site sits behind Cloudflare's bot-challenge middleware, which blocks a
plain HTTP request regardless of what robots.txt says. So this connector
renders the page with headless Chromium (Playwright) purely to get past
that JS challenge; no account, no session, nothing credential-shaped. Same
story for the contact-email lookup in `jobpilot/core/email_extract.py` - it
tries a plain request first and only falls back to a headless browser if
the response looks challenge-walled. Adding another job source means
implementing `search()` in `jobpilot/connectors/base.py`'s `JobConnector`
interface - see CONTRIBUTING.md.

Bayt serves the same posting under `/en/...` and `/ar/...` (and other
locale) paths with only the display text translated, keeping the same
numeric job id - so an Arabic-script keyword is searched against the
`/ar/` path (where local postings actually live) and still dedupes
correctly against anything the English-language search also found.

Finding a contact email per job is best-effort: `jobpilot/core/email_extract.py`
looks for one on the listing page. When it can't find one, the application
is marked `failed` and retried on the next `apply` run rather than being
skipped forever - some listings (Bayt's own "Quick Apply" ones especially)
genuinely never expose a direct email and will keep failing, which is
expected: that job needs a manual application. Every successful application
email includes the resume PDF from Settings as an attachment, not just a
text cover letter.

## Risks and privacy

- Auto-sending emails on your behalf (applications and replies) is
  powerful but not infallible - the email agent classifies and drafts with
  an LLM. Uncheck "Auto-send replies" in Settings to have it draft without
  sending if you'd rather review first.
- Your resume, parsed profile, API keys, and email password all live in
  the local SQLite database under `data/` (gitignored) - never in a file
  that gets committed. If you fork this repo publicly, don't hardcode your
  own credentials anywhere in source; use the Settings page.

## Project layout

```
jobpilot/
  agents/        profile, search, matching, application, email agents
  connectors/    one module per job source (implements connectors/base.py)
  core/          settings store (DB-backed), database, models, LLM
                 provider abstraction, rate limiter, email extraction
  web/           the dashboard (FastAPI + Jinja2 templates)
  orchestrator.py
  cli.py
tests/
examples/sample_profile.json
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues: another job
connector, a third AI provider, or improving the email classifier's prompt.

## License

MIT - see [LICENSE](LICENSE).
