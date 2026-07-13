# Changelog

All notable changes to discord-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
