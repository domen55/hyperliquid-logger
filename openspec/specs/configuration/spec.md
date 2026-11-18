# configuration Specification

## Purpose

Describe which wallets are tracked and how often, in one JSON file that can be edited while the application
runs.

## Requirements

### Requirement: Configuration file
The application SHALL read `config.json` (or `--config FILE`) with these keys and defaults: `addresses` (required
list), `interval_seconds` (300), `db` (`hyperliquid.sqlite`), `port` (8765), `fills` (false), `backfill_hours` (0),
`log_dir` (`logs`), `log_level` (`DEBUG`). Relative `db` and `log_dir` paths SHALL resolve against the
configuration file's folder.

#### Scenario: Minimal file
- **WHEN** the file contains only `addresses`
- **THEN** the defaults above apply

### Requirement: Wallet entries
Each address entry SHALL be a string or an object with `address`, optional `label` and optional `fills`.
Addresses SHALL be lower-cased. The label defaults to the shortened address (`0xabcd…1234`); `fills` defaults to
the global `fills` value.

#### Scenario: Per-wallet fills
- **WHEN** the global `fills` is false and one wallet sets `"fills": true`
- **THEN** fills are collected only for that wallet

### Requirement: Minimum interval
`interval_seconds` SHALL be at least 5 so the collector cannot flood the public API; lower values are raised
to 5.

#### Scenario: Too small interval
- **WHEN** `interval_seconds` is 1
- **THEN** the effective interval is 5 seconds

### Requirement: Live reload
The configuration SHALL be re-read before every round, so changes to `interval_seconds`, addresses, labels,
`fills` and `backfill_hours` apply without a restart. Saving the file during the wait SHALL end the wait and
start a new round at once; a save made while a round is running SHALL start the next round immediately after it
instead of one interval later. `db`, `port`, `log_dir` and `log_level` require a restart.

#### Scenario: Faster interval while developing
- **WHEN** `interval_seconds` is changed from 300 to 60 while the app runs
- **THEN** a new round starts immediately and later rounds are 60 s apart

#### Scenario: Wallet added while a round is running
- **WHEN** a wallet is added to the configuration during a round
- **THEN** the next round starts as soon as that round ends and already includes the new wallet

### Requirement: Invalid configuration file
A file that cannot be read or parsed SHALL be reported as an ERROR `config` event and the last valid
configuration kept, by the collector and by the dashboard API alike. The dashboard API SHALL keep answering
requests, and the error SHALL be reported once per change of the file, not once per request.

#### Scenario: Broken file
- **WHEN** the saved file contains invalid JSON
- **THEN** an ERROR `config` event is recorded and collection continues with the previous settings

#### Scenario: Dashboard while the file is broken
- **WHEN** the saved file contains invalid JSON and the dashboard requests `/api/status`
- **THEN** the request succeeds using the last valid configuration
- **AND** only one ERROR `config` event is recorded no matter how many requests arrive

#### Scenario: File fixed again
- **WHEN** the file is saved with valid content after being broken
- **THEN** the dashboard API uses the new configuration from the next request

### Requirement: Invalid file at startup
If the configuration file cannot be read or parsed when the application starts, the application SHALL refuse to
start, because there is no earlier configuration to fall back to.

#### Scenario: Invalid at startup
- **WHEN** the application starts and the file is invalid
- **THEN** it exits with the parse error instead of serving

### Requirement: Development setting
The shipped `config.json` SHALL use a 60 second interval while the project is under development; the default
for production use is 300 seconds (5 minutes).

#### Scenario: Shipped file
- **WHEN** the project is checked out
- **THEN** `config.json` has `interval_seconds: 60`

### Requirement: Network settings
The configuration SHALL accept `host` (default `127.0.0.1`), `allow_remote_edit` (default false) and
`allowed_hosts` (default empty list of extra `host:port` names accepted in the `Host` header). `host` and `port`
require a restart; `allow_remote_edit` and `allowed_hosts` apply to the next request.

#### Scenario: Default
- **WHEN** the file does not mention `host`
- **THEN** the server listens on `127.0.0.1` only

#### Scenario: Reachable from the network
- **WHEN** `host` is `0.0.0.0`
- **THEN** the server listens on all interfaces after the next start
