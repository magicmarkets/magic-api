# Contributing

Thank you for helping. This repository is a Claude skill for the
MagicMarkets API: `SKILL.md` and `references/` are what Claude reads, and
`examples/` is runnable Python.

## Before you change anything

The published docs are the source of truth:
[`llms-full.txt`](https://magicmarkets.com/llms-full.txt) and
[`openapi.yaml`](https://magicmarkets.com/v2/openapi.yaml). If this skill
disagrees with them, the skill is wrong. Cite the section you relied on in
your pull request.

## Set up

```bash
git clone https://github.com/magicmarkets/magic-api.git
cd magic-api
python3 -m venv .venv && . .venv/bin/activate
make install
```

## Check your change

```bash
make check                          # ruff, offline tests, copy and link checks
MAGIC_API_KEY=... make test-live    # optional: read-only calls to the real API
```

The live tests never create a betslip, heartbeat or order. Do not add a test
that does.

## Rules

- Examples that place or close orders are dry runs by default and need
  `--live`. Keep it that way.
- Read `bet_type` strings off offers. Do not build them by hand in examples.
- Copy rules, checked by `scripts/check_copy.py`: no em or en dashes, no
  emoji, and the brand is one word, MagicMarkets.
- Add a line to `CHANGELOG.md` under a new heading for your change.
