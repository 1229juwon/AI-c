# Development Guide

## Scope

This project is a local learning crawler for `web-scraping.dev`.

## Required behavior

- Respect `https://web-scraping.dev/robots.txt`.
- Never request `/robots-disallowed`.
- Enforce the declared crawl delay between requests.
- Keep requests limited to the configured allowed host.
- Do not add anti-bot, CAPTCHA, authentication, or access-control bypasses.

## Commands

```powershell
python -m uvicorn app.main:app --reload
python -m ruff check .
python -m pytest
```

## Style

- Prefer small, typed modules.
- Keep crawler policy decisions separate from Selenium execution.
- Surface failures in logs and API responses; do not silently ignore them.
