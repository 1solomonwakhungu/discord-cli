#!/usr/bin/env node
"use strict";

const { spawnSync } = require("child_process");

const args = process.argv.slice(2);
const result = spawnSync("discord-cli", args, { stdio: "inherit" });

if (result.error) {
  console.error(
    "Could not find the `discord-cli` command. Ensure discordcli-agents was installed " +
      "correctly via pip (pip install discordcli-agents) and that its install location is on your PATH."
  );
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
