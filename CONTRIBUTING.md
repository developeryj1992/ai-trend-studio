# Contributing

Thanks for helping improve AI Trend Studio.

## Ways to help

- Add or improve a public/official source connector.
- Improve Chinese and multilingual summarization.
- Add tests for edge cases and malformed API responses.
- Improve accessibility, responsive layout, and UI polish.
- Report platform compatibility issues.

## Development setup

```bash
python -m unittest discover -s tests -v
python app.py
```

There are no required Python packages.

## Pull request checklist

- Keep the change scoped and compatible with Python 3.10+.
- Add tests for parsing, filtering, or summarizing behavior.
- Run `python -m unittest discover -s tests -v`.
- Do not commit `data/db.json`, API keys, cookies, or scraped content.
- Do not add logic that bypasses CAPTCHAs, authentication, rate limits, or platform protections.

## Reporting bugs

Include the Python version, OS, browser, steps to reproduce, and redacted logs. Platform API failures are often regional or temporary, so mention whether the same URL opens in a normal browser.
