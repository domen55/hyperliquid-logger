# diagnostics Specification

## Purpose

Make it visible, while developing and operating the collector, whether data arrives from the exchange: a live
event stream in the dashboard and a log file.

## Requirements

### Requirement: Structured events
The application SHALL record events with `id` (increasing), `ts`, `level` (DEBUG, INFO, WARNING, ERROR), `kind`,
`msg` and a `data` object. Kinds: `start`, `config`, `round`, `snapshot`, `position`, `fills`, `error`, `http`,
`web`. The newest 3000 events SHALL be kept in memory.

#### Scenario: Event overflow
- **WHEN** more than 3000 events are recorded
- **THEN** the oldest are dropped and ids keep increasing

### Requirement: Round and snapshot events
Each round SHALL emit a start and a done event (with duration in ms). Each wallet SHALL emit a `snapshot` event
with its number of positions, equity, position value, uPnL, open orders and duration, or an `error` event when
it failed.

#### Scenario: Successful round
- **WHEN** a round finishes for a wallet with 133 positions
- **THEN** an INFO `snapshot` event states 133 positions and the wallet's equity

### Requirement: Position change events
After each snapshot the collector SHALL compare the wallet's positions with the previous round and emit a
`position` event for every position that was opened (`OPENED`), closed (`CLOSED`) or changed size
(`old -> new (+/-delta)`). The first round of a wallet has nothing to compare and emits none.

#### Scenario: Size changed
- **WHEN** a BTC size goes from -2 to -2.5 between rounds
- **THEN** one event reads `BTC size -2.0000 -> -2.5000 (-0.5000)`

### Requirement: HTTP call events
Every Hyperliquid request SHALL produce an event: DEBUG `http` with request type, dex, latency and size on
success; WARNING `http` with the error and attempt number on a failed attempt.

#### Scenario: Retry
- **WHEN** a request fails with HTTP 429 and succeeds on the next attempt
- **THEN** a WARNING event and a DEBUG event are recorded

### Requirement: Log file
Events SHALL also be logged to the console (INFO and above) and to `<log_dir>/hyperliquid-logger.log`
(default `logs/`), rotating at 2 MB with 5 backups. The file level SHALL follow `log_level` (default `DEBUG`,
which includes HTTP calls; `INFO` leaves them out). The application's own messages SHALL be ASCII so Windows consoles do not fail.

#### Scenario: Reduce noise
- **WHEN** `log_level` is `INFO`
- **THEN** HTTP call lines are not written to the file

### Requirement: Events API
`GET /api/events?after=<id>&limit=<n>` SHALL return events newer than `id` (at most `limit`, default 500, newest
kept) and the `last_id` to continue from. `GET /api/status` SHALL include collector status: number of rounds,
duration of the last round, time of the next round, start time and the log file path.

#### Scenario: Polling
- **WHEN** the client passes the `last_id` it received
- **THEN** only events recorded since then are returned

### Requirement: Debug drawer
The dashboard SHALL have a **Debug** button that opens a bottom panel with the live event stream, polled every
2 s while open. The panel SHALL show round number, last duration, countdown to the next round, interval and the
log file path; hide HTTP calls by default with a "HTTP calls" toggle; and offer Pause, Clear and Close. It SHALL
colour warnings, errors and position changes, keep scrolling to the newest line unless the user scrolled up, and
show an event's `data` as a tooltip.

#### Scenario: Watching for data
- **WHEN** the user opens Debug during a round
- **THEN** snapshot and position events appear within a few seconds of being recorded

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

### Requirement: Dashboard URLs and exposure notice
The start banner and `--check` SHALL list the URLs under which the dashboard can be opened (loopback and, when the
host is not loopback-only, this computer's LAN addresses). When the server is reachable from the network they SHALL
state that the dashboard has no password, whether editing from other devices is on, and that the Windows Firewall
may need to allow Python on private networks.

#### Scenario: Exposed on the network
- **WHEN** `host` is `0.0.0.0`
- **THEN** the banner shows `http://127.0.0.1:8765` and `http://<LAN IP>:8765` and the no-password notice

#### Scenario: Local only
- **WHEN** `host` is `127.0.0.1`
- **THEN** only the loopback URL is listed and no exposure notice is shown
