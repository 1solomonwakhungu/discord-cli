#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const pkg = require("./package.json");
const PACKAGE_SPEC = `${pkg.name}==${pkg.version}`;
const VENV_DIR = path.join(__dirname, ".venv");
const IS_WIN = process.platform === "win32";
const VENV_PYTHON = IS_WIN
  ? path.join(VENV_DIR, "Scripts", "python.exe")
  : path.join(VENV_DIR, "bin", "python");

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit" });
  return result.status === 0;
}

function installIntoVenv(pythonCommand) {
  if (!fs.existsSync(VENV_PYTHON)) {
    if (!run(pythonCommand, ["-m", "venv", VENV_DIR])) {
      return false;
    }
  }
  return run(VENV_PYTHON, ["-m", "pip", "install", "--no-cache-dir", PACKAGE_SPEC]);
}

const candidates = IS_WIN ? ["python", "py"] : ["python3", "python"];

let installed = false;
for (const candidate of candidates) {
  if (installIntoVenv(candidate)) {
    installed = true;
    break;
  }
}

if (!installed) {
  console.error(
    `Failed to install ${PACKAGE_SPEC} into isolated virtualenv ${VENV_DIR}. ` +
      `Please ensure Python 3.9+ with venv and pip are available, ` +
      `or install directly via: uv tool install ${pkg.name}`
  );
  process.exit(1);
}
