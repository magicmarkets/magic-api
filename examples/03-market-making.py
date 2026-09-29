#!/usr/bin/env python3
"""
03: Place an order end to end, under heartbeat protection.

    verify key -> stream -> sync -> register_event -> pick offer
      -> POST /betslips/ -> wait for pmm quote -> POST /orders/ -> watch order

DRY RUN BY DEFAULT. The dry run only reads: it creates no betslip, no
heartbeat and no order. Nothing is placed unless you pass --live. With
--live this commits real USDT.

It picks the next match that has not started, and a back (`for`) offer
priced between 1.50 and 4.00, so the demo does not land on an outright.

Usage:
    export MAGIC_API_KEY=...
    python 03-market-making.py fb              # dry run, football
    python 03-market-making.py fb 2.00 --live  # place 2 USDT for real
"""

import json
import sys
import threading
import time

from _common import (
    TERMINAL_STATUSES,
    ApiError,
    best,
    frames,
    label,
    new_request_uuid,
    open_stream,
    pick_match,
    register,
    rest,
    run_cli,
    sync_events,
    verify_key,
)


class Heartbeat:
    """Deadman's switch. If it expires, the server closes all open orders.

    Refreshed on its own thread so a stall in the trading loop cannot let it
    lapse. timeout must be 10-300 seconds.
    """

    def __init__(self, timeout=60):
        self.timeout = timeout
        self.id = None
        self._stop = threading.Event()

    def __enter__(self):
        self.id = rest("POST", "/heartbeats/", json={"timeout": self.timeout})["heartbeat_id"]
        print(f"heartbeat {self.id} ({self.timeout}s)")
        threading.Thread(target=self._loop, daemon=True).start()
        return self

    def _loop(self):
        while not self._stop.wait(self.timeout / 3):
            try:
                rest("POST", f"/heartbeats/{self.id}/refresh/")
            except ApiError as exc:
                # An expired heartbeat cannot be refreshed: its close-out has run.
                print(f"!! heartbeat refresh failed: {exc}")
                return

    def __exit__(self, *exc):
        self._stop.set()
        try:
            rest("DELETE", f"/heartbeats/{self.id}/")
            print(f"heartbeat {self.id} released")
        except ApiError:
            pass


def main(sport_filter, live, stake_amount):
    verify_key()

    with open_stream() as ws:
        ev = pick_match(sync_events(ws), sport_filter)
        if not ev:
            sys.exit("No priced match found.")

        print(f"event: {ev['sport']} {ev['event_id']}: {label(ev)}")
        register(ws, ev["sport"], ev["event_id"])

        offer = wait_for_offer(ws)
        if not offer:
            sys.exit("No back offer between 1.50 and 4.00 on that event.")

        b = best(offer["price_list"])
        print(f"offer:  {offer['bet_type']}  best={b['price']}  max={b['max']}")

        if not live:
            print("\nDRY RUN: pass --live to place. Would send:")
            print(
                json.dumps(
                    {
                        "betslip": {k: offer[k] for k in ("sport", "event_id", "bet_type")},
                        "order": {
                            "price": b["price"],
                            "stake": ["USDT", stake_amount],
                            "duration": 5.0,
                            "request_uuid": "<fresh uuid>",
                        },
                    },
                    indent=2,
                )
            )
            return

        with Heartbeat(60):
            place(ws, offer, stake_amount)


def wait_for_offer(ws, timeout=20):
    """First back offer whose best price is between 1.50 and 4.00."""
    deadline = time.time() + timeout
    for tag, p in frames(ws):
        if tag == "offer" and p["bet_type"].startswith("for,"):
            b = best(p.get("price_list"))
            if b and 1.5 <= b["price"] <= 4.0:
                return p
        if tag == "response" and p and p.get("status") == "error":
            sys.exit(f"register_event failed: {p.get('code')}")
        if time.time() > deadline:
            return None
    return None


def place(ws, offer, stake_amount):
    betslip = rest(
        "POST",
        "/betslips/",
        json={
            "sport": offer["sport"],
            "event_id": offer["event_id"],
            "bet_type": offer["bet_type"],
            "betslip_type": "normal",
        },
    )
    bs_id = betslip["betslip_id"]
    print(f"betslip {bs_id} (expires {betslip.get('expiry_ts')})")

    # The create response carries no prices. The quote arrives on the socket.
    quote, deadline = None, time.time() + 15
    for tag, p in frames(ws):
        if tag == "pmm" and p.get("betslip_id") == bs_id and p.get("price_list"):
            quote = p
            break
        if tag == "betslip_closed" and p.get("betslip_id") == bs_id:
            sys.exit(f"betslip closed before quoting: {p.get('close_reason')}")
        if time.time() > deadline:
            break
    if not quote:
        sys.exit("no quote within 15s: no liquidity for this selection")

    price = best(quote["price_list"])["price"]
    order = rest(
        "POST",
        "/orders/",
        json={
            "betslip_id": bs_id,
            "price": price,
            "stake": ["USDT", stake_amount],
            "duration": 5.0,
            "request_uuid": new_request_uuid(),  # safe to retry on timeout
        },
    )
    order_id = order["order_id"]
    print(f"order {order_id} placed at {price}: watching")

    for tag, p in frames(ws):
        if tag == "order" and p.get("order_id") == order_id:
            print(f"  {p.get('status')}  {p.get('close_reason') or ''}")
            if p.get("status") in TERMINAL_STATUSES:
                # 'done' means filled, not settled: profit_loss finalises later.
                # 'failed' usually means the limit expired unmatched: see close_reason.
                print(f"  price={p.get('price')} stake={p.get('stake')} pl={p.get('profit_loss')}")
                return


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_cli(
        main,
        sport_filter=args[0] if args else None,
        live="--live" in sys.argv,
        stake_amount=float(args[1]) if len(args) > 1 else 1.0,
    )
