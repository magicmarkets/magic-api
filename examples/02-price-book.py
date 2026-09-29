#!/usr/bin/env python3
"""
02: Maintain a live price book from the stream.

Demonstrates the three rules that separate a correct book from a subtly
wrong one:

  * "offer" is a FULL REPLACEMENT for its (sport, event_id, bet_type) triple,
    not a delta. Overwrite, never merge.
  * "remove_offer" means that bet type has no liquidity left. Delete it:
    do not leave last-known prices in the book.
  * "clear_events" means the server lost its upstream feed. Drop everything
    and wait for the fresh snapshot.

It watches the next match that has not started, not an outright.

Usage:
    export MAGIC_API_KEY=...
    python 02-price-book.py            # next priced match, any sport
    python 02-price-book.py fb         # next priced football match
"""

import sys

from _common import best, frames, label, open_stream, pick_match, register, run_cli, sync_events, verify_key


def main(sport_filter):
    verify_key()

    with open_stream() as ws:
        ev = pick_match(sync_events(ws), sport_filter)
        if not ev:
            sys.exit("No priced match found.")

        print(f"watching {ev['sport']} {ev['event_id']}: {label(ev)}\n")
        register(ws, ev["sport"], ev["event_id"])

        book = {}
        for tag, p in frames(ws):
            if tag == "offer":
                book[(p["sport"], p["event_id"], p["bet_type"])] = p["price_list"]
            elif tag == "remove_offer":
                book.pop((p["sport"], p["event_id"], p["bet_type"]), None)
            elif tag == "clear_events":
                print("!! upstream feed lost: clearing book")
                book.clear()
                continue
            elif tag == "response" and p and p.get("status") == "error":
                sys.exit(f"stream error: {p.get('code')}")
            else:
                continue

            render(label(ev), book)

    print("stream closed: reconnect and re-register (registrations do not persist)")


def render(title, book):
    print("\033[2J\033[H", end="")  # clear screen
    print(title)
    print(f"{'bet_type':<28} {'best':>8} {'min':>10} {'max':>12}   depth")
    print("-" * 74)
    for (_sport, _eid, bet_type), price_list in sorted(book.items()):
        b = best(price_list)
        if not b:
            continue
        mn = f"{b['min'][1]:.2f}" if b.get("min") else "-"
        mx = f"{b['max'][1]:.2f}" if b.get("max") else "-"
        print(f"{bet_type:<28} {b['price']:>8.2f} {mn:>10} {mx:>12}   {len(price_list)}")


if __name__ == "__main__":
    run_cli(main, sys.argv[1] if len(sys.argv) > 1 else None)
