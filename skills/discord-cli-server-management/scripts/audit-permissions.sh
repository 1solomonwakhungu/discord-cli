#!/usr/bin/env bash
# Read-only guild permission audit using discord-cli safety guardrails.
set -euo pipefail

GUILD_ARG=()
if [[ -n "${1:-}" ]]; then
  GUILD_ARG=(--guild "$1")
fi

CHANNELS=$(discord-cli --policy read-only --no-plugins --quiet "${GUILD_ARG[@]}" channel list)
for ch in $CHANNELS; do
  discord-cli --policy read-only --no-plugins --compact --string-ids "${GUILD_ARG[@]}" \
    permissions list --channel "$ch"
done
