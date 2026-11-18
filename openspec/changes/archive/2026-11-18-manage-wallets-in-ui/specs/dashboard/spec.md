## ADDED Requirements

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
