# discord-cli

discord-cli is a headless, scriptable Discord CLI for automation and AI-agent workflows. It connects with a Discord bot token, runs a single command, and exits; command output is JSON by default so you can pipe it into `jq`, save it in CI logs, or call it from shell scripts and local agents.

[![PyPI version](https://img.shields.io/pypi/v/discordcli-agents.svg)](https://pypi.org/project/discordcli-agents/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://codecov.io/gh/1solomonwakhungu/discord-cli/branch/main/graph/badge.svg)](https://codecov.io/gh/1solomonwakhungu/discord-cli)
[![CI](https://github.com/1solomonwakhungu/discord-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/1solomonwakhungu/discord-cli/actions/workflows/ci.yml)
[![Security](https://img.shields.io/badge/security-policy-reviewed-brightgreen.svg)](SECURITY.md)

Current release: 1.2.1 ([PyPI](https://pypi.org/project/discordcli-agents/))

## Why discord-cli?

- Script Discord operations from shell, cron, GitHub Actions, or an AI agent
- Keep the bot token and workflow logic outside a long-running service process
- Use JSON output for automation and `jq` for filtering without custom glue code

## Install

```bash
pip install discordcli-agents
# or
npx discordcli-agents
```

The installed command is `discord-cli`.

## Quick setup

1. Create a bot at the [Discord Developer Portal](https://discord.com/developers/applications)
2. Add it to your server with the permissions you need
3. Export a token:

```bash
export DISCORD_BOT_TOKEN="your-bot-token-here"
```

Or create a `.env` file in the same directory:

```bash
echo 'DISCORD_BOT_TOKEN=your-bot-token-here' > .env
```

## Quick start

```bash
# Server info
discord-cli guild info

# List channels
discord-cli channel list

# Create a channel
discord-cli channel create "announcements" --type text --topic "Server announcements"

# Send a message
discord-cli message send 123456789012345678 --content "Hello from the CLI!"

# Export channel history
discord-cli export channel 123456789012345678 --limit 500 --format json > history.json
```

## Recipes

Use the ready-to-copy examples in [docs/recipes.md](docs/recipes.md) for:

- GitHub Actions notifications
- Scheduled maintenance and status checks
- Server/channel export and backup
- Bulk role and permission changes
- Claude/Codex and generic terminal-agent workflows

Need a deeper AI-agent workflow guide? See [docs/ai-agents.md](docs/ai-agents.md).

## Command groups

- `channel` — channel management and inspection
- `message` — send, edit, react, purge, and fetch messages
- `guild` — guild profile, emojis, stickers, bans, and prune flows
- `member` — list, info, kick, ban, timeout, nickname, and role checks
- `role` — create, edit, assign, remove, and inspect roles
- `permissions` — per-channel permission overwrites
- `webhook`, `threads`, `invite`, `category`, `search`, and `export` — the rest of the automation surface

## Documentation

- [Recipes](docs/recipes.md)
- [AI agent integration](docs/ai-agents.md)
- [Plugin guide](docs/plugins.md)
- [Contributing guide](CONTRIBUTING.md)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
