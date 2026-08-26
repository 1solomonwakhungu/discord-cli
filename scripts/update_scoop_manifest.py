#!/usr/bin/env python3
"""Point the Scoop manifest at a published PyPI release.

The manifest carries a ``version``, a wheel ``url`` and that wheel's ``hash``.
Only the version can be derived by substitution, so semantic-release cannot own
this file the way it owns the other version-bearing files. Instead the release
workflow runs this script once the wheel is on PyPI and reads the real digest
back out of the API, which is the same digest Scoop will verify against.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PACKAGE = "discordcli-agents"
DEFAULT_MANIFEST = Path("packaging/scoop/discordcli-agents.json")
API = "https://pypi.org/pypi/{package}/{version}/json"

#: Returned when the requested version is older than the one already pinned.
#: Distinct from 1 so a re-publish of an old release can be skipped by the
#: workflow without being mistaken for a genuine failure.
EXIT_WOULD_DOWNGRADE = 3


def fetch_wheel(version: str, *, attempts: int = 10, delay: float = 15.0) -> dict:
    """Return the ``bdist_wheel`` entry PyPI published for ``version``.

    The version-pinned endpoint is used rather than the general one because the
    latter is CDN-cached and can serve a stale ``info.version`` for minutes
    after an upload.
    """
    url = API.format(package=PACKAGE, version=version)

    payload = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payload = json.load(response)
            break
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == attempts:
                raise SystemExit(f"could not read {url}: {error}") from error
            print(
                f"attempt {attempt}/{attempts} failed ({error}); retrying in {delay:.0f}s",
                file=sys.stderr,
            )
            time.sleep(delay)

    assert payload is not None

    wheels = [
        entry for entry in payload.get("urls", []) if entry.get("packagetype") == "bdist_wheel"
    ]
    if not wheels:
        raise SystemExit(f"{PACKAGE} {version} has no wheel on PyPI")
    if len(wheels) > 1:
        names = ", ".join(sorted(entry["filename"] for entry in wheels))
        raise SystemExit(
            f"{PACKAGE} {version} publishes multiple wheels ({names}); "
            "the Scoop manifest assumes a single pure-Python wheel"
        )

    wheel = wheels[0]
    expected = f"discordcli_agents-{version}-py3-none-any.whl"
    if wheel["filename"] != expected:
        raise SystemExit(
            f"expected wheel {expected} but PyPI published {wheel['filename']}; "
            "the manifest installer script builds the filename from $version "
            "and would no longer match"
        )
    return wheel


def release_sort_key(version: str) -> tuple:
    """Order plain ``X.Y.Z`` versions. Anything unusual sorts last."""
    parts = version.split(".")
    try:
        return (0, tuple(int(part) for part in parts))
    except ValueError:
        return (1, ())


def update_manifest(path: Path, version: str, url: str, sha256: str, *, force: bool) -> bool:
    """Rewrite the manifest in place. Returns True when the file changed."""
    original = path.read_text(encoding="utf-8")
    manifest = json.loads(original)

    current = manifest.get("version", "")
    if not force and current and release_sort_key(version) < release_sort_key(current):
        print(
            f"refusing to move the manifest from {current} back to {version}; "
            "re-publishing an old release must not downgrade what Scoop installs "
            "(pass --allow-downgrade if that really is the intent)",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_WOULD_DOWNGRADE)

    manifest["version"] = version
    manifest["url"] = url
    manifest["hash"] = sha256

    updated = json.dumps(manifest, indent=4) + "\n"
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="published version, for example 1.3.0")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--attempts",
        type=int,
        default=10,
        help="how many times to poll PyPI before giving up",
    )
    parser.add_argument(
        "--allow-downgrade",
        action="store_true",
        help="permit pointing the manifest at an older release than it holds",
    )
    args = parser.parse_args(argv)

    version = args.version.lstrip("v")
    wheel = fetch_wheel(version, attempts=args.attempts)
    sha256 = wheel["digests"]["sha256"]

    changed = update_manifest(
        args.manifest, version, wheel["url"], sha256, force=args.allow_downgrade
    )
    print(f"{args.manifest}: {'updated to' if changed else 'already at'} {version}")
    print(f"  url  {wheel['url']}")
    print(f"  hash {sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
