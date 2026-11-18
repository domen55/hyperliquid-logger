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
