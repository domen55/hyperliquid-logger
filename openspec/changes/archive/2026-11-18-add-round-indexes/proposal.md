## Why

A simulated month of data (43,200 rounds, 7.7 M rows) showed that every query for one round of a wallet scans
all rows of that wallet: the positions table took 1,041 ms, the summary cards 247 ms and the collector's
comparison with the previous round 518 ms, growing linearly with history. The existing index
`position_snapshot (address, coin, round_ms)` cannot seek by `round_ms`, and `spot_snapshot` has no index on it.
Position trends (see `add-position-trends`) read several older rounds per request and would multiply this.

## What Changes

- Add indexes `position_snapshot (address, round_ms)` and `spot_snapshot (address, round_ms)`.
- Existing databases get them automatically on the next start (`CREATE INDEX IF NOT EXISTS`).

## Capabilities

### Modified Capabilities
- `data-storage`: the "Lookup indexes" requirement lists the two new indexes.

## Impact

`logger.py` schema, one test. Measured on the simulated month: the three queries drop to 0.0-0.3 ms; the index
build took 5.6 s and adds about 20 % to the file size.
