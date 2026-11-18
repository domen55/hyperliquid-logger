## MODIFIED Requirements

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
