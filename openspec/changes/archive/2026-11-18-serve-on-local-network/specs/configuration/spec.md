## ADDED Requirements

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
