## ADDED Requirements

### Requirement: Readable console
The console SHALL show the start banner (dashboard URL, interval, database and log paths, wallets), one line per
round start and end, one line per wallet snapshot, a summary line "N position changes" per wallet, and all
warnings and errors. Individual position-change events and HTTP-call events SHALL appear on the console only
with `--verbose`; the log file and the Debug panel are not affected by that option.

#### Scenario: Busy market maker
- **WHEN** a wallet's 40 positions change between two rounds
- **THEN** the console shows one summary line for that wallet, not 40 lines

#### Scenario: Verbose
- **WHEN** the app is started with `--verbose`
- **THEN** every position change and every HTTP call is also printed

### Requirement: Error hints
An error event for a failed wallet SHALL contain a plain-language hint when the cause is recognisable: unreachable
API (network, VPN, firewall), rate limiting (HTTP 429), server error (5xx), locked database (another program or a
second copy), read-only database or full disk, and an unexpected API answer. The Python traceback SHALL be kept
in the event data. The wallet's status note on the dashboard SHALL show the hint.

#### Scenario: Internet down
- **WHEN** the API cannot be reached
- **THEN** the error event says that api.hyperliquid.xyz cannot be reached and what to check

### Requirement: Self-check
`python app.py --check` SHALL print one OK, WARN or FAIL line, with a hint on failure, for: Python version,
configuration, port availability, database, Hyperliquid API reachability, every configured wallet (positions and
equity, probed without writing to the real database) and the latest errors in the log file. It SHALL exit with
status 0 when nothing failed and 1 otherwise, and SHALL NOT start the collector or the server.

#### Scenario: Everything fine
- **WHEN** the configuration is valid and the API is reachable
- **THEN** all lines are OK and the exit status is 0

#### Scenario: API unreachable
- **WHEN** the API cannot be reached
- **THEN** the API line is FAIL with a hint, the wallets are reported as not checked, and the exit status is 1

### Requirement: Startup failures are explained
The server port SHALL be bound before the collector starts. When the port is in use the app SHALL print that
another copy is probably running (with the URL and the `port` setting to change) and exit with status 1 without
collecting. When `config.json` is invalid at startup the app SHALL print the file path and the parse error in one
line and exit with status 1, without a traceback.

#### Scenario: Second copy
- **WHEN** a second copy of the app is started while the first one is running
- **THEN** it exits with the port message and does not write to the database

### Requirement: Log tail
`GET /api/log?lines=<n>` SHALL return the last lines (default 300, at most 2000) of the current log file as plain
text, and the Debug panel SHALL link to it.

#### Scenario: After a restart
- **WHEN** the app was restarted and the Debug panel is empty
- **THEN** the log link still shows the events from before the restart
