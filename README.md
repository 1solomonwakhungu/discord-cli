# discord-cli

**Headless, JSON-first Discord CLI for AI agents, shell scripts, cron jobs, and CI/CD.**

[![PyPI version](https://img.shields.io/pypi/v/discordcli-agents.svg)](https://pypi.org/project/discordcli-agents/)
[![PyPI Downloads](https://static.pepy.tech/badge/discordcli-agents/month)](https://pepy.tech/projects/discordcli-agents)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/1solomonwakhungu/discord-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/1solomonwakhungu/discord-cli/actions/workflows/ci.yml)
[![skills.sh](https://skills.sh/b/1solomonwakhungu/discord-cli)](https://skills.sh/1solomonwakhungu/discord-cli)

Current release: 1.4.1 ([PyPI](https://pypi.org/project/discordcli-agents/))

> **64 commands across 13 groups** — manage channels, categories, roles, permissions, members, messages, threads, webhooks, invites, search, and JSON/CSV exports from one command-line binary. No long-running bot daemon. No MCP tool-schema context bloat.

---

## Why `discord-cli`?

- **Built for AI coding agents without MCP overhead** — ships with a prompt-injection-hardened [`skills.sh`](https://skills.sh/1solomonwakhungu/discord-cli/discord-cli-server-management) skill for Claude Code, Codex, Cursor, and GitHub Copilot. Load instructions on demand instead of injecting dozens of tool schemas into every turn.
- **JSON-first by default, human tables on demand** — every command returns `{"ok": true, "data": ...}` (or `{"ok": false, "error": {...}}` with exit code `1`) for clean `jq` pipelines and agent parsing. Add `--human` for Rich terminal tables.
- **Headless & fire-and-exit** — authenticates with a Discord bot token, executes one command, prints the payload, and exits. Drop it straight into GitHub Actions, cron jobs, or shell scripts.
- **Extensible & offline-documented** — add custom command groups via Python entry-point plugins (`discord_cli.plugins`), and read the full auto-generated reference offline with `man discord-cli`.

### Example output

```bash
$ discord-cli guild info
```

```json
{
  "ok": true,
  "data": {
    "id": 123456789012345678,
    "name": "Engineering HQ",
    "member_count": 42,
    "channel_count": 18,
    "role_count": 9,
    "verification_level": "medium"
  }
}
```

Pipe directly into `jq`:

```bash
# Find the ID of #announcements and post a release message
CHANNEL_ID=$(discord-cli channel list | jq -r '.data.channels[] | select(.name == "announcements") | .id')
discord-cli message send "$CHANNEL_ID" --content "v1.4.0 deployed to production"
```

---

## Install

> **Package vs. command name:** The PyPI distribution is **`discordcli-agents`**; the installed executable is **`discord-cli`**.

### Recommended (isolated CLI install)

```bash
# Using uv (fastest)
uv tool install discordcli-agents

# Or using pipx
pipx install discordcli-agents

# Or standard pip
pip install discordcli-agents
```

### Homebrew (macOS / Linux)

```bash
brew install 1solomonwakhungu/tap/discordcli-agents
```

### Windows (Scoop manual manifest)

A CI-synced Scoop manifest is provided in [`packaging/scoop/`](packaging/scoop/README.md) for local/manual installs.

### Offline manual page

A man page ships with the Python package:

```bash
man discord-cli
```

If your virtualenv prefix is not on `MANPATH`:

```bash
man "$(python -c 'import sysconfig; print(sysconfig.get_path("data"))')/share/man/man1/discord-cli.1"
```

---

## Use with AI Agents (Claude Code, Codex, Cursor, Copilot)

Install the bundled **`discord-cli-server-management`** skill via the open [skills CLI](https://skills.sh/1solomonwakhungu/discord-cli/discord-cli-server-management):

```bash
npx skills add 1solomonwakhungu/discord-cli --skill discord-cli-server-management
```

Once installed (with `DISCORD_BOT_TOKEN` in your environment or `.env`), ask your agent things like:
- *"Audit channel permission overwrites across the server and flag anything open to `@everyone`."*
- *"Create a `Releases` category with `#changelog` and `#alerts` channels, and post today's release notes."*
- *"Export the last 500 messages from `#support` to JSON and summarize recurring user issues."*

The published skill includes explicit prompt-injection guardrails instructing agents to treat retrieved Discord messages, usernames, topics, and embeds as untrusted data. See [docs/ai-agents.md](docs/ai-agents.md) for full integration patterns.

---

## Quick setup (2 minutes)

1. Create an application and bot in the [Discord Developer Portal](https://discord.com/developers/applications) and copy the **Bot Token**.
2. Under **Bot → Privileged Gateway Intents**, enable **Server Members Intent** and **Message Content Intent** if you use member listing/search or message search/export. *(Non-privileged commands automatically fall back if privileged intents are disabled.)*
3. Invite the bot to your server with the permissions your workflows need.
4. Provide your token via environment variable or a local `.env` file:

```bash
export DISCORD_BOT_TOKEN="your-bot-token-here"
# Optional: default server when the bot is in multiple guilds
export DISCORD_GUILD_ID="123456789012345678"
```

Verify connectivity:

```bash
discord-cli --human guild info
```

---

## Quick start

```bash
# Inspect server & channels (JSON by default; pass --human before the subcommand for Rich tables)
discord-cli guild info
discord-cli --human channel list

# Create a category and a channel inside it
CAT_ID=$(discord-cli category create "Releases" | jq -r '.data.created.id')
discord-cli channel create "announcements" --type text --category "$CAT_ID" --topic "Release updates"

# Send a plain or embed message
discord-cli message send 123456789012345678 --content "Deploy finished!"
discord-cli message send 123456789012345678 --embed-json '{"title":"Release v1.4.0","color":5763719}'

# Search messages or members (positional query)
discord-cli search messages "deployment" --channel-id 123456789012345678 --limit 25
discord-cli search members "alice"

# Export channel history to JSON or extract CSV
discord-cli export channel 123456789012345678 --limit 500 --format json > history.json
discord-cli export channel 123456789012345678 --limit 500 --format csv | jq -r '.data.data' > history.csv

# Create a role and assign channel permission overwrites
ROLE_ID=$(discord-cli role create "Ops" --color "#3498db" --mentionable --hoist | jq -r '.data.created.id')
discord-cli permissions set --channel 123456789012345678 --role "$ROLE_ID" --allow "view_channel,send_messages"

# Preview inactive member pruning safely (dry-run defaults to true)
discord-cli guild prune --days 30
```

---

## Command reference (64 commands, 13 groups)

Global options (placed **before** the command group): `--token TEXT`, `--guild INTEGER`, `--human`, `--version`.

| Group | Commands | What it covers |
|---|---|---|
| `channel` | `list`, `create`, `delete`, `edit`, `move`, `info` | Text, voice, stage, and forum channels |
| `category` | `list`, `create`, `delete`, `edit` | Channel category organization |
| `role` | `list`, `create`, `delete`, `edit`, `assign`, `remove`, `info` | Server roles, colors, permissions, assignments |
| `member` | `list`, `info`, `kick`, `ban`, `unban`, `timeout`, `untimeout`, `nickname`, `roles` | Member lookup and moderation |
| `message` | `list`, `send`, `edit`, `delete`, `purge`, `fetch`, `pin`, `unpin`, `react` | Messaging, embeds, reactions, bulk purge |
| `guild` | `info`, `edit`, `emojis {list,create,delete}`, `stickers list`, `bans list`, `regions`, `prune` | Server profile, emojis, stickers, bans, pruning |
| `permissions` | `list`, `set`, `reset` | Per-channel role/member permission overwrites |
| `webhook` | `list`, `create`, `delete`, `info` | Channel webhook management |
| `invites` | `list`, `create`, `delete` | Server invite links with max-age/max-uses/temporary |
| `threads` | `list`, `create`, `delete`, `archive`, `unarchive`, `members` | Public/private threads and thread membership |
| `search` | `messages`, `members` | Substring search across channel history or members |
| `export` | `channel` | Export channel history as JSON or CSV |
| `plugins` | `list` | Inspect loaded third-party `discord_cli.plugins` |

---

## Recipes & Automation

Copy-paste workflows in **[docs/recipes.md](docs/recipes.md)**:

- **GitHub Actions** deployment & release notifications
- **Cron** nightly server snapshots and channel exports
- **Bulk role & permission** provisioning scripts
- **Claude Code / Codex** terminal-agent shell and Python wrappers

---

## Extending with Plugins

Third-party Python packages can register new top-level command groups via the `discord_cli.plugins` entry-point group. Broken plugins log a warning and never crash built-in commands. See **[docs/plugins.md](docs/plugins.md)** and [`examples/plugin-hello/`](examples/plugin-hello/).

---

## Documentation

- `man discord-cli` — complete auto-generated CLI reference ([docs/man/discord-cli.1](docs/man/discord-cli.1))
- [Practical recipes](docs/recipes.md)
- [AI agent integration guide](docs/ai-agents.md)
- [Plugin development guide](docs/plugins.md)
- [Contributing guide](CONTRIBUTING.md) · [Security policy](SECURITY.md)

---

## License

MIT License — see [LICENSE](LICENSE).
