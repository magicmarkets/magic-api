"""Read-only smoke tests against the real API. Excluded by default.

    MAGIC_API_KEY=... python -m pytest -m live

They read the published OpenAPI spec, list events and offers, and read the
balance. They never create a betslip, heartbeat or order.
"""

from __future__ import annotations

import os
import re

import pytest
import requests

import _common
from conftest import ROOT

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("MAGIC_API_KEY"), reason="needs MAGIC_API_KEY"),
]

OPENAPI = "https://magicmarkets.com/v2/openapi.yaml"


def test_key_is_accepted():
    assert "balance" in _common.verify_key()


def test_skill_index_matches_the_published_spec():
    spec = requests.get(OPENAPI, timeout=30, headers={"User-Agent": _common.USER_AGENT}).text
    published = set(re.findall(r"^  (/v2/\S+):$", spec, re.M))
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    index = skill[skill.index("## Endpoint index") :]
    documented = set(re.findall(r"`(?:GET|POST|DELETE|GET\|POST|GET\|DELETE) (/v2/[^`]+)`", index))
    assert published == documented


def test_events_and_offers_agree():
    matches = _common.upcoming_matches(_common.list_events(sport="fb", ir_status="pre_event"))
    if not matches:
        pytest.skip("no priced football match right now")
    offers = _common.list_offers("fb", [m["event_id"] for m in matches[:5]])
    assert offers, "priced events should have offers"
    for offer in offers:
        assert offer["price_list"], "markets with no stake are left out"
        prices = [level["effective"]["price"] for level in offer["price_list"]]
        assert prices == sorted(prices, reverse=True)
        for p in prices:
            assert _common.snap_limit(p, "for") == _common.snap_limit(p, "against"), "feed prices are on tick"


def test_stream_sync_matches_rest_discovery():
    with _common.open_stream() as ws:
        streamed = {(e["sport"], e["event_id"]) for e in _common.sync_events(ws)}
    listed = {(e["sport"], e["event_id"]) for e in _common.list_events()}
    # The two reads are a few seconds apart, so allow a little churn.
    assert len(streamed ^ listed) <= max(20, len(listed) // 50)
