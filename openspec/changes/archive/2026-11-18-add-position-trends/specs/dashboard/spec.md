## ADDED Requirements

### Requirement: Position trends
`/api/positions` SHALL add to every position a `trend` object with the keys `15m`, `2h` and `1d`. For each
window the reference round is the newest stored round at or before `latest_round - window`. The value for the
window SHALL be `null` when no such round exists or when it is older than 1.5 times the window (history too short
or a gap in collection). Otherwise it SHALL contain `base_ms` (the reference round), the position's earlier `szi`,
`position_value` and `upnl`, and `opened: true` when the position did not exist in the reference round (earlier
values then being 0).

#### Scenario: Enough history
- **WHEN** rounds exist 130, 20, 16, 1 and 0 minutes before the latest round and BTC had sizes -1, -2, -3, -4, -5
- **THEN** BTC's `15m` reference is the round 16 minutes back (size -3) and its `2h` reference the round 130 minutes
  back (size -1)

#### Scenario: Not enough history
- **WHEN** the oldest stored round is only 20 minutes old
- **THEN** the `2h` and `1d` trends are `null` and the `15m` trend is present

#### Scenario: Gap in collection
- **WHEN** the newest round at or before the 15-minute target is 60 minutes old
- **THEN** the `15m` trend is `null`

#### Scenario: Position opened within the window
- **WHEN** a coin is missing in the reference round
- **THEN** its trend has `opened: true` and earlier size 0

### Requirement: Trend columns in the positions table
The positions table SHALL show three trend columns (15 min, 2 h, 1 day) with a metric selector: size (default),
position value or uPnL. A cell SHALL show the absolute change (now minus then) and the percentage change relative
to the earlier absolute value, coloured by the sign of the change; a position opened within the window SHALL be
marked "new"; a missing trend SHALL show a dash. The tooltip SHALL show the earlier and current value and the age
of the reference round.

#### Scenario: Short grew
- **WHEN** an ETH short went from -12,000 to -12,250 over the last 2 hours
- **THEN** the size cell for 2 h shows -250 with its percentage, and the tooltip shows -12,000 -> -12,250

#### Scenario: Switch metric
- **WHEN** the user selects "Position value"
- **THEN** the three columns show USD changes of the position value
