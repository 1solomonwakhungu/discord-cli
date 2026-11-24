---
name: discord-cli-server-management
description: "Manages Discord servers from the terminal with JSON-first commands covering channels, categories, roles, members, messages, guilds, permissions, webhooks, invites, threads, search, export, audit logs, diagnostics, raw REST API, runtime schema introspection, auth profiles, config, and shell completions. Use when automating Discord administration, moderation, CI notifications, or server audits from an AI agent or shell script."
license: MIT
compatibility: "Python >=3.9, discord-cli (PyPI: discordcli-agents) installed via uv, pipx, pip, npm, Homebrew, Scoop, or OCI container."
metadata:
  version: "2.0"
  category: "developer-tools"
  agent-workflow: "discover-dry-run-execute"
---

# discord-cli-server-management: AI Agent Integration Guide

## Agent Workflow (Discover → Dry-Run → Execute)

1. **Discover capabilities & schemas (zero network calls):**
   - `discord-cli describe list --compact` — list every command with its `risk` (`read`, `write`, `destructive`)
   - `discord-cli describe command <group> <subcommand>` or `discord-cli <group> <subcommand> --schema` — inspect exact JSON Schema inputs & required bot permissions
2. **Diagnose connectivity & permissions:**
   - `discord-cli doctor` — verify bot auth, intents, role hierarchy, and permissions
3. **Preview mutations safely:**
   - Pass `--dry-run` on any `write` or `destructive` command to inspect the plan and obtain a deterministic `confirm_token` without modifying Discord.
4. **Enforce guardrails & prompt-injection defense:**
   - Use `--policy read-only` or `--policy allow-write` (or env `DISCORD_CLI_POLICY`), `--untrusted-envelope`, `--redact-pii`, `--compact`, `--fields`, `--max-chars`, `--string-ids`, and `--semantic-exit-codes`.
   - See [references/safety-and-guardrails.md](references/safety-and-guardrails.md) for policy ceilings, allowlists, confirmation tokens, and audit logging.
   - See [references/messaging-and-webhooks.md](references/messaging-and-webhooks.md) for rich embeds, zero-gateway webhooks, templates, and human selectors.
   - See [scripts/audit-permissions.sh](scripts/audit-permissions.sh) for a ready-to-run guild permission audit recipe.

## Command Catalog

### channel
Manage text, voice, stage, and forum channels.
- `channel list` — List all channels with IDs, types, categories
- `channel create <name> [--type text|voice|stage|forum] [--category ID] [--topic "text"] [--position N] [--nsfw] [--slowmode SECONDS]` — Create a channel
- `channel delete <id>` — Delete a channel
- `channel edit <id> [--name NEW] [--topic "text"] [--position N] [--slowmode SECONDS] [--nsfw true|false]` — Edit a channel
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
- `role edit <id> [--name NEW] [--color HEX] [--permissions PERMS] [--mentionable true|false] [--hoist true|false]` — Edit a role
- `role assign <role_id> <user_id>` — Assign role to user
- `role remove <role_id> <user_id>` — Remove role from user
- `role info <id>` — Detailed role info

### member
Moderate and manage server members.
- `member list [--limit N] [--after ID]` — List members (with optional pagination)
- `member info <id>` — Detailed member info
- `member kick <id> [--reason "text"]` — Kick a member
- `member ban <id> [--reason "text"] [--delete-message-days N]` — Ban a member
- `member unban <user_id>` — Unban a user
- `member timeout <id> <duration> [--reason "text"]` — Timeout (30s, 5m, 1h, 2d)
- `member untimeout <id>` — Remove timeout
- `member nickname <id> <nickname>` — Set nickname
- `member roles <id>` — List roles for a member

### message
Manage channel messages (supports numeric IDs, `#channel` selectors, and Discord message URLs).
- `message list <channel_id> [--limit N] [--before ID] [--after ID]` — List recent messages in a channel
- `message send <channel_id> [--content "text"] [--embed-json JSON] [--embed-file PATH] [--file PATH] [--reply-to ID] [--silent] [--split]` — Send a message
- `message edit <message_id> [--channel ID] --content "new text"` — Edit a message
- `message delete <message_id> [--channel ID]` — Delete a message
- `message purge <channel_id> --limit N [--user ID] [--contains "text"]` — Bulk delete
- `message fetch <message_id> [--channel ID]` — Get message content
- `message pin <message_id> [--channel ID]` — Pin a message
- `message unpin <message_id> [--channel ID]` — Unpin a message
- `message pins <channel_id> [--limit N]` — List pinned messages
- `message publish <message_id> [--channel ID]` — Crosspost an announcement message
- `message download <message_id> [--channel ID] --out DIR` — Download attachments safely
- `message react <message_id> [--channel ID] --emoji "emoji"` — React to a message
- `message unreact <message_id> [--channel ID] --emoji "emoji" [--user ID]` — Remove a reaction

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
- `permissions set --channel ID [--role ID] [--user ID] [--allow PERMS] [--deny PERMS]` — Set permissions
- `permissions reset --channel ID [--role ID] [--user ID]` — Reset permissions

### webhook
Manage and execute webhooks for automation.
- `webhook list [--channel ID] [--show-secrets]` — List webhooks (tokens redacted by default)
- `webhook create --channel ID --name "name" [--show-secrets]` — Create webhook
- `webhook edit <id> [--name "name"] [--channel ID] [--show-secrets]` — Edit webhook
- `webhook delete <id>` — Delete webhook
- `webhook info <id> [--show-secrets]` — Webhook details
- `webhook send [--url URL] [--content "text"] [--embed-json JSON] [--embed-file PATH] [--file PATH] [--username NAME] [--avatar-url URL] [--thread-id ID] [--thread-name NAME] [--template NAME] [--title TEXT] [--description TEXT] [--color HEX] [--field K=V] [--split] [--silent] [--no-wait]` — Send via webhook URL (zero Gateway)
- `webhook edit-message <message_id> [--url URL] [--thread-id ID] [--content "text"] [--embed-json JSON] [--embed-file PATH] [--template NAME] [--title TEXT] [--description TEXT] [--color HEX] [--field K=V]` — Edit webhook message
- `webhook delete-message <message_id> [--url URL] [--thread-id ID]` — Delete webhook message
- `webhook fetch-message <message_id> [--url URL] [--thread-id ID]` — Fetch webhook message

### invites
Manage server invites (`invite` also works as a shorthand alias).
- `invites list` — List all invites
- `invites create --channel-id ID [--max-age SECONDS] [--max-uses N] [--temporary]` — Create invite
- `invites delete <code>` — Delete invite

### threads
Manage forum and thread channels.
- `threads list [--channel-id ID]` — List threads
- `threads create <name> --channel-id ID [--type public|private] [--auto-archive 60|1440|4320|10080]` — Create thread
- `threads delete <id>` — Delete thread
- `threads archive <id>` — Archive thread
- `threads unarchive <id>` — Unarchive thread
- `threads members <id>` — List thread members

### search
Search server content.
- `search messages <query> [--channel-id ID] [--limit N] [--scan-limit N]` — Search messages
- `search members <query> [--limit N]` — Search members

### export
Export message history.
- `export channel <id> [--limit N] [--format json|csv]` — Export messages

### plugins
Inspect loaded third-party `discord_cli.plugins` extensions.
- `plugins list` — List loaded plugins

### audit
Inspect guild audit logs for moderation and security triage.
- `audit list [--limit N] [--action NAME] [--user ID] [--before ID] [--after ID]` — List recent audit log entries
- `audit user <user_id> [--limit N]` — List audit entries performed by or targeting a user

### doctor
Diagnose bot auth, privileged intents, role hierarchy, and permissions.
- `doctor check [--channel ID]` — Run connectivity, intent, hierarchy, and permission diagnostics

### api
Call any Discord REST API v10 endpoint directly.
- `api request <method> <endpoint> [--json-body JSON] [--query K=V] [--reason TEXT]` — Execute a raw Discord REST API v10 request

### describe
Introspect live CLI schemas, risk levels, and `commands.json`.
- `describe list [--compact] [--group NAME] [--risk read|write|destructive]` — List commands with risk metadata
- `describe command <path...>` — Return full JSON Schema for a command
- `describe commands-json` — Emit live `commands.json` manifest

### auth
Manage named authentication profiles and optional OS keyring tokens.
- `auth login [--profile NAME] [--token TOKEN] [--guild ID] [--set-default]` — Configure a profile and optionally store its token in OS keyring
- `auth status [--profile NAME]` — Show active profile, token source, and keyring availability
- `auth switch <profile_name>` — Switch the default active profile
- `auth logout [--profile NAME]` — Remove stored keyring token for a profile

### config
Inspect and edit non-secret TOML configuration and guild aliases.
- `config path` — Show user and project config file paths
- `config list` — Display merged non-secret configuration
- `config get <key>` — Read a dot-path config value
- `config set <key> <value>` — Set a non-secret config value (e.g. `guilds.prod 123456`)

### completion
Generate shell completions.
- `completion generate <bash|zsh|fish>` — Output shell completion script

## Global Options

| Flag | Description |
|------|-------------|
| `--token` | Discord bot token (overrides env/.env/keyring) |
| `--guild ID` | Target guild ID or config alias |
| `--profile NAME` | Named config profile (`DISCORD_PROFILE`) |
| `--human` | Rich table output (human-only) |
| `--gateway` | Opt into WebSocket Gateway instead of REST-first default |
| `--no-plugins` | Disable third-party plugins |
| `--compact` | Minified single-line JSON |
| `--fields` | Comma-separated dot-path field projection |
| `--max-chars` | Token-aware valid-JSON truncation (min 256) |
| `--string-ids` | Serialize 64-bit snowflake IDs as strings |
| `--format` | Output format (`json\|jsonl\|csv\|table\|markdown\|raw`) |
| `--quiet` | Print only primary resource IDs |
| `--output` | Write output atomically to file |
| `--policy` | Safety ceiling (`read-only\|allow-write\|allow-destructive`) |
| `--dry-run` | Preview mutation and return `confirm_token` without modifying Discord |
| `--yes` | Confirm destructive command when `DISCORD_CLI_REQUIRE_CONFIRM=1` |
| `--confirm-token` | Deterministic token from `--dry-run` |
| `--max-mutations` | Cap bulk mutations (e.g. `message purge`) |
| `--reason` | Default audit log reason (`DISCORD_CLI_REASON`) |
| `--untrusted-envelope` | Wrap external Discord text in random-nonce XML boundaries |
| `--redact-pii` | Scrub emails, tokens, API keys, JWTs, and webhooks |
| `--semantic-exit-codes` | Return exit codes 3–7 for structured error classes |
