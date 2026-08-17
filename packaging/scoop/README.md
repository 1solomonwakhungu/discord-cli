This folder contains a Scoop manifest (discordcli-agents.json) intended as a manual/local helper, not a published public bucket entry.

Why: There is no public `scoop` bucket maintained by this project in this repository. Do NOT assume `scoop install discordcli-agents` will work — that command requires the manifest to be in a public bucket (or a bucket name). Instead, to install the project use one of these reliable options:

- Install from PyPI (recommended):

  pip install discordcli-agents

- Use the raw Scoop manifest locally (manual install):

  # Download the raw manifest file from this repository
  curl -L -o discordcli-agents.json \
    https://raw.githubusercontent.com/1solomonwakhungu/discord-cli/main/packaging/scoop/discordcli-agents.json

  # Install from the local manifest (PowerShell/Windows):
  scoop install .\discordcli-agents.json

  # Or add to your own bucket and then `scoop install <bucket>/discordcli-agents`

Notes:
- This manifest references PyPI wheel files; it is provided as a convenience for packagers and for manual/local installs only.
- If you maintain a public Scoop bucket and want this package added, either open an issue in this repository or create a PR in your bucket pointing to this manifest. The project does not publish a public Scoop bucket by default.
