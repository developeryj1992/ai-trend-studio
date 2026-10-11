# Security Policy

## Reporting a vulnerability

Please open a private security advisory on GitHub or contact a maintainer directly. Do not publicly post exploit details or user data.

## Data handling

- Workspace data is stored locally in `data/db.json`.
- API keys entered in Settings remain on the local machine.
- UI state and exports mask API keys.
- The optional model endpoint receives only the content you choose to summarize.

## Recommended deployment

Run the app on `127.0.0.1`. Do not expose the server publicly without adding authentication, TLS, upload limits, and stricter request validation.
