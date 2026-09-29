"""The shared helpers in examples/_common.py, against a fake transport."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

import _common
from conftest import FAKE_KEY, FakeSocket, envelope, event, ok

# ---------------------------------------------------------------------- REST


def test_rest_unwraps_the_envelope_and_sends_the_key(fake_api):
    api = fake_api(lambda *a: ok({"balance": ["USDT", 12.5]}))
    assert _common.rest("GET", "/balance/") == {"balance": ["USDT", 12.5]}
    sent = api.calls[0]["headers"]
    assert sent["X-Api-Key"] == FAKE_KEY
    assert sent["User-Agent"].startswith("magicmarkets-magic-api-examples/")


def test_rest_raises_api_error_with_code(fake_api):
    fake_api(lambda *a: (401, {"status": "error", "code": "auth_error", "data": {"detail": "x"}}))
    with pytest.raises(_common.ApiError) as exc:
        _common.rest("GET", "/balance/")
    assert exc.value.http_status == 401
    assert exc.value.code == "auth_error"
    assert "401 auth_error" in str(exc.value)


def test_rest_reports_a_body_without_the_envelope(fake_api):
    fake_api(lambda *a: (503, {"detail": "Service unavailable"}))
    with pytest.raises(_common.ApiError) as exc:
        _common.rest("GET", "/events/")
    assert exc.value.code == "no_envelope"
    assert exc.value.data == {"detail": "Service unavailable"}


def test_rest_reports_a_non_json_body(fake_api):
    fake_api(lambda *a: (502, "<html>Bad gateway</html>"))
    with pytest.raises(_common.ApiError) as exc:
        _common.rest("GET", "/events/")
    assert exc.value.code == "no_envelope"


def test_missing_key_exits_with_a_hint(monkeypatch):
    monkeypatch.delenv("MAGIC_API_KEY")
    monkeypatch.delenv("MM_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="MAGIC_API_KEY"):
        _common.api_key()


# -------------------------------------------------------------------- paging


def test_list_events_pages_with_after(fake_api):
    pages = {
        None: [
            event("2026-10-01,1,2", "2026-10-01T12:00:00Z"),
            event("2026-10-01,3,4", "2026-10-01T13:00:00Z"),
        ],
        "fb,2026-10-01,3,4": [event("2026-10-01,5,6", "2026-10-01T14:00:00Z")],
    }
    api = fake_api(lambda m, p, params, j: ok(pages[params.get("after")]))
    events = _common.list_events(page_size=2, sport="fb")
    assert [e["event_id"] for e in events] == ["2026-10-01,1,2", "2026-10-01,3,4", "2026-10-01,5,6"]
    assert [c["params"].get("after") for c in api.calls] == [None, "fb,2026-10-01,3,4"]
    assert all(c["params"]["sport"] == "fb" and c["params"]["limit"] == 2 for c in api.calls)


def test_list_events_stops_on_an_empty_page(fake_api):
    api = fake_api(lambda *a: ok([]))
    assert _common.list_events() == []
    assert len(api.calls) == 1


def test_list_offers_names_at_most_20_events_per_request(fake_api):
    ids = [f"2026-10-01,{i},{i + 100}" for i in range(45)]
    api = fake_api(
        lambda m, p, params, j: ok([{"event_id": e, "bet_type": "for,h"} for e in params["event_id"]])
    )
    offers = _common.list_offers("fb", ids, market_type=["wdw"])
    assert len(offers) == 45
    assert [len(c["params"]["event_id"]) for c in api.calls] == [20, 20, 5]
    assert all(c["params"]["sport"] == "fb" and c["params"]["market_type"] == ["wdw"] for c in api.calls)


def test_list_offers_pages_each_group(fake_api):
    def handler(m, p, params, j):
        if params.get("after") is None:
            return ok([{"event_id": "e1", "bet_type": "for,a"}, {"event_id": "e1", "bet_type": "for,h"}])
        return ok([{"event_id": "e2", "bet_type": "for,d"}])

    api = fake_api(handler)
    offers = _common.list_offers("fb", ["e1", "e2"], page_size=2)
    assert len(offers) == 3
    assert api.calls[1]["params"]["after"] == "e1,for,h"


def test_list_orders_reads_every_page(fake_api):
    def handler(m, p, params, j):
        start = (params["page"] - 1) * params["page_size"]
        return ok([{"order_id": i} for i in range(start, min(start + params["page_size"], 7))])

    api = fake_api(handler)
    assert [o["order_id"] for o in _common.list_orders(page_size=3)] == list(range(7))
    assert [c["params"]["page"] for c in api.calls] == [1, 2, 3]


# --------------------------------------------------------------- event choice

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def test_upcoming_matches_skips_outrights_live_and_started_events():
    events = [
        {"event_type": "multirunner", "sport": "fb", "event_id": "o", "start_time": "2026-10-02T00:00:00Z"},
        event("live", "2026-10-01T13:00:00Z", ir_status="in_running"),
        event("stale", "2026-09-30T18:45:00Z"),  # started, but still says pre_event
        event("later", "2026-10-01T15:00:00Z"),
        event("soon", "2026-10-01T12:30:00Z"),
        event("tennis", "2026-10-01T12:10:00Z", sport="tennis"),
    ]
    assert [e["event_id"] for e in _common.upcoming_matches(events, now=NOW)] == ["tennis", "soon", "later"]
    assert _common.pick_match(events, "fb", now=NOW)["event_id"] == "soon"
    assert _common.pick_match(events[:3], now=NOW) is None


def test_label_handles_both_event_shapes():
    assert _common.label({"event_name": "A vs. B"}) == "A vs. B"
    assert _common.label({"home": "A", "away": "B"}) == "A v B"
    outright = {"event_type": "multirunner", "teams": [{"name": "X"}, {"name": "Y"}]}
    assert _common.label(outright) == "[outright] X, Y..."


def test_best_is_the_first_price_level():
    levels = [{"effective": {"price": 2.1}}, {"effective": {"price": 2.0}}]
    assert _common.best(levels) == {"price": 2.1}
    assert _common.best([]) is None


# ---------------------------------------------------------------------- ticks


@pytest.mark.parametrize(
    ("price", "tick"),
    [("1.01", "0.01"), ("2", "0.01"), ("2.02", "0.02"), ("3.5", "0.05"), ("7.2", "0.20"), ("15", "0.50")],
)
def test_tick_size(price, tick):
    assert _common.tick_size(price) == Decimal(tick)


@pytest.mark.parametrize(
    ("price", "direction", "snapped"),
    [
        ("7.15", "for", "7.20"),  # the example in the published docs
        ("7.15", "against", "7.00"),
        ("7.20", "for", "7.20"),  # already on tick
        ("2.01", "for", "2.02"),
        ("2.01", "against", "2.00"),
        ("1.995", "for", "2.00"),
        ("33", "for", "34"),
        ("33", "against", "32"),
        (1.555, "for", "1.56"),
    ],
)
def test_snap_limit_moves_to_the_first_tick_that_honours_the_limit(price, direction, snapped):
    assert _common.snap_limit(price, direction) == Decimal(snapped)


def test_snap_limit_rejects_bad_input():
    with pytest.raises(ValueError):
        _common.snap_limit("2.5", "back")
    with pytest.raises(ValueError):
        _common.snap_limit("1.001", "for")
    with pytest.raises(ValueError):
        _common.snap_limit("1001", "against")


# --------------------------------------------------------------------- stream


def test_frames_iterates_entries_and_skips_junk():
    ws = FakeSocket(
        [
            envelope(["event", {"event_id": "a"}], ["offer", {"bet_type": "for,h"}]),
            "not json",
            envelope([], "not a list", ["echo"]),
            envelope(["sync", {"session_id": "s"}]),
        ]
    )
    assert list(_common.frames(ws)) == [
        ("event", {"event_id": "a"}),
        ("offer", {"bet_type": "for,h"}),
        ("echo", None),
        ("sync", {"session_id": "s"}),
    ]


def test_sync_events_stops_at_sync():
    ws = FakeSocket(
        [
            envelope(["event", {"event_id": "a"}]),
            envelope(["event", {"event_id": "b"}], ["sync", {"session_id": "s"}], ["offer", {}]),
        ]
    )
    assert [e["event_id"] for e in _common.sync_events(ws)] == ["a", "b"]


def test_register_and_unregister_send_commands():
    ws = FakeSocket([])
    _common.register(ws, "fb", "2026-10-01,1,2")
    _common.unregister(ws, "fb", "2026-10-01,1,2")
    assert ws.sent == [
        ["register_event", "fb", "2026-10-01,1,2"],
        ["unregister_event", "fb", "2026-10-01,1,2"],
    ]


def test_open_stream_url_encodes_the_key(monkeypatch):
    seen = {}
    monkeypatch.setattr(_common, "connect", lambda url, **kw: seen.setdefault("url", url))
    _common.open_stream()
    assert seen["url"] == (
        "wss://magicmarkets.com/v2/stream?api_key=EXAMPLE-key%2Fwith%2Bodd%26chars%3D1&lang=en"
    )


def test_terminal_statuses_cover_the_documented_end_states():
    assert {"done", "failed", "partial_void", "full_void", "reconciled"} == _common.TERMINAL_STATUSES
    assert "open" not in _common.TERMINAL_STATUSES
    assert "pending" not in _common.TERMINAL_STATUSES
