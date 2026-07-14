# discord-cli: Command-Line Tool for Discord Server Management & Automation

**discord-cli** is a command-line interface for managing Discord servers and automating Discord operations via AI agents. It provides 50+ commands for channel management, role administration, member moderation, message operations, and more — all from the terminal with JSON output for programmatic consumption.

[![PyPI version](https://img.shields.io/pypi/v/discordcli-agents.svg)](https://pypi.org/project/discordcli-agents/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/1solomonwakhungu/discord-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/1solomonwakhungu/discord-cli/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/1solomonwakhungu/discord-cli/branch/main/graph/badge.svg)](https://codecov.io/gh/1solomonwakhungu/discord-cli)

---

## What is discord-cli?

discord-cli is a Discord command-line tool that lets you manage Discord servers from the terminal. Instead of clicking through the Discord UI, you run commands like `discord-cli channel list` or `discord-cli role create "Moderators"` to automate server administration, bulk operations, and bot-like workflows — all without keeping a bot process running.

It's designed for **DevOps teams**, **server administrators**, and **AI agents** who need programmatic, scriptable access to Discord server management.

## Features

discord-cli provides **50+ commands** organized into 12 command groups:

| Command Group | Key Commands | Use Case |
|---------------|-------------|----------|
| **channels** | list, create, delete, edit, move, info | Manage text, voice, stage, and forum channels |
| **categories** | list, create, delete, edit | Organize channels into categories |
| **roles** | list, create, delete, edit, assign, remove | Manage server roles and permissions |
| **members** | list, info, kick, ban, timeout, nickname | Moderate and manage server members |
| **messages** | send, edit, delete, purge, pin, react | Manage channel messages at scale |
| **guilds** | info, edit, emojis, bans, prune | Server-level configuration and management |
| **permissions** | list, set, reset | Fine-grained permission control per channel |
| **webhooks** | list, create, delete, info | Manage webhooks for automation |
| **invites** | list, create, delete | Manage server invites |
| **threads** | list, create, archive, members | Manage forum and thread channels |
| **search** | messages, members | Search server content programmatically |
| **export** | channel | Export message history to JSON or CSV |

### Key Design Principles

- **JSON by default**: Every command outputs structured JSON for programmatic consumption and piping
- **Human-readable mode**: Add `--human` flag for rich table output in the terminal
- **Headless operation**: Connects, performs the action, disconnects — no persistent bot process needed
- **AI agent friendly**: JSON output makes it trivial for AI agents (Claude, Codex, GPT) to parse results

## Installation

### pip (recommended)

```bash
pip install discordcli-agents
```

The PyPI package is named `discordcli-agents`; the installed command remains `discord-cli`.

### Homebrew

```bash
brew install ./packaging/homebrew/discordcli-agents.rb
```

### Scoop (Windows)

```powershell
scoop install ./packaging/scoop/discordcli-agents.json
```

### npm

```bash
npx discordcli-agents
# or
npm install -g discordcli-agents
```

The npm package is a thin wrapper that installs `discordcli-agents` via pip and forwards commands to `discord-cli`. See [packaging/npm](packaging/npm) for details.

### From source

```bash
git clone https://github.com/1solomonwakhungu/discord-cli.git
cd discord-cli
pip install -e .
```

### Quick setup

1. Create a Discord bot application at the [Discord Developer Portal](https://discord.com/developers/applications)
2. Enable the **Message Content Intent** and **Server Members Intent** in your bot settings
3. Add the bot to your server with administrator permissions
4. Set your bot token:

```bash
export DISCORD_BOT_TOKEN="your-bot-token-here"
```

Or create a `.env` file in your working directory:

```bash
echo 'DISCORD_BOT_TOKEN=your-bot-token-here' > .env
```

## Quickstart

```bash
# Get server info
discord-cli guild info

# List all channels
discord-cli channels list

# Create a new text channel
discord-cli channels create "announcements" --type text --topic "Server announcements"

# List all members
discord-cli members list

# Send a message
discord-cli messages send 1234567890 --content "Hello from the CLI!"

# Bulk delete messages
discord-cli messages purge 1234567890 --limit 100

# Ban a member
discord-cli members ban 9876543210 --reason "Spam"

# Export channel history
discord-cli export channel 1234567890 --limit 500 --format json
```

## AI Agent Integration

discord-cli is designed to be used by AI agents for Discord automation. The JSON output format makes it easy for agents to parse results and make decisions:

```python
# Example: AI agent uses discord-cli to manage a server
import subprocess
import json

# List all channels
result = subprocess.run(
    ["discord-cli", "channels", "list"],
    capture_output=True, text=True
)
channels = json.loads(result.stdout)

# Find a channel by name
target = next(c for c in channels if c["name"] == "general")

# Send a message to that channel
subprocess.run([
    "discord-cli", "messages", "send", str(target["id"]),
    "--content", "Automated message from AI agent"
])
```

**Supported AI agent platforms:**
- Claude Code (Anthropic)
- Codex CLI (OpenAI)
- Custom LLM agents with terminal access
- Any tool that can parse JSON output

## Configuration

discord-cli loads configuration in the following order (first match wins):

1. `--token` CLI flag
2. `DISCORD_BOT_TOKEN` environment variable
3. `.env` file in the current directory
4. `.env` file in the package directory

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--token` | Discord bot token | Falls back to env/.env |
| `--guild ID` | Target guild ID (for multi-guild bots) | First available guild |
| `--human` | Human-readable table output | JSON (default) |
| `--dry-run` | Preview without executing | Disabled |

## FAQ

### How does discord-cli differ from a Discord bot?

A Discord bot runs as a persistent process that stays online and responds to events. discord-cli is a **headless command-line tool** — it connects, performs a single action, and disconnects. This makes it ideal for scripts, CI/CD pipelines, and AI agent workflows where you need one-off actions without maintaining a bot process.

### Can I use discord-cli without a Discord bot token?

No. discord-cli requires a valid Discord bot token to connect to the Discord API. You can create a bot for free at the [Discord Developer Portal](https://discord.com/developers/applications).

### Does discord-cli support multiple servers?

Yes. If your bot is in multiple servers, use `--guild ID` to specify which server to operate on. Without this flag, discord-cli defaults to the first available guild.

### Is discord-cli safe for production use?

discord-cli uses the official [discord.py](https://github.com/dpydpyd/discord.py) library and respects Discord's rate limits automatically. However, always test commands in a development server first, especially destructive operations like `channel delete` or `member ban`.

### Can AI agents use discord-cli?

Yes! discord-cli is specifically designed for AI agent integration. The JSON output format allows agents to parse results programmatically. See the [AI Agent Integration](#ai-agent-integration) section above.

### How do I contribute to discord-cli?

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and PR guidelines.

## Comparison with Alternatives

| Feature | discord-cli | Discord Bot | Discord UI |
|---------|-------------|-------------|------------|
| Headless/CLI | Yes | No (persistent process) | No |
| JSON output | Yes (default) | Custom code needed | No |
| AI agent compatible | Yes | Requires custom integration | No |
| Bulk operations | Yes | Custom code needed | Limited |
| Scriptable | Yes (shell/python) | Requires bot framework | No |
| Persistent process | No | Yes | N/A |
| Setup time | 2 minutes | 30+ minutes | Instant |

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Links

- [GitHub Repository](https://github.com/1solomonwakhungu/discord-cli)
- [Issue Tracker](https://github.com/1solomonwakhungu/discord-cli/issues)
- [PyPI Package](https://pypi.org/project/discordcli-agents/)
