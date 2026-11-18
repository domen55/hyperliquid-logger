# data-storage Specification

## Purpose

Persist the collected time series in a single local SQLite file that the collector writes and the dashboard
reads concurrently.

## Requirements

### Requirement: SQLite file with automatic schema
The system SHALL store all data in one SQLite database (path `db` in the configuration, default
`hyperliquid.sqlite` next to the configuration file) and SHALL create the file and schema if missing, with
write-ahead logging enabled so readers are not blocked by the writer.

#### Scenario: First start
- **WHEN** the application starts and the database file does not exist
- **THEN** the file and all tables are created before the dashboard serves requests

### Requirement: Account snapshots
Table `account_snapshot` SHALL hold one row per wallet, dex and exchange timestamp: `ts_ms`, `address`, `dex`
(empty string = main dex), `account_value`, `total_ntl_pos`, `total_margin_used`, `withdrawable`, `leverage`,
`n_positions`, `n_open_orders`, `long_value`, `short_value`, `upnl`, `round_ms`. Primary key:
`(address, dex, ts_ms)`.

#### Scenario: Wallet with two dexes
- **WHEN** a round stores a wallet with positions on `''` and `xyz`
- **THEN** two rows exist for that `round_ms`, one per dex

### Requirement: Position snapshots
Table `position_snapshot` SHALL hold one row per wallet, coin and exchange timestamp: `ts_ms`, `address`,
`coin`, `szi` (signed size, negative = short), `side`, `entry_px`, `mark_px`, `position_value`, `upnl`, `roe`,
`liq_px`, `margin_used`, `leverage`, `leverage_type`, `cum_funding_all_time`, `cum_funding_since_open`,
`round_ms`. Primary key: `(address, ts_ms, coin)`.

#### Scenario: No liquidation price
- **WHEN** the API reports no liquidation price
- **THEN** `liq_px` is NULL

### Requirement: Spot snapshots
Table `spot_snapshot` SHALL hold spot balances per wallet and coin: `ts_ms`, `address`, `coin`, `total`, `hold`,
`entry_ntl`, `round_ms`. Primary key: `(address, ts_ms, coin)`. Balances are stored as coin amounts, not valued in USD.

#### Scenario: Spot balance stored
- **WHEN** a wallet holds 10 USDC with 1 on hold
- **THEN** a row with `total = 10` and `hold = 1` exists for that round

### Requirement: Fills
Table `fill` SHALL hold executions: `address`, `tid`, `oid`, `time_ms`, `coin`, `side`, `dir`, `px`, `sz`,
`start_position`, `closed_pnl`, `fee`, `fee_token`, `crossed`, `hash`. Primary key: `(address, tid)`.

#### Scenario: Duplicate execution
- **WHEN** an execution with an existing `(address, tid)` is stored again
- **THEN** the row count does not change

### Requirement: Numeric values
Values the exchange sends as strings SHALL be stored as REAL; missing or invalid values SHALL become NULL.

#### Scenario: String number
- **WHEN** the API returns `"szi": "-12255.524"`
- **THEN** it is stored as the number -12255.524

### Requirement: Lookup indexes
Indexes SHALL exist on `account_snapshot (address, round_ms)`, `position_snapshot (address, coin, round_ms)`,
`position_snapshot (address, round_ms)`, `spot_snapshot (address, round_ms)` and `fill (address, time_ms)`, so
that both time-range queries for one coin and lookups of one whole round stay fast as data grows. Missing
indexes SHALL be created when the application opens an existing database.

#### Scenario: Series query
- **WHEN** the dashboard asks for one coin's history since a timestamp
- **THEN** the query uses the `(address, coin, round_ms)` index

#### Scenario: Whole round lookup
- **WHEN** the positions or spot balances of one wallet in one round are read
- **THEN** the query seeks by `(address, round_ms)` instead of scanning the wallet's rows

#### Scenario: Existing database
- **WHEN** the application opens a database created before these indexes existed
- **THEN** the indexes are created and no data is lost
