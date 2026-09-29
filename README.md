# MagicMarkets API: Claude Skill

[![CI](https://github.com/magicmarkets/magic-api/actions/workflows/ci.yml/badge.svg)](https://github.com/magicmarkets/magic-api/actions/workflows/ci.yml)

A drop-in Claude skill for the **MagicMarkets** sports markets exchange:
**zero fees**, USDT-denominated, REST + WebSocket. Built so an LLM can
write a working trading tool against the API the first time you ask.

```
              +----------------------------------------------+
              |  magicmarkets.com                            |
              |                                              |
  REST   -->  |  /v2/events/       events with prices        |
  REST   -->  |  /v2/offers/       stake at each price       |
  REST   -->  |  /v2/betslips/     quote a selection         |
  REST   -->  |  /v2/orders/       place / close trades      |
  REST   -->  |  /v2/heartbeats/   deadman's switch          |
  REST   -->  |  /v2/balance/      balance & open stake      |
  wss:// -->  |  /v2/stream        live offers, quotes, fills|
              +----------------------------------------------+
```

## What it enables

- **Discover events**: `GET /v2/events/`, or the stream's initial sync.
- **Read prices**: `GET /v2/offers/` for scripts and reports; the stream for
  a live book built from `offer`, `remove_offer` and `clear_events`.
- **Place orders**: back, lay or parlay, with idempotency via `request_uuid`.
- **Run protected bots**: heartbeats that close open orders if the bot dies.
- **Handle failure properly**: handshake codes, in-band error codes, 1008
  and silent closes, reconnect-and-re-register, rate limits.

This skill is for the trading API. The read-only data feed at
`data.magicmarkets.com` is a separate product with its own skill:
[magicmarkets/magicmarkets-data-feed](https://github.com/magicmarkets/magicmarkets-data-feed).

## Source of truth

MagicMarkets publishes complete, current documentation. This skill is a
working guide over it, not a replacement: it tells Claude to fetch the real
docs for exact schemas.

| URL | What |
|-----|------|
| [`/docs`](https://magicmarkets.com/docs) | Documentation site |
| [`/llms.txt`](https://magicmarkets.com/llms.txt) | Index of the machine-readable docs |
| [`/llms-full.txt`](https://magicmarkets.com/llms-full.txt) | Full API reference (about 150 KB of Markdown) |
| [`/v2/openapi.yaml`](https://magicmarkets.com/v2/openapi.yaml) | OpenAPI 3.1: 20 paths |

## Install

Clone into your Claude skills directory. The folder name must match the
`name:` in `SKILL.md`, which is `magicmarkets-magic-api`:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/magicmarkets/magic-api.git \
  ~/.claude/skills/magicmarkets-magic-api
```

Auto-loads in **Claude Code** (`~/.claude/skills/` user-wide, or
`.claude/skills/` per-project: no restart needed) and any host using the same
layout. For **Claude Desktop**, add the folder in Settings, Skills.

To update an existing install:

```bash
git -C ~/.claude/skills/magicmarkets-magic-api pull
```

### Verify

```bash
ls ~/.claude/skills/magicmarkets-magic-api/SKILL.md

# smoke-test your key (Settings -> API on magicmarkets.com)
curl -H "X-Api-Key: $MAGIC_API_KEY" https://magicmarkets.com/v2/balance/
```

Then ask Claude something like *"using the MagicMarkets API, what's tradeable
right now?"*

## Layout

```
SKILL.md                    concepts, flow, gotchas: what Claude reads first
references/rest.md          REST endpoints, market data, schemas, errors, limits
references/streaming.md     WebSocket protocol in full
references/recipes.md       task-shaped patterns
examples/                   runnable Python (03 and 04 dry-run by default)
tests/                      offline tests, plus read-only live tests (-m live)
scripts/                    copy and link checks used by CI
```

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
make install        # pip install -r requirements-dev.txt
make check          # ruff, offline tests, copy and link checks
MAGIC_API_KEY=... make test-live   # read-only calls to the real API
```

CI runs the offline tests on Python 3.10-3.14. It never calls the live API.
See [CHANGELOG.md](CHANGELOG.md) for what changed.

## Licence

MIT: see [LICENSE](LICENSE).
