# Changelog

All notable changes to discord-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-09-14

### Added

- Published the agent skill on [skills.sh](https://skills.sh/1solomonwakhungu/discord-cli/discord-cli-server-management)
- Automated Scoop manifest updates after each PyPI publish
- Automated version synchronization across `README.md`, `commands.json`, `packaging/npm/package.json`, `CITATION.cff`, and `docs/man/discord-cli.1` in release commits

### Changed

- Renamed the agent skill to `discord-cli-server-management` for better agent search discovery
- Hardened agent skill instructions against prompt injection from untrusted Discord content

## [1.3.0] - 2026-08-26

### Added

- Auto-generated offline man page (`docs/man/discord-cli.1`) shipped in the wheel and verified in CI
- Global `--token`, `--guild`, and `--human` options on the root CLI group
- Practical automation recipes (`docs/recipes.md`) and sharpened project positioning
- Homebrew tap installation instructions and automated coverage enforcement
- Expanded `SECURITY.md` guidance and clarified manual/local Scoop manifest documentation

### Fixed

- Pinned `gitpython` to keep semantic-release workflows working reliably
- Removed broken Codecov and security badges from `README.md`

## [1.2.1] - 2026-07-15

### Fixed

- Resolved `mypy` typecheck errors and synchronized packaging metadata
- Fixed protected-branch release CI workflow and updated GitHub Actions dependencies

## [1.2.0] - 2026-07-14

### Added

- Plugin system for third-party command extensions
- Homebrew, Scoop, and npm installation packaging

## [1.1.0] - 2026-07-14

### Added

- Automated semantic release, changelog generation, and PyPI publishing

## [1.0.0] - 2026-07-14

### Added

- Test suite, coverage reporting, type checking, and contributor tooling

## [0.1.1] - 2026-07-13

### Fixed

- Broken CI badge URL in README that pointed to the non-existent `container.yaml` workflow
- PyPI badge switched to shields.io for reliability
- Import errors in the invites, search, threads, and export modules caused by a non-existent output function and incorrect `run_bot` signature
- All command modules now use the `registry.invoke()` pattern consistently

## [0.1.0] - 2026-07-13

### Added

- Initial release of discordcli-agents
- 50+ commands across 12 command groups (channels, categories, roles, members, messages, guilds, permissions, webhooks, invites, threads, search, export)
- JSON output by default with `--human` flag for table output
- Headless operation (connect, act, disconnect)
- AI agent-friendly design with structured JSON output
- Modular command architecture with plugin-friendly registry pattern
