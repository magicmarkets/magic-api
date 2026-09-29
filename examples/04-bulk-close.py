#!/usr/bin/env python3
"""
04: Inspect and bulk-close open orders.

DRY RUN BY DEFAULT: lists what would close. Pass --live to actually close.

GET /v2/orders/ is paged (25 orders a page by default), so this reads every
page before it filters. It prefers close_many/ over close_all/: close_all
takes no filter and cannot be undone, so this names each order unless you
ask for everything.

Usage:
    export MAGIC_API_KEY=...
    python 04-bulk-close.py                 # list all open orders
    python 04-bulk-close.py fb              # list open football orders
    python 04-bulk-close.py fb --live       # close them
    python 04-bulk-close.py --all --live    # close_all/ (no filter)
"""

import sys

from _common import list_orders, rest, run_cli, verify_key


def main(sport_filter, live, use_close_all):
    verify_key()

    if use_close_all:
        if not live:
            print("DRY RUN: would call POST /orders/close_all/ (every open order)")
            return
        rest("POST", "/orders/close_all/")
        print("close_all/ sent")
        return

    filters = {"sport": sport_filter} if sport_filter else {}
    still_open = [o for o in list_orders(**filters) if not o.get("closed")]

    if not still_open:
        print("No open orders matched.")
        return

    print(f"{len(still_open)} open order(s):")
    for o in still_open:
        print(
            f"  {o['order_id']:<12} {o.get('sport', '?'):<9} "
            f"{o.get('bet_type', '?'):<26} @{o.get('want_price')} "
            f"{o.get('want_stake')}"
        )

    if not live:
        print("\nDRY RUN: pass --live to close these.")
        return

    ids = [o["order_id"] for o in still_open]
    rest("POST", "/orders/close_many/", json={"order_ids": ids})
    print(f"close_many/ sent for {len(ids)} order(s)")
    # Closing an already-closed order returns 400 order_closed, which is
    # distinct from 404 not_found.


if __name__ == "__main__":
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_cli(
        main,
        sport_filter=positional[0] if positional else None,
        live="--live" in sys.argv,
        use_close_all="--all" in sys.argv,
    )
