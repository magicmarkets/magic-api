---
name: magicmarkets-magic-api
description: >
  MagicMarkets API assistant: sports markets exchange with zero fees.
  Covers the REST API at magicmarkets.com/v2/ for market data
  (GET /v2/events/, GET /v2/offers/), betslips, placing and closing
  orders, positions, balance and heartbeats, and the WebSocket stream at
  magicmarkets.com/v2/stream for live offers, private betslip quotes and
  order updates. Use this skill when the user mentions MagicMarkets, the
  Magic API, magicmarkets.com, betslips, placing orders, back/lay/parlay,
  heartbeats, the price stream, register_event, USDT stakes, X-Api-Key
  auth, betslip_id, order_id, request_uuid, or building trading tools
  against MagicMarkets. Not for the read-only data feed at
  data.magicmarkets.com, which is a separate product.
---

# MagicMarkets API

MagicMarkets is a **sports markets exchange** with zero fees. Every order
matches peer liquidity or liquidity-provider liquidity in one order book.
MagicMarkets never takes the other side. All stakes are USDT.

| Detail | Value |
|--------|-------|
| **REST base** | `https://magicmarkets.com/v2/` |
| **WebSocket** | `wss://magicmarkets.com/v2/stream?api_key=<key>` |
| **REST auth** | `X-Api-Key: <key>` header |
| **WS auth** | `?api_key=<key>` query param (same key, URL-encoded) |
| **Stakes** | `["USDT", <amount>]` tuples, always USDT in responses |
| **Prices** | Decimal odds on a fixed tick schedule |

Keys are created on the website: **Settings, API, Add API Key**. The value
is shown once at creation. There is no endpoint for key management.

---

## The published docs are the source of truth

MagicMarkets publishes complete, current documentation. **Fetch it rather
than trusting memory.** This skill is a working guide, not a replacement:

| URL | What |
|-----|------|
| `https://magicmarkets.com/docs` | Documentation site: guides, account rules, API pages |
| `https://magicmarkets.com/llms.txt` | Index of the machine-readable docs |
| `https://magicmarkets.com/llms-full.txt` | Full API reference in one Markdown file, about 150 KB |
| `https://magicmarkets.com/v2/openapi.yaml` | OpenAPI 3.1 spec: 20 paths |
| `https://magicmarkets.com/v2/openapi.json` | The same spec as JSON |

Fetch `llms-full.txt` whenever you need exact request and response schemas,
the full sport-code table, per-endpoint error codes, or anything this file
summarises.

**Retired: do not use.** `pro.magicmarkets.com` (301s to the root domain),
the old `/magic-cpricefeed/v2` WebSocket (returns 502) and
`/web/offerhist/...` (404). Any code or doc that still names these is stale.

---

## Glossary

**Event**: a match (`normal`) or an outright (`multirunner`), keyed by
`(sport, event_id)`. Only events that currently have prices are listed.

**Offer**: one priced selection, keyed by `(sport, event_id, bet_type)`.
`for` and `against` on the same selection are two separate offers.

**Betslip**: a *quote request*. You name a selection (`sport`, `event_id`,
`bet_type`) and get a `betslip_id`. The prices arrive separately, as `pmm`
messages on the WebSocket, or by polling the betslip. Betslips are
short-lived: watch `expiry_ts`.

**Order**: a *commitment*. A `betslip_id` plus a limit `price` and a
`stake`. See [Order lifecycle](#order-lifecycle).

**pmm**: your *private* quote for an open betslip, delivered on the WS.

**Heartbeat**: a deadman's switch. If you stop refreshing it, the server
closes every open order on the account, across all sessions and API keys.
Matched bets are unaffected.

---

## Two ways to read the market

| | REST market data | WebSocket stream |
|---|---|---|
| Discover events | `GET /v2/events/` (paged, filterable) | Initial sync: `["event", ...]` until `["sync", ...]` |
| Read prices | `GET /v2/offers/` (up to 20 events a call) | `register_event`, then `offer` / `remove_offer` pushes |
| Freshness | Can be about 4 s behind | Live |
| Use for | Scripts, reports, checks, a first look | Trading, quoting, anything price-sensitive |

Both list the same events: only events that currently have prices. Private
quotes (`pmm`) and order updates come only on the stream. **Trade from the
stream.** A `bet_type` from either source goes into a betslip unchanged.

### The trading flow

```
1. GET /v2/balance/            verify the key over REST first
2. connect wss://.../v2/stream collect ["event", ...] until ["sync", ...]
3. ["register_event", sport, event_id]   -> ["offer", ...] snapshot
4. pick an offer: its sport/event_id/bet_type is all you need
5. POST /v2/betslips/          -> betslip_id
6. wait for ["pmm", ...] on the WS matching your betslip_id -> prices
7. POST /v2/orders/            -> order_id
8. watch ["order", ...] / ["bet", ...] on the WS until a terminal status
```

**Verify the key over REST before opening the socket.** A bad key fails the
WebSocket *handshake* with a non-101 status, which a client library shows as
a handshake error. `GET /v2/balance/` turns that into a clear
`401 auth_error`.

**Check `start_time` as well as `ir_status`.** An event can still show
`pre_event` after its start time. Do not treat such an event as pre-match.

---

## REST market data

### `GET /v2/events/`

Lists the events that currently have prices. Each entry is the same object
the stream sends as `["event", {...}]`.

- Filters: `sport`, `competition_id`, `event_id`, `ir_status`
  (`pre_event` / `in_running`), `start_time_from`, `start_time_to`, `lang`.
  List filters repeat the parameter: `?sport=fb&sport=tennis`.
- `event_id` and `competition_id` need `sport`, or you get a 400.
- Paging: `limit` (default 500) and `after`. Pass the last entry of the
  previous page as `after="{sport},{event_id}"`. A page shorter than
  `limit` is the last. There is no total count.

### `GET /v2/offers/`

The stake available at each price, for each market on the named events.
Each entry is the same object the stream sends as `["offer", {...}]`.

- `sport` and `event_id` are required. Name **up to 20 events** in one call.
- Filters: `bet_type`, `market_type` (families such as `ah`, `ou`, `wdw`),
  `min_liquidity` (USDT summed over a market's `price_list`).
- Paging: `limit` and `after="{event_id},{bet_type}"`.
- Markets with no stake are left out. An unknown or unpriced event returns
  no offers, and the other events still come back.
- `Cache-Control: private, max-age=2`. A reply can be about 4 seconds behind.
- **Only 4 calls can be open at once** for each account. One call that names
  20 events costs the same as one that names 1, so batch.

---

## Wire format: read this before writing any WS code

**Every** server frame is a batch envelope:

```json
{"ts": 1586042815.269000, "data": [ <message>, <message>, ... ]}
```

Each `data[]` entry is an array whose first element is a type tag:

```python
frame = json.loads(ws.recv())
for entry in frame["data"]:
    tag = entry[0]          # "event" | "offer" | "pmm" | "order" | "sync" | ...
    payload = entry[1]
```

Batching boundaries carry **no meaning**. Never rely on ordering, grouping,
or a type appearing exactly once per frame. Always iterate `data[]` and
dispatch on `entry[0]`.

### Discovery on the stream

On connect the server sends the currently priced events as `["event", {...}]`
entries, ending with `["sync", {"session_id": ...}]`. The snapshot may span
several envelopes. After sync, changed events re-arrive as `["event", ...]`
and events that lose their prices arrive as `["remove_event", ...]`.

Two event shapes: dispatch on `event_type`.
- `normal`: a match; carries `home` and `away`.
- `multirunner`: outright or futures; no home/away, carries a `teams` array
  (`[{"team_id", "name"}, ...]`) and an `end_time`.

### Commands

```json
["register_event", "<sport>", "<event_id>"]     -> offer snapshot, then ok response
["unregister_event", "<sport>", "<event_id>"]   -> ok (idempotent)
["list_registered_events"]                       -> {"registered_events": [[sport, id], ...]}
["echo", "anything"]                             -> echoed back verbatim
```

Registering an event with no prices is **not** an error: you get an empty
snapshot. There is no "unknown event" error. Register event ids you saw in
the sync or in `GET /v2/events/`.

### Message types you will see

`event`, `remove_event`, `sync`, `offer`, `remove_offer`, `pmm`, `betslip`,
`betslip_closed`, `order`, `bet`, `balance`, `xrate`, `info`, `response`,
`clear_events`, plus in-play state (`event_time`, `event_score`,
`event_red_cards`, `ir_info`, `remove_ir_info`,
`event_exchange_dark_liquidity`).

Two that matter for correctness:
- **`clear_events`**: the server lost its upstream feed. Discard all event,
  offer and live-state data you hold; a fresh snapshot follows.
- **`betslip_closed`**: `{betslip_id, close_reason}`. No further `pmm` will
  arrive; create a new betslip to re-quote.

### Offers

```json
["offer", {
  "sport": "fb", "event_id": "2026-06-15,1001,2002",
  "bet_type": "for,ah,h,-4", "market_type": "ah", "in_running": false,
  "price_list": [
    {"effective": {"price": 2.0, "min": ["USDT", 5.0], "max": ["USDT", 150.0]}},
    {"effective": {"price": 1.99, "min": null, "max": ["USDT", 80.0]}}
  ]
}]
```

`price_list` is sorted by decimal price **descending**, one entry per price.
`min` is `null` when there is no minimum; `max` is the stake available at that
price. An empty `price_list` means no liquidity: pick another offer.

---

## Bet types

`bet_type` is a comma-separated string. The first token is the direction:
`for` (back) or `against` (lay). The rest encodes the market and its
parameters. **Handicaps always refer to the home team.**

**Asian handicap lines are integers equal to 4 x the real line**:
`for,ah,h,-4` is home -1.0, `for,ah,h,2` is home +0.5, and
`for,ahover,7` is over 1.75. The integer is the home line, and the side
token picks the team.

**Never construct a `bet_type` by hand.** Read it off an offer and pass it
through verbatim. To check one, call
`GET /v2/sports/{sport}/bet_types/{bet_type}/`. That endpoint cannot check
outright bet types (`for,win,...`, `for,top,...`): they always return 400.

`sport` codes are lowercase and period-scoped (`fb`, `fb_ht`, `fb_htft`,
`fb_corn`, `basket_q1`, `tennis`, `af`, `horse`, `esports`, `politics`, ...).
One match can appear under several codes. Treat the list as **open**: new
codes are added; do not hard-fail on an unknown one. On parlays, `sport` is
the literal string `parlay` and per-leg sports sit inside `legs[]`.

Full sport table and market grammar: fetch `llms-full.txt`.

---

## Prices and ticks

All single-market prices sit on a fixed tick schedule that widens as the
price grows: 0.01 up to 2, then 0.02 to 3, 0.05 to 4, 0.10 to 6, 0.20 to 10,
0.50 to 20, 1 to 30, 2 to 50, 5 to 100 and 10 to 1000.

- Prices from the feed are **already on tick**: quote them straight through.
- An order `price` is a limit. A bet is taken only at that price or better:
  higher for `for`, lower for `against`.
- An off-tick limit moves to the **first tick that honours it**: **up** for
  `for`, **down** for `against`. A back limit of 7.15 becomes 7.20, and is
  not filled at 7.00. The moved price is the one the order runs with.
- Parlay prices are the product of the legs and are on no tick schedule.

---

## Order lifecycle

`POST /v2/orders/` returns **201** with `order_id` and `status: "open"`.

- Statuses: `open`, `pending`, `done`, `failed`, `partial_void`,
  `full_void`, `reconciled`. Treat all but `open` and `pending` as terminal.
- `done` means **filled, not settled**. The final `profit_loss` lands after
  the event.
- `failed` usually means a limit order that expired without a match. Read
  `close_reason` for the cause.
- `exchange_mode`: `make_and_take` (default), `take_only`, `dark`. Every mode
  takes crossing liquidity first. There is **no post-only mode**.
- `duration` is in seconds, default 15.

---

## Errors

REST errors share one envelope:

```json
{"status": "error", "code": "validation_error",
 "data": {"validation_errors": {"bet_type": ["invalid_bet_type"]}}}
```

Always check `status` before reading `data`. Branch on `code`, not the HTTP
status alone.

| HTTP | `code` | Meaning |
|------|--------|---------|
| 400 | `validation_error` | `data.validation_errors` is `{field: [reason]}`; cross-field issues in `non_field_errors`; a list field is index-keyed |
| 400 | `order_closed` | Order exists but is already closed or settled |
| 401 | `auth_error` | Key missing, malformed or rejected |
| 403 | `forbidden` | Valid key, action not allowed |
| 403 | `invalid_customer` | Market data: the feed has no record of your account. Contact support |
| 404 | `not_found` | Unknown, or not visible to this key |
| 409 | `order_already_created` | `request_uuid` reused; `data` has the existing `order_id` |
| 409 | `limit_reached` | Per-customer cap hit |
| 429 | `throttled` | Honour `Retry-After` / `data.retry_after` |
| 500 | `server_error` | `data` carries a support token: quote it |
| 503 | `warming` | Market data is loading. Retry with backoff |
| 503 | *(no envelope)* | Body `{"detail": "Service unavailable"}`. Retry with backoff |

The 401 detail text is the same for a missing key and a wrong key. Check both.

**Stream handshake.** A refused upgrade returns a non-101 status with a short
text body: `400 missing_credentials` or `invalid_lang`, `401 auth_rejected`,
`503 unavailable`. Do not retry a 401 with the same key.

**Stream command errors** arrive in-band and leave the socket open:
`["response", {"status": "error", "code": "..."}]`. Codes: `bad_json`,
`invalid_input`, `already_registered`, `customer_event_limit_exceeded`,
`invalid_customer`, `system_error`. Treat any other code as opaque: log and
retry with backoff.

**Dropped connections.** A slow reader is closed with code **1008**: read
faster or register fewer events, because an immediate reconnect overflows
again. An I/O error or an internal error closes the connection with a raw
TCP close: no close frame and no error. Always reconnect with backoff and
re-register your events. Do not assume a quiet socket is a healthy one.

---

## Rate limits

Per **account**: all keys share one budget. Each limit is a token bucket
that refills continuously.

| Applies to | Limit |
|---|---|
| All endpoints | 100 req/s burst, 1200 req/min sustained |
| `POST /v2/betslips/` | 10 req/s, and 2000 betslips a day |
| `POST /v2/orders/` | 5 req/s |
| `GET /v2/offers/` | 4 requests open at once |

The betslip and order limits are their own budgets. Market data shares the
general budget. There is no per-IP limit. Success responses carry **no**
remaining-quota header, so track your own rate. The WS stream has no
message-rate limit.

---

## Idempotency

`POST /v2/orders/` accepts an optional `request_uuid`. Reusing one returns
`409 order_already_created` with the existing `order_id`, so a retry after a
timeout is safe and will not double-place. **Always send one** from
automated code. `GET /v2/orders/tracked/{uuid}/` retrieves an order by its
`request_uuid` for up to 6 hours after placement.

---

## Endpoint index

Market data: `GET /v2/events/` · `GET /v2/offers/`

Betslips: `GET|POST /v2/betslips/` · `GET /v2/betslips/{betslip_id}/` ·
`POST /v2/betslips/{betslip_id}/refresh/`

Orders: `GET|POST /v2/orders/` · `GET /v2/orders/{order_id}/` ·
`GET /v2/orders/updates/` · `GET /v2/orders/tracked/{uuid}/` ·
`POST /v2/orders/{order_id}/close/` · `POST /v2/orders/close_many/` ·
`POST /v2/orders/close_all/` · `GET /v2/orders/position/`

Account: `GET /v2/balance/` · `GET /v2/xrates/`

Heartbeats: `GET|POST /v2/heartbeats/` · `GET|DELETE /v2/heartbeats/{heartbeat_id}/` ·
`POST /v2/heartbeats/{heartbeat_id}/refresh/`

Reference: `GET /v2/sports/{sport}/bet_types/{bet_type}/`

Stream: `GET /v2/stream` (WebSocket upgrade)

`GET /v2/orders/` is paged with `page` and `page_size` (25 by default). Read
every page before you conclude that an order is not there.

Exact schemas, parameters and per-endpoint error codes: fetch
`https://magicmarkets.com/llms-full.txt`.

---

## Deeper reference

- [`references/rest.md`](references/rest.md): REST endpoints, shapes, errors, limits.
- [`references/streaming.md`](references/streaming.md): full WebSocket protocol.
- [`references/recipes.md`](references/recipes.md): task-shaped patterns.
- [`examples/`](examples/): runnable Python scripts. 03 and 04 are dry runs by default.

---

## Common mistakes

- **Using a retired host or endpoint.** See the list at the top.
- **Trading from `GET /v2/offers/`.** It can be 4 s behind. Quote and trade
  from the stream.
- **One `/v2/offers/` call per event.** Name up to 20 events in each call;
  only 4 calls can be open at once.
- **Taking `events[0]` as a match.** It is often an outright. Filter on
  `event_type == "normal"` and check `start_time`.
- **Reading one page of `GET /v2/orders/`.** It holds 25 orders by default.
- **Treating a frame as a message.** Frames are batch envelopes; iterate `data[]`.
- **Expecting prices in the `POST /v2/betslips/` response.** They arrive as
  `pmm` messages on the WebSocket.
- **Constructing `bet_type` strings, or reading a handicap integer as the
  line.** Read them off offers; the line is the integer divided by 4.
- **Rounding a back limit down to the tick below.** The server moves it up.
- **Treating `done` as settled.** It means filled; `profit_loss` finalises later.
- **Assuming a quiet socket is healthy.** Reconnect with backoff and
  re-register.
- **Omitting `request_uuid`** on automated order placement.
