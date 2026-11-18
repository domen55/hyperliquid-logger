## MODIFIED Requirements

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
