# RepoPilot

RepoPilot is a read-only-first MCP agent for exploring unfamiliar code
repositories before coding.

It is designed for the moment after cloning a repository and before making the
first change: RepoPilot inspects project structure, build clues, Git metadata,
and task-related files, then produces concise onboarding briefs, runbooks,
module maps, and task briefs.

## Planned Capabilities

- Repository overview: purpose, stack, important files, and directory roles.
- Runbook inference: install, build, test, and launch hints.
- Module mapping: key modules and likely entry points.
- Task briefing: task-oriented search and recommended reading order.
- Permission control: session-scoped read roots and output-only write roots.
- Dual interface: developer-friendly CLI and lightweight Web UI.

## Status

Initial project scaffold. Implementation will be added after the repository and
monorepo integration are in place.

## License

MIT
