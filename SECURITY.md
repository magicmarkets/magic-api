# Security

## Reporting a problem

Report a security problem in this skill or its examples through GitHub
[private vulnerability reporting](https://github.com/magicmarkets/magic-api/security/advisories/new).
Do not open a public issue for it.

For a problem in the MagicMarkets API or the exchange itself, contact
MagicMarkets support from your account.

## API keys

- Never commit an API key, and never paste one into an issue. The examples
  read the key from `MAGIC_API_KEY` only.
- The stream URL carries the key as `?api_key=`. Do not log stream URLs.
- A key can place and close orders with real USDT. If a key leaks, delete it
  on the website (Settings, API) and create a new one.
- The tests use a placeholder key. CI never calls the live API.
