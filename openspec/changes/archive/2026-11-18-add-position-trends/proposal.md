## Why

The positions table shows the current size and the change since the previous round only. To judge what a wallet
is doing (is it adding to the ETH short or reducing it?) the owner wants a per-position trend over 15 minutes,
2 hours and 1 day, visible directly in the table.

## What Changes

- `/api/positions` returns, for every position and for each of 15 m, 2 h and 1 d, the values the position had in
  the round at or just before `latest - window` (size, position value, uPnL) and whether the position did not exist
  then.
- The positions table gets three trend columns (15 min, 2 h, 1 day) and a selector for the metric shown in them:
  size (default), position value or uPnL. Each cell shows the absolute and the percentage change; the tooltip
  shows the earlier value and how old the reference round is.
- Windows without enough history show a dash.

## Capabilities

### Modified Capabilities
- `dashboard`: new requirement "Position trends"; `/api/positions` gains a `trend` field.

## Impact

`app.py` (`q_positions`), `static/index.html`, tests. No schema change (uses `add-round-indexes` for speed).
