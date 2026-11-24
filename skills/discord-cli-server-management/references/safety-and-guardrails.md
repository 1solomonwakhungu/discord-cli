# Safety Policies, Prompt-Injection Defense, and Audit Trails

## Monotonic Policy Ceilings

Operators can lock down autonomous agents using environment variables that CLI flags can **only tighten, never widen**:

| Env Variable | Purpose |
|---|---|
| `DISCORD_CLI_POLICY` | Ceiling: `read-only`, `allow-write`, or `allow-destructive` |
| `DISCORD_CLI_ALLOW_GUILDS` | Comma-separated allowlist of guild snowflake IDs (fail-closed) |
| `DISCORD_CLI_ALLOW_CHANNELS` | Comma-separated allowlist of channel snowflake IDs |
| `DISCORD_CLI_ALLOW_GROUPS` | Comma-separated allowlist of command groups (e.g. `channel,message,audit`) |
| `DISCORD_CLI_MAX_MUTATIONS` | Maximum bulk deletions allowed (e.g. `message purge --limit`) |
| `DISCORD_CLI_REQUIRE_CONFIRM=1` | Require `--confirm-token` (from `--dry-run`) or `--yes` for `destructive` commands |
| `DISCORD_CLI_AUDIT_LOG` | Path to append compact JSONL invocation records (never writes tokens) |

Policy denials exit immediately with code `6` (`POLICY_DENIED`) before opening any Discord connection.

## Two-Step Confirmation Flow

```bash
# Step 1: Preview destructive action and obtain deterministic confirm_token
TOKEN=$(discord-cli --dry-run channel delete "#old-temp" | jq -r '.data.confirm_token')

# Step 2: Execute with the bound confirmation token
discord-cli --confirm-token "$TOKEN" --reason "Approved cleanup" channel delete "#old-temp"
```

## Prompt-Injection & Secret Defense

- Pass `--untrusted-envelope` (`DISCORD_CLI_UNTRUSTED_ENVELOPE=1`) when reading messages, topics, usernames, or audit logs into an LLM context. Each call generates a fresh cryptographic 64-bit nonce tag (`<untrusted_dcli_<nonce>>...</untrusted_dcli_<nonce>>`) and neutralizes spoofed tags inside user text.
- Pass `--redact-pii` (`DISCORD_CLI_REDACT_PII=1`) to scrub emails, Discord bot tokens, OpenAI/Anthropic keys, GitHub tokens, JWTs, and webhook URLs.

## Semantic Exit Codes

Every error payload includes `error.category`, `error.exit_code`, `error.retryable`, `error.recovery_hint`, and optional `error.suggested_command`. Pass `--semantic-exit-codes` (`DISCORD_CLI_SEMANTIC_EXIT_CODES=1`) to return the semantic code directly from the process:

| Code | Category |
|---|---|
| `0` | Success / `--dry-run` |
| `1` | `RUNTIME_ERROR` |
| `2` | `USAGE_ERROR` |
| `3` | `AUTH_OR_CONFIG` |
| `4` | `NOT_FOUND` / `AMBIGUOUS_SELECTOR` |
| `5` | `PERMISSION_DENIED` |
| `6` | `POLICY_DENIED` |
| `7` | `RATE_LIMITED` (`retryable: true`) |
