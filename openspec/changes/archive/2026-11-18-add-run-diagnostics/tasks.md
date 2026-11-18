## 1. Tests first

- [x] 1.1 `explain_error` hints for network, 429, 5xx, locked/read-only DB, bad JSON, missing field
- [x] 1.2 Console filter hides position/HTTP events unless verbose; warnings and errors always shown
- [x] 1.3 `collect_once` emits a "N position changes" summary and an error with hint and traceback
- [x] 1.4 `--check` report: all OK (exit 0); API down (exit 1, wallets not checked); bad config (exit 1)
- [x] 1.5 Port in use gives a clear error before anything starts; invalid config at startup is one line
- [x] 1.6 `tail_text` limits lines and bytes; `/api/log` serves it

## 2. Implementation

- [x] 2.1 App: console filter + `--verbose`, `explain_error`, change summary, `bind_server`, startup errors
- [x] 2.2 `check.py` and `--check`
- [x] 2.3 `/api/log` and the Debug panel link

## 3. Docs

- [x] 3.1 `NAVODILA.md` (Slovenian), `start.cmd`, `check.cmd`, README pointer

## 4. Verification

- [x] 4.1 Full test suite green
- [x] 4.2 Live: console output, `--check`, second copy refused
