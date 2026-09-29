"""Shared test helpers: a fake REST transport, a fake WebSocket, and example loading.

No test here touches the network, except those marked `live`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(EXAMPLES))

# A placeholder key with characters that must be URL-encoded. No real keys anywhere.
FAKE_KEY = "EXAMPLE-key/with+odd&chars=1"


@pytest.fixture(autouse=True)
def fake_key(request, monkeypatch):
    """Every test except the live ones sees a placeholder key."""
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setenv("MAGIC_API_KEY", FAKE_KEY)


class FakeResponse:
    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not JSON")
        return self._body


class FakeApi:
    """Records each request and answers from a handler(method, path, params, json)."""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict] = []

    def __call__(self, method, url, headers=None, timeout=None, params=None, json=None):
        path = urlsplit(url).path.removeprefix("/v2")
        call = {"method": method, "path": path, "params": params or {}, "json": json, "headers": headers}
        self.calls.append(call)
        status, body = self.handler(method, path, params or {}, json)
        return FakeResponse(status, body)

    def paths(self, method: str | None = None) -> list[str]:
        return [c["path"] for c in self.calls if method is None or c["method"] == method]


@pytest.fixture
def fake_api(monkeypatch):
    """Install a FakeApi. Call it with a handler; returns the FakeApi."""
    import requests

    def install(handler):
        api = FakeApi(handler)
        monkeypatch.setattr(requests, "request", api)
        return api

    return install


def ok(data):
    return 200, {"status": "ok", "data": data}


class FakeSocket:
    """Plays a list of frames from recv(), then raises as a closed socket does."""

    def __init__(self, frames: list):
        self._frames = [f if isinstance(f, str) else json.dumps(f) for f in frames]
        self.sent: list = []

    def recv(self):
        if not self._frames:
            raise ConnectionError("closed")
        return self._frames.pop(0)

    def send(self, text):
        self.sent.append(json.loads(text))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def envelope(*entries) -> dict:
    return {"ts": 1759122000.0, "data": list(entries)}


def load_example(name: str):
    """Import an example whose file name starts with a digit, such as 03-market-making.py."""
    path = EXAMPLES / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def query(url: str) -> dict:
    return parse_qs(urlsplit(url).query)


def event(event_id: str, start: str, sport: str = "fb", **extra) -> dict:
    home, away = f"Home {event_id[-1]}", f"Away {event_id[-1]}"
    return {
        "event_type": "normal",
        "sport": sport,
        "event_id": event_id,
        "home": home,
        "away": away,
        "event_name": f"{home} vs. {away}",
        "ir_status": "pre_event",
        "start_time": start,
        **extra,
    }
