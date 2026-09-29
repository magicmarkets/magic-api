#!/usr/bin/env python3
"""
05: Read prices over REST, without a socket.

    GET /v2/events/  ->  pick matches  ->  GET /v2/offers/

Good for scripts, reports and one-off checks. A reply can be about 4 seconds
behind the stream, so use the stream (02, 06) for anything price-sensitive.

Rules this shows:

  * One /v2/offers/ call names up to 20 events. That costs the same as one
    event, and an account can have only 4 of these calls open at once.
  * A bet_type from /v2/offers/ goes straight into POST /v2/betslips/.
  * `market_type` and `min_liquidity` filter on the server.

Usage:
    export MAGIC_API_KEY=...
    python 05-rest-offers.py                  # 5 football matches, main markets
    python 05-rest-offers.py tennis 10        # 10 tennis matches
    python 05-rest-offers.py fb 20 --all      # every market, not only the main ones
"""

import sys
from collections import defaultdict

from _common import best, label, list_events, list_offers, run_cli, upcoming_matches, verify_key

# Match result, Asian handicap and totals. Other sports use other families.
MAIN_MARKETS = ["wdw", "ah", "ou", "ml"]


def main(sport, count, all_markets):
    verify_key()

    matches = upcoming_matches(list_events(sport=sport, ir_status="pre_event"))[:count]
    if not matches:
        sys.exit(f"No priced {sport} matches that have not started.")

    filters = {} if all_markets else {"market_type": MAIN_MARKETS}
    offers = list_offers(sport, [e["event_id"] for e in matches], min_liquidity=10, **filters)

    by_event = defaultdict(list)
    for o in offers:
        by_event[o["event_id"]].append(o)

    for ev in matches:
        print(f"\n{ev.get('start_time')}  {label(ev)}  ({ev['event_id']})")
        rows = by_event.get(ev["event_id"], [])
        if not rows:
            print("  no offers with 10 USDT or more")
        for o in rows:
            b = best(o["price_list"])
            depth = sum(level["effective"]["max"][1] for level in o["price_list"])
            levels = len(o["price_list"])
            print(f"  {o['bet_type']:<24} {b['price']:>7.2f}   {depth:>10.2f} USDT over {levels} prices")


if __name__ == "__main__":
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_cli(
        main,
        sport=positional[0] if positional else "fb",
        count=int(positional[1]) if len(positional) > 1 else 5,
        all_markets="--all" in sys.argv,
    )
