#!/usr/bin/env python3
"""Check relative links in Markdown files. No network.

    python3 scripts/check_links.py              check every *.md in the repository
    python3 scripts/check_links.py FILE ...     check only these files

For each [text](target) or [text]: target reference whose target is not a URL
(http, https, mailto), checks that the file or directory exists and that any
#anchor matches a heading in the target Markdown file (GitHub slug rules).

It also checks that every github.com URL that names this repository (in
Markdown files and in .github/*.yml) uses the right organisation. The expected
<org>/<repo> comes from `git remote get-url origin`, or EXPECTED_REPO if git
is not available.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_URL = "https://github.com/magicmarkets/magic-api"
EXPECTED_REPO = EXPECTED_URL.removeprefix("https://github.com/")
GITHUB_URL = re.compile(r"(?:https?://(?:www\.)?github\.com/|git@github\.com:)([\w.-]+)/([\w.-]+)", re.I)
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", ".pytest_cache"}

INLINE = re.compile(r"!?\[(?:[^\]\\]|\\.)*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$", re.M)
FENCE = re.compile(r"^(```|~~~).*?^\1", re.M | re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.M)
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.I)


def slugify(heading: str) -> str:
    """GitHub-style anchor for a heading."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # keep link text only
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    seen: dict[str, int] = {}
    out = set()
    for heading in HEADING.findall(text):
        slug = slugify(heading)
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        out.add(slug if n == 0 else f"{slug}-{n}")
    return out


def expected_repo(root: Path = ROOT) -> str:
    """<org>/<repo> of the origin remote, lowercase; EXPECTED_REPO without git."""
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=root, capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        url = ""
    match = GITHUB_URL.search(url)
    if not match:
        return EXPECTED_REPO
    return f"{match[1]}/{match[2].removesuffix('.git')}".lower()


def check_github_urls(path: Path, expected: str) -> list[str]:
    """github.com URLs that name this repository under another organisation."""
    org, repo = expected.split("/")
    problems = []
    text = path.read_text(encoding="utf-8")
    for match in GITHUB_URL.finditer(text):
        found_org, found_repo = match[1].lower(), match[2].lower().removesuffix(".git")
        if found_repo == repo and found_org != org:
            lineno = text.count("\n", 0, match.start()) + 1
            problems.append(f"{path}:{lineno}: wrong repository URL: {match[0]} (expected {expected})")
    return problems


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    body = INLINE_CODE.sub("", FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text))
    problems = []
    targets = [(m.start(), m.group(1)) for m in INLINE.finditer(body)]
    targets += [(m.start(), m.group(1)) for m in REFERENCE.finditer(body)]
    for offset, target in sorted(targets):
        if EXTERNAL.match(target):
            continue
        lineno = body.count("\n", 0, offset) + 1
        file_part, _, anchor = target.partition("#")
        dest = (path.parent / unquote(file_part)).resolve() if file_part else path
        if not dest.exists():
            problems.append(f"{path}:{lineno}: broken link: {target}")
        elif anchor and dest.suffix == ".md" and anchor.lower() not in anchors(dest):
            problems.append(f"{path}:{lineno}: missing anchor: {target}")
    return problems


def main(argv: list[str] | None = None, expected: str | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    files = [Path(a) for a in args] or [
        p for p in sorted(ROOT.rglob("*.md")) if not SKIP_DIRS.intersection(p.parts)
    ]
    expected = expected or expected_repo()
    extra = [] if args else sorted((ROOT / ".github").rglob("*.yml"))
    problems = [msg for f in files for msg in check_file(f)]
    problems += [msg for f in [*files, *extra] for msg in check_github_urls(f, expected)]
    for msg in problems:
        print(msg)
    print(f"checked {len(files)} Markdown file(s): {len(problems)} problem(s)", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
