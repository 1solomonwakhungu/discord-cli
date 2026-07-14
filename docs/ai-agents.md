# AI Agent Integration Guide

This guide covers how to integrate discord-cli with AI agents for Discord server automation.

## Why discord-cli for AI Agents?

discord-cli is designed **JSON-first**, making it ideal for AI agent consumption:

1. **Structured output**: Every command returns `{"ok": true/false, "data": ..., "error": ...}`
2. **No persistent process**: Connects, performs action, disconnects — perfect for one-shot agent calls
3. **Comprehensive**: 50+ commands across 12 command groups cover every Discord operation
4. **Scriptable**: Shell-friendly, pipeable, works in any automation pipeline

## Claude Code Integration

### Option 1: Bash Tool (Recommended)

Claude Code can use discord-cli directly via the Bash tool:

```python
# In Claude Code, ask it to:
"Use discord-cli to list all channels in the server"
```

Claude Code will run:
```bash
discord-cli channel list
```

And parse the JSON output to understand the result.

### Option 2: Add as a Skill

Place `SKILL.md` in your project's `.claude/skills/` directory. Claude Code will automatically discover it and know when to use discord-cli.

### Option 3: MCP Server (Advanced)

Wrap discord-cli in an MCP server for deeper integration:

```json
{
  "mcpServers": {
    "discord": {
      "command": "discord-cli",
      "args": ["mcp", "serve"]
    }
  }
}
```

## Codex CLI Integration

Codex CLI can use discord-cli via terminal execution:

```bash
# Tell Codex: "List all Discord channels and find the one named 'general'"
# Codex will run: discord-cli channel list
# Then parse JSON to find the channel
```

For automated workflows, pipe discord-cli output to Codex:

```bash
discord-cli channel list | codex "Find the channel named 'general' and return its ID"
```

## General LLM Agent Integration

### Python Integration

```python
import subprocess
import json

def discord_cli(*args):
    """Run a discord-cli command and return parsed JSON."""
    result = subprocess.run(
        ["discord-cli"] + list(args),
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

# Example: List channels, find 'general', send a message
channels = discord_cli("channel", "list")
general = next(c for c in channels["data"] if c["name"] == "general")
discord_cli("message", "send", str(general["id"]), "--content", "Hello from AI agent!")
```

### Shell Script Integration

```bash
#!/bin/bash
# Get server info and save to file
discord-cli guild info > server_info.json

# List all members and filter for admins
discord-cli member list | jq '.data[] | select(.roles[] | contains("Admin"))'
```

### JSON Output Parsing

All commands return this structure:

```json
// Success
{"ok": true, "data": <result>}

// Error
{"ok": false, "error": {"type": "ConfigError", "message": "DISCORD_BOT_TOKEN not found"}}
```

Parse with `jq`:
```bash
# Get just the data array
discord-cli channel list | jq '.data'

# Get specific field
discord-cli guild info | jq '.data.name'

# Check for errors
discord-cli member info 999 | jq '.ok'
```

## Common Automation Patterns

### Server Setup Automation

```bash
# Create a complete server structure
CATEGORY_ID=$(discord-cli category create "Projects" | jq -r '.data.id')
discord-cli channel create "general" --type text --category $CATEGORY_ID
discord-cli channel create "voice" --type voice --category $CATEGORY_ID
ROLE_ID=$(discord-cli role create "Member" --mentionable | jq -r '.data.id')
```

### Moderation Workflow

```bash
# Find a member by name
MEMBER_ID=$(discord-cli search members --query "spammer" | jq -r '.data[0].id')

# Kick with reason
discord-cli member kick $MEMBER_ID --reason "Spam"

# Log the action
echo "$(date): Kicked user $MEMBER_ID for spam" >> moderation.log
```

### Message Export and Analysis

```bash
# Export channel history
discord-cli export channel 1234567890 --limit 1000 --format json > history.json

# Analyze with jq
cat history.json | jq '.data | length'  # Message count
cat history.json | jq '[.data[].author.name] | unique'  # Unique authors
```

## Best Practices

1. **Always check `ok` field**: `if ! data.ok; then handle_error(data.error); fi`
2. **Use `--human` for debugging**: Rich table output helps when debugging interactively
3. **Cache results**: `discord-cli channel list` is expensive — cache the output
4. **Handle rate limits**: discord.py handles them, but be aware of API limits
5. **Never log tokens**: Use environment variables, never hardcode in scripts
