# Contributing

Thanks for taking a look at RepoPilot.

## Development Setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest tests
```

## Local Data

RepoPilot stores runtime configuration, API keys, and reports in `.repopilot/`. This directory is intentionally ignored by Git.

Before opening a pull request, check that you have not included:

- API keys or `.env` values.
- Local absolute paths.
- Private repository content copied from analyzed projects.

## Pull Requests

Keep changes focused and include the tests or manual verification you ran.
