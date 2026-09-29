"""Shared helpers for the MagicMarkets examples.

REST  : https://magicmarkets.com/v2/
Stream: wss://magicmarkets.com/v2/stream?api_key=<key>

Requires:  pip install -r requirements.txt
Env:       export MAGIC_API_KEY=...
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from urllib.parse import quote

import requests
from websockets.sync.client import connect

API = os.environ.get("MAGIC_API_URL", "https://magicmarkets.com/v2")
WS = os.environ.get("MAGIC_WS_URL", "wss://magicmarkets.com/v2/stream")
USER_AGENT = "magicmarkets-magic-api-examples/1.0"

# An order stops changing once it reaches one of these. `done` means filled,
# not settled: `profit_loss` is final only after the event.
TERMINAL_STATUSES = frozenset({"done", "failed", "partial_void", "full_void", "reconciled"})

# GET /v2/offers/ accepts up to 20 events in one request.
OFFERS_EVENTS_PER_REQUEST = 20

# (upper bound of the band, tick). Bounds are exact decimal prices, and each
# bound is a whole number of ticks in both bands next to it.
TICKS = (
    (Decimal("2"), Decimal("0.01")),
    (Decimal("3"), Decimal("0.02")),
    (Decimal("4"), Decimal("0.05")),
    (Decimal("6"), Decimal("0.10")),
    (Decimal("10"), Decimal("0.20")),
    (Decimal("20"), Decimal("0.50")),
    (Decimal("30"), Decimal("1")),
    (Decimal("50"), Decimal("2")),
    (Decimal("100"), Decimal("5")),
    (Decimal("1000"), Decimal("10")),
)
MIN_PRICE, MAX_PRICE = Decimal("1.01"), Decimal("1000")


def api_key() -> str:
    key = os.environ.get("MAGIC_API_KEY") or os.environ.get("MM_API_KEY")
    if not key:
        sys.exit("Set MAGIC_API_KEY (Settings -> API on magicmarkets.com)")
    return key


def headers() -> dict:
    return {"X-Api-Key": api_key(), "Content-Type": "application/json", "User-Agent": USER_AGENT}


class ApiError(Exception):
    """A REST call returned the error envelope, or no envelope at all."""

    def __init__(self, method: str, path: str, http_status: int, code: str, data):
        self.method, self.path, self.http_status, self.code, self.data = method, path, http_status, code, data
        detail = json.dumps(data, default=str)[:300]
        super().__init__(f"{method} {path} failed [{http_status} {code}]: {detail}")


def rest(method: str, path: str, **kw):
    """Call the REST API and unwrap the envelope. Raises ApiError on error.

    `code` is `no_envelope` when the body is not the API envelope, for
    example the 503 `{"detail": "Service unavailable"}` body.
    """
    r = requests.request(method, f"{API}{path}", headers=headers(), timeout=30, **kw)
    try:
        body = r.json()
    except ValueError:
        raise ApiError(method, path, r.status_code, "no_envelope", r.text[:200]) from None

    if not isinstance(body, dict) or body.get("status") != "ok":
        body = body if isinstance(body, dict) else {}
        raise ApiError(method, path, r.status_code, body.get("code", "no_envelope"), body.get("data", body))
    return body.get("data")


def verify_key():
    """Check the key over REST before opening a socket.

    A refused WebSocket upgrade surfaces as a handshake error. This turns a
    bad key into a clear `401 auth_error` first.
    """
    return rest("GET", "/balance/")


# ---------------------------------------------------------------- market data


def list_events(page_size: int = 500, **filters) -> list[dict]:
    """Every event that currently has prices, from GET /v2/events/.

    Filters are the query parameters of the endpoint: sport, competition_id,
    event_id, ir_status, start_time_from, start_time_to, lang. A list value
    is sent as a repeated parameter. `event_id` and `competition_id` need
    `sport`. Pages until a page comes back shorter than `page_size`.
    """
    events, after = [], None
    while True:
        params = {**filters, "limit": page_size}
        if after:
            params["after"] = after
        page = rest("GET", "/events/", params=params) or []
        events.extend(page)
        if len(page) < page_size:
            return events
        after = f"{page[-1]['sport']},{page[-1]['event_id']}"


def list_offers(sport: str, event_ids: list[str], page_size: int = 500, **filters) -> list[dict]:
    """Offers for the named events, from GET /v2/offers/.

    Sends the events in groups of 20, the most one request can name, and
    pages each group. Filters: bet_type, market_type, min_liquidity. The
    reply can be about 4 seconds behind the stream.
    """
    offers = []
    for i in range(0, len(event_ids), OFFERS_EVENTS_PER_REQUEST):
        group, after = event_ids[i : i + OFFERS_EVENTS_PER_REQUEST], None
        while True:
            params = {**filters, "sport": sport, "event_id": group, "limit": page_size}
            if after:
                params["after"] = after
            page = rest("GET", "/offers/", params=params) or []
            offers.extend(page)
            if len(page) < page_size:
                break
            after = f"{page[-1]['event_id']},{page[-1]['bet_type']}"
    return offers


def list_orders(page_size: int = 100, **filters) -> list[dict]:
    """Every order that matches the filters, from GET /v2/orders/.

    The endpoint pages with `page` and `page_size` (25 by default), so a
    single call can miss orders. Filters: status, sport, event_id,
    order_type, date_from, date_to, search.
    """
    orders, page_no = [], 1
    while True:
        page = rest("GET", "/orders/", params={**filters, "page": page_no, "page_size": page_size}) or []
        orders.extend(page)
        if len(page) < page_size:
            return orders
        page_no += 1


def upcoming_matches(events: list[dict], sport: str | None = None, now: datetime | None = None) -> list[dict]:
    """`normal` events that have not started, soonest first, optionally for one sport.

    A demo that takes events[0] often lands on a season-long outright. This
    also checks `start_time`, not only `ir_status`: an event can still show
    `pre_event` after its start time.
    """
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    matches = [
        e
        for e in events
        if e.get("event_type") == "normal"
        and e.get("ir_status") != "in_running"
        and (e.get("start_time") or "") > stamp
        and (sport is None or e.get("sport") == sport)
    ]
    return sorted(matches, key=lambda e: e["start_time"])


def pick_match(events: list[dict], sport: str | None = None, now: datetime | None = None) -> dict | None:
    """The next match that has not started. See upcoming_matches()."""
    matches = upcoming_matches(events, sport, now)
    return matches[0] if matches else None


# ---------------------------------------------------------------------- stream


def open_stream(lang: str = "en"):
    return connect(f"{WS}?api_key={quote(api_key(), safe='')}&lang={lang}", max_size=None)


def frames(ws):
    """Yield individual (tag, payload) messages.

    Every server frame is a batch envelope {"ts": ..., "data": [...]}.
    Batching boundaries are not meaningful, so callers only ever see
    individual entries. Returns when the socket closes, including a silent
    TCP close and the 1008 close for a slow reader.
    """
    while True:
        try:
            raw = ws.recv()
        except Exception:
            return
        try:
            envelope = json.loads(raw)
        except ValueError:
            continue
        for entry in envelope.get("data", []):
            if not isinstance(entry, list) or not entry:
                continue
            yield entry[0], (entry[1] if len(entry) > 1 else None)


def sync_events(ws, timeout: float = 30.0) -> list:
    """Collect the initial event snapshot, up to and including ["sync", ...].

    The snapshot holds the same events as GET /v2/events/: only events that
    currently have prices.
    """
    events, deadline = [], time.time() + timeout
    for tag, payload in frames(ws):
        if tag == "event":
            events.append(payload)
        elif tag == "sync":
            return events
        if time.time() > deadline:
            break
    return events


def register(ws, sport: str, event_id: str):
    ws.send(json.dumps(["register_event", sport, event_id]))


def unregister(ws, sport: str, event_id: str):
    ws.send(json.dumps(["unregister_event", sport, event_id]))


# ---------------------------------------------------------------------- values


def label(event: dict) -> str:
    """Human-readable name for either event shape."""
    if event.get("event_name"):
        return event["event_name"]
    if event.get("event_type") == "multirunner":
        runners = ", ".join(t["name"] for t in event.get("teams", [])[:3])
        return f"[outright] {runners}..."
    return f"{event.get('home', '?')} v {event.get('away', '?')}"


def best(price_list) -> dict | None:
    """Best available price. price_list is sorted descending already."""
    return price_list[0]["effective"] if price_list else None


def tick_size(price) -> Decimal:
    """The tick of the band that holds `price`. A band bound counts in the band below it."""
    p = Decimal(str(price))
    if not MIN_PRICE <= p <= MAX_PRICE:
        raise ValueError(f"price {price} is outside {MIN_PRICE}-{MAX_PRICE}")
    return next(tick for upper, tick in TICKS if p <= upper)


def snap_limit(price, direction: str) -> Decimal:
    """The price an off-tick limit runs at, as the server moves it.

    The server moves an off-tick limit to the first tick that honours it: up
    for a back (`for`) order and down for a lay (`against`) order, so a back
    limit of 7.15 becomes 7.20. Prices from the feed are already on tick.
    """
    if direction not in ("for", "against"):
        raise ValueError("direction must be 'for' or 'against'")
    p = Decimal(str(price))
    tick = tick_size(p)
    rounding = ROUND_CEILING if direction == "for" else ROUND_FLOOR
    return ((p / tick).to_integral_value(rounding=rounding) * tick).quantize(tick)


def new_request_uuid() -> str:
    """Idempotency key. Always send one when placing orders."""
    return str(uuid.uuid4())


def run_cli(main, *args, **kwargs):
    """Run an example's main() and turn API and handshake errors into one line."""
    from websockets.exceptions import InvalidStatus

    try:
        return main(*args, **kwargs)
    except ApiError as exc:
        sys.exit(str(exc))
    except InvalidStatus as exc:
        body = (exc.response.body or b"").decode(errors="replace").strip()
        sys.exit(f"stream handshake refused: HTTP {exc.response.status_code} {body}")
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        # Output piped into `head` or similar, which closed early.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
