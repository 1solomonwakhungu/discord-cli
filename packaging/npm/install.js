#!/usr/bin/env node
"use strict";

const { spawnSync } = require("child_process");

const PACKAGE = "discordcli-agents";

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit" });
  return result.status === 0;
}

function pipInstall(pythonCommand) {
  return run(pythonCommand, ["-m", "pip", "install", "--upgrade", PACKAGE]);
}

const candidates = process.platform === "win32" ? ["python", "py"] : ["python3", "python"];

let installed = false;
for (const candidate of candidates) {
  if (pipInstall(candidate)) {
    installed = true;
    break;
  }
}

if (!installed) {
  console.error(
    `Failed to install ${PACKAGE} via pip. Please ensure Python 3.9+ and pip are installed, ` +
      `then run: pip install ${PACKAGE}`
  );
  process.exit(1);
}
