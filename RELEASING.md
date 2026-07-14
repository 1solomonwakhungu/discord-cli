# Releasing discord-cli

This document describes the release process for maintainers.

## Automated Releases (Tag-triggered)

Releases are automated via GitHub Actions. The release workflow (`.github/workflows/release.yml`) triggers when a tag matching `v*` is pushed.

### Steps to Release

1. **Ensure main is green**: Verify CI passes on the `main` branch.

2. **Update version** in `src/discord_cli/__init__.py`:
   ```python
   __version__ = "0.2.0"  # Follow semantic versioning
   ```

3. **Update CHANGELOG.md** with the changes for this release.

4. **Commit and push**:
   ```bash
   git add -A
   git commit -m "chore: bump version to 0.2.0"
   git push origin main
   ```

5. **Create and push a tag**:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

6. **The release workflow will**:
   - Run lint checks
   - Run tests
   - Build source and wheel distributions
   - Publish to PyPI (via OIDC trusted publishing -- no API token needed)
   - Create a GitHub Release with the CHANGELOG as release notes

7. **Verify**: Check that the package appears on [PyPI](https://pypi.org/project/discordcli-agents/) and the GitHub Release is created.

## Semantic Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.x.x): Breaking changes / API redesign
- **MINOR** (0.x.0): New features, backward-compatible
- **PATCH** (0.0.x): Bug fixes, backward-compatible

## Pre-releases

For pre-release versions, use suffixes:

```bash
git tag v0.2.0-rc.1
git push origin v0.2.0-rc.1
```

The GitHub Release will be marked as a pre-release.

## Rollback

If a release is broken:

1. **Yank from PyPI**: `python -m twine yank discordcli-agents==0.2.0` (requires API token)
2. **Fix the issue** on main
3. **Release a patch**: Bump to `0.2.1` and tag

## PyPI Trusted Publishing

This project uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC-based).
No API tokens are stored as secrets. The workflow authenticates using the GitHub Actions
OIDC token, which PyPI trusts based on the repository configuration.

To modify trusted publisher settings, visit:
https://pypi.org/manage/project/discordcli-agents/settings/publishing/
