# MagicMarkets: Runnable Examples

Python scripts for the most common MagicMarkets workflows, written against
the live API: REST at `https://magicmarkets.com/v2/`, stream at
`wss://magicmarkets.com/v2/stream`.

## Setup

```bash
pip install -r requirements.txt
export MAGIC_API_KEY="your-api-key"     # Settings -> API on magicmarkets.com
```

Run them from this directory so `_common.py` is importable:

```bash
cd examples && python 01-discover.py
```

Tested on Python 3.10-3.14.

## Scripts

| # | Script | What it does |
|---|--------|--------------|
| - | [`_common.py`](_common.py) | Shared helpers: REST wrapper and paging, envelope-aware frame parsing, match picking, tick snapping |
| 01 | [`01-discover.py`](01-discover.py) | List everything currently priced, via `GET /v2/events/` or the stream sync (`--stream`) |
| 02 | [`02-price-book.py`](02-price-book.py) | Maintain a correct live price book from `offer` / `remove_offer` / `clear_events` |
| 03 | [`03-market-making.py`](03-market-making.py) | Full betslip, quote and order flow under heartbeat protection |
| 04 | [`04-bulk-close.py`](04-bulk-close.py) | Inspect and bulk-close open orders, across every page |
| 05 | [`05-rest-offers.py`](05-rest-offers.py) | Read prices over REST with `GET /v2/offers/`, 20 events a call |
| 06 | [`06-multi-stream.py`](06-multi-stream.py) | Many events on one socket, with reconnect and re-registration |

01, 02, 05 and 06 only read. The examples that watch a market (02, 03, 06)
pick the next match that has not started, not an outright.

## Safety

**03 and 04 are dry-run by default.** They print what they would do and exit.
The dry runs only read: they create no betslip, no heartbeat and no order.
Pass `--live` to actually place or close, which commits real USDT. Read the
output of the dry run first.

`04 --all --live` calls `POST /v2/orders/close_all/`, which takes no filter
and cannot be undone. Without `--all` the script names each order and uses
`close_many/`, so you can see exactly what will close.

## Things these examples exist to demonstrate

- **Every frame is a batch envelope** `{"ts": ..., "data": [...]}`. Iterate
  `data[]` and dispatch on `entry[0]`. Never assume one message per frame.
- **Discovery works over REST or the stream.** Both list the same priced
  events. Trade from the stream, because REST prices can be 4 s behind.
- **Lists are paged.** `GET /v2/events/` and `GET /v2/offers/` page with
  `after`; `GET /v2/orders/` pages with `page`, 25 orders by default.
- **`offer` is a full replacement**, not a delta; `remove_offer` means delete;
  `clear_events` means drop everything you hold.
- **Betslip creation returns no prices.** The quote arrives as a `pmm` message
  on the socket.
- **Registrations do not survive a reconnect.** Re-register every time.
- **A silent close looks like a clean EOF.** Always reconnect with backoff.
- **Always send `request_uuid`** when placing orders, so a retry cannot
  double-place.
