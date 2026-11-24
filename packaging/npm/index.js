#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const IS_WIN = process.platform === "win32";
const VENV_BIN = IS_WIN
  ? path.join(__dirname, ".venv", "Scripts", "discord-cli.exe")
  : path.join(__dirname, ".venv", "bin", "discord-cli");

const executable = fs.existsSync(VENV_BIN) ? VENV_BIN : "discord-cli";
const args = process.argv.slice(2);
const result = spawnSync(executable, args, { stdio: "inherit" });

if (result.error) {
  console.error(
    "Could not find the `discord-cli` command. Ensure discordcli-agents was installed " +
      "correctly (re-run `npm rebuild discordcli-agents` or install via `uv tool install discordcli-agents`)."
  );
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
