## MODIFIED Requirements

### Requirement: Live reload
The configuration SHALL be re-read before every round, so changes to `interval_seconds`, addresses, labels,
`fills` and `backfill_hours` apply without a restart. Saving the file during the wait SHALL end the wait and
start a new round at once. A file that cannot be read or parsed SHALL be reported as an error event and the
previous configuration kept, both by the collector and by the dashboard API, which SHALL keep answering
requests with the last valid configuration; the error SHALL be reported once per change of the file, not once
per request. `db`, `port`, `log_dir` and `log_level` require a restart. If the file is invalid at startup the
application SHALL refuse to start.

#### Scenario: Faster interval while developing
- **WHEN** `interval_seconds` is changed from 300 to 60 while the app runs
- **THEN** a new round starts immediately and later rounds are 60 s apart

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

#### Scenario: Invalid at startup
- **WHEN** the application starts and the file is invalid
- **THEN** it exits with the parse error instead of serving
