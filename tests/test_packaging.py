"""Guards for the Scoop manifest.

The manifest is refreshed by the release workflow after a PyPI publish, so it
deliberately lags ``__version__`` between the release commit and the follow-up
manifest commit. These tests therefore assert internal consistency rather than
agreement with ``__version__``, which would red-light CI during that window.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "packaging" / "scoop" / "discordcli-agents.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


class TestScoopManifest:
    def test_manifest_exists_and_parses(self, manifest):
        assert manifest["version"]

    def test_version_is_a_release_number(self, manifest):
        assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])

    def test_url_matches_the_pinned_version(self, manifest):
        """A stale url next to a fresh version would install the wrong wheel."""
        expected = f"discordcli_agents-{manifest['version']}-py3-none-any.whl"
        assert manifest["url"].endswith(expected), (
            f"url points at {manifest['url'].rsplit('/', 1)[-1]} but version is "
            f"{manifest['version']}; regenerate with scripts/update_scoop_manifest.py"
        )

    def test_hash_is_a_sha256(self, manifest):
        assert re.fullmatch(r"[0-9a-f]{64}", manifest["hash"])

    def test_installer_derives_the_filename_from_version(self, manifest):
        """Hardcoding the version here silently breaks every later release.

        Scoop expands ``$version`` in the installer script via PowerShell's
        dynamic scoping, so the wheel name must be templated, not literal.
        """
        script = " ".join(manifest["installer"]["script"])
        assert "${version}" in script
        assert manifest["version"] not in script, (
            "installer script hardcodes the version; use ${version} so the "
            "wheel name follows the manifest automatically"
        )

    def test_autoupdate_url_is_templated(self, manifest):
        assert "$version" in manifest["autoupdate"]["url"]

    def test_checkver_tracks_pypi(self, manifest):
        assert manifest["checkver"]["url"].startswith("https://pypi.org/pypi/")
