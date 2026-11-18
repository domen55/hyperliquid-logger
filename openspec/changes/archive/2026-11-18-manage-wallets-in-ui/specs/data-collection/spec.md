## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Empty wallet warning
When a wallet has no positions, zero equity, no open orders and no spot balances in a round, the collector SHALL
record a WARNING event naming the wallet and suggesting that the address may be wrong, and SHALL mark the wallet
with that note until data appears. It SHALL NOT fail the round.

#### Scenario: Mistyped address
- **WHEN** a valid-looking address that has never been used on Hyperliquid is tracked
- **THEN** each round records a WARNING `snapshot` event and the wallet shows the note on the dashboard
