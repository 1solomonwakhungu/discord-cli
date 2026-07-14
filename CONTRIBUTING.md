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

## Pre-commit hooks

This project uses [pre-commit](https://pre-commit.dev/) to enforce code quality
before commits are made. Install it once after cloning:

```bash
pip install pre-commit
pre-commit install
```

This runs `ruff` (lint + format), trailing-whitespace checks, end-of-file fixers,
and YAML/TOML validation on every commit.

## Pull requests

Keep pull requests focused, include tests when practical, and describe user-visible changes. Do not commit bot tokens, `.env` files, or other credentials.

Use Conventional Commits (required for automated releases):

- `feat:` for a new feature (triggers minor release)
- `fix:` for a bug fix (triggers patch release)
- `docs:` for documentation-only changes
- `chore:` for maintenance
- `refactor:` for code restructuring without behavior changes
- `test:` for test additions
- `ci:` for CI/CD changes
- `perf:` for performance improvements
- `style:` for formatting only
- `build:` for build system changes

**Breaking changes**: Use `!` after the type, e.g., `feat!: remove deprecated API`
or include `BREAKING CHANGE:` in the commit footer.

See [RELEASING.md](RELEASING.md) for how commits trigger automated releases.

### Branch naming

- `feat/description` — new features
- `fix/description` — bug fixes
- `docs/description` — documentation
- `chore/description` — maintenance tasks

### Code style

- Line length: 100 characters (enforced by ruff)
- Target Python version: 3.9+
- Imports sorted with ruff (isort-compatible)
- Type hints encouraged on all public functions

### Testing

Write tests for new features in `tests/` mirroring the `src/` structure. Run:

```bash
python -m pytest tests/ -v --cov=discord_cli --cov-report=term-missing
```

Coverage threshold is 80%. All tests must pass offline (no real Discord token needed).
