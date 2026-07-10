#!/usr/bin/env python3
"""Fail a release when tag, package version, or changelog disagree."""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent


def fail(message: str) -> None:
    print(f"release metadata error: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]

    expected = sys.argv[1].removeprefix("v") if len(sys.argv) > 1 else version
    if expected != version:
        fail(f"tag {expected} does not match project version {version}")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    releases = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", changelog, flags=re.MULTILINE)
    if not releases or releases[0] != version:
        actual = releases[0] if releases else "missing"
        fail(f"latest changelog version {actual} does not match project version {version}")

    pending = re.search(
        r"^## \[Unreleased\]\s*(.*?)(?=^## \[)",
        changelog,
        flags=re.MULTILINE | re.DOTALL,
    )
    if pending and pending.group(1).strip():
        fail("CHANGELOG.md still has pending Unreleased entries")

    print(f"release metadata ok: {version}")


if __name__ == "__main__":
    main()
