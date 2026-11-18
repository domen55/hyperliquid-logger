## Why

Starting the app and finding out why nothing updates currently needs knowledge of the code: there are no run
instructions, the console is flooded with per-position lines, errors are raw Python reprs, a second copy of the app
fails with a stack trace (after its collector has already started writing to the same database), and the log is
only reachable as a file.

## What Changes

- Run instructions in Slovenian (`NAVODILA.md`) and `start.cmd` / `check.cmd` launchers.
- A calm console: start banner, one line per round and wallet, a "N position changes" summary, warnings and errors;
  the individual position changes and HTTP calls only with `--verbose`.
- Errors carry a plain-language hint (network, rate limit, server error, locked or read-only database, unexpected
  answer) and the traceback in the event data.
- `python app.py --check`: a self-check that prints OK / FAIL for config, port, database, Hyperliquid API, every
  wallet and recent log errors, and exits 0 or 1.
- The port is bound before the collector starts; if it is taken the app says so and exits, so two copies can never
  write to the same database. An invalid `config.json` at startup is reported in one line, without a traceback.
- `/api/log` returns the tail of the log file and the Debug panel links to it, so errors from before the last restart
  are reachable.

## Capabilities

### Modified Capabilities
- `diagnostics`: console output, error hints, self-check, startup failures, log tail.

## Impact

`app.py`, new `check.py`, `static/index.html` (one link), docs and launchers, tests.
