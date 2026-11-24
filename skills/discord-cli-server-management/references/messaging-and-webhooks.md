# Messaging, Zero-Gateway Webhooks, and Human Selectors

## Human Selectors

Commands accept either raw numeric snowflakes or ergonomic selectors:
- **Channel:** `#announcements`, `cat:Engineering/#alerts`, `<#123456789012345678>`
- **Category:** `cat:Engineering`
- **Role:** `role:Ops`, `@everyone`, `<@&123456789012345678>`
- **Member:** `@alice`, `user:alice`, `<@123456789012345678>`
- **Message URL:** `https://discord.com/channels/<guild>/<channel>/<message>` (auto-fills guild & channel)
- **Guild alias:** configure via `discord-cli config set guilds.prod 123456789012345678`, then pass `--guild prod`

If a selector matches multiple resources, `discord-cli` fails closed with `AMBIGUOUS_SELECTOR` and lists all `error.details.candidates`.

## Zero-Gateway Webhooks (CI/CD Notifications)

No bot token or Gateway connection required:

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
discord-cli webhook send \
  --template deploy \
  --title "v1.8.0 Deployed" \
  --description "Production rollout completed cleanly." \
  --field "Commit=$(git rev-parse --short HEAD)" \
  --field "Status=Green"
```

## Context-Window Shaping for Agents

```bash
discord-cli --compact --string-ids --fields id,author.name,content --max-chars 4000 \
  --untrusted-envelope --redact-pii \
  message list "#incidents" --limit 25
```
