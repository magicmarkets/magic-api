#!/usr/bin/env python3
"""
06: Register many events on one socket and stream best-of-book.

Shows the multi-event patterns that matter:
  * one socket, many registrations: never a socket per event
  * the registered-event cap is counted across ALL your connections
  * registrations do NOT survive a reconnect: re-register after any drop
  * reconnect with exponential backoff; a silent close looks like a clean EOF

It watches the next matches that have not started, not outrights.

Usage:
    export MAGIC_API_KEY=...
    python 06-multi-stream.py               # the next 10 priced matches
    python 06-multi-stream.py fb 20         # the next 20 football matches
"""

import sys
import time

from _common import (
    best,
    frames,
    label,
    open_stream,
    register,
    run_cli,
    sync_events,
    upcoming_matches,
    verify_key,
)


def main(sport_filter, limit):
    verify_key()

    delay = 1
    while True:
        try:
            run(sport_filter, limit)
            delay = 1
        except (KeyboardInterrupt, SystemExit, BrokenPipeError):
            raise
        except Exception as exc:
            print(f"!! {type(exc).__name__}: {exc}")
        print(f"reconnecting in {delay}s")
        time.sleep(delay)
        delay = min(delay * 2, 60)


def run(sport_filter, limit):
    with open_stream() as ws:
        events = upcoming_matches(sync_events(ws), sport_filter)[:limit]
        if not events:
            raise SystemExit("No priced matches found.")

        names = {}
        for ev in events:
            # Re-register on every (re)connect: the server does not remember
            # registrations across connections.
            register(ws, ev["sport"], ev["event_id"])
            names[(ev["sport"], ev["event_id"])] = label(ev)
        print(f"registered {len(events)} event(s)\n")

        book = {}
        for tag, p in frames(ws):
            if tag == "offer":
                book[(p["sport"], p["event_id"], p["bet_type"])] = p["price_list"]
                show(names, p)
            elif tag == "remove_offer":
                book.pop((p["sport"], p["event_id"], p["bet_type"]), None)
            elif tag == "clear_events":
                print("!! upstream feed lost: clearing")
                book.clear()
            elif tag == "response" and p and p.get("status") == "error":
                code = p.get("code")
                if code == "customer_event_limit_exceeded":
                    raise SystemExit(
                        "registered-event cap hit (counted across all your connections): unregister first"
                    )
                print(f"!! stream error: {code}")

        # frames() returning means the socket closed, possibly silently.
        raise ConnectionError("stream closed")


def show(names, offer):
    b = best(offer["price_list"])
    if not b:
        return
    who = names.get((offer["sport"], offer["event_id"]), offer["event_id"])
    print(f"{who[:38]:<38} {offer['bet_type']:<26} {b['price']:>7.2f}")


if __name__ == "__main__":
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_cli(
        main,
        sport_filter=positional[0] if positional else None,
        limit=int(positional[1]) if len(positional) > 1 else 10,
    )
