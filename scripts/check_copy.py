#!/usr/bin/env python3
"""Fail on copy-rule violations in docs, code and config.

    python3 scripts/check_copy.py              scan the whole repository
    python3 scripts/check_copy.py FILE_OR_DIR  scan only these paths

Scans *.md, *.py, *.mjs, *.json, *.yml, *.yaml, *.toml, *.txt and Makefile.
Reports file:line for:

- em dash (U+2014) and en dash (U+2013), and their HTML entities
- emoji and pictographic symbols (the arrows U+2191 and U+2193 are allowed)
- the brand written as two words (it is one word). The GitHub organisation
  slug in a github.com URL is allowed.

The two-word brand pattern is assembled from pieces so this file passes its own check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUFFIXES = {".md", ".py", ".mjs", ".json", ".yml", ".yaml", ".toml", ".txt"}
NAMES = {"Makefile"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".ruff_cache"}

EMOJI = (
    "\U0001f000-\U0001faff"  # pictographs, emoticons, transport, flags, supplemental symbols
    "\u2600-\u27bf"  # miscellaneous symbols and dingbats (includes check marks)
    "\u2b00-\u2bff"  # miscellaneous symbols and arrows (stars, large squares)
    "\u231a\u231b\u23e9-\u23f3\u23f8-\u23fa"  # watch, hourglass, media controls
    "\u3030\u303d\u3297\u3299"
    "\ufe0f\u200d\u20e3"  # emoji variation selector, zero-width joiner, keycap
)

BANNED: list[tuple[str, re.Pattern[str]]] = [
    ("em dash", re.compile("\u2014|&" + "mdash;")),
    ("en dash", re.compile("\u2013|&" + "ndash;")),
    ("emoji", re.compile(f"[{EMOJI}]")),
    ("brand is one word: MagicMarkets", re.compile("magic" + r"[\s_-]+" + "markets", re.I)),
]

# The organisation slug is allowed as a path segment right after github.com
# (https://github.com/<org>/..., git@github.com:<org>/...).
URL_SLUG_PREFIX = re.compile(r"github\.com[/:]$", re.I)


def iter_files(paths: list[Path]):
    for path in paths:
        if path.is_file():
            yield path
        elif path.is_dir():
            for p in sorted(path.rglob("*")):
                wanted = p.suffix in SUFFIXES or p.name in NAMES
                if p.is_file() and wanted and not SKIP_DIRS.intersection(p.parts):
                    yield p


def check_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        return [f"{path}: cannot read as UTF-8 ({exc})"]
    found = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for label, pattern in BANNED:
            for match in pattern.finditer(line):
                if label.startswith("brand") and URL_SLUG_PREFIX.search(line[: match.start()]):
                    continue  # the GitHub organisation slug in a URL
                found.append(f"{path}:{lineno}: {label}: {match.group(0)!r}")
                break
    return found


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    paths = [Path(a) for a in args] or [ROOT]
    missing = [p for p in paths if not p.exists()]
    for p in missing:
        print(f"no such file or directory: {p}", file=sys.stderr)
    problems = [msg for f in iter_files(paths) for msg in check_file(f)]
    for msg in problems:
        print(msg)
    if problems:
        print(f"{len(problems)} copy-rule violation(s)", file=sys.stderr)
    return 1 if problems or missing else 0


if __name__ == "__main__":
    sys.exit(main())
