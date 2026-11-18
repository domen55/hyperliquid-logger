# data-collection Specification

## Purpose

Periodically read the state of configured Hyperliquid wallets from the public Hyperliquid info API
(`https://api.hyperliquid.xyz/info`, no API key) and store it as a time series. This is the same data
Hyperbot shows on `hyperbot.network/trader/<address>`; Hyperbot's own (key-protected) Open API is not used.

## Requirements

### Requirement: Public API only
The collector SHALL obtain all data from the public Hyperliquid info API using only the Python standard
library, and SHALL NOT require any API key or account.

#### Scenario: No credentials configured
- **WHEN** the collector runs with only wallet addresses configured
- **THEN** it collects data without authentication

### Requirement: Collection rounds
The collector SHALL run in rounds. A round SHALL visit every configured wallet sequentially and SHALL tag
everything it stores with one `round_ms` (the round's start time in epoch milliseconds). The first round SHALL
start immediately at startup, later rounds every `interval_seconds` measured from the start of the previous round.

#### Scenario: Two wallets in one round
- **WHEN** a round collects two wallets
- **THEN** all their stored rows share the same `round_ms`

#### Scenario: Round longer than the interval
- **WHEN** a round takes longer than `interval_seconds`
- **THEN** the next round starts after a pause of at least 1 second, never overlapping the previous one

### Requirement: All perp dexes
For each wallet the collector SHALL query the main perp dex and every builder (HIP-3) dex returned by the
`perpDexs` request, so that positions such as `xyz:TSLA` are included. The main dex SHALL always be stored, even
when it is empty, so that a spot-only or new wallet shows up; builder dexes SHALL be stored only when they have
positions, equity or open orders.

#### Scenario: Wallet with positions on the xyz dex
- **WHEN** a wallet holds positions on the main dex and on dex `xyz`
- **THEN** both sets of positions are stored for that round, with coins keeping their dex prefix (`xyz:TSLA`)

#### Scenario: Empty dex
- **WHEN** a builder dex returns no positions, zero account value and no open orders for the wallet
- **THEN** no account row is stored for that dex

#### Scenario: Empty main dex
- **WHEN** the main dex has no positions, zero equity and no open orders
- **THEN** an account row with zero values is still stored for that round

### Requirement: Data captured per wallet and round
For each dex the collector SHALL capture the account summary (`clearinghouseState`), the number of open orders
(`openOrders`) and every perp position; once per wallet and round it SHALL also capture the spot balances
(`spotClearinghouseState`).

#### Scenario: Derived values
- **WHEN** a position is stored
- **THEN** `side` is `long` for a positive size and `short` otherwise, and `mark_px` is `position_value / |szi|`
- **AND** the account row's `leverage` is `total_ntl_pos / account_value` (null when equity is zero)

### Requirement: Atomic rounds per wallet
All rows of one wallet's round (every dex and the spot balances) SHALL be written in a single database
transaction, and only after every API call for that wallet has succeeded.

#### Scenario: One dex fails
- **WHEN** the request for one dex of a wallet fails after all retries
- **THEN** nothing of that wallet's round is written and the failure is reported as an error event

#### Scenario: Reader during a round
- **WHEN** the dashboard reads while a round is being written
- **THEN** it never sees a wallet with only some of its dexes

### Requirement: Idempotent snapshots
Writes SHALL use `INSERT OR IGNORE` on the table keys, so storing the same exchange timestamp twice does not
create duplicates.

#### Scenario: Same snapshot stored twice
- **WHEN** the same wallet snapshot with the same exchange time is stored twice
- **THEN** each table keeps one row per key

### Requirement: Optional fills
When `fills` is enabled for a wallet (default off), the collector SHALL fetch executions with
`userFillsByTime`, resuming at the newest stored fill time + 1 ms. On the first run it SHALL start at
`now - backfill_hours`. It SHALL page through results of up to 2000 fills and SHALL fetch at most 10 pages per round.

#### Scenario: Overlapping fills
- **WHEN** a page contains fills that are already stored
- **THEN** they are not duplicated (key `address, tid`)

#### Scenario: Busy wallet
- **WHEN** more than 20000 new fills exist
- **THEN** the remainder is fetched in the following rounds

### Requirement: Resilient HTTP
Each API call SHALL have a 30 s timeout and SHALL be retried up to 5 attempts with exponential backoff
(1 s, 2 s, 4 s, ...) on HTTP 429/500/502/503/504, network errors, timeouts and invalid JSON. Other HTTP
errors SHALL fail immediately.

#### Scenario: Rate limited
- **WHEN** the API answers 429 and then 200
- **THEN** the call succeeds on the second attempt and both attempts are reported to diagnostics

### Requirement: Failure isolation
A failure for one wallet SHALL NOT stop the round for other wallets nor the collector loop.

#### Scenario: Network down
- **WHEN** every request fails during a round
- **THEN** an error event is recorded per wallet, the previous data is untouched and the next round runs on schedule

### Requirement: Standalone CLI
`logger.py` SHALL be usable without the dashboard: `python logger.py <addr...> [--db FILE] [--interval S]
[--once] [--no-fills] [--backfill-hours N]`.

#### Scenario: Single snapshot
- **WHEN** it is run with `--once`
- **THEN** it stores one snapshot per address and exits

### Requirement: Empty wallet warning
When a wallet has no positions, zero equity, no open orders and no spot balances in a round, the collector SHALL
record a WARNING event naming the wallet and suggesting that the address may be wrong, and SHALL mark the wallet
with that note until data appears. It SHALL NOT fail the round.

#### Scenario: Mistyped address
- **WHEN** a valid-looking address that has never been used on Hyperliquid is tracked
- **THEN** each round records a WARNING `snapshot` event and the wallet shows the note on the dashboard
