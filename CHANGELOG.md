# Changelog

Notable changes to this skill. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). The API itself is
identified by its URL path (`/v2/`).

## [1.0.0] - 2026-09-29

### Added

- REST market data: `GET /v2/events/` and `GET /v2/offers/`, in `SKILL.md`,
  `references/rest.md` and a new recipe.
- `examples/05-rest-offers.py`: prices over REST, 20 events a call.
- Helpers in `examples/_common.py`: `list_events()`, `list_offers()` and
  `list_orders()` with paging, `upcoming_matches()`, `pick_match()`,
  `tick_size()`, `snap_limit()`, `ApiError` and `run_cli()`.
- Offline tests, read-only live tests (`pytest -m live`), and CI on Python
  3.10-3.14 with ruff, copy checks and link checks.
- `examples/requirements.txt`, `requirements-dev.txt`, `Makefile`,
  `CHANGELOG.md`, `SECURITY.md` and `CONTRIBUTING.md`.

### Changed

- The repository moved to the `magicmarkets` GitHub organisation.
- Off-tick limits: a back limit now moves **up** to the next tick and a lay
  limit **down**, as the published docs state. The skill said the opposite.
- Asian handicap examples use the wire form: lines are 4 x the real line,
  so `for,ah,h,-4` is home -1.0. The skill described `for,ah,h,1` as +1.
- Rate limits: token buckets, 2000 betslips a day, and at most 4 open
  `GET /v2/offers/` requests. The skill said there were no daily caps.
- Order statuses include `partial_void`, `full_void` and `reconciled`.
- Stream errors: the handshake codes (`400 missing_credentials`,
  `401 auth_rejected`, `503 unavailable`) and the 1008 close for a slow
  reader.
- `GET /v2/orders/` is paged (25 a page by default). `04-bulk-close.py`
  now reads every page; before, it could miss open orders.
- Examples 02, 03 and 06 pick the next match that has not started, not the
  first event, which was often a season-long outright.
- `rest()` raises `ApiError` in place of `SystemExit`.
- Counterparty wording follows the published docs.
- No em or en dashes anywhere, checked in CI.

### Removed

- The redirect stubs `examples/01-find-and-bet.py`,
  `examples/05-arb-detector.py`, `references/pricefeed-reference.md` and
  `references/rest-reference.md`. They pointed to the retired
  `pro.` host, the retired `cpricefeed` stream and the `offerhist` endpoint
  that never existed.

## [0.2.0] - 2026-09-03

### Changed

- Rewritten for the current API: the root domain, `/v2/stream`, and
  corrected order fields (`exchange_mode`, `current_score`, heartbeats).

## [0.1.0] - 2026-05-12

- Initial public release.

[1.0.0]: https://github.com/magicmarkets/magic-api/releases/tag/v1.0.0
[0.2.0]: https://github.com/magicmarkets/magic-api/tree/e1fa1a7
[0.1.0]: https://github.com/magicmarkets/magic-api/tree/62ea240
