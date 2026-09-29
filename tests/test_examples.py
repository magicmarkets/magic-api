"""The example scripts: dry runs never write, and errors read as one line."""

from __future__ import annotations

import py_compile
import re

import pytest

import _common
from conftest import EXAMPLES, ROOT, FakeSocket, envelope, event, load_example, ok

SCRIPTS = sorted(p.name for p in EXAMPLES.glob("[0-9][0-9]-*.py"))

FUTURE = "2099-01-01T12:00:00Z"
MATCH = event("2099-01-01,1,2", FUTURE)
OFFER = {
    "sport": "fb",
    "event_id": MATCH["event_id"],
    "bet_type": "for,h",
    "market_type": "wdw",
    "price_list": [{"effective": {"price": 2.1, "min": None, "max": ["USDT", 50.0]}}],
}


def test_there_are_examples():
    assert len(SCRIPTS) >= 6


@pytest.mark.parametrize("name", SCRIPTS)
def test_each_example_compiles(name):
    py_compile.compile(str(EXAMPLES / name), doraise=True)


@pytest.mark.parametrize("name", SCRIPTS)
def test_each_example_has_usage_in_its_docstring(name):
    module = load_example(name)
    assert "Usage:" in (module.__doc__ or "")


def test_examples_readme_lists_every_script_and_nothing_else():
    readme = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"\(([0-9][0-9]-[\w-]+\.py)\)", readme))
    assert listed == set(SCRIPTS)


def stream_with_offer():
    return FakeSocket(
        [
            envelope(["event", MATCH], ["sync", {"session_id": "s"}]),
            envelope(["offer", OFFER], ["response", {"status": "ok", "data": None}]),
        ]
    )


def test_market_making_dry_run_only_reads(fake_api, monkeypatch, capsys):
    api = fake_api(lambda *a: ok({"balance": ["USDT", 10.0]}))
    mm = load_example("03-market-making.py")
    monkeypatch.setattr(mm, "open_stream", stream_with_offer)
    mm.main(sport_filter="fb", live=False, stake_amount=1.0)
    assert api.paths("POST") == [] and api.paths("DELETE") == []
    assert "DRY RUN" in capsys.readouterr().out


def test_market_making_skips_an_offer_outside_the_price_range(fake_api, monkeypatch):
    fake_api(lambda *a: ok({}))
    mm = load_example("03-market-making.py")
    far = {**OFFER, "price_list": [{"effective": {"price": 12.0, "min": None, "max": ["USDT", 5.0]}}]}
    ws = FakeSocket([envelope(["offer", far])])
    assert mm.wait_for_offer(ws, timeout=1) is None


def test_bulk_close_dry_run_only_reads(fake_api, capsys):
    def handler(method, path, params, body):
        if path == "/orders/":
            return ok([{"order_id": 1, "closed": False, "sport": "fb"}, {"order_id": 2, "closed": True}])
        return ok({})

    api = fake_api(handler)
    load_example("04-bulk-close.py").main(sport_filter=None, live=False, use_close_all=False)
    assert api.paths("POST") == []
    out = capsys.readouterr().out
    assert "1 open order(s)" in out and "DRY RUN" in out


def test_bulk_close_all_dry_run_sends_nothing(fake_api):
    api = fake_api(lambda *a: ok({}))
    load_example("04-bulk-close.py").main(sport_filter=None, live=False, use_close_all=True)
    assert api.paths("POST") == []


def test_bulk_close_live_names_each_open_order(fake_api):
    def handler(method, path, params, body):
        if path == "/orders/":
            return ok([{"order_id": 1, "closed": False}, {"order_id": 3, "closed": False}])
        return ok({})

    api = fake_api(handler)
    load_example("04-bulk-close.py").main(sport_filter=None, live=True, use_close_all=False)
    closes = [c for c in api.calls if c["method"] == "POST"]
    assert [(c["path"], c["json"]) for c in closes] == [("/orders/close_many/", {"order_ids": [1, 3]})]


def test_rest_offers_example_reads_events_then_offers(fake_api, capsys):
    def handler(method, path, params, body):
        if path == "/events/":
            return ok([MATCH])
        if path == "/offers/":
            return ok([OFFER])
        return ok({})

    api = fake_api(handler)
    load_example("05-rest-offers.py").main(sport="fb", count=5, all_markets=False)
    offers_call = next(c for c in api.calls if c["path"] == "/offers/")
    assert offers_call["params"]["market_type"] == ["wdw", "ah", "ou", "ml"]
    assert "for,h" in capsys.readouterr().out


def test_run_cli_turns_an_api_error_into_one_line():
    def boom():
        raise _common.ApiError("GET", "/balance/", 401, "auth_error", {"detail": "x"})

    with pytest.raises(SystemExit) as exc:
        _common.run_cli(boom)
    assert str(exc.value).startswith("GET /balance/ failed [401 auth_error]")


def test_run_cli_reports_a_refused_handshake():
    from websockets.datastructures import Headers
    from websockets.exceptions import InvalidStatus
    from websockets.http11 import Response

    def refused():
        raise InvalidStatus(Response(401, "Unauthorized", Headers(), b"auth_rejected"))

    with pytest.raises(SystemExit) as exc:
        _common.run_cli(refused)
    assert str(exc.value) == "stream handshake refused: HTTP 401 auth_rejected"


def test_no_example_or_reference_names_a_retired_endpoint():
    # SKILL.md names them once, in a warning, so a model with old knowledge avoids them.
    retired = ("magic-" + "cpricefeed", "pro." + "magicmarkets.com", "/web/" + "offerhist")
    files = [*EXAMPLES.glob("*.py"), *(ROOT / "references").glob("*.md")]
    for path in files:
        text = path.read_text(encoding="utf-8")
        for name in retired:
            assert name not in text, f"{path.name} names {name}"
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert all(skill.count(name) == 1 for name in retired)
