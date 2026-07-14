# Releasing discord-cli

This document describes the release process for maintainers.

## Automated Releases (python-semantic-release)

Releases are **fully automated** via [python-semantic-release](https://python-semantic-release.readthedocs.io/).
The release workflow (`.github/workflows/release.yml`) triggers on every push to `main`.

### How It Works

1. **CI gate**: Lint and tests run first. If they fail, no release happens.
2. **Version computation**: `python-semantic-release` analyzes commits since the last release tag using the Angular commit parser.
3. **Version bump**: Based on commit types:
   - `feat:` → minor version bump (0.1.0 → 0.2.0)
   - `fix:` → patch version bump (0.1.0 → 0.1.1)
   - `BREAKING CHANGE` or `feat!:` → major version bump (0.1.0 → 1.0.0)
   - `chore:`, `docs:`, `test:`, `ci:`, `style:`, `refactor:` → no release (idempotent)
4. **Changelog**: `CHANGELOG.md` is automatically updated with the new version's changes.
5. **Git tag**: A tag `v{version}` is created and pushed.
6. **Build**: Source and wheel distributions are built.
7. **PyPI publish**: The package is published to PyPI via OIDC Trusted Publishing (no API token needed).
8. **GitHub Release**: A release is created with the changelog as notes and distribution artifacts attached.

### Conventional Commits

All commits MUST follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat:` — new feature (triggers minor release)
- `fix:` — bug fix (triggers patch release)
- `docs:` — documentation only (no release)
- `chore:` — maintenance (no release)
- `refactor:` — code restructuring (no release)
- `test:` — test additions (no release)
- `ci:` — CI/CD changes (no release)
- `perf:` — performance improvement (triggers patch release)
- `style:` — formatting only (no release)
- `build:` — build system changes (no release)

**Breaking changes**: Use `feat!:` or `fix!:` or add `BREAKING CHANGE:` in the footer.

### Idempotency

If a push to main contains only non-releasable commits (e.g., `chore:`, `docs:`, `test:`), no release is created. The workflow exits successfully without publishing anything.

## Manual Release (Fallback)

If the automated workflow fails, you can trigger a manual release:

1. Ensure main is green (CI passes).
2. Create and push a tag manually:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
3. The tag-triggered release will build and publish.

## Semantic Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.x.x): Breaking changes / API redesign
- **MINOR** (0.x.0): New features, backward-compatible
- **PATCH** (0.0.x): Bug fixes, backward-compatible

## Pre-releases

For pre-release versions, use suffixes in the version:

```bash
# The automated workflow handles pre-releases if commits contain pre-release markers
# For manual pre-releases:
git tag v0.2.0-rc.1
git push origin v0.2.0-rc.1
```

## Rollback

If a release is broken:

1. **Yank from PyPI**: Visit https://pypi.org/manage/project/discordcli-agents/releases/ and yank the version
2. **Fix the issue** with a `fix:` commit on main
3. The next push to main will automatically create a patch release

## PyPI Trusted Publishing

This project uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC-based).
No API tokens are stored as secrets. The workflow authenticates using the GitHub Actions
OIDC token, which PyPI trusts based on the repository configuration.

To modify trusted publisher settings, visit:
https://pypi.org/manage/project/discordcli-agents/settings/publishing/

**Required trusted publisher configuration:**
- PyPI Project Name: `discordcli-agents`
- Owner: `1solomonwakhungu`
- Repository: `discord-cli`
- Workflow filename: `release.yml`
- Environment: (leave empty or set to `pypi`)
