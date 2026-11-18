# dashboard Specification

## Purpose

A local web page and JSON API that show the stored time series: account totals, positions and their history,
so changes of values such as `-12,256.0897 ETH` can be followed over time.

## Requirements

### Requirement: Local-only server
The application SHALL serve HTTP on `127.0.0.1` at the configured `port` (default 8765) from the same process
that runs the collector, SHALL answer with `Cache-Control: no-store`, and SHALL serve only `/` (the page) and
`/chart.js` (a vendored Chart.js, so the page works offline) as static files.

#### Scenario: Open the dashboard
- **WHEN** the user opens `http://127.0.0.1:8765/`
- **THEN** the page and its script load without internet access

#### Scenario: Other static path
- **WHEN** a path other than `/` or `/chart.js` outside `/api/` is requested
- **THEN** the server answers 404

### Requirement: Read-only JSON API
The server SHALL expose `GET /api/status`, `/api/summary`, `/api/positions`, `/api/account_series`,
`/api/series` and `/api/events`, opening the database read-only for each request. Query parameters:
`address`, `since` (epoch ms, 0 = all), `coin`, and for events `after` and `limit`. Errors SHALL be answered with
HTTP 500 and `{"error": ...}` and recorded as an event; unknown endpoints with 404.

#### Scenario: Unknown wallet
- **WHEN** `/api/summary` is requested for an address without data
- **THEN** it returns `null` and `/api/positions` returns an empty list

### Requirement: Summary across dexes
`/api/summary` SHALL return, for the wallet's latest round, the sums over all dexes of equity, position value,
margin used, uPnL, long value, short value, positions and open orders, plus leverage (position value / equity)
and the spot balances ordered by total descending.

#### Scenario: Two dexes
- **WHEN** a wallet has equity 32.8 M on the main dex and 13.9 M on `xyz`
- **THEN** the summary equity is 46.7 M

### Requirement: Positions with change since previous round
`/api/positions` SHALL return the positions of the latest round ordered by position value descending, each with
`szi_prev` (size in the previous round, null when absent).

#### Scenario: Position grew
- **WHEN** a short went from -2 to -3 between rounds
- **THEN** the position has `szi = -3` and `szi_prev = -2`

### Requirement: Time series
`/api/account_series` SHALL return per round the summed equity, position value, uPnL and margin used.
`/api/series` SHALL return per round one coin's size, position value, uPnL, mark price, entry price,
liquidation price and ROE. Both SHALL return only rounds at or after `since`, in ascending order, and SHALL
downsample to at most 3000 points while always keeping the newest point.

#### Scenario: Long history
- **WHEN** more than 3000 rounds match
- **THEN** evenly spaced rows are returned and the last row is the newest round

### Requirement: Overview page
The page SHALL provide a wallet selector (labels from the configuration), a time range selector
(1 h, 6 h, 24 h default, 7 d, 30 d, all), eight summary cards (account equity, position value, uPnL, leverage,
margin used, long/short, positions, open orders) and two charts over time: equity with position value, and uPnL.

#### Scenario: Change range
- **WHEN** the user selects 7 d
- **THEN** the charts reload for the last seven days

### Requirement: Positions table and history
The page SHALL list the latest perp positions (symbol, side, size, change vs previous round, position value,
uPnL, ROE, entry, mark, liquidation price, leverage), filterable by symbol. Sizes SHALL be shown with
thousands separators, up to 4 decimals and the symbol (for example `-12,256.0897 ETH`). Clicking a row SHALL show
that position's history as four charts: size, position value, uPnL, and mark with entry price. The largest
position is selected by default.

#### Scenario: Select a position
- **WHEN** the user clicks the ETH row
- **THEN** the four history charts show ETH for the selected range

### Requirement: Charts fit their data
Time axes SHALL span the data (with a small padding), so that a single point or a few points are not stretched
over a huge range, and tick labels SHALL include the date when the span exceeds 36 hours.

#### Scenario: One data point
- **WHEN** only one round exists
- **THEN** the chart shows one point on a short time axis

### Requirement: Live refresh and status
The page SHALL refresh itself every 30 s and SHALL show the time of the last collection, its age and the
interval. It SHALL warn when the last collection is older than 2.5 intervals ("collector looks stalled") or the
wallet has an error, and SHALL retry every 3 s while no data exists yet.

#### Scenario: Stalled collector
- **WHEN** the newest round is older than 2.5 times the interval
- **THEN** the status line is highlighted as a warning

### Requirement: Spot balances
The page SHALL offer a collapsible table of the wallet's spot balances (coin, total, hold) from the latest round.

#### Scenario: Wallet with spot balances
- **WHEN** the user expands "Spot balances"
- **THEN** the balances of the latest round are listed

### Requirement: Position trends
`/api/positions` SHALL add to every position a `trend` object with the keys `15m`, `2h` and `1d`. For each
window it SHALL contain `base_ms` (the reference round), the position's earlier `szi`, `position_value` and
`upnl`, and `opened: true` when the position did not exist in the reference round (earlier values then being 0).

#### Scenario: Enough history
- **WHEN** rounds exist 130, 20, 16, 1 and 0 minutes before the latest round and BTC had sizes -1, -2, -3, -4, -5
- **THEN** BTC's `15m` reference is the round 16 minutes back (size -3) and its `2h` reference the round 130 minutes
  back (size -1)

#### Scenario: Position opened within the window
- **WHEN** a coin is missing in the reference round
- **THEN** its trend has `opened: true` and earlier size 0

### Requirement: Trend reference round
For each window the reference round SHALL be the newest stored round at or before `latest_round - window`. The
trend for that window SHALL be `null` when no such round exists or when it is older than 1.5 times the window
(history too short, or a gap in collection).

#### Scenario: Not enough history
- **WHEN** the oldest stored round is only 20 minutes old
- **THEN** the `2h` and `1d` trends are `null` and the `15m` trend is present

#### Scenario: Gap in collection
- **WHEN** the newest round at or before the 15-minute target is 60 minutes old
- **THEN** the `15m` trend is `null`

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

### Requirement: Wallets panel
The page SHALL have a **Wallets** button that opens a panel listing the tracked wallets (label, shortened address)
with a Remove button each, and a form to add a wallet: address, optional label, and a "collect fills" checkbox.
Remove SHALL need a second confirming click (no browser dialogs). After adding, the new wallet SHALL be selected;
after removing the selected wallet, the first remaining one SHALL be selected. Errors from the API SHALL be shown
in the panel.

#### Scenario: Add a wallet
- **WHEN** the user enters a valid address and presses Add
- **THEN** the wallet appears in the list and in the wallet selector, and data arrives within one collection round

#### Scenario: Remove a wallet
- **WHEN** the user presses Remove and then Confirm
- **THEN** the wallet disappears from the list and the selector, while its stored history stays in the database

### Requirement: Wallet management API
`POST /api/wallets` with `{"address", "label"?, "fills"?}` SHALL add a wallet and `POST /api/wallets/remove` with
`{"address"}` SHALL remove one, by rewriting `config.json` atomically (temporary file, then replace) and keeping
its other keys. The address SHALL be `0x` followed by 40 hex digits and is stored lower-case; the label defaults
to the shortened address and is at most 40 characters. The response SHALL be the new list of wallets.

#### Scenario: Invalid address
- **WHEN** the address is not `0x` plus 40 hex digits
- **THEN** the answer is HTTP 400 and `config.json` is unchanged

#### Scenario: Duplicate and unknown
- **WHEN** an already tracked address is added
- **THEN** the answer is HTTP 409
- **AND** removing an address that is not tracked answers HTTP 404

#### Scenario: Broken configuration file
- **WHEN** `config.json` cannot be parsed
- **THEN** the answer is HTTP 400 and the file is not overwritten

### Requirement: Write requests only from the page
Requests that change the configuration SHALL be accepted only with `Content-Type: application/json`, a `Host`
header of `127.0.0.1:<port>` or `localhost:<port>`, and, if an `Origin` header is present, an origin of the same
host and port. Others SHALL be answered with HTTP 403 and change nothing, so a web page opened in the same browser
cannot edit the configuration.

#### Scenario: Foreign origin
- **WHEN** a request carries `Origin: https://example.com`
- **THEN** the answer is HTTP 403 and `config.json` is unchanged

### Requirement: Range selector scope
The time range selector SHALL be labelled "Range" and have a tooltip stating that it sets the period shown in the
charts; the trend columns of the positions table SHALL NOT depend on it.

#### Scenario: Change range
- **WHEN** the user changes the range from 24 h to 7 d
- **THEN** the charts change and the 15 min / 2 h / 1 day trend columns stay the same
