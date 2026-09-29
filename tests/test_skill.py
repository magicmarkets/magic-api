"""SKILL.md: the frontmatter a Claude host reads, and the files it points to."""

from __future__ import annotations

import re

from conftest import ROOT

SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")


def frontmatter() -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", SKILL, re.S)
    assert match, "SKILL.md must start with a --- frontmatter block"
    fields, key = {}, None
    for line in match.group(1).splitlines():
        if re.match(r"^[a-z_]+:", line):
            key, _, value = line.partition(":")
            fields[key] = value.strip().removeprefix(">").strip()
        elif key:
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return fields


def test_frontmatter_name_matches_the_install_folder():
    assert frontmatter()["name"] == "magicmarkets-magic-api"


def test_description_is_within_the_host_limit():
    description = frontmatter()["description"]
    assert 100 < len(description) <= 1024


def test_description_names_the_market_data_endpoints():
    description = frontmatter()["description"]
    assert "/v2/events/" in description and "/v2/offers/" in description


def test_every_endpoint_in_the_index_is_documented_in_rest_md():
    index = SKILL[SKILL.index("## Endpoint index") :]
    rest_md = (ROOT / "references" / "rest.md").read_text(encoding="utf-8")
    paths = set(re.findall(r"`(?:GET|POST|DELETE|GET\|POST|GET\|DELETE) (/v2/[^`]+)`", index))
    assert len(paths) >= 18
    for path in paths:
        assert path.split("{")[0].rstrip("/") in rest_md, path
