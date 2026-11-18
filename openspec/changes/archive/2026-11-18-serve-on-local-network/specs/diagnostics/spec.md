## ADDED Requirements

### Requirement: Dashboard URLs and exposure notice
The start banner and `--check` SHALL list the URLs under which the dashboard can be opened (loopback and, when the
host is not loopback-only, this computer's LAN addresses). When the server is reachable from the network they SHALL
state that the dashboard has no password, whether editing from other devices is on, and that the Windows Firewall
may need to allow Python on private networks.

#### Scenario: Exposed on the network
- **WHEN** `host` is `0.0.0.0`
- **THEN** the banner shows `http://127.0.0.1:8765` and `http://<LAN IP>:8765` and the no-password notice

#### Scenario: Local only
- **WHEN** `host` is `127.0.0.1`
- **THEN** only the loopback URL is listed and no exposure notice is shown
