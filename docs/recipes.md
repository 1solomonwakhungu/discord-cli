# Practical recipes

These examples use only commands and flags that are present in this repository. They assume `DISCORD_BOT_TOKEN` is exported in the environment or available from a local `.env` file.

## GitHub Actions notifications

Use `discord-cli message send` from a workflow to post a deployment or release notice to a Discord channel.

```yaml
name: notify-discord

on:
  push:
    branches: [main]

jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install discord-cli
        run: pip install discordcli-agents

      - name: Send deployment notification
        env:
          DISCORD_BOT_TOKEN: ${{ secrets.DISCORD_BOT_TOKEN }}
        run: |
          discord-cli message send "${{ vars.DISCORD_ALERT_CHANNEL_ID }}" \
            --content "Deploy complete on ${GITHUB_REF_NAME}: ${GITHUB_SHA::7}"
```

If you want a richer payload, use `--embed-json` with a JSON string that matches Discord embed fields.

## Scheduled operations

Cron works well for lightweight health checks and status snapshots because each CLI call is a one-shot action.

```bash
# Example: daily server snapshot at 09:00 UTC
0 9 * * * DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  /usr/local/bin/discord-cli guild info > /var/backups/discord/guild-info.json
```

You can also schedule a full export for a channel:

```bash
# Run nightly, capture the last 1,000 messages
0 1 * * * DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  /usr/local/bin/discord-cli export channel 123456789012345678 --limit 1000 --format json \
  > /var/backups/discord/announcements-$(date -u +%F).json
```

## Server and channel export / backup

```bash
mkdir -p backups

# Export the last 1,000 messages from one channel
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  discord-cli export channel 123456789012345678 --limit 1000 --format json \
  > backups/general-$(date -u +%F).json

# Save a server snapshot for reference
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  discord-cli guild info > backups/guild-info-$(date -u +%F).json
```

If you want CSV output instead of JSON, switch `--format csv`.

## Bulk role and server administration

Create a role and assign it to a member in a scriptable, reproducible way:

```bash
# List current roles in the server
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" discord-cli role list | jq '.data.roles[] | {id, name}'

# Create a new role
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  discord-cli role create "Ops" --mentionable --hoist

# Assign a role to a user
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  discord-cli role assign 111111111111111111 222222222222222222
```

For channel-level access control, set permission overwrites by role or member:

```bash
# Example: allow view_channel and send_messages on one channel for a role
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  discord-cli permissions set \
    --channel 333333333333333333 \
    --role 111111111111111111 \
    --allow "view_channel, send_messages"
```

Permission names are the standard Discord permission attributes, such as `view_channel`, `send_messages`, `manage_messages`, and similar names exposed by `discord.py`.

## Claude Code, Codex, and generic terminal-agent integration

The CLI is easy to call from a terminal agent because each command returns JSON. A plain shell wrapper is enough:

```bash
# List channels and print their IDs/names
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  discord-cli channel list | jq '.data.channels[] | {id, name}'

# Find a target channel and send a message
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  discord-cli channel list | jq -r '.data.channels[] | select(.name == "general") | .id' | \
  while read -r channel_id; do
    discord-cli message send "$channel_id" --content "Message from a terminal agent."
  done
```

A Python wrapper is also straightforward:

```python
import json
import os
import subprocess


def run(*args):
    result = subprocess.run(
        ["discord-cli", *args],
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)

channels = run("channel", "list")
general = next(c for c in channels["data"]["channels"] if c["name"] == "general")
run("message", "send", str(general["id"]), "--content", "Hello from a terminal agent.")
```

## Thread and invite workflow

```bash
# Create a public thread in a channel
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  discord-cli threads create "Release notes" --channel-id 123456789012345678 --type public

# Create an invite for a channel
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN}" \
  discord-cli invites create --channel-id 123456789012345678 --max-age 3600 --max-uses 1
```

## Useful patterns

- Verify environment setup before automation: `discord-cli guild info`
- Save JSON to disk for review: `discord-cli export channel 123 --limit 500 --format json > backup.json`
- Filter a command result with `jq` before acting on it: `discord-cli channel list | jq '.data.channels[] | select(.name == "general")'`
- Keep bot secrets in environment variables or `.env`, not hardcoded into scripts
