# Contributing

Thanks for helping improve discord-cli.

## Development setup

Use Python 3.9 or newer, then install the project and development dependencies:

```bash
git clone https://github.com/1solomonwakhungu/discord-cli.git
cd discord-cli
python -m pip install -e ".[dev]"
```

Run the checks before opening a pull request:

```bash
ruff check src/
ruff format --check src/
python -m pytest tests/
```

If the repository has no tests for your change yet, run the import smoke test:

```bash
python -c "import discord_cli; print(discord_cli.__version__)"
```

## Pull requests

Keep pull requests focused, include tests when practical, and describe user-visible changes. Do not commit bot tokens, `.env` files, or other credentials.

Use Conventional Commit-style subjects:

- `feat:` for a new feature
- `fix:` for a bug fix
- `docs:` for documentation-only changes
- `chore:` for maintenance
- `refactor:` for code restructuring without behavior changes
