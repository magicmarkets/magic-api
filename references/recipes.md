# MagicMarkets: Recipes

Task-shaped patterns. All against `https://magicmarkets.com/v2/` and
`wss://magicmarkets.com/v2/stream`.

Assumes `MAGIC_API_KEY` is exported. Runnable versions live in
[`../examples/`](../examples/). For concepts see [`../SKILL.md`](../SKILL.md);
for schemas see [`rest.md`](rest.md) and [`streaming.md`](streaming.md).

---

## A: See what is tradeable right now

`GET /v2/events/` lists every event that currently has prices. It pages
with `limit` and `after`:

```python
import os, requests

API, H = "https://magicmarkets.com/v2", {"X-Api-Key": os.environ["MAGIC_API_KEY"]}

events, after = [], None
while True:
    params = {"sport": "fb", "limit": 500, **({"after": after} if after else {})}
    page = requests.get(f"{API}/events/", headers=H, params=params, timeout=30).json()["data"]
    events += page
    if len(page) < 500:
        break
    after = f"{page[-1]['sport']},{page[-1]['event_id']}"

for e in sorted(events, key=lambda e: e["start_time"]):
    label = e.get("event_name") or f"{e.get('home')} v {e.get('away')}"
    print(f"{e['start_time']}  {e['sport']:<8} {label}")
```

The stream's initial sync gives the same set. Use it when you keep the socket
open anyway: connect, collect `["event", ...]` entries until `["sync", ...]`,
and changes then arrive as they happen.

```python
import json, os
from urllib.parse import quote
from websockets.sync.client import connect

key = quote(os.environ["MAGIC_API_KEY"], safe="")
with connect(f"wss://magicmarkets.com/v2/stream?api_key={key}", max_size=None) as ws:
    events, synced = [], False
    while not synced:
        for entry in json.loads(ws.recv())["data"]:
            if entry[0] == "event":
                events.append(entry[1])
            elif entry[0] == "sync":
                synced = True
```

Both return only events **with live prices**, not the full fixture list. That
can still be a few thousand events, many of them outrights
(`event_type: "multirunner"`) and period-scoped codes such as `fb_ht`. To
find a match, filter on `event_type == "normal"` and on a `start_time` in the
future: an event can still show `pre_event` after its start time.

---

## B: Place a back order end to end

```
verify key → connect stream → sync → register_event → pick offer
  → POST /v2/betslips/ → wait for pmm → POST /v2/orders/ → watch order
```

1. `GET /v2/balance/`: fail fast on a bad key.
2. Connect the stream; collect events until `sync`. Pick a `normal` event
   whose `start_time` is in the future.
3. `["register_event", sport, event_id]`; collect `["offer", …]` until the ok
   `["response", …]`.
4. Pick an offer with a non-empty `price_list`. Its `sport`, `event_id` and
   `bet_type` are all you need: pass them through verbatim.
5. `POST /v2/betslips/` → `betslip_id`.
6. Wait for `["pmm", …]` on the socket whose `betslip_id` matches and whose
   `price_list` is non-empty.
7. `POST /v2/orders/` with `betslip_id`, `price` from the quote, `stake`,
   `duration`, and a fresh `request_uuid`.
8. Watch `["order", …]` until `status` is `done` or `failed`.

### curl variant

Assumes you already have `sport` / `event_id` / `bet_type` from an offer.

```bash
API=https://magicmarkets.com/v2
H="X-Api-Key: $MAGIC_API_KEY"

# 1. deadman's switch (10-300s)
HB=$(curl -s -X POST "$API/heartbeats/" -H "$H" -H 'Content-Type: application/json' \
  -d '{"timeout": 60}' | jq -r .data.heartbeat_id)

# 2. betslip. Note: no prices in this response
BS=$(curl -s -X POST "$API/betslips/" -H "$H" -H 'Content-Type: application/json' \
  -d '{"sport":"fb","event_id":"2026-06-15,1001,2002","bet_type":"for,ah,h,-4","betslip_type":"normal"}' \
  | jq -r .data.betslip_id)

# 3. poll for the quote (or read pmm off the stream)
curl -s "$API/betslips/$BS/" -H "$H" | jq '.data.price_list'

# 4. place, with an idempotency key
curl -s -X POST "$API/orders/" -H "$H" -H 'Content-Type: application/json' \
  -d "{\"betslip_id\":\"$BS\",\"price\":2.0,\"stake\":[\"USDT\",10.0],\"duration\":5.0,\"request_uuid\":\"$(uuidgen)\"}" | jq

# 5. refresh well inside the timeout, then release
curl -s -X POST "$API/heartbeats/$HB/refresh/" -H "$H" > /dev/null
curl -s -X DELETE "$API/heartbeats/$HB/" -H "$H" > /dev/null
```

---

## C: Maintain a live price book

Register the events you care about and keep a dict keyed by
`(sport, event_id, bet_type)`.

```python
book = {}

for entry in json.loads(ws.recv())["data"]:
    tag = entry[0]
    p = entry[1] if len(entry) > 1 else None
    if tag == "offer":
        book[(p["sport"], p["event_id"], p["bet_type"])] = p["price_list"]
    elif tag == "remove_offer":
        book.pop((p["sport"], p["event_id"], p["bet_type"]), None)
    elif tag == "clear_events":
        book.clear()          # upstream feed lost: everything held is stale
```

Three rules that separate a correct book from a subtly wrong one:

- **`offer` is a full replacement** for that triple, not a delta. Overwrite,
  do not merge.
- **`remove_offer`** means that bet type has no liquidity left. Delete it:
  do not leave last-known prices in the book.
- **`clear_events`** means the server lost its upstream feed. Drop everything
  and wait for the fresh snapshot + `sync`.

`price_list` is sorted descending, so `price_list[0]["effective"]` is the best
available price.

---

## D: Market-making with heartbeat protection

Any unattended strategy should sit inside a heartbeat so a crashed process
does not leave exposure open.

```
create heartbeat (timeout T)
  loop:
    refresh every T/3
    re-quote, place / close orders
  on exit: close orders, delete heartbeat
```

Choosing `T` (valid range **10-300 s**):
- Short (10-30 s): tight protection, but a slow tick risks self-inflicted
  closure. Refresh at `T/3`.
- Long (120-300 s): tolerant of hiccups, leaves exposure open longer after a
  genuine crash.

Refresh on a timer **independent of your trading loop**. If refreshing is
coupled to a loop that can block on a slow REST call, a stall expires the
heartbeat and closes your book.

Always send a `request_uuid`. Under retry, a reused uuid returns
`409 order_already_created` with the existing `order_id`: safe. Without one,
a timeout-then-retry can double-place.

---

## E: Bulk-close

```bash
API=https://magicmarkets.com/v2
H="X-Api-Key: $MAGIC_API_KEY"

# always look before closing. The list is paged (25 by default): read every page
PAGE=1
while :; do
  ROWS=$(curl -s "$API/orders/?page=$PAGE&page_size=100" -H "$H")
  echo "$ROWS" | jq '[.data[] | select(.closed == false)
        | {order_id, sport, bet_type, want_price, want_stake}]'
  [ "$(echo "$ROWS" | jq '.data | length')" -lt 100 ] && break
  PAGE=$((PAGE + 1))
done

# one order
curl -s -X POST "$API/orders/12345/close/" -H "$H"

# a specific set
curl -s -X POST "$API/orders/close_many/" -H "$H" -H 'Content-Type: application/json' \
  -d '{"order_ids": [12345, 12346]}'

# everything: unfiltered and irreversible
curl -s -X POST "$API/orders/close_all/" -H "$H"
```

A page past the last one is empty. `close_all` takes no filter. Enumerate and close
explicitly unless you really do mean every open order. Closing an already-closed order returns
`400 order_closed`, distinct from `404 not_found`.

---

## F: Multi-event streaming

Register many events on one socket: do not open a socket per event.

```python
for ev in events[:20]:
    ws.send(json.dumps(["register_event", ev["sport"], ev["event_id"]]))
```

- The registered-event cap is counted across **all** your connections.
  Exceeding it returns `customer_event_limit_exceeded`: unregister first.
- `["list_registered_events"]` returns the current set.
- Registrations **do not survive a reconnect**. Re-register after any drop.
- Read fast. A slow reader is closed with code 1008, and an immediate
  reconnect overflows again. If you do heavy work per message, hand frames
  to a queue and process them off the read loop.

---

## G: Price snapshot over REST

For a report or a check, read prices without a socket: list the events,
then ask `GET /v2/offers/` for up to 20 of them in each call.

```python
ids = [e["event_id"] for e in matches]           # one sport, from recipe A
offers = []
for i in range(0, len(ids), 20):                 # 20 events per call
    r = requests.get(f"{API}/offers/", headers=H, timeout=30, params={
        "sport": "fb", "event_id": ids[i:i + 20],
        "market_type": ["wdw", "ah", "ou"], "min_liquidity": 10,
    })
    offers += r.json()["data"]                   # page with `after` past 500 rows
```

- A call that names 20 events costs the same as one that names 1, and an
  account can have only 4 calls open at once. Batch; do not fan out.
- The reply can be about 4 seconds behind. Quote and trade from the stream.
- Each `bet_type` goes into `POST /v2/betslips/` unchanged.

Runnable version: [`../examples/05-rest-offers.py`](../examples/05-rest-offers.py).

---

## Cross-cutting patterns

### Frame parsing

Every frame is `{"ts": …, "data": [...]}`. Never assume one message per frame,
a fixed order, or that a type appears exactly once.

```python
for entry in json.loads(raw)["data"]:
    tag = entry[0]
    payload = entry[1] if len(entry) > 1 else None
```

### Reconnect

```python
delay = 1
while True:
    try:
        with connect(url) as ws:
            delay = 1
            resync(ws)          # collect events → sync
            re_register(ws)     # registrations are not preserved
            pump(ws)
    except Exception:
        time.sleep(delay)
        delay = min(delay * 2, 60)
```

A silent drop looks like a clean EOF. Treat any exit from `pump()` as a
reconnect trigger.

### Auth failures

Verify with `GET /v2/balance/` before connecting. WebSocket auth fails at the
handshake with a non-101 status and a short text body (`401 auth_rejected`,
`400 missing_credentials`). `websockets` raises `InvalidStatus` with the body
on `exc.response.body`. A `401 auth_error` from REST is easier to read. Its
detail text is the same for a missing key and a wrong key, so check both.
