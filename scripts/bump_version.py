#!/usr/bin/env python3
"""
Automated semantic version bump based on conventional commits.

Bump rules (first match wins, evaluated across all commits since last tag):
  feat!: / fix!: / BREAKING CHANGE in body  → major
  feat:                                       → minor
  fix: / perf: / refactor: / build:          → patch

Ignored prefixes (do not trigger a bump on their own):
  chore: / docs: / style: / test: / ci:

If no bumpable commits exist since the last tag, exits cleanly with
BUMPED= (empty) so the CI job can skip the push step.

Prints one line to stdout: BUMPED=vX.Y.Z  or  BUMPED=
"""

import datetime
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BREAKING_RE = re.compile(r"^(feat|fix|refactor|perf)(\(.+\))?!:")
MINOR_RE    = re.compile(r"^feat(\(.+\))?:")
PATCH_RE    = re.compile(r"^(fix|perf|refactor|build)(\(.+\))?:")


def run(*cmd):
    return subprocess.check_output(cmd, text=True).strip()


def get_current_version() -> str:
    text = (ROOT / "backend/__init__.py").read_text()
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        raise RuntimeError("Could not find __version__ in backend/__init__.py")
    return m.group(1)


def get_last_tag() -> str | None:
    try:
        return run("git", "describe", "--tags", "--abbrev=0")
    except subprocess.CalledProcessError:
        return None


def commits_since(ref: str | None) -> list[str]:
    """Return list of full commit messages (subject + body) since ref."""
    fmt = "%s%n%b%n---END---"
    if ref:
        raw = run("git", "log", f"{ref}..HEAD", f"--format={fmt}")
    else:
        raw = run("git", "log", f"--format={fmt}")
    chunks = raw.split("---END---")
    return [c.strip() for c in chunks if c.strip()]


def determine_bump(messages: list[str]) -> str | None:
    """Return 'major', 'minor', 'patch', or None."""
    result = None
    for msg in messages:
        lines = msg.splitlines()
        subject = lines[0].strip() if lines else ""
        body    = "\n".join(lines[1:])

        if BREAKING_RE.match(subject) or "BREAKING CHANGE" in body:
            return "major"
        if MINOR_RE.match(subject):
            if result != "major":
                result = "minor"
        elif PATCH_RE.match(subject):
            if result not in ("major", "minor"):
                result = "patch"
    return result


def apply_bump(version: str, bump: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def update_files(old: str, new: str) -> None:
    # backend/__init__.py
    init = ROOT / "backend/__init__.py"
    init.write_text(init.read_text().replace(
        f'__version__ = "{old}"', f'__version__ = "{new}"'
    ))

    # frontend/package.json
    pkg = ROOT / "frontend/package.json"
    pkg.write_text(pkg.read_text().replace(
        f'"version": "{old}"', f'"version": "{new}"'
    ))

    # CHANGELOG.md — prepend a new section after the heading line
    today = datetime.date.today().isoformat()
    cl = ROOT / "CHANGELOG.md"
    content = cl.read_text()
    new_section = f"\n## [{new}] - {today}\n\nSee commit history for changes.\n"
    # Insert after the first line ("# Changelog")
    first_newline = content.index("\n")
    cl.write_text(content[: first_newline + 1] + new_section + content[first_newline + 1 :])


def main() -> None:
    # Skip if HEAD is already a version bump commit (prevents loops)
    head_subject = run("git", "log", "-1", "--format=%s")
    if head_subject.startswith("chore: bump version"):
        print("BUMPED=")
        return

    current = get_current_version()
    last_tag = get_last_tag()
    messages = commits_since(last_tag)
    bump = determine_bump(messages)

    if not bump:
        print("BUMPED=")
        return

    new_ver = apply_bump(current, bump)
    update_files(current, new_ver)
    print(f"BUMPED=v{new_ver}")


if __name__ == "__main__":
    main()
