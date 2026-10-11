# Architecture

AI Trend Studio is intentionally small enough to audit in one sitting.

```text
Browser dashboard
  ├── Trends: filter public signals
  ├── Content distillation: import text/subtitles
  ├── Live sessions: capture speaker events
  └── Settings: keywords + optional LLM
        │
        ▼
Standard-library HTTP API
  ├── /api/refresh
  ├── /api/imports
  ├── /api/live/sessions/*
  ├── /api/settings
  └── /api/export
        │
        ├── Source adapters
        │   ├── Douyin public hot search
        │   ├── Bilibili popular videos
        │   ├── Weibo public hot search
        │   └── Zhihu public hot list
        │
        ├── Distillation engine
        │   ├── SRT/VTT cleanup
        │   ├── Chinese sentence scoring
        │   ├── Keyword extraction
        │   └── OpenAI-compatible endpoint, optional
        │
        └── JSON store
            └── data/db.json
```

## Design rules

1. **No hidden network calls.** Public sources run only when refresh is requested; the optional model is called only when a summary is requested and configured.
2. **No runtime framework.** `app.py` uses the Python standard library, reducing supply-chain risk and install friction.
3. **Local-first storage.** A single JSON file is easy to inspect, back up, and export.
4. **Graceful degradation.** A failing source does not break the refresh cycle; a missing model key falls back to local summarization.
5. **Compliance by default.** The collectors use public metadata endpoints and normal browser headers only.

## Adding a source connector

Implement a function that returns a normalized list:

```python
def my_source() -> list[dict[str, Any]]:
    return [
        item(
            platform="my_platform",
            kind="hot_search",
            title="Example topic",
            url="https://example.com/topic",
            rank=1,
            heat=1234,
        )
    ]
```

Then register it in `SOURCE_ADAPTERS`. Add tests for malformed payloads and do not include credentials in repository code.
