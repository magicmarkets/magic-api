#!/usr/bin/env python3
"""
01: Discover what is tradeable right now.

Two ways to list the events that currently have prices. Both return the same
set:

  * GET /v2/events/ (default): paged REST, with filters for sport,
    competition, event, start time and in-play status.
  * The stream's initial sync (--stream): connect, collect ["event", ...]
    entries until ["sync", ...]. Use this when you keep the socket open
    anyway, because it then tells you about changes as they happen.

Only events with prices appear, not the full fixture list.

Usage:
    export MAGIC_API_KEY=...
    python 01-discover.py                 # everything priced, via REST
    python 01-discover.py fb tennis       # only these sports
    python 01-discover.py fb --stream     # the same, via the stream sync
"""

import sys
from collections import Counter

from _common import label, list_events, open_stream, run_cli, sync_events, verify_key


def main(sports: set[str], use_stream: bool):
    verify_key()

    if use_stream:
        with open_stream() as ws:
            events = sync_events(ws)
        if sports:
            events = [e for e in events if e.get("sport") in sports]
    else:
        # A list value is sent as a repeated `sport` parameter.
        events = list_events(sport=sorted(sports)) if sports else list_events()

    if not events:
        print("No priced events." + (f" (filtered to {', '.join(sorted(sports))})" if sports else ""))
        return

    by_sport = Counter(e.get("sport") for e in events)
    source = "stream sync" if use_stream else "GET /v2/events/"
    print(f"{len(events)} priced events across {len(by_sport)} sports ({source})")
    print("  " + "  ".join(f"{s}={n}" for s, n in by_sport.most_common()))
    print()

    for e in sorted(events, key=lambda e: e.get("start_time") or ""):
        kind = "OUT" if e.get("event_type") == "multirunner" else "   "
        live = "IR " if e.get("ir_status") == "in_running" else "   "
        print(
            f"{e.get('start_time', '?'):<21} {kind}{live}{e.get('sport', '?'):<9} "
            f"{e.get('competition_name', '')[:28]:<28} {label(e)}"
        )
        print(f"{'':27}id: {e.get('event_id')}")


if __name__ == "__main__":
    run_cli(main, {a for a in sys.argv[1:] if not a.startswith("--")}, "--stream" in sys.argv)
