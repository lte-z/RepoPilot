# Security Policy

RepoPilot is read-only-first and keeps local configuration in `.repopilot/`, which is ignored by Git.

## Reporting A Vulnerability

Please open a GitHub issue with a minimal description of the vulnerability. Do not include API keys, private repository code, or sensitive paths in public issue text.

## Sensitive Data

Do not commit:

- `.repopilot/`
- `.env` files
- API keys or bearer tokens
- Reports containing private repository content
