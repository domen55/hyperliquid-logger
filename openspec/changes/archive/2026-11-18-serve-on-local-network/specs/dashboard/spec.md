## RENAMED Requirements

- FROM: `### Requirement: Local-only server`
- TO: `### Requirement: Server address and static files`

## MODIFIED Requirements

### Requirement: Server address and static files
The application SHALL serve HTTP on the configured `host` (default `127.0.0.1`, this computer only; `0.0.0.0`
serves all network interfaces) and `port` (default 8765) from the same process that runs the collector, SHALL
answer with `Cache-Control: no-store`, and SHALL serve only `/` (the page) and `/chart.js` (a vendored Chart.js,
so the page works offline) as static files.

#### Scenario: Open the dashboard
- **WHEN** the user opens `http://127.0.0.1:8765/`
- **THEN** the page and its script load without internet access

#### Scenario: Other static path
- **WHEN** a path other than `/` or `/chart.js` outside `/api/` is requested
- **THEN** the server answers 404

#### Scenario: Another device on the network
- **WHEN** `host` is `0.0.0.0` and a phone on the same network opens `http://<computer IP>:8765/`
- **THEN** the dashboard loads and shows the data

### Requirement: Write requests only from the page
Requests that change the configuration SHALL be accepted only with `Content-Type: application/json` and, if an
`Origin` header is present, an origin equal to `http://` plus an allowed `Host` of this server. Others SHALL be
answered with HTTP 403 and change nothing, so a web page opened in the same browser cannot edit the configuration.

#### Scenario: Foreign origin
- **WHEN** a request carries `Origin: https://example.com`
- **THEN** the answer is HTTP 403 and `config.json` is unchanged

## ADDED Requirements

### Requirement: Allowed hosts
Every request SHALL be answered with HTTP 403 unless its `Host` header, with the port, is `127.0.0.1`, `localhost`,
`[::1]`, this computer's host name (also with `.local`), one of its IP addresses, or an entry of `allowed_hosts`
in the configuration. The answer SHALL list the addresses that work. This keeps other web sites from reading the
dashboard through the browser under a hostile name (DNS rebinding).

#### Scenario: Foreign Host header
- **WHEN** a request arrives with `Host: evil.example:8765`
- **THEN** the answer is HTTP 403 and names the addresses that can be used

#### Scenario: Computer's own address
- **WHEN** a request arrives with the computer's LAN IP and the port as `Host`
- **THEN** it is served normally

### Requirement: Editing only from this computer
Requests that change the configuration (adding or removing wallets) SHALL be accepted only from a loopback client
address, unless `allow_remote_edit` is true in the configuration, so other devices on the network get a read-only
dashboard by default. The refusal SHALL be HTTP 403 with a message saying how to allow it.

#### Scenario: Phone tries to add a wallet
- **WHEN** a request from another device adds a wallet and `allow_remote_edit` is false
- **THEN** the answer is HTTP 403 and `config.json` is unchanged

#### Scenario: Remote editing switched on
- **WHEN** `allow_remote_edit` is true and a request from another device passes the other checks
- **THEN** the wallet is added
