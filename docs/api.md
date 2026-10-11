# HTTP API

All responses are JSON unless otherwise noted. The default base URL is `http://127.0.0.1:8765`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/state` | Read workspace state with masked credentials |
| `POST` | `/api/refresh` | Refresh public trend sources |
| `POST` | `/api/imports` | Import and summarize content |
| `POST` | `/api/settings` | Update keywords and model settings |
| `POST` | `/api/live/sessions` | Create a live session |
| `POST` | `/api/live/sessions/{id}/events` | Append a speech/caption/comment event |
| `POST` | `/api/live/sessions/{id}/finish` | Finish a session and generate a summary |
| `GET` | `/api/export` | Export workspace JSON with masked credentials |

## Refresh

```http
POST /api/refresh
Content-Type: application/json

{"include_unrelated": false}
```

Each source reports success independently. A failing source does not prevent other sources from returning.

## Import

```http
POST /api/imports
Content-Type: application/json

{
  "platform": "xiaohongshu",
  "kind": "note",
  "title": "Example note",
  "url": "https://example.com/note",
  "author": "example",
  "raw_text": "Paste a description, transcript, or comments here."
}
```

SRT/VTT timestamps are removed automatically before summarization.
