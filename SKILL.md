---
name: discord-cli
description: "Command-line tool for managing Discord servers via AI agents. 50+ commands with JSON output for programmatic consumption."
when_to_use: "When you need to manage Discord servers, channels, roles, members, messages, or any Discord operation from the terminal or via AI agent automation."
---

# discord-cli: AI Agent Integration Guide

## Prerequisites

1. **Install:** `pip install discordcli-agents`
2. **Bot token:** Create a bot at the [Discord Developer Portal](https://discord.com/developers/applications)
3. **Required intents:** Guilds, Members, Messages, Message Content, Presences
4. **Set token:** `export DISCORD_BOT_TOKEN="your-token"` or create a `.env` file

## JSON-First Design

discord-cli outputs **JSON by default** — every command returns `{"ok": true, "data": ...}` or `{"ok": false, "error": {"type": "...", "message": "..."}}`. This makes it trivial for AI agents to parse results programmatically.

Use `--human` for rich table output (human-only, not for agents).

## Command Catalog

### channel
Manage text, voice, stage, and forum channels.
- `channel list` — List all channels with IDs, types, categories
- `channel create <name> [--type text|voice|stage|forum] [--category ID] [--topic "text"]` — Create a channel
- `channel delete <id>` — Delete a channel
- `channel edit <id> [--name NEW] [--topic "text"] [--position N]` — Edit a channel
- `channel move <id> --category ID` — Move channel to category
- `channel info <id>` — Detailed channel info

### category
Organize channels into categories.
- `category list` — List all categories
- `category create <name> [--position N]` — Create a category
- `category delete <id>` — Delete a category
- `category edit <id> [--name NEW] [--position N]` — Edit a category

### role
Manage server roles and permissions.
- `role list` — List all roles
- `role create <name> [--color HEX] [--permissions PERMS] [--mentionable] [--hoist]` — Create a role
- `role delete <id>` — Delete a role
- `role edit <id> [--name NEW] [--color HEX] [--mentionable true|false]` — Edit a role
- `role assign <role_id> <user_id>` — Assign role to user
- `role remove <role_id> <user_id>` — Remove role from user
- `role info <id>` — Detailed role info

### member
Moderate and manage server members.
- `member list` — List all members
- `member info <id>` — Detailed member info
- `member kick <id> [--reason "text"]` — Kick a member
- `member ban <id> [--reason "text"] [--delete-message-days N]` — Ban a member
- `member unban <user_id>` — Unban a user
- `member timeout <id> <duration> [--reason "text"]` — Timeout (30s, 5m, 1h, 2d)
- `member untimeout <id>` — Remove timeout
- `member nickname <id> <nickname>` — Set nickname
- `member roles <id>` — List roles for a member

### message
Manage channel messages.
- `message send <channel_id> --content "text"` — Send a message
- `message edit <message_id> --channel ID --content "new text"` — Edit a message
- `message delete <message_id> --channel ID` — Delete a message
- `message purge <channel_id> --limit N [--user ID] [--contains "text"]` — Bulk delete
- `message fetch <message_id> --channel ID` — Get message content
- `message pin <message_id> --channel ID` — Pin a message
- `message unpin <message_id> --channel ID` — Unpin a message
- `message react <message_id> --channel ID --emoji "emoji"` — React to a message

### guild
Server-level management.
- `guild info` — Server info
- `guild edit [--name NEW] [--description "text"]` — Edit server
- `guild emojis list` — List custom emojis
- `guild emojis create <name> --image URL` — Create emoji
- `guild emojis delete <id>` — Delete emoji
- `guild stickers list` — List stickers
- `guild bans list` — List banned users
- `guild prune --days N [--dry-run false]` — Prune inactive members
- `guild regions` — Available voice regions

### permissions
Fine-grained permission control.
- `permissions list --channel ID` — List permission overwrites
- `permissions set --channel ID --role ID --allow PERMS --deny PERMS` — Set permissions
- `permissions reset --channel ID --role ID` — Reset permissions

### webhook
Manage webhooks for automation.
- `webhook list [--channel ID]` — List webhooks
- `webhook create --channel ID --name "name"` — Create webhook
- `webhook delete <id>` — Delete webhook
- `webhook info <id>` — Webhook details

### invite
Manage server invites.
- `invite list` — List all invites
- `invite create --channel ID [--max-age SECONDS] [--max-uses N] [--temporary]` — Create invite
- `invite delete <code>` — Delete invite

### threads
Manage forum and thread channels.
- `threads list [--channel ID]` — List threads
- `threads create <name> --channel-id ID [--type public|private]` — Create thread
- `threads delete <id>` — Delete thread
- `threads archive <id>` — Archive thread
- `threads unarchive <id>` — Unarchive thread
- `threads members <id>` — List thread members

### search
Search server content.
- `search messages --query "text" [--channel-id ID] [--limit N]` — Search messages
- `search members --query "name" [--limit N]` — Search members

### export
Export message history.
- `export channel <id> --limit N [--format json|csv]` — Export messages

## Agent Recipes

### Create Category + Channels + Roles
```bash
# 1. Create a category
discord-cli category create "Projects" | jq -r '.data.id'

# 2. Create channels in that category
discord-cli channel create "general" --type text --category <CATEGORY_ID>
discord-cli channel create "voice" --type voice --category <CATEGORY_ID>

# 3. Create a role
discord-cli role create "ProjectMember" --mentionable | jq -r '.data.id'

# 4. Assign role to a member
discord-cli role assign <ROLE_ID> <USER_ID>
```

### Bulk Message Export
```bash
# Export last 500 messages from a channel as JSON
discord-cli export channel <CHANNEL_ID> --limit 500 --format json > messages.json

# Parse with jq
cat messages.json | jq '.data[] | {author: .author, content: .content, timestamp: .created_at}'
```

### Permission Audit
```bash
# List all channels
CHANNELS=$(discord-cli channel list | jq -r '.data[].id')

# For each channel, list permission overwrites
for ch in $CHANNELS; do
  echo "=== Channel $ch ==="
  discord-cli permissions list --channel $ch
done
```

## Safety Notes

- **Rate limits:** discord.py handles rate limits automatically. No special handling needed.
- **Destructive commands:** `channel delete`, `role delete`, `member kick`, `member ban` are irreversible. Always verify IDs before running.
- **Dry-run:** `guild prune` defaults to dry-run. Use `--dry-run false` to actually prune.
- **Token safety:** Never commit `.env` files or hardcode tokens. Use environment variables.

## Global Options

| Flag | Description | Default |
|------|-------------|---------|
| `--token` | Discord bot token (overrides env/.env) | From env/.env |
| `--guild ID` | Target guild ID (for multi-guild bots) | First available |
| `--human` | Human-readable table output | JSON (default) |
