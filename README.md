# discord-cli

A command-line tool for managing Discord servers and automating Discord via AI agents. It wraps [discord.py](https://github.com/Rapptz/discord.py) in a scriptable interface with JSON output, making it easy to drive Discord server management from shell scripts, CI pipelines, or AI agent tool calls.

## Features

- Manage channels, categories, roles, members, messages, threads, webhooks, invites, and emojis
- JSON output by default (`--human` for a readable summary instead)
- Bot token loaded from the environment or a local `.env` file

## Installation

```bash
pip install discord-cli
```

Or install from source:

```bash
git clone https://github.com/1solomonwakhungu/discord-cli.git
cd discord-cli
pip install -e .
```

## Configuration

Set your Discord bot token via environment variable or a `.env` file in your working directory:

```bash
export DISCORD_BOT_TOKEN="your-bot-token"
```

```
# .env
DISCORD_BOT_TOKEN=your-bot-token
```

## Usage

```bash
# Show help
discord-cli --help

# List channels in a guild
discord-cli --guild <GUILD_ID> channel list

# Send a message
discord-cli message send <CHANNEL_ID> --content "Hello from discord-cli"

# Human-readable output
discord-cli --guild <GUILD_ID> --human role list
```

Or run as a module:

```bash
python -m discord_cli --help
```

## License

MIT
