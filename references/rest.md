# MagicMarkets: REST reference

Base: `https://magicmarkets.com/v2/` · Auth: `X-Api-Key: <key>` on every request.

> Canonical source: `https://magicmarkets.com/llms-full.txt` and
> `https://magicmarkets.com/v2/openapi.yaml`. Fetch those for exact schemas,
> every optional field, and per-endpoint error codes. This file covers the
> shapes you need in practice.

All responses share one envelope: check `status` before reading `data`:

```json
{"status": "ok", "data": ...}
{"status": "error", "code": "<code>", "data": <details>}
```

List query parameters repeat: `?sport=fb&sport=tennis`.

---

## Market data

Both endpoints return the same objects the stream sends, so code that reads
one can read the other. For live prices, use the stream.

### `GET /v2/events/`: events with prices

| Parameter | Notes |
|---|---|
| `sport` | List. Needed with `event_id` or `competition_id` |
| `competition_id` | List of integers |
| `event_id` | List. The form an event carries, such as `2026-06-15,1001,2002`; other forms get a 400 |
| `ir_status` | `pre_event` or `in_running` |
| `start_time_from`, `start_time_to` | ISO 8601 times |
| `lang` | `en` (default), `zh-hans`, `ko` |
| `limit` | Default 500, at most 5000 |
| `after` | `"{sport},{event_id}"` of the last entry on the previous page |

A page shorter than `limit` is the last. There is no total count. A filter
that matches nothing returns an empty `data`.

`event_type` gives the shape: `normal` has `home` and `away`; `multirunner`
has `teams` and `end_time`. Every entry has its `sport`, so a follow-up call
can always supply it.

Check `start_time` as well as `ir_status`. An event can still show
`pre_event` after its start time.

### `GET /v2/offers/`: stake at each price

| Parameter | Notes |
|---|---|
| `sport` | Required, one value |
| `event_id` | Required. Up to 20 events in one request |
| `bet_type` | List. The same strings `POST /v2/betslips/` takes |
| `market_type` | List of families, such as `ah`, `ou`, `wdw` |
| `min_liquidity` | Keep a market when its `max` stakes add up to at least this many USDT |
| `limit` | Default 500, at most 5000 |
| `after` | `"{event_id},{bet_type}"` of the last entry on the previous page |

- Offers come back in `event_id` order, then `bet_type` order.
- Markets with no stake are left out. `for` and `against` on one selection
  are two markets.
- An event with no prices, or one the feed does not know, returns no offers.
  The other events in the request still come back.
- For a sport your account is not enabled for, the list is empty.
- The reply can be about 4 seconds behind the stream
  (`Cache-Control: private, max-age=2`). Each page is read when it is
  requested, so pages of one event can differ in time.
- **Only 4 requests can be open at once** for each account. A call that names
  20 events costs the same as one that names 1. A request over the cap gets
  `429 throttled` with `retry_after: 1`.

Errors specific to market data: `403 invalid_customer` (the feed has no
record of your account; contact support) and `503 warming` (the feed is
loading; retry with backoff).

---

## Betslips

### `POST /v2/betslips/`: create

Normal / lay: supply `sport`, `event_id`, `bet_type`. Parlay: supply `legs`
instead.

```json
{
  "sport": "fb",
  "event_id": "2026-06-15,1001,2002",
  "bet_type": "for,ah,h,-4",
  "betslip_type": "normal"
}
```

| Field | Notes |
|---|---|
| `sport`, `event_id`, `bet_type` | Required for `normal` / `lay`. Copy verbatim off an offer |
| `legs[]` | For parlays: `[{sport, event_id, bet_type, live_score?}, ...]` |
| `betslip_type` | `normal` (default), `lay`, `parlay` |
| `live_score` | In-play: `{"home": 1, "away": 0}`. Liquidity quoted at a different score is then never treated as equal to your selection |
| `equivalent_bets` | Default `true` |
| `exclude_danger` | Only use liquidity sources with no bets in danger status |
| `user_data` | Free-form string echoed back |

Returns **201** with `betslip_id`, `bet_type_description`, `expiry_ts`,
`is_open`, `close_reason`, `betslip_type`, `legs[]`.

**The create response carries no prices.** Quotes are gathered
asynchronously. Either:
- read them off the WebSocket as `["pmm", ...]` entries matching your
  `betslip_id` (preferred: you should already hold the socket open), or
- poll `GET /v2/betslips/{betslip_id}/` until `price_list` populates.

Typically a couple of seconds. Watch `expiry_ts`: betslips are short-lived.
An empty `price_list` that stays empty means no liquidity; pick another offer.
Each account can create 2000 betslips a day.

On parlays, `sport` comes back as the literal `parlay` and `event_id` as `""`.

### Others

- `GET /v2/betslips/`: list.
- `GET /v2/betslips/{betslip_id}/`: fetch one, including `price_list`.
- `POST /v2/betslips/{betslip_id}/refresh/`: re-quote an existing betslip.

---

## Orders

### `POST /v2/orders/`: place

```json
{
  "betslip_id": "65b6ff7da480479b9dda1c7ff765c434",
  "price": 2.0,
  "stake": ["USDT", 10.0],
  "duration": 5.0,
  "request_uuid": "..."
}
```

| Field | Notes |
|---|---|
| `betslip_id` | Required |
| `price` | Limit decimal price. Off-tick moves **up** for `for`, **down** for `against` (see below) |
| `stake` | `["USDT", amount]` |
| `duration` | Order lifetime in **seconds**, default 15 |
| `request_uuid` | Idempotency key: **always send one** from automated code |
| `exchange_mode` | `make_and_take` (default), `take_only`, `dark`. See below |
| `keep_open_ir` | Keep the order open when the event goes in-play |
| `accept_partial_fill` | Default `true` |
| `accept_better_price` | Default `true` |
| `force_want_price` | Force the requested price |
| `min_taker_want_stake` | `dark` only. Stake tuple or `null`: the smallest order that can match yours |
| `current_score` | `[home, away]` score assertion. See below |
| `exclude_danger` | As per betslips |
| `bookie_min_stakes` | Optional per-source minimum stakes, `{source: [currency, amount]}` |
| `user_data`, `placer_type` | Optional tags recorded against the order |

#### `exchange_mode`

Every mode takes crossing liquidity first. There is **no post-only mode**.
The difference is what happens to the unfilled remainder:

- `make_and_take` (default): advertises the remainder at your price and keeps
  taking newly available liquidity.
- `take_only`: never advertises the remainder. Nothing can match against you.
- `dark`: advertises the remainder invisibly. Other orders can match it when
  their price crosses yours, but they cannot see your price.

The values `make` and `take` do not exist. The API rejects them with
`validation_error`.

#### `current_score`

Optional array of exactly two integers, `[home, away]`. It is a
placement-time assertion: if the value does not match the live score the
exchange holds for the event, the order is rejected with HTTP 400, code
`validation_error`, `non_field_errors: ["event_scores_dont_match"]`.
Rejection is always explicit. There is no silent flagging.

The check is only meaningful for football-style scores. For other sports,
and while no score is known yet, the server assumes `[0, 0]` and rejects any
other value. Omit the field outside football.

### Order lifecycle

Returns **201** with `order_id` and `status: "open"`. `price`, `stake` and
`profit_loss` are `null` until the order fills.

Statuses: `open`, `pending`, `done`, `failed`, `partial_void`, `full_void`,
`reconciled`. The usual path is `open -> pending -> done | failed`. Watch
`["order", ...]` and `["bet", ...]` on the WebSocket, or
`GET /v2/orders/{order_id}/`.

**`done` means filled, not settled.** The final `profit_loss` lands after the
event finishes. `failed` usually means a limit order that expired without a
match; read `close_reason`.

`order_type` is `normal`, `lay` or `parlay` for orders placed through the
API. `brokerage`, `cashout` and `custom` can appear on orders from other
channels. Treat it as an open set.

### Idempotency

Reusing a `request_uuid` returns `409 order_already_created` with the existing
`order_id` in `data`, so retrying after a timeout is safe and cannot
double-place. `GET /v2/orders/tracked/{uuid}/` looks an order up by
`request_uuid` for up to **6 hours** after placement; after that it is `404`.

### Reading and closing

| Endpoint | Purpose |
|---|---|
| `GET /v2/orders/` | List orders. **Paged**: `page`, `page_size` (default 25). Filters: `status`, `sport`, `event_id`, `order_type`, `date_from`, `date_to`, `search` |
| `GET /v2/orders/{order_id}/` | Fetch one |
| `GET /v2/orders/updates/` | Changes since a timestamp: requires `updated_at_from` |
| `GET /v2/orders/tracked/{uuid}/` | Look up by `request_uuid` (6 h window) |
| `POST /v2/orders/{order_id}/close/` | Close one. `400 order_closed` if already closed |
| `POST /v2/orders/close_many/` | Close a named set: `{"order_ids": [...]}` |
| `POST /v2/orders/close_all/` | Close everything open |
| `GET /v2/orders/position/` | Current position; requires filter params |

A page past the last one returns an empty list. Read every page before you
conclude that an order is not there.

`close_all` is unfiltered and cannot be undone: confirm intent before calling it.

---

## Account

- `GET /v2/balance/`: `balance`, `open_stake` and, when the account has it,
  `smart_credit` (extra funds equal to what open bets are expected to win).
  Also the **cheapest key check**; call it before opening the WebSocket.
- `GET /v2/xrates/`: exchange rates.

---

## Heartbeats (deadman's switch)

When a heartbeat expires, the exchange closes **every open order on the
account** that was created before the expiry instant: unfilled stake is
cancelled and unmatched advertised liquidity is withdrawn. Bets that already
matched are unaffected. The switch is account-wide, covering all sessions and
API keys, and expiry is evaluated server-side about once per second. Use one
around any unattended strategy.

| Endpoint | Purpose |
|---|---|
| `POST /v2/heartbeats/` | Create: body `{"timeout": <seconds>}` |
| `GET /v2/heartbeats/` | List active |
| `GET /v2/heartbeats/{heartbeat_id}/` | Fetch one |
| `POST /v2/heartbeats/{heartbeat_id}/refresh/` | Reset the timer: call well inside `timeout` |
| `DELETE /v2/heartbeats/{heartbeat_id}/` | Cancel |

`timeout` must be **10-300 seconds**; outside that range returns `400`.
Create returns **200** with `heartbeat_id` and `expiry_time`.

Two behaviours to build risk handling around:

- `DELETE` only disarms the timer. It closes nothing.
- An expired heartbeat cannot be refreshed; its close-out has already been
  triggered. Open a new one instead.

Refresh on an interval comfortably shorter than `timeout`. A refresh that
races the expiry will not save the orders.

---

## Reference data

`GET /v2/sports/{sport}/bet_types/{bet_type}/`: check and describe a bet
type. A 200 has a readable `bet_type_description` and the payoff grid; a
`400 invalid_bet_type` means the string did not parse. It cannot check
outright bet types (`for,win,...`, `for,top,...`), which always return 400.
Use it instead of parsing or constructing `bet_type` strings yourself.

---

## Error codes

| HTTP | `code` | Meaning |
|------|--------|---------|
| 400 | `validation_error` | `data.validation_errors` is `{field: [reason]}`; cross-field in `non_field_errors`; a rejected list field is index-keyed: `{field: {"0": [reason]}}` |
| 400 | `order_closed` | Order exists but already closed/settled (distinct from `not_found`) |
| 401 | `auth_error` | Key missing, malformed, or rejected. The detail text is the same for a missing and a wrong key |
| 403 | `forbidden` | Valid key, action not permitted |
| 403 | `invalid_customer` | Market data: the feed has no record of your account. A retry gets the same answer |
| 404 | `not_found` | Unknown resource, or not visible to this key |
| 409 | `order_already_created` | `request_uuid` reused; `data` has the existing `order_id` |
| 409 | `limit_reached` | Per-customer cap; `data.detail` describes it |
| 429 | `throttled` | `data.retry_after` seconds, plus a `Retry-After` header |
| 500 | `server_error` | `data` is `["An error has occurred, token:", "<token>"]`: quote the token to support |
| 503 | `warming` | Market data is loading. Retry with backoff |
| 503 | *(no envelope)* | Upstream unreachable; body is `{"detail": "Service unavailable"}` |

Branch on `code`, not on the HTTP status alone. For `validation_error`, branch
on the keys of `data.validation_errors`.

---

## Rate limits

Per **account**: all keys share one budget. Each limit is a token bucket that
refills continuously, so an idle account can spend a full bucket at once.

| Applies to | Limit |
|---|---|
| All endpoints | 100 req/s burst, 1200 req/min sustained |
| `POST /v2/betslips/` | 10 req/s, and 2000 betslips a day |
| `POST /v2/orders/` | 5 req/s |
| `GET /v2/offers/` | 4 requests open at once |

The betslip and order limits are their own budgets: a busy market-data
poller never throttles placement. Every other endpoint, market data
included, shares the general budget. Budgets are keyed on the account, not
the address, so several hosts do not multiply them. Success responses carry
**no** remaining-quota header: track your own rate. Limits can be raised per
account through support.

The stream at `/v2/stream` has no message-rate limit. See
[`streaming.md`](streaming.md) for its connection limits.

---

## Currencies and price ticks

Stakes are `[currency, amount]` tuples and responses are always **USDT**.

Single-market prices lie on a fixed tick schedule:

| Decimal price | Tick |
|---|---|
| 1.01 - 2 | 0.01 |
| 2 - 3 | 0.02 |
| 3 - 4 | 0.05 |
| 4 - 6 | 0.10 |
| 6 - 10 | 0.20 |
| 10 - 20 | 0.50 |
| 20 - 30 | 1 |
| 30 - 50 | 2 |
| 50 - 100 | 5 |
| 100 - 1000 | 10 |

Band boundaries are exact in decimal price. Feed prices are always on tick.
An order price is a limit: a bet is taken only at that price or better
(higher for `for`, lower for `against`). An off-tick limit moves to the
first tick that honours it: **up** for `for` and **down** for `against`. A
back limit of 7.15 becomes 7.20 and is not filled at 7.00. The moved price is
the one the order runs with and the one the response reports.
`snap_limit()` in [`../examples/_common.py`](../examples/_common.py) does
the same calculation.

Parlay prices are the product of the legs' prices, so they are on no tick
schedule. They are quoted and accepted at full precision, up to 1000.
