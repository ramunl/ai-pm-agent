# Python rules review — 2026-09-27

Reviewed `ai_pm_agent/` against `/opt/ai-rules/global/python.md`.
This completes an existing unpublished refactor and integrates the latest
`origin/main`. The deployed checkout is unchanged.

## Changes

- Split command registration, help/version/core handlers, rule commands, TODO
  commands, and Telegram transport into focused modules.
- Consolidated duplicated Git operations behind an immutable RepositoryConfig.
  Every failed sync stops before editing; failed publication gets a warning
  rather than a success checkmark.
- Preserved shared-core authorization, command hints, runtime reports, and
  snapshot startup/shutdown, payloads, heartbeat, and owner-only file access.
- Added a warning when rule counting skips an unreadable file.
- Enforced imports, 88-character lines, naming, parameter and return annotations,
  public and constructor docstrings, and mutable/default-call checks through Ruff.
  CI runs the same lint, formatting, and pytest checks with submodules initialized.
- Updated the architecture and development instructions.

## Validation and limits

- 99 tests and 2 subtests pass, including the pinned shared-core tests.
- Ruff lint and formatter checks pass.
- Largest production module: 171 lines. No production function exceeds
  55 lines; no function requires more than five parameters.
- No wildcard imports, mutable parameter defaults, or unowned TODO comments found.
- Tests use mock operations and temporary files; no live deployments, package
  upgrades, service restarts, or Telegram messages were performed.

The shared core is tested but not modified. Type annotations are lint-enforced;
a full mypy/pyright analysis and exhaustive behavioral coverage are not claimed.
Logged broad exception handling at the PM publisher boundary retains its retry
contract; atomic-write cleanup re-raises after deleting the temporary file.
